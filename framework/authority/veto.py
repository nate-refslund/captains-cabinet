"""Deferred-send veto window for internal comms — block-then-redirect [FIX-3].

Component 5 of docs/authority-matrix-design-2026-06-19.md. When the authority
gate resolves an internal-comms action to `auto_with_veto_window`, the officer's
direct send is BLOCKED (the gate exits 2) and the payload is ENQUEUED here. The
Captain gets a Telegram notice ("sending to <person> in N min — reply `kill <id>` to
stop"); if he does nothing, an out-of-band scan fires the ACTUAL send on TTL
expiry through the SAME approved `queue_draft` backend (brain-bridge.md:
`queue_draft` is the ONLY outbound path). If he kills it, the entry is deleted
before it can send.

This module is intentionally tiny and side-effect-free in itself: a queue
producer, a notifier (composes a string — never sends), a kill handler, and a
scan-sender. Every external dependency — Redis, the clock, the send backend,
and the event emitter — is INJECTED so the whole thing is unit-testable with
fakes (no real Redis, no real time, no real outbound, no real event ledger).

It implements NO new send path: the real byte egress is the caller-supplied
`send_backend` (the existing approved `queue_draft` backend in the Captain's external
screenpipe brain-mcp). It touches no `queue_draft` internals.

Crash-safety + idempotency are the spine:
  * the stream entry survives officer/cabinet restart (durable Redis stream);
  * a `sent:<draft_id>` marker is written BEFORE the entry is deleted, so a
    crash between mark and delete cannot cause a double-send — the next scan
    sees the marker and reaps the stale entry without re-sending;
  * a backend failure dead-letters the entry (it never silently drops), and one
    bad send never blocks a sibling good send in the same scan.

NOTE: this is the STANDALONE module per the A3 build scope. It is NOT wired into
`policy_engine.py` or `pre-tool-use.sh` — that integration is a later
Captain-authorized pass. Nothing here runs unless a caller invokes it.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

# Repo root on sys.path so the framework package imports cleanly (same
# convention as the sibling authority/fidelity modules). Used only to read the
# veto window default from the authority matrix floor.
_FRAMEWORK_ROOT = Path(__file__).resolve().parents[2]
if str(_FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_ROOT))

# ---------------------------------------------------------------------------
# Redis key namespace (single source — tests reference these by name).
# ---------------------------------------------------------------------------

#: The deferred-send veto stream. One XADD per queued internal-comms draft.
VETO_STREAM = "cabinet:drafts:veto"

#: List key that holds dead-lettered drafts (backend failures, never dropped).
DEAD_LETTER_KEY = "cabinet:drafts:veto:deadletter"

#: Prefix for the idempotency sent-marker keys (`sent:<draft_id>`).
_SENT_PREFIX = "cabinet:drafts:veto:sent:"

#: TTL on sent markers — orders of magnitude past any crash/retry window,
#: but finite so success markers stop accumulating forever.
SENT_MARKER_TTL_S = 14 * 24 * 3600

#: The org event type emitted on a kill (a §4 demotion-signal candidate).
GATE_DECISION_EVENT = "authority.gate_decision"

#: Hard floor if the matrix is unreadable (matches the shipped floor default).
_FALLBACK_WINDOW_MINUTES = 7


# Type aliases for the injected collaborators (duck-typed; tests pass fakes).
ClockFn = Callable[[], float]
SendBackend = Callable[[dict], Any]
EmitFn = Callable[[str, dict], Any]


def sent_marker_key(draft_id: str) -> str:
    """The idempotency marker key for a draft: set BEFORE delete, blocks re-send."""
    return f"{_SENT_PREFIX}{draft_id}"


# ---------------------------------------------------------------------------
# Window default — read from the authority matrix floor, not hardcoded.
# ---------------------------------------------------------------------------


def default_window_minutes() -> int:
    """The deferred-send delay N (minutes) from the authority matrix floor.

    Reads `authority-matrix.yml → veto_window_minutes` via the germline matrix
    loader (READ-ONLY — A3 never writes germline). Falls back to a safe literal
    if the matrix is unreadable, so a missing floor never blocks the queue.
    """
    try:
        from framework.authority import matrix as _matrix

        policy = _matrix.matrix_policy(_matrix.load_matrix())
        n = policy.get("veto_window_minutes")
        if isinstance(n, int) and not isinstance(n, bool) and n > 0:
            return n
    except Exception:
        pass
    return _FALLBACK_WINDOW_MINUTES


# ---------------------------------------------------------------------------
# 1. Enqueue (called by the gate on verdict auto_with_veto_window)
# ---------------------------------------------------------------------------


def enqueue_veto(
    officer: str,
    lane: str,
    action_type: str,
    payload: dict,
    window_minutes: Optional[int] = None,
    *,
    redis,
    clock: ClockFn,
) -> str:
    """Queue an internal-comms draft for deferred send; return its draft_id.

    XADDs one entry to `cabinet:drafts:veto` carrying the full payload plus a
    `send_at = now + N*60` epoch-seconds deadline and a fresh `draft_id`. N is
    `window_minutes` when given, else the matrix floor default. The caller (the
    gate) returns exit 2 with the "queued for veto window" directive so the
    officer does not ALSO send — this function performs no send.

    `redis` and `clock` are injected (a real Redis client + `time.time`-style
    callable in production; fakes in tests).
    """
    if window_minutes is None:
        window_minutes = default_window_minutes()
    draft_id = uuid.uuid4().hex
    send_at = float(clock()) + float(window_minutes) * 60.0

    fields = {
        "draft_id": draft_id,
        "officer": str(officer),
        "lane": str(lane),
        "action_type": str(action_type),
        "send_at": repr(send_at),
        # The whole payload (recipient/body/etc.) rides as JSON so the scan can
        # reconstruct the exact draft to hand the approved backend.
        "payload": json.dumps(payload, default=str),
    }
    redis.xadd(VETO_STREAM, fields)
    return draft_id


# ---------------------------------------------------------------------------
# 2. Notifier (the notify-after half — composes a string, NEVER sends)
# ---------------------------------------------------------------------------


def compose_veto_notice(
    draft_id: str,
    payload: dict,
    window_minutes: Optional[int] = None,
) -> str:
    """Compose the Telegram veto notice. Returns a string; sends nothing.

    Shape (design §Component 5 step 2): "Sending to <person> in N min —
    [preview]. Reply `kill <draft_id>` to stop." A preview snippet of the body
    is included so the Captain can judge at a glance. Per telegram-communication rules
    the caller threads the reply; this function only builds the text.
    """
    if window_minutes is None:
        window_minutes = default_window_minutes()
    recipient = payload.get("recipient", "the recipient")
    body = str(payload.get("body", ""))
    preview = body if len(body) <= 140 else body[:137] + "…"
    return (
        f"Sending to {recipient} in {window_minutes} min — {preview}\n"
        f"Reply `kill {draft_id}` to stop."
    )


# ---------------------------------------------------------------------------
# 3. Kill path (CoS handler on `kill <draft_id>`)
# ---------------------------------------------------------------------------


def kill_draft(
    draft_id: str,
    *,
    redis,
    emitter: Optional[EmitFn] = None,
) -> bool:
    """Kill a queued draft before its TTL; return True if one was removed.

    XDELs the matching stream entry and emits an `authority.gate_decision`
    `{killed: true, ...}` record (a demotion-signal candidate, §4 trigger 4/5)
    so false-positive / kill signals are durable. A kill for an unknown/already
    -gone draft is a no-op: returns False and emits nothing.

    `emitter` is injected (a fake in tests; a thin wrapper over the org-event
    emitter in production). Emission failures never raise — the kill itself is
    the safety-critical action and must succeed regardless of the ledger.
    """
    entry = _find_entry(redis, draft_id)
    if entry is None:
        return False
    entry_id, fields = entry
    redis.xdel(VETO_STREAM, entry_id)

    if emitter is not None:
        cell = (
            fields.get("officer", ""),
            fields.get("lane", ""),
            fields.get("action_type", ""),
        )
        record = {
            "cell": cell,
            "verdict": "auto_with_veto_window",
            "action_type": fields.get("action_type", ""),
            "officer": fields.get("officer", ""),
            "lane": fields.get("lane", ""),
            "draft_id": draft_id,
            "killed": True,
        }
        try:
            emitter(GATE_DECISION_EVENT, record)
        except Exception as exc:  # ledger is best-effort, kill is not
            print(f"veto: WARN gate_decision emit failed: {exc}", file=sys.stderr)
    return True


# ---------------------------------------------------------------------------
# 4. Auto-send on expiry (resilient, idempotent scan-sender)
# ---------------------------------------------------------------------------


def scan_and_send(
    now_ts: float,
    *,
    redis,
    send_backend: SendBackend,
) -> list:
    """Send every queued draft whose `send_at` has passed; return sent draft_ids.

    The resilient sweep (post-tool-use or a 60s cron). For each entry past its
    deadline:

      1. If a `sent:<draft_id>` marker already exists (a crash landed between
         mark and delete on a previous scan), REAP the stale entry without
         re-sending — idempotency.
      2. Otherwise CLAIM the `sent:` marker FIRST (SET NX, reply checked —
         an overlapping sweep that loses the claim reaps the entry instead of
         sending a second copy), then fire the approved `send_backend`. The
         marker-before-send ordering means a crash after the marker but before
         delete still cannot double-send. Markers carry a finite TTL
         (`SENT_MARKER_TTL_S`) so they stop accumulating.
      3. On backend success: XDEL the entry. On backend FAILURE: dead-letter the
         entry (RPUSH to the DLQ), clear the sent marker (so a future operator
         requeue is honest), and XDEL from the live stream — a failure is never
         a silent drop, and one bad send never blocks a sibling good send.

    Idempotent + crash-safe. `redis` and `send_backend` are injected.
    """
    sent: list = []
    for entry_id, fields in list(redis.xrange(VETO_STREAM)):
        try:
            send_at = float(fields.get("send_at", "inf"))
        except (TypeError, ValueError):
            send_at = float("inf")
        if float(now_ts) < send_at:
            continue  # not yet due

        draft_id = fields.get("draft_id") or entry_id
        marker = sent_marker_key(draft_id)

        # (1) idempotency: already-sent (crash window) → reap, don't re-send.
        if redis.exists(marker):
            redis.xdel(VETO_STREAM, entry_id)
            continue

        # (2) mark BEFORE send so a crash here cannot double-send. The SET NX
        #     reply IS the claim: an overlapping sweep that lost the race
        #     must not fall through and send a second copy — the winner owns
        #     the send; the loser reaps its view of the entry and moves on
        #     (a stale XDEL under the winner is a harmless no-op).
        if not redis.set(marker, "1", nx=True):
            redis.xdel(VETO_STREAM, entry_id)
            continue
        try:  # finite marker life — hygiene only, never blocks the send
            redis.expire(marker, SENT_MARKER_TTL_S)
        except Exception as exc:
            print(f"veto: WARN sent-marker TTL failed for {draft_id}: {exc}",
                  file=sys.stderr)

        draft = _decode_payload(fields)
        try:
            send_backend(draft)
        except Exception as exc:
            # (3b) failure → dead-letter, never a silent drop.
            _dead_letter(redis, entry_id, fields, str(exc))
            redis.delete(marker)  # not actually sent — keep the record honest
            redis.xdel(VETO_STREAM, entry_id)
            continue

        # (3a) success → remove the live entry; the marker stays as the proof.
        redis.xdel(VETO_STREAM, entry_id)
        sent.append(draft_id)
    return sent


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_entry(redis, draft_id: str):
    """Return (entry_id, fields) for the stream entry with this draft_id, or None."""
    for entry_id, fields in list(redis.xrange(VETO_STREAM)):
        if fields.get("draft_id") == draft_id or entry_id == draft_id:
            return entry_id, fields
    return None


def _decode_payload(fields: dict) -> dict:
    """Reconstruct the draft dict the send backend expects from stream fields."""
    raw = fields.get("payload")
    if isinstance(raw, str) and raw:
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except (ValueError, TypeError):
            pass
    # Fallback: reconstruct from the flat fields (no JSON payload present).
    return {
        k: v for k, v in fields.items()
        if k not in ("payload", "send_at")
    }


def _dead_letter(redis, entry_id: str, fields: dict, error: str) -> None:
    """Move a failed send to the dead-letter list — never silently drop it."""
    record = {
        "entry_id": entry_id,
        "draft_id": fields.get("draft_id", entry_id),
        "fields": {k: v for k, v in fields.items()},
        "error": error,
    }
    try:
        redis.rpush(DEAD_LETTER_KEY, json.dumps(record, default=str))
    except Exception as exc:  # last-ditch: surface, never swallow into the void
        print(f"veto: WARN dead-letter push failed for "
              f"{fields.get('draft_id', entry_id)}: {exc}", file=sys.stderr)
