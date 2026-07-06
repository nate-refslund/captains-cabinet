"""Fast EventKit delete-by-identifier — the WRITE-side counterpart of the
read-only ``calendar_read`` gather, kept in a SEPARATE module so ``calendar_read``
never gains a mutating call and its read-only invariant stays literally true.

This is the fast path of the calendar undo/reverse. The germline
``action_undo._inv_calendar_delete`` dispatches to :func:`delete_event` first;
on ANY failure it falls back to the proven-authoritative AppleScript
``whose uid is`` delete (which keys on the SAME uid space the writer stored). So
the fast path only ever needs to be CORRECT-or-LOUD, never exhaustive.

CONTRACT (safety-critical — the undo must never claim a delete it did not do):
:func:`delete_event` returns a confirmation dict ONLY on a CONFIRMED removal —
the helper's ``delete`` subcommand acquires fullAccess BEFORE any lookup (the
write-only trap defense), removes by ``calendarItemExternalIdentifier`` scoped to
the named calendar, RE-QUERIES to confirm the event is gone, and prints
``{"ok":true,"deleted":N}`` + exit 0 only then. Anything else — a non-zero exit
(0-match / recurrence / remove-throw / unconfirmed), an absent binary, a timeout,
non-JSON or a non-``ok:true`` object — normalizes to CalendarDeleteError so the
germline dispatcher falls through to the AppleScript fallback (fail-closed).

Stdlib-only, importable under system Python 3.9.6 (``from __future__`` +
Optional annotations). The subprocess runner is INJECTED (the germline reverse
passes the same arg-list osascript runner it already uses), so this is fully
mock-testable with no real spawn.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from framework.frontdoor import calendar_read

__all__ = ["CalendarDeleteError", "delete_event", "DELETE_SUBCOMMAND"]

# The mutating subcommand this module owns on the consolidated helper.
DELETE_SUBCOMMAND = "delete"


class CalendarDeleteError(RuntimeError):
    """The fast EventKit delete could not be CONFIRMED (helper missing/non-zero
    exit, timeout, non-JSON or non-``ok:true`` stdout, or empty calendar/uid).
    The germline reverse treats this as 'not confirmed' and falls through to the
    authoritative AppleScript delete — it NEVER reads as a successful undo."""


def delete_event(calendar: str, uid: str, *,
                 runner: Callable[[list], str]) -> Dict[str, Any]:
    """Delete the event with external id ``uid`` in the named ``calendar`` via the
    consolidated helper's ``delete`` subcommand, returning the parsed confirmation
    dict ONLY on a confirmed removal. Raises CalendarDeleteError on ANY uncertainty
    (fail-closed). ``runner`` is the injected arg-list subprocess runner (the same
    one the germline reverse uses for AppleScript) — it must RAISE on a non-zero
    exit so a helper refusal (exit 4/5/6/3) surfaces here as a raise."""
    cal = (calendar or "").strip()
    ext = (uid or "").strip()
    if not cal or not ext:
        raise CalendarDeleteError("delete_event requires a non-empty calendar and uid")
    cmd = [calendar_read.helper_path(), DELETE_SUBCOMMAND, cal, ext]
    try:
        out = runner(cmd)
    except CalendarDeleteError:
        raise
    except Exception as e:                       # non-zero exit / missing / timeout
        raise CalendarDeleteError(
            f"calendar delete failed ({type(e).__name__}: {e})") from e
    try:
        obj = json.loads(out or "")
    except (ValueError, TypeError) as e:
        raise CalendarDeleteError(
            f"calendar delete stdout is not valid JSON: {(out or '')[:120]!r}") from e
    if not isinstance(obj, dict) or obj.get("ok") is not True:
        raise CalendarDeleteError(
            f"calendar delete not confirmed (stdout {(out or '')[:120]!r})")
    return obj
