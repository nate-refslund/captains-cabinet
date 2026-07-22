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
from framework.cortex.belief import canonical_bytes as _canonical, digest as _digest
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


def _is_tombstone(row: dict) -> bool:
    """A SOURCE-side tombstone (§5.4b, A-B3/C-F12): the outbox row's PAYLOAD
    content is purged (new_status NULL'd) while its identity columns (id,
    event_id, task_id, occurred_at, correlation_id, cabinet_id, idempotency_key)
    survive. In the live 047 schema new_status is NOT NULL, so a NULL new_status
    only ever arises post-purge; an explicit ``purged`` marker is also honored
    (the pure-path signal). The fold regenerates a source_purged stub — claim
    absent, identity + provenance intact (possible only because belief_id never
    embeds claim bytes, so identity survives the content loss)."""
    return bool(row.get("purged")) or row.get("new_status") is None


def _row_to_protos(row: dict) -> list[dict]:
    """One eligible outbox row -> [entity proto (ordinal 0), observation proto
    (ordinal 1)]. The v2 mapping is relay.build_dispatch_fields (drift-proof). A
    TOMBSTONED row (§5.4b) still yields BOTH protos — with the claim ABSENT and
    purged flagged — so the (claim-independent) belief_ids stay byte-stable and
    the source_purged stub replaces the live belief in place. build_dispatch_fields
    still resolves the surviving provenance (it reads only identity/scope columns,
    all of which survive a payload purge), so the universal provenance minimum is
    preserved on the stub."""
    # recorded_at is unused (axes degenerate); env["occurred_at"] is the
    # canonical UTC-second value the belief's two clocks both take.
    _flat, env = build_dispatch_fields(row, event_id=row["event_id"], recorded_at="")
    occ = env["occurred_at"]
    payload = env["payload"]
    subject = f"tasks/{int(row['task_id'])}"
    purged = _is_tombstone(row)

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
        proto = {
            "kind": kind,
            "subject_key": subject,
            "dimension": dimension,
            "adapter_ordinal": ordinal,
            "claim": None if purged else claim,
            "source_time": occ,
            "observation_time": occ,
            "provenance": dict(provenance),
            "claim_completeness": "purged" if purged else "inline",
        }
        if purged:
            proto["purged"] = True
        return proto

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


# ---------------------------------------------------------------------------
# Envelope-file adapter (§5.2a) — the COG-2 UNIT 2 two-axis + contradiction seam
# ---------------------------------------------------------------------------
#
# Production code (the general seam any future envelope-durable source uses),
# with NO production feed this phase (§2). It folds validate_any-gated v2
# envelope JSONL with INDEPENDENT occurred_at/recorded_at — the only real
# two-clock path in the slice (the outbox is single-clock). Sims 2 and 3 ride
# it, so their seeds traverse the SAME fold + query code as production streams
# (no test-only ingest seam — C-F4/C-F9).
#
# Derivation, pinned mechanically per adapter (never heuristic content
# comparison — §4):
#   * subject_key := "<payload_schema domain>/<payload.subject>" (a future
#     envelope-durable source declares a `subject` field — the analogue of the
#     outbox's tasks/<task_id>; namespaced away from the outbox by the domain)
#   * dimension  := the payload_schema "<domain>/<name>" ("payload_schema-
#     declared" — every envelope on one schema shares a supersession/contradict
#     dimension)
#   * kind       := "observation" (an envelope-file belief records an observation)
#   * source_time := occurred_at (valid time); observation_time := recorded_at
#     (transaction time — the SECOND axis)
#
# FAIL-CLOSED ingest (§7.4 / C-F19): every line is validate_any-gated AND
# cabinet-scoped; an invalid / absent-or-foreign-cabinet / payload_ref (no
# inline subject) / malformed-JSON line is QUARANTINED with a receipt — never
# silently skipped (silent skip is the pinned mutant failure). The full
# cross-cabinet suite (sentinels, classification=cross_cabinet, receipt-to-file)
# is the sim-7 unit; this adapter ships the fail-closed core.

_ENVELOPE_STREAM_RANK = RANK_TABLE["envelope_file"]  # 2
_ENVELOPE_SUBJECT_FIELD = "subject"
_ENVELOPE_KIND = "observation"


def _envelope_scope_reason(env: dict, *, local_cabinet_id: str) -> Optional[str]:
    """Fail-closed scope check on a validated envelope: a refusal reason, or None
    when local. Absent cabinet_id fails closed (absent is never local); a foreign
    cabinet_id is refused (§7.4)."""
    cab = env.get("cabinet_id")
    if not isinstance(cab, str) or not cab:
        return "absent cabinet_id (absent is never local — fail closed)"
    if cab != local_cabinet_id:
        return f"foreign cabinet_id {cab[:32]!r} (local is {local_cabinet_id[:32]!r})"
    return None


