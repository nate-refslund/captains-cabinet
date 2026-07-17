"""captain-reminder instant push through the attention gate (Captain ruling
2026-07-17: "the time of day is set by the captain → push instantly").

Teeth:
  * a captain-reminder card SENDS inside quiet hours under the SHIPPED
    default charter (floor class with Captain provenance, §4.10.4);
  * the FLOOR LAW negative controls: a direct-now NON-floor class and a
    batch class at the same 03:00 instant fold to the briefing — adding the
    reminder class widened nothing else;
  * the charter default's floor stays kind-only (no keyword can pierce);
  * the BELT: under an instance-like charter that LACKS the class, the
    structural ``deadline_iso`` pierce still delivers at fire time — and a
    deadline beyond the next briefing does NOT pierce (no free loudness);
  * buttons ride the decision to the send transport untouched.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from framework.attention import charter, gate

# 03:00 UTC — deep inside the default 21:00→07:00 quiet window.
NIGHT = datetime(2026, 7, 17, 3, 0, tzinfo=timezone.utc)

BUTTONS = [[{"text": "✓ Done", "data": "cv2|ndg|aabbccdd"},
            {"text": "⏰ Later 7d", "data": "cv2|ndl|aabbccdd"},
            {"text": "✗ Drop", "data": "cv2|ndd|aabbccdd"}]]


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_ATTENTION_DIR", str(tmp_path / "attention"))
    monkeypatch.setenv("CABINET_CAPTAIN_TZ", "UTC")
    monkeypatch.setenv("CABINET_BRIEFING_TIMES", "07:30,19:30")


def _default_ch():
    return charter.load_default()


def _reminder(**kw):
    base = {"kind": "captain-reminder",
            "subject": "Reminder: sign the quarterly filing",
            "situation": "due Thu 2026-07-17 03:00 — tap a button or reply: "
                         "grant/later/deny NEED-aabbccdd",
            "evidence": ["9a1f0c9e-2b3d-5f47-8a6c-0d9e8f7a6b5c"],
            "urgency": "ping-now",
            "deadline_iso": "2026-07-17T03:00:00Z",   # the Captain's instant
            "buttons": BUTTONS}
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# The instant path: fire time inside quiet hours ⇒ SEND, loud
# ---------------------------------------------------------------------------

def test_reminder_sends_inside_quiet_hours_default_charter():
    d = gate.decide(_reminder(), ch=_default_ch(), now=NIGHT, standing={})
    assert d["action"] == "send", d
    assert d["reason"] == "ping-now-direct"
    assert d["class_id"] == "captain-reminder"
    assert d["silent"] is False          # the Captain CHOSE this instant
    assert d["buttons"] == BUTTONS


def test_reminder_delivery_carries_buttons_to_transport():
    sent = []

    def send_fn(text, **kw):
        sent.append({"text": text, **kw})
        return {"sent": True, "message_ids": [901]}

    d = gate.decide(_reminder(), ch=_default_ch(), now=NIGHT, standing={})
    gate.deliver(d, send_fn=send_fn, standing={})
    assert len(sent) == 1
    assert sent[0]["buttons"] == BUTTONS
    assert "Reminder: sign the quarterly filing" in sent[0]["text"]


def test_same_fire_resubmit_suppresses_never_double_pings():
    """Crash-before-mark re-file: identical item (same evidence, same render)
    against the persisted standing entry suppresses instead of re-pinging."""
    standing = {}
    it = _reminder()
    d1 = gate.decide(it, ch=_default_ch(), now=NIGHT, standing=standing)
    gate.deliver(d1, send_fn=lambda t, **k: {"sent": True, "message_ids": [77]},
                 standing=standing)
    d2 = gate.decide(it, ch=_default_ch(), now=NIGHT, standing=standing)
    assert d2["action"] == "suppress"
    assert d2["reason"] == "no-change"


# ---------------------------------------------------------------------------
# FLOOR LAW negative controls — nothing else got louder
# ---------------------------------------------------------------------------

def test_direct_now_non_floor_class_does_not_pierce():
    """triage-nudge is direct-now but NOT a floor class: at 03:00 it folds to
    the briefing. Pins that the reminder class pierces via the FLOOR, not via
    some general direct-now loophole."""
    item = {"kind": "triage-nudge", "subject": "3 decisions ready",
            "evidence": ["thread:triage-1"]}
    d = gate.decide(item, ch=_default_ch(), now=NIGHT, standing={})
    assert d["action"] == "briefing"
    assert d["reason"] == "quiet-hours"


def test_batch_class_does_not_pierce():
    item = {"kind": "fyi", "subject": "fyi the build is green",
            "evidence": ["thread:fyi-1"]}
    d = gate.decide(item, ch=_default_ch(), now=NIGHT, standing={})
    assert d["action"] == "briefing"


def test_prose_keyword_cannot_reach_the_reminder_class():
    """A captured card that merely SAYS reminder-ish words stays its own
    class — captain-reminder is kind-matched only (producer-attested)."""
    ch = _default_ch()
    cid = charter.classify(
        {"kind": "fyi", "subject": "reminder: do it today, urgent",
         "situation": "captain-reminder wording planted in captured text"},
        ch)
    assert cid != "captain-reminder"
    floor = set(ch["quiet_hours"]["floor_classes"])
    cls = {c["id"]: c for c in ch["classes"]}
    assert "captain-reminder" in floor    # the ruling is ON the floor
    for fid in floor:
        assert not (cls[fid].get("matchers") or {}).get("keywords"), \
            f"floor class {fid} is keyword-matched — 3am false-send risk"


# ---------------------------------------------------------------------------
# The BELT: deadline_iso pierce under a charter WITHOUT the class
# ---------------------------------------------------------------------------

# An instance-like charter that never heard of captain-reminder.
CH_NO_CLASS = {
    "version": 1, "_source": "test", "verbosity": "terse",
    "ack_style": "silent-fyi",
    "quiet_hours": {"start": "21:00", "end": "07:00",
                    "floor_classes": ["infra-page"]},
    "classes": [
        {"id": "infra-page", "matchers": {"kinds": ["infra-page"]},
         "route": "direct-now", "silent": False, "reaction": ["🚨"]},
        {"id": "default", "route": "next-briefing", "silent": True},
    ],
}


def test_deadline_belt_pierces_without_the_class():
    """Instance charter drift (no captain-reminder class): the arm's stamped
    deadline_iso=due_at is a REAL timestamp before the next briefing, so the
    structural pierce still delivers at fire time (class falls to default —
    quieter, but never held until morning)."""
    d = gate.decide(_reminder(), ch=CH_NO_CLASS, now=NIGHT, standing={})
    assert d["class_id"] == "default"
    assert d["action"] == "send"
    assert d["reason"] == "ping-now-direct"


def test_future_deadline_does_not_pierce():
    """No free loudness from the belt: a deadline AFTER the next briefing
    demotes the ping-now to the briefing (the gate's own law, unchanged)."""
    it = _reminder(deadline_iso="2026-07-18T12:00:00Z")   # beyond 07:30
    d = gate.decide(it, ch=CH_NO_CLASS, now=NIGHT, standing={})
    assert d["action"] == "briefing"
    assert d["reason"] == "ping-now-demoted-not-wrong-by-briefing"


def test_garbage_deadline_never_pierces_without_the_floor():
    it = _reminder(deadline_iso="today at three-ish")
    d = gate.decide(it, ch=CH_NO_CLASS, now=NIGHT, standing={})
    assert d["action"] == "briefing"      # unparseable timestamp = no pierce
