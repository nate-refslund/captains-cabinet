"""COG-1 W3 — EFFECTIVE-STATUS mapping unit cases (§6.1 step 3, §12.2 item 4).

The legacy stream vocabulary is EFFECTIVE status, not the raw officer_tasks
columns: my-tasks.sh rewrites OLD_STATUS to 'blocked' when a row LEAVES
blocked and emits new_status='blocked' when it ENTERS blocked. The relay must
reproduce that mapping over the raw capture columns before it builds the v2
envelope, or every blocked transition mis-maps and the parity monitor
false-breaches.

Pinned mapping (plan §6.1):
  * new_blocked = TRUE  -> new_status := 'blocked'
  * old_blocked = TRUE  -> old_status := 'blocked'
  * INSERT-arm NULL old_status -> ''

The four cases the plan names (block, unblock, done-from-blocked,
cancel-from-blocked) are the ones where the overlay diverges from the raw
column; each is asserted here AND round-tripped through validate_v2 so the
mapped payload is provably schema-legal (tasks/task-event@1 enum).

Tests-first: these fail RED against HEAD (relay exposes no effective_* /
build_dispatch_fields yet); the W3 relay extension turns them green. No
Postgres or Redis needed — pure functions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.outbox import relay
from framework.triggers import envelope


# ---------------------------------------------------------------------------
# The mapping functions in isolation
# ---------------------------------------------------------------------------

class TestEffectiveMapping:
    def test_block_new_blocked_maps_new_to_blocked(self):
        # block: status unchanged (wip), blocked false -> true
        assert relay.effective_old_status("wip", False) == "wip"
        assert relay.effective_new_status("wip", True) == "blocked"

    def test_unblock_old_blocked_maps_old_to_blocked(self):
        # unblock: status unchanged (wip), blocked true -> false
        assert relay.effective_old_status("wip", True) == "blocked"
        assert relay.effective_new_status("wip", False) == "wip"

    def test_done_from_blocked_maps_old_to_blocked(self):
        # done-from-blocked: wip(blocked) -> done, blocked cleared
        assert relay.effective_old_status("wip", True) == "blocked"
        assert relay.effective_new_status("done", False) == "done"

    def test_cancel_from_blocked_maps_old_to_blocked(self):
        # cancel-from-blocked: wip(blocked) -> cancelled, blocked cleared
        assert relay.effective_old_status("wip", True) == "blocked"
        assert relay.effective_new_status("cancelled", False) == "cancelled"

    def test_insert_arm_null_old_status_maps_to_empty(self):
        # INSERT arm: old_status NULL, old_blocked NULL -> ''
        assert relay.effective_old_status(None, None) == ""

    def test_old_blocked_true_wins_over_raw_old_status(self):
        # old_blocked overlay dominates any raw old_status
        assert relay.effective_old_status("queue", True) == "blocked"

    def test_normal_transition_passes_raw_through(self):
        # queue -> wip (no blocked overlay either side)
        assert relay.effective_old_status("queue", False) == "queue"
        assert relay.effective_new_status("wip", False) == "wip"


# ---------------------------------------------------------------------------
# The mapped payload rides a schema-LEGAL v2 envelope (round-trip)
# ---------------------------------------------------------------------------

def _row(old_status, new_status, old_blocked, new_blocked, **over):
    base = {
        "id": 7, "idempotency_key": "task:42:1000:x:false", "event_id": None,
        "task_id": 42, "old_status": old_status, "new_status": new_status,
        "old_blocked": old_blocked, "new_blocked": new_blocked,
        "blocked_reason": None, "actor": "cos", "context_slug": "cog1",
        "cabinet_id": "cog1-harness",
        "correlation_id": "0123456789abcdef0123456789abcdef",
        "causation_id": None,
        "occurred_at": "2026-07-21T10:00:00Z",
    }
    base.update(over)
    return base


class TestMappedEnvelopeIsValid:
    EID = "01J0000000000000000000000A"  # 26-char Crockford ULID
    RECORDED = "2026-07-21T10:00:05Z"

    def _build(self, old_status, new_status, old_blocked, new_blocked, **over):
        row = _row(old_status, new_status, old_blocked, new_blocked, **over)
        # occurred_at may be a str or datetime; both must serialize UTC-second.
        return relay.build_dispatch_fields(
            row, event_id=self.EID, recorded_at=self.RECORDED)

    def test_block_case_envelope_valid_and_flat_effective(self):
        flat, env = self._build("wip", "wip", False, True)
        ok, reasons = envelope.validate_v2(env)
        assert ok, reasons
        assert flat["old_status"] == "wip" and flat["new_status"] == "blocked"
        assert env["payload"]["old_status"] == "wip"
        assert env["payload"]["new_status"] == "blocked"
        # the flat envelope field is the SAME v2 object (payload nested)
        assert json.loads(flat["envelope"])["payload"]["new_status"] == "blocked"

    def test_unblock_case_envelope_valid_and_flat_effective(self):
        flat, env = self._build("wip", "wip", True, False)
        ok, reasons = envelope.validate_v2(env)
        assert ok, reasons
        assert flat["old_status"] == "blocked" and flat["new_status"] == "wip"
        assert env["payload"]["old_status"] == "blocked"

    def test_done_from_blocked_case_envelope_valid(self):
        flat, env = self._build("wip", "done", True, False)
        ok, reasons = envelope.validate_v2(env)
        assert ok, reasons
        assert flat["old_status"] == "blocked" and flat["new_status"] == "done"

    def test_cancel_from_blocked_case_envelope_valid(self):
        flat, env = self._build("wip", "cancelled", True, False)
        ok, reasons = envelope.validate_v2(env)
        assert ok, reasons
        assert flat["old_status"] == "blocked" and flat["new_status"] == "cancelled"

    def test_insert_arm_case_envelope_valid_empty_old(self):
        flat, env = self._build(None, "queue", None, False)
        ok, reasons = envelope.validate_v2(env)
        assert ok, reasons
        assert flat["old_status"] == "" and flat["new_status"] == "queue"
        assert env["payload"]["old_status"] == ""

    def test_envelope_carries_pinned_v2_fields(self):
        _, env = self._build("wip", "wip", False, True)
        assert env["schema_version"] == envelope.V2_SCHEMA_VERSION
        assert env["event_type"] == "tasks.status_changed"
        assert env["payload_schema"] == "tasks/task-event@1"
        assert env["scope_kind"] == "cabinet"
        assert "lane_id" not in env and "project_id" not in env
        assert env["producer"] == "officer_tasks/outbox-relay"
        assert env["event_id"] == self.EID
        assert env["occurred_at"] == "2026-07-21T10:00:00Z"
        assert env["recorded_at"] == self.RECORDED
        assert env["classification"] in envelope.TAINT_TIERS

    def test_flat_fields_are_task_event_value_compatible(self):
        # the shape task-events-watch.py consumes: envelope + the 6 flat cols
        flat, _ = self._build("wip", "wip", False, True)
        assert set(flat) == {"envelope", "task_id", "old_status", "new_status",
                             "actor", "context_slug", "ts"}
        assert flat["task_id"] == "42"  # numeric-as-str (task_event_emit shape)

    def test_null_context_slug_flat_is_empty_string(self):
        flat, env = self._build("wip", "wip", False, True, context_slug=None)
        assert flat["context_slug"] == ""          # never the literal "None"
        assert env["payload"]["context_slug"] is None
