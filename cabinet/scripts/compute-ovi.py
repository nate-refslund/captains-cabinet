#!/usr/bin/env python3
"""Compute the Outcome Value Index (OVI) from component signals.

Usage:
  python3 compute-ovi.py                    # compute from live DB
  python3 compute-ovi.py --sample-data FILE # compute from JSON sample data (for CI)
  python3 compute-ovi.py --output json      # output as JSON instead of markdown

Sample data JSON format:
{
  "components": {
    "task_throughput": 25,
    "outcome_progress": 0.6,
    "captain_attention_cost": 5,
    "learning_rate": 15,
    "verification_pass_rate": 0.85
  },
  "history": [
    {"date": "2026-05-11", "score": 62.5},
    {"date": "2026-05-18", "score": 65.0}
  ]
}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Resolve the repo root — scripts live at cabinet/scripts/compute-ovi.py
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent  # cabinet/scripts -> cabinet -> repo root

FRAMEWORK_COMPONENTS = REPO_ROOT / "framework" / "ovi" / "components.yml"
INSTANCE_OVERRIDES = REPO_ROOT / "instance" / "config" / "ovi-weights.yml"


@dataclass
class ComponentDef:
    """Definition of an OVI component from components.yml."""
    name: str
    description: str
    weight: float
    source: str
    default_range: list[float]
    direction: str = "normal"  # "normal" or "inverse"
    query: Optional[str] = None


@dataclass
class ComponentReading:
    """A single component's computed reading."""
    name: str
    raw_value: float
    normalized_value: float
    weight: float
    weighted_value: float


def load_components_yaml(path: Path) -> list[dict]:
    """Load components YAML without requiring PyYAML (simple subset parser)."""
    # We support a minimal YAML subset sufficient for components.yml.
    # For robustness, try PyYAML first, fall back to manual parsing.
    try:
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
        return data.get("components", [])
    except (ImportError, AttributeError):
        pass

    # Minimal parser for the specific YAML structure we emit
    components: list[dict] = []
    current: Optional[dict] = None

    with open(path) as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("- name:"):
                if current is not None:
                    components.append(current)
                current = {"name": stripped.split(":", 1)[1].strip().strip('"')}
            elif current is not None and ":" in stripped and not stripped.startswith("-"):
                key, val = stripped.split(":", 1)
                key = key.strip()
                val = val.strip().strip('"')
                if key == "weight":
                    current[key] = float(val)
                elif key == "default_range":
                    # Parse [0, 50] style
                    val = val.strip("[]")
                    parts = [float(x.strip()) for x in val.split(",")]
                    current[key] = parts
                elif key == "direction":
                    current[key] = val
                elif key == "query":
                    current[key] = val
                else:
                    current[key] = val

    if current is not None:
        components.append(current)

    return components


def load_component_defs() -> list[ComponentDef]:
    """Load component definitions, applying instance overrides if present."""
    raw = load_components_yaml(FRAMEWORK_COMPONENTS)

    # Apply weight overrides from instance config
    overrides: dict[str, float] = {}
    if INSTANCE_OVERRIDES.exists():
        override_raw = load_components_yaml(INSTANCE_OVERRIDES)
        for entry in override_raw:
            if "name" in entry and "weight" in entry:
                overrides[entry["name"]] = float(entry["weight"])

    defs: list[ComponentDef] = []
    for entry in raw:
        weight = overrides.get(entry["name"], float(entry.get("weight", 0)))
        defs.append(ComponentDef(
            name=entry["name"],
            description=entry.get("description", ""),
            weight=weight,
            source=entry.get("source", "computed"),
            default_range=entry.get("default_range", [0, 100]),
            direction=entry.get("direction", "normal"),
            query=entry.get("query"),
        ))

    return defs


def normalize(value: float, range_min: float, range_max: float,
              direction: str = "normal") -> float:
    """Normalize a raw value to the 0-1 range.

    For 'normal' direction: higher raw value = higher normalized.
    For 'inverse' direction: lower raw value = higher normalized.
    """
    if range_max == range_min:
        return 0.0

    clamped = max(range_min, min(range_max, value))
    normalized = (clamped - range_min) / (range_max - range_min)

    if direction == "inverse":
        normalized = 1.0 - normalized

    return normalized


def compute_ovi(
    component_defs: list[ComponentDef],
    raw_values: dict[str, float],
) -> tuple[float, list[ComponentReading]]:
    """Compute the OVI composite score from raw component values.

    Returns (composite_score_0_to_100, list_of_readings).
    """
    readings: list[ComponentReading] = []
    weighted_sum = 0.0

    for comp in component_defs:
        raw = raw_values.get(comp.name, 0.0)
        range_min, range_max = comp.default_range[0], comp.default_range[1]
        norm = normalize(raw, range_min, range_max, comp.direction)
        weighted = norm * comp.weight

        readings.append(ComponentReading(
            name=comp.name,
            raw_value=raw,
            normalized_value=round(norm, 4),
            weight=comp.weight,
            weighted_value=round(weighted, 4),
        ))
        weighted_sum += weighted

    composite = round(weighted_sum * 100, 2)
    return composite, readings


