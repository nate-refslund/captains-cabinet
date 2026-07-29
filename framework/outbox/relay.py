"""Transactional outbox: durable cross-system writes.

Two drains live here, side by side (COG-1 §6 — never a second outbox):

LEGACY event-ledger drain (Phase 1.4). The classic transactional-outbox
pattern over the event ledger: queue() emits an `outbox_queued` event, the
relay replays those events, dispatches each to a registered adapter, and emits
`outbox_dispatched` / `outbox_failed`. Idempotency is replay-derived.

COG-1 TABLE drain (`--drain-tasks-outbox`, default OFF). Drains the co-committed
`officer_tasks_outbox` table for the tasks-domain pilot
(docs/plans/cognitive-core-phase-1-contract-2026-07-20.md §6). The dispatch
order per row is claim -> committed event_id -> effect -> record:

  1. claim a batch with FOR UPDATE SKIP LOCKED + a claim-TTL (concurrency-safe;
     TTL redelivery on relay death);
  2. backfill the ULID `event_id` in its OWN committed UPDATE, durable BEFORE
     any adapter effect, so redelivery re-emits the SAME id (replay-stable
     consumer dedupe key);
  3. build the v2 envelope (EFFECTIVE-status mapping), validate_v2 it, re-check
     cabinet_id (spoof backstop, terminal), then invoke the destination adapter
     carrying the idempotency token (stream adapter = redis-cli XADD, value-
     compatible with task_event_emit + a v2 envelope inside; its stream target
     defaults to SHADOW cabinet:tasks:events:shadow and is retargeted to the LIVE
     cabinet:tasks:events ONLY when the wrapper passes it down at cutover, §8.4);
  4. record dispatched_at. The table drain emits ZERO central-ledger events
     (§7 fence) — its only telemetry is the parity JSONL.

Terminal is VALIDATION-CLASS ONLY (invalid envelope, unresolvable schema, over
bound, cabinet spoof, unknown destination) and quarantines only past the
attempt cap; transport-class failures (redis/network) retry UNBOUNDED and are
NEVER terminal (a partition must not repeal M1). Per-row isolation: one row's
failure never aborts the batch.

S0 pin: the production work store is PostgreSQL 17.10, so the harness/CI pin is
MAJOR 17 (the plan text's "16" is superseded). The Postgres driver import is
LAZY inside the drain path (house precedent: etl-common.py:20-23 lazy psycopg2,
intake.py:229 lazy redis) so the module top stays stdlib-only and collection in
driver-less jobs never breaks (§9.4).

Usage:
    from framework.outbox.relay import queue, dispatch_pending, register_adapter

    qid = queue(destination="<sink>", payload={...}, actor="<role>")
    result = dispatch_pending()           # legacy: {"dispatched","failed","skipped"}

    # COG-1 table drain (cron / launchd); the host identity resolves from the
    # CABINET_ID env or the DB-level app.cabinet_id GUC — never a tracked literal:
    counts = drain_tasks_outbox(dsn)

Provenance: COG-1 relay-plane extension authored per the 2026-07-07
full-autonomy grant.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.events.emitter import emit, replay

# The positive marker queue() stamps; the legacy drain processes ONLY
# marker-bearing rows (§6.2, §7) so task_sync's historical adapter-less
# outbox_queued rows are mechanically neutralized (never drained).
QUEUED_BY_MARKER = "framework.outbox.relay"


# ---------------------------------------------------------------------------
# Adapter registry (LEGACY event-ledger drain)
# ---------------------------------------------------------------------------

AdapterFn = Callable[[dict[str, Any]], None]

# Phase 1.4 ships with a stub adapter only. Phase 5 wires real adapters
# for Monday, Jira, Linear, Asana, GitHub Issues, Notion.
_ADAPTERS: dict[str, AdapterFn] = {}


def register_adapter(destination: str, fn: AdapterFn) -> None:
    """Register a LEGACY adapter for a destination.

    The adapter takes the payload dict and either returns normally (success)
    or raises an exception (failure → relay emits outbox_failed and retries
    on the next cycle).
    """
    _ADAPTERS[destination] = fn


def _stub_adapter(payload: dict[str, Any]) -> None:
    """Default no-op adapter used in tests + as a sentinel until Phase 5."""
    return None


register_adapter("stub", _stub_adapter)


# ---------------------------------------------------------------------------
# Queue API (callers) — §6.2 flock + queued_by marker
# ---------------------------------------------------------------------------


def _queue_lock_path() -> Path:
    """The queue() flock file, colocated with the event ledger (per-sandbox —
    never a shared global that would serialize unrelated runs)."""
    from framework.events.emitter import _event_log_dir
    return _event_log_dir() / ".outbox-queue.lock"


@contextlib.contextmanager
def _queue_lock():
    """Exclusive flock spanning queue()'s dedupe-scan + emit (§6.2 — the
    legacy check-then-emit race fix for the single-host path; the pilot
    path's real fix is the SQL UNIQUE key)."""
    path = _queue_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            f.close()


