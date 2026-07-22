#!/usr/bin/env python3.12
"""cog2-rebuild.py — rebuild the Cortex projection from zero over the outbox.

COG-2 UNIT 1 (deterministic-rebuild core). Plan:
docs/plans/cognitive-core-phase-2-contract-2026-07-22.md §5 (fold), §6 (storage).
This is the subprocess entry the §8 sim-1 determinism gate drives: three
rebuilds under three distinct PYTHONHASHSEED values must print an IDENTICAL
belief-store hash (C-F3).

The rebuild is full-refold-only: read the outbox under a read-only REPEATABLE
READ snapshot behind the §5.3 frontier, fold (pure), write beliefs.jsonl +
fold-manifest.json, print the epoch + hash. The DSN is EXPLICIT (--dsn or
COG2_OUTBOX_DSN) — this shadow tool deliberately does NOT auto-resolve the live
NEON_CONNECTION_STRING/DATABASE_URL (point it at the source on purpose). The
SQLite query index is a later-unit (query-API) concern and is not written here.

Usage:
    cog2-rebuild.py --dsn <conninfo> [--cache-dir DIR] [--trust-table F] [--json]
    cog2-rebuild.py --dsn <conninfo> --past-null   # the frontier-past-NULL MUTANT

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import yaml  # noqa: E402

from framework.cortex import adapters, belief, engine  # noqa: E402

_DEFAULT_TRUST_TABLE = _REPO_ROOT / "cabinet" / "config" / "cortex-source-trust.v1.yml"


def load_trust_table(path: Path) -> dict:
    """Load the versioned trust table (a hashed rebuild input). Shape:
    {table_version:int, producers:{producer_key: ppm_int}}."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "table_version" not in raw:
        raise ValueError("trust table must be a mapping with table_version")
    raw.setdefault("producers", {})
    return raw


def rebuild(dsn: str, *, trust_table: dict, past_null: bool = False,
            cache_dir: Path | None = None, validate: bool = True) -> dict:
    """Full refold from zero. Returns the fold manifest."""
    protos, frontier, max_id = adapters.read_and_build(dsn, past_null=past_null)
    beliefs = engine.fold(protos, trust_table=trust_table)
    if validate:
        for b in beliefs:
            issues = belief.validate_belief(b)
            if issues:
                raise SystemExit(
                    f"cog2-rebuild: belief {b.belief_id[:12]} fails cortex/belief@1: "
                    + "; ".join(f"{i.code}@{i.path}" for i in issues[:4]))
    manifest = engine.build_manifest(beliefs, trust_table=trust_table,
                                     frontier=frontier, max_id=max_id)
    if cache_dir is not None:
        engine.write_projection(beliefs, manifest, Path(cache_dir))
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild the Cortex projection (§5/§6)")
    parser.add_argument("--dsn", default=None,
                        help="outbox DSN (else COG2_OUTBOX_DSN); never the live store")
    parser.add_argument("--cache-dir", default=None,
                        help="write beliefs.jsonl + fold-manifest.json here")
    parser.add_argument("--trust-table", default=str(_DEFAULT_TRUST_TABLE))
    parser.add_argument("--past-null", action="store_true",
                        help="MUTANT (sim 1): advance the frontier past a NULL event_id")
    parser.add_argument("--no-validate", action="store_true",
                        help="skip cortex/belief@1 schema validation")
    parser.add_argument("--json", action="store_true",
                        help="emit the full manifest JSON (default: hash + counts)")
    args = parser.parse_args(argv)

    dsn = args.dsn or os.environ.get("COG2_OUTBOX_DSN")
    if not dsn:
        print("cog2-rebuild: need --dsn or COG2_OUTBOX_DSN", file=sys.stderr)
        return 2

    trust_table = load_trust_table(Path(args.trust_table))
    manifest = rebuild(dsn, trust_table=trust_table, past_null=args.past_null,
                       cache_dir=Path(args.cache_dir) if args.cache_dir else None,
                       validate=not args.no_validate)
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps({
            "hash": manifest["belief_store_hash"],
            "beliefs": manifest["belief_count"],
            "frontier": manifest["frontier"],
            "max_id": manifest["max_id"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
