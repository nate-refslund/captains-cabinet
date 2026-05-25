"""Tests for the OVI computation engine."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure framework root is importable
_ROOT = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, _ROOT)

from framework.ovi.compute import (
    compute_ovi,
    compute_sample,
    normalize_value,
    determine_trend,
    _load_components,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def event_log_dir(tmp_path, monkeypatch):
    """Route event logs to a temp directory."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path / "events"


@pytest.fixture
def components_file(tmp_path):
    """Create a minimal components.yml for testing."""
    content = """version: 1
components:
  - name: throughput
    description: "Tasks completed"
    weight: 0.5
    default_range: [0, 100]

  - name: quality
    description: "Pass rate"
    weight: 0.3
    default_range: [0, 1]

  - name: cost
    description: "Spending (lower = better)"
    weight: 0.2
    direction: inverse
    default_range: [0, 1000]
"""
    path = tmp_path / "components.yml"
    path.write_text(content)
    return path


@pytest.fixture
def sample_data():
    """Sample data matching the test components file."""
    return {
        "throughput": 50,
        "quality": 0.8,
        "cost": 200,
    }


@pytest.fixture
def real_components_path():
    """Path to the actual components.yml in the framework."""
    return Path(__file__).parent.parent / "components.yml"


@pytest.fixture
def real_sample_data():
    """Sample data matching the real components.yml."""
    return {
        "task_throughput": 35,
        "outcome_progress": 0.7,
        "captain_attention_cost": 5,
        "learning_rate": 20,
        "verification_pass_rate": 0.9,
    }


# ---------------------------------------------------------------------------
# Tests: normalize_value
# ---------------------------------------------------------------------------


class TestNormalizeValue:
    def test_midpoint(self):
        """Middle of range normalizes to 0.5."""
        assert normalize_value(50, 0, 100) == 0.5

    def test_minimum(self):
        """Minimum of range normalizes to 0.0."""
        assert normalize_value(0, 0, 100) == 0.0

    def test_maximum(self):
        """Maximum of range normalizes to 1.0."""
        assert normalize_value(100, 0, 100) == 1.0

    def test_clamp_above(self):
        """Values above range are clamped to 1.0."""
        assert normalize_value(150, 0, 100) == 1.0

    def test_clamp_below(self):
        """Values below range are clamped to 0.0."""
        assert normalize_value(-10, 0, 100) == 0.0

    def test_inverse_direction(self):
        """Inverse direction: low raw value = high score."""
        # At minimum (0), inverse should give 1.0
        assert normalize_value(0, 0, 100, direction="inverse") == 1.0
        # At maximum (100), inverse should give 0.0
        assert normalize_value(100, 0, 100, direction="inverse") == 0.0
        # At midpoint, inverse should give 0.5
        assert normalize_value(50, 0, 100, direction="inverse") == 0.5

    def test_degenerate_range(self):
        """When min == max, returns 0.5."""
        assert normalize_value(5, 5, 5) == 0.5

    def test_fractional_values(self):
        """Works with fractional values."""
        result = normalize_value(0.7, 0, 1)
        assert abs(result - 0.7) < 1e-10


# ---------------------------------------------------------------------------
# Tests: determine_trend
# ---------------------------------------------------------------------------


class TestDetermineTrend:
    def test_no_previous(self):
        """First snapshot (no previous) returns flat."""
        assert determine_trend(0.7, None) == "flat"

    def test_up(self):
        """Increase above threshold is up."""
        assert determine_trend(0.75, 0.70) == "up"

    def test_down(self):
        """Decrease below threshold is down."""
        assert determine_trend(0.65, 0.70) == "down"

    def test_flat_within_threshold(self):
        """Small changes within threshold are flat."""
        assert determine_trend(0.71, 0.70) == "flat"
        assert determine_trend(0.69, 0.70) == "flat"

    def test_custom_threshold(self):
        """Custom threshold changes sensitivity."""
        # With threshold 0.1, a 0.05 change is flat
        assert determine_trend(0.75, 0.70, threshold=0.1) == "flat"
        # With threshold 0.01, a 0.05 change is up
        assert determine_trend(0.75, 0.70, threshold=0.01) == "up"


# ---------------------------------------------------------------------------
# Tests: compute_ovi
# ---------------------------------------------------------------------------


