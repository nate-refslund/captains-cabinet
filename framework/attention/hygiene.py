"""framework.attention.hygiene — closure propagation + queue-hygiene events.

The command-center prerequisite set (proposal 2026-07-10 §5) that turns
"CLOSURE:" from a 24th stream item into a VERB:

  H2 — ``propagate_closure``: ONE event retires everything a resolved
       situation left behind — the open ledger proposals (superseding close
       rows), the parked ``cabinet:action:<pid>`` Redis cards, the standing
       Telegram card state, and the captain-attention stream entries. Plus
       ``sweep_zombie_cards`` (the 3 observed 146h zombie keys, generalized:
       any parked Redis card whose ledger proposal is no longer open) and
       ``trim_forwarded_streams`` (the 23 never-trimmed stream items).
  H4 — ``supersede_stream_entry``: officer→captain streams get edit/replace
       semantics by situation ("supersedes my 10:10Z card" becomes XDEL of
       the superseded entry, not queue growth). Index:
       ``cabinet:attention:sit-index:<project>`` (situation_key → entry id).
  H6 — ``file_screenpipe_triage_row``: the C5 ruling as a ledger row — the
       screenpipe estate gate is EXCLUDED from room v1; its one-time triage
       is recorded, never silently double-counted. Idempotent (no-ops when
       the row already exists).

Closure semantics vs H5: an EXPIRY is a demotion (situations.py re-types
it); a CLOSURE here is deliberate — it writes BOTH the superseding ledger
close (so digest AWAITING legs stop counting it) AND a ``closure`` feed row
per situation (the verb situations.py treats as resolved). Silence never
closes; this function is only called on real resolution evidence (org-acted
via the overlay, Captain word, or world-proof).

All transports injectable; the Redis default is argv redis-cli (no shell).
Best-effort: hygiene must never brick a drain loop.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from framework.attention.situation import canonical_refs, path_grade

_SIT_INDEX_PREFIX = "cabinet:attention:sit-index:"
_ACTION_PREFIX = "cabinet:action:"
_ATTENTION_STREAM_PREFIX = "cabinet:captain-attention:"
_FORWARDED_SET = "cabinet:frontdoor:attention-forwarded"

_TRIAGE_ACTION = "screenpipe-gate-triage"


def _now_iso(now: "datetime | None" = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _redis(*args: str) -> str:
    from framework.attention.queue import _redis_argv
    return _redis_argv(*args)


# ---------------------------------------------------------------------------
# H2 — closure propagation
# ---------------------------------------------------------------------------

def _id_grade(refs: Iterable) -> frozenset:
    return frozenset(r for r in canonical_refs(refs) if not path_grade(r))


def propagate_closure(refs: Iterable, *, reason: str, by: str,
                      now: "datetime | None" = None,
                      ledger_rows: "list | None" = None,
                      emit: "Callable | None" = None,
                      append_feed: "Callable | None" = None,
                      redis_del: "Callable | None" = None,
                      standing: "dict | None" = None,
                      save_standing_fn: "Callable | None" = None) -> dict:
    """Retire EVERYTHING a resolved situation left behind, in one verb.

    ``refs``: the resolved situation's evidence refs (id-grade overlap binds).
    ``reason``/``by``: journaled provenance (e.g. "org-acted", "officer:cos").

    Per overlapping OPEN proposal: emit the superseding close row (ledger),
    append ONE ``closure`` feed row on its exact situation key (the view's
    resolve verb), DEL its parked cabinet:action card, and flip its standing
    card state. Returns counts. Never raises (per-item best-effort)."""
    from framework.acting.loop import expire_event, pending_proposals, proposal_id
    from framework.attention.situations import _key_of_row

    now_s = _now_iso(now)
    target = _id_grade(refs)
    if not target:
        return {"closed": 0, "reason": "no id-grade refs — nothing binds"}

    if ledger_rows is None:
        open_props = pending_proposals()
    else:
        open_props = pending_proposals(rows=ledger_rows)

    if emit is None:
        from framework.fidelity.consequence import emit_consequence
        emit = emit_consequence
    if append_feed is None:
        from framework.attention.feed import append_event
        append_feed = append_event
    if redis_del is None:
        redis_del = lambda key: _redis("DEL", key)          # noqa: E731
    persist_standing = standing is None
    if standing is None:
        from framework.attention.gate import load_standing
        standing = load_standing()
    if save_standing_fn is None:
        from framework.attention.gate import save_standing
        save_standing_fn = save_standing

    closed, keys_seen = 0, set()
    for prop in open_props:
        prop_refs = [r for r in (prop.get("refs") or []) if isinstance(r, str)]
        if not (_id_grade(prop_refs) & target):
            continue
        try:
            # decided_at = the proposal's own ts (the suppression clock,
            # loop.expire_event doctrine); reviewed_at = the real closure
            # moment. The H5 re-type would read a bare expire row as a
            # demotion — the paired closure FEED row below is what resolves
            # the situation (only a verb or world-proof closes).
            emit(**expire_event(prop, reviewed_at=now_s,
                                decided_at=prop.get("ts")))
        except Exception as e:                              # noqa: BLE001
            print(f"[hygiene] closure emit failed for "
                  f"{prop.get('subject')!r}: {e}", file=sys.stderr)
            continue
        closed += 1
        skey = _key_of_row(prop)
        if skey not in keys_seen:
            keys_seen.add(skey)
            try:
                append_feed({"direction": "in", "kind": "closure",
                             "situation_key": skey, "ts": now_s,
                             "closure_reason": str(reason)[:200],
                             "closed_by": str(by)[:80]})
            except Exception as e:                          # noqa: BLE001
                print(f"[hygiene] closure feed row failed for {skey}: {e}",
                      file=sys.stderr)
        try:
            redis_del(_ACTION_PREFIX + proposal_id(prop))
        except Exception:                                   # noqa: BLE001
            pass
        card = standing.get(skey)
        if isinstance(card, dict):
            card["state"] = "resolved"

    if closed and persist_standing:
        try:
            save_standing_fn(standing)
        except Exception as e:                              # noqa: BLE001
            print(f"[hygiene] standing save failed: {e}", file=sys.stderr)

    return {"closed": closed, "situations": sorted(keys_seen)}


def propagate_view_closures(view: "dict | None" = None, *,
                            by: str = "system:surface-drain",
                            **kw) -> dict:
    """H2 drain wiring (review 2026-07-10): fire ``propagate_closure`` for
    every situation the situations.py view itself derives as resolved/acted
    while overlapping ledger proposals remain OPEN — the Mercantila failure
    class (a CLOSURE that retires nothing). Called from the 300s surface
    drain; this is real-resolution evidence (a ``closure`` feed row or an
    un-reversed ``acted:*`` world row won the fold), never silence — so the
    silence-never-closes law holds. Extra kwargs pass through to
    ``propagate_closure`` (injectable transports for tests). Best-effort:
    never raises past stderr."""
    try:
        if view is None:
            from framework.attention.situations import build_view
            view = build_view()
        fired, closed = 0, 0
        for sit in (view or {}).values():
            state = sit.get("state")
            if state not in ("resolved", "acted"):
                continue
            if not sit.get("open_pids"):
                continue   # nothing left behind — closure already propagated
            reason = "org-acted" if state == "acted" else "view-resolved"
            out = propagate_closure(sit.get("refs") or [],
                                    reason=reason, by=by, **kw)
            fired += 1
            closed += int(out.get("closed") or 0)
        return {"situations": fired, "closed": closed}
    except Exception as e:                                  # noqa: BLE001
        print(f"[hygiene] view-closure propagation failed: {e}",
              file=sys.stderr)
        return {"situations": 0, "closed": 0, "error": str(e)}


def sweep_zombie_cards(*, ledger_rows: "list | None" = None,
                       redis_scan: "Callable | None" = None,
                       redis_del: "Callable | None" = None) -> dict:
    """DEL every parked ``cabinet:action:<pid>`` whose ledger proposal is no
    longer open (decided/expired situations whose Redis card outlived them —
    the observed 3×146h zombies, generalized + idempotent).

    Safe under a racing late approve: the binder refuses already-decided
    proposals BEFORE dispatch, so a swept key was unreachable anyway (the
    same argument as the lane's own DEL-on-expiry)."""
    from framework.acting.loop import pending_proposals, proposal_id

    if redis_scan is None:
        redis_scan = lambda: _redis(                        # noqa: E731
            "--scan", "--pattern", _ACTION_PREFIX + "*").splitlines()
    if redis_del is None:
        redis_del = lambda key: _redis("DEL", key)          # noqa: E731

    try:
        props = (pending_proposals() if ledger_rows is None
                 else pending_proposals(rows=ledger_rows))
        open_pids = {proposal_id(p) for p in props}
    except Exception as e:                                  # noqa: BLE001
        return {"swept": 0, "error": f"ledger unreadable: {e}"}

    swept = 0
    for key in redis_scan():
        key = str(key).strip()
        if not key.startswith(_ACTION_PREFIX):
            continue
        pid = key[len(_ACTION_PREFIX):]
        if not pid or pid.startswith("asks:"):
            continue
        if pid in open_pids:
            continue
        try:
            redis_del(key)
            swept += 1
        except Exception:                                   # noqa: BLE001
            continue
    return {"swept": swept, "open": len(open_pids)}


def trim_forwarded_streams(*, backend=None, count: int = 500) -> dict:
    """XDEL captain-attention stream entries already forwarded to the intake
    (H2: forwarded items live on in the intake/briefing — the stream copy is
    queue growth). Uses the drain's own forwarded-marker set, so an entry is
    only trimmed once its content provably reached the front door.

    Consumption-aware (2026-07-11 finding): forwarded is necessary but NOT
    sufficient — captain-attention.sh creates ``ceo-reader-<project>`` at
    push time (:97,140) and post-tool-use.sh §3b (:292-322) consumes it in
    single_ceo mode, so a LIVE consumer group may still be owed the entry.
    Every XDEL is therefore gated on ``ad._safe_to_trim`` (the same guard
    as the drain's own call sites): a live group still owes the entry
    (beyond its last-delivered-id under numeric (ms,seq) compare, or in its
    PEL) → skip; never-read groups are vestigial and never block (the
    stranded-card cleanup survives); probe errors skip the entry (fail
    safe — it retries on the next 300s sweep). The CEO-plane delivery
    contract outranks queue growth."""
    from framework.frontdoor import attention_drain as ad

    if backend is None:
        try:
            backend = ad._backend()
        except Exception:
            return {"trimmed": 0}

    trimmed, streams = 0, 0
    try:
        stream_keys = ad._discover_streams(backend)
    except Exception:
        return {"trimmed": 0}
    for stream in stream_keys:
        project = stream[len(_ATTENTION_STREAM_PREFIX):]
        streams += 1
        try:
            if ad._is_redispy(backend):
                rows = backend._c.xrange(stream, "-", "+", count=count)
                entry_ids = [(r[0] if isinstance(r[0], str) else
                              r[0].decode()) for r in rows]
            else:
                out = backend._run("XRANGE", stream, "-", "+",
                                   "COUNT", str(count), raw=True)
                entry_ids = [ln.strip() for ln in out.split("\n")
                             if ad.intake._looks_like_id(ln.strip())]
        except Exception:
            continue
        for entry_id in entry_ids:
            marker = f"{project}:{entry_id}"
            try:
                if not ad._already_forwarded(backend, marker):
                    continue
                # Consumption-aware guard (2026-07-11): never XDEL an entry
                # another LIVE consumer group (ceo-reader-<project>) still
                # owes. Guard-no / probe error → leave it for the next sweep.
                if not ad._safe_to_trim(backend, stream, entry_id):
                    continue
                if ad._is_redispy(backend):
                    backend._c.xdel(stream, entry_id)
                else:
                    backend._run("XDEL", stream, entry_id, raw=True)
                trimmed += 1
            except Exception:
                continue
    return {"trimmed": trimmed, "streams": streams}


# ---------------------------------------------------------------------------
# H4 — supersede-in-place for officer→captain streams
# ---------------------------------------------------------------------------

def stream_situation_key(fields: dict) -> str:
    """The situation key of a captain-attention card: canonical ids from its
    summary+body (prose-free identity), slug fallback on the summary."""
    from framework.attention.situation import situation_key
    return situation_key([str(fields.get("summary") or ""),
                          str(fields.get("body") or "")],
                         str(fields.get("summary") or ""))


def supersede_stream_entry(backend, project: str, skey: str,
                           new_entry_id: str) -> Optional[str]:
    """Edit/replace-by-situation for a captain-attention stream: if an earlier
    entry carried the SAME situation, XDEL it (supersede-in-place) and point
    the index at the new entry. Returns the superseded entry id or None.
    Best-effort; the index is rebuildable (next card re-seeds it)."""
    from framework.frontdoor import attention_drain as ad

    idx = _SIT_INDEX_PREFIX + project
    old = None
    try:
        if ad._is_redispy(backend):
            raw = backend._c.hget(idx, skey)
            old = raw if raw is None or isinstance(raw, str) else raw.decode()
        else:
            out = backend._run("HGET", idx, skey, raw=True).strip()
            old = out if out and out != "(nil)" else None
    except Exception:
        old = None

    superseded = None
    if old and old != new_entry_id:
        try:
            stream = _ATTENTION_STREAM_PREFIX + project
            if ad._is_redispy(backend):
                backend._c.xdel(stream, old)
            else:
                backend._run("XDEL", stream, old, raw=True)
            superseded = old
        except Exception:
            superseded = None
    try:
        if ad._is_redispy(backend):
            backend._c.hset(idx, skey, new_entry_id)
        else:
            backend._run("HSET", idx, skey, new_entry_id, raw=True)
    except Exception:
        pass
    return superseded


# ---------------------------------------------------------------------------
# H6 — the C5 estate-gate triage, as a ledger row (record, not mechanism)
# ---------------------------------------------------------------------------

def file_screenpipe_triage_row(*, emit: "Callable | None" = None,
                               ledger_rows: "list | None" = None,
                               now: "datetime | None" = None) -> dict:
    """Record the C5 ruling ONCE: the screenpipe Telegram estate gate
    (161 unanswered, median 18.6d at measurement) is EXCLUDED from war-room
    v1; its one-time triage sweep is a Captain to-do, not a census row. A
    ledger row only — idempotent (no-op when the row already exists), so the
    estate is never silently double-counted into the census."""
    if ledger_rows is None:
        from framework.fidelity.consequence import read_ledger
        try:
            ledger_rows = read_ledger()
        except Exception:
            ledger_rows = []
    for row in ledger_rows:
        if isinstance(row, dict) and row.get("action") == _TRIAGE_ACTION:
            return {"filed": False, "reason": "already-recorded"}
    if emit is None:
        from framework.fidelity.consequence import emit_consequence
        emit = emit_consequence
    row = {
        "ts": _now_iso(now),
        # actor vocab is crew|officer|pipe — a mechanical producer is a pipe.
        "actor": {"kind": "pipe", "id": "war-room-hygiene"},
        "lane": None,
        "action": _TRIAGE_ACTION,
        "subject": ("screenpipe estate gate excluded from war-room v1 (C5); "
                    "one-time triage sweep queued as a Captain to-do"),
        "refs": ["kind:estate-triage"],
        "outcome": {"status": "ok",
                    "evidence": ("C5 Captain ruling 2026-07-10: exclude the "
                                 "screenpipe Telegram gate (161 unanswered, "
                                 "median 18.6d) from room v1; adapter-or-"
                                 "retire decision deferred to Stage 3")},
    }
    emit(**row)
    return {"filed": True}