def queue(
    destination: str,
    payload: dict[str, Any],
    actor: str = "system",
    idempotency_key: str | None = None,
) -> str:
    """Queue a cross-system write to the outbox event log.

    Stamps `payload["queued_by"]` so the legacy drain can fence out foreign
    outbox_* writers (§6.2). Scan+emit run under a module flock.

    Returns the event id of the outbox_queued event (or the prior one if
    deduped by idempotency_key).
    """
    with _queue_lock():
        if idempotency_key is not None:
            # Look for a previously queued event with the same key
            for ev in replay(event_types=["outbox_queued"]):
                p = ev.get("payload") or {}
                if p.get("idempotency_key") == idempotency_key:
                    return ev["id"]

        event = emit(
            "outbox_queued",
            actor=actor,
            payload={
                "destination": destination,
                "payload": payload,
                "idempotency_key": idempotency_key,
                "queued_by": QUEUED_BY_MARKER,
            },
        )
        return event["id"]


# ---------------------------------------------------------------------------
# Relay (LEGACY dispatcher)
# ---------------------------------------------------------------------------


def _already_processed_ids() -> set[str]:
    """Set of outbox_queued event ids already terminal-dispatched.

    Terminal = either outbox_dispatched (success) OR outbox_failed with
    `terminal=True` in the payload (permanent failure, give up).
    Transient outbox_failed events (terminal=False or absent) are retryable
    and DO NOT count as processed.
    """
    processed: set[str] = set()
    for ev in replay(event_types=["outbox_dispatched"]):
        qid = (ev.get("payload") or {}).get("queued_event_id")
        if qid:
            processed.add(qid)
    for ev in replay(event_types=["outbox_failed"]):
        p = ev.get("payload") or {}
        if p.get("terminal") is True:
            qid = p.get("queued_event_id")
            if qid:
                processed.add(qid)
    return processed


def _is_marker_row(ev: dict[str, Any]) -> bool:
    return (ev.get("payload") or {}).get("queued_by") == QUEUED_BY_MARKER


def _pending_queue() -> list[dict[str, Any]]:
    """Marker-bearing outbox_queued events not yet terminal-dispatched, oldest
    first. Non-marker (foreign) rows are fenced out (§6.2/§7)."""
    queued = replay(event_types=["outbox_queued"])
    processed = _already_processed_ids()
    return [ev for ev in queued
            if ev["id"] not in processed and _is_marker_row(ev)]


def _foreign_ledger_rows() -> list[dict[str, Any]]:
    """Non-marker outbox_queued events the legacy drain SKIPS (§7 counted
    foreign-rows telemetry — task_sync_runner cycle telemetry, orphan rows).
    Never dispatched, never terminal-failed: simply never drained."""
    queued = replay(event_types=["outbox_queued"])
    processed = _already_processed_ids()
    return [ev for ev in queued
            if ev["id"] not in processed and not _is_marker_row(ev)]


