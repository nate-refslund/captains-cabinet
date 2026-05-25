"""Tests for work_graph.py — DAG operations for mission/task execution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure lib is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from work_graph import WorkGraph, WorkNode, NodeStatus


# ── Helpers ──────────────────────────────────────────────────────────


def _linear_dag() -> WorkGraph:
    """A -> B -> C (3-node linear chain)."""
    g = WorkGraph()
    g.add_node(WorkNode(id="A", description="Task A"))
    g.add_node(WorkNode(id="B", description="Task B", assigned_role="cto"))
    g.add_node(WorkNode(id="C", description="Task C", assigned_role="cto"))
    g.add_edge("A", "B")
    g.add_edge("B", "C")
    return g


def _diamond_dag() -> WorkGraph:
    """A -> B, A -> C, B -> D, C -> D (diamond shape)."""
    g = WorkGraph()
    g.add_node(WorkNode(id="A", description="Task A"))
    g.add_node(WorkNode(id="B", description="Task B", assigned_role="cto"))
    g.add_node(WorkNode(id="C", description="Task C", assigned_role="cpo"))
    g.add_node(WorkNode(id="D", description="Task D", assigned_role="cos"))
    g.add_edge("A", "B")
    g.add_edge("A", "C")
    g.add_edge("B", "D")
    g.add_edge("C", "D")
    return g


# ── Topological Sort ─────────────────────────────────────────────────


class TestTopologicalSort:
    def test_linear_dag_order(self):
        g = _linear_dag()
        order = g.topological_sort()
        assert order == ["A", "B", "C"]

    def test_diamond_dag_a_before_bcd(self):
        g = _diamond_dag()
        order = g.topological_sort()
        assert order[0] == "A"
        assert order[-1] == "D"
        # B and C can be in either order, but both come after A and before D
        assert set(order[1:3]) == {"B", "C"}

    def test_single_node(self):
        g = WorkGraph()
        g.add_node(WorkNode(id="X", description="Solo"))
        assert g.topological_sort() == ["X"]

    def test_empty_graph(self):
        g = WorkGraph()
        assert g.topological_sort() == []

    def test_cycle_raises(self):
        g = WorkGraph()
        g.add_node(WorkNode(id="A", description="A"))
        g.add_node(WorkNode(id="B", description="B", assigned_role="cto"))
        g.add_node(WorkNode(id="C", description="C", assigned_role="cto"))
        g.add_edge("A", "B")
        g.add_edge("B", "C")
        g.add_edge("C", "A")
        with pytest.raises(ValueError, match="cycle"):
            g.topological_sort()


# ── Cycle Detection via validate() ──────────────────────────────────


class TestCycleDetection:
    def test_cycle_detected_in_validate(self):
        g = WorkGraph()
        g.add_node(WorkNode(id="A", description="A"))
        g.add_node(WorkNode(id="B", description="B", assigned_role="cto"))
        g.add_node(WorkNode(id="C", description="C", assigned_role="cto"))
        g.add_edge("A", "B")
        g.add_edge("B", "C")
        g.add_edge("C", "A")
        errors = g.validate()
        assert any("ycle" in e for e in errors)

    def test_no_cycle_valid(self):
        g = _linear_dag()
        errors = g.validate()
        assert not any("ycle" in e for e in errors)


# ── ready_tasks ──────────────────────────────────────────────────────


class TestReadyTasks:
    def test_linear_dag_initial(self):
        g = _linear_dag()
        ready = g.ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "A"

    def test_diamond_dag_initial(self):
        g = _diamond_dag()
        ready = g.ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "A"

    def test_linear_dag_after_first_complete(self):
        g = _linear_dag()
        newly_ready = g.complete_task("A")
        ids = [n.id for n in newly_ready]
        assert "B" in ids
        assert "C" not in ids  # C depends on B

    def test_diamond_after_a_complete(self):
        g = _diamond_dag()
        newly_ready = g.complete_task("A")
        ids = sorted(n.id for n in newly_ready)
        assert ids == ["B", "C"]

    def test_diamond_after_a_and_b_complete(self):
        g = _diamond_dag()
        g.complete_task("A")
        newly_ready = g.complete_task("B")
        ids = [n.id for n in newly_ready]
        # D not ready yet — C not done
        assert "D" not in ids
        assert "C" in ids  # C was already ready

    def test_diamond_d_ready_after_b_and_c(self):
        g = _diamond_dag()
        g.complete_task("A")
        g.complete_task("B")
        newly_ready = g.complete_task("C")
        ids = [n.id for n in newly_ready]
        assert "D" in ids

    def test_empty_graph(self):
        g = WorkGraph()
        assert g.ready_tasks() == []

    def test_single_node_ready(self):
        g = WorkGraph()
        g.add_node(WorkNode(id="X", description="Solo"))
        ready = g.ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "X"

    def test_all_tasks_done(self):
        g = _linear_dag()
        g.complete_task("A")
        g.complete_task("B")
        g.complete_task("C")
        assert g.ready_tasks() == []


# ── complete_task ────────────────────────────────────────────────────


class TestCompleteTask:
    def test_marks_done(self):
        g = _linear_dag()
        g.complete_task("A")
        assert g.nodes["A"].status == NodeStatus.DONE
        assert g.nodes["A"].verification_passed is True

    def test_verification_failed(self):
        g = _linear_dag()
        g.complete_task("A", verification_passed=False)
        assert g.nodes["A"].status == NodeStatus.FAILED
        assert g.nodes["A"].verification_passed is False

    def test_failed_task_blocks_dependents(self):
        g = _linear_dag()
        g.complete_task("A", verification_passed=False)
        # B depends on A which is FAILED (not DONE), so B should not be ready
        ready = g.ready_tasks()
        ids = [n.id for n in ready]
        assert "B" not in ids

    def test_unknown_node_raises(self):
        g = _linear_dag()
        with pytest.raises(ValueError, match="Unknown node"):
            g.complete_task("NONEXISTENT")


# ── JSON Round-trip ──────────────────────────────────────────────────


class TestJsonRoundTrip:
    def test_linear_dag_roundtrip(self):
        original = _linear_dag()
        json_str = original.to_json()
        restored = WorkGraph.from_json(json_str)

        assert set(restored.nodes.keys()) == set(original.nodes.keys())
        assert len(restored.edges) == len(original.edges)

        for nid in original.nodes:
            orig_node = original.nodes[nid]
            rest_node = restored.nodes[nid]
            assert rest_node.description == orig_node.description
            assert rest_node.assigned_role == orig_node.assigned_role
            assert rest_node.status == orig_node.status

    def test_diamond_dag_roundtrip(self):
        original = _diamond_dag()
        json_str = original.to_json()
        restored = WorkGraph.from_json(json_str)

        assert set(restored.nodes.keys()) == set(original.nodes.keys())
        assert len(restored.edges) == len(original.edges)

    def test_roundtrip_preserves_completed_state(self):
        g = _linear_dag()
        g.complete_task("A")
        g.nodes["B"].status = NodeStatus.IN_PROGRESS

        json_str = g.to_json()
        restored = WorkGraph.from_json(json_str)

        assert restored.nodes["A"].status == NodeStatus.DONE
        assert restored.nodes["A"].verification_passed is True
        assert restored.nodes["B"].status == NodeStatus.IN_PROGRESS

    def test_roundtrip_preserves_verification_criteria(self):
        g = WorkGraph()
        g.add_node(WorkNode(
            id="X",
            description="test",
            verification_criteria=["criterion 1", "criterion 2"],
        ))
        restored = WorkGraph.from_json(g.to_json())
        assert restored.nodes["X"].verification_criteria == [
            "criterion 1", "criterion 2"
        ]

    def test_empty_graph_roundtrip(self):
        g = WorkGraph()
        restored = WorkGraph.from_json(g.to_json())
        assert len(restored.nodes) == 0
        assert len(restored.edges) == 0

    def test_to_json_is_valid_json(self):
        g = _diamond_dag()
        parsed = json.loads(g.to_json())
        assert "nodes" in parsed
        assert "edges" in parsed


# ── Validation ───────────────────────────────────────────────────────


class TestValidation:
    def test_valid_linear_dag(self):
        g = _linear_dag()
        assert g.validate() == []

    def test_valid_diamond_dag(self):
        g = _diamond_dag()
        assert g.validate() == []

    def test_unassigned_non_root_role(self):
        g = WorkGraph()
        g.add_node(WorkNode(id="A", description="Root"))
        g.add_node(WorkNode(id="B", description="Leaf"))  # no role
        g.add_edge("A", "B")
        errors = g.validate()
        assert any("assigned_role" in e for e in errors)

    def test_root_without_role_is_ok(self):
        """Root nodes (no deps) don't need an assigned_role."""
        g = WorkGraph()
        g.add_node(WorkNode(id="A", description="Root"))  # no role, no deps
        errors = g.validate()
        assert not any("assigned_role" in e for e in errors)

    def test_empty_graph_is_valid(self):
        g = WorkGraph()
        assert g.validate() == []


