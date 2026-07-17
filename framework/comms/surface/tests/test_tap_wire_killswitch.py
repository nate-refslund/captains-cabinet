"""tap_wire — kill-switch verbs (the /killswitch card's Halt/Resume taps).

Pins the poller-facing contract (captain-controls plan 2026-07-17 Phase 1):
  * classify yields the instant-ack toast for both verbs;
  * ksh executes `activate`, ksr executes `deactivate` — through the
    seam-injected executor ONLY, followed by a FRESH `status` read that
    repaints the standing card (fresh buttons included);
  * any payload on the wire is refused fail-closed BEFORE the executor runs
    (minted kill-switch buttons carry none) — hostile/spliced args never
    reach the door;
  * NO executor seam ⇒ refused: importing tap_wire is not a door, so an
    officer session calling apply_tap can never flip the switch (the
    EVAL-001b officer-side hook refusal stays a different, untouched door);
  * a failed flip is LOUD on the card (🚨 + the script's own words) and
    relays the bracket floor; a repaint failure never un-handles the tap.

Run: python3.12 -m pytest framework/comms/surface/tests/test_tap_wire_killswitch.py -q
"""
from __future__ import annotations

import pytest

from framework.comms.surface import tap_wire

ACTIVE_OUT = "Kill switch: ACTIVE (all operations halted)"
INACTIVE_OUT = "Kill switch: INACTIVE (normal operation)"
ACTIVATED_OUT = ("2026-07-17 09:00:00 UTC — KILL SWITCH ACTIVATED "
                 "(verified by read-back)")
DEACTIVATED_OUT = ("2026-07-17 09:05:00 UTC — KILL SWITCH DEACTIVATED "
                   "(verified by read-back)")
FAILED_OUT = ("2026-07-17 09:00:00 UTC — KILL SWITCH ACTIVATION FAILED: "
              "control plane unreachable or write unverified.")


class FakeExec:
    """Records every sanctioned action; scripted (rc, out) per action."""

    def __init__(self, results):
        self.results = dict(results)
        self.calls: list = []

    def __call__(self, action):
        self.calls.append(action)
        return self.results[action]


class Repaint:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls: list = []

    def __call__(self, message_id, text, keyboard):
        if self.fail:
            raise RuntimeError("edit refused")
        self.calls.append((message_id, text, keyboard))


# ---------------------------------------------------------------------------
# classify — pure, instant-ack toasts
# ---------------------------------------------------------------------------

def test_classify_yields_killswitch_toasts():
    verb, arg, toast = tap_wire.classify("cv2|ksh")
    assert (verb, arg) == ("ksh", "") and "Halting" in toast
    verb, arg, toast = tap_wire.classify("cv2|ksr")
    assert (verb, arg) == ("ksr", "") and "Resuming" in toast


# ---------------------------------------------------------------------------
# Executions — both verbs, through the seam, fresh-status repaint
# ---------------------------------------------------------------------------

def test_halt_tap_executes_activate_and_repaints_fresh_status():
    ks = FakeExec({"activate": (0, ACTIVATED_OUT), "status": (0, ACTIVE_OUT)})
    paint = Repaint()
    res = tap_wire.apply_tap("cv2|ksh", message_id=41, edit_text=paint,
                             ks_exec=ks)
    assert ks.calls == ["activate", "status"]      # flip THEN a fresh read
    assert res["handled"] is True and res["relay"] is False
    assert res["mode"] == "killswitch:ksh" and res["outcome"] == "halted"
    assert res["state"] == "armed" and res["marked"] is True
    (mid, text, kb), = paint.calls
    assert mid == 41
    assert "KILL SWITCH ACTIVATED (verified by read-back)" in text
    assert "ARMED — everything is halted." in text
    flat = [b["callback_data"] for row in kb for b in row]
    assert flat == ["cv2|ksh", "cv2|ksr"]          # the card stays the control