class TestComputeOvi:
    def test_basic_computation(self, components_file, sample_data):
        """compute_ovi returns a valid snapshot dict."""
        snapshot = compute_ovi(sample_data, components_path=components_file)

        assert "date" in snapshot
        assert "composite_score" in snapshot
        assert "trend_direction" in snapshot
        assert "components" in snapshot
        assert "raw_data" in snapshot

    def test_score_in_range(self, components_file, sample_data):
        """Composite score is between 0 and 1."""
        snapshot = compute_ovi(sample_data, components_path=components_file)
        assert 0.0 <= snapshot["composite_score"] <= 1.0

    def test_components_normalized(self, components_file, sample_data):
        """Each component score is between 0 and 1."""
        snapshot = compute_ovi(sample_data, components_path=components_file)
        for name, score in snapshot["components"].items():
            assert 0.0 <= score <= 1.0, f"{name} out of range: {score}"

    def test_expected_scores(self, components_file, sample_data):
        """Verify specific normalized values."""
        snapshot = compute_ovi(sample_data, components_path=components_file)

        # throughput: 50/100 = 0.5
        assert abs(snapshot["components"]["throughput"] - 0.5) < 1e-3

        # quality: 0.8/1.0 = 0.8
        assert abs(snapshot["components"]["quality"] - 0.8) < 1e-3

        # cost (inverse): 200/1000 = 0.2, inverted = 0.8
        assert abs(snapshot["components"]["cost"] - 0.8) < 1e-3

    def test_weighted_composite(self, components_file, sample_data):
        """Verify the weighted composite calculation."""
        snapshot = compute_ovi(sample_data, components_path=components_file)

        # throughput=0.5*0.5 + quality=0.8*0.3 + cost=0.8*0.2
        # = 0.25 + 0.24 + 0.16 = 0.65
        expected = (0.5 * 0.5 + 0.8 * 0.3 + 0.8 * 0.2) / (0.5 + 0.3 + 0.2)
        assert abs(snapshot["composite_score"] - round(expected, 4)) < 1e-3

    def test_trend_up(self, components_file, sample_data):
        """Trend is up when current > previous + threshold."""
        snapshot = compute_ovi(
            sample_data, previous_score=0.3, components_path=components_file
        )
        assert snapshot["trend_direction"] == "up"

    def test_trend_down(self, components_file, sample_data):
        """Trend is down when current < previous - threshold."""
        snapshot = compute_ovi(
            sample_data, previous_score=0.9, components_path=components_file
        )
        assert snapshot["trend_direction"] == "down"

    def test_trend_flat_first(self, components_file, sample_data):
        """First snapshot (no previous) is flat."""
        snapshot = compute_ovi(sample_data, components_path=components_file)
        assert snapshot["trend_direction"] == "flat"

    def test_custom_bounds(self, components_file):
        """Custom bounds override default_range."""
        data = {"throughput": 5, "quality": 0.5, "cost": 50}
        bounds = {
            "throughput": (0, 10),  # 5/10 = 0.5
            "quality": (0, 1),  # 0.5/1 = 0.5
            "cost": (0, 100),  # 50/100 inverted = 0.5
        }
        snapshot = compute_ovi(data, bounds=bounds, components_path=components_file)

        # All components at 0.5 -> composite should be 0.5
        assert abs(snapshot["composite_score"] - 0.5) < 1e-3

    def test_missing_component_raises(self, components_file):
        """Missing data for a component raises ValueError."""
        incomplete_data = {"throughput": 50, "quality": 0.8}
        with pytest.raises(ValueError, match="Missing data for OVI components"):
            compute_ovi(incomplete_data, components_path=components_file)

    def test_event_emitted(self, components_file, sample_data, event_log_dir):
        """compute_ovi emits an ovi_snapshot_computed event."""
        snapshot = compute_ovi(sample_data, components_path=components_file)

        log_files = list(event_log_dir.glob("events-*.jsonl"))
        assert len(log_files) == 1

        events = []
        with open(log_files[0]) as f:
            for line in f:
                events.append(json.loads(line))

        assert len(events) == 1
        assert events[0]["event_type"] == "ovi_snapshot_computed"
        assert events[0]["payload"]["composite_score"] == snapshot["composite_score"]
        assert events[0]["payload"]["trend_direction"] == snapshot["trend_direction"]

    def test_no_event_when_disabled(self, components_file, sample_data, event_log_dir):
        """Events can be suppressed with emit_event=False."""
        compute_ovi(sample_data, components_path=components_file, emit_event=False)

        log_files = list(event_log_dir.glob("events-*.jsonl"))
        assert len(log_files) == 0

    def test_raw_data_preserved(self, components_file, sample_data):
        """The raw input data is preserved in the snapshot."""
        snapshot = compute_ovi(sample_data, components_path=components_file)
        assert snapshot["raw_data"] == sample_data

    def test_all_zero_values(self, components_file):
        """All zeros produce valid (low) scores."""
        data = {"throughput": 0, "quality": 0, "cost": 0}
        snapshot = compute_ovi(data, components_path=components_file)
        # throughput=0, quality=0, cost=0 inverted=1.0
        # composite = (0*0.5 + 0*0.3 + 1.0*0.2) / 1.0 = 0.2
        assert 0.0 <= snapshot["composite_score"] <= 1.0

    def test_all_max_values(self, components_file):
        """All max values produce valid (high) scores."""
        data = {"throughput": 100, "quality": 1.0, "cost": 1000}
        snapshot = compute_ovi(data, components_path=components_file)
        # throughput=1.0, quality=1.0, cost=1000/1000 inverted=0.0
        # composite = (1.0*0.5 + 1.0*0.3 + 0.0*0.2) / 1.0 = 0.8
        assert 0.0 <= snapshot["composite_score"] <= 1.0


