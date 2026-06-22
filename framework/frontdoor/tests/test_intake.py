"""Tests for framework.frontdoor.intake — durable Redis-Streams intake queue.

TDD-first. These tests use a UNIQUE test-prefixed stream key per test
(cabinet:frontdoor:intake:test:<uuid4>) and DEL/XTRIM it in teardown; they
NEVER touch the production key (cabinet:frontdoor:intake). If redis-cli cannot
reach a server (ping fails), the Redis-backed tests SKIP — fakeredis is not
installed. The pure validate_item() coverage runs unconditionally.

Connection mirrors triggers.sh: REDIS_HOST (default 'redis'), REDIS_PORT
(default 6379). In CI/dev where 'redis' does not resolve, run with
REDIS_HOST=localhost to actually exercise the Redis path.
"""
from __future__ import annotations

import uuid

import pytest

from framework.frontdoor import intake


# ---------------------------------------------------------------------------
# Redis availability guard — skip the durable tests if no server answers ping.
# ---------------------------------------------------------------------------
def _redis_up() -> bool:
    try:
        return intake._redis().ping()
    except Exception:
        return False


redis_required = pytest.mark.skipif(
    not _redis_up(),
    reason="redis-cli cannot reach a Redis server (set REDIS_HOST=localhost to run)",
)


@pytest.fixture
def stream_key():
    """A unique, test-only stream key with guaranteed teardown."""
    key = f"cabinet:frontdoor:intake:test:{uuid.uuid4()}"
    # Hard guard: never let a test point at production.
    assert key != "cabinet:frontdoor:intake"
    yield key
    try:
        intake._redis().delete(key)
    except Exception:
        pass


def _item(**over):
    base = {
        "source": "morning-brief",
        "kind": "brief",
        "ts": "2026-06-22T07:00:00Z",
        "urgency_tier": "batch",
        "payload": {"summary": "headline of the day", "detail": "more"},
        "context": {"why": "scheduled briefing", "sources": ["cron"],
                    "audience": None, "thread_ref": None},
        "correlation_id": "corr-1",
    }
    base.update(over)
    return base


# ===========================================================================
# validate_item — pure, no Redis. Fail-closed BEFORE enqueue.
# ===========================================================================
class TestValidateItem:
    def test_accepts_a_canonical_item(self):
        intake.validate_item(_item())  # must not raise

    @pytest.mark.parametrize("missing", ["source", "kind", "ts", "payload"])
    def test_rejects_missing_required_field(self, missing):
        bad = _item()
        del bad[missing]
        with pytest.raises(Exception):
            intake.validate_item(bad)

    def test_rejects_bad_urgency_tier(self):
        with pytest.raises(Exception):
            intake.validate_item(_item(urgency_tier="immediately"))

    def test_accepts_each_valid_urgency_tier(self):
        for tier in ("ping-now", "batch", "fyi"):
            intake.validate_item(_item(urgency_tier=tier))

    def test_rejects_payload_without_summary(self):
        with pytest.raises(Exception):
            intake.validate_item(_item(payload={"detail": "no summary"}))

    def test_rejects_non_dict_item(self):
        with pytest.raises(Exception):
            intake.validate_item("not a dict")


# ===========================================================================
# enqueue / drain / ack — durable round-trip (Redis-backed).
# ===========================================================================
@redis_required
class TestEnqueueDrainAck:
    def test_enqueue_returns_redis_id(self, stream_key):
        mid = intake.enqueue(_item(), stream_key=stream_key)
        assert isinstance(mid, str)
        # Redis stream id shape '<ms>-<seq>'
        assert "-" in mid

    def test_enqueue_validates_before_xadd(self, stream_key):
        with pytest.raises(Exception):
            intake.enqueue(_item(urgency_tier="nope"), stream_key=stream_key)
        # nothing should have landed
        assert intake.drain(stream_key=stream_key) == []

    def test_round_trips_exact_item_including_nested(self, stream_key):
        item = _item(
            payload={"summary": "s", "detail": {"nested": [1, 2, 3]},
                     "confidence": 0.7},
            context={"why": "w", "sources": ["a", "b"],
                     "audience": {"to": ["x"]}, "thread_ref": "t1"},
        )
        mid = intake.enqueue(item, stream_key=stream_key)
        got = intake.drain(stream_key=stream_key)
        assert len(got) == 1
        rec = got[0]
        # id is the Redis-assigned id and merged in
        assert rec["id"] == mid
        # every supplied field round-trips exactly
        for k, v in item.items():
            assert rec[k] == v

    def test_id_is_the_ack_key_and_ack_removes_from_pending(self, stream_key):
        mid = intake.enqueue(_item(), stream_key=stream_key)
        # first drain delivers it (and makes it pending)
        first = intake.drain(stream_key=stream_key)
        assert [r["id"] for r in first] == [mid]
        # it is now pending until ack'd
        assert [r["id"] for r in intake.drain_pending(stream_key=stream_key)] == [mid]
        acked = intake.ack(mid, stream_key=stream_key)
        assert acked == 1
        # no longer pending
        assert intake.drain_pending(stream_key=stream_key) == []

    def test_redrain_does_not_reyield_delivered(self, stream_key):
        intake.enqueue(_item(), stream_key=stream_key)
        first = intake.drain(stream_key=stream_key)
        assert len(first) == 1
        # a second '>' drain sees only NEW (undelivered) — none
        assert intake.drain(stream_key=stream_key) == []

    def test_ack_accepts_a_list_of_ids(self, stream_key):
        ids = [intake.enqueue(_item(correlation_id=f"c{i}"), stream_key=stream_key)
               for i in range(3)]
        drained = intake.drain(stream_key=stream_key)
        assert {r["id"] for r in drained} == set(ids)
        assert intake.ack(ids, stream_key=stream_key) == 3
        assert intake.drain_pending(stream_key=stream_key) == []

    def test_drain_pending_recovers_after_simulated_restart(self, stream_key):
        """A delivered-but-unacked item must be recoverable (crash recovery)."""
        mid = intake.enqueue(_item(), stream_key=stream_key)
        intake.drain(stream_key=stream_key)  # delivered, NOT acked (= crash)
        # "restart": a fresh consumer-group read of '>' sees nothing new...
        assert intake.drain(stream_key=stream_key) == []
        # ...but drain_pending recovers the un-acked work.
        pending = intake.drain_pending(stream_key=stream_key)
        assert [r["id"] for r in pending] == [mid]

    def test_drain_since_filters_by_ts(self, stream_key):
        old = _item(ts="2026-06-20T00:00:00Z", correlation_id="old")
        new = _item(ts="2026-06-22T12:00:00Z", correlation_id="new")
        intake.enqueue(old, stream_key=stream_key)
        intake.enqueue(new, stream_key=stream_key)
        got = intake.drain(since="2026-06-21T00:00:00Z", stream_key=stream_key)
        assert [r["correlation_id"] for r in got] == ["new"]

    def test_drain_returns_fully_rehydrated_dicts(self, stream_key):
        intake.enqueue(_item(), stream_key=stream_key)
        got = intake.drain(stream_key=stream_key)
        rec = got[0]
        assert isinstance(rec, dict)
        assert isinstance(rec["payload"], dict)
        assert isinstance(rec["context"], dict)

    def test_never_touches_production_key(self, stream_key, monkeypatch):
        """A sanity assertion: the default key is production and our tests
        always pass an explicit test stream_key."""
        assert intake._default_stream_key() == "cabinet:frontdoor:intake"
        # our fixture key is clearly namespaced under :test:
        assert ":test:" in stream_key
