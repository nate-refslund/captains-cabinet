"""Role eval runner — runs per-role scenario evals, emits eval events, tracks failures.

Phase 2 of the convergence plan. Unlike `scenario_runner.py` (which tests the
**org as a system**), this module tests **individual roles**:

  - Did the role's logic for X produce the right output?
  - Did the role handle edge case Y correctly?
  - Does the role's charter still cover what it's being asked to do?

Each eval is a small Python module in `framework/measurement/role_evals/` with
`name`, `role_slug`, `category`, and setup/execute/verify callables — the same
shape as Scenario but with a role binding.

Role binding is ROSTER-DRIVEN (R8 retarget, 2026-07-04): the slug an eval
declares is resolved against the live roster from
`cabinet/officer-capabilities.conf` at registration time
(`_eval_registry.resolve_role_slug`), so evals authored for the retired
work-preset roster (cto/cpo/cro/coo) attribute their events to a role the
evolution loop can actually load and amend (this deployment: `cos`). The
declared slug is preserved on `RoleEval.declared_role_slug`.

Events emitted:
  - `eval_run_started` — when a run begins (per role or overall)
  - `eval_passed` — per eval that passes all assertions
  - `eval_failed` — per eval that fails, with failure_type for pattern detection

Usage:
    from framework.measurement.role_eval_runner import run_all_for_role, run_all

    # Run all evals bound to the coordinating officer (includes evals
    # inherited from the retired work-preset roster via roster resolution)
    results = run_all_for_role("cos")

    # Run everything (weekly cron path)
    results = run_all()
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.events.emitter import emit


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Registry + discovery
# ---------------------------------------------------------------------------
# Parked in framework/measurement/_eval_registry.py so the `python -m`
# entrypoint and the canonical-package-path importers share ONE registry.
# Re-exported here so existing call sites (`from
# framework.measurement.role_eval_runner import register`) keep working
# unchanged. See _eval_registry.py docstring for the full story.

from framework.measurement._eval_registry import (  # noqa: E402
    EXTINCT_WORK_ROSTER,
    RoleEval,
    RoleEvalResult,
    _EVALS,
    is_discovered as _is_discovered,
    mark_discovered as _mark_discovered,
    register,
    resolve_role_slug,
)


def _get_discovered() -> bool:
    return _is_discovered()


# Backwards-compat shim: legacy code may read/write the module-level
# `_discovered` directly. Mirror to the registry flag.
class _DiscoveredProxy:
    def __bool__(self) -> bool:
        return _is_discovered()

    def __repr__(self) -> str:
        return repr(_is_discovered())


_discovered = _DiscoveredProxy()


def _discover_evals() -> None:
    """Auto-load every .py module in role_evals/ (idempotent)."""
    if _is_discovered():
        return
    _mark_discovered()

    evals_dir = Path(__file__).parent / "role_evals"
    if not evals_dir.exists():
        return

    for f in sorted(evals_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        module_name = f"framework.measurement.role_evals.{f.stem}"
        try:
            importlib.import_module(module_name)
        except (ImportError, ModuleNotFoundError):
            spec = importlib.util.spec_from_file_location(module_name, f)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)


def list_evals(role_slug: str | None = None) -> list[RoleEval]:
    """List all registered evals, optionally filtered by role."""
    _discover_evals()
    evals = list(_EVALS.values())
    if role_slug:
        evals = [e for e in evals if e.role_slug == role_slug]
    return evals


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def run_eval(name: str, actor: str = "role_eval_runner") -> RoleEvalResult:
    """Run a single eval by name."""
    _discover_evals()
    if name not in _EVALS:
        return RoleEvalResult(
            name=name, role_slug="unknown", category="unknown",
            passed=False, duration_ms=0, error=f"Unknown eval: {name}",
        )

    ev = _EVALS[name]
    emit("eval_run_started", actor=actor, payload={
        "eval_name": ev.name,
        "role_slug": ev.role_slug,
        "category": ev.category,
    })

    start = time.time()
    try:
        context = ev.setup()
        results = ev.execute(context)
        assertions_raw = ev.verify(context, results)
        # Each assertion is (name, passed, failure_type)
        assertions = [
            {"name": a_name, "passed": a_passed, "failure_type": a_failtype}
            for a_name, a_passed, a_failtype in assertions_raw
        ]
        all_passed = all(a["passed"] for a in assertions)
        failure_types = list({
            a["failure_type"] for a in assertions
            if not a["passed"] and a["failure_type"] not in (None, "", "n/a")
        })

        result = RoleEvalResult(
            name=ev.name,
            role_slug=ev.role_slug,
            category=ev.category,
            passed=all_passed,
            duration_ms=(time.time() - start) * 1000,
            assertions=assertions,
            failure_types=failure_types,
        )

        if all_passed:
            emit("eval_passed", actor=actor, payload={
                "eval_name": ev.name,
                "role_slug": ev.role_slug,
                "category": ev.category,
                "duration_ms": result.duration_ms,
            })
        else:
            emit("eval_failed", actor=actor, payload={
                "eval_name": ev.name,
                "role_slug": ev.role_slug,
                "category": ev.category,
                "failure_types": failure_types,
                "failed_assertions": [a["name"] for a in assertions if not a["passed"]],
                "duration_ms": result.duration_ms,
            })

        return result

    except Exception as e:  # noqa: BLE001
        emit("eval_failed", actor=actor, payload={
            "eval_name": ev.name,
            "role_slug": ev.role_slug,
            "category": ev.category,
            "failure_types": ["runtime_error"],
            "error": str(e),
            "duration_ms": (time.time() - start) * 1000,
        })
        return RoleEvalResult(
            name=ev.name,
            role_slug=ev.role_slug,
            category=ev.category,
            passed=False,
            duration_ms=(time.time() - start) * 1000,
            error=str(e),
            failure_types=["runtime_error"],
        )


def run_all_for_role(role_slug: str, actor: str = "role_eval_runner") -> list[RoleEvalResult]:
    """Run every eval bound to a role."""
    evals = list_evals(role_slug=role_slug)
    return [run_eval(e.name, actor=actor) for e in evals]


def run_all(actor: str = "role_eval_runner") -> list[RoleEvalResult]:
    """Run every registered eval (used by weekly cron)."""
    evals = list_evals()
    return [run_eval(e.name, actor=actor) for e in evals]


# ---------------------------------------------------------------------------
# Reporting + CLI
# ---------------------------------------------------------------------------


def print_summary(results: list[RoleEvalResult]) -> int:
    """Print a summary block. Return 0 if all pass, 1 if any fail."""
    print(f"\n{'=' * 60}")
    print("  Role Eval Runner")
    print(f"{'=' * 60}\n")

    by_role: dict[str, list[RoleEvalResult]] = {}
    for r in results:
        by_role.setdefault(r.role_slug, []).append(r)

    overall_pass = 0
    overall_fail = 0
    for role_slug in sorted(by_role.keys()):
        role_results = by_role[role_slug]
        p = sum(1 for r in role_results if r.passed)
        f = len(role_results) - p
        overall_pass += p
        overall_fail += f
        print(f"  {role_slug}: {p} pass / {f} fail")
        for r in role_results:
            status = "PASS" if r.passed else "FAIL"
            print(f"    [{status}] {r.name} ({r.category}, {r.duration_ms:.1f}ms)")
            if not r.passed:
                for a in r.assertions:
                    if not a["passed"]:
                        print(f"          FAIL: {a['name']} (type: {a.get('failure_type', 'n/a')})")
                if r.error:
                    print(f"          ERROR: {r.error}")

    print(f"\n{'=' * 60}")
    print(f"  Total: {overall_pass + overall_fail}  |  Pass: {overall_pass}  |  Fail: {overall_fail}")
    print(f"{'=' * 60}\n")

    return 0 if overall_fail == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run role evals")
    parser.add_argument("--role", help="Run evals for a specific role slug")
    parser.add_argument("--eval", help="Run a single eval by name")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--list", action="store_true", help="List registered evals (no run)")
    args = parser.parse_args(argv)

    if args.list:
        evals = list_evals(role_slug=args.role)
        if args.json:
            print(json.dumps([{
                "name": e.name,
                "role_slug": e.role_slug,
                "category": e.category,
                "description": e.description,
            } for e in evals]))
        else:
            for e in evals:
                print(f"  {e.role_slug:12}  {e.category:12}  {e.name}")
            print(f"\n{len(evals)} eval(s)")
        return 0

    if args.eval:
        results = [run_eval(args.eval)]
    elif args.role:
        results = run_all_for_role(args.role)
    else:
        results = run_all()

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
        return 0 if all(r.passed for r in results) else 1

    return print_summary(results)


if __name__ == "__main__":
    sys.exit(main())
