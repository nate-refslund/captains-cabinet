"""Tests for the trigger firing path — the contract that keeps DM receive safe:
fires when free, SKIPS when busy (stays due), no-ops cleanly, and never raises.
"""
import datetime as dt

import pytest

from framework.triggers import firing, registry as R


@pytest.fixture
def reg(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_TRIGGERS_FILE", str(tmp_path / "triggers.json"))
    return R


def _past() -> str:
    return (dt.datetime.now(dt.timezone.utc)
            - dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_fires_when_pane_free(reg):
    reg.register_trigger(kind="at-time", payload={"about": "ping Lisa"}, fire_at=_past())
    calls, logs = [], []
    n = firing.fire_due_triggers("sess", lambda: False, logs.append,
                                 tmux=lambda *a: calls.append(a))
    assert n == 1
    assert any(a[0] == "send-keys" for a in calls)          # injected a turn
    assert reg.due_triggers() == []                         # fired → no longer due


def test_skips_when_pane_busy(reg):
    reg.register_trigger(kind="at-time", payload={"about": "x"}, fire_at=_past())
    calls = []
    n = firing.fire_due_triggers("sess", lambda: True, lambda _m: None,
                                 tmux=lambda *a: calls.append(a))
    assert n == 0 and calls == []                           # nothing injected, no block
    assert len(reg.due_triggers()) == 1                     # stays due → fires next cycle


def test_no_due_triggers_is_noop(reg):
    calls = []
    n = firing.fire_due_triggers("sess", lambda: False, lambda _m: None,
                                 tmux=lambda *a: calls.append(a))
    assert n == 0 and calls == []


def test_pane_busy_check_error_is_safe(reg):
    reg.register_trigger(kind="at-time", payload={"about": "x"}, fire_at=_past())

    def boom():
        raise RuntimeError("tmux capture failed")

    n = firing.fire_due_triggers("sess", boom, lambda _m: None, tmux=lambda *a: None)
    assert n == 0                                           # can't read pane → don't inject
    assert len(reg.due_triggers()) == 1                    # untouched


def test_tmux_failure_is_caught_not_raised(reg):
    reg.register_trigger(kind="at-time", payload={"about": "x"}, fire_at=_past())

    def boom(*a):
        raise RuntimeError("inject failed")

    # must NOT raise into the caller (the receive loop); trigger stays due (unmarked)
    n = firing.fire_due_triggers("sess", lambda: False, lambda _m: None, tmux=boom)
    assert n == 0
    assert len(reg.due_triggers()) == 1


def test_interval_trigger_reschedules_on_fire(reg):
    reg.register_trigger(kind="interval", payload={"about": "watch"},
                         interval_sec=1800, fire_at=_past())
    n = firing.fire_due_triggers("sess", lambda: False, lambda _m: None, tmux=lambda *a: None)
    assert n == 1
    assert reg.due_triggers() == []                        # rescheduled into the future
    assert len(reg.list_triggers()) == 1                   # still pending (interval persists)
