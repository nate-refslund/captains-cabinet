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
import tempfile
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
    "work_item_unroutable",  # ready task whose assigned_role is not in the active roster
    "work_item_started",
    "work_item_completed",
    "work_item_failed",
    "work_item_verified",
    # Subagent lifecycle (2026-07-04 ledger hygiene + g-hooks). Generic
    # helper-agent completions (code reviewers, explainer crews, exploration,
    # debugging — no task ref in agent_type) land HERE, not on
    # work_item_completed: the SubagentStop hook
    # (cabinet/scripts/hooks/on-subagent-stop.sh) used to emit
    # work_item_completed for EVERY subagent stop, burying genuine work-graph
    # completions — and the mission-ledger consumers that replay
    # work_item_completed (OVI task_throughput / verification_pass_rate, mission
    # compiler DONE overlay) — under ~6.6k task-ref-less rows (purge:
    # cabinet/scripts/ledger-purge-testrows.sh). This entry is the WRITABLE half
    # of the fix — a valid landing type for the hook; the hook's switch itself
    # is germline and is applied via the germline process. Telemetry-only — no
    # consumer replays it yet. (De-duplicated at integration: the ledger and
    # germline lanes each registered this type; one canonical entry.)
    "subagent_completed",

    # Policy
    "policy_evaluated",
    "policy_blocked",
    "policy_updated",

    # Measurement
    "ovi_snapshot_computed",
    "eval_run_started",
    "eval_passed",
    "eval_failed",

    # Fidelity harness (F) — officer-under-test evaluation + leak guard
    "fidelity_case_evaluated",      # blind officer decision captured for a held-out case
    "fidelity_case_leak_detected",  # anti-leakage breach → case hard-failed, never scored
    "fidelity_case_scored",         # [T3] scored case: intent axis + intent-mapped review.verdict
    # Graduation visibility (lane instrument, 2026-07-05): a per-cell autonomy
    # STATE TRANSITION (unmeasured/propose_only/eligible/graduated/demote)
    # observed by the sweep cabinet/scripts/emit-graduation-transitions.py.
    # graduation.evaluate is stateless and schg-LOCKED, so transitions are
    # detected + emitted by that UNLOCKED caller (current state vs its own
    # last-seen state file) — this is how a briefing SEES cells moving instead
    # of re-deriving state on every read. payload: {cell:{actor,lane,
    # action_type}, from_state, to_state, evidence:{...}}. At-least-once:
    # consumers must tolerate a duplicated transition (a failed state-file
    # write after a successful emit re-emits next sweep).
    "graduation_transition",

    # Self-improvement loop (R8) — closed-loop learning pipeline
    "role_evolved",                       # charter/capability auto-applied via self-improvement
    "skill_promoted",                     # induced draft skill passed validation gate
    "self_improvement_loop_started",
    "self_improvement_loop_completed",

    # Self-extension loop — capability gaps → auto-skill or propose-then-approve
    "capability_gap_recorded",            # officer hit a wall, or loop inferred one
    "capability_gap_merged",              # dedup: a recurring gap, hit_count incremented
    "capability_gap_classified",          # routed: procedure | tool | integration
    "capability_gap_proposed",            # tool/integration gap → proposal sent to Captain
    "capability_gap_approved",            # Captain approved the proposal (install gate key)
    "capability_gap_declined",            # Captain declined (with reason → learning)
    "capability_gap_resolved",            # gap closed (auto-skilled OR built+installed)

    # Self-extension surfacing — the Chair PREPARES + SURFACES; the Captain applies.
    "self_proposal_prepared",             # Chair surfaced a one-tap MCP/plugin scope-grant proposal
    "account_flow_surfaced",              # Chair surfaced a "credential needed" account-flow step

    # Trust ladder — the earn_up posture's climb surface (axes build, spec
    # 2026-07-05 §1 L1). REMOVED 2026-07-04 with framework/learning/
    # trust_ladder.py (earn-demotion ruling: as a DEFAULT the ladder
    # contradicted trust-first), RESURRECTED as the OPT-IN earn_up surface:
    # `proposed` is the one-tap climb card trust_ladder.propose_next_rung
    # surfaces (only when resolve_posture()==earn_up); `granted` is the
    # Captain surface's (trust_ladder.grant_rung) AUDIT record ONLY — this
    # ledger is same-uid-appendable, so NO authority ever derives from the
    # event: current_rung() reads the `granted:` rows of the ATTESTED
    # (Captain-locked) trust-ladder.yml exclusively (AX-8) and a forged
    # event mints nothing. Guardian/sovereign never emit either type.
    "trust_rung_proposed",
    "trust_rung_granted",

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

    # Sovereign posture kernel (SOV-1) — needs ledger [FI-3] + brakes [FI-5]
    "need_filed",
    "need_granted",
    "need_denied",
    "need_snoozed",
    "need_expired",
    "need_escalated",
    "cap_alarm",       # sovereign: daily cap reached ⇒ alarm + proceed (D11)
    "kind_unfrozen",   # unfreeze primitive lifted a frozen kind (D11/SOV-5)
})


