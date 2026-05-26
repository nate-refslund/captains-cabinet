"""Tests for the scenario eval runner framework."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.measurement.scenario_runner import (
    Scenario, register, run_scenario, run_all, _SCENARIOS,
)


@pytest.fixture(autouse=True)
def clean_env(tmp_path):
    os.environ["CABINET_ROOT"] = str(tmp_path)
    os.environ["CABINET_EVENT_LOG_DIR"] = str(tmp_path / "events")
    os.environ.pop("DATABASE_URL", None)
    (tmp_path / "instance" / "roles" / "active").mkdir(parents=True)
    yield


@pytest.fixture
def sample_scenario():
    """A minimal passing scenario for testing the runner."""
    s = Scenario(
        name="test_sample",
        description="A sample scenario",
        category="test",
        setup=lambda: {"value": 42},
        execute=lambda ctx: {"result": ctx["value"] * 2},
        verify=lambda ctx, res: [
            ("doubled", res["result"] == 84),
            ("original_preserved", ctx["value"] == 42),
        ],
    )
    register(s)
    yield s
    _SCENARIOS.pop("test_sample", None)


@pytest.fixture
def failing_scenario():
    """A scenario that fails verification."""
    s = Scenario(
        name="test_failing",
        description="A failing scenario",
        category="test",
        setup=lambda: {},
        execute=lambda ctx: {"wrong": True},
        verify=lambda ctx, res: [
            ("should_fail", False),
            ("should_pass", True),
        ],
    )
    register(s)
    yield s
    _SCENARIOS.pop("test_failing", None)


@pytest.fixture
def error_scenario():
    """A scenario that raises an exception."""
    def _boom(ctx):
        raise RuntimeError("Something went wrong")

    s = Scenario(
        name="test_error",
        description="An erroring scenario",
        category="test",
        setup=lambda: {},
        execute=_boom,
        verify=lambda ctx, res: [],
    )
    register(s)
    yield s
    _SCENARIOS.pop("test_error", None)


class TestScenarioRunner:
    def test_passing_scenario(self, sample_scenario):
        result = run_scenario("test_sample")
        assert result.passed is True
        assert result.name == "test_sample"
        assert len(result.assertions) == 2
        assert all(a["passed"] for a in result.assertions)
        assert result.duration_ms >= 0

    def test_failing_scenario(self, failing_scenario):
        result = run_scenario("test_failing")
        assert result.passed is False
        assert any(not a["passed"] for a in result.assertions)

    def test_error_scenario(self, error_scenario):
        result = run_scenario("test_error")
        assert result.passed is False
        assert "Something went wrong" in result.error

    def test_unknown_scenario(self):
        result = run_scenario("nonexistent")
        assert result.passed is False
        assert "Unknown scenario" in result.error

    def test_run_all_by_category(self, sample_scenario, failing_scenario):
        results = run_all(category="test")
        assert len(results) == 2
        passed = [r for r in results if r.passed]
        failed = [r for r in results if not r.passed]
        assert len(passed) == 1
        assert len(failed) == 1

    def test_result_to_dict(self, sample_scenario):
        result = run_scenario("test_sample")
        d = result.to_dict()
        assert d["name"] == "test_sample"
        assert d["passed"] is True
        assert "assertions" in d
        assert "duration_ms" in d


class TestOrgScenarios:
    """Run the actual org scenarios to verify they work."""

    def test_role_adaptation_scenario(self):
        result = run_scenario("role_adaptation")
        assert result.passed, f"Failed assertions: {[a for a in result.assertions if not a['passed']]}"

    def test_role_retirement_scenario(self):
        result = run_scenario("role_retirement")
        assert result.passed, f"Failed assertions: {[a for a in result.assertions if not a['passed']]}"

    def test_policy_enforcement_scenario(self):
        result = run_scenario("policy_enforcement")
        assert result.passed, f"Failed assertions: {[a for a in result.assertions if not a['passed']]}"

    def test_outcome_to_mission_scenario(self):
        """Phase 1 baseline: outcome compiles into a valid mission."""
        result = run_scenario("outcome_to_mission")
        assert result.passed, f"Failed assertions: {[a for a in result.assertions if not a['passed']]}"

    def test_outcome_to_verified_scenario(self):
        """Phase 1 closure: outcome → completed → verified → OVI reflects activity."""
        result = run_scenario("outcome_to_verified")
        assert result.passed, f"Failed assertions: {[a for a in result.assertions if not a['passed']]}"
