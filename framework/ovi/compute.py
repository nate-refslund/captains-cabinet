"""OVI (Outcome Value Index) computation engine.

Computes a weekly composite score measuring organizational outcome value.
Reads component definitions from components.yml, normalizes raw values,
applies weights, and produces a composite score with trend direction.

Usage:
    from framework.ovi.compute import compute_ovi, compute_sample

    # With real data
    sample_data = {
        "task_throughput": 35,
        "outcome_progress": 0.7,
        "captain_attention_cost": 5,
        "learning_rate": 20,
        "verification_pass_rate": 0.9,
    }
    snapshot = compute_ovi(sample_data)
    print(snapshot["composite_score"])  # 0.0 - 1.0

    # Sample/CI mode
    snapshot = compute_sample()  # generates synthetic data, verifies math
"""

from __future__ import annotations

import os
import random
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.events.emitter import emit

try:
    from yaml import safe_load as _yaml_load
except ImportError:
    import yaml as _yaml_mod
    _yaml_load = _yaml_mod.safe_load


# ---------------------------------------------------------------------------
# Component loading
# ---------------------------------------------------------------------------


def _load_components(components_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load OVI component definitions from components.yml.

    Returns list of component dicts with: name, weight, direction, default_range.
    """
    if components_path is None:
        components_path = Path(__file__).parent / "components.yml"
    else:
        components_path = Path(components_path)

    if not components_path.exists():
        raise FileNotFoundError(f"OVI components file not found: {components_path}")

    with open(components_path) as f:
        data = _yaml_load(f)

    if not data or "components" not in data:
        raise ValueError(f"Invalid components file: missing 'components' key")

    return data["components"]


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalize_value(
    raw_value: float,
    range_min: float,
    range_max: float,
    direction: str = "normal",
) -> float:
    """Normalize a raw value to 0-1 range.

    Args:
        raw_value: the measured value
        range_min: minimum of the expected range
        range_max: maximum of the expected range
        direction: "normal" (higher=better) or "inverse" (lower=better)

    Returns:
        Normalized score between 0.0 and 1.0 (clamped)
    """
    if range_max == range_min:
        return 0.5  # degenerate range, return midpoint

    # Clamp to range
    clamped = max(range_min, min(raw_value, range_max))

    # Normalize to 0-1
    normalized = (clamped - range_min) / (range_max - range_min)

    # Invert if direction is inverse (lower raw value = higher score)
    if direction == "inverse":
        normalized = 1.0 - normalized

    return normalized


# ---------------------------------------------------------------------------
# Trend computation
# ---------------------------------------------------------------------------


def determine_trend(
    current_score: float,
    previous_score: float | None,
    threshold: float = 0.02,
) -> str:
    """Determine trend direction vs previous snapshot.

    Args:
        current_score: the new composite score
        previous_score: the previous composite score (None if first snapshot)
        threshold: minimum change to count as up/down (default 2%)

    Returns:
        "up", "down", or "flat"
    """
    if previous_score is None:
        return "flat"  # first snapshot has no trend

    delta = current_score - previous_score

    if delta > threshold:
        return "up"
    elif delta < -threshold:
        return "down"
    else:
        return "flat"


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def compute_ovi(
    sample_data: dict[str, float],
    previous_score: float | None = None,
    bounds: dict[str, tuple[float, float]] | None = None,
    components_path: str | Path | None = None,
    actor: str = "ovi_engine",
    emit_event: bool = True,
) -> dict[str, Any]:
    """Compute the OVI composite score from raw component values.

    Args:
        sample_data: dict mapping component names to raw values
        previous_score: previous composite score for trend computation
        bounds: optional dict mapping component names to (min, max) tuples;
                overrides default_range from components.yml
        components_path: optional path to components.yml (defaults to sibling)
        actor: actor name for event emission
        emit_event: whether to emit ovi_snapshot_computed event

    Returns:
        OVISnapshot dict with:
            date: ISO date string
            composite_score: float 0-1
            trend_direction: "up" | "down" | "flat"
            components: dict mapping component names to their normalized scores
            raw_data: the input sample_data
    """
    components = _load_components(components_path)

    # Validate: all components in the definition should have data
    component_names = {c["name"] for c in components}
    provided_names = set(sample_data.keys())

    missing = component_names - provided_names
    if missing:
        raise ValueError(
            f"Missing data for OVI components: {sorted(missing)}. "
            f"Required: {sorted(component_names)}"
        )

    # Compute normalized scores and weighted composite
    normalized_components: dict[str, float] = {}
    weighted_sum = 0.0
    total_weight = 0.0

    for component in components:
        name = component["name"]
        weight = component["weight"]
        direction = component.get("direction", "normal")
        raw_value = sample_data[name]

        # Get bounds (override or default)
        if bounds and name in bounds:
            range_min, range_max = bounds[name]
        else:
            default_range = component.get("default_range", [0, 1])
            range_min, range_max = default_range[0], default_range[1]

        # Normalize
        normalized = normalize_value(raw_value, range_min, range_max, direction)
        normalized_components[name] = normalized

        # Weighted sum
        weighted_sum += normalized * weight
        total_weight += weight

    # Composite score (normalize by total weight in case weights don't sum to 1)
    composite_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Trend
    trend_direction = determine_trend(composite_score, previous_score)

    # Build snapshot
    snapshot = {
        "date": date.today().isoformat(),
        "composite_score": round(composite_score, 4),
        "trend_direction": trend_direction,
        "components": {
            name: round(score, 4) for name, score in normalized_components.items()
        },
        "raw_data": sample_data,
    }

    # Emit event
    if emit_event:
        emit(
            "ovi_snapshot_computed",
            actor=actor,
            payload={
                "date": snapshot["date"],
                "composite_score": snapshot["composite_score"],
                "trend_direction": snapshot["trend_direction"],
                "components": snapshot["components"],
            },
        )

    return snapshot


# ---------------------------------------------------------------------------
# Sample/CI mode
# ---------------------------------------------------------------------------


def compute_sample(
    seed: int | None = None,
    components_path: str | Path | None = None,
    actor: str = "ovi_engine",
    emit_event: bool = True,
) -> dict[str, Any]:
    """Generate synthetic data and compute OVI. For CI testing.

    Generates random values within each component's default_range,
    runs the full computation, and verifies mathematical properties.

    Args:
        seed: optional random seed for reproducibility
        components_path: optional path to components.yml
        actor: actor name for event emission
        emit_event: whether to emit events

    Returns:
        OVISnapshot dict (same as compute_ovi)

    Raises:
        AssertionError: if mathematical properties don't hold
    """
    if seed is not None:
        random.seed(seed)

    components = _load_components(components_path)

    # Generate synthetic data within default ranges
    sample_data: dict[str, float] = {}
    for component in components:
        name = component["name"]
        default_range = component.get("default_range", [0, 1])
        range_min, range_max = default_range[0], default_range[1]

        # Generate a value within range
        sample_data[name] = random.uniform(range_min, range_max)

    # Compute with a synthetic previous score
    previous_score = random.uniform(0.2, 0.8)
    snapshot = compute_ovi(
        sample_data,
        previous_score=previous_score,
        components_path=components_path,
        actor=actor,
        emit_event=emit_event,
    )

    # Verify mathematical properties
    assert 0.0 <= snapshot["composite_score"] <= 1.0, (
        f"Composite score out of range: {snapshot['composite_score']}"
    )
    assert snapshot["trend_direction"] in ("up", "down", "flat"), (
        f"Invalid trend direction: {snapshot['trend_direction']}"
    )
    for name, score in snapshot["components"].items():
        assert 0.0 <= score <= 1.0, (
            f"Component {name} normalized score out of range: {score}"
        )
    assert snapshot["date"] == date.today().isoformat()

    return snapshot


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Compute OVI snapshot")
    parser.add_argument(
        "--sample-data",
        action="store_true",
        help="Generate synthetic data and verify math (CI mode)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility (with --sample-data)",
    )
    parser.add_argument(
        "--components",
        type=str,
        default=None,
        help="Path to components.yml (default: sibling file)",
    )
    args = parser.parse_args()

    if args.sample_data:
        snapshot = compute_sample(
            seed=args.seed,
            components_path=args.components,
        )
        print(json.dumps(snapshot, indent=2))
        print(f"\nOVI Score: {snapshot['composite_score']:.4f} ({snapshot['trend_direction']})")
    else:
        parser.print_help()
        sys.exit(1)
