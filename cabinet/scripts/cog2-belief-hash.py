#!/usr/bin/env python3.12
"""cog2-belief-hash.py — re-derive the Cortex belief-store hash from JSONL.

COG-2 UNIT 1. Plan: docs/plans/cognitive-core-phase-2-contract-2026-07-22.md
§5.1 (A-m11 rows-not-bytes) / §6. The hash is computed by RE-PARSING and
re-canonicalizing each JSONL row and chaining — NEVER by hashing the file byte
stream. Because the writer emits exactly the canonical bytes, this re-derived
hash equals the fold-time manifest hash iff the store is intact; a byte-flip is
detected. This instrument is the standing rows-not-bytes proof and (in a later
unit) the serve-time store-hash binding's engine.

Usage:
    cog2-belief-hash.py <beliefs.jsonl>       # prints the 64-char hex hash
    cog2-belief-hash.py <beliefs.jsonl> --json

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.cortex import belief, engine  # noqa: E402


def hash_jsonl(path: Path) -> tuple[str, int]:
    rows = engine.read_beliefs_jsonl(Path(path))
    return belief.hash_canonical_rows(rows), len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-derive the belief-store hash (§5.1)")
    parser.add_argument("jsonl", help="path to a beliefs.jsonl")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    digest, count = hash_jsonl(Path(args.jsonl))
    if args.json:
        print(json.dumps({"hash": digest, "beliefs": count}, sort_keys=True))
    else:
        print(digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
