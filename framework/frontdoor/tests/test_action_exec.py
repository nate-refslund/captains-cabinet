"""Action executor — fixtured (fake redis / monday / osascript; no live calls)."""
from __future__ import annotations

import json

from framework.frontdoor import action_exec as ax


def _store(steps):
    rec = {"lane": "polads", "steps": steps}
    return lambda k: json.dumps(rec) if k.startswith("cabinet:action:") else ""


class MondaySpy:
    def __init__(self, fail_on: int | None = None):
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, query, variables):
        self.calls.append((query, variables))
        if self.fail_on is not None and len(self.calls) == self.fail_on:
            raise RuntimeError("monday 500")
        if "create_item" in query:
            return {"create_item": {"id": "12345"}}
        return {"create_update": {"id": "u1"}, "change_column_value": {"id": "c1"}}


def test_create_task_executes_and_reports():
    spy = MondaySpy()
    r = ax.deliver_action(
        "pid1", redis_get=_store([{"kind": "monday_task_create",
                                   "payload": {"board_id": "5091706356",
                                               "title": "Ship VIES autofill",
                                               "description": "from scrum"}}]),
        monday_post=spy, osascript=lambda c: "ok")
    assert r["ok"] is True and r["via"] == "action-lane"
    assert r["executed"][0]["monday_id"] == "12345"
    assert len(spy.calls) == 2                     # create_item + description update


def test_update_task_label_based_writes():
    spy = MondaySpy()
    r = ax.deliver_action(
        "pid2", redis_get=_store([{"kind": "monday_task_update",
                                   "payload": {"monday_id": "999",
                                               "board_id": "5091706356",
                                               "set": {"status": "Done"},
                                               "why": "shipped in scrum"}}]),
        monday_post=spy, osascript=lambda c: "ok")
    assert r["ok"] is True
    assert "status" in r["executed"][0]["applied"]
    # label-based write with create_labels_if_missing (people-board gotcha)
    q, v = spy.calls[-1]
    assert "create_labels_if_missing: true" in q
    assert json.loads(v["val"]) == {"label": "Done"}


def test_reminder_passes_values_as_argv_not_script():
    seen = {}
    def osa(cmd):
        seen["cmd"] = cmd
        return "ok"
    evil = 'x" & (do shell script "rm -rf ~") & "'
    r = ax.deliver_action(
        "pid3", redis_get=_store([{"kind": "reminder_create",
                                   "payload": {"title": evil, "list": "Screenpipe Work",
                                               "due_iso": "2026-07-04T09:00"}}]),
        monday_post=MondaySpy(), osascript=osa)
    assert r["ok"] is True
    script = seen["cmd"][2]
    assert evil not in script                      # untrusted text NOT in source
    assert evil in seen["cmd"][3:]                 # it travels as argv


def test_chain_stops_at_first_failure_and_reports_partial():
    spy = MondaySpy(fail_on=3)                     # step1 = 2 calls; step2 fails
    r = ax.deliver_action(
        "pid4", redis_get=_store([
            {"kind": "monday_task_create",
             "payload": {"board_id": "1", "title": "a", "description": "d"}},
            {"kind": "monday_task_update",
             "payload": {"monday_id": "2", "board_id": "1", "set": {"status": "Done"}}},
        ]),
        monday_post=spy, osascript=lambda c: "ok")
    assert r["ok"] is False
    assert "step 2/2" in r["error"]
    assert len(r["executed"]) == 1                 # step 1 reported, not silent


def test_edit_defers_never_executes():
    spy = MondaySpy()
    r = ax.deliver_action(
        "pid5", override_text="change due to Friday",
        redis_get=_store([{"kind": "monday_task_create",
                           "payload": {"board_id": "1", "title": "t"}}]),
        monday_post=spy, osascript=lambda c: "ok")
    assert r["ok"] is False and r.get("edit_deferred") is True
    assert spy.calls == []                         # nothing executed


def test_missing_record_and_dry_run():
    assert ax.deliver_action("gone", redis_get=lambda k: "")["ok"] is False
    r = ax.deliver_action(
        "pid6", dry_run=True,
        redis_get=_store([{"kind": "reminder_create", "payload": {"title": "t"}}]),
        monday_post=MondaySpy(), osascript=lambda c: "ok")
    assert r["ok"] is True and r["executed"][0]["dry_run"] is True
