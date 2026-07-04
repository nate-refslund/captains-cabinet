"""UNDO-1 — write-ahead journal + inverse executors (fixtured: fake monday /
osascript / redis, tmp journal dir; no live calls)."""
from __future__ import annotations

import json

import pytest

from framework.frontdoor import action_undo as au


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    """Journal to a tmp dir; never touch a live Redis."""
    monkeypatch.setenv("CABINET_UNDO_DIR", str(tmp_path / "undo"))
    monkeypatch.setattr(au, "_default_redis_set", lambda *a, **k: None)
    monkeypatch.setattr(au, "_default_redis_get", lambda *a, **k: "")
    monkeypatch.setattr(au, "_default_redis_del", lambda *a, **k: None)
    yield


class FakeMonday:
    """Records every GraphQL call; answers a column read from a seeded map."""
    def __init__(self, columns=None):
        self.calls = []
        self.columns = columns or {}          # {col_id: {"text":.., "value":..}}

    def __call__(self, query, variables):
        self.calls.append((query, variables))
        if "items(ids" in query.replace(" ", ""):     # a column read
            cols = variables.get("cols") or []
            return {"items": [{"column_values": [
                {"id": c, "text": (self.columns.get(c) or {}).get("text"),
                 "value": (self.columns.get(c) or {}).get("value")} for c in cols]}]}
        return {"archive_item": {"id": "x"}, "delete_update": {"id": "x"},
                "change_column_value": {"id": "x"},
                "create_item": {"id": "9001"}, "create_update": {"id": "u1"}}

    def qs(self):
        return " ".join(q for q, _ in self.calls)


def _no_op_del(_k):
    return None


def _journal_executed(pid, step, kind, backend, *, created,
                      payload=None, prestate=None, lane="polads",
                      subject="thread-x", cid=""):
    """Write one COMMITTED journal row (write-ahead + enrichment collapsed)."""
    row = au.new_row(
        pid=pid, cid=cid, step=step, kind=kind, backend=backend, lane=lane,
        subject=subject, actor={"kind": "officer", "id": "officer:cos"},
        prestate=prestate or {}, created=created,
        inverse=au.inverse_for(kind, backend, payload or {}, created, prestate or {}),
        executed_at=au._now())
    return au.journal_step(row)


# --- inverse round-trips per kind --------------------------------------------

def test_create_reverse_archives_never_deletes():
    fm = FakeMonday()
    _journal_executed("pid1", 1, "monday_task_create", "monday",
                      created={"monday_id": "555", "board_id": "9", "update_id": "u1"})
    res = au.reverse("pid1", monday_post=fm, osascript=lambda c: "ok", redis_del=_no_op_del)
    assert res["ok"] is True and res["reversed"][0]["step"] == 1
    assert "archive_item" in fm.qs() and "delete_item" not in fm.qs()   # NEVER delete
    assert "delete_update" in fm.qs()                                   # the desc post


def test_reverse_is_idempotent():
    fm = FakeMonday()
    _journal_executed("pid1b", 1, "monday_task_create", "monday",
                      created={"monday_id": "1", "board_id": "9", "update_id": None})
    au.reverse("pid1b", monday_post=fm, osascript=lambda c: "ok", redis_del=_no_op_del)
    n_after_first = len(fm.calls)
    res2 = au.reverse("pid1b", monday_post=fm, osascript=lambda c: "ok", redis_del=_no_op_del)
    assert res2["ok"] is True and res2.get("already_undone") is True
    assert len(fm.calls) == n_after_first          # second call touched nothing


def test_reverse_unknown_pid_already_undone():
    res = au.reverse("nope", monday_post=lambda *a: {}, osascript=lambda c: "ok",
                     redis_del=_no_op_del)
    assert res["ok"] is True and res["already_undone"] is True and res["reversed"] == []


def test_calendar_reverse_deletes_by_uid_argv():
    seen = {}
    def osa(cmd):
        seen["cmd"] = cmd
        return "ok"
    _journal_executed("pid2", 1, "reminder_create", "calendar",
                      created={"uid": "UID-9", "calendar": "Cabinet"})
    res = au.reverse("pid2", monday_post=lambda *a: {}, osascript=osa, redis_del=_no_op_del)
    assert res["ok"] is True
    assert "UID-9" in seen["cmd"] and "Cabinet" in seen["cmd"]   # values travel as argv
    assert "delete ev" in seen["cmd"][2]                         # never interpolated