def dispatch_one(
    queued_event: dict[str, Any],
    actor: str = "outbox_relay",
) -> str:
    """Dispatch a single outbox_queued event.

    Returns the outcome literal: 'dispatched', 'failed', or 'skipped'.
    Emits the corresponding terminal event.
    """
    qid = queued_event["id"]
    p = queued_event.get("payload") or {}
    destination = p.get("destination")
    payload = p.get("payload") or {}

    adapter = _ADAPTERS.get(destination) if destination else None
    if adapter is None:
        # Unknown destination → terminal failure so we don't loop forever
        # on a misconfigured queue entry.
        emit(
            "outbox_failed",
            actor=actor,
            payload={
                "queued_event_id": qid,
                "destination": destination,
                "error": f"no adapter registered for destination: {destination}",
                "terminal": True,
            },
            parent_id=qid,
        )
        return "skipped"

    try:
        adapter(payload)
    except Exception as e:  # noqa: BLE001 — adapter contract is exception-on-failure
        emit(
            "outbox_failed",
            actor=actor,
            payload={
                "queued_event_id": qid,
                "destination": destination,
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc().splitlines()[-3:],
                "terminal": False,  # retryable next cycle
            },
            parent_id=qid,
        )
        return "failed"

    emit(
        "outbox_dispatched",
        actor=actor,
        payload={
            "queued_event_id": qid,
            "destination": destination,
        },
        parent_id=qid,
    )
    return "dispatched"


def dispatch_pending(actor: str = "outbox_relay") -> dict[str, int]:
    """Dispatch every currently-pending (marker-bearing) outbox entry.

    Returns the FROZEN three-key contract {"dispatched","failed","skipped"}.
    Foreign-row telemetry rides `_foreign_ledger_rows()`, NEVER this dict —
    presets/*/measurement/role_evals/coo_outbox_*.py assert the exact shape.
    """
    counts = {"dispatched": 0, "failed": 0, "skipped": 0}
    for queued in _pending_queue():
        outcome = dispatch_one(queued, actor=actor)
        counts[outcome] += 1
    return counts


# ===========================================================================
# COG-1 table drain — officer_tasks_outbox (§6.1)
# ===========================================================================

SHADOW_STREAM = "cabinet:tasks:events:shadow"

# COG-1 F1 live-stream retarget seam (§8.4). The LIVE tasks exhaust — and the
# landing-marker TOKEN the cog1-authority-flip.sh interlock probes for: its
# presence in this module self-releases the fail-closed cutover interlock.
# SHADOW stays the HARD DEFAULT everywhere. LAYER LAW: the framework relay NEVER
# reads the authority pointer file — the cron WRAPPER (cabinet/cron/
# outbox-relay.sh) resolves the pointer VALUE and passes this target DOWN only
# at cutover (pointer=outbox). Anything else -> SHADOW. This is a stream-name
# literal, never the pointer path.
COG1_LIVE_STREAM_TARGET = "cabinet:tasks:events"

MAX_ATTEMPTS = 5
DEFAULT_CLAIM_TTL_SECONDS = 120
DEFAULT_BATCH = 100

# v2 envelope constants for the tasks pilot (§4.2, §6.1).
TASKS_EVENT_TYPE = "tasks.status_changed"      # declared by tasks/task-event@1
TASKS_PAYLOAD_SCHEMA = "tasks/task-event@1"
V2_PRODUCER = "officer_tasks/outbox-relay"
V2_CLASSIFICATION = "officer"                  # DATA ONLY (v1 taint tier; no join law)
V2_SCOPE_KIND = "cabinet"                      # pilot events are cabinet-scope

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # ULID Crockford base32 (no I,L,O,U)


class RelayValidationError(Exception):
    """A validation-class failure — deterministic poison. Terminal-eligible
    (quarantined past the attempt cap): invalid v2 build, unresolvable schema,
    over-bound payload, cabinet spoof (backstop), unknown destination."""


class RelayTransportError(Exception):
    """A transport-class failure — redis/network/adapter transport. NEVER
    terminal (retried unbounded); a partition must not repeal M1 (§6.1)."""


class RelayPreflightError(RuntimeError):
    """The drain cannot even start (unresolvable cabinet identity, etc.)."""


