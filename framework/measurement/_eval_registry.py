"""Module-identity-safe registry for role evals.

Mirrors the fix in `_scenario_registry.py`. See that module's docstring for
the full explanation of the `__main__` vs canonical-package-path module-
identity bug.

TL;DR: when `role_eval_runner.py` is invoked via `python3 -m
framework.measurement.role_eval_runner` (which the weekly cron at
`cabinet/cron/role-evals-weekly.sh` does), Python loads it as `__main__`,
so its module-level `_EVALS` dict is distinct from the one that the
`framework/measurement/role_evals/*.py` files write into via
`from framework.measurement.role_eval_runner import register`. Result:
runner iterates an empty dict, weekly cron produces zero signal.

Park `_EVALS`, `register`, the `RoleEval` / `RoleEvalResult` dataclasses,
and the discovery flag in this dedicated module. Both `-m` runner entry
and canonical-path importers see exactly one registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class RoleEval:
    """A single eval bound to a specific role.

    Categories: 'capability' (does the role know how to X?), 'authority'
    (does the role's charter cover X?), 'quality' (does the role's output
    meet standard X?), 'memory' (does the role correctly use its memory
    artifacts?).
    """
    name: str
    role_slug: str
    category: str  # capability | authority | quality | memory
    description: str
    setup: Callable[[], dict[str, Any]]
    execute: Callable[[dict[str, Any]], dict[str, Any]]
    verify: Callable[[dict[str, Any], dict[str, Any]], list[tuple[str, bool, str]]]
    # verify returns list of (assertion_name, passed, failure_type)
    # failure_type is one of: missing_skill | wrong_authority | scope_confusion |
    # quality_gap | n/a (for passing assertions)


@dataclass
class RoleEvalResult:
    name: str
    role_slug: str
    category: str
    passed: bool
    duration_ms: float
    assertions: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    failure_types: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role_slug": self.role_slug,
            "category": self.category,
            "passed": self.passed,
            "duration_ms": self.duration_ms,
            "assertions": self.assertions,
            "error": self.error,
            "failure_types": self.failure_types,
        }


# Single source of truth for registered role evals. Importers must reach
# THIS module (directly OR via the re-export shim in `role_eval_runner`).
_EVALS: dict[str, RoleEval] = {}

# Discovery flag shared between -m runner and canonical importers.
_discovered: bool = False


def register(ev: RoleEval) -> RoleEval:
    """Register a role eval. Returns the eval for chaining in module scope."""
    _EVALS[ev.name] = ev
    return ev


def mark_discovered() -> None:
    global _discovered
    _discovered = True


def is_discovered() -> bool:
    return _discovered
