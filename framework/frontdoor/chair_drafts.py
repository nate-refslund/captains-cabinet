"""Chair-owned draft flow.

Captain directive (2026-06-24, "make the drafts end here in this chat"): ALL
outbound drafts present in the Chair chat (the Captain's HQ Chair bot) via present_draft()
and deliver post-approval via deliver_draft(). The personal-source bot is no
longer in the approval path — it is back-end (capture/index) only.

SRC-3 (source-adapter boundary): the SEND execution (email_lib / teams_graph_lib
over Microsoft Graph) + the signature helper (draft_lib.ensure_signature) are
re-homed behind framework.sources.get_dispatch() — the Flavor-A dispatch
implementation OWNS the adapter's send libs, byte-identical to what ran when
they were imported here; framework names no adapter-specific lib and carries
no adapter-specific path. This module keeps the cabinet-side orchestration:
present the draft, store/clear the redis draft record, and (post-approval)
call the dispatch to send.

Approval gate is preserved: deliver_draft() is the egress and runs ONLY after
the Captain replies 'send' to a presented draft in the Chair chat. The Chair reply
handler (cos session, via the inbound watchdog's reply-threading) maps a
'send'/'edit:'/'skip:' reply back to the pid and calls deliver_draft().
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone

from framework.frontdoor import channel
from framework.sources import get_dispatch

_REDIS_H = os.environ.get("REDIS_HOST", "localhost")


def _r(*args: str) -> str:
    return subprocess.run(
        ["redis-cli", "-h", _REDIS_H, *args], capture_output=True, text=True
    ).stdout.strip()


def present_draft(person: str, channel_name: str, draft: str,
                  recipient_email: str = "", subject: str = "",
                  why: str = "", slug: str = "") -> str:
    """Present a draft in the Chair chat with a short pid; store it for delivery.

    Returns the pid. The Captain replies 'send' (or 'send <pid>') in the Chair chat to
    deliver, 'edit: <text>' to send his version, 'skip: <why>' to drop it.

    The draft is signed via the dispatch (get_dispatch().ensure_signature —
    Flavor-A: draft_lib.ensure_signature, idempotent, email only; a null/clean-room
    dispatch returns it unchanged), so the SIGNED text is what is both shown and
    stored for verbatim send.
    """
    draft = get_dispatch().ensure_signature(draft, channel_name)
    pid = hashlib.sha1(f"{person}{draft}{time.time()}".encode()).hexdigest()[:6]
    payload = {
        "slug": slug or person.lower().replace(" ", "-"),
        "person": person, "draft": draft, "channel": channel_name,
        "recipient_email": recipient_email, "subject": subject,
        "last_subject": subject, "why": why, "lane": "send-1to1-reply",
        # queued_ts anchors the verify-at-fire re-gather (fire_gate): "did the
        # captain reply on this thread AFTER this draft was queued?" needs the
        # queue moment as its clock (captain-surface §3.5, 2026-07-10).
        "queued_ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _r("SET", f"cabinet:draft:{pid}", json.dumps(payload, ensure_ascii=False),
       "EX", "604800")
    via = "Teams" if channel_name.lower() == "teams" else "email"
    dest = f" <{recipient_email}>" if recipient_email else ""
    # B-2 defense-in-depth (cp2 re-review 2026-07-03): strip the marker char from
    # the (possibly external) display name so it can't forge a second ·…· marker.
    safe_person = (person or "").replace("·", "")
    blocks = [f"✍️ Draft {via} to *{safe_person}*{dest}  ·{pid}·", "", draft]
    if why:
        blocks += ["", f"_{why}_"]
    blocks += ["", f"Reply *send* / *edit: <text>* / *skip: <why>*  (or `send {pid}`)"]
    channel.send("\n".join(blocks))
    return pid


def deliver_draft(pid: str, override_text: str = "", dry_run: bool = False,
                  force: bool = False) -> dict:
    """Send the stored draft via the Flavor-A dispatch. Post-approval egress —
    call ONLY after the Captain approved in the Chair chat. Clears the draft on a
    real send.

    The redis draft GET/DEL stays cabinet-side here; the actual send execution
    (Graph thread-resolution, reply-vs-fresh, verify-sent, email_lib.send_email /
    teams_graph_lib.send_teams_to_email) lives in the Flavor-A dispatch
    implementation (get_dispatch().deliver), byte-identical to the former
    inline path. On a clean-room / Flavor-B box the null dispatch no-ops
    (returns None) → treated as "no dispatch", nothing sends, the draft is
    retained.

    dry_run=True wires everything (subject calc, env, import the send lib) but does
    NOT send — used to verify the path without an actual egress.

    VERIFY-AT-FIRE (captain-surface §3.5, 2026-07-10 — the Casey case): right
    before the egress, ``fire_gate.verify_at_fire`` re-gathers through the
    personal-sensing seam; on POSITIVE evidence the thread was already handled
    (the captain replied himself / no longer awaiting) the draft SELF-CANCELS —
    removed from the store, journaled (``draft_queue.journal_fire_cancel``),
    and the returned ``reason`` is a plain sentence the Chair relays. Honest
    uncertainty always fires (the captain's explicit approval is never vetoed
    on unknown). ``force=True`` (an explicit "send anyway") skips the gate.
    A withdrawn/superseded/self-cancelled pid returns its honest reason
    instead of the generic miss.
    """
    raw = _r("GET", f"cabinet:draft:{pid}")
    if not raw:
        # Withdrawn (or fire-cancelled) drafts get their real reason back —
        # the generic miss was the root of the Casey confusion.
        try:
            from framework.acting import draft_queue
            w = draft_queue.withdrawal_of(pid)
        except Exception:
            w = None
        if w:
            why = w.get("captain_reason") or w.get("reason") or "withdrawn"
            return {"ok": False, "withdrawn": True, "reason": why,
                    "error": f"draft {pid} was withdrawn — {why}"}
        return {"ok": False, "error": f"no draft {pid} (expired or already sent)"}
    p = json.loads(raw)

    from framework.acting import fire_gate
    verdict = fire_gate.verify_at_fire(p, pid=pid, force=force)
    if verdict.get("action") == "cancel" and not dry_run:
        _r("DEL", f"cabinet:draft:{pid}")
        try:
            from framework.acting import draft_queue
            draft_queue.journal_fire_cancel(pid, p, verdict)
        except Exception:
            pass
        return {"ok": False, "cancelled": True,
                "reason": verdict.get("captain_reason") or verdict.get("reason"),
                "verify": verdict}

    res = get_dispatch().deliver(record=p, override_text=override_text, dry_run=dry_run)
    if not isinstance(res, dict):
        # null/clean-room dispatch (no send backend) — never crash on None.
        res = {"ok": False, "error": f"no dispatch configured for {pid}"}
    # Surface the fire-time verification alongside the transport result
    # (additive key; on dry_run this includes a would-cancel verdict).
    res.setdefault("verify", {"action": verdict.get("action"),
                              "reason": verdict.get("reason")})
    # Clear the stored draft ONLY on a real (non-dry) successful send — exactly the
    # former deliver_draft behavior (dry_run returned before the DEL).
    if res.get("ok") and not res.get("dry_run"):
        _r("DEL", f"cabinet:draft:{pid}")
    return res