class _RelayCrash(BaseException):
    """Test-only simulated relay death. A BaseException so the per-row
    isolation guard (`except Exception`) does NOT catch it — a real crash is
    uncaught, leaving committed work committed and the open txn rolled back on
    connection close. Never raised by any production path."""


def _mint_ulid() -> str:
    """A ULID (48-bit ms timestamp + 80-bit randomness, Crockford base32) —
    matches envelope.ULID_RE, the exact minting the legacy task_event_emit
    uses (triggers.sh)."""
    ms = int(time.time() * 1000) & ((1 << 48) - 1)
    n = (ms << 80) | int.from_bytes(os.urandom(10), "big")
    return "".join(_CROCKFORD[(n >> (5 * i)) & 31] for i in range(25, -1, -1))


# ---------------------------------------------------------------------------
# EFFECTIVE-status mapping (§6.1 step 3) — legacy vocabulary is effective
# status, not the raw columns
# ---------------------------------------------------------------------------

def effective_old_status(old_status: Any, old_blocked: Any) -> str:
    """old_blocked=TRUE → 'blocked'; INSERT-arm NULL old_status → ''."""
    if old_blocked is True:
        return "blocked"
    if old_status is None:
        return ""
    return old_status


def effective_new_status(new_status: Any, new_blocked: Any) -> str:
    """new_blocked=TRUE → 'blocked'."""
    if new_blocked is True:
        return "blocked"
    return new_status


def _utc_second(value: Any) -> str:
    """Coerce a datetime / ISO string to the single Phase-0 §3.3 UTC-second
    spelling YYYY-MM-DDTHH:MM:SSZ. None → now."""
    from datetime import datetime, timezone
    if value is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, str):
        s = value.strip()
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return s  # best effort; validate_v2 judges it
    else:
        dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_dispatch_fields(row: dict, *, event_id: str,
                          recorded_at: str) -> tuple[dict, dict]:
    """Build (flat_fields, v2_envelope) for one outbox row.

    flat_fields is the task_event_emit-shaped XADD payload
    {envelope, task_id, old_status, new_status, actor, context_slug, ts} — the
    old_status/new_status are EFFECTIVE-mapped so the consumer's only rule
    (new_status=='blocked') keeps firing. The envelope INSIDE is v2 (§4.2).
    occurred_at = mutation time (row.occurred_at); recorded_at = relay emission
    time (occurred_at ≤ recorded_at is DESCRIPTIVE, never validated — §4.2).
    """
    from framework.triggers import envelope

    old_eff = effective_old_status(row.get("old_status"), row.get("old_blocked"))
    new_eff = effective_new_status(row.get("new_status"), row.get("new_blocked"))
    occurred_at = _utc_second(row.get("occurred_at"))

    inner_payload = {
        "task_id": int(row["task_id"]),
        "old_status": old_eff,
        "new_status": new_eff,
        "old_blocked": row.get("old_blocked"),
        "new_blocked": row.get("new_blocked"),
        "blocked_reason": row.get("blocked_reason"),
        "actor": row.get("actor"),
        "context_slug": row.get("context_slug"),
    }
    env = {
        "schema_version": envelope.V2_SCHEMA_VERSION,
        "event_id": event_id,
        "event_type": TASKS_EVENT_TYPE,
        "occurred_at": occurred_at,
        "recorded_at": recorded_at,
        "cabinet_id": row.get("cabinet_id"),
        "scope_kind": V2_SCOPE_KIND,
        "producer": V2_PRODUCER,
        "correlation_id": row.get("correlation_id"),
        "idempotency_key": row.get("idempotency_key"),
        "classification": V2_CLASSIFICATION,
        "payload_schema": TASKS_PAYLOAD_SCHEMA,
        "payload": inner_payload,
    }
    causation = row.get("causation_id")
    if causation:  # pilot rows are roots; carry it only if a real cause exists
        env["causation_id"] = causation

    flat = {
        "envelope": json.dumps(env, ensure_ascii=False, sort_keys=True),
        "task_id": str(row["task_id"]),
        "old_status": old_eff,
        "new_status": new_eff,
        "actor": row.get("actor") or "",
        "context_slug": row.get("context_slug") or "",
        "ts": recorded_at,
    }
    return flat, env


