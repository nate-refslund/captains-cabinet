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
        "captain_attention_well_spent": 0.8,
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

from framework.events.emitter import emit, replay

try:
    from yaml import safe_load as _yaml_load
except ImportError:
    import yaml as _yaml_mod
    _yaml_load = _yaml_mod.safe_load


# ---------------------------------------------------------------------------
# Event-sourced data gathering (Phase 1.3)
# ---------------------------------------------------------------------------
#
# The compute module is otherwise pure: callers pass in sample_data. Production
# usage (the weekly LaunchAgent) needs to derive real values from the event
# ledger. `gather_from_events()` materializes a sample_data dict from the last
# N days of events.
#
# Each OVI component has a derivation rule:
#   task_throughput       = count(work_item_completed in window)
#   outcome_progress      = unique outcomes with at least one completed task
#                            in window, divided by total outcomes touched in
#                            window (defaults to 0 if no activity)
#   captain_attention_well_spent
#                         = decisions / (decisions + bounces) in window, where
#                           decisions = the four captain_* decision events and
#                           bounces = captain_gate_bounced (an escalation the
#                           gate refused for lacking exhaustion proof — an ask
#                           that should not have been made). 0.0 when there was
#                           NO contact at all: going quiet is a failure, not a
#                           free win. (Captain ruling 2026-07-25 "attention
#                           WELL SPENT"; polarity fixed 2026-07-26 — was
#                           captain_attention_cost, direction inverse, which
#                           scored zero contact a perfect 1.00.)
#   learning_rate         = count(experience_recorded in window) / window_days
#                            — a real per-day RATE (§4.2 growth-metrics fix,
#                            2026-07-09: the raw count silently rescaled with
#                            any window change and was a volume, not a rate)
#   verification_pass_rate = count(work_item_verified) / count(work_item_completed)
#                            in window; defaults to 0 if no completions
#
# Window defaults to 7 days, matching the weekly LaunchAgent cadence and the
# DB queries in components.yml.


_DEFAULT_WINDOW_DAYS = 7

#: Captain contact that WAS a decision only he could make — the numerator of
#: attention-well-spent. Each of these is the Captain exercising authority the
#: org structurally cannot exercise for him.
_ATTENTION_EVENT_TYPES: list[str] = [
    "captain_decision_logged",
    "captain_boundary_set",
    "captain_outcome_ratified",
    "captain_goal_declared",
]

#: Captain attention the org spent BADLY: an escalation that reached the
#: attention gate and was refused for lacking exhaustion proof ("the lane tried
#: X, the Chair tried Y, this specifically needs you because Z"). It sits in the
#: denominator only, so over-asking pushes the term down.
#:
#: HONEST LIMITATION, stated rather than hidden: the escalation gate is dark by
#: default (``CABINET_ESCALATION_GATE=1``), so today this count is ~always 0 and
#: the over-ask arm rarely fires in production. It is wired to a REAL, already
#: registered event type with a real producer — not a dead twin — and it is
#: exercised by tests in both directions. The under-ask arm below needs no
#: producer at all and is live from the first computation.
_ATTENTION_MISSPENT_EVENT_TYPES: list[str] = [
    "captain_gate_bounced",
]


def attention_well_spent(decisions: int, misspent: int) -> float:
    """The share of spent Captain attention that went on decisions only he
    could make. PURE — no I/O, so the degenerate ends are directly testable.

    Captain ruling 2026-07-25: the metric is **attention WELL SPENT**, which
    makes UNDER-asking a failure exactly as much as over-asking. Both ends
    therefore read 0.0, and only genuinely well-spent attention reads 1.0:

    ==========================  ======  ====================================
    situation                   reads   why
    ==========================  ======  ====================================
    no contact at all           0.0     the org went quiet, or decided on his
                                        behalf. Silence is NOT safe. This is
                                        the case that used to read 1.00.
    no data / empty window      0.0     same reading, deliberately: an absent
                                        signal must never be scored as a good
                                        one. A quiet week is quiet whether the
                                        cause is idleness or an outage, and
                                        the composite's other four terms carry
                                        delivery separately.
    contact, none of it his     0.0     over-asking — his minutes were spent
                                        on things the org should have closed.
    contact, all of it his      1.0     every minute was a decision only he
                                        could make.
    mixed                       share   the honest fraction.
    ==========================  ======  ====================================

    Note the asymmetry is deliberate and is the whole point: the OLD term was
    ``1 - normalize(count)``, so its best score was achieved by never making
    contact. This one cannot be maximised by silence — silence is its minimum.
    """
    asks = int(decisions) + int(misspent)
    if asks <= 0:
        # THE DEGENERATE END THAT MATTERS. Was 1.00 (a perfect score for a week
        # of never speaking to the Captain); is now 0.0.
        return 0.0
    return float(decisions) / float(asks)


