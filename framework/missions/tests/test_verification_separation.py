"""Separation of duties on verification, and dependency-ordering integrity.

Both properties here were measured broken on 05871f12 and are asserted at the
level the component EXISTS to deliver, not at the level of an internal field:

  * a work item does not get to count itself independently verified;
  * a criterion carrying an explicit node_id is still reachable by the
    documented sequential-inference fallback.

NOT asserted here, deliberately: that a PARTIAL `depends_on` is refused. It
is a real hazard (an un-annotated sibling silently loses its ordering) but it
is structurally identical to the documented "these run in parallel" idiom
(`depends_on: []` alongside un-annotated siblings — see the
ghost_outcomes_yml fixture in test_supervisor.py). Refusing it would break
legitimate declarations; separating the two needs a schema-level change.

STRENGTH OF THE VERIFICATION RULE — stated plainly so no reader over-reads
these tests: the event actor is self-asserted (work-graph-complete.sh takes it
from $OFFICER_NAME) and every officer runs as the same OS user. This is
SEPARATION OF DUTIES, not authentication. It stops accidents and self-dealing.
A determined caller can still name any actor it likes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, _ROOT)

from framework.missions.compiler import (  # noqa: E402
    compile_outcome,
    _apply_status_from_events,
    _generate_task_id,
)
from framework.events.emitter import emit  # noqa: E402
from cabinet.scripts.lib.work_graph import WorkGraph, WorkNode, NodeStatus  # noqa: E402


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path / "events"


def _graph(owner="engineering", verifier=None):
    """One-node graph whose single node is owned by `owner`."""
    g = WorkGraph()
    g.add_node(WorkNode(
        id=_generate_task_id("outcome-x", 0),
        description="ship the thing",
        assigned_role=owner,
        status=NodeStatus.PENDING,
        verifier_role=verifier,
    ))
    return g


def _emit_verified(actor):
    emit("work_item_verified", actor=actor, payload={
        "task_id": _generate_task_id("outcome-x", 0),
        "outcome_id": "outcome-x",
        "status": "verified",
    })


# ---------------------------------------------------------------------------
# Separation of duties — the scoreboard is not writable by the player
# ---------------------------------------------------------------------------

class TestVerificationSeparationOfDuties:

    def test_owner_cannot_verify_its_own_work(self):
        """THE defect: the officer that owns the work marked it verified.

        Asserts the delivered property — the node is NOT credited as
        verified — rather than any internal flag name.
        """
        graph = _graph(owner="engineering")
        _emit_verified(actor="engineering")          # the owner verifying itself

        _apply_status_from_events(graph, "outcome-x")
        node = graph.nodes[_generate_task_id("outcome-x", 0)]
        assert node.verification_passed is not True, (
            "work owned by 'engineering' was credited as verified by "
            "'engineering' — the player wrote its own scoreboard"
        )

    def test_independent_verifier_still_succeeds(self):
        """No false positive: a legitimate third party still verifies."""
        graph = _graph(owner="engineering")
        _emit_verified(actor="operations")

        _apply_status_from_events(graph, "outcome-x")
        node = graph.nodes[_generate_task_id("outcome-x", 0)]
        assert node.verification_passed is True
        assert node.status == NodeStatus.DONE

    def test_actor_must_match_declared_verifier_role(self):
        """A node naming its verifier is not verifiable by anyone else."""
        graph = _graph(owner="engineering", verifier="auditor")
        _emit_verified(actor="operations")           # not the named verifier

        _apply_status_from_events(graph, "outcome-x")
        node = graph.nodes[_generate_task_id("outcome-x", 0)]
        assert node.verification_passed is not True

    def test_declared_verifier_role_succeeds(self):
        """Non-vacuity twin of the arm above: the named verifier works."""
        graph = _graph(owner="engineering", verifier="auditor")
        _emit_verified(actor="auditor")

        _apply_status_from_events(graph, "outcome-x")
        node = graph.nodes[_generate_task_id("outcome-x", 0)]
        assert node.verification_passed is True

    def test_unattributed_verification_is_not_credited(self):
        """An unattributed verification is the unaccountable case."""
        graph = _graph(owner="engineering")
        _emit_verified(actor="")

        _apply_status_from_events(graph, "outcome-x")
        node = graph.nodes[_generate_task_id("outcome-x", 0)]
        assert node.verification_passed is not True

    @pytest.mark.parametrize("actor", [
        "Engineering",           # one keystroke
        "ENGINEERING",
        "  engineering  ",       # padded
        "ｅngineering",      # fullwidth e -- NFKC folds it
        "engi​neering",     # zero-width space; str.strip does NOT remove it
    ])
    def test_near_miss_spelling_of_the_owner_is_still_refused(self, actor):
        """Case/width/zero-width variants of the owner's own name must not
        buy a verification. A raw == compare credited every one of these."""
        graph = _graph(owner="engineering")
        _emit_verified(actor=actor)

        _apply_status_from_events(graph, "outcome-x")
        assert graph.nodes[_generate_task_id("outcome-x", 0)].verification_passed is not True

    def test_unattributed_sentinel_actor_is_refused(self):
        """work-graph-complete.sh refuses "system" for --status verified; the
        overlay must agree or the two surfaces disagree about the same event."""
        graph = _graph(owner="engineering")
        _emit_verified(actor="system")

        _apply_status_from_events(graph, "outcome-x")
        assert graph.nodes[_generate_task_id("outcome-x", 0)].verification_passed is not True

    def test_owner_named_as_its_own_verifier_is_rejected_at_construction(self):
        """An unsatisfiable node (no actor is both != owner and == verifier)
        must not be constructible, or it compiles clean and is then verifiable
        by nobody, forever."""
        with pytest.raises(ValueError, match="verifier_role"):
            WorkNode(id="n", description="d", assigned_role="cos", verifier_role="Cos")

    def test_refused_verification_still_records_completion(self):
        """A refused verification is DOWNGRADED, not discarded.

        The work really was reported finished; only the independent-verification
        credit is withheld. Nothing is escalated (this is the same status a
        work_item_completed from the same owner would have produced) and nothing
        is lost.
        """
        graph = _graph(owner="engineering")
        _emit_verified(actor="engineering")

        _apply_status_from_events(graph, "outcome-x")
        node = graph.nodes[_generate_task_id("outcome-x", 0)]
        assert node.status == NodeStatus.DONE
        assert node.verification_passed is not True


# ---------------------------------------------------------------------------
# Dependency ordering — stated order is honoured or refused, never dropped
# ---------------------------------------------------------------------------

_ROLES = [{"slug": "cos", "name": "cos", "capabilities": ["contract"], "status": "active"}]


def _compile(criteria):
    return compile_outcome(
        {"id": "o1", "name": "n", "description": "d",
         "measurable_criteria": criteria, "status": "active"},
        roles=_ROLES, emit_event=False,
    )["work_graph"]


class TestDependencyOrderingIntegrity:

    def test_fully_stated_depends_on_orders_correctly(self):
        """Non-vacuity twin: a complete DAG still compiles and is ordered.

        Asserts the property that matters — you cannot start signing before
        drafting — via ready_tasks(), not via the edge list.
        """
        g = _compile([
            {"node_id": "draft", "title": "Draft the contract",
             "owner_role": "cos", "depends_on": []},
            {"node_id": "sign", "title": "Sign the contract",
             "owner_role": "cos", "depends_on": ["draft"]},
            {"node_id": "file", "title": "File the contract",
             "owner_role": "cos", "depends_on": ["sign"]},
        ])
        assert sorted(n.id for n in g.ready_tasks()) == ["draft"]

    def test_explicit_ids_resolve_in_the_inference_fallback(self):
        """With no depends_on anywhere, the documented sequential fallback
        must work on EXPLICIT node ids. It used to regenerate auto ids and
        raise 'Unknown node', making the fallback unusable with explicit ids.
        """
        g = _compile([
            {"node_id": "draft", "title": "Draft the contract", "owner_role": "cos"},
            {"node_id": "sign", "title": "Sign the contract", "owner_role": "cos"},
            {"node_id": "file", "title": "File the contract", "owner_role": "cos"},
        ])
        assert sorted(n.id for n in g.ready_tasks()) == ["draft"]
        unordered = set(g.nodes) - ({a for a, b in g.edges} | {b for a, b in g.edges})
        assert unordered == set(), f"nodes left with no ordering at all: {unordered}"