# ---------------------------------------------------------------------------
# Tests: compute_sample (CI mode)
# ---------------------------------------------------------------------------


class TestComputeSample:
    def test_produces_valid_snapshot(self):
        """Sample mode produces a complete, valid snapshot."""
        snapshot = compute_sample(seed=42)

        assert "date" in snapshot
        assert "composite_score" in snapshot
        assert "trend_direction" in snapshot
        assert "components" in snapshot
        assert 0.0 <= snapshot["composite_score"] <= 1.0

    def test_reproducible_with_seed(self):
        """Same seed produces same results."""
        s1 = compute_sample(seed=123, emit_event=False)
        s2 = compute_sample(seed=123, emit_event=False)
        assert s1["composite_score"] == s2["composite_score"]
        assert s1["components"] == s2["components"]

    def test_different_seeds_differ(self):
        """Different seeds produce different results."""
        s1 = compute_sample(seed=1, emit_event=False)
        s2 = compute_sample(seed=2, emit_event=False)
        # Very unlikely to be the same with different seeds
        assert s1["composite_score"] != s2["composite_score"]

    def test_event_emitted(self, event_log_dir):
        """Sample mode emits event by default."""
        compute_sample(seed=42)

        log_files = list(event_log_dir.glob("events-*.jsonl"))
        assert len(log_files) == 1

    def test_math_properties_verified(self):
        """The internal assertions in compute_sample pass."""
        # If math is wrong, compute_sample raises AssertionError
        for seed in range(10):
            compute_sample(seed=seed, emit_event=False)


# ---------------------------------------------------------------------------
# Tests: _load_components
# ---------------------------------------------------------------------------


class TestLoadComponents:
    def test_loads_real_file(self, real_components_path):
        """Can load the actual components.yml from the framework."""
        components = _load_components(real_components_path)
        assert len(components) == 5
        names = {c["name"] for c in components}
        assert "task_throughput" in names
        assert "outcome_progress" in names

    def test_weights_sum_to_one(self, real_components_path):
        """Component weights sum to 1.0 (sanity check on components.yml)."""
        components = _load_components(real_components_path)
        total_weight = sum(c["weight"] for c in components)
        assert abs(total_weight - 1.0) < 1e-10

    def test_file_not_found(self, tmp_path):
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            _load_components(tmp_path / "nonexistent.yml")

    def test_invalid_format(self, tmp_path):
        """File without components key raises ValueError."""
        bad_file = tmp_path / "bad.yml"
        bad_file.write_text("something: else\n")
        with pytest.raises(ValueError, match="missing 'components' key"):
            _load_components(bad_file)


# ---------------------------------------------------------------------------
# Tests: integration with real components.yml
# ---------------------------------------------------------------------------


class TestRealComponents:
    def test_compute_with_real_components(self, real_components_path, real_sample_data):
        """OVI computes correctly against the real components.yml."""
        snapshot = compute_ovi(
            real_sample_data,
            components_path=real_components_path,
            emit_event=False,
        )

        assert 0.0 <= snapshot["composite_score"] <= 1.0
        assert len(snapshot["components"]) == 5

        # Verify captain_attention_cost is inverse-normalized
        # raw=5, range=[0,20], normalized=5/20=0.25, inverted=0.75
        assert abs(snapshot["components"]["captain_attention_cost"] - 0.75) < 1e-3

    def test_sample_with_real_components(self, real_components_path):
        """Sample mode works with the real components.yml."""
        snapshot = compute_sample(
            seed=42,
            components_path=real_components_path,
            emit_event=False,
        )
        assert 0.0 <= snapshot["composite_score"] <= 1.0
        assert len(snapshot["components"]) == 5
