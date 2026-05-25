"""Work graph engine for mission/task DAG execution.

Pure Python library (stdlib + json only) for directed acyclic graph operations.
Used by the mission compiler and runtime to manage task dependencies.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class NodeStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass
class WorkNode:
    id: str
    description: str
    assigned_role: Optional[str] = None
    status: NodeStatus = NodeStatus.PENDING
    verification_criteria: list[str] = field(default_factory=list)
    verification_passed: Optional[bool] = None


class WorkGraph:
    """Directed acyclic graph of work nodes with dependency edges.

    Edges are (from_id, to_id) meaning from_id must complete before to_id starts.
    """

    def __init__(self):
        self.nodes: dict[str, WorkNode] = {}
        self.edges: list[tuple[str, str]] = []  # (from_id, to_id)
        self._deps: dict[str, set[str]] = defaultdict(set)    # to_id -> {from_ids}
        self._rdeps: dict[str, set[str]] = defaultdict(set)   # from_id -> {to_ids}

    def add_node(self, node: WorkNode) -> None:
        """Add a node to the graph. Raises ValueError on duplicate ID."""
        if node.id in self.nodes:
            raise ValueError(f"Duplicate node ID: {node.id}")
        self.nodes[node.id] = node

    def add_edge(self, from_id: str, to_id: str) -> None:
        """Add a dependency edge. from_id must complete before to_id starts.

        Raises ValueError if either node doesn't exist or edge is a self-loop.
        """
        if from_id not in self.nodes:
            raise ValueError(f"Unknown node: {from_id}")
        if to_id not in self.nodes:
            raise ValueError(f"Unknown node: {to_id}")
        if from_id == to_id:
            raise ValueError(f"Self-loop not allowed: {from_id}")
        if (from_id, to_id) not in self.edges:
            self.edges.append((from_id, to_id))
            self._deps[to_id].add(from_id)
            self._rdeps[from_id].add(to_id)

    def validate(self) -> list[str]:
        """Returns list of validation errors. Empty list means valid graph."""
        errors: list[str] = []

        if not self.nodes:
            return errors  # empty graph is valid

        # --- Cycle detection via Kahn's algorithm ---
        in_degree: dict[str, int] = {nid: 0 for nid in self.nodes}
        for _, to_id in self.edges:
            in_degree[to_id] += 1

        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        visited_count = 0
        while queue:
            nid = queue.popleft()
            visited_count += 1
            for dep_id in self._rdeps.get(nid, set()):
                in_degree[dep_id] -= 1
                if in_degree[dep_id] == 0:
                    queue.append(dep_id)

        if visited_count != len(self.nodes):
            cycle_nodes = [nid for nid, deg in in_degree.items() if deg > 0]
            errors.append(f"Cycle detected involving nodes: {sorted(cycle_nodes)}")

        # --- Reachability: all nodes reachable from at least one root ---
        roots = {nid for nid in self.nodes if not self._deps.get(nid)}
        if not roots and self.nodes:
            errors.append("No root nodes found (every node has dependencies)")
        else:
            reachable: set[str] = set()
            bfs_queue: deque[str] = deque(roots)
            while bfs_queue:
                nid = bfs_queue.popleft()
                if nid in reachable:
                    continue
                reachable.add(nid)
                for dep_id in self._rdeps.get(nid, set()):
                    if dep_id not in reachable:
                        bfs_queue.append(dep_id)
            unreachable = set(self.nodes.keys()) - reachable
            if unreachable:
                errors.append(
                    f"Unreachable nodes (not reachable from any root): "
                    f"{sorted(unreachable)}"
                )

        # --- Non-root nodes must have assigned_role ---
        for nid, node in self.nodes.items():
            if self._deps.get(nid) and node.assigned_role is None:
                errors.append(f"Non-root node '{nid}' has no assigned_role")

        return errors

    def ready_tasks(self) -> list[WorkNode]:
        """Return tasks whose dependencies are all DONE and own status is PENDING or READY."""
        ready: list[WorkNode] = []
        for nid, node in self.nodes.items():
            if node.status not in (NodeStatus.PENDING, NodeStatus.READY):
                continue
            deps = self._deps.get(nid, set())
            if all(self.nodes[d].status == NodeStatus.DONE for d in deps):
                ready.append(node)
        return ready

    def complete_task(
        self, node_id: str, verification_passed: bool = True
    ) -> list[WorkNode]:
        """Mark a task as DONE (or FAILED if verification fails).

        Returns the list of newly ready tasks after this completion.
        Raises ValueError if node doesn't exist.
        """
        if node_id not in self.nodes:
            raise ValueError(f"Unknown node: {node_id}")

        node = self.nodes[node_id]
        node.verification_passed = verification_passed

        if verification_passed:
            node.status = NodeStatus.DONE
        else:
            node.status = NodeStatus.FAILED

        # Compute newly ready tasks
        return self.ready_tasks()

    def topological_sort(self) -> list[str]:
        """Returns node IDs in dependency order (Kahn's algorithm).

        Raises ValueError if the graph contains a cycle.
        """
        in_degree: dict[str, int] = {nid: 0 for nid in self.nodes}
        for _, to_id in self.edges:
            in_degree[to_id] += 1

        queue = deque(sorted(
            nid for nid, deg in in_degree.items() if deg == 0
        ))
        result: list[str] = []

        while queue:
            nid = queue.popleft()
            result.append(nid)
            for dep_id in sorted(self._rdeps.get(nid, set())):
                in_degree[dep_id] -= 1
                if in_degree[dep_id] == 0:
                    queue.append(dep_id)

        if len(result) != len(self.nodes):
            raise ValueError("Graph contains a cycle; topological sort impossible")

        return result

    def to_json(self) -> str:
        """Serialize the graph to a JSON string."""
        data = {
            "nodes": [
                {
                    "id": n.id,
                    "description": n.description,
                    "assigned_role": n.assigned_role,
                    "status": n.status.value,
                    "verification_criteria": n.verification_criteria,
                    "verification_passed": n.verification_passed,
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {"from": f, "to": t} for f, t in self.edges
            ],
        }
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, data: str) -> "WorkGraph":
        """Deserialize a graph from a JSON string."""
        parsed = json.loads(data)
        graph = cls()

        for node_data in parsed["nodes"]:
            node = WorkNode(
                id=node_data["id"],
                description=node_data["description"],
                assigned_role=node_data.get("assigned_role"),
                status=NodeStatus(node_data["status"]),
                verification_criteria=node_data.get("verification_criteria", []),
                verification_passed=node_data.get("verification_passed"),
            )
            graph.add_node(node)

        for edge_data in parsed["edges"]:
            graph.add_edge(edge_data["from"], edge_data["to"])

        return graph
