#!/usr/bin/env python3.12
"""cog4-schedule.py — run the pure fold: wake snapshot -> schedule store
(COG-4 §7.2). The CLI owns the path defaults (§4.4 layer law); the fold is a
pure function of the snapshot file and writes ONLY under the cache dir,
serialized by the §7.5 writer lock (a held lock fails LOUD, exit 2 — losers
never race, never corrupt).

After the build the result is printed THROUGH the one kernel-bound loader
(serve_schedule — the F1 law): what this CLI reports is what a verified serve
returns, never a side-channel read of the store it just wrote.

SHADOW-ONLY: the schedule store influences nothing this phase — launchd keeps
its fixed wakes; the separate dispatcher (§7.3, W5) only ever compares.

Usage:
    cog4-schedule.py [--snapshot FILE] [--cache-dir DIR]
                     [--cache-root DIR] [--json]

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

from framework.scheduler import model  # noqa: E402
from framework.scheduler.fold import ScheduleLockHeld, build_schedule  # noqa: E402
from framework.scheduler.serve import ScheduleRefused, serve_schedule  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="COG-4 pure fold: snapshot -> schedule store")
    parser.add_argument("--cache-root",
                        default=str(_REPO_ROOT / "cabinet" / "cache"),
                        help="the shared cache root the defaults derive from")
    parser.add_argument("--snapshot", default=None,
                        help="the wake-snapshot file (default: "
                             "<cache-root>/scheduler/wake-snapshot.json)")
    parser.add_argument("--cache-dir", default=None,
                        help="the schedule store dir (default: "
                             "<cache-root>/scheduler)")
    parser.add_argument("--json", action="store_true",
                        help="emit a JSON result record")
    args = parser.parse_args(argv)

    cache_root = Path(args.cache_root)
    snapshot_path = Path(args.snapshot) if args.snapshot \
        else cache_root / "scheduler" / "wake-snapshot.json"
    cache_dir = Path(args.cache_dir) if args.cache_dir \
        else cache_root / "scheduler"

    try:
        build_schedule(snapshot_path, cache_dir)
    except ScheduleLockHeld as exc:
        print(f"cog4-schedule: LOCK HELD — {exc}", file=sys.stderr)
        return 2
    except (model.SnapshotError, OSError, ValueError) as exc:
        print(f"cog4-schedule: REFUSED — {exc}", file=sys.stderr)
        return 1
    try:
        served = serve_schedule(cache_dir)        # F1: report via the loader
    except ScheduleRefused as exc:
        print(f"cog4-schedule: built store failed its own verified serve — "
              f"{exc}", file=sys.stderr)
        return 1
    manifest = served["manifest"]
    if args.json:
        print(json.dumps({
            "cache_dir": str(cache_dir),
            "schedule_rows_hash": served["schedule_rows_hash"],
            "snapshot_hash": manifest["epoch"]["snapshot_hash"],
            "counts": manifest["counts"],
            "budget": manifest["budget"],
        }, sort_keys=True))
    else:
        counts = manifest["counts"]
        print(f"{served['schedule_rows_hash']}  rows={counts['rows']} "
              f"selected={counts['selected']} deferred={counts['deferred']} "
              f"conflicts={counts['conflicts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
