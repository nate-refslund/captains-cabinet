"""Eval: CRO — OVI components are weighted correctly.

Tests the **quality** of CRO's measurement framework. A failure signals
`quality_gap` — OVI weights don't sum to 1 (introduces score drift).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.measurement.role_eval_runner import RoleEval, register


def _setup():
    return {}


def _execute(ctx):
    from framework.ovi.compute import _load_components
    components = _load_components()
    total_weight = sum(c["weight"] for c in components)
    return {
        "components": components,
        "total_weight": total_weight,
        "component_count": len(components),
    }


def _verify(ctx, results):
    weights = [c["weight"] for c in results["components"]]
    names = {c["name"] for c in results["components"]}
    expected_names = {
        "task_throughput",
        "outcome_progress",
        "captain_attention_cost",
        "learning_rate",
        "verification_pass_rate",
    }
    return [
        ("five_components", results["component_count"] == 5, "quality_gap"),
        ("expected_names_present", names == expected_names, "quality_gap"),
        ("weights_sum_to_one", abs(results["total_weight"] - 1.0) < 1e-6, "quality_gap"),
        ("all_weights_positive", all(w > 0 for w in weights), "quality_gap"),
    ]


register(RoleEval(
    name="cro_ovi_components",
    role_slug="cro",
    category="quality",
    description="CRO OVI components present, named correctly, weights sum to 1.0.",
    setup=_setup,
    execute=_execute,
    verify=_verify,
))
