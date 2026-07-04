"""TI-4 — binder_wire ↔ veto_registry wiring (never: persist / lift / freeform).

Fully fixtured: injected record_veto / lift_veto / present / redis, plus one
end-to-end test through the REAL registry against a tmp yml (env-pointed). No
Telegram, no live ledger, no network. The veto branch is DARK + captain-gated,
so these arm it explicitly (inject a transport) or via env."""
from __future__ import annotations

import json

from framework.frontdoor import action_undo, binder_wire

_ACTED_PID = "acted-card-0001"


def _acted_row(pid=_ACTED_PID, step=1, kind="monday_task_create",
               executed_at="2026-07-04T10:00:00Z", subject="thr-x"):
    created = {"monday_id": "555", "board_id": "9", "update_id": "u1"}
    return action_undo.new_row(
        pid=pid, cid="a" * 32, step=step, kind=kind, backend="monday", lane="polads",
        subject=subject, actor={"kind": "officer", "id": "officer:cos"},
        created=created,
        inverse=action_undo.inverse_for(kind, "monday", {"board_id": "9"}, created, {}),
        executed_at=executed_at, jid=f"jid-{step}", canary=False)


def _undo_redis(pid=_ACTED_PID):
    store = {f"cabinet:undo:{pid}": json.dumps({"pid": pid})}
    return lambda k: store.get(k, "")


class ActedRec:
    def __init__(self):
        self.emitted, self.reversed_pids, self.frozen = [], [], []

    def emit(self, **ev):
        self.emitted.append(ev)

    def reverse(self, pid):
        self.reversed_pids.append(pid)
        return {"ok": True, "via": "action-undo", "reversed": [{"step": 1}]}

    def freeze(self, kind, reason):
        self.frozen.append((kind, reason))
        return {"kind": kind}


# --- pid-bound never: now PERSISTS the server-derived scope -------------------

def test_pid_never_records_veto_when_wired():
    row = _acted_row(kind="monday_task_update")
    a = ActedRec()
    calls = []
    def rec_veto(scope, verbatim, ts):
        calls.append((scope, verbatim, ts))
        return {"id": "veto-001"}
    r = binder_wire.handle_captain_update(
        "never: stop auto-creating tasks", f"·{_ACTED_PID}·",
        redis_get=_undo_redis(), emit=a.emit, reverse=a.reverse, freeze=a.freeze,
        journal_rows_for=lambda pid=None: [row], read_ledger_fn=lambda: [],
        record_veto=rec_veto, now="2026-07-06T12:00:00Z")
    assert r["primary"] == "never" and r["veto_id"] == "veto-001"
    assert r["veto_scope"] == {"action_type": "board_status", "lane": "polads"}
    # recorded with the SERVER-derived scope (== veto_scope) + verbatim reply text
    assert calls == [(r["veto_scope"], "never: stop auto-creating tasks",
                      "2026-07-06T12:00:00Z")]
    assert a.reversed_pids == []                       # never never reverses the instance


def test_pid_never_captain_unverified_records_nothing():
    """A veto is UNFORGEABLE — off the CAPTAIN_TELEGRAM_ID-gated path nothing is
    recorded, even with a record_veto injected. The verdict + scope still land."""
    row = _acted_row(kind="monday_task_update")
    a = ActedRec()
    calls = []
    r = binder_wire.handle_captain_update(
        "never: stop", f"·{_ACTED_PID}·",
        redis_get=_undo_redis(), emit=a.emit, reverse=a.reverse, freeze=a.freeze,
        journal_rows_for=lambda pid=None: [row], read_ledger_fn=lambda: [],
        record_veto=lambda *a2: calls.append(1) or {"id": "veto-001"},
        captain_verified=False, now="2026-07-06T12:00:00Z")
    assert r["primary"] == "never" and "veto_id" not in r
    assert r["veto_scope"] == {"action_type": "board_status", "lane": "polads"}
    assert calls == []                                 # NOTHING recorded — unforgeable


def test_pid_never_dark_records_nothing_but_returns_scope():
    """No wiring injected, flag off (dark): the never: verdict + scope return
    unchanged and the registry stays untouched — pre-TI-4 behaviour."""
    row = _acted_row(kind="monday_task_update")
    a = ActedRec()
    r = binder_wire.handle_captain_update(
        "never: no", f"·{_ACTED_PID}·",
        redis_get=_undo_redis(), emit=a.emit, reverse=a.reverse, freeze=a.freeze,
        journal_rows_for=lambda pid=None: [row], read_ledger_fn=lambda: [],
        now="2026-07-06T12:00:00Z")
    assert r["primary"] == "never" and "veto_id" not in r
    assert "registry dark" in r["summary"]


# --- lift veto-NNN -----------------------------------------------------------

def test_lift_veto_command_normalizes_id():
    lifts = []
    def lift(vid, ts):
        lifts.append((vid, ts))
        return {"id": vid, "lifted_at": ts}
    for typed in ("lift veto-2", "lift veto-002", "lift veto 2"):
        lifts.clear()
        r = binder_wire.handle_captain_update(
            typed, "", pending_source=lambda: [], lift_veto=lift,
            redis_get=lambda k: "", now="2026-07-06T12:00:00Z")
        assert r["handled"] and r["veto"] == "lift" and r["veto_id"] == "veto-002"
        assert lifts == [("veto-002", "2026-07-06T12:00:00Z")]