def test_apple_reminders_excluded_from_act_first():
    inv = au.inverse_for("reminder_create", "apple_reminders", {}, {}, {})
    assert inv["op"] == "none"
    assert au.act_first_eligible("reminder_create", "apple_reminders") is False
    assert au.act_first_eligible("reminder_create", "calendar") is True
    _journal_executed("pid3", 1, "reminder_create", "apple_reminders", created={"list": "X"})
    res = au.reverse("pid3", monday_post=lambda *a: {}, osascript=lambda c: "ok",
                     redis_del=_no_op_del)
    assert res["ok"] is True and res["reversed"][0].get("skipped")


def test_delegate_has_no_inverse():
    assert au.inverse_for("delegate_work", "delegate", {}, {}, {})["op"] == "none"
    assert au.act_first_eligible("delegate_work", "delegate") is False


# --- compare-and-restore [RT-A11] --------------------------------------------

def test_compare_restore_restores_when_value_unchanged():
    fm = FakeMonday(columns={"status": {"text": "Done"}})      # still what we wrote
    _journal_executed("pid4", 1, "monday_task_update", "monday",
                      created={"note_update_id": None},
                      payload={"monday_id": "7", "board_id": "9", "set": {"status": "Done"}},
                      prestate={"status": {"text": "In Progress"}})
    res = au.reverse("pid4", monday_post=fm, osascript=lambda c: "ok", redis_del=_no_op_del)
    assert res["ok"] is True
    change = [v for q, v in fm.calls if "change_column_value" in q]
    assert change and json.loads(change[-1]["val"]) == {"label": "In Progress"}   # prior restored


def test_compare_restore_dead_letters_on_colleague_edit():
    fm = FakeMonday(columns={"status": {"text": "Blocked"}})   # a colleague changed it
    _journal_executed("pid5", 1, "monday_task_update", "monday",
                      created={"note_update_id": None},
                      payload={"monday_id": "7", "board_id": "9", "set": {"status": "Done"}},
                      prestate={"status": {"text": "In Progress"}})
    res = au.reverse("pid5", monday_post=fm, osascript=lambda c: "ok", redis_del=_no_op_del)
    assert res["ok"] is False
    dl = res["manual_cleanup"][0]["result"]["dead_letters"]
    assert dl[0]["reason"] == "drifted" and dl[0]["current"] == "Blocked"
    assert not any("change_column_value" in q for q, _ in fm.calls)   # NEVER clobbered
    assert au._read_journal(pid="pid5")[0]["status"] == "reversal_failed"


def test_compare_restore_clears_previously_empty_column():
    fm = FakeMonday(columns={"priority": {"text": "High"}})
    _journal_executed("pid5b", 1, "monday_task_update", "monday",
                      created={"note_update_id": None},
                      payload={"monday_id": "7", "board_id": "9", "set": {"priority": "High"}},
                      prestate={"priority": {"text": None}})       # was empty
    res = au.reverse("pid5b", monday_post=fm, osascript=lambda c: "ok", redis_del=_no_op_del)
    assert res["ok"] is True
    change = [v for q, v in fm.calls if "change_column_value" in q]
    assert change and change[-1]["val"] == "{}"                 # cleared, not a label


# --- ordering, crash reconciliation, single-step undo ------------------------

def test_reverse_runs_in_reverse_step_order():
    order = []
    def fm(query, variables):
        if "items(ids" in query.replace(" ", ""):
            return {"items": [{"column_values": [{"id": "status", "text": "Done"}]}]}
        if "archive_item" in query:
            order.append("archive")
        if "change_column_value" in query:
            order.append("restore")
        return {"archive_item": {"id": "x"}, "change_column_value": {"id": "x"}}
    _journal_executed("pid8", 1, "monday_task_create", "monday",
                      created={"monday_id": "1", "board_id": "9", "update_id": None})
    _journal_executed("pid8", 2, "monday_task_update", "monday",
                      created={"note_update_id": None},
                      payload={"monday_id": "1", "board_id": "9", "set": {"status": "Done"}},
                      prestate={"status": {"text": "New"}})
    au.reverse("pid8", monday_post=fm, osascript=lambda c: "ok", redis_del=_no_op_del)
    assert order == ["restore", "archive"]         # step 2 reversed before step 1


