"""framework.acting.fire_gate — verify-at-FIRE-time on the send path.

THE PRINCIPLE (captain-surface master prompt §3.5, 2026-07-10; standing
captain-pattern): verify-first at fire time, not just at enqueue. Between the
moment a draft was queued/approved and the moment it actually fires, the world
may have moved — the WORKED CASE: the captain replied to Alice himself, so the
queued draft must SELF-CANCEL, never fire. This generalizes the cabinet's
gather-then-decide discipline to the last instant of the send path.

The gate re-gathers through the personal-sensing seam
(``framework.sources.get_source()`` — never a hardcoded estate) at the moment
``chair_drafts.deliver_draft`` is about to egress:

  * ``captain_replied_since(slug, queued_at)`` is ``True``  → CANCEL
    (the captain already handled the thread himself — superseded by reality).
  * ``still_awaiting(slug)`` is ``False`` on a REPLY-lane record → CANCEL
    (the thread no longer needs this reply — resolved or closed).
  * anything else → FIRE.

FAIL-SAFE DIRECTION — cancel only on POSITIVE evidence. The captain explicitly
approved this send; honest uncertainty (tri-state ``None``, an unbound/null
source, a probe error) must never veto his explicit word. A sourceless
deployment therefore always fires (the approval gate upstream is unchanged).

The ``still_awaiting`` check is scoped to reply-lane records only: a future
proactive/outreach draft was never "awaiting" to begin with, and cancelling it
for that would wrongly block a legitimate approved send. Records missing a
``lane`` field are treated as replies (both current writers are reply flows).

Env: ``CABINET_VERIFY_AT_FIRE=0`` disables the gate (escape hatch; default ON —
it can only cancel on positive evidence, so ON is safe by construction).
``force=True`` (the caller's explicit override, e.g. a captain "send anyway")
skips the checks and records that it did.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone


def _parse_iso(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _is_reply(record: dict) -> bool:
    """Reply-lane record? Missing lane ⇒ reply (both current writers —
    ``chair_drafts.present_draft`` and ``run_draft_lane._store_draft`` — are
    reply flows; a future proactive writer must stamp a non-reply lane)."""
    lane = str((record or {}).get("lane") or "").strip()
    if not lane:
        return True
    return "reply" in lane


def _result(action: str, reason: str, checks: dict, record: dict) -> dict:
    person = str((record or {}).get("person") or
                 (record or {}).get("slug") or "them").strip() or "them"
    captain_reason = ""
    if action == "cancel":
        # PLAIN-LANGUAGE LAW (captain ruling 2026-07-10): this string reaches
        # the captain — one plain sentence, no internal vocabulary.
        if reason == "captain-already-replied":
            captain_reason = (f"Not sent — you already replied to {person} "
                              f"yourself after this draft was written.")
        elif reason == "thread-no-longer-awaiting":
            captain_reason = (f"Not sent — the conversation with {person} no "
                              f"longer needs this reply (it was already "
                              f"handled or closed).")
        else:
            captain_reason = f"Not sent — this draft to {person} is no longer needed."
    return {"action": action, "reason": reason,
            "captain_reason": captain_reason, "checks": checks}


def verify_at_fire(record: dict, *, pid: str = "", source=None,
                   force: bool = False) -> dict:
    """The fire-time re-gather. Returns
    ``{"action": "fire"|"cancel", "reason", "captain_reason", "checks"}``.

    Pure decision — it removes nothing itself; the caller
    (``chair_drafts.deliver_draft``) executes a cancel (delete the record +
    ``draft_queue.journal_fire_cancel``) and surfaces ``captain_reason``.
    Never raises: any probe error degrades to honest-unknown, which fires."""
    checks = {"captain_replied_since": None, "still_awaiting": None,
              "pid": pid or ""}
    record = record if isinstance(record, dict) else {}

    if force:
        return _result("fire", "forced", checks, record)
    if str(os.environ.get("CABINET_VERIFY_AT_FIRE", "1")).strip() == "0":
        return _result("fire", "gate-disabled", checks, record)

    slug = str(record.get("slug") or "").strip()
    if not slug:
        # Nothing to verify against — no thread identity. Fire (the upstream
        # approval gate already ruled).
        return _result("fire", "no-thread-identity", checks, record)

    if source is None:
        try:
            from framework.sources import get_source
            source = get_source()
        except Exception:
            return _result("fire", "source-unavailable", checks, record)

    # (1) Did the captain send an outbound on this thread AFTER we queued?
    # Only meaningful when the record carries its queue moment — a record
    # without ``queued_ts`` skips this probe (never call with a fabricated
    # clock) and relies on the still-awaiting probe below.
    queued_at = _parse_iso(record.get("queued_ts"))
    replied = None
    if queued_at is not None:
        try:
            replied = source.captain_replied_since(slug, queued_at)
        except Exception:
            replied = None
    checks["captain_replied_since"] = replied
    if replied is True:
        return _result("cancel", "captain-already-replied", checks, record)

    # (2) Is the thread still awaiting a reply at all? (reply-lane records
    # only — see module docstring.)
    if _is_reply(record):
        awaiting = None
        try:
            awaiting = source.still_awaiting(slug)
        except Exception:
            awaiting = None
        checks["still_awaiting"] = awaiting
        if awaiting is False:
            return _result("cancel", "thread-no-longer-awaiting", checks, record)

    return _result("fire", "verified-still-needed", checks, record)
