"""Tests for compute-ovi.py — OVI computation logic."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add parent dirs to path
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent.parent))  # cabinet/scripts

# Import the computation functions from compute-ovi.py
# Python doesn't allow hyphens in module names, so we use importlib
import importlib.util
import types

_ovi_path = SCRIPT_DIR.parent.parent / "compute-ovi.py"
_spec = importlib.util.spec_from_file_location(
    "compute_ovi",
    _ovi_path,
)
compute_ovi_mod = types.ModuleType("compute_ovi")
compute_ovi_mod.__file__ = str(_ovi_path)
compute_ovi_mod.__spec__ = _spec
sys.modules["compute_ovi"] = compute_ovi_mod
_spec.loader.exec_module(compute_ovi_mod)

normalize = compute_ovi_mod.normalize
compute_ovi = compute_ovi_mod.compute_ovi
determine_trend = compute_ovi_mod.determine_trend
ComponentDef = compute_ovi_mod.ComponentDef
ComponentReading = compute_ovi_mod.ComponentReading


# ── Fixtures ─────────────────────────────────────────────────────────


def _default_components() -> list[ComponentDef]:
    """Standard 5-component OVI definition matching framework defaults."""
    return [
        ComponentDef(
            name="task_throughput",
            description="Tasks completed",
            weight=0.25,
            source="database",
            default_range=[0, 50],
        ),
        ComponentDef(
            name="outcome_progress",
            description="Outcome progress fraction",
            weight=0.30,
            source="computed",
            default_range=[0, 1],
        ),
        ComponentDef(
            name="captain_attention_cost",
            description="Captain interventions",
            weight=0.20,
            source="database",
            default_range=[0, 20],
            direction="inverse",
        ),
        ComponentDef(
            name="learning_rate",
            description="Experience records",
            weight=0.15,
            source="database",
            default_range=[0, 30],
        ),
        ComponentDef(
            name="verification_pass_rate",
            description="Verification pass rate",
            weight=0.10,
            source="computed",
            default_range=[0, 1],
        ),
    ]


# ── Normalization ────────────────────────────────────────────────────


class TestNormalization:
    def test_value_at_min_is_zero(self):
        assert normalize(0, 0, 100) == 0.0

    def test_value_at_max_is_one(self):
        assert normalize(100, 0, 100) == 1.0

    def test_value_at_midpoint(self):
        assert normalize(50, 0, 100) == 0.5

    def test_value_at_quarter(self):
        assert normalize(25, 0, 100) == 0.25

    def test_clamped_below_min(self):
        assert normalize(-10, 0, 100) == 0.0

    def test_clamped_above_max(self):
        assert normalize(150, 0, 100) == 1.0

    def test_equal_min_max_returns_zero(self):
        assert normalize(50, 50, 50) == 0.0

    def test_custom_range(self):
        assert normalize(15, 10, 20) == 0.5

    def test_inverse_high_raw_low_normalized(self):
        """Inverse direction: high raw value -> low normalized."""
        result = normalize(100, 0, 100, direction="inverse")
        assert result == 0.0

    def test_inverse_low_raw_high_normalized(self):
        """Inverse direction: low raw value -> high normalized."""
        result = normalize(0, 0, 100, direction="inverse")
        assert result == 1.0

    def test_inverse_midpoint(self):
        result = normalize(50, 0, 100, direction="inverse")
        assert result == 0.5

    def test_inverse_clamped(self):
        result = normalize(150, 0, 100, direction="inverse")
        assert result == 0.0  # clamped to max, then inverted


# ── Determinism ──────────────────────────────────────────────────────


class TestDeterminism:
    def test_same_input_same_output(self):
        components = _default_components()
        values = {
            "task_throughput": 25,
            "outcome_progress": 0.5,
            "captain_attention_cost": 10,
            "learning_rate": 15,
            "verification_pass_rate": 0.8,
        }
        score1, readings1 = compute_ovi(components, values)
        score2, readings2 = compute_ovi(components, values)
        assert score1 == score2
        for r1, r2 in zip(readings1, readings2):
            assert r1.normalized_value == r2.normalized_value
            assert r1.weighted_value == r2.weighted_value

    def test_repeated_calls_stable(self):
        """Run 10 times, all produce the same score."""
        components = _default_components()
        values = {"task_throughput": 30, "outcome_progress": 0.7,
                  "captain_attention_cost": 5, "learning_rate": 20,
                  "verification_pass_rate": 0.9}
        scores = [compute_ovi(components, values)[0] for _ in range(10)]
        assert len(set(scores)) == 1


# ── Weighted Sum ─────────────────────────────────────────────────────


class TestWeightedSum:
    def test_manual_calculation(self):
        """Verify composite matches hand-calculated weighted sum."""
        components = _default_components()
        values = {
            "task_throughput": 25,        # norm = 25/50 = 0.5
            "outcome_progress": 0.6,      # norm = 0.6/1 = 0.6
            "captain_attention_cost": 5,   # norm = 5/20 = 0.25, inv = 0.75
            "learning_rate": 15,           # norm = 15/30 = 0.5
            "verification_pass_rate": 0.8, # norm = 0.8/1 = 0.8
        }
        composite, readings = compute_ovi(components, values)

        # Manual: 0.5*0.25 + 0.6*0.30 + 0.75*0.20 + 0.5*0.15 + 0.8*0.10
        #       = 0.125   + 0.18     + 0.15      + 0.075    + 0.08
        #       = 0.61
        expected = 61.0
        assert composite == expected

    def test_all_max_values(self):
        """All components at max should give 100 * sum(weights)."""
        components = _default_components()
        values = {
            "task_throughput": 50,
            "outcome_progress": 1.0,
            "captain_attention_cost": 0,  # inverse: 0 raw = best
            "learning_rate": 30,
            "verification_pass_rate": 1.0,
        }
        composite, _ = compute_ovi(components, values)
        total_weight = sum(c.weight for c in components)
        assert composite == round(total_weight * 100, 2)

    def test_all_zero_values(self):
        """All components at min (or inverse max) should give 0."""
        components = _default_components()
        values = {
            "task_throughput": 0,
            "outcome_progress": 0,
            "captain_attention_cost": 20,  # inverse: max raw = worst
            "learning_rate": 0,
            "verification_pass_rate": 0,
        }
        composite, _ = compute_ovi(components, values)
        assert composite == 0.0

    def test_single_component(self):
        """Single component at midpoint."""
        components = [ComponentDef(
            name="solo",
            description="solo",
            weight=1.0,
            source="computed",
            default_range=[0, 100],
        )]
        composite, _ = compute_ovi(components, {"solo": 50})
        assert composite == 50.0

    def test_weights_sum_to_one(self):
        """Default component weights sum to 1.0."""
        components = _default_components()
        total = sum(c.weight for c in components)
        assert abs(total - 1.0) < 1e-9

    def test_missing_component_defaults_to_zero(self):
        """If a component has no raw value, it defaults to 0."""
        components = _default_components()
        composite, _ = compute_ovi(components, {})
        # task_throughput=0 -> norm 0, outcome_progress=0 -> 0,
        # captain_attention_cost=0 -> inv 1.0 * 0.20 = 0.20,
        # learning_rate=0 -> 0, verification_pass_rate=0 -> 0
        # Total: 0.20 * 100 = 20.0
        assert composite == 20.0


# ── Trend Detection ──────────────────────────────────────────────────


class TestTrendDetection:
    def test_improving(self):
        history = [
            {"date": "2026-05-11", "score": 50.0},
            {"date": "2026-05-18", "score": 55.0},
        ]
        assert determine_trend(60.0, history) == "improving"

    def test_declining(self):
        history = [
            {"date": "2026-05-11", "score": 70.0},
            {"date": "2026-05-18", "score": 65.0},
        ]
        assert determine_trend(60.0, history) == "declining"

    def test_stable_mixed(self):
        """Current between the two previous scores -> stable."""
        history = [
            {"date": "2026-05-11", "score": 50.0},
            {"date": "2026-05-18", "score": 70.0},
        ]
        assert determine_trend(60.0, history) == "stable"

    def test_stable_equal_to_one(self):
        """Current equals one historical score -> stable."""
        history = [
            {"date": "2026-05-11", "score": 60.0},
            {"date": "2026-05-18", "score": 55.0},
        ]
        assert determine_trend(60.0, history) == "stable"

    def test_no_history(self):
        assert determine_trend(60.0, []) == "stable"

    def test_one_history_entry(self):
        history = [{"date": "2026-05-18", "score": 50.0}]
        assert determine_trend(60.0, history) == "stable"

    def test_three_increasing_uses_last_two(self):
        """Only the last 2 history entries matter."""
        history = [
            {"date": "2026-05-04", "score": 40.0},
            {"date": "2026-05-11", "score": 50.0},
            {"date": "2026-05-18", "score": 55.0},
        ]
        assert determine_trend(60.0, history) == "improving"


# ── Sample Data Mode ─────────────────────────────────────────────────


class TestSampleDataMode:
    def test_full_sample_data_computation(self, tmp_path):
        """End-to-end: write sample data, compute OVI, verify result."""
        sample = {
            "components": {
                "task_throughput": 25,
                "outcome_progress": 0.6,
                "captain_attention_cost": 5,
                "learning_rate": 15,
                "verification_pass_rate": 0.85,
            },
            "history": [
                {"date": "2026-05-11", "score": 55.0},
                {"date": "2026-05-18", "score": 58.0},
            ],
        }
        sample_file = tmp_path / "sample.json"
        sample_file.write_text(json.dumps(sample))

        components = _default_components()
        with open(sample_file) as f:
            data = json.load(f)

        raw_values = {k: float(v) for k, v in data["components"].items()}
        composite, readings = compute_ovi(components, raw_values)
        trend = determine_trend(composite, data["history"])

        assert isinstance(composite, float)
        assert 0 <= composite <= 100
        assert trend in ("improving", "declining", "stable")
        assert len(readings) == 5

    def test_three_week_trend_simulation(self, tmp_path):
        """Simulate 3 weeks of data for CI trend testing."""
        components = _default_components()

        # Week 1
        w1_values = {"task_throughput": 10, "outcome_progress": 0.3,
                     "captain_attention_cost": 15, "learning_rate": 5,
                     "verification_pass_rate": 0.5}
        w1_score, _ = compute_ovi(components, w1_values)

        # Week 2 (improving)
        w2_values = {"task_throughput": 20, "outcome_progress": 0.5,
                     "captain_attention_cost": 10, "learning_rate": 12,
                     "verification_pass_rate": 0.7}
        w2_score, _ = compute_ovi(components, w2_values)

        # Week 3 (still improving)
        w3_values = {"task_throughput": 35, "outcome_progress": 0.8,
                     "captain_attention_cost": 3, "learning_rate": 22,
                     "verification_pass_rate": 0.9}
        w3_score, _ = compute_ovi(components, w3_values)

        history = [
            {"date": "2026-05-11", "score": w1_score},
            {"date": "2026-05-18", "score": w2_score},
        ]
        trend = determine_trend(w3_score, history)

        assert w1_score < w2_score < w3_score
        assert trend == "improving"


# ── Edge Cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_components(self):
        composite, readings = compute_ovi([], {})
        assert composite == 0.0
        assert readings == []

    def test_all_zeros(self):
        """All raw values at 0 — inverse component still contributes."""
        components = _default_components()
        values = {c.name: 0.0 for c in components}
        composite, _ = compute_ovi(components, values)
        # captain_attention_cost is inverse: 0 raw -> 1.0 norm -> 0.20 weighted
        assert composite == 20.0
