"""Event emitter for the organizational event ledger.

Every meaningful state change in the org runtime emits an event.
Events are the single source of truth — all other systems derive state from them.

Usage:
    from framework.events.emitter import emit

    emit("mission_created", actor="cos", payload={"mission_id": "...", "name": "..."})
    emit("role_hat_assigned", actor="captain", payload={...}, parent_id="<event-uuid>")
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Event types — the vocabulary of the organizational runtime.
# Add new types here as systems are built.
VALID_EVENT_TYPES = frozenset({
    # Captain actions
    "captain_goal_declared",
    "captain_outcome_ratified",
    "captain_decision_logged",
    "captain_boundary_set",

    # Role lifecycle
    "role_created",
    "role_charter_changed",
    "role_capability_added",
    "role_capability_removed",
    "role_authority_changed",
    "role_suspended",
    "role_reactivated",
    "role_retired",
    "role_hat_assigned",
    "role_hat_removed",
    "role_hat_promoted",  # hat becomes a permanent capability

    # Mission lifecycle
    "mission_created",
    "mission_activated",
    "mission_completed",
    "mission_failed",

    # Work graph
    "work_item_created",
    "work_item_assigned",
    "work_item_started",
    "work_item_completed",
    "work_item_failed",
    "work_item_verified",

    # Policy
    "policy_evaluated",
    "policy_blocked",
    "policy_updated",

    # Measurement
    "ovi_snapshot_computed",
    "eval_run_started",
    "eval_passed",
    "eval_failed",

    # Learning
    "experience_recorded",
    "digest_published",
    "memory_claim_created",
    "memory_claim_superseded",

    # System
    "session_started",
    "session_ended",
    "kill_switch_activated",
    "kill_switch_deactivated",
    "spending_limit_reached",

    # Outbox (cross-system writes)
    "outbox_queued",
    "outbox_dispatched",
    "outbox_failed",
})


def emit(
    event_type: str,
    actor: str,
    payload: dict[str, Any] | None = None,
    parent_id: str | None = None,
) -> dict[str, Any]:
    """Emit an organizational event.

    Returns the event dict (with generated id and timestamp).
    Writes to the event log file and optionally to Postgres.
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(
            f"Unknown event type: {event_type}. "
            f"Add it to VALID_EVENT_TYPES in {__file__}"
        )

    event = {
        "id": str(uuid.uuid4()),
        "event_type": event_type,
        "actor": actor,
        "payload": payload or {},
        "parent_id": parent_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Always write to the local event log (append-only JSONL)
    _write_to_log(event)

    # Write to Postgres if available
    _write_to_db(event)

    return event


def _write_to_log(event: dict[str, Any]) -> None:
    """Append event to the local JSONL event log."""
    log_dir = Path(os.environ.get(
        "CABINET_EVENT_LOG_DIR",
        "/tmp/cabinet-events"
    ))
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"events-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(event, default=str) + "\n")


def _write_to_db(event: dict[str, Any]) -> None:
    """Insert event into Postgres org_events table if DATABASE_URL is set."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return

    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO org_events (id, event_type, actor, payload, parent_id, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    event["id"],
                    event["event_type"],
                    event["actor"],
                    json.dumps(event["payload"]),
                    event["parent_id"],
                    event["created_at"],
                ),
            )
            conn.commit()
        conn.close()
    except Exception as e:
        # DB write is best-effort — the JSONL log is the guaranteed record.
        # Log to stderr so failures are visible in hook output.
        print(f"event-emitter: WARN db write failed: {e}", file=sys.stderr)


def replay(
    since: str | None = None,
    event_types: list[str] | None = None,
    actor: str | None = None,
) -> list[dict[str, Any]]:
    """Replay events from the local JSONL log.

    Args:
        since: ISO timestamp — only events after this time
        event_types: filter to these event types
        actor: filter to this actor
    """
    log_dir = Path(os.environ.get(
        "CABINET_EVENT_LOG_DIR",
        "/tmp/cabinet-events"
    ))
    if not log_dir.exists():
        return []

    events = []
    for log_file in sorted(log_dir.glob("events-*.jsonl")):
        with open(log_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)

                if since and event["created_at"] < since:
                    continue
                if event_types and event["event_type"] not in event_types:
                    continue
                if actor and event["actor"] != actor:
                    continue

                events.append(event)

    return events


if __name__ == "__main__":
    # CLI: emit an event from shell scripts
    # Usage: python3 emitter.py <event_type> <actor> [payload_json]
    if len(sys.argv) < 3:
        print("Usage: emitter.py <event_type> <actor> [payload_json]", file=sys.stderr)
        sys.exit(1)

    event_type = sys.argv[1]
    actor = sys.argv[2]
    payload = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}

    event = emit(event_type, actor, payload)
    print(json.dumps(event))
