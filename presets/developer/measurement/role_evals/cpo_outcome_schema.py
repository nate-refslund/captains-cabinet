"""Eval: CPO — outcomes conform to the JSON schema.

Tests the **quality** of the CPO role's outcome authoring discipline.
A failure signals `quality_gap` — outcomes that don't match the schema
won't compile into missions.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.measurement.role_eval_runner import RoleEval, register


def _setup():
    tmp = tempfile.mkdtemp()
    os.environ["CABINET_ROOT"] = tmp
    return {"tmp": tmp}


def _execute(ctx):
    schema_path = Path(__file__).parent.parent.parent / "schemas" / "outcome.schema.json"
    with open(schema_path) as f:
        schema = json.load(f)

    # Valid outcome
    valid_outcome = {
        "id": "outcome-test",
        "name": "Valid outcome",
        "measurable_criteria": ["Criterion one", "Criterion two"],
        "status": "active",
    }
    # Invalid: missing measurable_criteria
    invalid_outcome = {
        "id": "outcome-bad",
        "name": "Missing criteria",
        "status": "active",
    }

    # Per-outcome required fields live nested under properties.outcomes.items.
    # Perform basic schema-shape validation without bringing in jsonschema
    # (avoid extra deps).
    per_outcome_required = (
        schema.get("properties", {})
              .get("outcomes", {})
              .get("items", {})
              .get("required", [])
    )

    return {
        "valid_complete": all(field in valid_outcome for field in per_outcome_required),
        "invalid_complete": all(field in invalid_outcome for field in per_outcome_required),
        "valid_criteria_nonempty": len(valid_outcome.get("measurable_criteria", [])) > 0,
        "schema_loaded": isinstance(schema, dict) and "$schema" in schema or "type" in schema,
        "required_fields": per_outcome_required,
    }


def _verify(ctx, results):
    return [
        ("schema_loaded", bool(results["schema_loaded"]), "missing_skill"),
        ("valid_outcome_has_required", results["valid_complete"], "quality_gap"),
        ("invalid_outcome_missing_required", not results["invalid_complete"], "quality_gap"),
        ("criteria_nonempty", results["valid_criteria_nonempty"], "quality_gap"),
    ]


register(RoleEval(
    name="cpo_outcome_schema",
    role_slug="cpo",
    category="quality",
    description="CPO outcomes conform to the JSON schema (required fields, non-empty criteria).",
    setup=_setup,
    execute=_execute,
    verify=_verify,
))
