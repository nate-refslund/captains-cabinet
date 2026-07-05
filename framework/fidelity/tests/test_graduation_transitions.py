"""Lane instrument (2026-07-05) — tests for the graduation-transition sweep
(cabinet/scripts/emit-graduation-transitions.py).

The sweep is the UNLOCKED caller that makes per-cell autonomy movement visible:
graduation.evaluate is stateless (and schg-locked), so the sweep diffs current
state against its own last-seen state file and emits `graduation_transition`
org events on change. Fully fenced: ledgers are injected or written to a
per-test CABINET_EVENT_LOG_DIR tmp dir; the state file lives in tmp via
CABINET_GRADUATION_STATE_FILE; org-event emission is read back from the same
tmp dir (the repo-root conftest additionally sandboxes the whole run).
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "cabinet" / "scripts" / "emit-graduation-transitions.py"

NOW = dt.datetime(2026, 7, 5, 12, 0, tzinfo=dt.timezone.utc)


def _load_sweep():
    spec = importlib.util.spec_from_file_location(
        "emit_graduation_transitions", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ev(ts, *, action_type="monday_task_create", required=True, decision=None,
        outcome="unknown", verdict=None, source=None, lane="polads",
        actor_id="cos", subject="subj-1"):
    """A consequence-ledger row (mirrors the falsifier-report test fixture,
    plus the `subject` field read_ledger's _is_consequence_row requires).
    compute_ratios flattens actor to 'kind:id' — so kind=officer, id=cos
    yields the cell actor 'officer:cos'."""
    ev = {"ts": ts, "actor": {"kind": "officer", "id": actor_id},
          "lane": lane, "action": "action-card", "subject": subject,
          "proposal": {"required": required, "decision": decision},
          "outcome": {"status": outcome},
          "review": {"verdict": verdict, "source": source}}
    if action_type:
        ev["action_type"] = action_type
    return ev


def _fixtured_ledger():
    """One measurable cell (officer:cos, polads, monday_task_create): 3 human-
    confirmed samples → match_rate 1.0 but far below every bar's sample floor
    ⇒ graduation.evaluate returns `propose_only` (the fail-safe state)."""
    return [
        _ev("2026-07-01T10:00:00Z", outcome="ok", verdict="confirmed",
            source="verdict_human", subject="s1"),
        _ev("2026-07-02T10:00:00Z", outcome="ok", verdict="confirmed",
            source="verdict_human", subject="s2"),
        _ev("2026-07-03T09:00:00Z", decision="approved", outcome="ok",
            verdict="confirmed", source="verdict_human", subject="s3"),
        # Unstamped legacy row — must NOT become a watched cell (sentinel).
        _ev("2026-07-03T11:00:00Z", action_type=None, decision="approved",
            outcome="ok", subject="s4"),
    ]


CELL = ("officer:cos", "polads", "monday_task_create")


# --- pure sweep() ------------------------------------------------------------------


def test_active_cells_excludes_unstamped_sentinel():
    m = _load_sweep()
    cells = m.active_cells(_fixtured_ledger())
    assert cells == [CELL]


def test_first_sweep_is_baseline_with_one_first_sighting():
    m = _load_sweep()
    res = m.sweep(_fixtured_ledger(), None, now=NOW)
    assert res["baseline"] is True
    assert res["current"] == {m._cell_key(CELL): "propose_only"}
    assert len(res["transitions"]) == 1
    t = res["transitions"][0]
    assert t["from_state"] is None and t["to_state"] == "propose_only"
    assert t["cell"] == {"actor": "officer:cos", "lane": "polads",
                         "action_type": "monday_task_create"}
    assert t["evidence"]["sample_count"] == 3


def test_no_change_yields_no_transition():
    m = _load_sweep()
    prev = {m._cell_key(CELL): "propose_only"}
    res = m.sweep(_fixtured_ledger(), prev, now=NOW)
    assert res["baseline"] is False
    assert res["transitions"] == []
    assert res["current"] == prev


def test_state_change_yields_transition_with_from_and_to():
    m = _load_sweep()
    prev = {m._cell_key(CELL): "unmeasured"}
    res = m.sweep(_fixtured_ledger(), prev, now=NOW)
    assert [(t["from_state"], t["to_state"]) for t in res["transitions"]] == [
        ("unmeasured", "propose_only")]


def test_vanished_cell_transitions_to_unmeasured_once():
    """A previously-seen cell whose rows left the ledger (rotation/purge) gets
    ONE honest transition to its re-evaluated state instead of silently
    disappearing from the record."""
    m = _load_sweep()
    prev = {m._cell_key(CELL): "graduated"}
    res = m.sweep([], prev, now=NOW)
    assert [(t["from_state"], t["to_state"]) for t in res["transitions"]] == [
        ("graduated", "unmeasured")]
    # …and once recorded, the next sweep is quiet.
    res2 = m.sweep([], res["current"], now=NOW)
    assert res2["transitions"] == []


def test_evaluate_error_yields_no_verdict_and_preserves_state(monkeypatch):
    """FAIL-SAFE: an evaluate error must never read as a state change — the
    cell is skipped, its previous state carries forward, no transition."""
    m = _load_sweep()
    from framework.fidelity import graduation

    def boom(cell, **kw):
        raise RuntimeError("matrix unreadable")

    monkeypatch.setattr(graduation, "evaluate", boom)
    prev = {m._cell_key(CELL): "eligible"}
    res = m.sweep(_fixtured_ledger(), prev, now=NOW)
    assert res["transitions"] == []
    assert res["current"] == prev              # carried forward unchanged
    assert len(res["errors"]) == 1 and "matrix unreadable" in res["errors"][0]["error"]


def test_corrupt_state_key_is_dropped_not_crashed():
    m = _load_sweep()
    prev = {"not-json": "graduated", m._cell_key(CELL): "propose_only"}
    res = m.sweep(_fixtured_ledger(), prev, now=NOW)
    assert res["transitions"] == []
    assert "not-json" not in res["current"]


# --- main() end-to-end (tmp ledger dir + tmp state file) ----------------------------


def _write_ledger(dirpath: Path, rows):
    dirpath.mkdir(parents=True, exist_ok=True)
    f = dirpath / "consequence-events-2026-07-03.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _org_events(dirpath: Path):
    out = []
    for f in sorted(dirpath.glob("events-*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


@pytest.fixture()
def fenced(tmp_path, monkeypatch):
    events = tmp_path / "events"
    state = tmp_path / "state" / "graduation-transitions.json"
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(events))
    monkeypatch.setenv("CABINET_GRADUATION_STATE_FILE", str(state))
    # Hermetic: emit() also mirrors to Postgres when DATABASE_URL is set —
    # never from a test (the Store SQLite mirror already auto-skips on
    # PYTEST_CURRENT_TEST; the DB write has no such guard).
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return events, state


def test_main_first_run_seeds_baseline_silently(fenced, capsys):
    events, state = fenced
    _write_ledger(events, _fixtured_ledger())
    m = _load_sweep()
    assert m.main([]) == 0
    # State seeded…
    doc = json.loads(state.read_text())
    assert doc["cells"] == {m._cell_key(CELL): "propose_only"}
    # …but NO transition event emitted (flood guard).
    assert _org_events(events) == []
    summary = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert summary["baseline_seeded"] is True and summary["emitted"] == 0


def test_main_emit_baseline_flag_emits_first_sightings(fenced):
    events, state = fenced
    _write_ledger(events, _fixtured_ledger())
    m = _load_sweep()
    assert m.main(["--emit-baseline"]) == 0
    evs = _org_events(events)
    assert [e["event_type"] for e in evs] == ["graduation_transition"]
    assert evs[0]["payload"]["from_state"] is None
    assert evs[0]["payload"]["to_state"] == "propose_only"
    assert evs[0]["actor"] == "graduation-sweep"


def test_main_transition_emits_then_goes_quiet(fenced):
    events, state = fenced
    _write_ledger(events, _fixtured_ledger())
    m = _load_sweep()
    # Pre-seed a stale state so the sweep sees a change.
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(
        {"updated_at": "x", "cells": {m._cell_key(CELL): "unmeasured"}}))
    assert m.main([]) == 0
    evs = _org_events(events)
    assert len(evs) == 1
    assert evs[0]["payload"]["from_state"] == "unmeasured"
    assert evs[0]["payload"]["to_state"] == "propose_only"
    # Second run: no change → no new event.
    assert m.main([]) == 0
    assert len(_org_events(events)) == 1


def test_main_dry_run_emits_nothing_and_writes_no_state(fenced, capsys):
    events, state = fenced
    _write_ledger(events, _fixtured_ledger())
    m = _load_sweep()
    assert m.main(["--dry-run"]) == 0
    assert not state.exists()
    assert _org_events(events) == []
    assert "[dry-run]" in capsys.readouterr().out


def test_main_emit_failure_keeps_prev_state_for_retry(fenced, monkeypatch):
    """AT-LEAST-ONCE: a failed emit reverts that cell in the written state so
    the SAME transition re-detects and re-emits on the next sweep."""
    events, state = fenced
    _write_ledger(events, _fixtured_ledger())
    m = _load_sweep()
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(
        {"updated_at": "x", "cells": {m._cell_key(CELL): "unmeasured"}}))

    import framework.events.emitter as emitter

    def broken_emit(*a, **kw):
        raise RuntimeError("ledger disk full")

    # context() so ONLY the emit patch reverts afterwards — a bare
    # monkeypatch.undo() would also strip the `fenced` fixture's env vars
    # (same monkeypatch instance) and the retry would leave the sandbox.
    with monkeypatch.context() as mp:
        mp.setattr(emitter, "emit", broken_emit)
        assert m.main([]) == 0
    doc = json.loads(state.read_text())
    assert doc["cells"][m._cell_key(CELL)] == "unmeasured"   # NOT advanced

    # Retry sweep with the real emitter: the transition now lands.
    assert m.main([]) == 0
    evs = _org_events(events)
    assert [e["payload"]["to_state"] for e in evs] == ["propose_only"]


def test_event_type_is_registered_in_emitter_vocabulary():
    """The sweep's event type must be pre-registered (emit() rejects unknown
    types — the fail-closed vocabulary contract)."""
    from framework.events.emitter import VALID_EVENT_TYPES
    assert "graduation_transition" in VALID_EVENT_TYPES
