"""Tests for Component 3 — the explicit trust ladder.

Non-negotiable properties under test:
  1. Fail-closed load: a missing/broken ladder file -> single would-like-to rung.
  2. Only the grand-plan rung vocabulary is valid; junk rungs are dropped.
  3. A rung is EARNED only when EVERY granted cell is `graduated`.
  4. A ceiling rung (granted cell maps to a hard-ceiling risk_class) is
     classified blocked_by_ceiling — NEVER 'earned' (no auto-advance path).
  5. propose_next_rung SURFACES, never grants. grant_rung is the only path that
     emits trust_rung_granted, and rejects an unknown rung.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, _ROOT)

from framework.learning import trust_ladder as T  # noqa: E402


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
    monkeypatch.setenv("CABINET_PRODUCT_SLUG", "testprod")
    monkeypatch.delenv("DATABASE_URL", raising=False)


def _write_ladder(tmp_path, body: str) -> Path:
    root = tmp_path / "cab"
    (root / "instance" / "config").mkdir(parents=True)
    (root / "instance" / "config" / "trust-ladder.yml").write_text(body)
    return root


# --------------------------------------------------------------------------
# 1. Fail-closed load.
# --------------------------------------------------------------------------

def test_missing_file_defaults_to_base_rung(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    ladder = T.load_ladder(cabinet_root=root)
    assert len(ladder) == 1
    assert ladder[0].name == T.BASE_RUNG
    assert ladder[0].grants == []


def test_broken_yaml_defaults_to_base_rung(tmp_path):
    root = _write_ladder(tmp_path, "rungs: [ this is : not : valid yaml ][")
    ladder = T.load_ladder(cabinet_root=root)
    assert [r.name for r in ladder] == [T.BASE_RUNG]


def test_empty_rungs_defaults_to_base(tmp_path):
    root = _write_ladder(tmp_path, "rungs: []\n")
    ladder = T.load_ladder(cabinet_root=root)
    assert [r.name for r in ladder] == [T.BASE_RUNG]


# --------------------------------------------------------------------------
# 2. Only the valid vocabulary survives.
# --------------------------------------------------------------------------

def test_junk_rung_names_dropped(tmp_path):
    root = _write_ladder(tmp_path, """
rungs:
  - name: super-autonomous
    lane: polads
    grants:
      - { action_type: task_status_move }
  - name: ive-done
    lane: polads
    grants:
      - { action_type: task_status_move }
