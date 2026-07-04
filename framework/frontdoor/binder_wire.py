"""Binder wire — MECHANICAL verdict capture at the Captain's inbound channel.

F0.5 (2026-07-02, plan docs/plans/): the single most load-bearing wire of the
program. Captain approve / edit: / skip: replies to a presented draft land as
SUPERSEDING consequence-ledger events IN-PROCESS with delivery — the Chair LLM
is out of the recording path (it still receives the DM afterwards for lesson
harvesting, but recording and delivery no longer depend on its discipline).

GERMLINE INVARIANT (gate-owns-ledger): presentation (the draft lane's
``·proposal-id·`` marker + ``cabinet:draft:<pid>`` store), decision delivery
(this wire, called by the inbound poller), and both ledger writes are ONE
component that migrates together. Any future channel migration moves them as a
unit — evidence continuity is never severed again (the twice-paid n=0 lesson).

FAIL-CLOSED ordering is inherited from ``loop.handle_response``: the
superseding event is emitted BEFORE dispatch is called, and dispatch receives
the draft ONLY on an explicit approve (loop FIX E). Our dispatch wrapper
additionally delivers ONLY on approve/edit — skip / policy-only / hold-downgraded
replies record their verdict and deliver nothing.

Every failure mode degrades to ``handled=False`` → the poller relays the DM to
the Chair exactly as before this wire existed. The Captain channel is
load-bearing; this module must never break passthrough.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from framework.acting import loop
from framework.fidelity.consequence import (
    emit_consequence, read_ledger, validate_consequence)

# The draft-lane presenter renders "·<proposal_id>·" where proposal_id is the
# identity tuple "actor.id|action|subject|ts" (loop.proposal_id). Match the
# marker content verbatim; single line, bounded length.
_PID_RE = re.compile(r"·([^·\n]{6,300})·")


def _redis_get(key: str, host: str = "localhost") -> str:
    out = subprocess.run(
        ["redis-cli", "-h", host, "GET", key],
        capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    return "" if out in ("", "(nil)") else out


def extract_pids(quoted: str, text: str = "") -> list[str]:
    """ALL pid markers found, in render order (quoted source before reply text).

    B-2 hardening (cp2 re-review 2026-07-03): a draft card embeds untrusted
    counterparty text ("they wrote: …") which a correspondent controls. The
    single-match extractor took the FIRST marker, so a `·fake·` planted in that
    text won. Callers cross-check these candidates against the OPEN proposal set
    and bind only a real one — a planted marker is not a pending pid, so it can
    neither bind nor mask the legitimate marker.
    """
    out: list[str] = []
    for source in (quoted or "", text or ""):
        out.extend(_PID_RE.findall(source))
    return out


def extract_pid(quoted: str, text: str = "") -> str | None:
    """Best single pid: the LAST marker. The legitimate pid renders last in the
    lane card (after quoted counterparty text); an injected marker renders
    earlier and must not win. Prefer extract_pids + a pending-set cross-check
    where the open set is available (see handle_captain_update)."""
    pids = extract_pids(quoted, text)
    return pids[-1] if pids else None


# =============================================================================
# UNDO-2 — the act-then-tell receipt grammar (acted-card verdicts).
#
# A DISTINCT reply grammar layered on the propose-card grammar above. When the
# Captain replies to an act-then-tell RECEIPT (an item the lane already executed,
# journaled with a ``cabinet:undo:<pid>`` pointer), the reply is a VERDICT on a
# landed act, not a decision on a pending draft:
#   👍 / ok / confirm   -> confirmed  (the ONLY promotion fuel)
#   undo / undo:<why>   -> wrong + reverse the artifact (mints a negative label)
#   edit:<text>         -> wrong + re-card via Chair (NEVER executes the edit)
#   never: / no more:   -> wrong + a server-derived veto scope (TI-4 persists it)
#   ok/undo <n>         -> the same, selecting a digest line by manifest index
#
# RT-A9 (unforgeable binding): an acted verb binds ONLY a server-issued opaque id
# — a ·pid· marker cross-checked against the ``cabinet:undo:<pid>`` pointer, or a
# ``cabinet:digest:<date>`` manifest index re-checked against that pointer. A
# ·fake· planted in untrusted quoted counterparty text has no server pointer, so
# it can neither bind nor mask the real one. Free text is NEVER matched.
#
# RT-B1 (routing): an acted pid routes through THIS branch — the acted branch
# runs BEFORE the pending-proposal lookup in handle_captain_update and returns
# None (falls through) for propose cards, so an acted pid NEVER reaches
# loop.handle_response and never counts as an approval.
# =============================================================================

_UNDO_RE = re.compile(r"^\s*(?:undo|revert|fortryd)\b\s*(\d+)?\s*[:,]?\s*(.*)$",
                      re.IGNORECASE | re.DOTALL)
# "never mind" / "nevermind" is a hold/cancel (loop._HOLD_CANCEL_RE), NOT a veto.
_NEVER_RE = re.compile(r"^\s*(?:never(?!\s*mind)|no more|stop doing)\b[:,]?\s*(.*)$",
                       re.IGNORECASE | re.DOTALL)
_EDIT_ACTED_RE = re.compile(r"^\s*edit\s*(\d+)?\s*:\s*(.+)$", re.IGNORECASE | re.DOTALL)
# Confirm token — a leading word or emoji, optional digest index. Deliberately
# the unambiguous set (loop._APPROVE_RE tokens minus "send", plus confirm/
# godkendt) so a mid-sentence "good/great" can't false-trigger a confirm on an
# acted receipt. The remainder is re-checked against loop's hold/negate guard so
# "ok but wait" is NOT a confirm.
_CONFIRM_LEAD_RE = re.compile(
    r"^\s*(?:(?:ok|okay|approved?|confirm(?:ed)?|yes|ja|godkendt)\b|[👍👌✅🚀])\s*(\d+)?",
    re.IGNORECASE)


@dataclass
class _ActedVerb:
    primary: str                 # "confirm" | "undo" | "edit" | "never"
    why: str = ""
    edit_text: str = ""
    category: str = ""           # never: free text — NEVER used for scope (server-side)
    index: Optional[int] = None  # digest-line index if the reply selected one


def _parse_acted_verb(text: str) -> Optional[_ActedVerb]:
    """Parse an acted-receipt verb, or None if the reply is not one (so the
    caller runs the propose-card path). Order: undo -> never -> edit -> confirm."""
    t = (text or "").strip()
    if not t:
        return None
    m = _UNDO_RE.match(t)
    if m:
        return _ActedVerb("undo", why=(m.group(2) or "").strip(),
                          index=int(m.group(1)) if m.group(1) else None)
    m = _NEVER_RE.match(t)
    if m:
        return _ActedVerb("never", category=(m.group(1) or "").strip())
    m = _EDIT_ACTED_RE.match(t)
    if m:
        return _ActedVerb("edit", edit_text=(m.group(2) or "").strip(),
                          index=int(m.group(1)) if m.group(1) else None)
    m = _CONFIRM_LEAD_RE.match(t)
    if m:
        remainder = t[m.end():].strip(" ,.-—\n")
        if loop._holds_or_negates_send(remainder):
            return None          # "ok but wait" — a hold, not a confirm
        return _ActedVerb("confirm", index=int(m.group(1)) if m.group(1) else None)
    return None


# The verdict specs the ONE builder applies. ``verdict None`` = review UNTOUCHED:
# ttl_ok is an OUTCOME label only (a machine outcome can never write a review),
# and PRESERVING the copied review is exactly what stops a TTL event erasing a 👍.
_ACTED_VERDICTS: Dict[str, Dict[str, Any]] = {
    "confirmed":     {"status": "ok",     "verdict": "confirmed", "source": "verdict_human",
                      "evidence": "captain confirmed acted card"},
    "undo":          {"status": "failed", "verdict": "wrong",     "source": "verdict_human",
                      "evidence": "captain-undo"},
    "edit":          {"status": "ok",     "verdict": "wrong",     "source": "verdict_human",
                      "evidence": "captain edited (re-card); acted artifact stands"},
    "never":         {"status": "ok",     "verdict": "wrong",     "source": "verdict_human",
                      "evidence": "captain veto (never); artifact stands, cell demoted"},
    "ttl_ok":        {"status": "ok",     "verdict": None,        "source": None,
                      "evidence": "ttl-48h survived; artifact intact; no reversal; no cascade flag"},
    "silent_revert": {"status": "failed", "verdict": "wrong",     "source": "verdict_judge",
                      "evidence": "silent revert: artifact missing without a captain undo"},
}


def acted_verdict_event(action_record: dict, verdict: str, *,
                        why: Optional[str] = None, evidence: Optional[str] = None,
                        reviewed_at: Optional[str] = None,
                        source: Optional[str] = None,
                        lesson_ref: Optional[str] = None) -> Dict[str, Any]:
    """The ONE read-modify-write superseding builder for acted cards [RT-B1].

    ``action_record`` is the CURRENT acted ledger row for the cell (or its base
    acted event when nothing has superseded it yet). Returns a superseding event
    on the SAME identity tuple (actor, action, subject, ts) — a field-preserving
    ``dict(action_record)`` copy with the verdict applied. ``proposal.decision``
    stays ``null`` forever (an unattended act was never proposed). ``ttl_ok``
    writes ONLY the outcome and PRESERVES the copied review, so a later
    TTL-survival machine event can never erase a landed human 👍. Both the binder
    (👍/undo) and the reconcile sweep (ttl_ok/silent_revert) build through THIS
    one function — the single guarantee that no verdict erases another. Validated
    before return; an invalid event is never emitted."""
    if verdict not in _ACTED_VERDICTS:
        raise ValueError(f"unknown acted verdict: {verdict!r}")
    spec = _ACTED_VERDICTS[verdict]
    ev = dict(action_record)
    ev["proposal"] = {"required": False, "decision": None}
    ev_evidence = evidence or spec["evidence"]
    if why:
        ev_evidence = f"{ev_evidence}: {why}"
    ev["outcome"] = {"status": spec["status"]}
    if spec["status"] in ("ok", "failed"):
        ev["outcome"]["evidence"] = ev_evidence[:500]
    rv = spec["verdict"]
    if rv is not None:
        review: Dict[str, Any] = {"verdict": rv, "source": source or spec["source"]}
        if reviewed_at:
            review["reviewed_at"] = reviewed_at
        if rv == "wrong" and lesson_ref:
            review["lesson_ref"] = lesson_ref
            # SIE-1: the superseding event also carries the lesson in refs, so
            # the ledger row → lesson-ledger join survives even readers that
            # only look at refs (the review object is verdict-plumbing).
            tag = f"lesson:{lesson_ref}"
            refs = list(ev.get("refs") or [])
            if tag not in refs:
                ev["refs"] = refs + [tag]
        ev["review"] = review
    # verdict == "ttl_ok": leave ev["review"] as-copied (preserved) [RT-B1].
    validate_consequence(ev)
    return ev


def veto_scope_from_record(record: dict) -> Dict[str, Any]:
    """A ``never:`` veto's scope, derived SERVER-SIDE from the stored acted
    record's deterministic fields (action_type + lane) — the reply text can never
    widen it [RT-A9/RT-A10]. The persistent veto registry (captain-vetoes.yml,
    three-layer enforcement) is TI-4's; this is the scope primitive it binds."""
    scope = {"action_type": record.get("action_type"), "lane": record.get("lane")}
    return {k: v for k, v in scope.items() if v is not None}