# ---------------------------------------------------------------------------
# Table adapters (destination handlers for the table drain)
# ---------------------------------------------------------------------------

# fn(fields: dict, *, idempotency_key: str) -> None. The invocation carries the
# idempotency token (§6.1): the stream adapter dedupes at the consumer via the
# envelope's event_id; an external adapter upserts by canonical_id (C2).
TableAdapterFn = Callable[..., None]
_TABLE_ADAPTERS: dict[str, TableAdapterFn] = {}


def register_table_adapter(destination: str, fn: TableAdapterFn) -> None:
    """The sanctioned framework-side seam for table-drain destinations (§9.2 —
    the harness registers its counting UPSERT adapter here). Sibling of
    register_adapter(); a separate registry because the table contract carries
    the idempotency token, which the legacy (payload)->None signature omits."""
    _TABLE_ADAPTERS[destination] = fn


def _stream_adapter(fields: dict, *, idempotency_key: str,
                    stream_target: str = SHADOW_STREAM) -> None:
    """XADD to `stream_target` via a redis-cli argv subprocess (the exact client
    task_event_emit uses; no shell, fixed argv). Value-compatible with
    task_event_emit; the v2 envelope rides the `envelope` field. `stream_target`
    defaults to the SHADOW stream (dark by construction) — the retarget to
    COG1_LIVE_STREAM_TARGET is passed DOWN by the wrapper at cutover (§8.4); the
    relay never reads the pointer. Redis failure → RelayTransportError (transport
    class: retried, never terminal)."""
    host = os.environ.get("REDIS_HOST", "127.0.0.1")
    port = os.environ.get("REDIS_PORT", "6379")
    argv = ["redis-cli", "-h", host, "-p", str(port), "XADD", stream_target, "*"]
    for key in ("envelope", "task_id", "old_status", "new_status",
                "actor", "context_slug", "ts"):
        argv += [key, str(fields.get(key, ""))]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        raise RelayTransportError(f"redis-cli XADD could not run: {e}") from e
    if r.returncode != 0 or r.stderr.strip():
        raise RelayTransportError(
            f"XADD to {stream_target} failed: {r.stderr.strip() or 'redis unreachable'}")
    if not re.match(r"^\d+-\d+$", r.stdout.strip()):
        raise RelayTransportError(
            f"XADD to {stream_target} returned no entry id: {r.stdout.strip()[:80]!r}")


register_table_adapter("stream", _stream_adapter)


def _resolve_stream_adapter(stream_target: str) -> TableAdapterFn:
    """Bind a resolved stream target into the stream adapter (§8.4 seam). The
    cron WRAPPER resolves the authority pointer VALUE and passes `stream_target`
    down; the relay NEVER reads the pointer file (LAYER LAW). SHADOW is the hard
    default; only pointer=outbox yields COG1_LIVE_STREAM_TARGET. A distinct
    module-level seam so a routing rig can monkeypatch it to prove the target
    plumbing has teeth (the shadow-stuck mutant)."""
    def bound(fields: dict, *, idempotency_key: str) -> None:
        _stream_adapter(fields, idempotency_key=idempotency_key,
                        stream_target=stream_target)
    return bound


# ---------------------------------------------------------------------------
# Drain internals (module-level seams so gates can inject their mutant)
# ---------------------------------------------------------------------------

def _db_identity(conn) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT current_setting('app.cabinet_id', TRUE)")
        v = cur.fetchone()[0]
    return v or None


def _claim_rows(conn, batch: int, claim_ttl_seconds: float) -> list[dict]:
    """Claim a batch: one UPDATE with FOR UPDATE SKIP LOCKED + a claim-TTL
    (concurrency-safe; TTL redelivery on relay death). Values are bound
    parameters; table/column names are fixed literals (no interpolation)."""
    import psycopg2.extras
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "UPDATE officer_tasks_outbox SET claimed_at=NOW(), attempts=attempts+1 "
            "WHERE id IN (SELECT id FROM officer_tasks_outbox "
            "  WHERE dispatched_at IS NULL AND failed_terminal_at IS NULL "
            "  AND (claimed_at IS NULL OR claimed_at < NOW() - %s * INTERVAL '1 second') "
            "  ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED) RETURNING *",
            (claim_ttl_seconds, batch))
        rows = [dict(r) for r in cur.fetchall()]
    conn.commit()
    return rows


