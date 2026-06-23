"""Fire due triggers into a Telegram-voice officer's tmux pane.

Called once per poll cycle by `officer-inbound-poller.py` (the inbound watchdog),
reusing its proven `tmux send-keys` wake path so a fired trigger wakes the Chair to
**gather-then-decide at fire time**. Kept in its own module so the critical receive
path only gains an import + one wrapped call, and so the logic is unit-testable.

Contract — fully isolated from DM receive:
  * Never raises into the caller's loop (every failure is caught + logged).
  * Never blocks: if the pane is busy (mid-turn) it returns 0 and the triggers stay
    due, firing next cycle when the pane is free. (The watchdog's `deliver()` idle-
    GATES — waits — which would stall DM receive; firing must not.)
  * Time-based only (at-time / interval). on-event triggers are fired by their event
    sources via `registry.due_event_triggers`, not here.
"""
from __future__ import annotations

import json
import time
import subprocess
from typing import Callable, Optional


def _default_tmux(*args: str) -> None:
    subprocess.run(["tmux", *args], timeout=10)


def fire_due_triggers(session: str,
                      pane_busy: Callable[[], bool],
                      log: Callable[[str], None],
                      *, tmux: Optional[Callable[..., None]] = None) -> int:
    """Fire all due time-based triggers into `session`; return the count fired.

    Each fire injects a '⏰ Trigger fired …' turn (gather-then-decide framing) and
    then `mark_fired` (interval → reschedule; at-time → one-shot). `pane_busy`/`log`/
    `tmux` are injected so this is testable without a live tmux session.
    """
    tmux = tmux or _default_tmux
    try:
        from framework.triggers import registry as R
        due = R.due_triggers()
    except Exception as e:                        # registry missing/unreadable → no-op
        log(f"trigger due-check skipped: {e}")
        return 0
    if not due:
        return 0
    try:
        if pane_busy():
            return 0                              # don't block; fire next cycle
    except Exception:
        return 0                                  # can't read pane → don't risk injecting

    fired = 0
    for t in due:
        tid = t.get("id")
        try:
            label = t.get("label") or t.get("kind") or "trigger"
            payload = json.dumps(t.get("payload") or {}, ensure_ascii=False)
            relay = (f"⏰ Trigger fired [{tid}]: {label}. Payload: {payload}. "
                     f"Gather-then-decide (re-check before acting), then act per the payload.")
            tmux("send-keys", "-t", session, relay)
            time.sleep(0.5)
            tmux("send-keys", "-t", session, "C-m")
            R.mark_fired(tid)
            fired += 1
            log(f"fired trigger {tid} ({label})")
        except Exception as e:                    # one bad trigger never stops the rest
            log(f"trigger fire error {tid}: {e}")
    return fired