def test_crash_row_reconcilable_never_reexecuted():
    wa = au.new_row(pid="pid6", cid="", step=1, kind="monday_task_create",
                    backend="monday", lane="polads", subject="s", actor=None,
                    inverse=au.inverse_for("monday_task_create", "monday", {}, {}, {}),
                    executed_at=None)                # write-ahead only — the mutation never returned
    au.journal_step(wa)
    fm = FakeMonday()
    res = au.reverse("pid6", monday_post=fm, osascript=lambda c: "ok", redis_del=_no_op_del)
    assert res["ok"] is True and res.get("already_undone") is True
    assert fm.calls == []                           # a crash row is NEVER re-executed
    rec = au.find_reconcilable(pid="pid6")
    assert len(rec) == 1 and rec[0]["step"] == 1


def test_undo_by_journal_id_reverses_one_step():
    fm = FakeMonday()
    r1 = _journal_executed("pid7", 1, "monday_task_create", "monday",
                           created={"monday_id": "1", "board_id": "9", "update_id": None})
    _journal_executed("pid7", 2, "monday_task_update", "monday",
                      created={"note_update_id": None},
                      payload={"monday_id": "1", "board_id": "9", "set": {"status": "Done"}},
                      prestate={"status": {"text": "New"}})
    res = au.undo(r1["jid"], monday_post=fm, osascript=lambda c: "ok", redis_del=_no_op_del)
    assert res["ok"] is True and res["reversed"][0]["step"] == 1
    rows = {r["step"]: r for r in au._read_journal(pid="pid7")}
    assert rows[1]["status"] == "reversed" and rows[2]["status"] == "executed"


def test_partial_reversal_returns_manual_cleanup():
    # step 2 (calendar) reverses fine; step 1 (update) dead-letters on drift.
    def fm(query, variables):
        if "items(ids" in query.replace(" ", ""):
            return {"items": [{"column_values": [{"id": "status", "text": "Blocked"}]}]}
        return {"change_column_value": {"id": "x"}}
    _journal_executed("pid9", 1, "monday_task_update", "monday",
                      created={"note_update_id": None},
                      payload={"monday_id": "7", "board_id": "9", "set": {"status": "Done"}},
                      prestate={"status": {"text": "New"}})
    _journal_executed("pid9", 2, "reminder_create", "calendar",
                      created={"uid": "U", "calendar": "Cabinet"})
    res = au.reverse("pid9", monday_post=fm, osascript=lambda c: "ok", redis_del=_no_op_del)
    assert res["ok"] is False
    assert [m["step"] for m in res["manual_cleanup"]] == [1]     # only the drifted step
    assert [r["step"] for r in res["reversed"]] == [2]          # calendar still reversed


# --- acted consequence event (RT-B1 / RT-B6) ---------------------------------

def test_acted_event_unknown_outcome_never_pending_and_validates():
    from framework.acting import loop
    from framework.fidelity.consequence import validate_consequence
    row = au.new_row(pid="p", cid="b" * 32, step=1, kind="monday_task_update",
                     backend="monday", lane="polads", subject="thread-x",
                     actor={"kind": "officer", "id": "officer:cos"},
                     created={"note_update_id": None}, executed_at=au._now())
    ev = au.acted_event({"kind": "monday_task_update", "title": "t"}, row)
    assert ev["outcome"] == {"status": "unknown"}
    assert ev["proposal"] == {"required": False, "decision": None}
    assert ev["action_type"] == "board_status"
    validate_consequence(ev)                        # schema-valid (raises otherwise)
    assert loop.pending_proposals(rows=[ev]) == []  # never enters the pending set


