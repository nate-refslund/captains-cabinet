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
from framework.events.emitter import emit, replay
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


# Per-criterion rich form (Mission Compiler v2). Folded in from parent codex
# branch (cabinet/scripts/lib/org_runtime.py MISSION_NODE_FIELDS).
#
# When a `measurable_criteria` item is a dict instead of a string, the
# compiler honors these explicit fields. Required: `title` (or
# `description`). Everything else is optional with safe defaults.
_RICH_CRITERION_FIELDS: tuple[str, ...] = (
    "title",
    "description",
    "owner_role",
    "assigned_role",  # alias for owner_role for backward compat
    "acceptance_criteria",
    "evidence_required",
    "verifier_role",
    "risk_level",
    "rollback_note",
    "budget_note",
    "captain_attention_estimate",
    "depends_on",
    "node_id",  # explicit override of the auto-generated task id
)


def _normalize_criterion(item: Any) -> dict[str, Any]:
    """Convert a measurable_criteria item (string or object) to a normalized dict.

    Strings become {"title": <string>}. Objects pass through with field
    validation and defaulting. The returned dict always has at minimum a
    "title" key.
    """
    if isinstance(item, str):
        return {"title": item}
    if not isinstance(item, dict):
        raise ValueError(
            f"measurable_criteria item must be a string or object, got {type(item).__name__}"
        )

    normalized: dict[str, Any] = dict(item)
    # title can be supplied as 'title' or 'description' (parent uses 'title',
    # legacy convergence used 'description')
    title = normalized.get("title") or normalized.get("description")
    if not title or not str(title).strip():
        raise ValueError(f"measurable_criteria object missing 'title'/'description': {item}")
    normalized["title"] = str(title).strip()

    # Reject unknown keys early so typos don't get silently swallowed
    unknown = set(normalized) - set(_RICH_CRITERION_FIELDS)
    if unknown:
        raise ValueError(
            f"measurable_criteria object has unknown fields: {sorted(unknown)}. "
            f"Allowed: {sorted(_RICH_CRITERION_FIELDS)}"
        )

    # captain_attention_estimate must coerce to float
    if "captain_attention_estimate" in normalized:
        try:
            normalized["captain_attention_estimate"] = float(
                normalized["captain_attention_estimate"]
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"captain_attention_estimate must be numeric: {normalized['captain_attention_estimate']!r}"
            ) from exc

    # depends_on must be a list of strings if present
    if "depends_on" in normalized:
        deps = normalized["depends_on"] or []
        if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
            raise ValueError(
                f"depends_on must be a list of strings: {normalized['depends_on']!r}"
            )
        normalized["depends_on"] = [d.strip() for d in deps if d.strip()]

    # risk_level constrained set
    if "risk_level" in normalized:
        risk = str(normalized["risk_level"]).strip().lower()
        if risk and risk not in {"low", "medium", "high"}:
            raise ValueError(
                f"risk_level must be one of low/medium/high (or empty): {risk!r}"
            )
        normalized["risk_level"] = risk

    return normalized


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


# ---------------------------------------------------------------------------
# Event-sourced status overlay
# ---------------------------------------------------------------------------
#
# The compiler builds work graphs in memory each session. Without a status
# overlay, every freshly-compiled graph would reset to PENDING — so an officer
# that completed task-001 yesterday would see it injected again today.
#
# Solution: replay work_item_completed / work_item_failed / work_item_verified
# events from the ledger and apply them to the graph after construction. The
# event ledger is the source of truth; the in-memory graph is a projection.

_COMPLETION_EVENT_TYPES: list[str] = [
    "work_item_started",
    "work_item_completed",
    "work_item_failed",
    "work_item_verified",
]

_EVENT_TYPE_TO_STATUS: dict[str, NodeStatus] = {
    # work_item_started overlays IN_PROGRESS so an actively-worked node drops
    # out of ready_tasks() and stops being re-injected before its completion
    # is recorded. Later events (completed/failed/verified) still override it —
    # they come after `started` in the ledger and latest-event-wins.
    "work_item_started": NodeStatus.IN_PROGRESS,
    "work_item_completed": NodeStatus.DONE,
    "work_item_failed": NodeStatus.FAILED,
    "work_item_verified": NodeStatus.DONE,  # verified implies done
}


