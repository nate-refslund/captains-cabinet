#!/usr/bin/env python3
"""Compile outcomes into missions with work-graph DAGs.

Usage:
  python3 compile-mission.py --outcomes FILE [--capabilities FILE] [--output json|db]
  python3 compile-mission.py --outcomes instance/config/outcomes.yml --output json

The compiler:
1. Reads outcomes YAML, validates against schema
2. For each active+ratified outcome, creates a mission
3. Decomposes measurable criteria into tasks
4. Assigns roles based on capabilities
5. Infers basic dependencies (verification tasks depend on implementation tasks)
6. Outputs as JSON (work graph format) or writes to DB

The decomposition is deterministic: same outcomes always produce the same
mission structure. This is a structured mapping, not AI decomposition.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Optional

# Add lib to path for work_graph import
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from work_graph import WorkGraph, WorkNode, NodeStatus


REPO_ROOT = SCRIPT_DIR.parent.parent
SCHEMA_PATH = REPO_ROOT / "framework" / "schemas" / "outcome.schema.json"
DEFAULT_CAPABILITIES = REPO_ROOT / "cabinet" / "officer-capabilities.conf"


def load_yaml(path: Path) -> dict:
    """Load YAML file."""
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except (ImportError, AttributeError):
        pass

    # Minimal YAML parser for outcomes structure
    data: dict = {"outcomes": []}
    current: Optional[dict] = None
    current_criteria: list[str] = []
    in_criteria = False

    with open(path) as f:
        for line in f:
            raw = line.rstrip("\n")
            stripped = raw.strip()

            if not stripped or stripped.startswith("#"):
                continue

            indent = len(raw) - len(raw.lstrip())

            if stripped.startswith("- id:"):
                if current is not None:
                    if current_criteria:
                        current["measurable_criteria"] = current_criteria
                    data["outcomes"].append(current)
                current = {"id": stripped.split(":", 1)[1].strip().strip('"')}
                current_criteria = []
                in_criteria = False
                continue

            if current is None:
                continue

            if stripped == "measurable_criteria:":
                in_criteria = True
                continue

            if in_criteria:
                if stripped.startswith("- "):
                    current_criteria.append(stripped[2:].strip().strip('"'))
                else:
                    in_criteria = False

            if not in_criteria and ":" in stripped and not stripped.startswith("- "):
                key, val = stripped.split(":", 1)
                key = key.strip()
                val = val.strip().strip('"')
                if key == "captain_ratified":
                    current[key] = val.lower() == "true"
                else:
                    current[key] = val

    if current is not None:
        if current_criteria:
            current["measurable_criteria"] = current_criteria
        data["outcomes"].append(current)

    return data


def validate_outcomes(data: dict) -> list[str]:
    """Validate outcomes data against schema rules.

    Returns list of validation errors. Empty means valid.
    """
    errors: list[str] = []

    if "outcomes" not in data:
        errors.append("Missing required field: 'outcomes'")
        return errors

    if not isinstance(data["outcomes"], list):
        errors.append("'outcomes' must be an array")
        return errors

    valid_statuses = {"draft", "active", "achieved", "retired"}

    for i, outcome in enumerate(data["outcomes"]):
        prefix = f"outcomes[{i}]"

        if not isinstance(outcome, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        # Required fields
        for field in ("id", "name", "measurable_criteria"):
            if field not in outcome:
                errors.append(f"{prefix}: missing required field '{field}'")

        if "measurable_criteria" in outcome:
            mc = outcome["measurable_criteria"]
            if not isinstance(mc, list) or len(mc) == 0:
                errors.append(
                    f"{prefix}.measurable_criteria: must be a non-empty array"
                )
            elif not all(isinstance(c, str) for c in mc):
                errors.append(
                    f"{prefix}.measurable_criteria: all items must be strings"
                )

        if "status" in outcome and outcome["status"] not in valid_statuses:
            errors.append(
                f"{prefix}.status: must be one of {sorted(valid_statuses)}"
            )

    return errors


def load_capabilities(path: Path) -> dict[str, list[str]]:
    """Load officer capabilities from conf file.

    Returns {capability: [officers]} mapping.
    """
    caps: dict[str, list[str]] = {}
    if not path.exists():
        return caps

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            officer, capability = line.split(":", 1)
            caps.setdefault(capability.strip(), []).append(officer.strip())

    return caps


def _deterministic_id(prefix: str, *parts: str) -> str:
    """Generate a deterministic short ID from prefix + parts."""
    content = "|".join(parts)
    digest = hashlib.sha256(content.encode()).hexdigest()[:8]
    return f"{prefix}-{digest}"


def _assign_role_for_criterion(
    criterion: str,
    capabilities: dict[str, list[str]],
) -> str:
    """Assign a role based on the criterion text and available capabilities.

    Uses keyword matching for deterministic assignment:
    - Build/CI/deploy/code keywords -> deploys_code officer
    - User/test/beta keywords -> validates_deployments officer
    - Spec/review keywords -> reviews_implementations officer
    - Default -> first available officer or 'unassigned'
    """
    criterion_lower = criterion.lower()

    # Keyword-to-capability mapping (order matters: first match wins)
    keyword_map = [
        (["build", "ci", "deploy", "code", "implement", "ship", "api",
          "database", "schema", "migrate"], "deploys_code"),
        (["test", "beta", "user", "access", "onboard", "invite",
          "launch", "release"], "validates_deployments"),
        (["spec", "review", "design", "flow", "feature", "ux",
          "retention", "engagement", "nps"], "reviews_implementations"),
        (["research", "competitor", "market", "analysis",
          "intelligence"], "reviews_research"),
    ]

    for keywords, capability in keyword_map:
        if any(kw in criterion_lower for kw in keywords):
            officers = capabilities.get(capability, [])
            if officers:
                return officers[0]

    # Fallback: pick the first officer from deploys_code, or 'unassigned'
    for cap in ["deploys_code", "validates_deployments",
                "reviews_implementations"]:
        officers = capabilities.get(cap, [])
        if officers:
            return officers[0]

    return "unassigned"


def compile_mission(
    outcome: dict,
    capabilities: dict[str, list[str]],
) -> dict:
    """Compile a single outcome into a mission with work graph.

    Returns a dict with mission metadata and a WorkGraph serialized to JSON.
    """
    outcome_id = outcome["id"]
    criteria = outcome["measurable_criteria"]

    graph = WorkGraph()

    # Create a root planning node (no deps, no assigned_role needed for root)
    root_id = _deterministic_id("plan", outcome_id)
    graph.add_node(WorkNode(
        id=root_id,
        description=f"Plan mission for: {outcome['name']}",
        assigned_role=None,
        status=NodeStatus.PENDING,
    ))

    impl_ids: list[str] = []

    for i, criterion in enumerate(criteria):
        # Implementation task
        impl_id = _deterministic_id("impl", outcome_id, str(i))
        role = _assign_role_for_criterion(criterion, capabilities)
        graph.add_node(WorkNode(
            id=impl_id,
            description=f"Implement: {criterion}",
            assigned_role=role,
            status=NodeStatus.PENDING,
            verification_criteria=[criterion],
        ))
        graph.add_edge(root_id, impl_id)  # impl depends on planning
        impl_ids.append(impl_id)

    # Verification task: depends on all implementation tasks
    verify_id = _deterministic_id("verify", outcome_id)
    verify_role = (
        capabilities.get("validates_deployments", ["unassigned"])[0]
        if capabilities.get("validates_deployments")
        else "unassigned"
    )
    graph.add_node(WorkNode(
        id=verify_id,
        description=f"Verify outcome: {outcome['name']}",
        assigned_role=verify_role,
        status=NodeStatus.PENDING,
        verification_criteria=criteria,
    ))
    for impl_id in impl_ids:
        graph.add_edge(impl_id, verify_id)

    # Validate the graph
    errors = graph.validate()
    if errors:
        raise ValueError(
            f"Work graph validation failed for {outcome_id}: {errors}"
        )

    return {
        "mission_name": f"Mission: {outcome['name']}",
        "mission_description": outcome.get("description", ""),
        "outcome_id": outcome_id,
        "status": "planning",
        "work_graph": json.loads(graph.to_json()),
    }


def compile_all_missions(
    outcomes_path: Path,
    capabilities_path: Path,
) -> list[dict]:
    """Compile all active+ratified outcomes into missions."""
    data = load_yaml(outcomes_path)

    errors = validate_outcomes(data)
    if errors:
        raise ValueError(
            f"Outcome validation errors:\n" +
            "\n".join(f"  - {e}" for e in errors)
        )

    capabilities = load_capabilities(capabilities_path)

    missions: list[dict] = []
    for outcome in data["outcomes"]:
        status = outcome.get("status", "draft")
        ratified = outcome.get("captain_ratified", False)

        if status == "active" and ratified:
            mission = compile_mission(outcome, capabilities)
            missions.append(mission)

    return missions


def write_to_db(missions: list[dict]) -> None:
    """Write compiled missions to the database."""
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("Error: psycopg2 required for DB output.", file=sys.stderr)
        sys.exit(1)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        for mission in missions:
            # Find the outcome UUID
            cur.execute(
                "SELECT id FROM outcomes WHERE outcome_id = %s",
                (mission["outcome_id"],),
            )
            row = cur.fetchone()
            if not row:
                print(
                    f"Warning: outcome {mission['outcome_id']} not in DB, "
                    f"skipping", file=sys.stderr,
                )
                continue
            outcome_uuid = row[0]

            # Insert mission
            cur.execute(
                """INSERT INTO missions (name, description, outcome_id, status)
                   VALUES (%s, %s, %s, %s)
                   RETURNING id""",
                (
                    mission["mission_name"],
                    mission["mission_description"],
                    outcome_uuid,
                    mission["status"],
                ),
            )
            mission_uuid = cur.fetchone()[0]

            # Insert work graph nodes
            wg = mission["work_graph"]
            node_uuid_map: dict[str, str] = {}

            for node in wg["nodes"]:
                cur.execute(
                    """INSERT INTO work_graph_nodes
                       (mission_id, description, assigned_role, status,
                        verification_criteria)
                       VALUES (%s, %s, %s, %s, %s)
                       RETURNING id""",
                    (
                        mission_uuid,
                        node["description"],
                        node.get("assigned_role"),
                        node["status"],
                        json.dumps(node.get("verification_criteria", [])),
                    ),
                )
                node_uuid_map[node["id"]] = str(cur.fetchone()[0])

            # Insert work graph edges
            for edge in wg["edges"]:
                cur.execute(
                    """INSERT INTO work_graph_edges (from_node, to_node)
                       VALUES (%s, %s)""",
                    (node_uuid_map[edge["from"]], node_uuid_map[edge["to"]]),
                )

        conn.commit()
        cur.close()
        print(f"Wrote {len(missions)} mission(s) to database.")
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Compile outcomes into missions with work-graph DAGs"
    )
    parser.add_argument(
        "--outcomes", type=str, required=True,
        help="Path to outcomes YAML file",
    )
    parser.add_argument(
        "--capabilities", type=str, default=None,
        help="Path to officer-capabilities.conf",
    )
    parser.add_argument(
        "--output", choices=["json", "db"], default="json",
        help="Output format (default: json to stdout)",
    )
    args = parser.parse_args()

    outcomes_path = Path(args.outcomes)
    capabilities_path = (
        Path(args.capabilities) if args.capabilities
        else DEFAULT_CAPABILITIES
    )

    missions = compile_all_missions(outcomes_path, capabilities_path)

    if not missions:
        print("No active+ratified outcomes found. Nothing to compile.",
              file=sys.stderr)
        sys.exit(0)

    if args.output == "json":
        print(json.dumps(missions, indent=2))
    elif args.output == "db":
        write_to_db(missions)


if __name__ == "__main__":
    main()