def test_acted_event_action_type_stamped_or_absent():
    from framework.acting import loop
    # [GERM-2] a create is a live enum member now — the acted event carries it.
    row = au.new_row(pid="p2", cid="", step=1, kind="monday_task_create",
                     backend="monday", lane="polads", subject="s", actor=None,
                     executed_at=au._now())
    ev = au.acted_event(None, row)
    assert ev["action_type"] == "task_create"
    assert loop.pending_proposals(rows=[ev]) == []
    # The original invariant survives: an UNMAPPED kind stays ABSENT — never a
    # literal null and never a fabricated stamp.
    row2 = au.new_row(pid="p3", cid="", step=1, kind="future_kind",
                      backend="monday", lane="polads", subject="s", actor=None,
                      executed_at=au._now())
    ev2 = au.acted_event(None, row2)
    assert "action_type" not in ev2


# --- freeze / pointer / validation -------------------------------------------

def test_freeze_and_is_frozen_fail_closed():
    store = {}
    rset = lambda k, v, ttl: store.__setitem__(k, v)
    rget = lambda k: store.get(k, "")
    assert au.is_frozen("task_create", redis_get=rget) is False
    au.freeze("task_create", "undo-rate breach", redis_set=rset)
    assert au.is_frozen("task_create", redis_get=rget) is True
    store.clear()                                   # Redis flushed
    assert au.is_frozen("task_create", redis_get=rget) is True    # durable JSONL mirror holds
    def boom(_k):
        raise RuntimeError("redis down")
    assert au.is_frozen("anything", redis_get=boom) is True       # fail-closed


def test_pointer_write_and_read_roundtrip():
    store = {}
    rset = lambda k, v, ttl: store.__setitem__(k, (v, ttl))
    rget = lambda k: store.get(k, ("", None))[0]
    au.write_pointer("pidP", [{"jid": "j1", "step": 1, "kind": "monday_task_create"}],
                     "2026-07-04T10:00:00Z", redis_set=rset)
    _v, ttl = store["cabinet:undo:pidP"]
    assert ttl == au.POINTER_TTL_S
    p = au.read_pointer("pidP", redis_get=rget)
    assert p["steps"][0]["jid"] == "j1" and p["executed_at"] == "2026-07-04T10:00:00Z"


def test_journal_step_rejects_malformed_row():
    with pytest.raises(au.UndoJournalError):
        au.journal_step({"pid": "p"})               # missing jid/kind/status/step


def test_dry_inverse_spec_replays_to_no_op():
    """A dry-run inverse (empty created args) applied through the registry is a
    guaranteed no-op — the impl-plan's dry-chain-replays-to-no-op invariant, and
    the crash-safety guard that a row with no created ids is never re-executed."""
    fm = FakeMonday()
    for kind, backend in (("monday_task_create", "monday"),
                          ("monday_task_update", "monday"),
                          ("reminder_create", "calendar")):
        spec = au.inverse_for(kind, backend, {}, {}, {})    # dry: no created ids
        res = au.INVERSE_OPS[spec["op"]](spec["args"], monday_post=fm,
                                         osascript=lambda c: "ok")
        assert res["ok"] is True and not res.get("dead_letters")
    assert fm.calls == []                            # nothing touched a backend


def test_deliver_then_reverse_end_to_end(monkeypatch):
    """Integration: deliver a create (journals a reversible row), then reverse it
    from the journal alone — archive, never delete."""
    from framework.frontdoor import action_exec as ax
    monkeypatch.setattr(ax, "_redis", lambda *a, **k: "")
    rec = {"lane": "polads", "subject": "s", "cid": "c" * 32,
           "steps": [{"kind": "monday_task_create",
                      "payload": {"board_id": "9", "title": "t", "description": "d"}}]}
    ax.deliver_action("pidI", redis_get=lambda k: json.dumps(rec),
                      monday_post=FakeMonday(), osascript=lambda c: "ok")
    fm = FakeMonday()
    res = au.reverse("pidI", monday_post=fm, osascript=lambda c: "ok", redis_del=_no_op_del)
    assert res["ok"] is True
    assert "archive_item" in fm.qs() and "delete_item" not in fm.qs()
