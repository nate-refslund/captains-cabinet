"""Module-identity-safe registry for scenario evals.

Background
----------
`scenario_runner.py` doubles as a CLI entrypoint (`python3 -m
framework.measurement.scenario_runner`). When loaded that way, Python
loads the module as `__main__`, so any *other* code that imports it via
its canonical package path (`framework.measurement.scenario_runner`)
gets a SECOND, distinct module object. That means two `_SCENARIOS`
dicts: one in `__main__`, one in the canonical module.

Each scenario file under `scenarios/` does
`from framework.measurement.scenario_runner import register` — i.e. the
canonical path — so it always populates the *canonical* dict. The
`__main__`-loaded runner then iterates an empty dict and reports zero
scenarios. That broke the weekly role-eval cron and quietly failed the
org-eval-in-CI success criterion.

Fix
---
Park the registry (`_SCENARIOS`, `register`, the `Scenario` /
`ScenarioResult` dataclasses, the discovery flag) in this dedicated
module that is *never* invoked as `__main__`. Both the `-m` runner and
the canonical importers go through this single module object, so there
is exactly one registry regardless of how the runner is entered.

This is the textbook "registry-in-its-own-module" pattern; it also
makes the public surface of the scenario system explicit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    duration_ms: float
    assertions: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "duration_ms": self.duration_ms,
            "assertions": self.assertions,
            "error": self.error,
        }


@dataclass
class Scenario:
    """A single organizational capability scenario."""
    name: str
    description: str
    category: str  # outcome, role, mission, policy, memory, recovery
    setup: Callable[[], dict[str, Any]]  # returns context
    execute: Callable[[dict[str, Any]], dict[str, Any]]  # returns results
    verify: Callable[[dict[str, Any], dict[str, Any]], list[tuple[str, bool]]]  # returns (assertion_name, passed) list


# Single source of truth for registered scenarios. Anything that needs
# to enumerate scenarios must import this dict (or `register`) from
# THIS module — not from `scenario_runner`, which may be loaded as
# `__main__`.
_SCENARIOS: dict[str, Scenario] = {}

# Discovery flag lives here too so the -m runner and the pytest path
# share the same "have we walked scenarios/ yet" state.
_discovered: bool = False


def register(scenario: Scenario) -> Scenario:
    """Register a scenario for the runner."""
    _SCENARIOS[scenario.name] = scenario
    return scenario


def mark_discovered() -> None:
    global _discovered
    _discovered = True


def is_discovered() -> bool:
    return _discovered
