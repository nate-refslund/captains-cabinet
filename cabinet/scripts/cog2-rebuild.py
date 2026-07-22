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

§7.2 READ-ONLY PROVISIONING (--provision-ro, G-F6): a second, ADMIN-side mode.
Given an ADMIN --dsn/COG2_OUTBOX_DSN it runs IDEMPOTENT provisioning SQL (the
provision-local-postgres.sh create-if-absent idiom) for the
read-only-by-construction ``cortex_ro`` role — LOGIN + NOINHERIT and NO other
attributes (never superuser/createdb/createrole), SELECT on EXACTLY
officer_tasks_outbox + officer_tasks and NOTHING else (every broader/default
privilege revoked so the grant catalog matches the enumerated §7.2 list
exactly) — then EXITS without rebuilding. Safe to re-run (harness/CI invoke it);
psycopg2 is lazy-imported and no secret is ever echoed.

Usage:
    cog2-rebuild.py --dsn <conninfo> [--cache-dir DIR] [--trust-table F] [--json]
    cog2-rebuild.py --dsn <conninfo> --past-null   # the frontier-past-NULL MUTANT
    cog2-rebuild.py --provision-ro --dsn <ADMIN conninfo>  # §7.2 cortex_ro (idempotent)

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

# §7.2 read-only-by-construction role (G-F6). The grant list is ENUMERATED and
# minimal — SELECT on these two tables ONLY (the parity falsifier's sample
# frame); test_cog2_fencing.py asserts the grant catalog matches this set
# EXACTLY. Fixed literals (no interpolation of any external value).
_RO_ROLE = "cortex_ro"
_RO_SELECT_TABLES = ("officer_tasks_outbox", "officer_tasks")


def provision_ro(dsn: str) -> None:
    """Idempotently provision the §7.2 read-only ``cortex_ro`` role (G-F6).

    ADMIN-side setup, NOT the shadow read path: the ``dsn`` is an ADMIN
    connection (it must be able to CREATE ROLE / GRANT). The SQL is idempotent
    — safe to run repeatedly (harness/CI drive it) — and mirrors
    provision-local-postgres.sh's create-if-absent role idiom (~L295): an
    existence-guarded CREATE, never a bare CREATE that errors on the second run.

    Guarantees the grant catalog is EXACTLY {SELECT on officer_tasks_outbox,
    SELECT on officer_tasks}: it REVOKEs every prior table/sequence privilege on
    cortex_ro first, then re-grants only the enumerated SELECTs, so a re-run
    converges to the same minimal catalog (no INSERT/UPDATE/DELETE/TRUNCATE, no
    sequence writes, no third table). The role is created LOGIN + NOINHERIT with
    no other attributes (a fresh role defaults to NOSUPERUSER/NOCREATEDB/
    NOCREATEROLE/NOREPLICATION/NOBYPASSRLS); the converge-ALTER re-asserts the
    safe subset every run.

    psycopg2 is lazy-imported in-function (the relay/rebuild precedent — the
    module top stays import-inert). No password/secret is ever echoed.
    """
    import psycopg2  # lazy (relay/rebuild precedent); module top stays import-inert

    stmts = [
        # create-if-absent (provision-local-postgres.sh idiom, ~L295): guarded
        # CREATE, never a bare CREATE ROLE that errors when the role already
        # exists. LOGIN + NOINHERIT, no other attribute — a fresh role is
        # NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS by
        # default, so it is a read-only login and nothing more.
        "DO $cortex_ro$ BEGIN "
        "  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cortex_ro') THEN "
        "    CREATE ROLE cortex_ro LOGIN NOINHERIT; "
        "  END IF; "
        "END $cortex_ro$;",
        # converge the safe, always-settable attributes every run — cortex_ro
        # can never create databases/roles or inherit member privileges even if
        # an out-of-band ALTER widened it (superuser/bypassrls are superuser-only
        # to change and are already off by construction on the CREATE above).
        "ALTER ROLE cortex_ro LOGIN NOINHERIT NOCREATEDB NOCREATEROLE;",
        # exact-catalog discipline: strip EVERY prior direct table/sequence
        # privilege so the catalog is EXACTLY the enumerated SELECTs after the
        # re-grant below (idempotent — a no-op on the first, clean run).
        "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM cortex_ro;",
        "REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM cortex_ro;",
        # schema USAGE is required to REACH objects; it is a SCHEMA privilege, so
        # it never appears in the role_table_grants catalog the §7.2 test pins.
        "GRANT USAGE ON SCHEMA public TO cortex_ro;",
    ]
    # the ENUMERATED, minimal grants — SELECT on the two tables and NOTHING else.
    stmts += [f"GRANT SELECT ON {tbl} TO cortex_ro;" for tbl in _RO_SELECT_TABLES]

    conn = psycopg2.connect(dsn)
    try:
        conn.autocommit = False           # one atomic transaction (all-or-nothing)
        with conn.cursor() as cur:
            for stmt in stmts:
                cur.execute(stmt)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
    parser.add_argument("--provision-ro", action="store_true",
                        help="§7.2/G-F6 ADMIN MODE: idempotently provision the "
                             "read-only cortex_ro role (SELECT on officer_tasks_outbox "
                             "+ officer_tasks only), then exit — no rebuild")
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

    if args.provision_ro:
        # §7.2/G-F6: run the idempotent read-only-role provisioning and EXIT
        # (no rebuild). Prints only role/table names — never the dsn or a secret.
        provision_ro(dsn)
        print(json.dumps({"provisioned_ro_role": _RO_ROLE,
                          "select_tables": list(_RO_SELECT_TABLES)},
                         sort_keys=True))
        return 0

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