def _since_iso(window_days: int) -> str:
    """Return the ISO-8601 cutoff timestamp for the rolling window."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    return cutoff.isoformat()


def gather_from_events(
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> dict[str, float]:
    """Materialize OVI raw sample_data from the local event ledger.

    Reads the JSONL event log, filters to a rolling window, and computes
    raw values for each of the five OVI components. Returns a dict suitable
    for passing directly to ``compute_ovi(sample_data=...)``.

    Args:
        window_days: rolling window size in days (default: 7)

    Returns:
        dict mapping component name → raw float value.
    """
    since = _since_iso(window_days)

    completed_events = replay(event_types=["work_item_completed"], since=since)
    verified_events = replay(event_types=["work_item_verified"], since=since)
    attention_events = replay(event_types=_ATTENTION_EVENT_TYPES, since=since)
    misspent_events = replay(event_types=_ATTENTION_MISSPENT_EVENT_TYPES,
                             since=since)
    learning_events = replay(event_types=["experience_recorded"], since=since)
    mission_events = replay(event_types=["mission_created"], since=since)

    # task_throughput — number of work items completed
    task_throughput = float(len(completed_events))

    # verification_pass_rate — verified / completed; defaults to 0 with no completions
    if completed_events:
        verification_pass_rate = float(len(verified_events)) / float(len(completed_events))
    else:
        verification_pass_rate = 0.0

    # outcome_progress — fraction of touched outcomes that had at least one
    # completion in the window. "touched" = referenced by any mission_created
    # or work_item_completed event.
    touched_outcomes: set[str] = set()
    progressed_outcomes: set[str] = set()
    for ev in mission_events:
        oid = (ev.get("payload") or {}).get("outcome_id")
        if oid:
            touched_outcomes.add(oid)
    for ev in completed_events:
        oid = (ev.get("payload") or {}).get("outcome_id")
        if oid:
            touched_outcomes.add(oid)
            progressed_outcomes.add(oid)

    if touched_outcomes:
        outcome_progress = float(len(progressed_outcomes)) / float(len(touched_outcomes))
    else:
        outcome_progress = 0.0

    # captain_attention_well_spent — the SHARE of spent Captain attention that
    # went on decisions only he could make. Already normalized to [0,1] by
    # construction, direction `normal`. Reads 0.0 at BOTH failure ends
    # (never asked / asked badly); see attention_well_spent() for the table.
    captain_attention_well_spent_value = attention_well_spent(
        len(attention_events), len(misspent_events))

    # learning_rate — experience records PER DAY (window-invariant rate; the
    # raw count masqueraded as a rate and rescaled with the window — §4.2 fix)
    learning_rate = (float(len(learning_events)) / float(window_days)
                     if window_days > 0 else 0.0)

    return {
        "task_throughput": task_throughput,
        "outcome_progress": outcome_progress,
        "captain_attention_well_spent": captain_attention_well_spent_value,
        "learning_rate": learning_rate,
        "verification_pass_rate": verification_pass_rate,
    }


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
        "--from-events",
        action="store_true",
        help="Read sample_data from the local event ledger (production mode)",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=_DEFAULT_WINDOW_DAYS,
        help=f"Rolling window for --from-events (default: {_DEFAULT_WINDOW_DAYS})",
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

    # Default behaviour (when invoked with no flags, e.g. by the weekly
    # LaunchAgent): use the event ledger so production runs don't silently
    # exit-1 the way they did before Phase 1.3.
    if not args.sample_data and not args.from_events:
        args.from_events = True

    if args.sample_data:
        snapshot = compute_sample(
            seed=args.seed,
            components_path=args.components,
        )
        print(json.dumps(snapshot, indent=2))
        print(f"\nOVI Score: {snapshot['composite_score']:.4f} ({snapshot['trend_direction']})")
    elif args.from_events:
        raw = gather_from_events(window_days=args.window_days)
        snapshot = compute_ovi(
            raw,
            components_path=args.components,
        )
        print(json.dumps(snapshot, indent=2))
        print(
            f"\nOVI Score: {snapshot['composite_score']:.4f} "
            f"({snapshot['trend_direction']}) "
            f"[window={args.window_days}d]"
        )
