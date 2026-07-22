"""Source adapters — source rows -> proto-beliefs (pre-fold).

COG-2 UNIT 1 (deterministic-rebuild core) ships ONE adapter: the tasks-outbox
adapter. The consequence and envelope-file adapters (§5.2a, §5.4) are later
COG-2 units. Plan: docs/plans/cognitive-core-phase-2-contract-2026-07-22.md §3
(reuse relay's pure row->v2 builder via allowlist — A-M8), §5.3 (frontier law +
repeatable-read snapshot), §5.4 (tasks supersession + dimensions).

A proto-belief is the near-final belief minus the cross-belief resolution the
fold owns (belief_id, claim_digest, confidence, source_trust, supersedes/
superseded_by/contradicts, status). The tasks adapter emits TWO per eligible
event: an ENTITY belief (dimension=status — the task's current status, which
supersedes across transitions) and an OBSERVATION belief (dimension=occurrence —
the transition observed). adapter_ordinal (0/1) distinguishes them.

DRIFT-PROOF (A-M8): the one row->v2 mapping is relay.build_dispatch_fields —
imported, never re-implemented. The belief's occurred_at is the canonical
UTC-second env["occurred_at"] the relay produces; recorded_at is unused here
(axes degenerate — observation_time := occurred_at, §4/A-B1).

SHADOW / READ-ONLY: reads Postgres under a read-only REPEATABLE READ snapshot
(psycopg2, lazy in-function import — relay/etl precedent); the SELECT is a fixed
literal carrying ORDER BY id (C-F4 physical-shuffle pin). No write path.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

from typing import Optional

# Allowlisted framework imports only (reverse-gate G-F1): own package + the
# relay's ONE pure builder. relay.build_dispatch_fields lazily imports
# framework.triggers.envelope; no authority/action module is reachable.
from framework.cortex.engine import RANK_TABLE, eligible_rows, frontier_of
from framework.outbox.relay import build_dispatch_fields

# The immutable-content projection needed to rebuild v2 + frontier, ORDER BY id
# (fixed literals — no interpolation; the ORDER BY is the C-F4 physical-shuffle
# determinism pin the gate string-checks). idempotency_key (047 DDL:
# `idempotency_key TEXT NOT NULL UNIQUE`) is fetched so it flows through
# build_dispatch_fields into provenance as the capture-stable secondary key
# (§5.3) — omitting it silently NULLed provenance.idempotency_key (F1).
_SELECT_SQL = (
    "SELECT id, idempotency_key, event_id, task_id, old_status, new_status, "
    "old_blocked, new_blocked, blocked_reason, actor, context_slug, cabinet_id, "
    "correlation_id, causation_id, occurred_at "
    "FROM officer_tasks_outbox ORDER BY id"
)

_STREAM_RANK = RANK_TABLE["officer_tasks_outbox"]  # 0


def read_outbox_rows(dsn: str) -> list[dict]:
    """Read the outbox under a READ-ONLY REPEATABLE READ snapshot (§5.3 A-M9).
    Lazy psycopg2 import (module top stays import-inert). ORDER BY id makes the
    read order stable under any physical/heap reordering."""
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(dsn)
    try:
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True,
                         autocommit=False)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_SELECT_SQL)
            rows = [dict(r) for r in cur.fetchall()]
        conn.rollback()  # read-only snapshot; close the transaction cleanly
        return rows
    finally:
        conn.close()


def _row_to_protos(row: dict) -> list[dict]:
    """One eligible outbox row -> [entity proto (ordinal 0), observation proto
    (ordinal 1)]. The v2 mapping is relay.build_dispatch_fields (drift-proof)."""
    # recorded_at is unused (axes degenerate); env["occurred_at"] is the
    # canonical UTC-second value the belief's two clocks both take.
    _flat, env = build_dispatch_fields(row, event_id=row["event_id"], recorded_at="")
    occ = env["occurred_at"]
    payload = env["payload"]
    subject = f"tasks/{int(row['task_id'])}"

    provenance = {
        "event_id": env["event_id"],
        "producer": env["producer"],
        "stream_rank": _STREAM_RANK,
        "intra_stream_seq": int(row["id"]),
        "cabinet_id": env.get("cabinet_id"),
        "scope_kind": env.get("scope_kind"),
        "correlation_id": env.get("correlation_id"),
        "classification": env.get("classification"),
        "payload_schema": env.get("payload_schema"),
        "idempotency_key": env.get("idempotency_key"),
    }
    if env.get("causation_id"):
        provenance["causation_id"] = env["causation_id"]

    def _proto(kind: str, dimension: str, ordinal: int, claim: dict) -> dict:
        return {
            "kind": kind,
            "subject_key": subject,
            "dimension": dimension,
            "adapter_ordinal": ordinal,
            "claim": claim,
            "source_time": occ,
            "observation_time": occ,
            "provenance": dict(provenance),
            "claim_completeness": "inline",
        }

    entity_claim = {"status": payload["new_status"], "blocked": payload["new_blocked"]}
    return [
        _proto("entity", "status", 0, entity_claim),
        _proto("observation", "occurrence", 1, dict(payload)),
    ]


def build_proto_beliefs(rows: list[dict], *, past_null: bool = False) -> list[dict]:
    """Apply the frontier law, then expand each eligible row to its protos."""
    protos: list[dict] = []
    for row in eligible_rows(rows, past_null=past_null):
        protos.extend(_row_to_protos(row))
    return protos


def read_and_build(dsn: str, *, past_null: bool = False) -> tuple[list[dict], Optional[int], Optional[int]]:
    """(proto_beliefs, frontier, max_id) from a live outbox DSN — the rebuild
    CLI entry. max_id/frontier feed the fold manifest's lag + blocker fields."""
    rows = read_outbox_rows(dsn)
    frontier = frontier_of(rows, past_null=past_null)
    max_id = max((int(r["id"]) for r in rows), default=None)
    return build_proto_beliefs(rows, past_null=past_null), frontier, max_id
