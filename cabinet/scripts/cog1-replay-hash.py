#!/usr/bin/env python3.12
"""cog1-replay-hash.py — deterministic replay hash over the officer_tasks outbox.

COG-1 (Cognitive Core Phase 1) §9.3 / M3 / sim 7. Two independent replays over
the SAME outbox state must produce a byte-identical SHA-256 — the mechanical
proof that the co-committed outbox row is a rebuildable projection substrate.

What is hashed — the IMMUTABLE CONTENT PROJECTION of officer_tasks_outbox rows,
ORDER BY id, exactly (in this order):

    id, idempotency_key, event_id, task_id, old_status, new_status,
    old_blocked, new_blocked, actor, context_slug, cabinet_id,
    correlation_id, causation_id, occurred_at, payload

Dispatch bookkeeping (claimed_at, attempts, dispatched_at, failed_terminal_at,
last_error) is EXCLUDED: it mutates on every redelivery, so a full-row hash
would spuriously fail under sim 7's redelivery churn. `blocked_reason` is
EXCLUDED because it travels inside `payload`; `destination` is EXCLUDED as
routing (constant 'stream' this phase), not content. Pre-dispatch rows
(event_id still NULL) are IN scope and hashed WITH the NULL — the §6.1 committed
backfill makes every dispatched row's event_id immutable thereafter.

Canonicalization is Phase-0 §3.3 verbatim (the SAME dialect, no second hashing
dialect): sorted keys (top-level AND nested payload), fixed-point integers, the
single UTC-second timestamp spelling (YYYY-MM-DDTHH:MM:SSZ), no clock, no
randomness. Rows are folded into a CHAINED SHA-256:

    acc = sha256(SEED); for row: acc = sha256(acc || canonical_json(row))

The ORDER BY id + the chain make the hash a function of the row SET and its
canonical order, invariant to input-row shuffle and to redelivery churn.

S0 ground (2026-07-20): the production work store is PostgreSQL 17.10, so the
harness/CI pin is MAJOR 17 (the plan text's "16" is superseded). The Postgres
driver import is LAZY inside the read path (module top stays stdlib-only —
house precedent: etl-common.py:20-23, intake.py:229) so this tool imports on a
driver-less box and the pure hashing core is testable with zero DB.

Usage:
    cog1-replay-hash.py --dsn <conninfo>        # prints the 64-char hex hash
    cog1-replay-hash.py --json                  # {"hash": "...", "rows": N}
    # dsn resolves: --dsn > COG1_OUTBOX_DSN > NEON_CONNECTION_STRING > DATABASE_URL

Provenance: authored per the 2026-07-07 full-autonomy grant (COG-1 §9.3).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Iterable

# The §9.3 immutable-content projection — EXACTLY these columns, in this order.
# (blocked_reason -> payload; destination -> routing; bookkeeping -> mutates.)
IMMUTABLE_CONTENT_COLUMNS: tuple[str, ...] = (
    "id", "idempotency_key", "event_id", "task_id",
    "old_status", "new_status", "old_blocked", "new_blocked",
    "actor", "context_slug", "cabinet_id", "correlation_id",
    "causation_id", "occurred_at", "payload",
)

# Domain-separation seed for the chain (keeps this hash distinct from any other
# SHA-256 stream over the same bytes). Frozen — changing it changes every hash.
_HASH_SEED = b"cog1-replay-hash/v1"

# The read SELECT: the projection, ORDER BY id. Table/column names are fixed
# literals (no interpolation). occurred_at is read raw and normalized in Python
# via _utc_second (ONE normalization path shared with the in-memory case).
_SELECT_SQL = (
    "SELECT " + ", ".join(IMMUTABLE_CONTENT_COLUMNS)
    + " FROM officer_tasks_outbox ORDER BY id"
)


def _utc_second(value: Any) -> str:
    """Coerce a datetime / ISO string to the single Phase-0 §3.3 UTC-second
    spelling YYYY-MM-DDTHH:MM:SSZ. IDENTICAL dialect to
    framework.outbox.relay._utc_second and the 047 capture DEFAULT — NOT a
    second dialect (cross-checked by test_utc_second_is_the_same_dialect_as_the
    _relay). None -> epoch-free empty guard is never hit for occurred_at (NOT
    NULL in 047), but we still normalize defensively."""
    if value is None:
        return ""
    if isinstance(value, str):
        s = value.strip()
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return s  # already-canonical or unparseable; hashed as-is
    else:
        dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def project_row(row: dict[str, Any]) -> dict[str, Any]:
    """Select the §9.3 immutable-content columns from a raw outbox row dict and
    normalize to JSON-native, canonical values. Bookkeeping / blocked_reason /
    destination are dropped by construction (not in IMMUTABLE_CONTENT_COLUMNS)."""
    out: dict[str, Any] = {}
    for col in IMMUTABLE_CONTENT_COLUMNS:
        val = row.get(col)
        if col in ("id", "task_id") and val is not None:
            val = int(val)                       # fixed-point integer
        elif col == "occurred_at":
            val = _utc_second(val)               # single UTC-second spelling
        out[col] = val
    return out


def canonical_row_json(projected: dict[str, Any]) -> str:
    """Phase-0 §3.3 canonical JSON for one projected row: sorted keys (top-level
    AND nested payload), compact separators, UTF-8 preserved. Deterministic —
    no clock, no randomness."""
    return json.dumps(projected, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=_json_default)


def _json_default(value: Any) -> Any:
    """Fail-loud on any type the projection should have normalized already — a
    silent str() would let a non-canonical value slip into the hash."""
    if isinstance(value, datetime):
        return _utc_second(value)
    raise TypeError(
        f"cog1-replay-hash: non-canonical value of type {type(value).__name__} "
        "in the projection (project_row must normalize it)")


def chained_hash(rows: Iterable[dict[str, Any]], *, order_by_id: bool = True) -> str:
    """The §9.3 chained SHA-256 over the projected rows. ORDER BY id is the
    canonical order (order_by_id=False is the sim-7 arrival-order MUTANT seam —
    a shuffle then changes the hash, which the gate detects)."""
    rows = list(rows)
    ordered = sorted(rows, key=lambda r: r["id"]) if order_by_id else rows
    acc = hashlib.sha256(_HASH_SEED).digest()
    for row in ordered:
        chunk = canonical_row_json(project_row(row)).encode("utf-8")
        acc = hashlib.sha256(acc + chunk).digest()
    return acc.hex()


def read_outbox_rows(dsn: str) -> list[dict[str, Any]]:
    """Read the immutable-content projection ORDER BY id. Lazy psycopg2 import
    (module top stays stdlib-only). Returns row dicts keyed by the projection
    columns (occurred_at is a datetime; payload is a dict — normalized by
    project_row at hash time)."""
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_SELECT_SQL)
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def hash_dsn(dsn: str) -> str:
    return chained_hash(read_outbox_rows(dsn))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic replay hash over officer_tasks_outbox (§9.3)")
    parser.add_argument("--dsn", default=None,
                        help="work-store DSN (else COG1_OUTBOX_DSN / "
                             "NEON_CONNECTION_STRING / DATABASE_URL)")
    parser.add_argument("--json", action="store_true",
                        help="emit {\"hash\":..., \"rows\":N} instead of the bare hash")
    args = parser.parse_args(argv)

    dsn = (args.dsn or os.environ.get("COG1_OUTBOX_DSN")
           or os.environ.get("NEON_CONNECTION_STRING")
           or os.environ.get("DATABASE_URL"))
    if not dsn:
        print("cog1-replay-hash: need --dsn or COG1_OUTBOX_DSN / "
              "NEON_CONNECTION_STRING", file=sys.stderr)
        return 2
    rows = read_outbox_rows(dsn)
    digest = chained_hash(rows)
    if args.json:
        print(json.dumps({"hash": digest, "rows": len(rows)}, sort_keys=True))
    else:
        print(digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
