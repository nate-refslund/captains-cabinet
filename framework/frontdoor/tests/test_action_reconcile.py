"""UNDO-3 — TTL-survival sweep + silent-revert + journal GC (fully fixtured:
injected journal rows / Monday probe / ledger reader / emit; tmp journal dir; no
live APIs)."""
from __future__ import annotations

import pytest

from framework.env import captain_name
from framework.fidelity import consequence
from framework.frontdoor import action_reconcile as ar
from framework.frontdoor import action_undo as au
from framework.frontdoor import binder_wire as bw


@pytest.fixture(autouse=True)
def _hermetic(tmp_path, monkeypatch):
    """Journal + ledger to tmp dirs; the default gc/read paths never touch a live
    location, and emit_consequence (when used) writes only under tmp."""
    monkeypatch.setenv("CABINET_UNDO_DIR", str(tmp_path / "undo"))
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    yield


def _row(pid="p1", step=1, kind="monday_task_create", *, canary=False, created=None,
         executed_at="2026-07-04T10:00:00Z", ttl="2026-07-06T10:00:00Z",
         status="executed", subject="thr"):
    created = created if created is not None else {
        "monday_id": "555", "board_id": "9", "update_id": "u1"}
    row = au.new_row(
        pid=pid, cid="a" * 32, step=step, kind=kind, backend="monday", lane="bakery",
        subject=subject, actor={"kind": "officer", "id": "officer:cos"}, created=created,
        inverse=au.inverse_for(kind, "monday", {"board_id": "9"}, created, {}),
        executed_at=executed_at, jid=f"j{step}", status=status, canary=canary)
    row["ttl_expires_at"] = ttl        # pin the survival clock for the test
    return row


class Rec:
    def __init__(self):
        self.emitted = []

    def emit(self, **ev):
        self.emitted.append(ev)


# --- TTL survival (the first machine outcome label) --------------------------

def test_ttl_survived_emits_ok_review_untouched():
    row = _row()
    rec = Rec()
    res = ar.run_sweep(now="2026-07-08T10:00:00Z", journal_rows=[row],
                       monday_probe=lambda r: {"exists": True, "archived": False},
                       read_ledger_fn=lambda: [], emit=rec.emit, gc=False)
    assert res["ttl_ok"] == ["j1"] and res["silent_reverts"] == []
    ev = rec.emitted[0]
    assert ev["outcome"]["status"] == "ok"
    assert "ttl-48h survived" in ev["outcome"]["evidence"]
    assert "review" not in ev                       # a machine outcome writes NO review
    assert ev["proposal"] == {"required": False, "decision": None}


def test_no_probe_assumes_survived_never_fabricates_revert():
    row = _row()
    rec = Rec()
    res = ar.run_sweep(now="2026-07-08T10:00:00Z", journal_rows=[row],
                       monday_probe=None, read_ledger_fn=lambda: [], emit=rec.emit, gc=False)
    assert res["ttl_ok"] == ["j1"] and res["silent_reverts"] == []


def test_within_ttl_window_not_swept():
    row = _row(ttl="2026-07-10T10:00:00Z")           # still inside the 48h window
    rec = Rec()
    ar.run_sweep(now="2026-07-08T10:00:00Z", journal_rows=[row],
                 monday_probe=lambda r: {"exists": False}, read_ledger_fn=lambda: [],
                 emit=rec.emit, gc=False)
    assert rec.emitted == []


def test_canary_rows_never_reconciled():
    row = _row(canary=True)
    rec = Rec()
    res = ar.run_sweep(now="2026-07-08T10:00:00Z", journal_rows=[row],
                       monday_probe=lambda r: {"exists": False}, read_ledger_fn=lambda: [],
                       emit=rec.emit, gc=False)
    assert rec.emitted == [] and res["ttl_ok"] == [] and res["silent_reverts"] == []


def test_demo_rows_never_reconciled():
    """The hatch-seeded receipt-anatomy row (emit-demo-receipt.sh, demo: true)
    is inert for the sweep: a past-TTL demo row must never mint a machine
    label — with no Monday item its probe reports intact, so without the skip
    it would conservatively verdict a FALSE ttl_ok from fake work."""
    row = _row(created={})                          # demo rows create nothing real
    row["demo"] = True
    rec = Rec()
    res = ar.run_sweep(now="2026-07-08T10:00:00Z", journal_rows=[row],
                       monday_probe=lambda r: {"exists": True, "archived": False},
                       read_ledger_fn=lambda: [], emit=rec.emit, gc=False)
    assert rec.emitted == [] and res["ttl_ok"] == [] and res["silent_reverts"] == []


