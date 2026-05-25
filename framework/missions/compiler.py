"""Mission compiler: transforms Captain-declared outcomes into executable work graphs.

Takes outcome declarations (name, description, measurable_criteria) and compiles
them into Mission objects with a dependency-ordered WorkGraph of tasks, assigned
to roles based on capability matching.

Usage:
    from framework.missions.compiler import compile_outcome, compile_from_yaml

    outcome = {
        "id": "outcome-001",
        "name": "Launch MVP",
        "description": "Ship the minimum viable product to first users",
        "measurable_criteria": [
            "Core API endpoints deployed and passing health checks",
            "User signup flow functional end-to-end",
            "Production database seeded with schema",
        ],
        "status": "active",
    }
    mission = compile_outcome(outcome)
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from cabinet.scripts.lib.work_graph import WorkGraph, WorkNode, NodeStatus
from framework.events.emitter import emit
from framework.roles.lifecycle import list_roles, get_effective_capabilities

try:
    from yaml import safe_load as _yaml_load
except ImportError:
    import yaml as _yaml_mod
    _yaml_load = _yaml_mod.safe_load


# ---------------------------------------------------------------------------
# Capability keywords used for task-to-role matching
# ---------------------------------------------------------------------------

_CAPABILITY_KEYWORDS: dict[str, list[str]] = {
    "deploys_code": ["deploy", "production", "hosting", "ci", "cd", "infrastructure"],
    "reviews_implementations": ["review", "code review", "implementation"],
    "reviews_specs": ["spec", "specification", "requirements", "design"],
    "reviews_research": ["research", "analysis", "competitive", "market"],
    "validates_deployments": ["validate", "verification", "health check", "monitoring"],
    "logs_captain_decisions": ["decision", "governance", "approval"],
    "engineering": ["api", "endpoint", "database", "schema", "backend", "frontend", "code", "build"],
    "product": ["user", "signup", "flow", "feature", "ux", "ui", "onboarding"],
    "research": ["research", "analysis", "brief", "competitive"],
    "operations": ["process", "coordination", "schedule", "budget"],
}


def _generate_task_id(outcome_id: str, index: int) -> str:
    """Generate a deterministic task ID from outcome ID and index."""
    return f"{outcome_id}-task-{index:03d}"


def _match_role_for_task(description: str, roles: list[dict[str, Any]]) -> str | None:
    """Match a task description to the best-fitting role based on capabilities.

    Returns the role slug, or None if no match found.
    """
    description_lower = description.lower()
    best_role: str | None = None
    best_score = 0

    for role in roles:
        slug = role.get("slug", "")
        capabilities = role.get("capabilities", [])
        score = 0

        # Score based on capability keywords
        for cap in capabilities:
            keywords = _CAPABILITY_KEYWORDS.get(cap, [])
            for keyword in keywords:
                if keyword in description_lower:
                    score += 1

        # Score based on role slug appearing as a domain keyword
        slug_keywords = _CAPABILITY_KEYWORDS.get(slug, [])
        for keyword in slug_keywords:
            if keyword in description_lower:
                score += 1

        if score > best_score:
            best_score = score
            best_role = slug

    return best_role


def _infer_dependencies(criteria: list[str]) -> list[tuple[int, int]]:
    """Infer task dependencies from measurable criteria ordering.

    Default strategy: sequential (each task depends on the previous).
    Tasks mentioning "deploy" or "production" are placed last.
    Tasks mentioning "schema" or "database" are placed early.

    Returns list of (from_index, to_index) dependency pairs.
    """
    if len(criteria) <= 1:
        return []

    # Classify tasks by phase
    early_keywords = {"schema", "database", "setup", "config", "initialize"}
    late_keywords = {"deploy", "production", "launch", "release", "ship"}

    phases: dict[int, int] = {}  # index -> phase (0=early, 1=middle, 2=late)
    for i, criterion in enumerate(criteria):
        lower = criterion.lower()
        if any(kw in lower for kw in early_keywords):
            phases[i] = 0
        elif any(kw in lower for kw in late_keywords):
            phases[i] = 2
        else:
            phases[i] = 1

    # Sort by phase, preserving original order within phase
    sorted_indices = sorted(range(len(criteria)), key=lambda i: (phases[i], i))

    # Create sequential dependencies based on sorted order
    edges: list[tuple[int, int]] = []
    for pos in range(len(sorted_indices) - 1):
        from_idx = sorted_indices[pos]
        to_idx = sorted_indices[pos + 1]
        edges.append((from_idx, to_idx))

    return edges


def compile_outcome(
    outcome: dict[str, Any],
    actor: str = "compiler",
    roles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compile a single outcome into a Mission with an executable work graph.

    Args:
        outcome: dict with id, name, description, measurable_criteria, status
        actor: who is compiling (for event emission)
        roles: optional list of role dicts; if None, queries from lifecycle

    Returns:
        Mission dict with: id, outcome_id, name, status, work_graph (WorkGraph)
    """
    outcome_id = outcome["id"]
    criteria = outcome["measurable_criteria"]

    if not criteria:
        raise ValueError(f"Outcome {outcome_id} has no measurable_criteria")

    # Load available roles if not provided
    if roles is None:
        roles = list_roles(status="active")

    # Build work graph
    graph = WorkGraph()

    # Create nodes from measurable criteria
    for i, criterion in enumerate(criteria):
        task_id = _generate_task_id(outcome_id, i)
        assigned_role = _match_role_for_task(criterion, roles)

        node = WorkNode(
            id=task_id,
            description=criterion,
            assigned_role=assigned_role,
            status=NodeStatus.PENDING,
            verification_criteria=[criterion],
        )
        graph.add_node(node)

    # Add dependency edges
    dependencies = _infer_dependencies(criteria)
    for from_idx, to_idx in dependencies:
        from_id = _generate_task_id(outcome_id, from_idx)
        to_id = _generate_task_id(outcome_id, to_idx)
        graph.add_edge(from_id, to_id)

    # Validate graph
    errors = graph.validate()
    if errors:
        raise ValueError(f"Work graph validation failed: {errors}")

    # Build mission
    mission_id = f"mission-{outcome_id}-{uuid.uuid4().hex[:8]}"
    mission = {
        "id": mission_id,
        "outcome_id": outcome_id,
        "name": outcome.get("name", outcome_id),
        "status": "active",
        "work_graph": graph,
    }

    # Emit event
    emit(
        "mission_created",
        actor=actor,
        payload={
            "mission_id": mission_id,
            "outcome_id": outcome_id,
            "name": mission["name"],
            "task_count": len(criteria),
            "assigned_roles": list({
                n.assigned_role for n in graph.nodes.values() if n.assigned_role
            }),
        },
    )

    return mission


def compile_from_yaml(
    path: str | Path,
    actor: str = "compiler",
    roles: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Read an outcomes YAML file and compile all active outcomes into missions.

    The YAML file should conform to framework/schemas/outcome.schema.json:
        outcomes:
          - id: outcome-001
            name: ...
            measurable_criteria: [...]
            status: active

    Args:
        path: path to the outcomes YAML file
        actor: who is compiling (for event emission)
        roles: optional list of role dicts; if None, queries from lifecycle

    Returns:
        List of Mission dicts (one per active outcome)
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Outcomes file not found: {path}")

    with open(path) as f:
        data = _yaml_load(f)

    if not data or "outcomes" not in data:
        raise ValueError(f"Invalid outcomes file: missing 'outcomes' key in {path}")

    outcomes = data["outcomes"]
    missions: list[dict[str, Any]] = []

    for outcome in outcomes:
        # Only compile active outcomes
        status = outcome.get("status", "draft")
        if status != "active":
            continue

        mission = compile_outcome(outcome, actor=actor, roles=roles)
        missions.append(mission)

    return missions
