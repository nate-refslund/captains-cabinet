"""Audit #50/#33 — intake.ack() must never evict an undelivered captain item.

``ack()`` used to do a blind ``XTRIM key MAXLEN ~1000``. MAXLEN is unsafe under
a consumer group: it knows nothing about the pending-entry list. Under a
Telegram-dark backlog >1000, the first drain+ack would discard everything older
than the newest ~1000 — INCLUDING never-delivered captain-bound items. The fix
trims to a MINID boundary (oldest-pending id, else the group's
last-delivered-id) and only when the stream has exactly the ``frontdoor`` group.

Unit tests pin the boundary logic (no Redis). The integration test (Redis
required) proves the real hole is closed: 1500 undelivered items, drain+ack the
first 100, and 101-1500 SURVIVE. A MUTANT that restores ``xtrim(key, _MAXLEN)``
drops >500 of them and turns the integration test red.

Run (with Redis): REDIS_HOST=localhost python3.12 -m pytest \
    framework/frontdoor/tests/test_intake_safe_trim.py -q
"""
from __future__ import annotations

import os
import subprocess
import uuid

import pytest

from framework.frontdoor import intake


# ---------------------------------------------------------------------------
# Unit — _safe_trim boundary logic against a recording fake backend (no Redis)
# ---------------------------------------------------------------------------
class _FakeBackend:
    def __init__(self, groups, pending_min):
        self._groups = groups
        self._pending_min = pending_min
        self.trimmed = None  # captures the xtrim_minid boundary, or None

    def xinfo_groups(self, key):
        return self._groups

    def xpending_min(self, key, group):
        return self._pending_min

    def xtrim_minid(self, key, minid):
        self.trimmed = minid


def test_safe_trim_prefers_oldest_pending():
    b = _FakeBackend([{"name": "frontdoor", "last-delivered-id": "9-0"}], "3-0")
    intake._safe_trim(b, "k")
    assert b.trimmed == "3-0"  # oldest PENDING, never the newer last-delivered


def test_safe_trim_falls_back_to_last_delivered_when_pel_empty():
    b = _FakeBackend([{"name": "frontdoor", "last-delivered-id": "9-0"}], None)
    intake._safe_trim(b, "k")
    assert b.trimmed == "9-0"


def test_safe_trim_skips_when_a_second_group_exists():
    b = _FakeBackend(
        [{"name": "frontdoor", "last-delivered-id": "9-0"},
         {"name": "observer", "last-delivered-id": "2-0"}], "3-0")
    intake._safe_trim(b, "k")
    assert b.trimmed is None  # a 2nd reader may be unread at that boundary


def test_safe_trim_skips_foreign_single_group():
    b = _FakeBackend([{"name": "not-frontdoor", "last-delivered-id": "9-0"}], "3-0")
    intake._safe_trim(b, "k")
    assert b.trimmed is None


def test_safe_trim_skips_zero_boundary():
    b = _FakeBackend([{"name": "frontdoor", "last-delivered-id": "0-0"}], None)
    intake._safe_trim(b, "k")
    assert b.trimmed is None


def test_safe_trim_noops_on_probe_failure():
    class _Boom:
        def xinfo_groups(self, key):
            raise RuntimeError("redis down")
    intake._safe_trim(_Boom(), "k")  # must not raise


# ---------------------------------------------------------------------------
# Integration — the real hole, against a live Redis
# ---------------------------------------------------------------------------
def _redis_up() -> bool:
    try:
        return intake._redis().ping()
    except Exception:
        return False


redis_required = pytest.mark.skipif(
    not _redis_up(),
    reason="redis-cli cannot reach a Redis server (set REDIS_HOST=localhost)")

_HOST = os.environ.get("REDIS_HOST", "redis")
_PORT = os.environ.get("REDIS_PORT", "6379")


@pytest.fixture
def stream_key():
    key = f"cabinet:frontdoor:intake:test:{uuid.uuid4()}"
    assert key != "cabinet:frontdoor:intake"
    yield key
    try:
        intake._redis().delete(key)
    except Exception:
        pass


def _bulk_xadd(key: str, n: int) -> None:
    """Seed n items directly on the stream (fast, one redis-cli process). The
    'item' field is compact JSON so intake._rehydrate round-trips it; the JSON
    is single-quoted so redis-cli's inline parser treats it as ONE argument
    (its double-quotes would otherwise split the value)."""
    cmds = "".join(f"XADD {key} * item '{{\"c\":{i}}}'\n" for i in range(n))
    proc = subprocess.run(
        ["redis-cli", "-h", _HOST, "-p", _PORT],
        input=cmds, text=True, capture_output=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    # every XADD must have returned a stream id (never an "Invalid argument")
    assert "Invalid" not in proc.stdout, proc.stdout[:200]


@redis_required
def test_backlog_ack_preserves_undelivered_items(stream_key):
    n = 1500  # a Telegram-dark backlog well past the retired _MAXLEN=1000
    _bulk_xadd(stream_key, n)

    # drain+ack only the first 100 (the Chair processes a batch)
    first = intake.drain(stream_key=stream_key, count=100)
    assert len(first) == 100
    assert intake.ack([r["id"] for r in first], stream_key=stream_key) == 100

    # the 1400 NEVER-DELIVERED items (101..1500) must all survive the trim —
    # a blind MAXLEN~1000 would have dropped >400 of them.
    survivors = {r["c"] for r in intake.drain(stream_key=stream_key, count=5000)}
    assert len(survivors) == n - 100
    assert 100 in survivors            # first undelivered item retained
    assert (n - 1) in survivors        # newest retained


@redis_required
def test_ack_still_trims_the_processed_prefix(stream_key):
    """No unbounded growth: the acked+delivered prefix IS trimmed (the boundary
    is retained, older acked entries go)."""
    _bulk_xadd(stream_key, 300)
    first = intake.drain(stream_key=stream_key, count=200)
    intake.ack([r["id"] for r in first], stream_key=stream_key)
    xlen = int(subprocess.run(
        ["redis-cli", "-h", _HOST, "-p", _PORT, "XLEN", stream_key],
        text=True, capture_output=True, timeout=10).stdout.strip())
    # 300 total, ~199 older-than-boundary acked entries trimmed -> ~101 remain
    assert xlen < 300
    assert xlen >= 100  # the 100 undelivered survive