def _backfill_event_id(conn, row: dict, fault_hook=None) -> str:
    """Backfill the ULID event_id in its OWN committed UPDATE, durable BEFORE
    any adapter effect (§6.1 step 2). WHERE event_id IS NULL makes redelivery
    a no-op, so the id is stable across crashes; the re-SELECT reads the
    committed value (reuse is explicit)."""
    fh = fault_hook or (lambda p: None)
    if row.get("event_id"):
        return row["event_id"]
    new_id = _mint_ulid()
    with conn.cursor() as cur:
        cur.execute("UPDATE officer_tasks_outbox SET event_id=%s "
                    "WHERE id=%s AND event_id IS NULL", (new_id, row["id"]))
    fh("before_backfill_commit")
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT event_id FROM officer_tasks_outbox WHERE id=%s",
                    (row["id"],))
        committed = cur.fetchone()[0]
    conn.commit()
    row["event_id"] = committed
    return committed


def _cabinet_backstop(row: dict, host_id: str) -> None:
    """Dispatch-time spoof BACKSTOP (§5.2): a row whose cabinet_id diverges
    from the host-configured identity is terminal (validation class). The
    capture trigger is the PRIMARY enforcement; this catches cross-database
    misconfiguration / hand-planted rows."""
    if row.get("cabinet_id") != host_id:
        raise RelayValidationError(
            f"cabinet_id backstop: row cabinet_id {row.get('cabinet_id')!r} "
            f"!= host identity {host_id!r}")


def _classify_failure(exc: BaseException) -> str:
    """'validation' (terminal-eligible) or 'transport' (never terminal).
    Unclassified errors default to TRANSPORT — fail-safe: never convert an
    acknowledged mutation into a quarantine over an unknown error (M1)."""
    if isinstance(exc, RelayValidationError):
        return "validation"
    if isinstance(exc, RelayTransportError):
        return "transport"
    return "transport"


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


class _DrainCtx:
    __slots__ = ("host_id", "adapters", "fault_hook", "max_attempts")

    def __init__(self, host_id, adapters, fault_hook, max_attempts):
        self.host_id = host_id
        self.adapters = adapters
        self.fault_hook = fault_hook or (lambda p: None)
        self.max_attempts = max_attempts


def _process_row(conn, row: dict, ctx: _DrainCtx) -> None:
    """One row: committed-id -> effect -> record. Raises RelayValidationError /
    RelayTransportError on failure (the caller isolates + classifies)."""
    fh = ctx.fault_hook

    # 2. committed id (durable before any effect)
    event_id = _backfill_event_id(conn, row, fault_hook=fh)
    fh("after_backfill_commit")

    # 3. effect: build + validate_v2 -> cabinet backstop -> adapter (with token)
    from framework.triggers import envelope
    flat, env = build_dispatch_fields(row, event_id=event_id,
                                      recorded_at=_utc_second(None))
    ok, reasons = envelope.validate_v2(env)
    if not ok:
        raise RelayValidationError("invalid v2 envelope: " + "; ".join(reasons[:4]))
    _cabinet_backstop(row, ctx.host_id)
    destination = row.get("destination") or "stream"
    adapter = ctx.adapters.get(destination)
    if adapter is None:
        raise RelayValidationError(f"unknown destination: {destination!r}")
    fh("before_effect")
    adapter(flat, idempotency_key=row["idempotency_key"])
    fh("after_effect")

    # 4. record
    with conn.cursor() as cur:
        cur.execute("UPDATE officer_tasks_outbox SET dispatched_at=NOW() WHERE id=%s",
                    (row["id"],))
    conn.commit()