# =============================================================================
# TI-4 — the veto registry wiring (never: persist / lift / freeform confirm).
#
# The acted-receipt ``never:`` above returns a SERVER-DERIVED scope; TI-4 makes
# it durable. Three verbs bind framework.frontdoor.veto_registry:
#   never:  (on an acted receipt) -> record_veto(scope_from_record, verbatim)
#   never:  (freeform, no receipt) -> Chair-drafted `veto confirm` round-trip
#   lift veto-NNN                  -> lift_veto (retire, never delete)
#
# DARK by default (CABINET_VETO_WIRED != "1"): the verbs behave exactly as
# pre-TI-4 (the acted never: still returns its scope; it just persists nothing),
# so the registry stays empty until Nate's deployment flips the flag. And every
# write is gated on ``captain_verified`` — a veto is unforgeable, only from Nate
# (the inbound poller relays ONLY CAPTAIN_TELEGRAM_ID messages here). Off the
# Captain path, or dark, nothing is recorded regardless of what parses.
# =============================================================================

def _veto_recording_enabled() -> bool:
    return os.environ.get("CABINET_VETO_WIRED") == "1"


def _default_record_veto(scope: Dict[str, Any], verbatim: str, ts: str) -> Optional[dict]:
    if not _veto_recording_enabled():
        return None
    from framework.frontdoor import veto_registry
    return veto_registry.record_veto(scope, verbatim, ts)


