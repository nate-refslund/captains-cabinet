#!/usr/bin/env python3
"""sync-checks.py — keep the mirrored world checks byte-identical to their source.

    python3.12 cabinet/scripts/world-capture/sync-checks.py --check   # verify
    python3.12 cabinet/scripts/world-capture/sync-checks.py --write   # re-copy

WHY A MIRROR AT ALL. The twelve invariants and the offline compositor's wharf
live in a private meta workspace that CI has never seen. A gate that only exists
on one laptop is not a gate — so the repo carries a copy, and CI runs that copy.

WHY A GUARD. Two copies of a sensor is exactly how a sensor goes quiet: someone
fixes a false positive in one and the other keeps passing. This script makes the
divergence mechanical — --check diffs every mirrored file against its source and
exits 1 on any difference, so "the mirror drifted" is a red build rather than a
discovery.

WHEN THE SOURCE IS ABSENT (a fresh CI checkout, or anyone without the meta
workspace) --check reports SKIPPED-NO-SOURCE and exits 0. That is honest rather
than convenient: with no source there is nothing to compare, and failing would
turn a green board red for a reason that has nothing to do with the code. It is
also why this is not the only sensor — the mirrored checks themselves run in CI
against a real capture, so the copy is exercised whether or not it can be
diffed.
"""
from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIRROR = HERE / "mirror"

# Default source root. Overridable so this is not a hardcoded personal path in
# the one place a hardcoded personal path would silently disable the guard.
DEFAULT_SOURCE = Path.home() / "cabinet-meta"

FILES = [
    ("checks/verify.py", "checks/verify.py"),
    ("checks/world_checks.py", "checks/world_checks.py"),
    ("designs/world-mockup-v2/palette.py", "designs/world-mockup-v2/palette.py"),
    ("designs/world-mockup-v2/quay.py", "designs/world-mockup-v2/quay.py"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(DEFAULT_SOURCE))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    a = ap.parse_args()

    src_root = Path(a.source)
    if not src_root.exists():
        print(f"sync-checks: SKIPPED-NO-SOURCE ({src_root} absent) — "
              f"{len(FILES)} mirrored files not diffed")
        return 0

    bad = []
    for rel_src, rel_dst in FILES:
        s = src_root / rel_src
        d = MIRROR / rel_dst
        if not s.exists():
            bad.append(f"source missing: {s}")
            continue
        if a.write:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
            continue
        if not d.exists():
            bad.append(f"mirror missing: {d}")
        elif not filecmp.cmp(s, d, shallow=False):
            bad.append(f"DRIFTED: {rel_dst} differs from {s}")

    if a.write:
        print(f"sync-checks: re-copied {len(FILES)} files from {src_root}")
        return 0
    for b in bad:
        print(f"  {b}", file=sys.stderr)
    print(f"sync-checks: {len(FILES) - len(bad)}/{len(FILES)} mirrored files identical")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