def test_lift_veto_not_found():
    r = binder_wire.handle_captain_update(
        "lift veto-9", "", pending_source=lambda: [],
        lift_veto=lambda vid, ts: None, redis_get=lambda k: "")
    assert r["veto"] == "lift" and "not found" in r["summary"]


def test_lift_unverified_falls_through_to_passthrough():
    r = binder_wire.handle_captain_update(
        "lift veto-2", "", pending_source=lambda: [],
        lift_veto=lambda vid, ts: {"id": vid}, redis_get=lambda k: "",
        captain_verified=False)
    assert r["handled"] is False                       # veto branch not armed


# --- freeform never: -> confirm-pending round-trip ---------------------------

def test_freeform_never_opens_pending_and_presents():
    stored, presented = {}, []
    r = binder_wire.handle_captain_update(
        "never: create tasks on the polads board", "",
        pending_source=lambda: [], list_undo_windows=lambda: [],
        redis_get=lambda k: "", redis_set=lambda k, v: stored.__setitem__(k, v),
        present=lambda m: presented.append(m), now="2026-07-06T12:00:00Z")
    assert r["handled"] and r["veto"] == "pending"
    assert "cabinet:veto-pending" in stored
    assert json.loads(stored["cabinet:veto-pending"])["verbatim"].startswith("never:")
    assert presented and "veto confirm" in presented[0]


def test_freeform_never_dark_falls_through():
    r = binder_wire.handle_captain_update(
        "never: create tasks", "", pending_source=lambda: [],
        list_undo_windows=lambda: [], redis_get=lambda k: "")
    assert r["handled"] is False                       # dark: not armed, passthrough


def test_veto_confirm_records_with_strict_scope_args():
    store = {"cabinet:veto-pending": json.dumps(
        {"verbatim": "never: no tasks here", "scope": {}, "ts": "t"})}
    dels, calls = [], []
    def rec_veto(scope, verbatim, ts):
        calls.append((scope, verbatim, ts))
        return {"id": "veto-003"}
    r = binder_wire.handle_captain_update(
        "veto confirm action_type=task_create board=5091706356 note=ignored", "",
        redis_get=lambda k: store.get(k, ""), redis_del=lambda k: dels.append(k),
        record_veto=rec_veto, now="2026-07-06T12:00:00Z")
    assert r["handled"] and r["veto"] == "confirmed" and r["veto_id"] == "veto-003"
    # only deterministic fields survive; free-text 'note=' is dropped [RT-A10]
    assert calls[0][0] == {"action_type": "task_create", "board": "5091706356"}
    assert calls[0][1] == "never: no tasks here"
    assert dels == ["cabinet:veto-pending"]            # pending cleared on record


def test_veto_confirm_scopeless_keeps_pending():
    store = {"cabinet:veto-pending": json.dumps({"verbatim": "x", "scope": {}})}
    dels, calls, presented = [], [], []
    r = binder_wire.handle_captain_update(
        "veto confirm", "", redis_get=lambda k: store.get(k, ""),
        redis_del=lambda k: dels.append(k),
        record_veto=lambda *a: calls.append(1) or {"id": "y"},
        present=lambda m: presented.append(m), now="t")
    assert r["veto"] == "confirm-need-scope"
    assert calls == [] and dels == []                  # nothing recorded / cleared
    assert presented and "deterministic" in presented[0]


def test_veto_confirm_nothing_pending():
    r = binder_wire.handle_captain_update(
        "veto confirm action_type=task_create", "", redis_get=lambda k: "",
        record_veto=lambda *a: {"id": "z"})
    assert r["handled"] and r["veto"] == "confirm-none"


# --- end-to-end through the REAL registry (env-pointed tmp yml) --------------

def test_integration_pid_never_persists_to_real_registry(tmp_path, monkeypatch):
    from framework.frontdoor import veto_registry
    from framework.fidelity import consequence
    vf = tmp_path / "captain-vetoes.yml"
    vf.write_text("# header\nversion: 1\nnext_id: 1\nvetoes: []\n", encoding="utf-8")
    monkeypatch.setenv("CABINET_VETO_WIRED", "1")
    monkeypatch.setenv("CABINET_CAPTAIN_VETOES", str(vf))
    # the registry's audit event lazily imports emit_consequence — keep it off
    # the real ledger during the test
    monkeypatch.setattr(consequence, "emit_consequence", lambda **e: e)
    row = _acted_row(kind="monday_task_update")
    a = ActedRec()
    r = binder_wire.handle_captain_update(          # NO record_veto -> default wiring
        "never: no auto tasks", f"·{_ACTED_PID}·",
        redis_get=_undo_redis(), emit=a.emit, reverse=a.reverse, freeze=a.freeze,
        journal_rows_for=lambda pid=None: [row], read_ledger_fn=lambda: [],
        now="2026-07-06T12:00:00Z")
    assert r["primary"] == "never" and r["veto_id"] == "veto-001"
    rows = veto_registry.load_vetoes(vf)
    assert len(rows) == 1 and rows[0]["id"] == "veto-001"
    assert rows[0]["verbatim"] == "never: no auto tasks"
    # the recorded veto now blocks the matching kind via the shared predicate
    at = r["veto_scope"]["action_type"]
    assert veto_registry.is_vetoed(at, path=vf) is True
    assert "veto-001" in vf.read_text(encoding="utf-8")
