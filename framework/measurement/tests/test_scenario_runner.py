"""Tests for the scenario eval runner framework."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from framework.measurement.scenario_runner import (
    Scenario, register, run_scenario, run_all, _SCENARIOS,
)

_FRAMEWORK_ROOT = Path(__file__).parent.parent.parent.parent


# The framework ships NO concrete scenarios (egg row R006, 2026-07-07): the
# five-officer archetype seed content lives in presets/work/measurement/
# and is installed into framework/measurement/scenarios/ by a work-preset
# deployment. The concrete-content tests (TestOrgScenarios + the
# discovers-all-shipped-scenarios half of the dash-m guard) moved with the
# seed to presets/work/measurement/tests/test_org_scenarios.py (R050 pair).
# This file keeps the RUNNER MACHINERY tests only.


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


class TestDashMEntrypoint:
    """Regression guard for the module-identity bug.

    `python3 -m framework.measurement.scenario_runner` loads scenario_runner
    as `__main__`, while each scenario module's `register()` call imports it
    via the canonical package path. Without a shared registry module the two
    paths see different `_SCENARIOS` dicts and the `-m` runner reports zero
    scenarios — silently breaking the weekly role-eval cron driver.
    """

    def _run_dash_m(self, *extra_args: str) -> subprocess.CompletedProcess:
        """Spawn a clean subprocess so we exercise the real `-m` import path."""
        env = os.environ.copy()
        # Pytest sets CABINET_ROOT / CABINET_EVENT_LOG_DIR to tmp_path via the
        # autouse fixture; for the subprocess invocation we just need clean
        # defaults that won't write into the repo.
        env.pop("CABINET_ROOT", None)
        env.pop("CABINET_EVENT_LOG_DIR", None)
        return subprocess.run(
            [sys.executable, "-m", "framework.measurement.scenario_runner", *extra_args],
            cwd=str(_FRAMEWORK_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_dash_m_entrypoint_runs_clean_with_no_shipped_content(self):
        """The `-m` entrypoint stays healthy with zero shipped scenarios.

        Since egg row R006 the framework ships no concrete scenarios (the
        seed lives in presets/work/measurement/ until a deployment installs
        it), so the entrypoint must degrade gracefully: emit valid JSON and
        exit 0 on an empty registry. The discovers-all-shipped-scenarios
        half of the old guard moved with the seed content
        (presets/work/measurement/tests/test_org_scenarios.py); the
        module-identity half stays in-process below.
        """
        result = self._run_dash_m("--json")
        assert result.returncode == 0, (
            f"Unexpected exit code {result.returncode}. stderr={result.stderr}"
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            pytest.fail(
                f"`-m` runner did not emit valid JSON. "
                f"stdout={result.stdout!r} stderr={result.stderr!r} err={e}"
            )
        assert isinstance(payload, list)
        assert all(r["passed"] for r in payload), (
            "content-less framework run must not report failing scenarios"
        )

    def test_registry_is_shared_across_import_paths(self):
        """`__main__` and canonical imports must reference the same dict.

        Cheaper than spawning a subprocess: any divergence between the two
        module objects' `_SCENARIOS` would indicate the registry has been
        re-defined in scenario_runner.py itself instead of re-exported.
        """
        from framework.measurement import _scenario_registry
        from framework.measurement import scenario_runner

        assert scenario_runner._SCENARIOS is _scenario_registry._SCENARIOS, (
            "scenario_runner._SCENARIOS must be the same object as "
            "_scenario_registry._SCENARIOS; otherwise the -m entrypoint "
            "will load _SCENARIOS into __main__ and the canonical path "
            "into framework.measurement.scenario_runner — two dicts."
        )
