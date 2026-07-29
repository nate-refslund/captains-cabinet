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

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from framework import env  # roster-resolved default role


@dataclass
class RoleEval:
    """A single eval bound to a specific role.

    Categories: 'capability' (does the role know how to X?), 'authority'
    (does the role's charter cover X?), 'quality' (does the role's output
    meet standard X?), 'memory' (does the role correctly use its memory
    artifacts?).

    `role_slug` is resolved against the LIVE roster at registration time
    (see `resolve_role_slug` below); when a remap happens the author's
    original binding is preserved in `declared_role_slug` for lineage.
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
    declared_role_slug: str = ""  # original author binding when remapped, else ""


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


# ---------------------------------------------------------------------------
# Live-roster resolution (R8 retarget, 2026-07-04, lane/learn-0705)
# ---------------------------------------------------------------------------
# The 10 shipped role_evals were authored for the original work-preset
# roster (cto/cpo/cro/coo), which the F0.2 residue purge (2026-07-02,
# Captain-blessed — see the header of cabinet/officer-capabilities.conf)
# retired. Those roles no longer exist in instance/roles/active/, so every
# eval_failed event attributed to them flowed into
# roles.evolution.propose_from_patterns → load_role(slug) → not loadable:
# the weekly R8 chain (cabinet/cron/role-evals-weekly.sh → pattern detector
# → self-improvement loop) dead-ended at the proposal step for 8 of 10
# evals. The evals themselves exercise FRAMEWORK subsystems (mission
# compiler, work routing, outbox relay, event replay, OVI components,
# policy engine, DAG validation) — role-generic content — so rather than
# hardcoding a new roster into framework/ (which must stay
# instance-agnostic: lane-CEO slugs like a per-product CEO are instance
# config, not framework knowledge), the registry resolves each declared
# slug against the LIVE roster from cabinet/officer-capabilities.conf at
# registration time. Attribution then always targets a role the evolution
# loop can actually load and amend.

# The retired work-preset roster. ONLY these slugs are ever remapped —
# synthetic test slugs and live slugs pass through untouched, and a
# deployment that genuinely still runs one of these (it appears in its own
# capabilities conf) keeps it (rule 2 in resolve_role_slug).
EXTINCT_WORK_ROSTER = frozenset({"cto", "cpo", "cro", "coo"})

# Static last-resort successor: `cos` is the one coordinator slug present in
# every shipped preset (work-preset CoS; the portfolio Chair id-reuses `cos`
# — documented in officer-capabilities.conf) and in the spawn fallback
# roster (instance/config/platform.yml "cos cto cpo coo cro" note).
# Platform-subsystem evals belong to the coordinating officer when their
# original owner is gone.
_STATIC_SUCCESSOR = env.chair_officer()


def _live_roster() -> dict[str, list[str]]:
    """Parse the live officer roster from cabinet/officer-capabilities.conf.

    That conf is the deployment's roster source of truth (its F0.2 header
    states it "describes the LIVE portfolio roster only"; format
    `officer:capability`, one per line, `#` comments). Read STRICTLY under
    $CABINET_ROOT — deliberately no fallback to this module's own repo when
    CABINET_ROOT points elsewhere: tests isolate by pointing CABINET_ROOT at
    a tmp dir, and a repo-relative fallback would leak the dev checkout's
    roster into them. Missing/unreadable conf → empty roster → the static
    successor below.
    """
    root = Path(os.environ.get("CABINET_ROOT", Path(__file__).parent.parent.parent))
    conf = root / "cabinet" / "officer-capabilities.conf"
    roster: dict[str, list[str]] = {}
    try:
        for raw in conf.read_text().splitlines():
            # Strip trailing inline comments BEFORE parsing — a line like
            # `cos:validates_deployments  # coordinator` must yield the bare
            # capability, or the exact-match capability lookup in
            # resolve_role_slug rule 3 silently misses (checkpoint-review
            # finding, cp1 #7).
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            officer, cap = line.split(":", 1)
            officer, cap = officer.strip(), cap.strip()
            if officer:
                roster.setdefault(officer, [])
                if cap:
                    roster[officer].append(cap)
    except OSError:
        return {}
    return roster


def resolve_role_slug(declared: str) -> str:
    """Map an eval's declared role slug onto the live roster.

    Rules (deliberately surgical — see the R8 block comment above):
      1. Only slugs in EXTINCT_WORK_ROSTER are ever remapped. Synthetic test
         slugs (e.g. `t_role`) and live slugs pass through untouched.
      2. An "extinct" slug that IS in the live conf stays — a deployment
         that genuinely runs a cto keeps cto-attributed evals.
      3. Otherwise the successor is `cos` when the conf lists it; else the
         first conf officer holding `validates_deployments` (the
         platform-quality owner — the capability tie that best matches what
         these subsystem evals measure); else the static `cos`.
    """
    if declared not in EXTINCT_WORK_ROSTER:
        return declared
    roster = _live_roster()
    if declared in roster:
        return declared
    if _STATIC_SUCCESSOR in roster:
        return _STATIC_SUCCESSOR
    for officer, caps in roster.items():
        if "validates_deployments" in caps:
            return officer
    return _STATIC_SUCCESSOR


# Single source of truth for registered role evals. Importers must reach
# THIS module (directly OR via the re-export shim in `role_eval_runner`).
_EVALS: dict[str, RoleEval] = {}

# Discovery flag shared between -m runner and canonical importers.
_discovered: bool = False


def register(ev: RoleEval) -> RoleEval:
    """Register a role eval. Returns the eval for chaining in module scope.

    Registration RESOLVES the declared role binding against the live roster
    (`resolve_role_slug`) so eval events + failure-pattern attribution
    always target a role that `roles.lifecycle.load_role` can actually load.
    The author's original slug is kept on `declared_role_slug` for lineage —
    the shipped eval files keep documenting which historical role owned the
    subsystem.
    """
    resolved = resolve_role_slug(ev.role_slug)
    if resolved != ev.role_slug:
        ev.declared_role_slug = ev.role_slug
        ev.role_slug = resolved
    _EVALS[ev.name] = ev
    return ev


def mark_discovered() -> None:
    global _discovered
    _discovered = True


def is_discovered() -> bool:
    return _discovered
