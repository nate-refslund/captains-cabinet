"""Transactional outbox: durable cross-system writes via the event ledger.

Phase 1.4 of the convergence plan. The classic transactional-outbox pattern
solves the dual-write problem (write to local DB + external system without
distributed transactions): write a local "outbox row" atomically with your
business state, then have a relay process dispatch it to the external system
with retry-on-failure.

In the event-sourced Cabinet, the event ledger IS the outbox table. Every
queued operation emits an `outbox_queued` event. The relay process replays
those events, dispatches each to a registered adapter, and emits
`outbox_dispatched` (success) or `outbox_failed` (transient failure, will
retry on the next relay cycle).

Idempotency: `outbox_dispatched` events carry the original `outbox_queued`
event's `parent_id`. Replaying the ledger gives us the set of already-
dispatched outbox IDs, so re-runs do not re-dispatch.

Destinations (pluggable adapters): each destination string maps to a
callable `adapter(payload: dict) -> None`. The MVP ships a stub-print
adapter for `stub`; real adapters (notion, linear, monday, asana, jira,
github_issues) are registered by Phase 5 of the convergence plan.

Usage:
    from framework.outbox.relay import queue, dispatch_pending, register_adapter

    # Queue a cross-system write (officer / hook):
    qid = queue(
        destination="notion",
        payload={"page_id": "abc", "title": "New mission", "body": "..."},
        actor="cos",
    )

    # Cron / launchd dispatcher:
    result = dispatch_pending()
    # → {"dispatched": 3, "failed": 1, "skipped": 0}

    # Plug in a real adapter (Phase 5):
    def notion_adapter(payload):
        # ... call Notion API
        pass
    register_adapter("notion", notion_adapter)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

# Ensure framework root is importable
_FRAMEWORK_ROOT = str(Path(__file__).parent.parent.parent)
if _FRAMEWORK_ROOT not in sys.path:
    sys.path.insert(0, _FRAMEWORK_ROOT)

from framework.events.emitter import emit, replay


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

AdapterFn = Callable[[dict[str, Any]], None]

# Phase 1.4 ships with a stub adapter only. Phase 5 wires real adapters
# for Monday, Jira, Linear, Asana, GitHub Issues, Notion.
_ADAPTERS: dict[str, AdapterFn] = {}


def register_adapter(destination: str, fn: AdapterFn) -> None:
    """Register an adapter function for a destination.

    The adapter takes the payload dict and either returns normally (success)
    or raises an exception (failure → relay emits outbox_failed and retries
    on the next cycle).
    """
    _ADAPTERS[destination] = fn


def _stub_adapter(payload: dict[str, Any]) -> None:
    """Default no-op adapter used in tests + as a sentinel until Phase 5."""
    # Intentionally silent. Printing would pollute the relay's structured
    # stdout/stderr contract.
    return None


register_adapter("stub", _stub_adapter)


# ---------------------------------------------------------------------------
# Queue API (callers)
# ---------------------------------------------------------------------------


def queue(
    destination: str,
    payload: dict[str, Any],
    actor: str = "system",
    idempotency_key: str | None = None,
) -> str:
    """Queue a cross-system write to the outbox event log.

    Args:
        destination: adapter slug (e.g., "notion", "linear", "stub")
        payload: arbitrary JSON-serializable dict the adapter understands
        actor: who is queueing (role slug or "system")
        idempotency_key: optional caller-provided key; if a prior
            outbox_queued event with the same key was already dispatched,
            this queue() is a no-op and returns that prior event's id.

    Returns:
        The event id of the outbox_queued event (or the prior one if
        deduped by idempotency_key).
    """
    if idempotency_key is not None:
        # Look for a previously dispatched event with the same key
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
        },
    )
    return event["id"]


# ---------------------------------------------------------------------------
# Relay (dispatcher)
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


def _pending_queue() -> list[dict[str, Any]]:
    """Return outbox_queued events not yet terminal-dispatched, oldest first."""
    queued = replay(event_types=["outbox_queued"])
    processed = _already_processed_ids()
    return [ev for ev in queued if ev["id"] not in processed]


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
    """Dispatch every currently-pending outbox entry.

    Returns:
        Counts: {"dispatched": int, "failed": int, "skipped": int}.
    """
    counts = {"dispatched": 0, "failed": 0, "skipped": 0}
    for queued in _pending_queue():
        outcome = dispatch_one(queued, actor=actor)
        counts[outcome] += 1
    return counts


# ---------------------------------------------------------------------------
# CLI (used by cabinet/cron/outbox-relay.sh)
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Outbox relay — dispatch pending cross-system writes."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print summary as JSON",
    )
    parser.add_argument(
        "--list-pending",
        action="store_true",
        help="Print pending outbox entries (no dispatch)",
    )
    args = parser.parse_args(argv)

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
            print(f"outbox: {len(pending)} pending")
        return 0

    counts = dispatch_pending()
    if args.json:
        print(json.dumps(counts))
    else:
        print(f"outbox-relay: dispatched={counts['dispatched']} "
              f"failed={counts['failed']} skipped={counts['skipped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
