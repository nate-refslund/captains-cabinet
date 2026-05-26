"""Organizational scenario eval runner.

Tests the Cabinet as a SYSTEM, not individual components.
Each scenario sets up a situation and verifies the org responds correctly.

Unlike golden evals (which test "does the machinery work"), scenario evals
test "is the organization getting better at achieving goals."

Usage:
    python3 -m framework.measurement.scenario_runner
    python3 -m framework.measurement.scenario_runner --scenario outcome_to_mission
    python3 -m framework.measurement.scenario_runner --ci  # lightweight CI mode

Module-identity note
--------------------
The registry (`_SCENARIOS`, `register`, `Scenario`, `ScenarioResult`) lives
in `_scenario_registry` so that the `-m` entrypoint (loaded as `__main__`)
and importers that go through the canonical package path share ONE module
object — and therefore one dict. Re-exporting here preserves the existing
`from framework.measurement.scenario_runner import Scenario, register`
call sites in scenarios/ and the test suite.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import time
from pathlib import Path

# Add framework root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from framework.measurement._scenario_registry import (  # noqa: E402
    Scenario,
    ScenarioResult,
    _SCENARIOS,
    is_discovered,
    mark_discovered,
    register,
)

__all__ = [
    "Scenario",
    "ScenarioResult",
    "_SCENARIOS",
    "register",
    "run_scenario",
    "run_all",
    "print_results",
]


def run_scenario(name: str) -> ScenarioResult:
    """Run a single scenario by name."""
    _discover_scenarios()
    if name not in _SCENARIOS:
        return ScenarioResult(
            name=name, passed=False, duration_ms=0,
            error=f"Unknown scenario: {name}"
        )

    scenario = _SCENARIOS[name]
    start = time.time()

    try:
        context = scenario.setup()
        results = scenario.execute(context)
        assertions = scenario.verify(context, results)

        assertion_dicts = [
            {"name": a_name, "passed": a_passed}
            for a_name, a_passed in assertions
        ]
        all_passed = all(a_passed for _, a_passed in assertions)

        return ScenarioResult(
            name=name,
            passed=all_passed,
            duration_ms=(time.time() - start) * 1000,
            assertions=assertion_dicts,
        )
    except Exception as e:
        return ScenarioResult(
            name=name,
            passed=False,
            duration_ms=(time.time() - start) * 1000,
            error=str(e),
        )


def run_all(category: str | None = None, ci_mode: bool = False) -> list[ScenarioResult]:
    """Run all registered scenarios, optionally filtered by category."""
    # Auto-discover and load scenario modules
    _discover_scenarios()

    scenarios = list(_SCENARIOS.values())
    if category:
        scenarios = [s for s in scenarios if s.category == category]
    if ci_mode:
        # In CI mode, only run scenarios marked as lightweight
        scenarios = [s for s in scenarios if not getattr(s, "heavy", False)]

    results = []
    for scenario in scenarios:
        result = run_scenario(scenario.name)
        results.append(result)

    return results


def _discover_scenarios():
    """Auto-discover scenario modules in the scenarios/ directory.

    The discovered-flag lives in `_scenario_registry` so the `-m` entry
    and the canonical-import entry can't double-walk (or, worse, walk
    against two separate flags and quietly disagree).
    """
    if is_discovered():
        return
    mark_discovered()

    scenarios_dir = Path(__file__).parent / "scenarios"
    if not scenarios_dir.exists():
        return

    for f in sorted(scenarios_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        module_name = f"framework.measurement.scenarios.{f.stem}"
        try:
            importlib.import_module(module_name)
        except (ImportError, ModuleNotFoundError):
            import importlib.util as _ilu
            spec = _ilu.spec_from_file_location(module_name, f)
            if spec and spec.loader:
                mod = _ilu.module_from_spec(spec)
                spec.loader.exec_module(mod)


def print_results(results: list[ScenarioResult]) -> int:
    """Print results and return exit code (0 = all pass, 1 = failures)."""
    print(f"\n{'=' * 60}")
    print(f"  Organizational Scenario Evals")
    print(f"{'=' * 60}\n")

    passed = 0
    failed = 0

    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"  [{status}] {result.name} ({result.duration_ms:.1f}ms)")

        if not result.passed:
            if result.error:
                print(f"        Error: {result.error}")
            for a in result.assertions:
                if not a["passed"]:
                    print(f"        FAIL: {a['name']}")

        if result.passed:
            passed += 1
        else:
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"  Total: {passed + failed}  |  Pass: {passed}  |  Fail: {failed}")
    print(f"{'=' * 60}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run organizational scenario evals")
    parser.add_argument("--scenario", help="Run a specific scenario by name")
    parser.add_argument("--category", help="Run scenarios in a category")
    parser.add_argument("--ci", action="store_true", help="CI mode (lightweight only)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    if args.scenario:
        _discover_scenarios()
        results = [run_scenario(args.scenario)]
    else:
        results = run_all(category=args.category, ci_mode=args.ci)

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
        sys.exit(0 if all(r.passed for r in results) else 1)
    else:
        sys.exit(print_results(results))
