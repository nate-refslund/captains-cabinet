"""Work graph engine for mission/task DAG execution.

Pure Python library (stdlib + json only) for directed acyclic graph operations.
Used by the mission compiler and runtime to manage task dependencies.
"""

from __future__ import annotations

import json
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


# work-graph-complete.sh's fallback actor when no officer is named. Kept in
# lockstep with that script's refusal for --status verified.
UNATTRIBUTED_ACTOR = "system"


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
    # Mission Compiler v2 fields — folded in from parent codex branch
    # (cabinet/scripts/lib/org_runtime.py MISSION_NODE_FIELDS). Optional with
    # safe defaults so simple `measurable_criteria: [string]` outcomes still
    # compile unchanged.
    evidence_required: str = ""
    verifier_role: Optional[str] = None
    risk_level: str = ""  # "" | "low" | "medium" | "high"
    rollback_note: str = ""
    budget_note: str = ""
    captain_attention_estimate: float = 0.0

    def __post_init__(self) -> None:
        # A node naming its own owner as its verifier is UNSATISFIABLE: no
        # actor can be both != owner and == verifier, so it would compile
        # clean and then be permanently unverifiable. Reject it at
        # construction, which covers every path (compiler, from_json, direct).
        # Only fires when BOTH are non-empty, so legacy nodes that simply have
        # no verifier_role keep loading.
        if self.verifier_role and self.assigned_role and (
            normalize_role_name(self.verifier_role) == normalize_role_name(self.assigned_role)
        ):
            raise ValueError(
                f"node {self.id!r} names its owner ({self.assigned_role}) as its own "
                "verifier_role; no actor could ever verify it"
            )


def normalize_role_name(value) -> str:
    """Fold a role name for comparison: NFKC, strip control/format chars, casefold.

    Without this a one-keystroke difference (`Engineering` vs `engineering`)
    read as two different roles and a self-verification was credited. NFKC also
    folds fullwidth and other compatibility look-alikes; the control/format
    filter removes zero-width characters, which `str.strip()` does not.

    This defeats near-miss spellings ONLY. It does nothing against a caller who
    deliberately types a different, real role name — see
    verification_is_independent for what that check is and is not worth.
    """
    text = unicodedata.normalize("NFKC", str(value or ""))
    return "".join(c for c in text if not unicodedata.category(c).startswith("C")).strip().casefold()


def verification_is_independent(node: "WorkNode", actor) -> bool:
    """True when `actor` may credit `node` with an independent verification.

    Applies the rule the work-graph-complete skill has always stated in prose
    but never enforced: "validators verify, executors complete."

    WHAT THIS IS WORTH — do not overstate it. The actor is self-asserted by the
    caller and every officer runs as the same OS user, so anyone able to emit an
    event can name any actor. It stops the DEFAULTED, UNATTRIBUTED and
    ACCIDENTAL cases — the routine ways work ends up marking its own homework
    verified. It does NOT stop an officer who deliberately types another role's
    name, and it is NOT authentication.

    Three refusals: a blank actor (an unattributed verification is exactly the
    unaccountable case); an actor equal to the node's own owner; an actor that
    is not the node's declared verifier_role when it has one. A node with no
    verifier_role keeps the weaker owner-only rule, so graphs written before
    that field was populated stay loadable.

    KNOWN GAP: a node with no assigned_role AND no verifier_role has no basis
    for comparison, so any non-blank actor passes. _match_role_for_task can
    leave assigned_role None when no capability keyword matches.
    """
    who = normalize_role_name(actor)
    owner = normalize_role_name(node.assigned_role)
    verifier = normalize_role_name(node.verifier_role)
    # "system" is work-graph-complete.sh's unattributed fallback; that gate
    # refuses it for --status verified, so the overlay must refuse it too or
    # the two surfaces disagree about the same event.
    if not who or who == UNATTRIBUTED_ACTOR:
        return False
    return who != owner and (not verifier or who == verifier)


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
                    # Mission Compiler v2 fields. These MUST round-trip:
                    # verifier_role names who is allowed to verify this node,
                    # so dropping it here silently erased the separation of
                    # duties the runtime relies on (a serialized graph came
                    # back with verifier_role=None and every field defaulted).
                    "evidence_required": n.evidence_required,
                    "verifier_role": n.verifier_role,
                    "risk_level": n.risk_level,
                    "rollback_note": n.rollback_note,
                    "budget_note": n.budget_note,
                    "captain_attention_estimate": n.captain_attention_estimate,
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
                # Mission Compiler v2 fields — read back with the same
                # defaults the dataclass declares, so a payload written
                # before these keys existed still loads unchanged.
                evidence_required=node_data.get("evidence_required") or "",
                verifier_role=node_data.get("verifier_role"),
                risk_level=node_data.get("risk_level") or "",
                rollback_note=node_data.get("rollback_note") or "",
                budget_note=node_data.get("budget_note") or "",
                captain_attention_estimate=float(
                    node_data.get("captain_attention_estimate") or 0.0
                ),
            )
            graph.add_node(node)

        for edge_data in parsed["edges"]:
            graph.add_edge(edge_data["from"], edge_data["to"])

        return graph
