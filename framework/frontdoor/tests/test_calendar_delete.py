"""Mock-level tests for the fast EventKit delete (framework/frontdoor/
calendar_delete). No subprocess is ever spawned — the runner is injected. The
REAL uid==calendarItemExternalIdentifier equality + real removal are
validation_gated to Ada's granted Terminal (see the calendar-followups runbook).
"""
from __future__ import annotations

import json

import pytest

from framework.frontdoor import calendar_delete as cd


def _runner(stdout):
    calls = []

    def run(cmd):
        calls.append(cmd)
        return stdout

    run.calls = calls
    return run


def test_confirmed_delete_returns_dict_and_builds_command():
    runner = _runner('{"ok":true,"deleted":1}')
    out = cd.delete_event("Home", "UID-9", runner=runner)
    assert out == {"ok": True, "deleted": 1}
    cmd = runner.calls[0]
    assert cmd[1] == "delete"          # the mutating subcommand
    assert cmd[2] == "Home" and cmd[3] == "UID-9"   # cal + uid travel as argv


def test_runner_raise_is_delete_error():
    def boom(cmd):
        raise RuntimeError("helper exited 4 (no match)")
    with pytest.raises(cd.CalendarDeleteError):
        cd.delete_event("Home", "UID-9", runner=boom)


def test_missing_binary_is_delete_error():
    def boom(cmd):
        raise FileNotFoundError("no such helper")
    with pytest.raises(cd.CalendarDeleteError):
        cd.delete_event("Home", "UID-9", runner=boom)


def test_non_json_stdout_is_delete_error():
    with pytest.raises(cd.CalendarDeleteError):
        cd.delete_event("Home", "UID-9", runner=_runner("ok"))


def test_ok_false_is_delete_error():
    with pytest.raises(cd.CalendarDeleteError):
        cd.delete_event("Home", "UID-9", runner=_runner('{"ok":false}'))


def test_missing_ok_is_delete_error():
    with pytest.raises(cd.CalendarDeleteError):
        cd.delete_event("Home", "UID-9", runner=_runner('{"deleted":1}'))


def test_non_object_json_is_delete_error():
    with pytest.raises(cd.CalendarDeleteError):
        cd.delete_event("Home", "UID-9", runner=_runner('[1,2,3]'))


@pytest.mark.parametrize("cal,uid", [("", "UID-9"), ("Home", ""), ("  ", "UID"),
                                     ("Home", "  ")])
def test_empty_cal_or_uid_is_delete_error(cal, uid):
    called = {"n": 0}

    def r(cmd):
        called["n"] += 1
        return '{"ok":true}'
    with pytest.raises(cd.CalendarDeleteError):
        cd.delete_event(cal, uid, runner=r)
    assert called["n"] == 0            # never even spawns on an empty arg


def test_helper_env_override_used_for_cmd0(monkeypatch):
    monkeypatch.setenv("CABINET_CAL_HELPER", "/tmp/custom/cabinet-calread")
    runner = _runner('{"ok":true,"deleted":1}')
    cd.delete_event("Home", "UID-9", runner=runner)
    assert runner.calls[0][0] == "/tmp/custom/cabinet-calread"