def _apply_status_from_events(graph: WorkGraph, outcome_id: str) -> int:
    """Overlay lifecycle status onto an in-memory work graph by replaying events.

    Reads work_item_started / work_item_completed / work_item_failed /
    work_item_verified events from the local event log and sets `node.status`
    for any task in this outcome's graph. `started` marks the node IN_PROGRESS
    (so it is not re-injected mid-flight); the terminal events mark it
    DONE/FAILED. Later events for the same task win (latest status sticks).

    Args:
        graph: the in-memory WorkGraph (mutated in place)
        outcome_id: only events whose payload.outcome_id matches are applied

    Returns:
        Number of nodes whose status was changed.
    """
    events = replay(event_types=_COMPLETION_EVENT_TYPES)
    if not events:
        return 0

    # Events come back in file order (chronological per day, days concatenated
    # in sorted order). Apply in order so the latest event wins.
    changed = 0
    for event in events:
        payload = event.get("payload") or {}
        if payload.get("outcome_id") != outcome_id:
            continue
        task_id = payload.get("task_id")
        if not task_id or task_id not in graph.nodes:
            continue
        new_status = _EVENT_TYPE_TO_STATUS.get(event["event_type"])
        if new_status is None:
            continue
        node = graph.nodes[task_id]
        status_changed = node.status != new_status
        if status_changed:
            node.status = new_status
            changed += 1

        # Track verification flag independently of status. A node may already
        # be DONE from a prior work_item_completed event when a subsequent
        # work_item_verified arrives; we still want to record the verification.
        if event["event_type"] == "work_item_verified":
            if node.verification_passed is not True:
                node.verification_passed = True
                if not status_changed:
                    changed += 1
        elif event["event_type"] == "work_item_failed":
            if node.verification_passed is not False:
                node.verification_passed = False
                if not status_changed:
                    changed += 1
    return changed


