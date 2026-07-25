"""Event emitter for the organizational event ledger.

Every meaningful state change in the org runtime emits an event.
Events are the single source of truth — all other systems derive state from them.

Usage:
    from framework.events.emitter import emit

    emit("mission_created", actor="cos", payload={"mission_id": "...", "name": "..."})
    emit("role_hat_assigned", actor="captain", payload={...}, parent_id="<event-uuid>")
"""

from __future__ import annotations

import fcntl
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
    # Registered 2026-07-17 (evidence Phase 2 Batch A): the attention gate
    # (framework/attention/escalation.py) has emitted this since the gate
    # shipped, but the type was never registered — emit() raised ValueError
    # which the call site's blanket except swallowed, so the durable
    # captain-gate-bounce record silently never landed. Additive,
    # observation-only vocabulary fix; the R-1 authority mirror selects it.
    "captain_gate_bounced",

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
    "fidelity_case_labeled",        # [Design C v0] Captain verdict_human label on a scored case (judge-calibration pairing)
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
    "notification_received",  # CC Notification hook (audit #20, 2026-07-07)
    "kill_switch_activated",
    "kill_switch_deactivated",
    "spending_limit_reached",

    # Authority/control-plane observations (R-1, evidence Phase 2 Batch B —
    # registered 2026-07-17). RECEIPT class by law: every one describes a
    # control-plane state change that ALREADY happened; none may ever gate,
    # block, or fail the verb/brake it describes. Emitters: the Captain's
    # narrow-only posture verb (framework/frontdoor/binder_wire.py
    # _route_posture_command) emits the cap pair at the verb; the UNLOCKED
    # state-diff sweep cabinet/scripts/emit-authority-transitions.py (the
    # emit-graduation-transitions.py idiom) emits posture_changed +
    # germline_*_observed + the pre-registered kill_switch_* classes on
    # TRANSITION only — never per-poll rows (59%-plumbing law). The
    # germline/kill-switch window timestamps are sweep-cadence quantized and
    # delivery is at-least-once (consumers must tolerate a duplicated
    # transition, same contract as graduation_transition).
    "posture_cap_narrowed",      # Captain `posture guardian|earn_up` wrote the narrow cap
    "posture_cap_cleared",       # Captain `posture clear` removed the narrow cap
    "posture_changed",           # observed effective posture resolution changed
    "germline_unlock_observed",  # germline path(s) observed leaving the locked state
    "germline_relock_observed",  # germline path(s) observed returning to the locked state

    # Evidence plane (Phase 2 telemetry mirrors — observation-only): emitted
    # best-effort when the org->evidence mirror loses the recorder (see
    # framework/evidence_mirror.py). MUST never join the mirror allow-list —
    # mirroring the degradation signal of a dead recorder would recurse.
    "evidence_mirror_degraded",

    # Outbox (cross-system writes)
    "outbox_queued",
    "outbox_dispatched",
    "outbox_failed",

    # Sovereign posture kernel (SOV-1) — needs ledger [FI-3] + brakes [FI-5]
    "need_filed",
    # R-1 Batch B (2026-07-17): the Captain's Telegram `grant NEED-x` verb
    # sets approved_pending_apply (the DECISION moment) — previously silent;
    # only the later root ceremony's granted emitted. Consumers must treat
    # need_approved (decision) and need_granted (applied) as DISTINCT verbs
    # on one need_id, never duplicates.
    "need_approved",
    "need_granted",
    "need_denied",
    "need_snoozed",
    "need_expired",
    "need_escalated",
    "cap_alarm",       # sovereign: daily cap reached ⇒ alarm + proceed (D11)
    "kind_unfrozen",   # unfreeze primitive lifted a frozen kind (D11/SOV-5)
    # R-1 Batch B (2026-07-17): symmetry fix — freeze() engaged the brake
    # with only the frozen-kinds.jsonl mirror row; the lift had an event but
    # the (more important) demotion moment did not. Best-effort AFTER the
    # durable mirror write; a dead event plane never blocks the brake.
    "kind_frozen",

    # Watchdog / doctor / officer-session lifecycle receipts (evidence
    # program Phase 2 Batch B, 2026-07-17 — receipt-class, mirror-signed).
    # Deliberately NEW officer-scoped TRANSITION classes: the generic
    # session_started/session_ended/subagent_completed families are ~94% of
    # live org volume, pinned OUT of the evidence mirror forever
    # (framework/evidence_mirror.py NEVER_MIRRORED_EXHAUST), and must never
    # be widened into it. These classes carry meaningful transitions ONLY —
    # a routed watchdog failure (cooldown-bounded), the daily doctor
    # verdict, fleet-officer session start/end/compaction, capped restart
    # attempts, exactly-once limit wakes — never per-poll sweeps, healthy
    # passes, heartbeats, or trigger/delivery mechanics (59%-plumbing law).
    # Emitters: framework/watchdog/check.py + cabinet-doctor.sh +
    # cabinet/cron/{heartbeat,limit-reset}-watchdog.sh (all via
    # `-m framework.watchdog.receipts`, the typed lens seam) and
    # cabinet/scripts/emit-officer-lifecycle-transitions.py (observer).
    "watchdog_outcome_failed",
    "doctor_verdict",
    "officer_session_started",
    "officer_session_ended",
    "officer_session_compacted",
    "officer_restarted",
    "officer_limit_wake",
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

    # Evidence mirror reservation (Phase 2, observation-only). For classes
    # on the explicit allow-list (framework/evidence_mirror.py — telemetry
    # receipts, degrade-loud-never-block) stamp the deterministic day-trial
    # id into a COPY of the payload (forward correlation org->evidence; the
    # payload is the only field all three sinks carry whole, and org rows
    # are immutable post-emit). ImportError = path-exec CLI producers (repo
    # root not on sys.path) — their classes are exhaust and never mirrored.
    evidence_mirror = None
    mirror_slot = None
    try:
        from framework import evidence_mirror  # type: ignore
        mirror_slot = evidence_mirror.reserve_org(event_type)
        if mirror_slot:
            event["payload"] = {
                **event["payload"],
                evidence_mirror.PAYLOAD_KEY: {"trial_id": mirror_slot["trial_id"]},
            }
    except ImportError:
        pass
    except Exception as exc:  # reservation must never block the domain emit
        mirror_slot = None
        print(f"event-emitter: WARN evidence mirror reserve failed: {exc}", file=sys.stderr)

    # Always write to the local event log (append-only JSONL)
    _write_to_log(event)

    # Write to Postgres if available
    _write_to_db(event)

    # F3: mirror to org_runtime.Store so dashboard + claude-task-bridge + CLI
    # see the same events as framework code (the unification fix).
    _write_to_store(event)

    # Evidence mirror receipt — strictly AFTER every domain sink. The mirror
    # is a receipt about an already-happened event: a recorder outage
    # degrades LOUD inside the module (stderr + doctor marker + best-effort
    # evidence_mirror_degraded org event, rate-limited) and never blocks
    # this emit or any bare call site.
    if mirror_slot and evidence_mirror is not None:
        try:
            evidence_mirror.mirror_org_event(event, mirror_slot)
        except Exception as exc:  # pragma: no cover — module degrades internally
            print(f"event-emitter: WARN evidence mirror failed: {exc}", file=sys.stderr)

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


