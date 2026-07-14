"""A3 — Component 5: deferred-send veto window (block-then-redirect) [FIX-3].

`framework/authority/veto.py` is the queue producer + notifier + kill handler +
scan-sender for the internal-comms veto window. It NEVER sends directly — the
actual byte egress goes through the existing approved `queue_draft` backend
(brain-bridge.md: `queue_draft` is the ONLY outbound path). Here every external
dependency is INJECTED so tests use fakes: no real Redis, no real send, no real
clock.

These tests drive the four behaviors the spec names (design §Component 5):
  * enqueue -> scan sends once (TTL expiry → backend fired)
  * kill before TTL -> never sent (+ authority.gate_decision {killed:true})
  * double scan -> single send (idempotent: the `sent:` marker)
  * backend failure -> dead-letter, not a silent drop

See docs/authority-matrix-design-2026-06-19.md §Component 5 + the error-handling
inventory ("Veto-send backend failure → dead-letter, no silent drop").
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Repo root on sys.path so the framework package imports cleanly (same
# convention as the sibling authority/fidelity tests).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority import veto as V


# ---------------------------------------------------------------------------
# Test doubles — a minimal in-memory Redis-stream fake, a controllable clock,
# and a recording / failing send backend.
# ---------------------------------------------------------------------------


class FakeRedis:
    """A tiny in-memory stand-in for the Redis-stream + key surface veto uses.

    Implements only what veto.py needs: XADD / XLEN / XRANGE / XDEL on a single
    stream, plus SET-NX / GET / DELETE / EXISTS on flat keys (sent markers,
    dead-letter list). Stream entries are (id, {field: value}) tuples, kept in
    insertion order; ids are monotonic strings so range scans are deterministic.
    """

    def __init__(self):
        self.streams: dict[str, list] = {}
        self.kv: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self._seq = 0

    # --- stream ops -------------------------------------------------------
    def xadd(self, stream, fields, id="*"):
        self._seq += 1
        entry_id = f"{self._seq}-0" if id == "*" else id
        self.streams.setdefault(stream, []).append((entry_id, dict(fields)))
        return entry_id

    def xlen(self, stream):
        return len(self.streams.get(stream, []))

    def xrange(self, stream, min="-", max="+"):
        return list(self.streams.get(stream, []))

    def xdel(self, stream, *ids):
        s = self.streams.get(stream, [])
        before = len(s)
        keep = [(i, f) for (i, f) in s if i not in ids]
        self.streams[stream] = keep
        return before - len(keep)

    # --- flat key ops -----------------------------------------------------
    def set(self, key, value, nx=False):
        if nx and key in self.kv:
            return None
        self.kv[key] = value
        return True

    def get(self, key):
        return self.kv.get(key)

    def exists(self, key):
        return 1 if key in self.kv else 0

    def delete(self, key):
        self.ttls.pop(key, None)
        return 1 if self.kv.pop(key, None) is not None else 0

    def expire(self, key, ttl):
        if key in self.kv:
            self.ttls[key] = int(ttl)
            return 1
        return 0

    def rpush(self, key, value):
        self.kv.setdefault(key, [])
        if not isinstance(self.kv[key], list):
            self.kv[key] = []
        self.kv[key].append(value)
        return len(self.kv[key])

    def lrange(self, key, start, end):
        v = self.kv.get(key, [])
        if not isinstance(v, list):
            return []
        return list(v)


class FakeClock:
    """Controllable monotonic clock (epoch seconds)."""

    def __init__(self, t0=1000.0):
        self.t = float(t0)

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += float(seconds)


class RecordingBackend:
    """Records each send; the actual approved queue_draft backend is stubbed."""

    def __init__(self):
        self.calls = []

    def __call__(self, draft):
        self.calls.append(dict(draft))
        return True


class FailingBackend:
    """Always raises — exercises the dead-letter path."""

    def __init__(self):
        self.calls = 0

    def __call__(self, draft):
        self.calls += 1
        raise RuntimeError("backend down")


class RecordingEmitter:
    """Captures authority.gate_decision (and any) emitted records."""

    def __init__(self):
        self.events = []

    def __call__(self, event_type, payload):
        self.events.append((event_type, dict(payload)))
        return {"event_type": event_type, "payload": payload}


@pytest.fixture()
def redis():
    return FakeRedis()


@pytest.fixture()
def clock():
    return FakeClock()


@pytest.fixture()
def backend():
    return RecordingBackend()


@pytest.fixture()
def emitter():
    return RecordingEmitter()


def _payload():
    return {
        "officer": "cos",
        "recipient": "Bo",
        "body": "Confirming the booking automation ships today.",
        "action_type": "internal_message",
        "lane": "ops",
    }


# ---------------------------------------------------------------------------
# 1. enqueue
# ---------------------------------------------------------------------------


def test_enqueue_writes_one_stream_entry_with_send_at(redis, clock):
    draft_id = V.enqueue_veto(
        "cos", "ops", "internal_message", _payload(),
        window_minutes=7, redis=redis, clock=clock,
    )
    assert isinstance(draft_id, str) and draft_id
    assert redis.xlen(V.VETO_STREAM) == 1
    _id, fields = redis.xrange(V.VETO_STREAM)[0]
    # send_at = now + N*60 (clock at 1000, 7 min → 1420)
    assert float(fields["send_at"]) == 1000.0 + 7 * 60
    assert fields["officer"] == "cos"
    assert fields["lane"] == "ops"
    assert fields["action_type"] == "internal_message"
    assert fields["draft_id"] == draft_id


def test_enqueue_returns_unique_ids(redis, clock):
    a = V.enqueue_veto("cos", "ops", "internal_message", _payload(),
                       window_minutes=7, redis=redis, clock=clock)
    b = V.enqueue_veto("cos", "ops", "internal_message", _payload(),
                       window_minutes=7, redis=redis, clock=clock)
    assert a != b
    assert redis.xlen(V.VETO_STREAM) == 2


# ---------------------------------------------------------------------------
# 2. notifier (compose only — does NOT send)
# ---------------------------------------------------------------------------


def test_notify_composes_message_and_does_not_send(redis, clock, backend):
    draft_id = V.enqueue_veto("cos", "ops", "internal_message", _payload(),
                              window_minutes=7, redis=redis, clock=clock)
    msg = V.compose_veto_notice(draft_id, _payload(), window_minutes=7)
    assert draft_id in msg
    assert "kill" in msg.lower()
    assert "7" in msg
    assert "Bo" in msg
    # composing a notice must never fire the backend
    assert backend.calls == []


# ---------------------------------------------------------------------------
# 3. enqueue -> scan sends once (TTL expiry)
# ---------------------------------------------------------------------------


def test_scan_sends_after_send_at_via_backend(redis, clock, backend):
    draft_id = V.enqueue_veto("cos", "ops", "internal_message", _payload(),
                              window_minutes=7, redis=redis, clock=clock)
    # before expiry: nothing sent
    sent = V.scan_and_send(clock(), redis=redis, send_backend=backend)
    assert sent == []
    assert backend.calls == []
    assert redis.xlen(V.VETO_STREAM) == 1

    # after expiry: sent exactly once, entry removed
    clock.advance(7 * 60 + 1)
    sent = V.scan_and_send(clock(), redis=redis, send_backend=backend)
    assert sent == [draft_id]
    assert len(backend.calls) == 1
    assert backend.calls[0]["recipient"] == "Bo"
    assert redis.xlen(V.VETO_STREAM) == 0
    # the sent marker is durable
    assert redis.exists(V.sent_marker_key(draft_id))


# ---------------------------------------------------------------------------
# 4. kill before TTL -> not sent (+ gate_decision killed:true)
# ---------------------------------------------------------------------------


def test_kill_before_ttl_prevents_send_and_emits_gate_decision(
    redis, clock, backend, emitter
):
    draft_id = V.enqueue_veto("cos", "ops", "internal_message", _payload(),
                              window_minutes=7, redis=redis, clock=clock)
    killed = V.kill_draft(draft_id, redis=redis, emitter=emitter)
    assert killed is True
    assert redis.xlen(V.VETO_STREAM) == 0

    # gate_decision {killed:true} emitted
    assert len(emitter.events) == 1
    etype, payload = emitter.events[0]
    assert etype == "authority.gate_decision"
    assert payload["killed"] is True
    assert payload["action_type"] == "internal_message"
    assert payload["cell"] == ("cos", "ops", "internal_message")

    # a scan past TTL now sends nothing — the entry is gone
    clock.advance(7 * 60 + 1)
    sent = V.scan_and_send(clock(), redis=redis, send_backend=backend)
    assert sent == []
    assert backend.calls == []


def test_kill_unknown_draft_is_noop_no_emit(redis, emitter):
    killed = V.kill_draft("does-not-exist", redis=redis, emitter=emitter)
    assert killed is False
    assert emitter.events == []


# ---------------------------------------------------------------------------
# 5. double scan -> single send (idempotent)
# ---------------------------------------------------------------------------


def test_double_scan_sends_exactly_once(redis, clock, backend):
    V.enqueue_veto("cos", "ops", "internal_message", _payload(),
                   window_minutes=7, redis=redis, clock=clock)
    clock.advance(7 * 60 + 1)
    first = V.scan_and_send(clock(), redis=redis, send_backend=backend)
    second = V.scan_and_send(clock(), redis=redis, send_backend=backend)
    assert len(first) == 1
    assert second == []
    assert len(backend.calls) == 1  # NOT two — the sent marker held


def test_overlapping_scan_nx_loser_reaps_never_double_sends(clock, backend):
    """framework-core-2: two overlapping sweeps can both pass the exists()
    pre-check; the sweep that LOSES the SET NX claim must reap the entry
    instead of falling through and sending a second copy."""

    class RacedRedis(FakeRedis):
        # exists() reports 0 for everything — simulating the concurrent
        # winner claiming the marker AFTER this sweep's exists() ran.
        def exists(self, key):
            return 0

    redis = RacedRedis()
    draft_id = V.enqueue_veto("cos", "ops", "internal_message", _payload(),
                              window_minutes=7, redis=redis, clock=clock)
    # The concurrent winner already holds the marker (its SET NX won).
    redis.set(V.sent_marker_key(draft_id), "1")
    clock.advance(7 * 60 + 1)
    sent = V.scan_and_send(clock(), redis=redis, send_backend=backend)
    assert sent == []
    assert backend.calls == []          # the loser never fires the backend
    assert redis.xlen(V.VETO_STREAM) == 0  # ...but reaps its stale view


def test_sent_marker_carries_ttl(redis, clock, backend):
    """Success markers must not accumulate forever — the claim sets a TTL."""
    draft_id = V.enqueue_veto("cos", "ops", "internal_message", _payload(),
                              window_minutes=7, redis=redis, clock=clock)
    clock.advance(7 * 60 + 1)
    sent = V.scan_and_send(clock(), redis=redis, send_backend=backend)
    assert sent == [draft_id]
    assert redis.ttls.get(V.sent_marker_key(draft_id)) == V.SENT_MARKER_TTL_S


def test_scan_sends_even_if_expire_unsupported(clock, backend):
    """The marker TTL is hygiene only — an injected redis whose EXPIRE fails
    (or is missing) must never block the send itself."""

    class NoExpire(FakeRedis):
        def expire(self, key, ttl):
            raise RuntimeError("EXPIRE unsupported")

    redis = NoExpire()
    draft_id = V.enqueue_veto("cos", "ops", "internal_message", _payload(),
                              window_minutes=7, redis=redis, clock=clock)
    clock.advance(7 * 60 + 1)
    sent = V.scan_and_send(clock(), redis=redis, send_backend=backend)
    assert sent == [draft_id]
    assert len(backend.calls) == 1


def test_scan_skips_entry_already_marked_sent(redis, clock, backend):
    """Crash-safe: an entry whose sent marker exists but was not yet XDEL'd
    (process died between mark and delete) is never re-sent on the next scan."""
    draft_id = V.enqueue_veto("cos", "ops", "internal_message", _payload(),
                              window_minutes=7, redis=redis, clock=clock)
    # Simulate the mark-before-delete crash window: marker set, entry still present.
    redis.set(V.sent_marker_key(draft_id), "1")
    clock.advance(7 * 60 + 1)
    sent = V.scan_and_send(clock(), redis=redis, send_backend=backend)
    # backend must NOT fire; the stale entry is reaped without a second send.
    assert backend.calls == []
    assert draft_id not in sent
    assert redis.xlen(V.VETO_STREAM) == 0


# ---------------------------------------------------------------------------
# 6. backend failure -> dead-letter, not silent drop
# ---------------------------------------------------------------------------


def test_backend_failure_dead_letters_not_silent_drop(redis, clock):
    failing = FailingBackend()
    draft_id = V.enqueue_veto("cos", "ops", "internal_message", _payload(),
                              window_minutes=7, redis=redis, clock=clock)
    clock.advance(7 * 60 + 1)
    sent = V.scan_and_send(clock(), redis=redis, send_backend=failing)
    # not reported as sent
    assert sent == []
    assert failing.calls == 1
    # the failed draft is dead-lettered, never silently dropped
    dead = redis.lrange(V.DEAD_LETTER_KEY, 0, -1)
    assert any(draft_id in str(d) for d in dead)
    # and the original entry is removed from the live stream (moved to DLQ),
    # so a healthy backend on the next scan does not double-send the failure.
    assert redis.xlen(V.VETO_STREAM) == 0
    # no sent marker for a failed send
    assert not redis.exists(V.sent_marker_key(draft_id))


def test_backend_failure_one_bad_does_not_block_good(redis, clock):
    """A failing send for one draft must not prevent a sibling good send in the
    same scan — partial failure is isolated."""
    sometimes = _SelectiveBackend(fail_recipients={"Bo"})
    good_payload = {**_payload(), "recipient": "Lena"}
    bad_id = V.enqueue_veto("cos", "ops", "internal_message", _payload(),
                            window_minutes=7, redis=redis, clock=clock)
    good_id = V.enqueue_veto("cos", "ops", "internal_message", good_payload,
                             window_minutes=7, redis=redis, clock=clock)
    clock.advance(7 * 60 + 1)
    sent = V.scan_and_send(clock(), redis=redis, send_backend=sometimes)
    assert sent == [good_id]
    dead = redis.lrange(V.DEAD_LETTER_KEY, 0, -1)
    assert any(bad_id in str(d) for d in dead)
    assert redis.exists(V.sent_marker_key(good_id))
    assert not redis.exists(V.sent_marker_key(bad_id))


class _SelectiveBackend:
    def __init__(self, fail_recipients):
        self.fail_recipients = set(fail_recipients)
        self.calls = []

    def __call__(self, draft):
        self.calls.append(dict(draft))
        if draft.get("recipient") in self.fail_recipients:
            raise RuntimeError("recipient unreachable")
        return True


# ---------------------------------------------------------------------------
# 7. window source — N from the matrix bar when not passed explicitly
# ---------------------------------------------------------------------------


def test_default_window_minutes_reads_matrix_floor(redis, clock):
    """When window_minutes is omitted, the default comes from the authority
    matrix floor (veto_window_minutes, currently 7) — not a hardcoded literal."""
    draft_id = V.enqueue_veto("cos", "ops", "internal_message", _payload(),
                              redis=redis, clock=clock)
    _id, fields = redis.xrange(V.VETO_STREAM)[0]
    expected = 1000.0 + V.default_window_minutes() * 60
    assert float(fields["send_at"]) == expected
    assert V.default_window_minutes() == 7  # matches the shipped floor
    assert draft_id
