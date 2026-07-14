"""fire_gate — verify-at-FIRE-time (captain-surface §3.5): cancel ONLY on
positive evidence the thread was already handled; honest uncertainty always
fires (the captain's explicit approval is never vetoed on unknown)."""
from datetime import datetime, timezone

import pytest

from framework.acting import fire_gate


class FakeSource:
    """Recording personal-source stub for the two fire-time probes."""

    def __init__(self, replied=None, awaiting=None, raise_on=()):
        self.replied = replied
        self.awaiting = awaiting
        self.raise_on = set(raise_on)
        self.calls = []

    def available(self):
        return True

    def captain_replied_since(self, slug, when):
        self.calls.append(("captain_replied_since", slug, when))
        if "captain_replied_since" in self.raise_on:
            raise RuntimeError("probe blew up")
        return self.replied

    def still_awaiting(self, slug, hours=72):
        self.calls.append(("still_awaiting", slug))
        if "still_awaiting" in self.raise_on:
            raise RuntimeError("probe blew up")
        return self.awaiting


def _rec(**kw):
    base = {"slug": "casey", "person": "Casey", "channel": "email",
            "draft": "Hi — following up.", "lane": "send-1to1-reply",
            "queued_ts": "2026-07-10T08:00:00Z"}
    base.update(kw)
    return base


def test_captain_already_replied_cancels():
    src = FakeSource(replied=True)
    v = fire_gate.verify_at_fire(_rec(), source=src)
    assert v["action"] == "cancel"
    assert v["reason"] == "captain-already-replied"
    # Plain-language law: the captain-facing line names the person plainly.
    assert "Casey" in v["captain_reason"] and "Not sent" in v["captain_reason"]
    # The probe got the QUEUE moment as its clock (tz-aware).
    name, slug, when = src.calls[0]
    assert slug == "casey" and when == datetime(2026, 7, 10, 8, 0,
                                                tzinfo=timezone.utc)


def test_no_longer_awaiting_cancels_a_reply_draft():
    src = FakeSource(replied=False, awaiting=False)
    v = fire_gate.verify_at_fire(_rec(), source=src)
    assert v["action"] == "cancel"
    assert v["reason"] == "thread-no-longer-awaiting"
    assert "Casey" in v["captain_reason"]


def test_uncertainty_fires_never_vetoes_the_captain():
    src = FakeSource(replied=None, awaiting=None)
    v = fire_gate.verify_at_fire(_rec(), source=src)
    assert v["action"] == "fire" and v["reason"] == "verified-still-needed"


def test_probe_errors_degrade_to_fire():
    src = FakeSource(raise_on=("captain_replied_since", "still_awaiting"))
    v = fire_gate.verify_at_fire(_rec(), source=src)
    assert v["action"] == "fire"


def test_non_reply_lane_ignores_still_awaiting():
    # A proactive/outreach draft was never "awaiting" — still_awaiting False
    # must NOT cancel it (only a positive captain-replied can).
    src = FakeSource(replied=False, awaiting=False)
    v = fire_gate.verify_at_fire(_rec(lane="proactive-outreach"), source=src)
    assert v["action"] == "fire"
    assert not any(c[0] == "still_awaiting" for c in src.calls)


def test_missing_lane_is_treated_as_a_reply():
    # Both current writers are reply flows; legacy records carry no lane.
    src = FakeSource(replied=None, awaiting=False)
    rec = _rec()
    del rec["lane"]
    v = fire_gate.verify_at_fire(rec, source=src)
    assert v["action"] == "cancel" and v["reason"] == "thread-no-longer-awaiting"


def test_missing_queued_ts_skips_the_replied_probe():
    # Never call the outbound probe with a fabricated clock.
    src = FakeSource(replied=True, awaiting=True)
    rec = _rec()
    del rec["queued_ts"]
    v = fire_gate.verify_at_fire(rec, source=src)
    assert v["action"] == "fire"
    assert not any(c[0] == "captain_replied_since" for c in src.calls)
    assert any(c[0] == "still_awaiting" for c in src.calls)


def test_force_skips_the_gate_entirely():
    src = FakeSource(replied=True, awaiting=False)
    v = fire_gate.verify_at_fire(_rec(), source=src, force=True)
    assert v["action"] == "fire" and v["reason"] == "forced"
    assert src.calls == []


def test_env_kill_switch_disables_the_gate(monkeypatch):
    monkeypatch.setenv("CABINET_VERIFY_AT_FIRE", "0")
    src = FakeSource(replied=True)
    v = fire_gate.verify_at_fire(_rec(), source=src)
    assert v["action"] == "fire" and v["reason"] == "gate-disabled"
    assert src.calls == []


def test_no_thread_identity_fires():
    src = FakeSource(replied=True)
    v = fire_gate.verify_at_fire({"person": "Someone", "draft": "x"}, source=src)
    assert v["action"] == "fire" and v["reason"] == "no-thread-identity"
    assert src.calls == []


def test_sourceless_deployment_fires(monkeypatch):
    # An unbound / null estate answers None to both probes — the gate must
    # fire (honest-empty can never veto an approved send).
    from framework.sources import NullPersonalSource
    v = fire_gate.verify_at_fire(_rec(), source=NullPersonalSource())
    assert v["action"] == "fire"