def determine_trend(
    current_score: float,
    history: list[dict],
) -> str:
    """Determine trend direction based on current score and historical data.

    'improving' if current > both previous scores
    'declining' if current < both previous scores
    'stable' otherwise
    """
    if len(history) < 2:
        return "stable"

    # Take the two most recent historical scores
    prev_scores = [h["score"] for h in history[-2:]]

    if current_score > prev_scores[0] and current_score > prev_scores[1]:
        return "improving"
    elif current_score < prev_scores[0] and current_score < prev_scores[1]:
        return "declining"
    else:
        return "stable"


def gather_raw_values_from_db(
    component_defs: list[ComponentDef],
) -> dict[str, float]:
    """Gather raw values from the live database."""
    try:
        import psycopg2
    except ImportError:
        print("Error: psycopg2 required for live DB mode. "
              "Use --sample-data for CI.", file=sys.stderr)
        sys.exit(1)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)

    values: dict[str, float] = {}
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        for comp in component_defs:
            if comp.source == "database" and comp.query:
                try:
                    cur.execute(comp.query)
                    row = cur.fetchone()
                    values[comp.name] = float(row[0]) if row and row[0] is not None else 0.0
                except Exception as e:
                    print(f"Warning: query for {comp.name} failed: {e}",
                          file=sys.stderr)
                    values[comp.name] = 0.0
            elif comp.source == "computed":
                # Computed components use fallback logic
                values[comp.name] = _compute_derived(comp.name, cur)
        cur.close()
    finally:
        conn.close()

    return values


def _compute_derived(name: str, cur) -> float:
    """Compute derived component values from DB queries."""
    if name == "outcome_progress":
        try:
            cur.execute("""
                SELECT
                  CASE WHEN count(*) = 0 THEN 0
                  ELSE count(*) FILTER (
                    WHERE m.status IN ('active', 'verifying', 'complete')
                  )::float / count(*)
                  END
                FROM outcomes o
                LEFT JOIN missions m ON m.outcome_id = o.id
                WHERE o.status = 'active'
            """)
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
        except Exception:
            return 0.0
    elif name == "verification_pass_rate":
        try:
            cur.execute("""
                SELECT
                  CASE WHEN count(*) = 0 THEN 0
                  ELSE count(*) FILTER (WHERE verification_passed = true)::float
                       / count(*)
                  END
                FROM work_graph_nodes
                WHERE status = 'done'
                  AND completed_at > NOW() - interval '7 days'
            """)
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
        except Exception:
            return 0.0
    return 0.0


def gather_history_from_db() -> list[dict]:
    """Fetch the two most recent OVI snapshots from DB."""
    try:
        import psycopg2
    except ImportError:
        return []

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return []

    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("""
            SELECT snapshot_date, composite_score
            FROM ovi_snapshots
            ORDER BY snapshot_date DESC
            LIMIT 2
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        # Return in chronological order (oldest first)
        return [
            {"date": str(row[0]), "score": float(row[1])}
            for row in reversed(rows)
        ]
    except Exception:
        return []


def format_markdown(
    composite: float,
    trend: str,
    readings: list[ComponentReading],
) -> str:
    """Format OVI results as markdown."""
    lines = [
        f"# OVI Report",
        f"",
        f"**Composite Score:** {composite}/100",
        f"**Trend:** {trend}",
        f"",
        f"## Components",
        f"",
        f"| Component | Raw | Normalized | Weight | Weighted |",
        f"|-----------|-----|------------|--------|----------|",
    ]
    for r in readings:
        lines.append(
            f"| {r.name} | {r.raw_value} | {r.normalized_value:.4f} "
            f"| {r.weight:.2f} | {r.weighted_value:.4f} |"
        )
    lines.append("")
    return "\n".join(lines)


def format_json(
    composite: float,
    trend: str,
    readings: list[ComponentReading],
) -> str:
    """Format OVI results as JSON."""
    data = {
        "composite_score": composite,
        "trend": trend,
        "components": [
            {
                "name": r.name,
                "raw_value": r.raw_value,
                "normalized_value": r.normalized_value,
                "weight": r.weight,
                "weighted_value": r.weighted_value,
            }
            for r in readings
        ],
    }
    return json.dumps(data, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Compute the Outcome Value Index")
    parser.add_argument(
        "--sample-data", type=str, default=None,
        help="Path to JSON sample data file (for CI, no DB needed)",
    )
    parser.add_argument(
        "--output", choices=["markdown", "json"], default="markdown",
        help="Output format (default: markdown)",
    )
    args = parser.parse_args()

    component_defs = load_component_defs()

    if args.sample_data:
        with open(args.sample_data) as f:
            sample = json.load(f)
        raw_values = {}
        for k, v in sample["components"].items():
            if isinstance(v, dict):
                raw_values[k] = float(v["raw"])
                comp_def = next((c for c in component_defs if c.name == k), None)
                if comp_def:
                    if "range" in v:
                        comp_def.default_range = [float(x) for x in v["range"]]
                    if "direction" in v:
                        comp_def.direction = v["direction"]
            else:
                raw_values[k] = float(v)
        if "weights" in sample:
            for k, w in sample["weights"].items():
                comp_def = next((c for c in component_defs if c.name == k), None)
                if comp_def:
                    comp_def.weight = float(w)
        history = sample.get("history", [])
    else:
        raw_values = gather_raw_values_from_db(component_defs)
        history = gather_history_from_db()

    composite, readings = compute_ovi(component_defs, raw_values)
    trend = determine_trend(composite, history)

    if args.output == "json":
        print(format_json(composite, trend, readings))
    else:
        print(format_markdown(composite, trend, readings))


if __name__ == "__main__":
    main()