def test_non_executed_and_reversed_rows_skipped():
    reversed_row = _row(status="reversed")
    crash_row = _row(step=2, executed_at=None)       # write-ahead only, never executed
    rec = Rec()
    res = ar.run_sweep(now="2026-07-08T10:00:00Z", journal_rows=[reversed_row, crash_row],
                       monday_probe=lambda r: {"exists": True, "archived": False},
                       read_ledger_fn=lambda: [], emit=rec.emit, gc=False)
    assert rec.emitted == [] and res["ttl_ok"] == []


# --- silent revert (the estate's first negative machine labels) --------------

def test_silent_revert_emits_failed_wrong_verdict_judge():
    row = _row()
    rec = Rec()
    res = ar.run_sweep(now="2026-07-08T10:00:00Z", journal_rows=[row],
                       monday_probe=lambda r: {"exists": False, "archived": False},
                       read_ledger_fn=lambda: [], emit=rec.emit, gc=False)
    assert res["silent_reverts"] == ["j1"] and res["ttl_ok"] == []
    ev = rec.emitted[0]
    assert ev["outcome"]["status"] == "failed"
    assert ev["review"] == {"verdict": "wrong", "source": "verdict_judge",
                            "reviewed_at": "2026-07-08T10:00:00Z"}


def test_silent_revert_nate_attributed_upgrades_to_human():
    row = _row()
    rec = Rec()
    probe = lambda r: {"exists": False, "archived": True, "reverted_by_captain": True}
    ar.run_sweep(now="2026-07-08T10:00:00Z", journal_rows=[row], monday_probe=probe,
                 read_ledger_fn=lambda: [], emit=rec.emit, gc=False)
    ev = rec.emitted[0]
    assert ev["review"]["verdict"] == "wrong" and ev["review"]["source"] == "verdict_human"
    assert f"attributed to {captain_name()}" in ev["outcome"]["evidence"]


# --- idempotency + the ordering guarantee (RT-B1) ----------------------------

def test_confirmed_record_is_skipped_never_overwritten():
    row = _row()
    base = au.acted_event(None, row)
    confirmed = bw.acted_verdict_event(base, "confirmed", reviewed_at="2026-07-06T09:00:00Z")
    rec = Rec()
    res = ar.run_sweep(now="2026-07-08T10:00:00Z", journal_rows=[row],
                       monday_probe=lambda r: {"exists": True, "archived": False},
                       read_ledger_fn=lambda: [confirmed], emit=rec.emit, gc=False)
    assert res["skipped"] == 1 and rec.emitted == []        # human confirm untouched


def test_second_sweep_reads_own_output_and_skips():
    """Idempotent against the real (tmp) ledger: the first sweep's ttl_ok row is
    read back on the second sweep (outcome=ok) and skipped — no double-emit."""
    row = _row()
    r1 = ar.run_sweep(now="2026-07-08T10:00:00Z", journal_rows=[row],
                      monday_probe=lambda r: {"exists": True, "archived": False}, gc=False)
    assert r1["ttl_ok"] == ["j1"]
    r2 = ar.run_sweep(now="2026-07-08T11:00:00Z", journal_rows=[row],
                      monday_probe=lambda r: {"exists": True, "archived": False}, gc=False)
    assert r2["ttl_ok"] == [] and r2["skipped"] == 1


def test_confirm_then_ttl_sweep_preserves_confirm_end_to_end():
    """The RT-B1 lifecycle across both modules: a human confirm lands, then the
    48h sweep runs and the confirm survives — the sweep skips the ok cell."""
    row = _row()
    base = au.acted_event(None, row)
    consequence.emit_consequence(
        **bw.acted_verdict_event(base, "confirmed", reviewed_at="2026-07-06T09:00:00Z"))
    rec = Rec()
    res = ar.run_sweep(now="2026-07-08T10:00:00Z", journal_rows=[row],
                       monday_probe=lambda r: {"exists": True, "archived": False},
                       emit=rec.emit, gc=False)
    assert res["skipped"] == 1 and rec.emitted == []
    live = consequence.read_ledger()
    assert len(live) == 1 and live[0]["review"]["verdict"] == "confirmed"


