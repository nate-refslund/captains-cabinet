"""Holder gaps: the union of contract A §3 (1-5) and B §3 (1-4).

Each arm names the SILENCE it replaces. Every one of them is red against
origin/master e34ff1b8 for the reason the invariant names — supervisor.py's
unowned branch emitted nothing, the pull path answered None with no trace,
and `framework/missions/gaps.py` did not exist — never merely because an
import failed after the fact.

Fully fixtured: a tmp cabinet root, a tmp event ledger, no network, no clock.
The concurrency arm forks real processes because the property it pins (one row
per subject under N simultaneous observers) does not exist inside one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.events.emitter import replay
from framework.learning import capability_gaps
from framework.missions import gaps as gaps_module
from framework.missions.compiler import compile_from_yaml
from framework.missions.gaps import (
    REASON_NOT_ON_ROSTER,
    REASON_NO_MATCH,
    holder_key,
    observe_holder_gaps,
)
from framework.missions.session_bridge import _outcomes_path, get_next_task


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """A throwaway ledger and root. CABINET_EVENT_LOG_DIR is pinned explicitly
    (A0.4): the subprocess arms inherit it, and an unset one gives every child
    its own ledger, which would make the concurrency arm vacuous."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CABINET_PRODUCT_SLUG", raising=False)
    monkeypatch.setenv("CABINET_WORKER_ID", "holder-under-test")
    return tmp_path


