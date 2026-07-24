#!/usr/bin/env python3.12
"""cog4-snapshot.py — build one versioned wake snapshot (COG-4 §7.1/§2.1).

The CLI owns EVERY path default and injection (§4.4 layer law — framework code
carries no instance literal): the cache root, the cortex/objectives store
dirs, the services manifest, and the declared SF2 ledger paths all live HERE.
Every snapshot input is a DECLARED parameter; `--cutoff` and `--scope` are
REQUIRED flags — this CLI never reads the clock, so the same invocation always
builds the same snapshot (A-M6 purity starts at the builder).

Honest absence (SF2): an OMITTED ledger flag records the empty ledger `{}` —
what was actually found. An EXPLICITLY passed path that does not exist is an
error (a declared input may not silently vanish). Missing/corrupt cortex or
objectives stores fail LOUD (no snapshot is built); the §7.4 fixed-safe-
schedule fallback is the dispatcher's law, never an invented input here.

Usage:
    cog4-snapshot.py --scope main --cutoff 2026-07-24T00:00:00Z \
        [--cache-root cabinet/cache] [--cortex-cache-dir DIR]
        [--objectives-cache-dir DIR] [--services-manifest FILE]
        [--organ-registry FILE] [--organ-health FILE]
        [--failure-history FILE] [--capability-availability FILE]
        [--budget-ceiling N] [--default-starvation-bound N]
        [--budget-version N] [--posture-version N]
        [--trust-table-version N] [--scheduler-policy-version N]
        [--out FILE] [--json]

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; COG-4 W3 u2 (scheduler CLIs).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.scheduler import model, snapshot  # noqa: E402


def _load_ledger(arg: str | None, name: str) -> dict:
    """Declared SF2 ledger: omitted flag => the honest empty ledger; a passed
    path must exist and hold a JSON object."""
    if arg is None:
        return {}
    path = Path(arg)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(
            f"cog4-snapshot: declared {name} ledger unreadable at {path} "
            f"({type(exc).__name__})")
    if not isinstance(data, dict):
        raise SystemExit(f"cog4-snapshot: {name} ledger must be a JSON object")
    return data


def _load_registry(arg: str | None) -> list:
    """Declared organ-registry input: omitted => the honest empty registry
    (no organs are packaged before the W4 germline window); a passed path must
    exist and hold a JSON array."""
    if arg is None:
        return []
    path = Path(arg)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(
            f"cog4-snapshot: declared organ registry unreadable at {path} "
            f"({type(exc).__name__})")
    if not isinstance(data, list):
        raise SystemExit("cog4-snapshot: organ registry must be a JSON array")
    return data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="COG-4 wake-snapshot builder (declared inputs only)")
    parser.add_argument("--cache-root",
                        default=str(_REPO_ROOT / "cabinet" / "cache"),
                        help="the shared cache root; per-store dirs derive "
                             "from it unless overridden")
    parser.add_argument("--cortex-cache-dir", default=None,
                        help="cortex store dir (default: <cache-root>/cortex)")
    parser.add_argument("--objectives-cache-dir", default=None,
                        help="objectives store dir (default: "
                             "<cache-root>/objectives)")
    parser.add_argument("--services-manifest",
                        default=str(_REPO_ROOT / "cabinet" / "services.yml"),
                        help="the services manifest whose bytes are hashed")
    parser.add_argument("--organ-registry", default=None,
                        help="JSON array of organ manifest excerpts "
                             "(omitted = the honest empty registry)")
    parser.add_argument("--organ-health", default=None,
                        help="declared SF2 health ledger (JSON object)")
    parser.add_argument("--failure-history", default=None,
                        help="declared SF2 failure-history ledger "
                             "(JSON object; carries wakes_waiting)")
    parser.add_argument("--capability-availability", default=None,
                        help="declared SF2 capability/MCP inventory "
                             "(JSON object)")
    parser.add_argument("--budget-ceiling", type=int, default=10,
                        help="external hard ceiling, units per wake (§7.2)")
    parser.add_argument("--default-starvation-bound", type=int, default=4,
                        help="scheduler_policy default when an organ declares "
                             "no starvation_bound (SF2)")
    parser.add_argument("--budget-version", type=int, default=1)
    parser.add_argument("--posture-version", type=int, default=1)
    parser.add_argument("--trust-table-version", type=int, default=1)
    parser.add_argument("--scheduler-policy-version", type=int, default=1)
    parser.add_argument("--scope", required=True,
                        help="declared scope token (e.g. the cabinet id)")
    parser.add_argument("--cutoff", required=True,
                        help="canonical YYYY-MM-DDTHH:MM:SSZ cutoff — "
                             "REQUIRED; this CLI never reads the clock")
    parser.add_argument("--out", default=None,
                        help="snapshot output path (default: "
                             "<cache-root>/scheduler/wake-snapshot.json)")
    parser.add_argument("--json", action="store_true",
                        help="emit a JSON result record")
    args = parser.parse_args(argv)

    cache_root = Path(args.cache_root)
    cortex_dir = Path(args.cortex_cache_dir) if args.cortex_cache_dir \
        else cache_root / "cortex"
    objectives_dir = Path(args.objectives_cache_dir) \
        if args.objectives_cache_dir else cache_root / "objectives"
    out = Path(args.out) if args.out \
        else cache_root / "scheduler" / "wake-snapshot.json"

    try:
        snap = snapshot.build_snapshot(
            cortex_cache_dir=cortex_dir,
            objectives_cache_dir=objectives_dir,
            services_manifest_path=args.services_manifest,
            organ_registry=_load_registry(args.organ_registry),
            organ_health=_load_ledger(args.organ_health, "organ-health"),
            failure_history=_load_ledger(args.failure_history,
                                         "failure-history"),
            capability_availability=_load_ledger(
                args.capability_availability, "capability-availability"),
            budget_ceiling_units_per_wake=args.budget_ceiling,
            default_starvation_bound=args.default_starvation_bound,
            budget_version=args.budget_version,
            posture_version=args.posture_version,
            trust_table_version=args.trust_table_version,
            scheduler_policy_version=args.scheduler_policy_version,
            scope=args.scope,
            cutoff=args.cutoff,
        )
        snapshot_hash = model.write_snapshot(snap, out)
    except model.SnapshotError as exc:
        print(f"cog4-snapshot: REFUSED — {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"out": str(out), "snapshot_hash": snapshot_hash,
                          "scope": args.scope, "cutoff": args.cutoff},
                         sort_keys=True))
    else:
        print(snapshot_hash)
    return 0


if __name__ == "__main__":
    sys.exit(main())
