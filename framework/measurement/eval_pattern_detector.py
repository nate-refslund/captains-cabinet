"""Eval pattern detector — flag role-level failure clusters worth evolving on.

Phase 2.2 of the convergence plan. Reads `eval_failed` events from the
ledger, groups by (role_slug, failure_type), and flags any group with
≥N occurrences in the last M days as a candidate for charter evolution.

The detector emits one ``role_eval_pattern_flagged`` event per candidate
so the evolution proposal generator (Phase 2.3) and the dashboard can
consume the signal without re-scanning the entire ledger.

Wait — `role_eval_pattern_flagged` isn't in the emitter vocabulary yet.
The detector therefore lives as a **read-only** module: it returns the
pattern list and a CLI prints it; evolution.py (next sub-phase) emits the
flag-events when it generates proposals.

Usage:
    from framework.measurement.eval_pattern_detector import detect_patterns

    patterns = detect_patterns(window_days=28, min_occurrences=3)
    for p in patterns:
        print(p["role_slug"], p["failure_type"], p["count"])
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.events.emitter import replay


_DEFAULT_WINDOW_DAYS = 28  # ~4 weeks
_DEFAULT_MIN_OCCURRENCES = 3


def _window_cutoff_iso(days: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return cutoff.isoformat()


def detect_patterns(
    window_days: int = _DEFAULT_WINDOW_DAYS,
    min_occurrences: int = _DEFAULT_MIN_OCCURRENCES,
) -> list[dict[str, Any]]:
    """Find recurring eval failures worth evolving the role's charter on.

    Args:
        window_days: only consider eval_failed events within this rolling window
        min_occurrences: threshold for flagging a (role, failure_type) cluster

    Returns:
        list of pattern dicts, each shaped:
            {
                "role_slug": str,
                "failure_type": str,
                "count": int,
                "eval_names": list[str],  # distinct evals contributing to the cluster
                "first_seen": iso8601 str,
                "last_seen": iso8601 str,
                "sample_failed_assertions": list[str],
            }
        sorted by count descending.
    """
    since = _window_cutoff_iso(window_days)
    failed = replay(event_types=["eval_failed"], since=since)

    # Group: (role_slug, failure_type) → list[event]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for ev in failed:
        p = ev.get("payload") or {}
        role_slug = p.get("role_slug")
        if not role_slug:
            continue
        # Each failed event may carry multiple failure_types; explode them so
        # one eval failing for two reasons contributes to both buckets.
        types = p.get("failure_types") or []
        if not types:
            # Fallback: count under the synthetic 'unspecified' bucket so we
            # still surface noisy roles with poorly-annotated evals.
            types = ["unspecified"]
        for ftype in types:
            groups[(role_slug, ftype)].append(ev)

    flagged: list[dict[str, Any]] = []
    for (role_slug, failure_type), events in groups.items():
        if len(events) < min_occurrences:
            continue

        eval_names = sorted({
            (e.get("payload") or {}).get("eval_name", "?")
            for e in events
        })
        # Sample up to 5 distinct failed assertion names
        failed_assertions: set[str] = set()
        for e in events:
            for name in (e.get("payload") or {}).get("failed_assertions", []) or []:
                failed_assertions.add(name)
                if len(failed_assertions) >= 5:
                    break

        timestamps = sorted(e["created_at"] for e in events)

        flagged.append({
            "role_slug": role_slug,
            "failure_type": failure_type,
            "count": len(events),
            "eval_names": eval_names,
            "first_seen": timestamps[0],
            "last_seen": timestamps[-1],
            "sample_failed_assertions": sorted(failed_assertions),
        })

    flagged.sort(key=lambda p: (-p["count"], p["role_slug"], p["failure_type"]))
    return flagged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect recurring role eval failure patterns."
    )
    parser.add_argument(
        "--window-days", type=int, default=_DEFAULT_WINDOW_DAYS,
        help=f"Rolling window (default: {_DEFAULT_WINDOW_DAYS})",
    )
    parser.add_argument(
        "--min-occurrences", type=int, default=_DEFAULT_MIN_OCCURRENCES,
        help=f"Threshold to flag (default: {_DEFAULT_MIN_OCCURRENCES})",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    patterns = detect_patterns(
        window_days=args.window_days,
        min_occurrences=args.min_occurrences,
    )

    if args.json:
        print(json.dumps(patterns, indent=2))
    elif not patterns:
        print(
            f"eval-pattern-detector: no patterns flagged "
            f"(window={args.window_days}d, threshold={args.min_occurrences})"
        )
    else:
        print(f"eval-pattern-detector: {len(patterns)} pattern(s) flagged")
        for p in patterns:
            print(f"  [{p['role_slug']}] {p['failure_type']}: "
                  f"{p['count']} occurrences across {len(p['eval_names'])} eval(s)")
            print(f"     evals: {', '.join(p['eval_names'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
