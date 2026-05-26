"""Hat graduation — promote temporary hats to permanent role capabilities.

Phase 7 of the convergence plan. The Cabinet's role model has TWO levels of
capability:

  1. **Base capabilities** — declared in the role's charter; rarely change.
  2. **Hats** — temporary specializations a role wears for a mission context.

A hat that proves consistently useful (≥N uses across ≥N missions, without
OVI regression during its use) is a candidate for **graduation**: its
capabilities become permanent base capabilities of the role, and the hat
itself can be retired (or kept for accounting).

This module reads the event ledger to:
  - count hat uses (role_hat_assigned events) per (role_slug, hat_slug)
  - infer the use window (first → last assignment)
  - check whether OVI regressed during that window
  - emit `role_hat_promoted` proposal events for hats meeting criteria

Criteria (configurable):
  - uses ≥ 5
  - distinct missions ≥ 5
  - OVI mean during use window not lower than 2% below baseline

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
DEFAULT_OVI_REGRESSION_THRESHOLD = 0.02  # 2%


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


def _ovi_regression_during(
    first_iso: str | None,
    last_iso: str | None,
    threshold: float,
) -> bool:
    """True if any OVI snapshot during the window dropped > threshold below the prior baseline.

    If no OVI snapshots exist in the window, returns False (no evidence of regression).
    """
    if not first_iso:
        return False

    snapshots = replay(event_types=["ovi_snapshot_computed"])
    in_window = [
        s for s in snapshots
        if (not first_iso or s["created_at"] >= first_iso)
        and (not last_iso or s["created_at"] <= last_iso)
    ]
    if not in_window:
        return False

    baseline_candidates = [
        s for s in snapshots
        if first_iso and s["created_at"] < first_iso
    ]
    if not baseline_candidates:
        return False
    baseline_score = float(
        (baseline_candidates[-1].get("payload") or {}).get("composite_score", 0)
    )

    for s in in_window:
        score = float((s.get("payload") or {}).get("composite_score", 0))
        if (baseline_score - score) > threshold:
            return True
    return False


def graduation_candidates(
    min_uses: int = DEFAULT_MIN_USES,
    min_missions: int = DEFAULT_MIN_MISSIONS,
    ovi_threshold: float = DEFAULT_OVI_REGRESSION_THRESHOLD,
) -> list[dict[str, Any]]:
    """Return all (role, hat) pairs that meet graduation criteria + have not yet promoted."""
    usage = _hat_usage_from_events()
    candidates: list[dict[str, Any]] = []
    for (role, hat), bucket in usage.items():
        if bucket["promoted"]:
            continue
        if bucket["uses"] < min_uses:
            continue
        if len(bucket["missions"]) < min_missions:
            continue
        if _ovi_regression_during(bucket["first"], bucket["last"], ovi_threshold):
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