# The layout comes from the LIVE resolver, never spelled out here: a fixture
# that hardcodes it keeps passing after the resolver has moved, which is the
# wired-to-a-dead-twin shape this program keeps finding in its own tests. An
# empty roster needs no directory at all — `list_roles` answers [] for one that
# does not exist, which is the state a fresh instance is in.
def _outcomes(root: Path, body: str) -> Path:
    path = _outcomes_path(str(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


UNOWNED = """outcomes:
  - id: outcome-unowned
    name: Nobody owns this
    measurable_criteria:
      - node_id: lonely-task
        title: A thing with no owner
        depends_on: []
    status: active
    captain_ratified: true
"""

GHOST = """outcomes:
  - id: outcome-ghost
    name: A role that is not here
    measurable_criteria:
      - node_id: ghost-task
        title: A thing owned by a role that does not exist
        owner_role: ghost-role
        depends_on: []
    status: active
    captain_ratified: true
"""

TWO_UNOWNED = """outcomes:
  - id: outcome-two
    name: Two of them
    measurable_criteria:
      - node_id: task-alpha
        title: First unowned thing
        depends_on: []
      - node_id: task-beta
        title: Second unowned thing
        depends_on: []
    status: active
    captain_ratified: true
"""


def _missions(path: Path, roles=None):
    return compile_from_yaml(path, actor="test", roles=roles or [], emit_event=False)


def _recorded():
    return replay(event_types=["capability_gap_recorded"])


def _merged():
    return replay(event_types=["capability_gap_merged"])


def _resolved():
    return replay(event_types=["capability_gap_resolved"])


# ---------------------------------------------------------------------------
# A §3.1 / B §3.1-2 — one row per subject, however many passes
# ---------------------------------------------------------------------------


def test_unowned_one_gap_after_five_scans(isolated):
    """A §3 sensor 1: five passes, one row, kind skill, zero merges.

    Red before: supervisor.py's `if not node.assigned_role` branch was a bare
    `continue` and nothing was ever recorded."""
    path = _outcomes(isolated, UNOWNED)
    missions = _missions(path)

    for _ in range(5):
        observe_holder_gaps(missions, set(), actor="mission_supervisor")

    recorded = _recorded()
    assert len(recorded) == 1, recorded
    payload = recorded[0]["payload"]
    assert payload["kind"] == "skill"
    assert payload["dedup_key"] == holder_key("outcome-unowned", "lonely-task")
    assert json.loads(payload["evidence"])["reason"] == REASON_NO_MATCH
    assert _merged() == []


def test_two_subjects_never_merge_into_one(isolated):
    """The Jaccard trap: two need sentences one id apart are 0.6+ similar.

    Without the key one of these rows swallows the other and every later pass
    emits `capability_gap_merged` — the surface would then say one thing needs
    a holder when two do."""
    path = _outcomes(isolated, TWO_UNOWNED)
    missions = _missions(path)

    observe_holder_gaps(missions, set(), actor="mission_supervisor")
    observe_holder_gaps(missions, set(), actor="mission_supervisor")

    assert len(_recorded()) == 2, _recorded()
    assert _merged() == []


def test_zero_ready_unowned_tasks_records_nothing(isolated):
    """A §3.4 / B §3.4 — the degenerate end. An owned, on-roster graph is
    silent, and so is an empty mission list."""
    path = _outcomes(isolated, GHOST)
    missions = _missions(path)

    result = observe_holder_gaps(missions, {"ghost-role"}, actor="test")
    assert result == {"opened": [], "resolved": [], "unchanged": []}

    assert observe_holder_gaps([], set(), actor="test") == {
        "opened": [], "resolved": [], "unchanged": [],
    }
    assert observe_holder_gaps(None, None, actor="test") == {
        "opened": [], "resolved": [], "unchanged": [],
    }
    assert _recorded() == []


# ---------------------------------------------------------------------------
# A §3.2 — the ghost role, and self-resolution
# ---------------------------------------------------------------------------


def test_ghost_role_records_not_on_roster(isolated):
    path = _outcomes(isolated, GHOST)
    missions = _missions(path)

    observe_holder_gaps(missions, {"engineering"}, actor="mission_supervisor")

    recorded = _recorded()
    assert len(recorded) == 1, recorded
    evidence = json.loads(recorded[0]["payload"]["evidence"])
    assert evidence["reason"] == REASON_NOT_ON_ROSTER
    assert evidence["assigned_role"] == "ghost-role"
    assert evidence["task_id"] == "ghost-task"
    assert evidence["outcome_id"] == "outcome-ghost"


def test_resolves_when_the_role_appears(isolated):
    """A §3.2 — self-resolving, no Captain act."""
    path = _outcomes(isolated, GHOST)
    missions = _missions(path)

    opened = observe_holder_gaps(missions, set(), actor="test")["opened"]
    assert len(opened) == 1

    healed = observe_holder_gaps(missions, {"ghost-role"}, actor="test")
    assert healed["resolved"] == opened
    assert healed["opened"] == []

    resolved = _resolved()
    assert len(resolved) == 1
    assert resolved[0]["payload"]["gap_id"] == opened[0]
    live = [
        g for g in capability_gaps.project_gaps()
        if g["gap_id"] == opened[0]
    ]
    assert live and live[0]["status"] == capability_gaps.STATUS_RESOLVED


def test_resolves_when_the_node_finishes(isolated):
    """Terminal is the other healed end: nothing will ever hold it now."""
    path = _outcomes(isolated, UNOWNED)
    missions = _missions(path)
    opened = observe_holder_gaps(missions, set(), actor="test")["opened"]
    assert len(opened) == 1

    from cabinet.scripts.lib.work_graph import NodeStatus

    missions[0]["work_graph"].nodes["lonely-task"].status = NodeStatus.DONE
    healed = observe_holder_gaps(missions, set(), actor="test")

    assert healed["resolved"] == opened


def test_a_subject_this_pass_cannot_see_stays_open(isolated):
    """"I cannot see it" is not "it is fixed" — the row is never dropped."""
    path = _outcomes(isolated, UNOWNED)
    missions = _missions(path)
    opened = observe_holder_gaps(missions, set(), actor="test")["opened"]

    result = observe_holder_gaps([], set(), actor="test")
    assert result["resolved"] == []
    assert result["unchanged"] == opened


# ---------------------------------------------------------------------------
# A §3.3 — structural kinds are surfaced, never proposed
# ---------------------------------------------------------------------------


def test_a_holder_gap_is_never_proposed(isolated):
    """A §3 sensor 3 / the whole point of the structural kinds.

    Red before U3a: `skill` was not in VALID_KINDS, so `classify()` decided,
    and a need naming a role classified to `tool` — a proposal the Captain
    cannot approve into existence."""
    path = _outcomes(isolated, UNOWNED)
    missions = _missions(path)
    observe_holder_gaps(missions, set(), actor="test")

    routed = capability_gaps.route_open_gaps()

    assert routed["proposed"] == []
    assert routed["auto_skilling"] == []
    assert len(routed["surfaced"]) == 1
    assert replay(event_types=["capability_gap_proposed"]) == []


# ---------------------------------------------------------------------------
# A §3.5 — nothing untrusted in the row
# ---------------------------------------------------------------------------


def test_the_need_names_ids_and_nothing_else(isolated):
    """A §3.5: no `<TODO`, and no description text, in a gap.

    Structural rather than filtered: the need is built from ids, so instance
    prose — a product noun, a skeleton marker — has no path into it."""
    path = _outcomes(isolated, """outcomes:
  - id: outcome-skeleton
    name: Skeleton
    measurable_criteria:
      - node_id: skeleton-task
        title: "<TODO: describe the acme-widget rollout>"
        depends_on: []
    status: active
""")
    missions = _missions(path)
    observe_holder_gaps(missions, set(), actor="test")

    payload = _recorded()[0]["payload"]
    assert "<TODO" not in payload["need"]
    assert "acme-widget" not in payload["need"]
    assert payload["need"] == (
        "no holder on the roster for `skeleton-task` of `outcome-skeleton`"
    )


def test_a_record_failure_never_kills_the_pass(isolated, monkeypatch, capsys):
    """B §3.4: `record_gap` raising must not kill a supervisor pass."""
    path = _outcomes(isolated, TWO_UNOWNED)
    missions = _missions(path)

    calls = {"n": 0}

    def _boom(*args, **kwargs):
        calls["n"] += 1
        raise RuntimeError("the record plane is down")

    monkeypatch.setattr(gaps_module, "record_gap", _boom)
    result = observe_holder_gaps(missions, set(), actor="test")

    assert calls["n"] == 2, "the pass stopped at the first failure"
    assert result == {"opened": [], "resolved": [], "unchanged": []}
    assert "the record plane is down" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# The callers
# ---------------------------------------------------------------------------


# The two wiring sensors live in the callers' own suites, where the silence
# they replace was pinned: test_supervisor.py::test_unmatched_roles_record_a_
# holder_gap and test_session_bridge.py::test_pull_records_holder_gap. Copying
# them here would double the arm without doubling the coverage.


def test_the_projection_pull_stays_event_free(isolated):
    """`claim=False` is a projection. The observation emits, so it is gated."""
    _outcomes(isolated, UNOWNED)

    assert get_next_task(
        "engineering", cabinet_root=str(isolated), claim=False,
    ) is None
    assert list((isolated / "events").glob("events-*.jsonl")) == []


def test_the_pull_path_takes_the_locks_in_order(isolated, monkeypatch):
    """claims -> gaps -> ledger, pinned at the ONE call site that holds both.

    A lock order is only a rule until something records it. This is the place
    A3.1 names: the pull path holding the claims lock across a keyed record.
    An inversion here (gaps lock taken before the claims lock) is a deadlock
    against any claimer, and nothing else in the tree would notice."""
    import contextlib

    from framework.missions import claims as claims_module

    order = []
    real_claims_lock = claims_module.claims_lock
    real_gaps_lock = capability_gaps._gaps_lock
    real_emit = capability_gaps.emit

    @contextlib.contextmanager
    def _claims_lock():
        order.append("claims")
        with real_claims_lock():
            yield

    @contextlib.contextmanager
    def _gaps_lock():
        order.append("gaps")
        with real_gaps_lock():
            yield

    def _emit(*args, **kwargs):
        order.append("ledger")
        return real_emit(*args, **kwargs)

    monkeypatch.setattr(claims_module, "claims_lock", _claims_lock)
    monkeypatch.setattr(capability_gaps, "_gaps_lock", _gaps_lock)
    monkeypatch.setattr(capability_gaps, "emit", _emit)

    _outcomes(isolated, UNOWNED)
    assert get_next_task("engineering", cabinet_root=str(isolated)) is None

    assert order == ["claims", "gaps", "ledger"], order


# ---------------------------------------------------------------------------
# A3.1 — the concurrency arm
# ---------------------------------------------------------------------------


_OBSERVER = """
import os, sys
sys.path.insert(0, os.environ["CABINET_REPO_ROOT"])
from framework.missions.compiler import compile_from_yaml
from framework.missions.gaps import observe_holder_gaps
missions = compile_from_yaml(
    os.environ["CABINET_TEST_OUTCOMES"], actor="test", roles=[], emit_event=False,
)
observe_holder_gaps(missions, set(), actor="observer")
"""


def test_eight_concurrent_observers_of_two_subjects_record_twice(isolated):
    """A3.1: 2 tasks x 8 simultaneous observers => 2 recorded, 0 merged.

    The property only exists across processes: inside one, the second call
    reads a projection the first already wrote. Eight children start before
    any of them can finish, so every one of them replays a ledger that does
    not hold the gap yet — the exact race the keyed record's lock exists for."""
    path = _outcomes(isolated, TWO_UNOWNED)

    env = dict(os.environ)
    env["CABINET_REPO_ROOT"] = _ROOT
    env["CABINET_TEST_OUTCOMES"] = str(path)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTEST_CURRENT_TEST", None)

    children = [
        subprocess.Popen(
            [sys.executable, "-c", _OBSERVER],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
        )
        for _ in range(8)
    ]
    for child in children:
        out, err = child.communicate(timeout=180)
        assert child.returncode == 0, err.decode("utf-8", "replace")

    recorded = _recorded()
    assert len(recorded) == 2, [r["payload"]["dedup_key"] for r in recorded]
    assert _merged() == []
    assert {r["payload"]["dedup_key"] for r in recorded} == {
        holder_key("outcome-two", "task-alpha"),
        holder_key("outcome-two", "task-beta"),
    }