def _mark_failure(conn, row: dict, cls: str, err: str, max_attempts: int) -> bool:
    """Record a per-row failure. Terminal ONLY when a validation-class error
    has driven attempts past the cap; transport-class NEVER terminal (§6.1)."""
    try:
        conn.rollback()  # clear any aborted txn left by the failed step
    except Exception:
        pass
    attempts = int(row.get("attempts") or 0)
    terminal = (cls == "validation" and attempts > max_attempts)
    msg = f"[{cls}] {err}"[:500]
    with conn.cursor() as cur:
        if terminal:
            cur.execute("UPDATE officer_tasks_outbox "
                        "SET failed_terminal_at=NOW(), last_error=%s WHERE id=%s",
                        (msg, row["id"]))
        else:
            cur.execute("UPDATE officer_tasks_outbox SET last_error=%s WHERE id=%s",
                        (msg, row["id"]))
    conn.commit()
    return terminal


def _safe_process(conn, row: dict, ctx: _DrainCtx, counts: dict) -> None:
    """Per-row isolation wrapper: one row's failure never aborts the batch.
    `_RelayCrash` (a BaseException) is NOT caught — a real crash is uncaught."""
    try:
        _process_row(conn, row, ctx)
        counts["dispatched"] += 1
    except Exception as e:  # noqa: BLE001 — per-row isolation
        cls = _classify_failure(e)
        terminal = _mark_failure(conn, row, cls, _describe(e), ctx.max_attempts)
        counts["terminal" if terminal else "transient"] += 1


def _append_parity_sample(path, counts: dict) -> None:
    """Append one per-cycle parity sample to the JSONL (§6.1 step 4 / §8.3 —
    every line carries its cycle's sample count for the freshness floor). The
    full asymmetric parity predicate + the falsifier reader are OTHER waves;
    the relay only WRITES the log."""
    from datetime import datetime, timezone
    sample = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "samples": counts.get("claimed", 0),
        "dispatched": counts.get("dispatched", 0),
        "terminal": counts.get("terminal", 0),
        "transient": counts.get("transient", 0),
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(sample, sort_keys=True) + "\n")


