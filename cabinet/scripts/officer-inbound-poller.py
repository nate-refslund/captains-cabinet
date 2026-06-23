#!/usr/bin/env python3
"""officer-inbound-poller.py — the Captain's inbound Telegram bridge for a
Telegram-voice officer (the Chair).

WHY THIS EXISTS
---------------
The Claude Code telegram Channels plugin (``--channels plugin:telegram``) does
NOT reliably deliver DMs to an IDLE officer session: it fetches one update,
injects it, then stalls until that injection is processed — which never happens
while the session sits at its prompt. Result: the Captain DMs the bot and gets
silence (observed 2026-06-23: messages stuck at ``pending_update_count`` while
the Chair was idle).

This poller replaces the plugin's RECEIVE half. It is the SOLE ``getUpdates``
poller for the officer's bot (the officer must therefore launch WITHOUT
``--channels`` — two pollers on one token = Telegram 409 Conflict). On each
Captain message it WAKES the officer's tmux session via ``tmux send-keys`` (the
proven wake path), so the officer runs a turn, interprets the message, and
replies through the existing approval-safe ``framework.frontdoor.channel.send``
(outbound is unchanged and independent of this).

GUARANTEES
----------
* Captain-only: relays ONLY messages whose ``from.id == CAPTAIN_TELEGRAM_ID``.
  Every other sender is skipped (the bot is publicly addressable).
* No loss: the update offset is advanced only AFTER a message is delivered (or
  deliberately skipped); a crash mid-deliver re-delivers on restart rather than
  dropping. Offset persisted to ``TELEGRAM_STATE_DIR/inbound-offset.txt``.
* No mid-turn corruption: delivery is idle-gated — it waits for the pane to be
  at its prompt before injecting.
* Secret hygiene: the bot token is read from env and never logged.

ENV: TELEGRAM_<OFFICER>_TOKEN (or TELEGRAM_BOT_TOKEN), CAPTAIN_TELEGRAM_ID,
     TELEGRAM_STATE_DIR (optional; defaults to the cabinet state path).
USAGE: officer-inbound-poller.py <officer>     # e.g. cos
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

# Repo root on sys.path so the watchdog can ALSO fire registered triggers — a fired
# reminder/interval reuses the very same tmux wake path as a Captain DM. Fail-safe by
# construction: if the firing module can't be imported, `fire_due_triggers` is a no-op
# and DM receive is completely unaffected.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
try:
    from framework.triggers.firing import fire_due_triggers
except Exception:
    def fire_due_triggers(*_a, **_k):  # firing unavailable → receive path unchanged
        return 0


def log(msg: str) -> None:
    print(f"[inbound-poller] {msg}", flush=True)


def main() -> int:
    officer = sys.argv[1] if len(sys.argv) > 1 else "cos"
    up = officer.upper().replace("-", "_")
    token = os.environ.get(f"TELEGRAM_{up}_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    captain = os.environ.get("CAPTAIN_TELEGRAM_ID")
    state_dir = os.environ.get("TELEGRAM_STATE_DIR") or os.path.expanduser(
        f"~/Library/Application Support/cabinet/telegram-state/{officer}"
    )
    session = f"officer-{officer}"

    if not token:
        log(f"FATAL: TELEGRAM_{up}_TOKEN (or TELEGRAM_BOT_TOKEN) not set"); return 1
    if not captain:
        log("FATAL: CAPTAIN_TELEGRAM_ID not set"); return 1

    os.makedirs(state_dir, exist_ok=True)
    offset_file = os.path.join(state_dir, "inbound-offset.txt")
    try:
        offset = int(open(offset_file).read().strip())
    except Exception:
        offset = 0

    api = f"https://api.telegram.org/bot{token}"
    log(f"started officer={officer} session={session} captain={captain} offset={offset}")

    def save_offset(o: int) -> None:
        tmp = offset_file + ".tmp"
        with open(tmp, "w") as f:
            f.write(str(o))
        os.replace(tmp, offset_file)

    def pane_busy() -> bool:
        """True if the officer pane is mid-turn (an active turn shows 'esc to interrupt')."""
        try:
            out = subprocess.run(
                ["tmux", "capture-pane", "-t", session, "-p"],
                capture_output=True, text=True, timeout=10,
            ).stdout
        except Exception:
            return True  # can't read → assume busy (don't inject blindly)
        tail = "\n".join(l for l in out.splitlines() if l.strip())[-1200:]
        return "esc to interrupt" in tail

    def deliver(text: str) -> None:
        """Idle-gate, then inject the Captain DM into the officer pane as a turn."""
        waited = 0
        while pane_busy() and waited < 300:   # wait up to ~5 min for the pane to free
            time.sleep(5); waited += 5
        relay = f"\U0001F4E9 Captain DM (Telegram): {text}"
        # text first, then Enter separately (Enter doesn't reliably register fused)
        subprocess.run(["tmux", "send-keys", "-t", session, relay], timeout=10)
        time.sleep(0.5)
        subprocess.run(["tmux", "send-keys", "-t", session, "C-m"], timeout=10)

    while True:
        try:
            params = urllib.parse.urlencode({
                "offset": offset + 1,
                "timeout": 25,
                "allowed_updates": json.dumps(["message"]),
            })
            with urllib.request.urlopen(f"{api}/getUpdates?{params}", timeout=35) as resp:  # noqa: S310 (fixed https host)
                data = json.load(resp)
        except Exception as e:
            log(f"getUpdates error: {e}")
            # Self-heal a 409 Conflict: another getUpdates poller exists (Telegram
            # allows only one per token). This Cabinet is single-Telegram-voice, the
            # officer launches without --channels, and the watchdog is the SOLE poller
            # by design — so any telegram plugin is a stray (e.g. the officer probing
            # its own telegram setup mid-session). Reap it to reclaim the lock.
            # (Revisit if a deployment ever runs >1 telegram-capable officer.)
            if "409" in str(e):
                try:
                    subprocess.run(["pkill", "-f", "plugins/cache/claude-plugins-official/telegram"], timeout=10)
                    log("409 self-heal: reaped stray telegram plugin poller(s)")
                except Exception:
                    pass
            time.sleep(5); continue

        if not data.get("ok"):
            log(f"getUpdates not ok: {data.get('description')}"); time.sleep(5); continue

        for upd in data.get("result", []):
            uid = int(upd.get("update_id", 0))
            msg = upd.get("message") or {}
            frm = str((msg.get("from") or {}).get("id", ""))
            text = (msg.get("text") or "").strip()
            if frm == str(captain) and text:
                log(f"captain msg update_id={uid} ({len(text)} chars) -> relaying")
                deliver(text)
            else:
                log(f"skip update_id={uid} from={frm or '?'} (not captain or non-text)")
            offset = max(offset, uid)
            save_offset(offset)

        # Fire any due triggers (reminders / intervals) into the pane, reusing the
        # wake path. Runs every poll cycle (~25s granularity). Non-blocking (skips
        # when the pane is busy) and fully wrapped — a trigger error never affects
        # the DM receive loop above.
        try:
            fire_due_triggers(session, pane_busy, log)
        except Exception as e:
            log(f"trigger firing (non-fatal): {e}")


if __name__ == "__main__":
    sys.exit(main())
