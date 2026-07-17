"""framework.comms.surface.killswitch_card — the /killswitch standing control card.

THE ONE LAW (captain-controls plan, ratified 2026-07-17): no localhost surface
may execute a captain-only action — the captain's Telegram identity is the
captain-held factor, routed through the verified tap door. This module is the
PURE face of that door for the emergency stop: the status card text plus the
``Halt`` / ``Resume`` keyboard, minted through ``decision_card``'s allowlisted
verb enum (``cv2|ksh`` / ``cv2|ksr``, NO payload — a kill-switch button never
carries an argument, and ``tap_wire`` refuses any fail-closed).

It never touches redis and never runs the script. Execution rides the
inbound poller's seam (``run_kill_switch`` → ``cabinet/scripts/kill-switch.sh``,
the sanctioned audit-emitting surface) after ``tap_wire`` re-validates the
verb; the callback path is captain-chat-gated in the poller. E-stop asymmetry
(the plan's first principle): HALT stays easy everywhere — ``activate`` is
unrestricted by design and this card adds a door, never a gate; RESUME requires
the captain factor. Both buttons render on every face — the script is
idempotent and read-back verified, and every tap re-renders the face from a
FRESH status read, so a stale card can never lie about the outcome.

Stdlib-only at import (foundation-module rule); the decision_card import is
the verb-mint single source, itself stdlib-only.
"""
from __future__ import annotations

from framework.comms.surface import decision_card as _dc

# Captain-facing labels — plain words, no org jargon (the card's whole
# audience is "a pensioner, not an engineer").
HALT_LABEL = "⏹ Halt"
RESUME_LABEL = "▶ Resume"
TITLE = "🛑 Emergency stop"

#: Honest tri-state of the switch as READ (never guessed).
STATE_ARMED = "armed"        # key present + "active" — everything halted
STATE_OFF = "off"            # verified absent — normal operation
STATE_UNKNOWN = "unknown"    # control plane didn't answer — treat as armed

_STATE_LINES = {
    STATE_ARMED: "🔴 ARMED — everything is halted.",
    STATE_OFF: "🟢 off — the cabinet is running.",
    STATE_UNKNOWN: ("⚠️ UNKNOWN — the switch didn't answer; "
                    "treat it as ARMED until it does."),
}

#: What each sanctioned script action is called on the card.
_ACTION_WORD = {"activate": "Halt", "deactivate": "Resume"}

_FOOTER = ("Halt stops everything instantly — anyone may pull it. "
           "Resume only works from your taps here.")

_CLIP = 700          # per-block clip for script output (Telegram cap is 4096)


def keyboard() -> list:
    """The Halt/Resume inline keyboard in Telegram shape. Both callback
    payloads are minted through ``decision_card.cb`` — the allowlisted verb
    enum is the ONLY mint, so an out-of-enum verb can never be composed here
    (``cb`` raises), and ``tap_wire``/``engine.parse_callback`` re-validate
    the same enum on the way back in."""
    return [[{"text": HALT_LABEL, "callback_data": _dc.cb("ksh")},
             {"text": RESUME_LABEL, "callback_data": _dc.cb("ksr")}]]


def parse_state(status_rc: int, status_out: str) -> str:
    """Classify one ``kill-switch.sh status`` run. Fail-closed: anything not
    an unambiguous verified read (rc 2, unreachable plane, garbled output)
    is UNKNOWN — the card then says to treat the switch as ARMED, mirroring
    the script's own fail-closed status contract."""
    if status_rc != 0:
        return STATE_UNKNOWN
    out = str(status_out or "")
    if "Kill switch: ACTIVE" in out:
        return STATE_ARMED
    if "Kill switch: INACTIVE" in out:
        return STATE_OFF
    return STATE_UNKNOWN


def _clip(text: str) -> str:
    # marker hygiene: the ·…· reply marker is reply-binding machinery and may
    # never ride card free text (decision_card._scrub law, same rule here).
    t = str(text or "").replace("·", "").strip()
    return t[:_CLIP] + "…" if len(t) > _CLIP else t


def render(status_rc: int, status_out: str, *, action: "str | None" = None,
           action_rc: "int | None" = None,
           action_out: "str | None" = None) -> dict:
    """The full card face: ``{"text", "keyboard", "state"}``.

    ``status_rc/status_out`` = a FRESH ``kill-switch.sh status`` read (state is
    never inferred from the flip we just ran — the watchdog or anything else
    may have moved it). ``action*`` (optional) = the flip that was just
    executed; its block quotes the script's OWN verified output verbatim, and
    a failed flip is LOUD (🚨 + the script's stderr) — never silent, never
    summarized away."""
    state = parse_state(status_rc, status_out)
    lines = [TITLE, "", f"Status: {_STATE_LINES[state]}"]
    if action in _ACTION_WORD:
        word = _ACTION_WORD[action]
        body = _clip(action_out) or "(the switch produced no output)"
        if action_rc == 0:
            lines += ["", f"✅ {word} done — the switch's own report:", body]
        else:
            lines += ["", f"🚨 {word.upper()} FAILED — NOT verified. "
                          "The switch says:", body]
    lines += ["", _FOOTER]
    return {"text": "\n".join(lines), "keyboard": keyboard(), "state": state}
