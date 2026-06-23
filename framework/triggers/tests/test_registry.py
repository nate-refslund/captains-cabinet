"""Tests for the trigger registry — lock in the durable-reminder guarantees.

A silently-not-firing reminder is the worst failure mode for this primitive, so we
pin: due-detection, interval reschedule, at-time/on-event one-shot, cancel, and that
under-specified specs RAISE rather than register a no-fire trigger.
"""
import datetime as dt

import pytest

from framework.triggers import registry as R


@pytest.fixture
def reg(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_TRIGGERS_FILE", str(tmp_path / "triggers.json"))
    return R


def _ts(delta_min: int) -> str:
    return (dt.datetime.now(dt.timezone.utc)
            + dt.timedelta(minutes=delta_min)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_at_time_due_then_oneshot(reg):
    t = reg.register_trigger(kind="at-time", payload={"about": "reply to Lisa"},
                             fire_at=_ts(-5))
    due = reg.due_triggers()
    assert [d["id"] for d in due] == [t["id"]]
    reg.mark_fired(t["id"])
    assert reg.due_triggers() == []                       # one-shot: drops out
    assert reg.list_triggers() == []                      # no longer pending
    done = reg.list_triggers(include_done=True)
    assert done[0]["status"] == "fired" and done[0]["fire_count"] == 1


def test_future_at_time_not_due(reg):
    reg.register_trigger(kind="at-time", payload={"about": "later"}, fire_at=_ts(120))
    assert reg.due_triggers() == []


def test_interval_reschedules_and_stays_pending(reg):
    t = reg.register_trigger(kind="interval", payload={"about": "watch deploy"},
                             interval_sec=1800, fire_at=_ts(-1))
    assert [d["id"] for d in reg.due_triggers()] == [t["id"]]
    up = reg.mark_fired(t["id"])
    assert up["status"] == "pending" and up["fire_count"] == 1
    # rescheduled into the future → no longer due
    assert reg.due_triggers() == []
    assert [p["id"] for p in reg.list_triggers()] == [t["id"]]


def test_cancel(reg):
    t = reg.register_trigger(kind="at-time", payload={"about": "x"}, fire_at=_ts(-1))
    assert reg.cancel_trigger(t["id"]) is True
    assert reg.due_triggers() == [] and reg.list_triggers() == []
    assert reg.cancel_trigger("nope") is False


def test_on_event_surfaced_by_key_only(reg):
    t = reg.register_trigger(kind="on-event", payload={"about": "PR merged → tell Nate"},
                             event_key="pr.merged")
    assert reg.due_triggers() == []                       # never time-due
    assert [d["id"] for d in reg.due_event_triggers("pr.merged")] == [t["id"]]
    assert reg.due_event_triggers("other.event") == []
    reg.mark_fired(t["id"])                                # one-shot
    assert reg.due_event_triggers("pr.merged") == []


@pytest.mark.parametrize("kwargs", [
    {"kind": "at-time", "payload": {"a": 1}},                       # no fire_at
    {"kind": "at-time", "payload": {"a": 1}, "fire_at": "not-a-date"},
    {"kind": "interval", "payload": {"a": 1}},                      # no interval_sec
    {"kind": "interval", "payload": {"a": 1}, "interval_sec": 0},
    {"kind": "on-event", "payload": {"a": 1}},                      # no event_key
    {"kind": "bogus", "payload": {"a": 1}, "fire_at": "2026-01-01T00:00:00Z"},
    {"kind": "at-time", "payload": {}, "fire_at": "2026-01-01T00:00:00Z"},  # empty payload
])
def test_invalid_specs_raise(reg, kwargs):
    with pytest.raises(ValueError):
        reg.register_trigger(**kwargs)


def test_persists_across_reload(reg):
    t = reg.register_trigger(kind="at-time", payload={"about": "durable"}, fire_at=_ts(-1))
    # a fresh read (simulating a process restart) still sees it
    assert any(p["id"] == t["id"] for p in reg.list_triggers())