def _default_lift_veto(veto_id: str, ts: str) -> Optional[dict]:
    if not _veto_recording_enabled():
        return None
    from framework.frontdoor import veto_registry
    return veto_registry.lift_veto(veto_id, ts)


def _default_redis_set(key: str, value: str) -> None:
    host = os.environ.get("REDIS_HOST", "localhost")
    subprocess.run(["redis-cli", "-h", host, "SET", key, value], timeout=10)


def _default_redis_del(key: str) -> None:
    host = os.environ.get("REDIS_HOST", "localhost")
    subprocess.run(["redis-cli", "-h", host, "DEL", key], timeout=10)


def _default_present(msg: str) -> None:
    from framework.frontdoor import channel
    channel.send(msg)


# `lift veto-NNN` retires a veto; `veto confirm [k=v]` commits a freeform veto's
# scope. STRICT deterministic scope args only — never a free-text→slug guess.
_LIFT_RE = re.compile(r"^\s*(?:lift|unveto|remove)\s+veto[-_ ]?0*(\d+)\b",
                      re.IGNORECASE)
_VETO_CONFIRM_RE = re.compile(r"^\s*veto\s+confirm\b(.*)$", re.IGNORECASE | re.DOTALL)
_SCOPE_ARG_RE = re.compile(r"\b(action_type|board|content_family)\s*=\s*([^\s,;]+)",
                           re.IGNORECASE)
_PENDING_VETO_KEY = "cabinet:veto-pending"


def _parse_scope_args(text: str) -> Dict[str, str]:
    """The allowed deterministic scope fields from a `veto confirm` reply, as
    literal key=value — never a slug inferred from prose [RT-A10]."""
    return {k.lower(): v.strip() for k, v in _SCOPE_ARG_RE.findall(text or "")}


# --- lazy production transports (all injectable; importing stays cheap) -------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _recent_dates(now: Optional[str]) -> List[str]:
    base = _parse_iso(now) or datetime.now(timezone.utc)
    return [(base - timedelta(days=d)).strftime("%Y-%m-%d") for d in (0, 1)]


def _default_reverse(pid: str) -> dict:
    from framework.frontdoor import action_undo
    return action_undo.reverse(pid)


def _default_freeze(kind: str, reason: str) -> dict:
    from framework.frontdoor import action_undo
    return action_undo.freeze(kind, reason)


def _default_journal_rows_for(*, pid: Optional[str] = None) -> List[dict]:
    from framework.frontdoor import action_undo
    return action_undo._read_journal(pid=pid)


