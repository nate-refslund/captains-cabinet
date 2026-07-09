"""framework.frontdoor.attention_drain — lane captain-attention cards → front-door intake.

GAP THIS CLOSES (2026-06-24): lane officers (polads-ceo, stephie-ceo, …) that
cannot DM the Captain card their decisions to a per-project Redis Stream
``cabinet:captain-attention:<project>`` (see cabinet/scripts/lib/captain-attention.sh).
In the portfolio preset NOTHING drained those streams to the Chair: the only
auto-scan (post-tool-use.sh §3b) is gated on ``OFFICER_NAME == CABINET_CEO_OFFICER``
in ``single_ceo`` bot mode, so for separate lane CEOs the cards sat stranded
(observed: 4 critical polads-ceo cards — Sentry blocker, DPA fix, deploy
approvals — never reached the Captain).

This module is the missing bridge. ``drain_attention()`` discovers every
``cabinet:captain-attention:<project>`` stream, reads each card via a DEDICATED
consumer group (``frontdoor-drain`` — distinct from the CEO's own
``ceo-reader-<project>`` group so it does NOT steal the CEO's delivery), maps the
card to a canonical front-door intake item, and ``intake.enqueue()``s it into
``cabinet:frontdoor:intake``. The existing ``surface.py`` loop (run every ~5 min
by com.cabinet.intake-surface) then surfaces ping-now items immediately and folds
batch/fyi into the next briefing — one voice, the architecture's intent.

Urgency mapping (captain-attention allowlist → intake urgency_tier):
    blocking, high  → ping-now   (time-critical; DM the Captain now)
    medium          → batch      (rides the next briefing's decision queue)
    low             → fyi        (digest only)

Durability + idempotency:
  * A dedicated consumer group means a card is delivered to the drainer exactly
    once; we XACK only AFTER a successful enqueue, so a crash mid-drain leaves
    the card pending for the next pass (never lost, §7 "nothing lost").
  * A belt-and-braces Redis SET (``cabinet:frontdoor:attention-forwarded``) of
    already-forwarded ``<project>:<entry_id>`` keys guards against a double
    enqueue even if the group is reset.

Dependency-light by design: reuses ``intake._redis()`` (redis-py when importable,
else a redis-cli subprocess) and adds only the few extra verbs it needs
(SCAN-by-pattern, XREADGROUP, XACK, SADD/SISMEMBER) via the same backend objects.
Best-effort: ``drain_attention()`` never raises — a malformed card or an
unreachable Redis degrades to "forwarded nothing" rather than bricking the
surface loop.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from framework.frontdoor import intake

# Per-project stream key prefix produced by captain-attention.sh.
_ATTENTION_PREFIX = "cabinet:captain-attention:"
# OUR consumer group — deliberately NOT the CEO's ceo-reader-<project> group.
_DRAIN_GROUP = "frontdoor-drain"
_DRAIN_CONSUMER = "chair"
# Idempotency ledger: SET of "<project>:<entry_id>" we have already enqueued.
_FORWARDED_SET = "cabinet:frontdoor:attention-forwarded"
# Slug contract shared across the Cabinet (FW-073…/captain-attention.sh).
_SLUG_MAX = 32

# captain-attention urgency → intake urgency_tier.
_URGENCY_TO_TIER = {
    "blocking": "ping-now",
    "high": "ping-now",
    "medium": "batch",
    "low": "fyi",
}
_DEFAULT_TIER = "batch"  # unknown/empty urgency → safe middle (rides the briefing).


# ---------------------------------------------------------------------------
# Slug guard — fail-closed before any slug reaches a Redis key (injection guard,
# mirrors captain-attention.sh _catn_validate_project).
# ---------------------------------------------------------------------------
def _valid_slug(slug: str) -> bool:
    if not slug or len(slug) > _SLUG_MAX:
        return False
    # ^[a-z0-9][a-z0-9-]*$ without importing re (cheap manual check).
    first = slug[0]
    if not (first.islower() or first.isdigit()):
        return False
    for ch in slug:
        if not (ch.islower() or ch.isdigit() or ch == "-"):
            return False
    return True


# ---------------------------------------------------------------------------
# Backend verbs we need beyond intake's surface. We talk to the SAME backend
# object intake builds (redis-py adapter or redis-cli subprocess) by reaching
# its underlying client / runner — keeping intake.py itself untouched.
# ---------------------------------------------------------------------------
def _backend():
    return intake._redis()


def _is_redispy(backend) -> bool:
    return backend.__class__.__name__ == "_RedisPyBackend"


def _discover_streams(backend) -> list[str]:
    """Return every cabinet:captain-attention:<project> stream key, slug-valid only."""
    keys: list[str] = []
    pattern = _ATTENTION_PREFIX + "*"
    try:
        if _is_redispy(backend):
            client = backend._c
            for k in client.scan_iter(match=pattern):  # type: ignore[attr-defined]
                keys.append(k if isinstance(k, str) else k.decode())
        else:
            # redis-cli backend: iterate SCAN cursor (argv only, no shell).
            cursor = "0"
            while True:
                out = backend._run(  # type: ignore[attr-defined]
                    "SCAN", cursor, "MATCH", pattern, "COUNT", "100", raw=True)
                lines = [ln for ln in out.split("\n") if ln != ""]
                if not lines:
                    break
                cursor = lines[0]
                keys.extend(lines[1:])
                if cursor == "0":
                    break
    except Exception:
        return []
    # Keep only well-formed keys whose project slug is valid.
    valid: list[str] = []
    seen: set[str] = set()
    for k in keys:
        if not k.startswith(_ATTENTION_PREFIX):
            continue
        proj = k[len(_ATTENTION_PREFIX):]
        if _valid_slug(proj) and k not in seen:
            seen.add(k)
            valid.append(k)
    return valid


def _ensure_group(backend, stream: str) -> None:
    try:
        if _is_redispy(backend):
            backend._c.xgroup_create(stream, _DRAIN_GROUP, id="0", mkstream=True)  # type: ignore[attr-defined]
        else:
            backend._run("XGROUP", "CREATE", stream, _DRAIN_GROUP, "0", "MKSTREAM")  # type: ignore[attr-defined]
    except Exception:
        pass  # BUSYGROUP — already exists.


# Canonical captain-attention card field names (the markers we split on). Their
# VALUES can contain embedded newlines (card bodies are multi-line), which is why
# intake._parse_cli_xread's line-pair heuristic mis-aligns ids↔values for these
# cards — it was built for intake's single-line JSON 'item' field. We parse cards
# field-aware instead, per single entry, so a multi-line body never bleeds into
# the next field or scrambles the entry id.
_CARD_FIELDS = ("source", "project", "urgency", "summary", "body", "ts")


def _parse_single_entry_fields(raw_lines: list[str]) -> dict:
    """Parse one XRANGE entry's flat field/value lines into {field: value}.

    ``raw_lines`` is the redis-cli --raw body for ONE entry: alternating field
    name / value lines, BUT a value may span multiple lines (card bodies do). We
    walk known field-name markers (_CARD_FIELDS): a line equal to a known field
    name starts a new field; everything until the NEXT known field-name marker is
    that field's (possibly multi-line) value. Unknown leading lines are ignored.
    """
    fields: dict[str, str] = {}
    cur: str | None = None
    buf: list[str] = []
    field_set = set(_CARD_FIELDS)
    for line in raw_lines:
        if line in field_set:
            if cur is not None:
                fields[cur] = "\n".join(buf).strip("\n")
            cur = line
            buf = []
        elif cur is not None:
            buf.append(line)
        # else: pre-first-field noise — skip.
    if cur is not None:
        fields[cur] = "\n".join(buf).strip("\n")
    return fields


def _read_group(backend, stream: str, start: str, count: int) -> list[tuple[str, dict]]:
    """XREADGROUP for OUR drain group at ``start`` ('>' = new, '0' = this
    consumer's pending/PEL): [(entry_id, {field: val}), ...].

    redis-py path returns proper field dicts directly. redis-cli path is parsed
    ROBUSTLY: XREADGROUP yields the entry IDs (single-line, parse-safe), then each
    id is read via XRANGE <id> <id> and parsed field-aware — this sidesteps the
    multi-line-value scramble in intake._parse_cli_xread for card streams.
    """
    _ensure_group(backend, stream)
    try:
        if _is_redispy(backend):
            res = backend._c.xreadgroup(  # type: ignore[attr-defined]
                _DRAIN_GROUP, _DRAIN_CONSUMER, {stream: start}, count=count)
            return intake._flatten_xread(res, stream)
        # redis-cli backend: deliver entries to our group, capture IDs only.
        out = backend._run(  # type: ignore[attr-defined]
            "XREADGROUP", "GROUP", _DRAIN_GROUP, _DRAIN_CONSUMER,
            "COUNT", str(count), "STREAMS", stream, start, raw=True)
        ids = [ln.strip() for ln in out.split("\n")
               if intake._looks_like_id(ln.strip())]
        rows: list[tuple[str, dict]] = []
        for entry_id in ids:
            entry_raw = backend._run(  # type: ignore[attr-defined]
                "XRANGE", stream, entry_id, entry_id, raw=True)
            lines = entry_raw.split("\n")
            # Drop the leading id echo line if present, and any trailing blank.
            lines = [ln for ln in lines if ln != ""]
            if lines and intake._looks_like_id(lines[0].strip()):
                lines = lines[1:]
            rows.append((entry_id, _parse_single_entry_fields(lines)))
        return rows
    except Exception:
        return []


def _read_new(backend, stream: str, count: int = 100) -> list[tuple[str, dict]]:
    """New (undelivered) entries plus a recovery sweep of THIS consumer's pending.

    Reading '0' first reclaims any entry delivered-but-not-ACKed on a prior pass
    (a crash mid-forward, or an XGROUP SETID artifact) so a card can never strand
    in the PEL — mirrors surface.py's drain_pending crash-recovery. Deduped by
    entry id, pending first (oldest), then new.
    """
    pending = _read_group(backend, stream, "0", count)
    fresh = _read_group(backend, stream, ">", count)
    out: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for entry_id, fields in pending + fresh:
        if entry_id in seen:
            continue
        seen.add(entry_id)
        out.append((entry_id, fields))
    return out


def _xack(backend, stream: str, entry_id: str) -> None:
    try:
        if _is_redispy(backend):
            backend._c.xack(stream, _DRAIN_GROUP, entry_id)  # type: ignore[attr-defined]
        else:
            backend._run("XACK", stream, _DRAIN_GROUP, entry_id, raw=True)  # type: ignore[attr-defined]
    except Exception:
        pass


def _xdel(backend, stream: str, entry_id: str) -> None:
    """H2 stream trim: retire a forwarded/duplicate card's stream copy. The
    content already reached the front door (intake + forwarded marker), so
    the stream row is pure queue growth. Best-effort — a failed XDEL just
    leaves the row for hygiene.trim_forwarded_streams to sweep later."""
    try:
        if _is_redispy(backend):
            backend._c.xdel(stream, entry_id)  # type: ignore[attr-defined]
        else:
            backend._run("XDEL", stream, entry_id, raw=True)  # type: ignore[attr-defined]
    except Exception:
        pass


def _already_forwarded(backend, marker: str) -> bool:
    try:
        if _is_redispy(backend):
            return bool(backend._c.sismember(_FORWARDED_SET, marker))  # type: ignore[attr-defined]
        out = backend._run("SISMEMBER", _FORWARDED_SET, marker, raw=True)  # type: ignore[attr-defined]
        return out.strip() == "1"
    except Exception:
        return False  # fail-open on the dedup check; the consumer group is the primary guard.


def _mark_forwarded(backend, marker: str) -> None:
    try:
        if _is_redispy(backend):
            backend._c.sadd(_FORWARDED_SET, marker)  # type: ignore[attr-defined]
        else:
            backend._run("SADD", _FORWARDED_SET, marker, raw=True)  # type: ignore[attr-defined]
    except Exception:
        pass


# ---------------------------------------------------------------------------
# SOV-6 — NEED-tagged / ask-shaped dedup + tier demote. The needs ledger is the
# canonical surface for standing asks (FI-3: deduped rows, blocking needs own
# their ping-now escalation), so a lane card duplicating one must not double-
# ping the Captain. DARK unless the needs plane is wired — the default world
# drains byte-identically.
# ---------------------------------------------------------------------------
_NEED_ID_RE = re.compile(r"\bNEED-([0-9a-f]{8})\b", re.IGNORECASE)
# Deliberately tight ask-lexicon: only unambiguous permission/grant asks demote
# (ping-now → batch); anything else keeps its carded urgency untouched.
_ASK_MARKERS = (
    "standing grant",
    "grant need-",
    "approval needed",
    "awaiting approval",
    "requires captain approval",
    "needs your approval",
    "permission needed",
)


def _needs_wired() -> bool:
    """True iff the needs plane is wired (sovereign / CABINET_NEEDS_WIRED /
    flag file). Lazy + fail-quiet: a broken needs module means OFF."""
    try:
        from framework.authority import needs
        return bool(needs.needs_enabled())
    except Exception:
        return False


def _card_need_id(card: dict) -> str | None:
    """The first NEED-<hex8> fingerprint tag in the card's summary/body,
    normalized to the ledger's lowercase-hex form, or None. Strict hex-only
    match — untrusted card text cannot mint a bindable tag any other way."""
    for f in ("summary", "body"):
        m = _NEED_ID_RE.search(str(card.get(f) or ""))
        if m:
            return "NEED-" + m.group(1).lower()
    return None


def _open_need_ids() -> set[str]:
    try:
        from framework.authority import needs
        return {str(r.get("id")) for r in needs.list_open()}
    except Exception:
        return set()


def _ask_shaped(card: dict) -> bool:
    text = ((card.get("summary") or "") + "\n" + (card.get("body") or "")).lower()
    return any(marker in text for marker in _ASK_MARKERS)


# ---------------------------------------------------------------------------
# Card → canonical intake item.
# ---------------------------------------------------------------------------
def card_to_item(card: dict, *, project: str,
                 needs_wired: bool = False) -> dict | None:
    """Map a captain-attention card to a front-door intake item, or None if unusable.

    Card fields (from captain-attention.sh): source, project, urgency, summary,
    body, ts. A card with no summary is unusable (intake requires a summary).
    ``needs_wired=True`` (SOV-6) demotes NEED-tagged / ask-shaped ping-now
    cards to batch — the needs digest is the canonical ask surface; the
    default (False) maps exactly as before.
    """
    summary = (card.get("summary") or "").strip()
    if not summary:
        return None
    urgency = (card.get("urgency") or "").strip().lower()
    tier = _URGENCY_TO_TIER.get(urgency, _DEFAULT_TIER)
    need_id = _card_need_id(card) if needs_wired else None
    if needs_wired and tier == "ping-now" and (need_id or _ask_shaped(card)):
        tier = "batch"
    origin = (card.get("source") or "unknown").strip() or "unknown"
    ts = (card.get("ts") or "").strip()
    if not ts:
        # intake requires a non-empty ts; fall back to now (ISO-8601 Z).
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = (card.get("body") or "").strip()

    payload: dict[str, Any] = {
        "summary": f"[{project}] {summary}",
        "detail": body,
        "project": project,
        "origin_officer": origin,
    }
    if need_id:
        payload["need_id"] = need_id
    return {
        "source": f"officer:{origin}",
        "kind": "captain-attention",
        "ts": ts,
        "urgency_tier": tier,
        "payload": payload,
        "context": {
            "why": f"lane officer {origin} carded a Captain decision for {project}",
            "sources": [f"{_ATTENTION_PREFIX}{project}"],
            "audience": None,
            "thread_ref": None,
        },
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def drain_attention(*, count: int = 100, only_projects: set[str] | None = None) -> dict:
    """Drain all cabinet:captain-attention:<project> cards into the front-door intake.

    For each discovered stream, reads NEW cards via the dedicated drain group,
    enqueues a mapped intake item, marks it forwarded, and ACKs the card. Never
    raises — returns a small dict of counts for logging.

    Override the intake target with env CABINET_FRONTDOOR_STREAM (tests do this).
    ``only_projects`` (test hook): when given, restricts the drain to those
    project slugs so a test never consumes a co-resident production stream — the
    drainer otherwise correctly discovers EVERY live captain-attention stream.
    """
    backend = _backend()
    try:
        streams = _discover_streams(backend)
    except Exception:
        streams = []
    if only_projects is not None:
        streams = [s for s in streams if s[len(_ATTENTION_PREFIX):] in only_projects]

    # SOV-6: computed once per drain — needs-aware dedup/demote arms only when
    # the needs plane is wired (default world byte-identical).
    wired = _needs_wired()
    open_ids = _open_need_ids() if wired else set()

    forwarded, skipped, by_project = 0, 0, {}
    for stream in streams:
        project = stream[len(_ATTENTION_PREFIX):]
        try:
            rows = _read_new(backend, stream, count=count)
        except Exception:
            rows = []
        for entry_id, fields in rows:
            marker = f"{project}:{entry_id}"
            # H4 (supersede-in-place): a re-card of a situation already in
            # this stream REPLACES it — the superseded entry is XDEL'd via
            # the per-project situation index instead of growing the queue
            # ("supersedes my 10:10Z card" as prose was queue growth).
            # Best-effort + lazy import (hygiene ↔ drain are call-time-only).
            try:
                from framework.attention import hygiene as _hyg
                _hyg.supersede_stream_entry(
                    backend, project, _hyg.stream_situation_key(fields),
                    entry_id)
            except Exception:
                pass
            # A card tagged with an OPEN need dedups on the need's fingerprint
            # id across projects/entries — the digest already surfaces the
            # need; only the FIRST card rides the briefing (demoted, see
            # card_to_item), later re-cards of the same need are dropped.
            need_marker = None
            if wired:
                nid = _card_need_id(fields)
                if nid and nid in open_ids:
                    need_marker = f"need:{nid}"
            if _already_forwarded(backend, marker) or (
                    need_marker and _already_forwarded(backend, need_marker)):
                _xack(backend, stream, entry_id)  # belt-and-braces: clear the dup
                _xdel(backend, stream, entry_id)  # H2: trim the dead copy
                skipped += 1
                continue
            item = card_to_item(fields, project=project, needs_wired=wired)
            if item is None:
                # Unusable card (no summary) — ACK so it doesn't redeliver forever.
                _xack(backend, stream, entry_id)
                _mark_forwarded(backend, marker)
                skipped += 1
                continue
            try:
                intake.enqueue(item)
            except Exception:
                # Enqueue failed — leave the card PENDING (no ACK) for next pass.
                continue
            _mark_forwarded(backend, marker)
            if need_marker:
                _mark_forwarded(backend, need_marker)
            _xack(backend, stream, entry_id)
            # H2 (trim forwarded streams): the card's content now lives in
            # the front-door intake + forwarded-marker set — the stream copy
            # is retired immediately instead of accumulating forever (the
            # observed 23 never-trimmed items; legacy backlog is swept by
            # hygiene.trim_forwarded_streams from the surface drain).
            _xdel(backend, stream, entry_id)
            forwarded += 1
            by_project[project] = by_project.get(project, 0) + 1

    return {
        "streams": len(streams),
        "forwarded": forwarded,
        "skipped": skipped,
        "by_project": by_project,
    }


if __name__ == "__main__":  # manual run / debugging
    print(json.dumps(drain_attention()))