def _envelope_to_proto(env: dict, *, seq: int) -> dict:
    """One validated, in-scope, inline-payload v2 envelope -> one observation
    proto-belief. The two clocks are read straight off the envelope."""
    from framework.triggers import schema_registry  # lazy: module stays import-inert
    domain, name, _version = schema_registry.parse_schema_id(env["payload_schema"])
    provenance = {
        "event_id": env["event_id"],
        "producer": env["producer"],
        "stream_rank": _ENVELOPE_STREAM_RANK,
        "intra_stream_seq": seq,
        "cabinet_id": env["cabinet_id"],
        "scope_kind": env["scope_kind"],
        "correlation_id": env["correlation_id"],
        "classification": env["classification"],
        "payload_schema": env["payload_schema"],
        "idempotency_key": env["idempotency_key"],
    }
    if env.get("causation_id"):
        provenance["causation_id"] = env["causation_id"]
    for level in ("lane_id", "project_id"):
        if level in env:
            provenance[level] = env[level]
    return {
        "kind": _ENVELOPE_KIND,
        "subject_key": f"{domain}/{env['payload'][_ENVELOPE_SUBJECT_FIELD]}",
        "dimension": f"{domain}/{name}",
        "adapter_ordinal": 0,
        "claim": dict(env["payload"]),
        "source_time": env["occurred_at"],       # valid time
        "observation_time": env["recorded_at"],   # transaction time — the 2nd axis
        "provenance": provenance,
        "claim_completeness": "inline",
    }


def build_envelope_protos(envelopes, *, local_cabinet_id: str) -> tuple[list[dict], list[dict]]:
    """(protos, receipts) from ordered (line_index, parsed_envelope_or_None)
    pairs. FAIL-CLOSED: validate_any + scope fence + inline-payload gate; each
    refusal writes a receipt (never a silent skip). intra_stream_seq := the file
    line index (deterministic source order for supersession)."""
    from framework.triggers import envelope as _envelope  # lazy: import-inert top
    protos: list[dict] = []
    receipts: list[dict] = []

    def refuse(line_index, reason, event_id=None):
        receipts.append({"line": line_index, "reason": reason, "event_id": event_id})

    for line_index, env in envelopes:
        if not isinstance(env, dict):
            refuse(line_index, "line is not a JSON object (malformed or non-object)")
            continue
        ok, reasons = _envelope.validate_any(env)
        if not ok:
            refuse(line_index, "; ".join(reasons[:4]) or "invalid envelope",
                   env.get("event_id"))
            continue
        scope_reason = _envelope_scope_reason(env, local_cabinet_id=local_cabinet_id)
        if scope_reason is not None:
            refuse(line_index, scope_reason, env.get("event_id"))
            continue
        if "payload" not in env:
            # payload_ref: the fold never derefs, so no inline subject to key on.
            refuse(line_index, "payload_ref envelope: no inline subject "
                   "(deref is never done)", env.get("event_id"))
            continue
        payload = env["payload"]
        subject = (payload.get(_ENVELOPE_SUBJECT_FIELD)
                   if isinstance(payload, dict) else None)
        if not isinstance(subject, str) or not subject:
            # a VALIDATED envelope whose inline payload declares no pinned subject
            # (e.g. the platform's own tasks/task-event@1 relay shape) cannot key a
            # belief — refuse WITH A RECEIPT, never crash on the KeyError and abort
            # the whole file (the fail-closed contract above; §7.4 / C-F19).
            # Subject-declaring schemas (the `observations` seam) enforce it at
            # validate_any, so this gate only fires for other-schema envelopes.
            refuse(line_index, "inline payload declares no %r field — cannot key a "
                   "belief (fold quarantines, never derefs)" % _ENVELOPE_SUBJECT_FIELD,
                   env.get("event_id"))
            continue
        protos.append(_envelope_to_proto(env, seq=line_index))
    return protos, receipts


def read_envelope_file(path, *, local_cabinet_id: str) -> tuple[list[dict], list[dict]]:
    """Read a v2 envelope JSONL READ-ONLY and fold-prepare it (§5.2a). A
    malformed line is quarantined, never a crash. Returns (protos, receipts)."""
    import json
    from pathlib import Path
    envelopes = []
    for line_index, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
        if not raw.strip():
            continue
        try:
            envelopes.append((line_index, json.loads(raw)))
        except ValueError:
            envelopes.append((line_index, None))  # fail-closed: quarantined below
    return build_envelope_protos(envelopes, local_cabinet_id=local_cabinet_id)


