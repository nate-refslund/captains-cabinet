"""COG-1 W3 — relay-side vocabulary fencing + legacy-path fixes (§6.2, §7).

Three writer families share the outbox_* central vocabulary; any parity metric
double-counts until fenced. This file pins the RELAY-side half of the fence
(the task_sync_runner.py discriminator and the parity arithmetic live in other
waves):

  * §6.2 — queue() stamps payload["queued_by"] = "framework.outbox.relay"; the
    legacy ledger drain processes ONLY marker-bearing rows and SKIPS non-marker
    rows (a counted foreign-rows telemetry, NOT a terminal failure) — this
    mechanically neutralizes task_sync's historical orphan outbox_queued rows.
  * §6.2 — queue()'s check-then-emit dedupe is wrapped in a module flock
    (scan+emit atomic for the legacy single-host path).
  * §6.1 step 4 / §7 item 4 — the table drain emits ZERO central-ledger events
    (no outbox_queued/dispatched/failed for table rows); its only telemetry is
    the parity JSONL. The pilot's metrics never touch the shared vocabulary.

The legacy dispatch_pending() return contract ({dispatched, failed, skipped})
is preserved EXACTLY — presets/*/measurement/role_evals/coo_outbox_*.py assert
that dict shape and are out of this wave's file-set.

The marker/flock tests use the event ledger only (fast, no Postgres); the
zero-central-ledger-emit test drives a real 047 table drain (PG17 + redis).
"""
from __future__ import annotations

import importlib.util as _ilu
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = str(_HERE.parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_spec = _ilu.spec_from_file_location("lib_relay_harness", _HERE / "lib_relay_harness.py")
HR = _ilu.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(HR)

from framework.outbox import relay
from framework.outbox.relay import (
    queue, dispatch_pending, _pending_queue, _foreign_ledger_rows,
    register_table_adapter, _TABLE_ADAPTERS, QUEUED_BY_MARKER,
)
from framework.events.emitter import emit, replay

CAB_ID = HR.CAB_ID
SHADOW = relay.SHADOW_STREAM


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    saved = dict(_TABLE_ADAPTERS)
    yield
    _TABLE_ADAPTERS.clear()
    _TABLE_ADAPTERS.update(saved)


# ===========================================================================
# §6.2 — queue() stamps the marker; the legacy drain fences non-marker rows
# ===========================================================================

class TestLegacyMarkerFence:
    def test_queue_stamps_queued_by_marker(self):
        qid = queue("stub", {"x": 1}, actor="cos")
        ev = replay(event_types=["outbox_queued"])[0]
        assert ev["payload"]["queued_by"] == QUEUED_BY_MARKER == "framework.outbox.relay"

    def test_non_marker_row_is_not_pending_and_is_counted_foreign(self):
        # A foreign writer (e.g. task_sync_runner) emits an adapter-less
        # outbox_queued with NO queued_by marker.
        emit("outbox_queued", actor="task_sync_runner",
             payload={"destination": "noop", "kind": "task_sync_telemetry"})
        # A real relay queue (marker-bearing).
        qid = queue("stub", {"y": 2}, actor="cos")
        pending = _pending_queue()
        assert [ev["id"] for ev in pending] == [qid], \
            "only marker-bearing rows are drained"
        foreign = _foreign_ledger_rows()
        assert len(foreign) == 1 and foreign[0]["actor"] == "task_sync_runner"

    def test_foreign_row_is_skipped_not_terminal_failed(self):
        emit("outbox_queued", actor="task_sync_runner",
             payload={"destination": "noop", "kind": "task_sync_telemetry"})
        counts = dispatch_pending()
        # legacy 3-key contract preserved; the foreign row is neither
        # dispatched nor terminal-failed — it is simply never drained.
        assert counts == {"dispatched": 0, "failed": 0, "skipped": 0}
        assert replay(event_types=["outbox_failed"]) == [], \
            "foreign rows are skipped, never terminal-failed (no orphan noise)"
        assert replay(event_types=["outbox_dispatched"]) == []

    def test_marked_row_still_dispatches_normally(self):
        queue("stub", {"z": 3}, actor="cos")
        emit("outbox_queued", actor="task_sync_runner",
             payload={"destination": "noop", "kind": "task_sync_telemetry"})
        counts = dispatch_pending()
        assert counts == {"dispatched": 1, "failed": 0, "skipped": 0}

    def test_dispatch_pending_return_is_the_frozen_three_key_contract(self):
        # presets/*/coo_outbox_*.py pin this exact shape — never widen it.
        queue("stub", {"a": 1}, actor="cos")
        counts = dispatch_pending()
        assert set(counts) == {"dispatched", "failed", "skipped"}


# ===========================================================================
# §6.2 — queue() dedupe scan+emit runs under a flock (single-host race fix)
# ===========================================================================

class TestQueueFlock:
    def test_idempotency_key_dedupes_under_the_flock(self):
        first = queue("stub", {"x": 1}, actor="cos", idempotency_key="op-1")
        second = queue("stub", {"x": 2}, actor="cos", idempotency_key="op-1")
        assert first == second
        assert len(replay(event_types=["outbox_queued"])) == 1

    def test_flock_path_is_colocated_with_the_ledger(self):
        # the lock file must sit beside the event ledger (per-sandbox), never a
        # shared global path that would serialize unrelated test runs.
        import framework.events.emitter as em
        lock = relay._queue_lock_path()
        assert str(em._event_log_dir()) in str(lock)


# ===========================================================================
# §7 item 4 / §6.1 step 4 — the table drain emits ZERO central-ledger events
# ===========================================================================

@pytest.mark.skipif(not (HR.pg_available() and HR.redis_available()),
                    reason="table-drain fence needs PG17 + redis")
class TestTableDrainVocabularyFence:
    def test_table_drain_writes_no_central_ledger_events(self, tmp_path_factory,
                                                         monkeypatch):
        c = HR.EphemeralPG17(tmp_path_factory.mktemp("cog1fence"), cabinet_id=CAB_ID)
        sb = HR.RedisSandbox().start()
        try:
            c.start()
            c.apply_base_chain()
            c.apply_identity_guc(CAB_ID)
            c.apply_047()
            for k, v in sb.env().items():
                monkeypatch.setenv(k, v)
            HR.seed_transition(c, "start", "cos", title="fence probe")
            counts = relay.drain_tasks_outbox(c.conninfo(), cabinet_id=CAB_ID)
            assert counts["dispatched"] == 1
            assert sb.xlen(SHADOW) == 1
            # the extension must NOT become the fourth outbox_* writer family
            for et in ("outbox_queued", "outbox_dispatched", "outbox_failed"):
                assert replay(event_types=[et]) == [], \
                    f"table drain leaked a central-ledger {et} event (§7 fence)"
        finally:
            sb.stop()
            c.stop()


# ===========================================================================
# §9.2 — register_table_adapter is the sanctioned framework-side seam
# ===========================================================================

class TestTableAdapterRegistry:
    def test_register_and_resolve_table_adapter(self):
        calls = []

        def rec(fields, *, idempotency_key):
            calls.append(idempotency_key)

        register_table_adapter("recorder", rec)
        assert _TABLE_ADAPTERS["recorder"] is rec
        # invocation carries the idempotency token (§6.1)
        _TABLE_ADAPTERS["recorder"]({"task_id": "1"}, idempotency_key="tok-9")
        assert calls == ["tok-9"]

    def test_stream_is_a_builtin_table_adapter_for_the_shadow(self):
        assert "stream" in _TABLE_ADAPTERS
