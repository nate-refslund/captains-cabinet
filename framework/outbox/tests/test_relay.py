"""Tests for the transactional outbox relay."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, _ROOT)

from framework.outbox.relay import (
    queue,
    dispatch_pending,
    dispatch_one,
    register_adapter,
    _pending_queue,
    _already_processed_ids,
    _ADAPTERS,
)
from framework.events.emitter import emit, replay


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Route each test to a fresh event log; preserve adapters across tests."""
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Restore the adapter registry to a known minimal state after each test.
    # We don't share registrations across tests so each one explicitly sets up
    # what it needs.
    saved_adapters = dict(_ADAPTERS)
    yield
    _ADAPTERS.clear()
    _ADAPTERS.update(saved_adapters)


# ---------------------------------------------------------------------------
# queue()
# ---------------------------------------------------------------------------


class TestQueue:
    def test_emits_outbox_queued_event(self):
        qid = queue(destination="stub", payload={"foo": "bar"}, actor="cos")
        events = replay(event_types=["outbox_queued"])
        assert len(events) == 1
        assert events[0]["id"] == qid
        assert events[0]["actor"] == "cos"
        assert events[0]["payload"]["destination"] == "stub"
        assert events[0]["payload"]["payload"] == {"foo": "bar"}

    def test_idempotency_key_dedupes(self):
        first = queue("stub", {"x": 1}, actor="cos", idempotency_key="op-001")
        second = queue("stub", {"x": 2}, actor="cos", idempotency_key="op-001")
        # second call returns the original event id and does NOT emit a new event
        assert first == second
        events = replay(event_types=["outbox_queued"])
        assert len(events) == 1

    def test_no_idempotency_key_allows_duplicates(self):
        q1 = queue("stub", {"x": 1}, actor="cos")
        q2 = queue("stub", {"x": 1}, actor="cos")
        assert q1 != q2
        events = replay(event_types=["outbox_queued"])
        assert len(events) == 2


# ---------------------------------------------------------------------------
# dispatch_one + dispatch_pending
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_stub_adapter_dispatches_successfully(self):
        queue("stub", {"foo": "bar"}, actor="cos")
        counts = dispatch_pending()
        assert counts == {"dispatched": 1, "failed": 0, "skipped": 0}
        assert len(replay(event_types=["outbox_dispatched"])) == 1

    def test_unknown_destination_marked_terminal(self):
        queue("does-not-exist", {"foo": "bar"}, actor="cos")
        counts = dispatch_pending()
        assert counts == {"dispatched": 0, "failed": 0, "skipped": 1}
        failed = replay(event_types=["outbox_failed"])
        assert len(failed) == 1
        assert failed[0]["payload"]["terminal"] is True
        assert "no adapter" in failed[0]["payload"]["error"].lower()

    def test_already_dispatched_not_re_dispatched(self):
        queue("stub", {"foo": "bar"}, actor="cos")
        first = dispatch_pending()
        assert first["dispatched"] == 1

        # Second cycle — nothing pending
        second = dispatch_pending()
        assert second == {"dispatched": 0, "failed": 0, "skipped": 0}

    def test_transient_failure_retries_next_cycle(self):
        attempts = {"count": 0}

        def flaky(payload):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("network blip")
            # Second attempt succeeds

        register_adapter("flaky", flaky)
        queue("flaky", {"x": 1}, actor="cos")

        first = dispatch_pending()
        assert first == {"dispatched": 0, "failed": 1, "skipped": 0}
        # Transient — not terminal, so it should still be pending
        assert len(_pending_queue()) == 1

        second = dispatch_pending()
        assert second == {"dispatched": 1, "failed": 0, "skipped": 0}
        assert attempts["count"] == 2

    def test_payload_reaches_adapter_unchanged(self):
        captured = {}

        def recorder(payload):
            captured.update(payload)

        register_adapter("recorder", recorder)
        queue("recorder", {"a": 1, "b": "two", "c": [1, 2, 3]}, actor="cto")
        dispatch_pending()
        assert captured == {"a": 1, "b": "two", "c": [1, 2, 3]}


# ---------------------------------------------------------------------------
# pending tracking
# ---------------------------------------------------------------------------


class TestPendingTracking:
    def test_pending_queue_is_oldest_first(self):
        qids = [queue("stub", {"i": i}, actor="cos") for i in range(3)]
        pending = _pending_queue()
        assert [ev["id"] for ev in pending] == qids

    def test_processed_set_includes_dispatched(self):
        qid = queue("stub", {"x": 1}, actor="cos")
        dispatch_pending()
        assert qid in _already_processed_ids()

    def test_processed_set_includes_terminal_failures(self):
        qid = queue("does-not-exist", {"x": 1}, actor="cos")
        dispatch_pending()
        assert qid in _already_processed_ids()  # terminal failure

    def test_processed_set_excludes_transient_failures(self):
        def always_fail(payload):
            raise RuntimeError("oops")

        register_adapter("transient_fail", always_fail)
        qid = queue("transient_fail", {"x": 1}, actor="cos")
        dispatch_pending()
        # Transient failure → still pending → not in processed
        assert qid not in _already_processed_ids()
        assert qid in {ev["id"] for ev in _pending_queue()}
