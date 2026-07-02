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
import re
import subprocess
from typing import Any, Callable

from framework.acting import loop

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


def extract_pid(quoted: str, text: str = "") -> str | None:
    """Pid from the replied-to message (primary) or the reply itself (rare)."""
    for source in (quoted or "", text or ""):
        m = _PID_RE.search(source)
        if m:
            return m.group(1)
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
        pid = extract_pid(quoted, text)
        if not pid:
            return {"handled": False, "reason": "no-pid"}

        pending = pending_source() if pending_source is not None else loop.pending_proposals()
        by_id = {loop.proposal_id(p): p for p in pending if isinstance(p, dict)}
        proposal = by_id.get(pid)
        if proposal is None:
            # Marker present but no open proposal (already decided / expired /
            # foreign marker). Passthrough — the Chair can still reason about it.
            return {"handled": False, "reason": "no-pending-match", "pid": pid}

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
                from framework.frontdoor import chair_drafts
                fn = chair_drafts.deliver_draft
            else:
                fn = deliver
            override = routed.edit_text if routed.primary == "edit" else ""
            delivery["attempted"] = True
            try:
                delivery["result"] = fn(pid, override_text=override or "")
            except Exception as e:  # record the failure; verdict already landed
                delivery["result"] = {"ok": False, "error": str(e)[:200]}

        from datetime import datetime, timezone
        kwargs = {"proposal": proposal, "reply_text": text,
                  "dispatch": _dispatch, "draft": draft_text,
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
                "delivery": delivery.get("result"), "pid": pid, "summary": summary}
    except Exception as e:  # NEVER break Captain-DM passthrough
        log(f"binder-wire error (passthrough preserved): {e!r}")
        return {"handled": False, "reason": f"error: {e!r}"}
