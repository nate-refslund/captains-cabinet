"""killswitch_card — the /killswitch standing control card's PURE face.

Pins the mint + the honest faces (captain-controls plan 2026-07-17 Phase 1):
  * Halt/Resume buttons are minted ONLY through decision_card's allowlisted
    verb enum (cv2|ksh / cv2|ksr, no payload, ≤64 bytes) and round-trip
    through engine.parse_callback;
  * the enum extension did not widen the mint — out-of-enum verbs still raise;
  * state classification is fail-closed (rc≠0 / garbled output ⇒ UNKNOWN,
    worded as "treat it as ARMED");
  * a failed flip renders LOUD (🚨 + the script's own words) — never silent;
  * card free text never carries the ·…· reply marker (marker-hygiene law).

Run: python3.12 -m pytest framework/comms/surface/tests/test_killswitch_card.py -q
"""
from __future__ import annotations

import pytest

from framework.comms.surface import decision_card as dc
from framework.comms.surface import engine
from framework.comms.surface import killswitch_card as kc

ACTIVE_OUT = "Kill switch: ACTIVE (all operations halted)"
INACTIVE_OUT = "Kill switch: INACTIVE (normal operation)"
UNKNOWN_OUT = ("Kill switch: UNKNOWN — control plane at 127.0.0.1:6379 "
               "unreachable (fail-closed: treat as ACTIVE for gating purposes)")
ACTIVATED_OUT = ("2026-07-17 09:00:00 UTC — KILL SWITCH ACTIVATED "
                 "(verified by read-back)\n"
                 "All Officer operations will halt on their next tool invocation.")
DEACTIVATED_OUT = ("2026-07-17 09:05:00 UTC — KILL SWITCH DEACTIVATED "
                   "(verified by read-back)\nOfficers will resume normal operation.")
FAILED_OUT = ("2026-07-17 09:00:00 UTC — KILL SWITCH ACTIVATION FAILED: "
              "control plane at 127.0.0.1:6379 unreachable or write unverified.\n"
              "Officers are NOT provably halted.")


# ---------------------------------------------------------------------------
# Mint — the allowlisted-verb machinery is the ONLY source of callback bytes
# ---------------------------------------------------------------------------

def test_keyboard_minted_through_decision_card_enum():
    rows = kc.keyboard()
    flat = [b for row in rows for b in row]
    assert [b["callback_data"] for b in flat] == ["cv2|ksh", "cv2|ksr"]
    assert [b["text"] for b in flat] == [kc.HALT_LABEL, kc.RESUME_LABEL]
    for b in flat:
        assert len(b["callback_data"].encode("utf-8")) <= 64
        # byte-identical to a direct mint — no second grammar
        verb = b["callback_data"].split("|")[1]
        assert b["callback_data"] == dc.cb(verb)


def test_minted_verbs_roundtrip_engine_parse():
    assert engine.parse_callback("cv2|ksh") == ("ksh", "")
    assert engine.parse_callback("cv2|ksr") == ("ksr", "")


def test_out_of_enum_verbs_still_refused_at_the_mint():
    with pytest.raises(ValueError):
        dc.cb("ksx")
    with pytest.raises(ValueError):
        dc.cb("killswitch")
    assert engine.parse_callback("cv2|ksx") is None


# ---------------------------------------------------------------------------
# State classification — fail-closed
# ---------------------------------------------------------------------------

def test_parse_state_verified_reads():
    assert kc.parse_state(0, ACTIVE_OUT) == kc.STATE_ARMED
    assert kc.parse_state(0, INACTIVE_OUT) == kc.STATE_OFF


@pytest.mark.parametrize("rc,out", [
    (2, UNKNOWN_OUT),          # the script's own unreachable contract
    (2, ""),
    (0, "totally unexpected"),  # garbled ⇒ never guessed
    (0, ""),
    (1, INACTIVE_OUT),         # non-zero rc outranks a plausible line
])
def test_parse_state_fails_closed_to_unknown(rc, out):
    assert kc.parse_state(rc, out) == kc.STATE_UNKNOWN


# ---------------------------------------------------------------------------
# Faces
# ---------------------------------------------------------------------------

def test_status_card_face_armed():
    face = kc.render(0, ACTIVE_OUT)
    assert face["state"] == kc.STATE_ARMED
    assert "🛑 Emergency stop" in face["text"]
    assert "ARMED — everything is halted." in face["text"]
    assert face["keyboard"] == kc.keyboard()


def test_status_card_face_off_and_unknown():
    off = kc.render(0, INACTIVE_OUT)
    assert off["state"] == kc.STATE_OFF
    assert "the cabinet is running" in off["text"]
    unk = kc.render(2, UNKNOWN_OUT)
    assert unk["state"] == kc.STATE_UNKNOWN
    assert "treat it as ARMED" in unk["text"]


def test_flip_success_quotes_the_scripts_own_report():
    face = kc.render(0, ACTIVE_OUT, action="activate", action_rc=0,
                     action_out=ACTIVATED_OUT)
    assert "✅ Halt done" in face["text"]
    assert "KILL SWITCH ACTIVATED (verified by read-back)" in face["text"]
    face2 = kc.render(0, INACTIVE_OUT, action="deactivate", action_rc=0,
                      action_out=DEACTIVATED_OUT)
    assert "✅ Resume done" in face2["text"]
    assert "KILL SWITCH DEACTIVATED (verified by read-back)" in face2["text"]


def test_flip_failure_is_loud_and_verbatim():
    face = kc.render(2, UNKNOWN_OUT, action="activate", action_rc=1,
                     action_out=FAILED_OUT)
    assert "🚨 HALT FAILED — NOT verified." in face["text"]
    assert "Officers are NOT provably halted." in face["text"]
    # the standing buttons survive a failure — the card stays the control
    assert face["keyboard"] == kc.keyboard()


def test_flip_failure_with_no_output_still_says_so():
    face = kc.render(2, "", action="deactivate", action_rc=1, action_out="")
    assert "🚨 RESUME FAILED" in face["text"]
    assert "(the switch produced no output)" in face["text"]


def test_card_text_bounded_and_marker_clean():
    noisy = ("x" * 5000) + "·" + ("y" * 5000)
    face = kc.render(0, ACTIVE_OUT, action="activate", action_rc=1,
                     action_out=noisy)
    assert "·" not in face["text"]          # marker-hygiene law
    assert len(face["text"]) < 4096          # Telegram sendMessage cap