def drain_tasks_outbox(
    dsn: str,
    *,
    batch: int = DEFAULT_BATCH,
    claim_ttl_seconds: float = DEFAULT_CLAIM_TTL_SECONDS,
    max_attempts: int = MAX_ATTEMPTS,
    cabinet_id: str | None = None,
    stream_target: str = SHADOW_STREAM,
    parity_log: Any = None,
    fault_hook=None,
    adapters: dict | None = None,
) -> dict:
    """Drain one batch of officer_tasks_outbox (§6.1). Returns cycle telemetry
    {"claimed","dispatched","terminal","transient"}.

    The Postgres driver import is LAZY here (module top stays stdlib-only —
    §9.4). Host identity for the spoof backstop resolves as cabinet_id arg →
    env CABINET_ID → the DB-level app.cabinet_id GUC; unresolvable → fail loud
    (never dispatch unattributable rows).

    `stream_target` (§8.4 seam): the stream the default adapter XADDs to; SHADOW
    is the HARD DEFAULT (see COG1_LIVE_STREAM_TARGET). A caller `adapters` dict
    is used as-is."""
    import psycopg2  # LAZY (etl-common.py:20-23 / intake.py:229 precedent)

    counts = {"claimed": 0, "dispatched": 0, "terminal": 0, "transient": 0}
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    try:
        host_id = cabinet_id or os.environ.get("CABINET_ID") or _db_identity(conn)
        if not host_id:
            raise RelayPreflightError(
                "relay cannot resolve the cabinet identity (pass cabinet_id, set "
                "CABINET_ID, or provision app.cabinet_id on the work store)")
        if adapters is None:
            # Default (production) path: bind the resolved stream target into the
            # stream adapter. The WRAPPER passed it down (§8.4); SHADOW is the
            # hard default. A caller/harness `adapters` dict is used as-is.
            adapters = dict(_TABLE_ADAPTERS)
            adapters["stream"] = _resolve_stream_adapter(stream_target)

        rows = _claim_rows(conn, batch, claim_ttl_seconds)
        counts["claimed"] = len(rows)
        (fault_hook or (lambda p: None))("after_claim")

        ctx = _DrainCtx(host_id, adapters, fault_hook, max_attempts)
        for row in rows:
            _safe_process(conn, row, ctx, counts)

        if parity_log:
            _append_parity_sample(parity_log, counts)
        return counts
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CLI (used by cabinet/cron/outbox-relay.sh)
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Outbox relay — dispatch pending cross-system writes."
    )
    parser.add_argument("--json", action="store_true", help="Print summary as JSON")
    parser.add_argument("--list-pending", action="store_true",
                        help="Print pending outbox entries (no dispatch)")
    # COG-1 table drain (default OFF; the cron wrapper enables it only after
    # the arming step + a fail-loud preflight, §8.2).
    parser.add_argument("--drain-tasks-outbox", action="store_true",
                        help="COG-1: drain the officer_tasks_outbox table (§6.1)")
    parser.add_argument("--dsn", default=None,
                        help="work-store DSN for --drain-tasks-outbox")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH)
    parser.add_argument("--claim-ttl", type=float, default=DEFAULT_CLAIM_TTL_SECONDS)
    parser.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS)
    parser.add_argument("--cabinet-id", default=None)
    parser.add_argument("--stream-target", default=SHADOW_STREAM,
                        help="COG-1 §8.4: stream the table drain XADDs to; the cron "
                             "wrapper resolves it from the pointer, relay never reads it. Default: SHADOW.")
    parser.add_argument("--parity-log", default=None)
    args = parser.parse_args(argv)

    if args.drain_tasks_outbox:
        dsn = (args.dsn or os.environ.get("COG1_OUTBOX_DSN")
               or os.environ.get("NEON_CONNECTION_STRING")
               or os.environ.get("DATABASE_URL"))
        if not dsn:
            print("outbox-relay: --drain-tasks-outbox needs --dsn or "
                  "COG1_OUTBOX_DSN / NEON_CONNECTION_STRING", file=sys.stderr)
            return 2
        # §8.3 default parity log (gitignored via cabinet/logs/*); env/flag
        # override for the harness. The relay only WRITES the log — the
        # asymmetric parity predicate + the falsifier reader are other waves.
        default_parity = str(Path(os.environ.get("CABINET_ROOT", _FRAMEWORK_ROOT))
                             / "cabinet" / "logs" / "cog1-parity.jsonl")
        parity_log = (args.parity_log
                      or os.environ.get("CABINET_COG1_PARITY_LOG")
                      or default_parity)
        counts = drain_tasks_outbox(
            dsn, batch=args.batch, claim_ttl_seconds=args.claim_ttl,
            max_attempts=args.max_attempts, cabinet_id=args.cabinet_id,
            stream_target=args.stream_target, parity_log=parity_log)
        if args.json:
            print(json.dumps(counts))
        else:
            print(f"outbox-relay(table): claimed={counts['claimed']} "
                  f"dispatched={counts['dispatched']} terminal={counts['terminal']} "
                  f"transient={counts['transient']}")
        return 0

    if args.list_pending:
        pending = _pending_queue()
        if args.json:
            print(json.dumps([{
                "id": ev["id"],
                "destination": (ev.get("payload") or {}).get("destination"),
                "actor": ev["actor"],
                "created_at": ev["created_at"],
            } for ev in pending]))
        else:
            for ev in pending:
                p = ev.get("payload") or {}
                print(f"  {ev['id'][:8]}  → {p.get('destination')}  ({ev['actor']}, {ev['created_at']})")
            print(f"outbox: {len(pending)} pending, "
                  f"{len(_foreign_ledger_rows())} foreign_rows (fenced)")
        return 0

    counts = dispatch_pending()
    foreign = len(_foreign_ledger_rows())
    if args.json:
        print(json.dumps(counts))
    else:
        print(f"outbox-relay: dispatched={counts['dispatched']} "
              f"failed={counts['failed']} skipped={counts['skipped']} "
              f"foreign_rows={foreign}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
