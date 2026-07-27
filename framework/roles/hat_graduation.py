"""Hat graduation — promote temporary hats to permanent role capabilities.

Phase 7 of the convergence plan. The Cabinet's role model has TWO levels of
capability:

  1. **Base capabilities** — declared in the role's charter; rarely change.
  2. **Hats** — temporary specializations a role wears for a mission context.

A hat that proves consistently useful (≥N uses across ≥N missions) is a
candidate for **graduation**: its capabilities become permanent base
capabilities of the role, and the hat itself can be retired (or kept for
accounting).

This module reads the event ledger to:
  - count hat uses (role_hat_assigned events) per (role_slug, hat_slug)
  - infer the use window (first → last assignment)
  - emit `role_hat_promoted` proposal events for hats meeting criteria

Criteria (configurable):
  - uses ≥ 5
  - distinct missions ≥ 5

NO OVI INPUT — DELIBERATE, AND ENFORCED (Captain rider, 2026-07-25). Until
2026-07-26 this module ALSO gated a candidate on ``_ovi_regression_during()``,
which replayed ``ovi_snapshot_computed`` and read its ``composite_score``.
That made the OVI composite a **selection input**, which the standing Captain
rider forbids absolutely: OVI is a Captain-FACING instrument and must never
select, rank, or gate anything. The wire is cut, and
``framework/tests/test_ovi_never_a_selection_input.py`` fails the suite if any
selection/ranking/gating path reads the composite or the attention term again.

Two independent reasons it had to go, either sufficient:

  1. **The rider.** A dormant violation is still a violation — this path feeds
     ``framework.learning.self_improvement_loop._apply_hat_graduations``, which
     emits ``role_capability_added``, so the composite was one snapshot away
     from mechanically widening a role's permanent capabilities.
  2. **It never worked.** The check failed OPEN at both degenerate ends — no
     snapshot in the window returned False (no regression), and no baseline
     before the window returned False as well — and the live ledger holds ZERO
     ``ovi_snapshot_computed`` events, so in its entire life it never once
     refused a candidate. Removing it changes no observed behaviour; it only
     removes the wire.

The composite it read is itself now known to have been mis-signed: its
attention term scored a week of ZERO Captain contact and ZERO delivery a
perfect 1.00 (see ``framework/ovi/components.yml``). A selection input built
on that would have rewarded going quiet.

Output: proposals for Captain to ratify. Each proposal is a draft amendment
to the role's charter (add capabilities, remove the hat). On ratification,
`framework.roles.lifecycle` applies the change.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.events.emitter import emit, replay


# Defaults
DEFAULT_MIN_USES = 5
DEFAULT_MIN_MISSIONS = 5


def _hat_usage_from_events() -> dict[tuple[str, str], dict[str, Any]]:
    """Replay role_hat_assigned + role_hat_promoted events; group by (role, hat).

    Returns:
        Dict keyed by (role_slug, hat_slug) → {uses, missions, first, last,
        capabilities_granted, promoted}.
    """
    usage: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {
        "uses": 0,
        "missions": set(),
        "first": None,
        "last": None,
        "capabilities_granted": set(),
        "promoted": False,
    })

    for ev in replay(event_types=["role_hat_assigned"]):
        p = ev.get("payload") or {}
        role = p.get("role_slug") or p.get("role")
        hat = p.get("hat_slug") or p.get("hat_name") or p.get("name")
        if not role or not hat:
            continue
        key = (role, hat)
        bucket = usage[key]
        bucket["uses"] += 1
        if p.get("mission_id"):
            bucket["missions"].add(p["mission_id"])
        ts = ev.get("created_at")
        if bucket["first"] is None or (ts and ts < bucket["first"]):
            bucket["first"] = ts
        if bucket["last"] is None or (ts and ts > bucket["last"]):
            bucket["last"] = ts
        for cap in p.get("capabilities") or p.get("capabilities_granted") or []:
            bucket["capabilities_granted"].add(cap)

    for ev in replay(event_types=["role_hat_promoted"]):
        p = ev.get("payload") or {}
        role = p.get("role_slug") or p.get("role")
        hat = p.get("hat_slug") or p.get("hat_name")
        if role and hat:
            usage[(role, hat)]["promoted"] = True

    return usage


def graduation_candidates(
    min_uses: int = DEFAULT_MIN_USES,
    min_missions: int = DEFAULT_MIN_MISSIONS,
) -> list[dict[str, Any]]:
    """Return all (role, hat) pairs that meet graduation criteria + have not yet promoted.

    Criteria are USE EVIDENCE ONLY: uses, distinct missions, not-yet-promoted.
    No OVI term participates — see the module docstring's "NO OVI INPUT"
    section for the Captain rider that forbids it and the two independent
    reasons the removed check was both unlawful and inert.
    """
    usage = _hat_usage_from_events()
    candidates: list[dict[str, Any]] = []
    for (role, hat), bucket in usage.items():
        if bucket["promoted"]:
            continue
        if bucket["uses"] < min_uses:
            continue
        if len(bucket["missions"]) < min_missions:
            continue
        candidates.append({
            "role_slug": role,
            "hat_slug": hat,
            "uses": bucket["uses"],
            "missions": len(bucket["missions"]),
            "first_used": bucket["first"],
            "last_used": bucket["last"],
            "capabilities_to_promote": sorted(bucket["capabilities_granted"]),
        })
    return candidates


def propose_graduations(
    actor: str = "hat_graduation",
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Find candidates and emit one role_hat_promoted event per candidate.

    The emitted event is a PROPOSAL, not a binding promotion — Captain
    ratifies via the proposals workflow. The event carries
    `status: pending_captain_approval` in its payload.
    """
    candidates = graduation_candidates(**kwargs)
    for c in candidates:
        emit("role_hat_promoted", actor=actor, payload={
            **c,
            "status": "pending_captain_approval",
        })
    return candidates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Identify and propose hat graduations."
    )
    parser.add_argument("--min-uses", type=int, default=DEFAULT_MIN_USES)
    parser.add_argument("--min-missions", type=int, default=DEFAULT_MIN_MISSIONS)
    parser.add_argument("--dry-run", action="store_true",
                        help="Identify candidates without emitting events")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.dry_run:
        candidates = graduation_candidates(
            min_uses=args.min_uses, min_missions=args.min_missions,
        )
    else:
        candidates = propose_graduations(
            min_uses=args.min_uses, min_missions=args.min_missions,
        )

    if args.json:
        print(json.dumps(candidates, indent=2, default=str))
    elif not candidates:
        print(f"hat-graduation: no candidates "
              f"(min_uses={args.min_uses}, min_missions={args.min_missions})")
    else:
        print(f"hat-graduation: {len(candidates)} candidate(s)")
        for c in candidates:
            print(f"  → {c['role_slug']} / {c['hat_slug']}: "
                  f"{c['uses']} uses across {c['missions']} missions; "
                  f"capabilities: {', '.join(c['capabilities_to_promote'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