def _warn_torn_record(log_file: Path, line_number: int | str, *, repaired: bool) -> None:
    action = "discarded" if repaired else "ignored"
    print(
        f"event-emitter: WARN {action} torn final JSONL record in "
        f"{log_file}:{line_number}",
        file=sys.stderr,
    )


def _trim_torn_tail_locked(fd: int, log_file: Path) -> None:
    """Drop a crash-torn, non-newline-terminated tail while holding LOCK_EX.

    Every healthy writer appends exactly one newline-terminated record.  A
    non-empty file whose final byte is not ``\\n`` therefore contains an
    interrupted final append.  Repair before the next write so a valid new
    event cannot be concatenated onto (and lost with) that torn fragment.
    """
    size = os.fstat(fd).st_size
    if size == 0 or os.pread(fd, 1, size - 1) == b"\n":
        return

    cursor = size
    truncate_at = 0
    while cursor > 0:
        start = max(0, cursor - 64 * 1024)
        chunk = os.pread(fd, cursor - start, start)
        newline = chunk.rfind(b"\n")
        if newline >= 0:
            truncate_at = start + newline + 1
            break
        cursor = start

    os.ftruncate(fd, truncate_at)
    _warn_torn_record(
        log_file,
        "tail",
        repaired=True,
    )


def _write_to_log(event: dict[str, Any]) -> None:
    """Durably append one event to the local JSONL ledger.

    An advisory cross-process lock prevents interleaved repair/appends, O_APPEND
    makes every physical write target EOF, and fsync makes the JSONL guarantee
    survive a successful return.  A prior crash-torn tail is removed under the
    same lock before the new record is appended.
    """
    log_dir = _event_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"events-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
    payload = (json.dumps(event, default=str) + "\n").encode("utf-8")
    created = not log_file.exists()
    fd = os.open(log_file, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        _trim_torn_tail_locked(fd, log_file)
        remaining = memoryview(payload)
        while remaining:
            try:
                written = os.write(fd, remaining)
            except InterruptedError:
                continue
            if written <= 0:
                raise OSError("event ledger append made no progress")
            remaining = remaining[written:]
        os.fsync(fd)
        if created:
            dir_fd = os.open(log_dir, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _write_to_db(event: dict[str, Any]) -> None:
    """Insert event into Postgres org_events table if DATABASE_URL is set.

    Column shape matches cabinet/sql/045-org-runtime-slice.sql (the canonical
    production schema): event_id, event_type, lane_slug, aggregate_type,
    aggregate_id, actor, source, payload, supersedes_event_id, created_at.

    F3 unification: the same event_id, aggregate_type, aggregate_id and
    lane_slug are used as the org_runtime.Store mirror, so an event has
    ONE authoritative id across JSONL, Postgres, and the Store SQLite.

    Note: parent_id (a framework-local field) is mapped to
    supersedes_event_id in the canonical schema. Both express
    "this event refers to that earlier event."
    """
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return

    agg_type, agg_id = _resolve_aggregate(event["event_type"], event["payload"])
    lane_slug = _resolve_lane_slug()

    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO org_events (
                       event_id, event_type, lane_slug, aggregate_type,
                       aggregate_id, actor, source, payload,
                       supersedes_event_id, created_at
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    event["id"],
                    event["event_type"],
                    lane_slug,
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
    "captain_gate_bounced":       ("captain",     "subject"),
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
    "fidelity_case_labeled":       ("fidelity",    "case_id"),
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
    "notification_received":      ("session",     "session_id"),
    "kill_switch_activated":      ("system",      "killswitch_id"),
    "kill_switch_deactivated":    ("system",      "killswitch_id"),
    "spending_limit_reached":     ("system",      "limit_id"),
    "evidence_mirror_degraded":   ("system",      "chokepoint"),
    # Phase 2 Batch B receipts (watchdog/doctor + officer lifecycle)
    "watchdog_outcome_failed":    ("watchdog",    "expectation_id"),
    "doctor_verdict":             ("system",      "verdict"),
    "officer_session_started":    ("officer",     "officer"),
    "officer_session_ended":      ("officer",     "officer"),
    "officer_session_compacted":  ("officer",     "officer"),
    "officer_restarted":          ("officer",     "officer"),
    "officer_limit_wake":         ("officer",     "officer"),
    # R-1 authority/control-plane observations (Batch B). need_approved maps
    # on the need id (its need_* siblings predate the map and stay
    # prefix-derived); kind_frozen is deliberately UNMAPPED like its sibling
    # kind_unfrozen (prefix-derived "kind") so the pair aggregates alike.
    "posture_cap_narrowed":       ("system",      "posture"),
    "posture_cap_cleared":        ("system",      "posture"),
    "posture_changed":            ("system",      "posture"),
    "germline_unlock_observed":   ("system",      "boundary_id"),
    "germline_relock_observed":   ("system",      "boundary_id"),
    "need_approved":              ("need",        "need_id"),
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


def _resolve_lane_slug() -> str:
    """Resolve lane_slug for the Store schema (env > active-project.txt > 'default')."""
    # The ENV KNOB keeps its legacy name: it is shared with framework.learning
    # capability-gap routing, so renaming it is a separate, wider change than
    # the 2026-07-25 column rename.
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
            lane_slug=_resolve_lane_slug(),
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
        fd = os.open(log_file, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH)
            size = os.fstat(fd).st_size
            with os.fdopen(os.dup(fd), "rb") as f:
                line_number = 0
                while True:
                    raw_line = f.readline()
                    if not raw_line:
                        break
                    line_number += 1
                    if not raw_line.strip():
                        continue
                    try:
                        event = json.loads(raw_line.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        is_torn_tail = f.tell() == size and not raw_line.endswith(b"\n")
                        if is_torn_tail:
                            _warn_torn_record(log_file, line_number, repaired=False)
                            continue
                        raise

                    if since and event["created_at"] < since:
                        continue
                    if event_types and event["event_type"] not in event_types:
                        continue
                    if actor and event["actor"] != actor:
                        continue

                    events.append(event)
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

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