# ---------------------------------------------------------------------------
# Consequence-ledger adapter (§3/§5.4) — the COG-2 UNIT 3 legacy SEAM
# ---------------------------------------------------------------------------
#
# The thin slice's ONE legacy adapter. It folds the append-only consequence
# ledger — read RAW via consequence.iter_ledger_rows() (the ONLY symbol imported
# from that module, reverse-import gate §7.1) — into observation beliefs on the
# `consequence` dimension. What it proves is the SEAM (§2/A-m12), NOT cross-time
# supersession: the ledger identity tuple is ts-INCLUSIVE, so the same
# (actor, action, subject) at two ts is TWO subjects and never supersedes by
# construction. Within ONE identity group an enrichment row (same tuple, later
# (file, line)) supersedes the original — the ONLY supersession here.
#
# DETERMINISTIC SYNTHETIC PROVENANCE (§5.4): a legacy row has no event_id, so the
# adapter mints one deterministically — digest("consequence:" + canonical row).
# The subject_key digests the ledger's OWN ts-inclusive identity tuple so an
# enrichment row shares the subject. LEGACY REGIME (A-M7): the row is not a v2
# envelope and is NEVER forced through validate_any; the belief it yields
# validates at the BELIEF level (universal provenance minimum + source_trust).

_CONSEQUENCE_STREAM_RANK = RANK_TABLE["consequence"]  # 1
_CONSEQUENCE_PRODUCER = "framework/fidelity/consequence"
_CONSEQUENCE_DIMENSION = "consequence"
_CONSEQUENCE_KIND = "observation"        # a consequence row records an observation


def _parse_ts_or_absent(value) -> Optional[str]:
    """Parse a ledger ts to the single canonical UTC-second spelling
    YYYY-MM-DDTHH:MM:SSZ, or return None (honest ABSENCE) for anything
    unparseable (C-F6). Unlike the cog1 _utc_second precedent it NEVER passes a
    garbage string through — a non-timestamp yields absence, never a value that
    would fence a query open."""
    from datetime import datetime, timezone
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _consequence_identity(row: dict) -> tuple:
    """The ledger's OWN ts-INCLUSIVE identity tuple (actor, action, subject, ts)
    — mirrors framework.fidelity.consequence._identity. The reverse-import gate
    (§7.1) admits ONLY iter_ledger_rows from that module, so the tuple is
    reconstructed inline; the seam-equivalence test (chain-heads ==
    read_ledger survivors) is the standing drift tripwire."""
    actor = row.get("actor")
    if isinstance(actor, dict):
        actor_id = f"{actor.get('kind')}:{actor.get('id')}"
    else:
        actor_id = f"{actor}:"           # defensive — non-dict actor never collides
    return (actor_id, row.get("action", ""), row.get("subject", ""), row.get("ts", ""))


def _consequence_row_to_proto(row: dict, seq: int) -> dict:
    """One consequence row -> one observation/consequence proto-belief with
    deterministic synthetic provenance. seq is the (file, line) enumeration index
    (source order) that orders the enrichment supersession chain."""
    identity = _consequence_identity(row)
    subject_key = f"{_CONSEQUENCE_DIMENSION}/{_digest(list(identity))}"
    # documented synthetic event_id: digest("consequence:" + canonical row bytes).
    event_id = _digest("consequence:" + _canonical(row).decode("utf-8"))
    ts = _parse_ts_or_absent(row.get("ts"))
    provenance = {
        "event_id": event_id,
        "producer": _CONSEQUENCE_PRODUCER,
        "stream_rank": _CONSEQUENCE_STREAM_RANK,
        "intra_stream_seq": seq,          # (file, line) order from iter_ledger_rows
    }
    return {
        "kind": _CONSEQUENCE_KIND,
        "subject_key": subject_key,
        "dimension": _CONSEQUENCE_DIMENSION,
        "adapter_ordinal": 0,
        "claim": dict(row),               # the surviving row == read_ledger survivor
        "source_time": ts,                # valid time (degenerate: ts, parse-or-absent)
        "observation_time": ts,           # transaction time (degenerate; C-F6)
        "provenance": provenance,
        "claim_completeness": "inline",
    }


def build_consequence_protos(ledger_rows) -> list[dict]:
    """Fold-prepare (file, line, row) triples from consequence.iter_ledger_rows()
    into proto-beliefs. intra_stream_seq = the enumeration index over the
    iterator's (file, line) order — a deterministic source order; within one
    identity group it orders the enrichment supersession chain (later == head)."""
    return [_consequence_row_to_proto(row, seq)
            for seq, (_file, _line, row) in enumerate(ledger_rows)]


def read_consequence_protos() -> list[dict]:
    """Read the consequence ledger via its OWN history-preserving reader
    (consequence.iter_ledger_rows — the ONLY symbol imported from that module,
    §7.1) and fold-prepare it. Lazy import keeps the module top import-inert."""
    from framework.fidelity.consequence import iter_ledger_rows
    return build_consequence_protos(iter_ledger_rows())