# --- per-cell human-revert-rate ----------------------------------------------

def _acted(ts, outcome, review=None, *, required=False, action_type="board_status"):
    e = {"ts": ts, "actor": {"kind": "officer", "id": "officer:cos"}, "lane": "bakery",
         "action": "acted:monday_task_update", "subject": "s" + ts,
         "action_type": action_type, "refs": [],
         "proposal": {"required": required,
                      "decision": None if required is False else "approved"},
         "outcome": outcome}
    if review:
        e["review"] = review
    return e


def test_human_revert_rate_counts_human_undos_only():
    ledger = [
        _acted("t1", {"status": "failed", "evidence": "u"},
               {"verdict": "wrong", "source": "verdict_human"}),      # human undo
        _acted("t2", {"status": "ok", "evidence": "c"},
               {"verdict": "confirmed", "source": "verdict_human"}),  # confirm
        _acted("t3", {"status": "ok", "evidence": "ttl-48h survived"}),  # machine ttl_ok
        _acted("t4", {"status": "failed", "evidence": "j"},
               {"verdict": "wrong", "source": "verdict_judge"}),      # MACHINE revert (not counted)
        # a PROPOSE row (required=True) is excluded entirely:
        _acted("t5", {"status": "ok", "evidence": "x"},
               {"verdict": "confirmed", "source": "verdict_human"}, required=True),
    ]
    rates = ar.human_revert_rates(ledger)
    key = "officer:officer:cos|bakery|board_status"
    assert rates[key]["acts"] == 4                 # the 4 acted (required=false) rows
    assert rates[key]["human_reverts"] == 1        # only the verdict_human undo
    assert abs(rates[key]["rate"] - 0.25) < 1e-9


# --- Monday probe (item_state / item_activity / attribution) -----------------

class FakeMonday:
    def __init__(self, state="active", logs=None):
        self.state, self.logs, self.calls = state, logs or [], []

    def __call__(self, q, v):
        self.calls.append((q, v))
        if "activity_logs" in q:
            return {"items": [{"activity_logs": self.logs}]}
        return {"items": [{"id": "555", "state": self.state}]}


def test_item_state_and_activity_parse_and_filter():
    fm = FakeMonday(state="archived", logs=[
        {"event": "archive_pulse", "user_id": 42, "created_at": "2026-07-07T00:00:00Z"},
        {"event": "create_pulse", "user_id": 42, "created_at": "2026-07-04T00:00:00Z"}])
    assert ar.item_state(fm, "555") == {"exists": True, "archived": True}
    acts = ar.item_activity(fm, "555", since="2026-07-05T00:00:00Z")
    assert len(acts) == 1 and acts[0]["event"] == "archive_pulse"   # older create filtered out
    assert ar.item_state(lambda q, v: {"items": []}, "999") == {
        "exists": False, "archived": False}                          # not found -> hard delete


def test_make_probe_attributes_nate_revert_and_skips_non_monday():
    fm = FakeMonday(state="archived", logs=[
        {"event": "archive_pulse", "user_id": "ADA", "created_at": "2026-07-07T00:00:00Z"}])
    probe = ar.make_monday_probe(fm, nate_user_id="ADA")
    res = probe({"created": {"monday_id": "555"}, "executed_at": "2026-07-04T00:00:00Z"})
    assert res["archived"] is True and res["reverted_by_captain"] is True
    # a non-Monday row (calendar backend, no monday_id) is reported intact.
    assert ar.make_monday_probe(fm)({"created": {}}) == {
        "exists": True, "archived": False, "reverted_by_captain": False}


def test_make_probe_no_nate_id_never_attributes():
    fm = FakeMonday(state="deleted", logs=[
        {"event": "delete_pulse", "user_id": "SOMEONE", "created_at": "2026-07-07T00:00:00Z"}])
    probe = ar.make_monday_probe(fm)                    # no nate_user_id configured
    res = probe({"created": {"monday_id": "555"}, "executed_at": "2026-07-04T00:00:00Z"})
    assert res["archived"] is True and res["reverted_by_captain"] is False


# --- journal GC (>30d) -------------------------------------------------------