def emit(
    event_type: str,
    actor: str,
    payload: dict[str, Any] | None = None,
    parent_id: str | None = None,
) -> dict[str, Any]:
    """Emit an organizational event.

    Returns the event dict (with generated id and timestamp).
    Writes (in order):
      1. JSONL ledger (always) — append-only, $CABINET_EVENT_LOG_DIR/events-YYYY-MM-DD.jsonl
      2. Postgres org_events table (optional) — only if DATABASE_URL is set
      3. org_runtime.Store SQLite ledger (F3 unification) — best-effort mirror so
         dashboard, claude-task-bridge, and CLI reads see the same events as
         framework code (scenario evals, mission compiler, OVI compute).

    The Store mirror is auto-disabled during pytest runs (PYTEST_CURRENT_TEST
    set) to avoid polluting the dev cache. Override via CABINET_FRAMEWORK_STORE_MIRROR.
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

    # F3: mirror to org_runtime.Store so dashboard + claude-task-bridge + CLI
    # see the same events as framework code (the unification fix).
    _write_to_store(event)

    return event


# Per-process cache for the pytest fallback dir (defense-in-depth fence,
# 2026-07-04). Cached so every resolver call inside ONE test process — the
# JSONL append in _write_to_log() AND the read in replay() — agrees on the
# SAME redirect target; a fresh dir per call would make emit-then-replay
# tests read an empty directory.
_PYTEST_FALLBACK_DIR: Path | None = None


def _event_log_dir() -> Path:
    """Resolve the JSONL event-ledger directory.

    CABINET_EVENT_LOG_DIR always wins when set. The default is a durable
    per-user location — /tmp/cabinet-events (the old default) is wiped on
    reboot/periodic cleanup, which silently truncated the event ledger.

    Defense-in-depth test fence (2026-07-04 leak incident): when running
    under pytest (PYTEST_CURRENT_TEST set) with NO explicit
    CABINET_EVENT_LOG_DIR, redirect to a per-process temp dir instead of the
    durable live default. The Store SQLite mirror already auto-skips under
    pytest (_write_to_store); this JSONL path did NOT — which is how 1,969+
    fidelity fixture rows (payload.subject "abc1234567") leaked into the live
    audit ledger. The PRIMARY fence is the repo-root conftest.py (+ pytest.ini
    rootdir anchor), which exports a session sandbox for the whole run
    including subprocesses; this layer catches any pytest invocation that
    bypasses the root conftest. Purge of the already-leaked rows:
    cabinet/scripts/ledger-purge-testrows.sh (Captain-gated).
    """
    explicit = os.environ.get("CABINET_EVENT_LOG_DIR")
    if explicit:
        return Path(explicit)
    if os.environ.get("PYTEST_CURRENT_TEST"):
        global _PYTEST_FALLBACK_DIR
        if _PYTEST_FALLBACK_DIR is None:
            _PYTEST_FALLBACK_DIR = Path(
                tempfile.mkdtemp(prefix="cabinet-pytest-events-")
            )
        return _PYTEST_FALLBACK_DIR
    return Path(os.path.expanduser("~/Library/Application Support/cabinet/events"))


def _write_to_log(event: dict[str, Any]) -> None:
    """Append event to the local JSONL event log."""
    log_dir = _event_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"events-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(event, default=str) + "\n")


def _write_to_db(event: dict[str, Any]) -> None:
    """Insert event into Postgres org_events table if DATABASE_URL is set.

    Column shape matches cabinet/sql/045-org-runtime-slice.sql (the canonical
    production schema): event_id, event_type, product_slug, aggregate_type,
    aggregate_id, actor, source, payload, supersedes_event_id, created_at.

    F3 unification: the same event_id, aggregate_type, aggregate_id and
    product_slug are used as the org_runtime.Store mirror, so an event has
    ONE authoritative id across JSONL, Postgres, and the Store SQLite.

    Note: parent_id (a framework-local field) is mapped to
    supersedes_event_id in the canonical schema. Both express
    "this event refers to that earlier event."
    """
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return

    agg_type, agg_id = _resolve_aggregate(event["event_type"], event["payload"])
    product_slug = _resolve_product_slug()

    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO org_events (
                       event_id, event_type, product_slug, aggregate_type,
                       aggregate_id, actor, source, payload,
                       supersedes_event_id, created_at
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    event["id"],
                    event["event_type"],
                    product_slug,
                    agg_type,
                    agg_id,
                    event["actor"],
                    "framework",
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


# ----------------------------------------------------------------------------
# F3: Org-runtime Store mirror (event-kernel unification)
# ----------------------------------------------------------------------------
#
# org_runtime.py has its own append-only ledger in a local SQLite file at
# cabinet/cache/org-runtime.sqlite3 (path overridable via ORG_RUNTIME_DB).
# Pre-F3, framework code emitted to JSONL but the dashboard /
# claude-task-bridge / org_runtime CLI all read from the Store. The two
# ledgers diverged → mission events from framework never surfaced in
# Captain-facing UI.
#
# Fix: framework emit() ALSO calls Store.append_event() so the Store is
# the single source of truth. JSONL stays as the always-on debug mirror.
#
# Auto-disabled during pytest (PYTEST_CURRENT_TEST set) to avoid polluting
# the dev cache. Override via CABINET_FRAMEWORK_STORE_MIRROR:
#   "1" = force on (even in tests)
#   "0" = force off (even in live runs)
#   unset = on outside pytest, off inside

# Map framework event_type → org_runtime aggregate. The payload key holds the
# aggregate_id (e.g. mission_created.payload.mission_id). Falls back to "id"
# or "unknown" if neither key is present.
_AGGREGATE_MAP: dict[str, tuple[str, str]] = {
    "mission_created":            ("mission",     "mission_id"),
    "mission_activated":          ("mission",     "mission_id"),
    "mission_completed":          ("mission",     "mission_id"),
    "mission_failed":             ("mission",     "mission_id"),
    "work_item_created":          ("work_item",   "task_id"),
    "work_item_assigned":         ("work_item",   "task_id"),
    "work_item_unroutable":       ("work_item",   "task_id"),
    "work_item_started":          ("work_item",   "task_id"),
    "work_item_completed":        ("work_item",   "task_id"),
    "work_item_failed":           ("work_item",   "task_id"),
    "work_item_verified":         ("work_item",   "task_id"),
    # Subagent lifecycle (2026-07-04): aggregate on the subagent's own id —
    # agent_id is the one key the SubagentStop hook payload ALWAYS carries
    # (task_ref only exists when agent_type encodes FW-*/PROD-*/TASK-*).
    "subagent_completed":         ("subagent",    "agent_id"),
    "role_created":               ("role",        "slug"),
    "role_charter_changed":       ("role",        "slug"),
    "role_capability_added":      ("role",        "slug"),
    "role_capability_removed":    ("role",        "slug"),
    "role_authority_changed":     ("role",        "slug"),
    "role_suspended":             ("role",        "slug"),
    "role_reactivated":           ("role",        "slug"),
    "role_retired":               ("role",        "slug"),
    "role_hat_assigned":          ("role",        "slug"),
    "role_hat_removed":           ("role",        "slug"),
    "role_hat_promoted":          ("role",        "slug"),
    "captain_goal_declared":      ("captain",     "goal_id"),
    "captain_outcome_ratified":   ("captain",     "outcome_id"),
    "captain_decision_logged":    ("captain",     "decision_id"),
    "captain_boundary_set":       ("captain",     "boundary_id"),
    "policy_evaluated":           ("policy",      "policy_id"),
    "policy_blocked":             ("policy",      "policy_id"),
    "policy_updated":             ("policy",      "policy_id"),
    "ovi_snapshot_computed":      ("ovi",         "period"),
    "eval_run_started":           ("eval",        "eval_id"),
    "eval_passed":                ("eval",        "eval_id"),
    "eval_failed":                ("eval",        "eval_id"),
    "fidelity_case_evaluated":     ("fidelity",    "case_id"),
    "fidelity_case_leak_detected": ("fidelity",    "case_id"),
    "fidelity_case_scored":        ("fidelity",    "case_id"),
    "role_evolved":               ("role",        "role_slug"),
    "skill_promoted":             ("skill",       "skill_slug"),
    "self_improvement_loop_started":   ("self_improvement", "loop_id"),
    "self_improvement_loop_completed": ("self_improvement", "loop_id"),
    "experience_recorded":        ("experience",  "experience_id"),
    "digest_published":           ("digest",      "digest_id"),
    "memory_claim_created":       ("memory",      "claim_id"),
    "memory_claim_superseded":    ("memory",      "claim_id"),
    "outbox_queued":              ("outbox",      "outbox_id"),
    "outbox_dispatched":          ("outbox",      "outbox_id"),
    "outbox_failed":              ("outbox",      "outbox_id"),
    "session_started":            ("session",     "session_id"),
    "session_ended":              ("session",     "session_id"),
    "kill_switch_activated":      ("system",      "killswitch_id"),
    "kill_switch_deactivated":    ("system",      "killswitch_id"),
    "spending_limit_reached":     ("system",      "limit_id"),
}


def _resolve_aggregate(event_type: str, payload: dict[str, Any]) -> tuple[str, str]:
    """Derive (aggregate_type, aggregate_id) for the Store schema."""
    spec = _AGGREGATE_MAP.get(event_type)
    if spec:
        agg_type, key = spec
        agg_id = payload.get(key) or payload.get("id") or "unknown"
        return (agg_type, str(agg_id))
    # Unmapped event — derive aggregate_type from the prefix
    agg_type = event_type.split("_", 1)[0] or "event"
    return (agg_type, str(payload.get("id", "unknown")))


def _resolve_product_slug() -> str:
    """Resolve product_slug for the Store schema (env > active-project.txt > 'default')."""
    slug = os.environ.get("CABINET_PRODUCT_SLUG")
    if slug:
        return slug
    cabinet_root = os.environ.get("CABINET_ROOT")
    if cabinet_root:
        try:
            active_project = Path(cabinet_root) / "instance" / "config" / "active-project.txt"
            if active_project.exists():
                slug = active_project.read_text().strip()
                if slug:
                    return slug
        except (IOError, OSError):
            pass
    return "default"


def _write_to_store(event: dict[str, Any]) -> None:
    """Mirror event into org_runtime.Store SQLite ledger (F3 unification).

    Best-effort: silently degrades if Store is unimportable or write fails.
    The JSONL ledger remains as the guaranteed record.
    """
    # Mirror policy: force-on/off override, else auto-skip inside pytest
    mirror = os.environ.get("CABINET_FRAMEWORK_STORE_MIRROR")
    if mirror == "0":
        return
    if mirror != "1" and os.environ.get("PYTEST_CURRENT_TEST"):
        return  # auto-disable during pytest unless forced on

    # Lazy import — only attempt if mirror is enabled
    try:
        framework_root = Path(__file__).resolve().parent.parent.parent
        lib_path = framework_root / "cabinet" / "scripts" / "lib"
        if str(lib_path) not in sys.path:
            sys.path.insert(0, str(lib_path))
        from org_runtime import Store  # type: ignore
    except ImportError:
        return

    try:
        store = Store()
        agg_type, agg_id = _resolve_aggregate(event["event_type"], event["payload"])
        # F3 (R4): pass framework's event_id through so Store + JSONL + Postgres
        # all share ONE authoritative id per logical event. Previously Store
        # minted its own uuid → divergent ids across ledgers.
        store.append_event(
            event_type=event["event_type"],
            product_slug=_resolve_product_slug(),
            aggregate_type=agg_type,
            aggregate_id=agg_id,
            actor=event["actor"],
            payload=event["payload"],
            source="framework",
            event_id=event["id"],
        )
    except Exception as e:
        # Best-effort — log to stderr but don't break the caller
        print(f"event-emitter: WARN store mirror failed: {e}", file=sys.stderr)


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
    log_dir = _event_log_dir()
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