def test_resume_tap_executes_deactivate():
    ks = FakeExec({"deactivate": (0, DEACTIVATED_OUT),
                   "status": (0, INACTIVE_OUT)})
    paint = Repaint()
    res = tap_wire.apply_tap("cv2|ksr", message_id=42, edit_text=paint,
                             ks_exec=ks)
    assert ks.calls == ["deactivate", "status"]
    assert res["handled"] is True and res["relay"] is False
    assert res["outcome"] == "resumed" and res["state"] == "off"
    (_, text, _), = paint.calls
    assert "KILL SWITCH DEACTIVATED (verified by read-back)" in text


def test_failed_flip_is_loud_and_relays():
    ks = FakeExec({"activate": (1, FAILED_OUT), "status": (2, "")})
    paint = Repaint()
    res = tap_wire.apply_tap("cv2|ksh", message_id=43, edit_text=paint,
                             ks_exec=ks)
    assert res["handled"] is False and res["relay"] is True
    assert res["outcome"] == "failed:activate"
    (_, text, _), = paint.calls
    assert "🚨 HALT FAILED — NOT verified." in text
    assert "ACTIVATION FAILED" in text             # the script's own words
    assert "treat it as ARMED" in text             # fail-closed status line


def test_executor_exception_never_escapes_and_stays_loud():
    def _boom(action):
        raise OSError("no such script")
    paint = Repaint()
    res = tap_wire.apply_tap("cv2|ksr", message_id=44, edit_text=paint,
                             ks_exec=_boom)
    assert res["handled"] is False and res["relay"] is True
    (_, text, _), = paint.calls
    assert "🚨 RESUME FAILED" in text
    assert "NOT verified" in text


# ---------------------------------------------------------------------------
# The poller-only door — no seam, no flip
# ---------------------------------------------------------------------------

def test_no_executor_seam_refuses_both_verbs():
    for data in ("cv2|ksh", "cv2|ksr"):
        res = tap_wire.apply_tap(data, message_id=45)
        assert res["handled"] is False and res["relay"] is True
        assert "poller-only door" in res["summary"]


# ---------------------------------------------------------------------------
# Payload bounding — refuse BEFORE the executor
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("data", [
    "cv2|ksr|deadbeef",            # a needs-style tail does not transfer
    "cv2|ksh|1",                   # any arg at all
    "cv2|ksr|$(reboot)",           # hostile splice
    "cv2|ksh|`id`",
])
def test_payload_on_the_wire_refused_before_execution(data):
    ks = FakeExec({"activate": (0, ACTIVATED_OUT),
                   "deactivate": (0, DEACTIVATED_OUT),
                   "status": (0, INACTIVE_OUT)})
    res = tap_wire.apply_tap(data, message_id=46, edit_text=Repaint(),
                             ks_exec=ks)
    assert ks.calls == []                          # the door never opened
    assert res["handled"] is False and res["relay"] is True
    assert "refused" in res["summary"]


def test_oversized_and_whitespace_args_die_at_parse():
    ks = FakeExec({})
    assert tap_wire.apply_tap("cv2|ksr|" + "a" * 65,
                              ks_exec=ks)["mode"] == "foreign"
    assert tap_wire.apply_tap("cv2|ksh|a b", ks_exec=ks)["mode"] == "foreign"
    assert ks.calls == []


# ---------------------------------------------------------------------------
# Repaint failure floors
# ---------------------------------------------------------------------------

def test_edit_text_failure_falls_back_to_markup_receipt():
    ks = FakeExec({"deactivate": (0, DEACTIVATED_OUT),
                   "status": (0, INACTIVE_OUT)})
    marks: list = []
    res = tap_wire.apply_tap(
        "cv2|ksr", message_id=47, edit_text=Repaint(fail=True),
        edit_markup=lambda mid, kb: marks.append((mid, kb)), ks_exec=ks)
    assert res["handled"] is True                  # never un-handled
    assert res["marked"] is True
    (mid, kb), = marks
    assert mid == 47 and kb[0][0]["text"] == "▶ Resumed"


def test_all_repaints_failing_still_handles_the_tap():
    ks = FakeExec({"activate": (0, ACTIVATED_OUT), "status": (0, ACTIVE_OUT)})

    def _no(*_a):
        raise RuntimeError("telegram down")

    res = tap_wire.apply_tap("cv2|ksh", message_id=48, edit_text=_no,
                             edit_markup=_no, ks_exec=ks)
    assert res["handled"] is True and res["marked"] is False