def test_journal_gc_prunes_old_keeps_recent_and_junk(tmp_path):
    d = tmp_path / "jdir"
    d.mkdir()
    old = d / "undo-journal-2026-05-01.jsonl"
    old.write_text('{"jid":"x"}\n')
    recent = d / "undo-journal-2026-07-03.jsonl"
    recent.write_text('{"jid":"y"}\n')
    junk = d / "undo-journal-notadate.jsonl"           # non-date name -> never touched
    junk.write_text("{}\n")
    res = ar.gc_journal(now="2026-07-08T10:00:00Z", retention_days=30, journal_dir=str(d))
    assert res["pruned"] == ["undo-journal-2026-05-01.jsonl"]
    assert not old.exists() and recent.exists() and junk.exists()
    assert res["kept"] >= 1


def test_gc_missing_dir_is_noop():
    assert ar.gc_journal(now="2026-07-08T10:00:00Z",
                         journal_dir="/nonexistent/undo/dir") == {"pruned": [], "kept": 0}


# --- ACTED-EVENT IDENTITY FIX (germline batch 2026-07-05): sweep parity -------
# End-to-end against the REAL executor + REAL fenced ledger/journal (no injected
# journal rows / ledger / emit): deliver_action(act_first=True) now emits the
# per-step acted row itself (action_exec._emit_acted_consequence) on the exact
# identity this sweep recomputes — so the TTL sweep SUPERSEDES that row in
# place. Pre-fix the lane's card-level 'action-card' emit never matched the
# recomputed identity: the sweep minted a SECOND row and the unknown row
# orphaned forever (2 rows/act double-count).

def test_ttl_sweep_supersedes_executor_emitted_acted_row(monkeypatch):
    from framework.acting import loop
    from framework.fidelity.consequence import read_ledger
    from framework.frontdoor import action_exec as ax

    # hermetic transports (the autouse fixture fences the dirs; the executor's
    # own redis paths are neutered exactly as test_action_exec.py does)
    monkeypatch.setattr(ax, "_redis", lambda *a, **k: "")
    monkeypatch.setattr(au, "_default_redis_set", lambda *a, **k: None)
    monkeypatch.setattr(au, "_default_redis_get", lambda *a, **k: "")
    monkeypatch.setattr(au, "_default_redis_del", lambda *a, **k: None)
    monkeypatch.setattr(ax, "_load_act_first_surfaces",
                        lambda: {"denylist": {}, "caps": {"per_kind_per_day": 20,
                                                          "estate_per_day": 40}})
    import json
    steps = [{"kind": "monday_task_create",
              "payload": {"board_id": "42424242", "title": "t"}}]
    rec = {"lane": "bakery", "subject": "close cmt", "steps": steps,
           "steps_sha256": ax._canonical_sha(steps)}

    def getter(k):
        return json.dumps(rec) if k.startswith("cabinet:action:") else ""

    class Monday:
        def __call__(self, query, variables):
            if "create_item" in query:
                return {"create_item": {"id": "12345"}}
            return {"create_update": {"id": "u1"}}

    out = ax.deliver_action("psweep", act_first=True, redis_get=getter,
                            monday_post=Monday(), osascript=lambda c: "ok",
                            redis_incr=lambda k, t: None)
    assert out["ok"] is True

    led = read_ledger()
    acted = [e for e in led if (e.get("action") or "").startswith("acted:")]
    assert len(acted) == 1 and acted[0]["outcome"] == {"status": "unknown"}

    # sweep with DEFAULT seams (real fenced journal + ledger + emit), far past
    # the 48h TTL; no probe → conservative ttl_ok.
    res = ar.run_sweep(now="2027-01-01T00:00:00Z", monday_probe=None, gc=False)
    assert len(res["ttl_ok"]) == 1 and res["silent_reverts"] == []

    led2 = read_ledger()
    acted2 = [e for e in led2 if (e.get("action") or "").startswith("acted:")]
    assert len(acted2) == 1                       # superseded in place, no 2nd mint
    assert acted2[0]["outcome"]["status"] == "ok"
    assert loop.proposal_id(acted2[0]) == loop.proposal_id(acted[0])   # same identity
    # no permanent outcome:unknown orphan survives the sweep
    assert not [e for e in led2 if (e.get("outcome") or {}).get("status") == "unknown"]

    # idempotent: the superseded row now gates the second pass (skipped, not
    # re-emitted) — pre-fix this skipped=0 + re-minted forever.
    res2 = ar.run_sweep(now="2027-01-01T00:00:00Z", monday_probe=None, gc=False)
    assert res2["ttl_ok"] == [] and res2["skipped"] == 1
