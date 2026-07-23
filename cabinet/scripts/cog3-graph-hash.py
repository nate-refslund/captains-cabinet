#!/usr/bin/env python3.12
"""cog3-graph-hash.py — the N1 chained-graph-hash instrument (COG-3 §8 / §5.4).

Prints the deterministic chained hash over the RE-PARSED graph rows + manifest
(never file bytes — A-m11) under an objectives cache dir. This is the core the
C-F3 subprocess-triple determinism gate drives: three rebuilds under three
distinct PYTHONHASHSEED values must print an IDENTICAL hash.

Usage:
    cog3-graph-hash.py --cache <objectives cache dir>

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; U2 (the objectives instruments/CLIs).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.objectives import graph  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="COG-3 chained-graph-hash instrument")
    parser.add_argument("--cache", required=True,
                        help="the objectives cache dir holding graph.jsonl + manifest")
    args = parser.parse_args(argv)
    print(graph.chained_graph_hash(args.cache))
    return 0


if __name__ == "__main__":
    sys.exit(main())