def compile_outcome(
    outcome: dict[str, Any],
    actor: str = "compiler",
    roles: list[dict[str, Any]] | None = None,
    emit_event: bool = True,
) -> dict[str, Any]:
    """Compile a single outcome into a Mission with an executable work graph.

    Args:
        outcome: dict with id, name, description, measurable_criteria, status
        actor: who is compiling (for event emission)
        roles: optional list of role dicts; if None, queries from lifecycle
        emit_event: when False, skip the mission_created ledger event.
            Projection/dry-run compiles (session-bridge task injection,
            supervisor --dry-run) re-derive the graph every few minutes;
            emitting on each of those floods the ledger with junk events
            that replay() then rereads on every tick. Only a compile whose
            result is acted on should emit.

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

    # Normalize criteria — each item becomes a dict with at minimum 'title'.
    # Rich form supports owner_role, evidence_required, verifier_role, etc.
    # (Mission Compiler v2 fields folded in from parent codex branch).
    normalized = [_normalize_criterion(c) for c in criteria]

    # Build work graph
    graph = WorkGraph()

    # Track explicit node_id → task_id mapping so depends_on references resolve
    explicit_id_map: dict[str, str] = {}

    # Create nodes from normalized criteria
    for i, crit in enumerate(normalized):
        task_id = crit.get("node_id") or _generate_task_id(outcome_id, i)
        if "node_id" in crit:
            explicit_id_map[crit["node_id"]] = task_id

        title = crit["title"]
        # owner_role (parent) or assigned_role (convergence) — fall back to
        # capability-keyword matching when neither explicit.
        explicit_owner = crit.get("owner_role") or crit.get("assigned_role")
        assigned_role = explicit_owner or _match_role_for_task(title, roles)

        # acceptance_criteria can be a string (parent) or list (convergence)
        ac = crit.get("acceptance_criteria")
        if ac is None:
            verification_criteria = [title]
        elif isinstance(ac, str):
            verification_criteria = [ac] if ac.strip() else [title]
        elif isinstance(ac, list):
            verification_criteria = [str(x) for x in ac if str(x).strip()]
            if not verification_criteria:
                verification_criteria = [title]
        else:
            raise ValueError(
                f"acceptance_criteria must be a string or list, got {type(ac).__name__}"
            )

        node = WorkNode(
            id=task_id,
            description=title,
            assigned_role=assigned_role,
            status=NodeStatus.PENDING,
            verification_criteria=verification_criteria,
            evidence_required=str(crit.get("evidence_required", "")),
            verifier_role=crit.get("verifier_role"),
            risk_level=str(crit.get("risk_level", "")),
            rollback_note=str(crit.get("rollback_note", "")),
            budget_note=str(crit.get("budget_note", "")),
            captain_attention_estimate=float(crit.get("captain_attention_estimate", 0.0)),
        )
        graph.add_node(node)

    # Edges: prefer explicit depends_on when present on ANY criterion, else
    # fall back to auto-inferred sequential dependencies on the string titles.
    has_explicit_deps = any("depends_on" in c for c in normalized)
    if has_explicit_deps:
        for i, crit in enumerate(normalized):
            to_id = crit.get("node_id") or _generate_task_id(outcome_id, i)
            for dep in crit.get("depends_on") or []:
                # Resolve a depends_on reference — could be an explicit node_id
                # or an auto-generated task_id from a sibling criterion.
                from_id = explicit_id_map.get(dep, dep)
                if from_id not in graph.nodes:
                    raise ValueError(
                        f"depends_on references unknown node: {dep!r} (in criterion {to_id})"
                    )
                graph.add_edge(from_id, to_id)
    else:
        titles = [c["title"] for c in normalized]
        dependencies = _infer_dependencies(titles)
        for from_idx, to_idx in dependencies:
            from_id = _generate_task_id(outcome_id, from_idx)
            to_id = _generate_task_id(outcome_id, to_idx)
            graph.add_edge(from_id, to_id)

    # Validate graph
    errors = graph.validate()
    if errors:
        raise ValueError(f"Work graph validation failed: {errors}")

    # Apply event-sourced status overlay so subsequent sessions don't re-inject
    # completed tasks. This is what closes Phase 1.1's mission loop.
    _apply_status_from_events(graph, outcome_id)

    # Build mission
    mission_id = f"mission-{outcome_id}-{uuid.uuid4().hex[:8]}"
    captain_attention_total = sum(
        float(n.captain_attention_estimate) for n in graph.nodes.values()
    )
    mission = {
        "id": mission_id,
        "outcome_id": outcome_id,
        "name": outcome.get("name", outcome_id),
        "status": "planning",
        "work_graph": graph,
        "captain_attention_estimate": captain_attention_total,
    }

    # Emit event — includes the v2 task-level fields so downstream consumers
    # (OVI compute, Captain dashboards, outbox relay) can see the richer plan
    # without re-loading the graph from disk. Skipped for projection/dry-run
    # compiles (emit_event=False) so they never spam the ledger.
    if emit_event:
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
                "verifier_roles": list({
                    n.verifier_role for n in graph.nodes.values() if n.verifier_role
                }),
                "risk_levels": [n.risk_level for n in graph.nodes.values() if n.risk_level],
                "captain_attention_estimate": captain_attention_total,
            },
        )

    return mission


def compile_from_yaml(
    path: str | Path,
    actor: str = "compiler",
    roles: list[dict[str, Any]] | None = None,
    emit_event: bool = True,
) -> list[dict[str, Any]]:
    """Read an outcomes YAML file and compile all active outcomes into missions.

    The YAML file should conform to framework/schemas/outcome.schema.json:
        deployment: my-cabinet-id   # optional gate (see below)
        outcomes:
          - id: outcome-001
            name: ...
            measurable_criteria: [...]
            status: active

    Args:
        path: path to the outcomes YAML file
        actor: who is compiling (for event emission)
        roles: optional list of role dicts; if None, queries from lifecycle
        emit_event: when False, suppress mission_created ledger events for
            every compiled outcome (projection/dry-run compiles — see
            compile_outcome)

    Returns:
        List of Mission dicts (one per active outcome). Empty (with one
        stderr warning, no exception) when the file pins a `deployment`
        that does not match this cabinet's CABINET_ID env (default "main").
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Outcomes file not found: {path}")

    with open(path) as f:
        data = _yaml_load(f)

    if not data or "outcomes" not in data:
        raise ValueError(f"Invalid outcomes file: missing 'outcomes' key in {path}")

    # Deployment gate (cross-deployment leak guard). A live outcomes file is
    # git-tracked, so any other deployment pulling the branch would compile
    # this machine's missions and double-execute its tasks. When the file
    # pins a `deployment`, only the cabinet whose CABINET_ID matches it
    # compiles; everyone else skips the whole file with one warning.
    # Absent field = compile everywhere (back-compat).
    deployment = data.get("deployment")
    if deployment is not None:
        raw_cabinet_id = os.environ.get("CABINET_ID")
        cabinet_id = raw_cabinet_id if raw_cabinet_id is not None else "main"
        if str(deployment) != cabinet_id:
            # LOUD WARN, not a silent skip. Returning [] here reads to a
            # caller as "no work" — but the real cause is a misconfigured
            # CABINET_ID (a mis-sourced cron pointed at the wrong deployment's
            # outcomes). Name both values (expected vs actual) so the operator
            # can fix it, and flag the unset-env case distinctly. Uses the
            # module's stderr WARN convention (cf. supervisor.py's
            # "mission-supervisor: WARN ...").
            actual = (
                f"'{raw_cabinet_id}'"
                if raw_cabinet_id is not None
                else "unset (defaulting to 'main')"
            )
            print(
                f"mission-compiler: WARN skipping {path}: file is pinned to "
                f"deployment '{deployment}' but this cabinet's CABINET_ID is "
                f"{actual} — expected '{deployment}', got '{cabinet_id}'; "
                f"refusing to compile another deployment's outcomes (set "
                f"CABINET_ID='{deployment}' if this IS that deployment)",
                file=sys.stderr,
            )
            return []

    outcomes = data["outcomes"]
    missions: list[dict[str, Any]] = []

    for outcome in outcomes:
        # Only compile active outcomes
        status = outcome.get("status", "draft")
        if status != "active":
            continue

        mission = compile_outcome(outcome, actor=actor, roles=roles,
                                  emit_event=emit_event)
        missions.append(mission)

    return missions