# ── Edge Cases: add_node / add_edge ──────────────────────────────────


class TestEdgeCases:
    def test_duplicate_node_raises(self):
        g = WorkGraph()
        g.add_node(WorkNode(id="A", description="First"))
        with pytest.raises(ValueError, match="Duplicate"):
            g.add_node(WorkNode(id="A", description="Second"))

    def test_edge_unknown_from_raises(self):
        g = WorkGraph()
        g.add_node(WorkNode(id="B", description="B"))
        with pytest.raises(ValueError, match="Unknown node"):
            g.add_edge("A", "B")

    def test_edge_unknown_to_raises(self):
        g = WorkGraph()
        g.add_node(WorkNode(id="A", description="A"))
        with pytest.raises(ValueError, match="Unknown node"):
            g.add_edge("A", "B")

    def test_self_loop_raises(self):
        g = WorkGraph()
        g.add_node(WorkNode(id="A", description="A"))
        with pytest.raises(ValueError, match="Self-loop"):
            g.add_edge("A", "A")

    def test_duplicate_edge_is_idempotent(self):
        g = WorkGraph()
        g.add_node(WorkNode(id="A", description="A"))
        g.add_node(WorkNode(id="B", description="B", assigned_role="cto"))
        g.add_edge("A", "B")
        g.add_edge("A", "B")  # should not duplicate
        assert len(g.edges) == 1