def _default_list_undo_windows() -> List[str]:
    """Open undo windows = the live ``cabinet:undo:*`` pointers. Arg-list scan
    (never a shell string); best-effort — a scan failure yields no fallback."""
    host = os.environ.get("REDIS_HOST", "localhost")
    try:
        out = subprocess.run(
            ["redis-cli", "-h", host, "--scan", "--pattern", "cabinet:undo:*"],
            capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return []
    prefix = "cabinet:undo:"
    return [ln.strip()[len(prefix):] for ln in out.splitlines()
            if ln.strip().startswith(prefix)]


# --- acted-pid resolution (server-issued ids only) ---------------------------

def _manifest_lookup(manifest: Any, index: int) -> Optional[str]:
    """Resolve a digest-line index to its pid from the stored manifest. Accepts
    both the ``{"<index>": pid}`` and ``{"items":[{"index":n,"pid":..}]}`` shapes
    TI-5 may write; any other shape resolves to None."""
    if not isinstance(manifest, dict):
        return None
    v = manifest.get(str(index))
    if isinstance(v, str) and v:
        return v
    for it in (manifest.get("items") or []):
        if isinstance(it, dict) and it.get("index") == index and isinstance(it.get("pid"), str):
            return it["pid"]
    return None


def _digest_index_pid(index: int, *, redis_get: Callable[[str], str],
                      now: Optional[str]) -> Optional[str]:
    """The pid a digest-line index binds, via the server-written
    ``cabinet:digest:<date>`` manifest (today then yesterday). None if no
    manifest carries the index — the caller re-checks the pid against the undo
    pointer, so a stale manifest can never bind a non-acted pid."""
    for date_str in _recent_dates(now):
        try:
            raw = redis_get(f"cabinet:digest:{date_str}")
        except Exception:
            raw = ""
        if not raw:
            continue
        try:
            manifest = json.loads(raw)
        except (ValueError, TypeError):
            continue
        pid = _manifest_lookup(manifest, index)
        if pid:
            return pid
    return None


def _resolve_acted_pid(quoted: str, text: str, verb: _ActedVerb, *,
                       redis_get: Callable[[str], str], now: Optional[str],
                       list_undo_windows: Callable[[], List[str]],
                       log: Callable[[str], None]) -> Optional[str]:
    """The pid an acted verb binds — a SERVER-ISSUED opaque id only [RT-A9], or
    None (fall through / refuse). Priority: (1) a ·pid· marker present in the
    undo store; (2) a digest-index selector via the manifest, re-checked against
    the store — MANIFEST-OR-NOTHING; (3) a single-open fallback for BARE
    undo/never only (an explicit index never reaches it)."""
    def _has_undo(pid: str) -> bool:
        try:
            return bool(redis_get(f"cabinet:undo:{pid}"))
        except Exception:
            return False
    # 1. explicit ·pid· marker cross-checked against the server pointer. The
    #    legit pid renders last; a planted ·fake· has no pointer, so it is inert.
    for cand in reversed(extract_pids(quoted, text)):
        if _has_undo(cand):
            return cand
    # 2. digest-index selector -> manifest -> pid, re-checked against the pointer.
    #    MANIFEST-OR-NOTHING (checkpoint 07-04, undo-by-index verify): an explicit
    #    index names ONE rendered digest line. If no recent manifest carries it
    #    (unknown n) or the mapped pid's undo window is gone (stale n), the verb
    #    resolves to NOTHING — it must never fall to the single-open guess below,
    #    which could bind a DIFFERENT act than the line the Captain tapped.
    if verb.index is not None:
        pid = _digest_index_pid(verb.index, redis_get=redis_get, now=now)
        if pid and _has_undo(pid):
            return pid
        log(f"binder-wire: digest index {verb.index} unknown/stale — refused "
            "(manifest-or-nothing; no fallback)")
        return None
    # 3. single-open fallback: BARE undo/never ONLY (never a bare confirm — that
    #    is the propose-approve token), and only when exactly ONE window is open.
    if verb.primary in ("undo", "never"):
        try:
            wins = list(list_undo_windows())
        except Exception:
            wins = []
        if len(wins) == 1:
            log(f"binder-wire: acted no-pid fallback bound '{verb.primary}' to the "
                f"single open undo window {wins[0][:60]}")
            return wins[0]
    return None


# --- SIE-1 lesson capture (structured correction rows at the verdict seam) ----

def _default_capture_lesson(**kw: Any) -> Optional[dict]:
    from framework.frontdoor import action_lessons
    return action_lessons.capture_lesson(**kw)


def _capture_lesson_safe(capture: Callable[..., Any], *, pid: str, verdict: str,
                         captain_text: str, record: dict, ts: str,
                         log: Callable[[str], None]) -> Optional[str]:
    """Append ONE lesson row for a Captain correction verdict; return its
    lesson_ref, or None on ANY failure (logged). The lesson ledger is a
    downstream consumer of the verdict, never a gate on it — a capture failure
    must not break verdict recording or Captain-DM passthrough. ``captain_text``
    is passed VERBATIM (inert quoted data — see action_lessons header); the
    deterministic fields (action_type/lane/cid) come from the STORED record,
    never from the reply text, so a lesson can't be steered by phrasing."""
    try:
        from framework.probes import correlation
        cid = correlation.cid_from_refs(list(record.get("refs") or []))
    except Exception:
        cid = None
    try:
        row = capture(pid=str(pid), verdict=verdict, captain_text=captain_text,
                      cid=cid, action_type=record.get("action_type"),
                      lane=record.get("lane"), ts=ts)
        return (row or {}).get("lesson_ref")
    except Exception as e:
        log(f"binder-wire: lesson capture failed (verdict stands): {e!r}")
        return None


def _acted_records_for_pid(pid: str, *,
                           journal_rows_for: Callable[..., List[dict]],
                           read_ledger_fn: Callable[[], List[dict]]) -> List[tuple]:
    """The (journal_row, current_ledger_record) pairs for every EXECUTED step of
    a pid. The current record is the live superseded ledger state (matched by the
    acted event's identity tuple), falling back to the base acted event when the
    executor's emit has not landed a row yet (dark build) — so the verdict lands
    either way. Canary rows carry no ledger consequence and are excluded."""
    from framework.frontdoor import action_undo
    jrows = [r for r in journal_rows_for(pid=pid)
             if r.get("status") == "executed" and r.get("executed_at")
             and not r.get("canary")]
    if not jrows:
        return []
    by_identity = {loop.proposal_id(e): e for e in read_ledger_fn()}
    out: List[tuple] = []
    for r in jrows:
        base = action_undo.acted_event(None, r)
        out.append((r, by_identity.get(loop.proposal_id(base), base)))
    return out


def _apply_acted_verdict(pid: str, verb: _ActedVerb, *,
                         emit: Callable[..., Any], reverse: Callable[[str], dict],
                         freeze: Callable[[str, str], Any], now: str,
                         journal_rows_for: Callable[..., List[dict]],
                         read_ledger_fn: Callable[[], List[dict]],
                         record_veto: Callable[..., Any],
                         verbatim: str,
                         log: Callable[[str], None],
                         capture_lesson: Optional[Callable[..., Any]] = None) -> Optional[dict]:
    """Emit the superseding verdict(s) for every step of an acted pid, and (for
    undo) reverse the artifact — ledger verdict BEFORE reversal (fail-closed)."""
    records = _acted_records_for_pid(pid, journal_rows_for=journal_rows_for,
                                     read_ledger_fn=read_ledger_fn)
    if not records:
        return None      # pointer present but no executed rows — passthrough
    short = str(pid)[:40]

    # SIE-1: a correction verdict (undo/edit/never — never a confirm) appends
    # ONE structured lesson row BEFORE the superseding events are built, so its
    # lesson_ref can be stamped into review.lesson_ref + refs on every step's
    # event. Best-effort by contract: a lesson failure logs and yields
    # lesson_ref=None — the verdict itself is the load-bearing artifact and is
    # recorded regardless.
    lesson_ref: Optional[str] = None
    if verb.primary in ("undo", "edit", "never") and capture_lesson is not None:
        lesson_ref = _capture_lesson_safe(
            capture_lesson, pid=pid, verdict=verb.primary, captain_text=verbatim,
            record=records[0][1], ts=now, log=log)

    if verb.primary == "confirm":
        for _jrow, rec in records:
            emit(**acted_verdict_event(rec, "confirmed", reviewed_at=now))
        return {"handled": True, "acted": True, "primary": "confirm",
                "verdict": "confirmed", "pid": pid,
                "summary": f"acted: 👍 confirmed ·{short}· ({len(records)} step(s))"}

    if verb.primary == "edit":
        for _jrow, rec in records:
            emit(**acted_verdict_event(
                rec, "edit",
                evidence=f"captain edited (re-card): {verb.edit_text}"[:400],
                reviewed_at=now, lesson_ref=lesson_ref))
        return {"handled": True, "acted": True, "primary": "edit", "verdict": "wrong",
                "pid": pid, "recard": True, "correction": verb.edit_text,
                "lesson_ref": lesson_ref,
                "summary": f"acted: edit recorded wrong + re-card ·{short}· (NOT executed)"}

    if verb.primary == "never":
        scope = veto_scope_from_record(records[0][1])
        for _jrow, rec in records:
            emit(**acted_verdict_event(
                rec, "never", evidence=f"captain veto (never); scope={scope}",
                reviewed_at=now, lesson_ref=lesson_ref))
        out = {"handled": True, "acted": True, "primary": "never", "verdict": "wrong",
               "pid": pid, "veto_scope": scope, "lesson_ref": lesson_ref}
        # Persist to the veto registry (TI-4). record_veto is a no-op when the
        # veto wiring is dark / off the Captain path — the verdict + server-side
        # scope stand regardless. A scope with no enforceable field (e.g. a kind
        # whose classifier action_type isn't mapped yet — lane-only) is refused
        # by the registry; that raises and is caught here. A persist failure
        # NEVER breaks the verdict or Captain-DM passthrough (the invariant).
        veto_id, note = None, "registry dark"
        try:
            res = record_veto(scope, verbatim, now)
            if res:
                veto_id = res.get("id")
        except Exception as e:
            note = f"not persisted ({e})"
            log(f"binder-wire: veto persist failed (verdict stands): {e!r}")
        if veto_id:
            out["veto_id"] = veto_id
            out["summary"] = (f"acted: never-veto ·{short}· scope={scope} "
                              f"→ recorded {veto_id}")
        else:
            out["summary"] = (f"acted: never-veto ·{short}· scope={scope} "
                              f"(scope on ledger; {note})")
        return out

    # verb.primary == "undo": ledger verdict FIRST, THEN reverse (fail-closed —
    # if the reversal errors the wrong verdict has already recorded the intent).
    for _jrow, rec in records:
        emit(**acted_verdict_event(rec, "undo", why=verb.why or "no reason given",
                                   reviewed_at=now, lesson_ref=lesson_ref))
    kinds = sorted({r.get("kind") for r, _ in records if r.get("kind")})
    try:
        rev = reverse(pid)
    except Exception as e:  # a reversal crash still keeps the recorded verdict
        rev = {"ok": False, "error": str(e)[:200]}
    if not rev.get("ok"):
        for k in kinds:
            try:
                freeze(k, f"undo reversal failed for pid {pid}")
            except Exception:
                pass
        manual = rev.get("manual_cleanup") or rev.get("error") or "unknown"
        return {"handled": True, "acted": True, "primary": "undo", "verdict": "wrong",
                "pid": pid, "reversal": rev, "frozen": kinds, "lesson_ref": lesson_ref,
                "summary": f"acted: undo ·{short}· — REVERSAL FAILED — manual cleanup: "
                           f"{manual}; kind(s) frozen: {', '.join(kinds) or '-'}"}
    return {"handled": True, "acted": True, "primary": "undo", "verdict": "wrong",
            "pid": pid, "reversal": rev, "lesson_ref": lesson_ref,
            "summary": f"acted: undo ·{short}· reversed ({len(records)} step(s)); wrong recorded"}


def _route_acted_reply(text: str, quoted: str, *,
                       redis_get: Callable[[str], str], emit: Callable[..., Any],
                       reverse: Callable[[str], dict], freeze: Callable[[str, str], Any],
                       now: str, list_undo_windows: Callable[[], List[str]],
                       read_ledger_fn: Callable[[], List[dict]],
                       journal_rows_for: Callable[..., List[dict]],
                       record_veto: Callable[..., Any],
                       log: Callable[[str], None],
                       capture_lesson: Optional[Callable[..., Any]] = None) -> Optional[dict]:
    """Route a Captain reply that is an acted-receipt verdict; None if it is not
    (the caller then runs the propose-card path). RT-B1: never touches
    loop.handle_response. Only activates when an acted verb parses AND a
    server-issued acted id resolves — a propose card falls straight through."""
    verb = _parse_acted_verb(text)
    if verb is None:
        return None
    pid = _resolve_acted_pid(quoted, text, verb, redis_get=redis_get, now=now,
                             list_undo_windows=list_undo_windows, log=log)
    if pid is None:
        if verb.index is not None:
            # An EXPLICIT digest index that resolved to nothing is digest grammar
            # aimed at a line that no longer exists — REFUSE the whole reply
            # (handled=False → poller relays to the Chair, who asks). It must
            # NEVER fall through to the propose path: a stale "ok 2" landing as
            # a propose-approve could ship a pending draft the Captain never
            # looked at (the wrong-bind class this seam exists to kill).
            log(f"binder-wire: indexed verb '{verb.primary} {verb.index}' had no "
                "live manifest/undo binding — refused, relayed for disambiguation")
            return {"handled": False,
                    "reason": f"digest-index-stale ({verb.primary} {verb.index})"}
        return None      # no server-issued acted id — fall through to propose path
    return _apply_acted_verdict(pid, verb, emit=emit, reverse=reverse, freeze=freeze,
                                now=now, journal_rows_for=journal_rows_for,
                                read_ledger_fn=read_ledger_fn,
                                record_veto=record_veto, verbatim=text, log=log,
                                capture_lesson=capture_lesson)


# --- TI-4 veto commands (lift / freeform never confirm) ----------------------

def _open_pending_veto(text: str, *, present: Callable[[str], Any],
                       redis_set: Callable[[str, str], Any], now: str,
                       log: Callable[[str], None]) -> dict:
    """A freeform ``never:`` (no acted receipt to derive scope from) can't be
    enforced without a deterministic scope, so it opens a confirm-pending state:
    stash the verbatim and ask the Captain to pin the scope with `veto confirm
    action_type=… [board=…]`. Nothing is recorded until he confirms."""
    pending = {"verbatim": text, "scope": {}, "ts": now}
    try:
        redis_set(_PENDING_VETO_KEY, json.dumps(pending, ensure_ascii=False))
    except Exception as e:
        log(f"binder-wire: veto-pending store failed: {e!r}")
    try:
        present("🛑 Veto noted — it needs a scope to enforce. Reply "
                "`veto confirm action_type=<kind> [board=<id>]` to record it, "
                f"or ignore to drop.\n«{(text or '')[:200]}»")
    except Exception as e:
        log(f"binder-wire: veto-pending present failed: {e!r}")
    return {"handled": True, "veto": "pending",
            "summary": "freeform veto pending — awaiting `veto confirm`"}


def _confirm_pending_veto(arg_text: str, *, record_veto: Callable[..., Any],
                          present: Callable[[str], Any], redis_get: Callable[[str], str],
                          redis_del: Callable[[str], Any], now: str,
                          log: Callable[[str], None]) -> dict:
    """Commit the pending freeform veto — scope pinned from the confirm reply's
    STRICT deterministic key=value args (never a slug), merged over any pending
    scope. Refuses a scopeless confirm (keeps it pending)."""
    try:
        raw = redis_get(_PENDING_VETO_KEY)
    except Exception:
        raw = ""
    if not raw:
        return {"handled": True, "veto": "confirm-none",
                "summary": "veto confirm — nothing pending"}
    try:
        pending = json.loads(raw)
    except Exception:
        pending = {"verbatim": "", "scope": {}}
    scope = dict(pending.get("scope") or {})
    scope.update(_parse_scope_args(arg_text))
    if not any(scope.get(f) for f in ("action_type", "board", "content_family")):
        try:
            present("Veto needs a deterministic field. Reply "
                    "`veto confirm action_type=<kind> [board=<id>]`.")
        except Exception:
            pass
        return {"handled": True, "veto": "confirm-need-scope",
                "summary": "veto confirm — need action_type/board (kept pending)"}
    try:
        veto = record_veto(scope, pending.get("verbatim", ""), now)
    except Exception as e:
        log(f"binder-wire: veto confirm persist failed: {e!r}")
        return {"handled": True, "veto": "confirm-error",
                "summary": f"veto confirm failed: {e!r}"}
    try:
        redis_del(_PENDING_VETO_KEY)
    except Exception:
        pass
    vid = (veto or {}).get("id")
    return {"handled": True, "veto": "confirmed", "veto_id": vid, "veto_scope": scope,
            "summary": f"veto recorded {vid} scope={scope}" if vid
                       else f"veto confirm — registry dark; scope={scope}"}


def _route_veto_command(text: str, *, record_veto: Callable[..., Any],
                        lift_veto: Callable[..., Any], present: Callable[[str], Any],
                        redis_get: Callable[[str], str], redis_set: Callable[[str, str], Any],
                        redis_del: Callable[[str], Any], now: str,
                        log: Callable[[str], None]) -> Optional[dict]:
    """`lift veto-NNN` / `veto confirm` / freeform `never:` → the veto registry.
    None (fall through) for anything else. Reached only when veto wiring is
    active AND captain_verified (handle_captain_update gate), so every write here
    is Captain-authored [unforgeable]. A pid-bound `never:` was already handled
    by the acted branch upstream — this sees only the freeform case."""
    t = (text or "").strip()
    m = _LIFT_RE.match(t)
    if m:
        vid = f"veto-{int(m.group(1)):03d}"
        try:
            res = lift_veto(vid, now)
        except Exception as e:
            log(f"binder-wire: veto lift failed: {e!r}")
            res = None
        return {"handled": True, "veto": "lift", "veto_id": vid,
                "summary": (f"veto {vid} lifted" if res
                            else f"veto lift: {vid} not found / dark (nothing lifted)")}
    m = _VETO_CONFIRM_RE.match(t)
    if m:
        return _confirm_pending_veto(m.group(1) or "", record_veto=record_veto,
                                     present=present, redis_get=redis_get,
                                     redis_del=redis_del, now=now, log=log)
    if _NEVER_RE.match(t):
        return _open_pending_veto(t, present=present, redis_set=redis_set,
                                  now=now, log=log)
    return None


def handle_captain_update(
    text: str,
    quoted: str,
    *,
    pending_source: Callable[[], list] | None = None,
    deliver: Callable[..., dict] | None = None,
    emit: Callable[..., Any] | None = None,
    redis_get: Callable[[str], str] = _redis_get,
    log: Callable[[str], None] = lambda m: None,
    reverse: Callable[[str], dict] | None = None,
    freeze: Callable[[str, str], Any] | None = None,
    now: str | None = None,
    list_undo_windows: Callable[[], List[str]] | None = None,
    read_ledger_fn: Callable[[], List[dict]] | None = None,
    journal_rows_for: Callable[..., List[dict]] | None = None,
    record_veto: Callable[..., Any] | None = None,
    lift_veto: Callable[..., Any] | None = None,
    present: Callable[[str], Any] | None = None,
    redis_set: Callable[[str, str], Any] | None = None,
    redis_del: Callable[[str], Any] | None = None,
    captain_verified: bool = True,
    capture_lesson: Callable[..., Any] | None = None,
) -> dict:
    """Bind a Captain reply to its pending draft proposal; record, then deliver.

    Returns {"handled": bool, ...}. handled=False ⇒ caller relays the DM
    unchanged (byte-identical passthrough behavior). handled=True carries:
    status (decided/expired/already-decided), verdict (confirmed/wrong/unknown
    when decided), primary (approve/edit/skip/none), delivery (dispatch result
    dict or None), pid, and summary (one line for the tmux relay prefix).

    All dependencies injectable for tests; production defaults resolve lazily
    so importing this module never touches redis/ledger.
    """
    try:
        now_s = now or _now_iso()
        # TI-4: veto writes bind ONLY on the Captain-verified path — a veto is
        # unforgeable (the inbound poller relays only CAPTAIN_TELEGRAM_ID here).
        # Off that path the never:/lift verbs record nothing (a _noop), even if a
        # record_veto was injected; on it, the default is dark until
        # CABINET_VETO_WIRED=1. The veto-command branch (lift/confirm/freeform)
        # only arms when wiring is active, so the propose path is byte-identical
        # for every non-veto reply.
        def _noop(*_a: Any, **_k: Any) -> None:
            return None
        _rv = (record_veto or _default_record_veto) if captain_verified else _noop
        _lv = (lift_veto or _default_lift_veto) if captain_verified else _noop
        _veto_armed = captain_verified and (
            _veto_recording_enabled() or record_veto is not None
            or lift_veto is not None or present is not None)
        # SIE-1: lessons mirror verdict recording — captured wherever a
        # correction verdict lands (the poller only relays Captain messages
        # here). Injectable for tests; the default writes the lesson ledger
        # (CABINET_ACTION_LESSONS overrides the path).
        _cap = capture_lesson if capture_lesson is not None else _default_capture_lesson

        # --- UNDO-2 ACTED BRANCH (RT-B1): a reply binding a server-issued acted
        # id routes through the undo registry, NEVER loop.handle_response. Runs
        # BEFORE the pending-proposal lookup; returns None for propose cards, so
        # the propose path below is byte-identical for every non-acted reply. ---
        acted = _route_acted_reply(
            text, quoted, redis_get=redis_get,
            emit=emit if emit is not None else emit_consequence,
            reverse=reverse or _default_reverse, freeze=freeze or _default_freeze,
            now=now_s,
            list_undo_windows=list_undo_windows or _default_list_undo_windows,
            read_ledger_fn=read_ledger_fn or read_ledger,
            journal_rows_for=journal_rows_for or _default_journal_rows_for,
            record_veto=_rv, log=log, capture_lesson=_cap)
        if acted is not None:
            log(f"binder-wire: acted {acted.get('primary')} "
                f"pid={str(acted.get('pid'))[:60]} verdict={acted.get('verdict')}")
            return acted

        # --- TI-4 VETO COMMANDS: lift veto-NNN / veto confirm / freeform never:.
        # Armed only on the Captain-verified path with veto wiring live; a
        # pid-bound never: was already recorded by the acted branch above. ---
        if _veto_armed:
            veto = _route_veto_command(
                text, record_veto=_rv, lift_veto=_lv,
                present=present or _default_present,
                redis_get=redis_get, redis_set=redis_set or _default_redis_set,
                redis_del=redis_del or _default_redis_del, now=now_s, log=log)
            if veto is not None:
                log(f"binder-wire: veto {veto.get('veto')} -> {veto.get('summary')}")
                return veto

        candidates = extract_pids(quoted, text)
        pending = pending_source() if pending_source is not None else loop.pending_proposals()
        by_id = {loop.proposal_id(p): p for p in pending if isinstance(p, dict)}

        pid: str | None = None
        proposal = None
        if candidates:
            # B-2 (cp2 re-review 2026-07-03): bind the LAST marker that is a REAL open
            # proposal. Cards render the legit pid last (lane) or on the header line
            # (chair) — either way, only a marker present in by_id may bind, so a
            # `·fake·` a correspondent planted in quoted text is inert: not in by_id,
            # it is skipped, and it cannot mask the genuine proposal. pid retained
            # for logging/return (last candidate when none are open).
            pid = candidates[-1]
            for cand in reversed(candidates):
                if cand in by_id:
                    pid, proposal = cand, by_id[cand]
                    break
            if proposal is None:
                # Marker(s) present but none is an open proposal (already decided /
                # expired / foreign). Passthrough — the Chair can still reason on it.
                return {"handled": False, "reason": "no-pending-match", "pid": pid}
        else:
            # NO-PID FALLBACK (CRIT-1 2026-07-03): the first REAL Captain verdict
            # ("send") was eaten here — he replied to the Chair's argument message,
            # which carries no ·pid· marker, so the wire passed through and the
            # verdict never landed on the ledger. Bind mechanically ONLY when it is
            # unambiguous: the reply routes to a clear approve/edit/skip verdict AND
            # exactly ONE proposal is open. Anything else stays passthrough — with
            # multiple proposals open we never guess which one he meant; the Chair
            # (who receives the DM either way) disambiguates.
            routed_probe = loop.route_captain_response(text)
            if routed_probe.primary not in ("approve", "edit", "skip"):
                return {"handled": False, "reason": "no-pid"}
            if len(by_id) != 1:
                log(f"binder-wire: no-pid verdict '{routed_probe.primary}' with "
                    f"{len(by_id)} open proposals — not guessing, passthrough")
                return {"handled": False,
                        "reason": f"no-pid-ambiguous ({len(by_id)} open)"}
            pid, proposal = next(iter(by_id.items()))
            log(f"binder-wire: no-pid fallback bound '{routed_probe.primary}' to the "
                f"single open proposal pid={pid[:60]}")

        raw = redis_get(f"cabinet:draft:{pid}")
        stored = None
        if raw:
            try:
                stored = json.loads(raw)
            except Exception:
                stored = None
        draft_text = (stored or {}).get("draft") or None

        delivery: dict[str, Any] = {"attempted": False}

        def _dispatch(routed, draft, _proposal) -> None:
            # Deliver ONLY on approve/edit. handle_response has ALREADY emitted
            # the superseding ledger event by the time dispatch runs (fail-closed
            # ordering) — if the emit had raised, we would never get here.
            if routed.primary not in ("approve", "edit"):
                return
            if deliver is None:
                # PAYLOAD ROUTING (2026-07-03 pivot): an action card stores its
                # chain under cabinet:action:<pid>; a reply draft under
                # cabinet:draft:<pid>. Route by which record exists — same gate,
                # different executor. Action-first: the pivot lane is the live
                # one (draft lane parked by Captain ruling).
                if redis_get(f"cabinet:action:{pid}"):
                    from framework.frontdoor import action_exec
                    fn = action_exec.deliver_action
                else:
                    from framework.frontdoor import chair_drafts
                    fn = chair_drafts.deliver_draft
            else:
                fn = deliver
            override = ""
            if routed.primary == "edit":
                override = routed.edit_text or ""
                # cp2 edit-path (2026-07-03): give the Captain's edit the SAME
                # charset hygiene the AI draft got at creation (em/en-dash → -,
                # smart quotes → straight, … → ...), so a reply typed on mobile
                # doesn't egress with characters the draft path already strips.
                # Lazy import (screenpipe_adapter prints a module-load notice);
                # fail-OPEN to raw text — a normalization import must never block
                # a delivery whose verdict has already landed. This chokepoint is
                # inherited by the capture→action lane's edit path.
                try:
                    from framework.acting.screenpipe_adapter import normalize_voice
                    override = normalize_voice(override)
                except Exception:
                    pass
            delivery["attempted"] = True
            try:
                delivery["result"] = fn(pid, override_text=override or "")
            except Exception as e:  # record the failure; verdict already landed
                delivery["result"] = {"ok": False, "error": str(e)[:200]}

        # SIE-1 (propose seam): an `edit:`/`skip:` on a still-open proposal is a
        # correction verdict — append ONE structured lesson row and hand its ref
        # to handle_response so the superseding outcome event carries it
        # (review.lesson_ref where verdict=wrong, plus a refs entry). Pre-routing
        # here duplicates handle_response's own deterministic routing (same
        # function, same text — cannot diverge); an already-decided proposal is
        # skipped so an idempotent re-delivery never double-appends. Approvals
        # are not corrections — no lesson.
        lesson_ref: Optional[str] = None
        if (proposal.get("proposal") or {}).get("decision") is None:
            pre = loop.route_captain_response(text)
            if pre.primary in ("edit", "skip"):
                lesson_ref = _capture_lesson_safe(
                    _cap, pid=pid,
                    verdict="edit" if pre.primary == "edit" else "rejected",
                    captain_text=text, record=proposal, ts=now_s, log=log)

        from datetime import datetime, timezone
        kwargs = {"proposal": proposal, "reply_text": text,
                  "dispatch": _dispatch, "draft": draft_text,
                  "lesson_ref": lesson_ref,
                  # decided_at must be the DECISION time, not the proposal ts —
                  # approval-latency metrics (rubber-stamp detector, starvation
                  # windows) read this field.
                  "reviewed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        if emit is not None:
            kwargs["emit"] = emit
        result = loop.handle_response(**kwargs)

        res = delivery.get("result") or {}
        if result.get("status") == "already-decided":
            summary = f"binder: ·{pid[:40]}…· already decided — nothing recorded"
        elif delivery["attempted"]:
            ok = bool(res.get("ok"))
            via = res.get("via", "?")
            dest = res.get("dest", "?")
            summary = (
                f"binder: {result.get('primary')} recorded (verdict={result.get('verdict')}); "
                + (f"DELIVERED via {via} to {dest}" if ok
                   else f"delivery FAILED: {res.get('error', res.get('dry_run', 'unknown'))} — Chair: complete delivery, do NOT re-record")
            )
        else:
            summary = (f"binder: {result.get('primary') or result.get('status')} recorded"
                       f" (status={result.get('status')}); nothing delivered")
        log(f"binder-wire: pid={pid[:60]} status={result.get('status')} "
            f"primary={result.get('primary')} delivered={delivery['attempted']}")
        return {"handled": True, "status": result.get("status"),
                "verdict": result.get("verdict"), "primary": result.get("primary"),
                "delivery": delivery.get("result"), "pid": pid,
                "lesson_ref": lesson_ref, "summary": summary}
    except Exception as e:  # NEVER break Captain-DM passthrough
        log(f"binder-wire error (passthrough preserved): {e!r}")
        return {"handled": False, "reason": f"error: {e!r}"}