""")
    ladder = T.load_ladder(cabinet_root=root)
    names = [r.name for r in ladder]
    assert "super-autonomous" not in names
    assert "ive-done" in names
    # base rung is injected + first.
    assert names[0] == T.BASE_RUNG


# --------------------------------------------------------------------------
# 3. Earned requires ALL granted cells graduated.
# --------------------------------------------------------------------------

def _eval_factory(states: dict):
    """states maps action_type -> (state, sample_count)."""
    def fn(cell):
        _actor, _lane, at = cell
        st, n = states.get(at, ("unmeasured", None))
        return {"state": st, "evidence": {"sample_count": n}}
    return fn


def test_rung_earned_when_all_cells_graduated(tmp_path, monkeypatch):
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "polads",
               [("polads", "task_status_move"), ("polads", "label")], None, []),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung", lambda lane=None: "would-like-to")
    ev = _eval_factory({"task_status_move": ("graduated", 30),
                        "label": ("graduated", 25)})
    res = T.evaluate_ladder("officer:cos", "polads", evaluate_fn=ev)
    assert [e["rung"]["name"] for e in res["earned"]] == ["ive-done"]
    assert res["pending"] == []


def test_rung_pending_when_one_cell_not_graduated(tmp_path, monkeypatch):
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "polads",
               [("polads", "task_status_move"), ("polads", "label")], None, []),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung", lambda lane=None: "would-like-to")
    ev = _eval_factory({"task_status_move": ("graduated", 30),
                        "label": ("eligible", 18)})
    res = T.evaluate_ladder("officer:cos", "polads", evaluate_fn=ev)
    assert res["earned"] == []
    assert [e["rung"]["name"] for e in res["pending"]] == ["ive-done"]


def test_min_samples_override_blocks_earn(tmp_path, monkeypatch):
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "polads", [("polads", "task_status_move")], 50, []),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung", lambda lane=None: "would-like-to")
    # graduated but only 30 samples < the rung's 50 override -> pending.
    ev = _eval_factory({"task_status_move": ("graduated", 30)})
    res = T.evaluate_ladder("officer:cos", "polads", evaluate_fn=ev)
    assert res["earned"] == []
    assert [e["rung"]["name"] for e in res["pending"]] == ["ive-done"]


def test_rung_with_no_grants_never_earned(tmp_path, monkeypatch):
    rungs = [T.Rung("would-like-to", None, [], None, []),
             T.Rung("ive-done", "polads", [], None, [])]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung", lambda lane=None: "would-like-to")
    res = T.evaluate_ladder("officer:cos", "polads", evaluate_fn=_eval_factory({}))
    assert res["earned"] == []


# --------------------------------------------------------------------------
# 4. Ceiling rung never earns — blocked_by_ceiling.
# --------------------------------------------------------------------------

def test_ceiling_rung_is_blocked_not_earned(tmp_path, monkeypatch):
    # external_message maps to external_comms (hard ceiling) via the real matrix.
    ceiling = T._grants_touch_ceiling([("polads", "external_message")])
    assert ceiling == ["external_comms"]  # sanity: matrix mapping holds

    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "polads", [("polads", "external_message")], None, ceiling),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung", lambda lane=None: "would-like-to")
    # even if the cell is fully graduated, it must NOT be 'earned'.
    ev = _eval_factory({"external_message": ("graduated", 100)})
    res = T.evaluate_ladder("officer:cos", "polads", evaluate_fn=ev)
    assert res["earned"] == []
    assert [e["rung"]["name"] for e in res["blocked_by_ceiling"]] == ["ive-done"]
    assert res["blocked_by_ceiling"][0]["ceiling"] == ["external_comms"]


# --------------------------------------------------------------------------
# 5. propose_next_rung surfaces; grant_rung is the only grant path.
# --------------------------------------------------------------------------

def test_propose_surfaces_lowest_earned_non_ceiling(tmp_path, monkeypatch):
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "polads", [("polads", "task_status_move")], None, []),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung", lambda lane=None: "would-like-to")
    ev = _eval_factory({"task_status_move": ("graduated", 30)})

    enq = []
    emitted = []
    prop = T.propose_next_rung(
        "officer:cos", "polads", evaluate_fn=ev,
        enqueue_fn=lambda item: enq.append(item) or "sid",
        emit_fn=lambda et, actor, payload: emitted.append((et, payload)),
    )
    assert prop is not None
    assert prop["rung"] == "ive-done"
    assert prop["ceiling"] is False
    assert prop["enqueued_id"] == "sid"
    assert enq[0]["source"] == "trust-ladder"
    assert ("trust_rung_proposed", {"actor_id": "officer:cos", "lane": "polads",
            "rung": "ive-done", "ceiling": False, "urgency_tier": "batch"}) in emitted


def test_propose_returns_none_when_nothing_earned(tmp_path, monkeypatch):
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "polads", [("polads", "task_status_move")], None, []),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung", lambda lane=None: "would-like-to")
    ev = _eval_factory({"task_status_move": ("eligible", 10)})
    prop = T.propose_next_rung("officer:cos", "polads", evaluate_fn=ev,
                               enqueue_fn=lambda i: "x", emit_fn=lambda *a, **k: None)
    assert prop is None


def test_propose_ceiling_rung_flagged_captain_only(tmp_path, monkeypatch):
    ceiling = T._grants_touch_ceiling([("polads", "external_message")])
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "polads", [("polads", "external_message")], None, ceiling),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung", lambda lane=None: "would-like-to")
    ev = _eval_factory({"external_message": ("graduated", 100)})
    prop = T.propose_next_rung("officer:cos", "polads", evaluate_fn=ev,
                               enqueue_fn=lambda i: "x", emit_fn=lambda *a, **k: None)
    assert prop is not None
    assert prop["ceiling"] is True
    assert "Captain-only" in prop["summary"]


def test_propose_does_not_emit_granted_event(tmp_path, monkeypatch):
    rungs = [
        T.Rung("would-like-to", None, [], None, []),
        T.Rung("ive-done", "polads", [("polads", "task_status_move")], None, []),
    ]
    monkeypatch.setattr(T, "load_ladder", lambda *a, **k: rungs)
    monkeypatch.setattr(T, "current_rung", lambda lane=None: "would-like-to")
    ev = _eval_factory({"task_status_move": ("graduated", 30)})
    emitted = []
    T.propose_next_rung("officer:cos", "polads", evaluate_fn=ev,
                        enqueue_fn=lambda i: "x",
                        emit_fn=lambda et, actor, payload: emitted.append(et))
    # propose emits trust_rung_proposed but NEVER trust_rung_granted.
    assert "trust_rung_proposed" in emitted
    assert "trust_rung_granted" not in emitted


def test_grant_rung_emits_granted_event():
    emitted = {}
    T.grant_rung("ive-done", lane="polads",
                 emit_fn=lambda et, actor, payload: emitted.update(
                     {"et": et, "actor": actor, "payload": payload}))
    assert emitted["et"] == "trust_rung_granted"
    assert emitted["payload"]["rung"] == "ive-done"
    assert emitted["payload"]["lane"] == "polads"


def test_grant_rung_rejects_unknown_rung():
    with pytest.raises(ValueError):
        T.grant_rung("god-mode", emit_fn=lambda *a, **k: None)


def test_current_rung_replays_granted_events(tmp_path, monkeypatch):
    # Use the REAL emit/replay (tmp log) to prove current_rung advances.
    from framework.learning.trust_ladder import grant_rung, current_rung
    assert current_rung("polads") == T.BASE_RUNG
    grant_rung("intend-to", lane="polads")
    assert current_rung("polads") == "intend-to"
    # a lower grant does not lower the rung.
    grant_rung("would-like-to", lane="polads")
    assert current_rung("polads") == "intend-to"
    # a different lane is unaffected.
    assert current_rung("stephie") == T.BASE_RUNG
