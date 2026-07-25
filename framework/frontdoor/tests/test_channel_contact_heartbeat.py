"""channel.py — the D1 outbound Captain-contact heartbeat.

THE PROPERTY UNDER TEST is not "a function got called". It is that the heartbeat
means what an off-machine watcher will assume it means: a message reached the
Captain's transport. So every arm here is about the boundary — the heartbeat
must fire on CONFIRMED delivery and must be unreachable from every path where
delivery did not happen. A heartbeat on a failed send is worse than no heartbeat
at all: it tells the watcher the cabinet is talking to its Captain while the lane
is dead, which suppresses exactly the alarm this whole detector exists to raise.

No network: http_post is always a mock, and the heartbeat emitter is stubbed at
``framework.liveness.deadman.emit`` (the root conftest additionally points
CABINET_LIVENESS_CONFIG at a non-existent file for the whole session).
"""
from __future__ import annotations

import pytest

import framework.env as env
import framework.frontdoor.channel as channel
from framework.liveness import deadman

TOKEN = "123456:SECRET-BOT-TOKEN-do-not-leak"
CAPTAIN = "98765432"


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch):
    monkeypatch.setattr(channel.time, "sleep", lambda *_a, **_k: None)


@pytest.fixture
def beats(monkeypatch):
    """Record every heartbeat the send path emits."""
    seen: list[str] = []

    def _fake_emit(event, **_kw):
        seen.append(event)
        return {"event": event, "emitted": True, "reason": "ok"}

    monkeypatch.setattr(deadman, "emit", _fake_emit)
    return seen


def _runtime(monkeypatch):
    monkeypatch.setattr(env, "allow_sends", lambda: True)
    monkeypatch.setenv("TELEGRAM_COS_TOKEN", TOKEN)
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", CAPTAIN)
    monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: None)


class _Post:
    """Mock http_post. ``fail_on`` is the 1-based call index that fails, so a
    multi-chunk partial failure can be driven deterministically."""

    def __init__(self, fail_on: int | None = None):
        self.calls = 0
        self._fail_on = fail_on

    def __call__(self, url, data):
        self.calls += 1
        if self._fail_on is not None and self.calls >= self._fail_on:
            raise RuntimeError("telegram HTTP 400")
        return {"ok": True, "result": {"message_id": 40 + self.calls}}


class TestFiresOnConfirmedDelivery:
    def test_successful_send_emits_exactly_one_outbound_heartbeat(
            self, monkeypatch, beats):
        _runtime(monkeypatch)
        res = channel.send("hello captain", http_post=_Post())
        assert res["sent"] is True
        assert beats == [deadman.EVENT_CAPTAIN_OUTBOUND]

    def test_multipart_send_emits_one_heartbeat_not_one_per_chunk(
            self, monkeypatch, beats):
        """The contact event is the MESSAGE, not the chunk — a long briefing
        must not inflate the watcher's view of how often contact happens."""
        _runtime(monkeypatch)
        post = _Post()
        res = channel.send("x" * 9000, http_post=post)
        assert res["sent"] is True
        assert post.calls > 1, "precondition: this text must split into chunks"
        assert beats == [deadman.EVENT_CAPTAIN_OUTBOUND]


class TestSilentWhenNothingWasDelivered:
    def test_dev_blocked_send_emits_no_heartbeat(self, monkeypatch, beats):
        """allow_sends() False means no bytes left the box. A heartbeat here
        would report contact from every developer's laptop."""
        monkeypatch.delenv("CABINET_ENV", raising=False)  # dev default
        monkeypatch.setenv("TELEGRAM_COS_TOKEN", TOKEN)
        monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", CAPTAIN)
        res = channel.send("hello", http_post=_Post())
        assert res["status"] == "blocked-dev"
        assert beats == []

    def test_unconfigured_transport_emits_no_heartbeat(self, monkeypatch, beats):
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        monkeypatch.delenv("TELEGRAM_COS_TOKEN", raising=False)
        monkeypatch.delenv("CAPTAIN_TELEGRAM_ID", raising=False)
        res = channel.send("hello", http_post=_Post())
        assert res["sent"] is False
        assert beats == []

    def test_failed_send_emits_no_heartbeat(self, monkeypatch, beats):
        """THE BUG-OF-RECORD SHAPE: the process runs, the send 400s. The
        watchdog once read this as delivered; the watcher never may."""
        _runtime(monkeypatch)
        res = channel.send("hello", http_post=_Post(fail_on=1))
        assert res["sent"] is False
        assert beats == []

    def test_partial_multipart_failure_emits_no_heartbeat(
            self, monkeypatch, beats):
        """Chunk 1 landed, chunk 2 did not. The Captain got a fragment, so the
        message was NOT delivered — and a fragment must not read as contact."""
        _runtime(monkeypatch)
        post = _Post(fail_on=2)
        res = channel.send("y" * 9000, http_post=post)
        assert res["sent"] is False
        assert res["sent_chunks"] == 1
        assert beats == []


class TestHeartbeatNeverCostsAMessage:
    def test_emitter_raising_does_not_break_a_delivered_send(self, monkeypatch):
        def _boom(_event, **_kw):
            raise RuntimeError("watcher exploded")

        monkeypatch.setattr(deadman, "emit", _boom)
        _runtime(monkeypatch)
        res = channel.send("hello", http_post=_Post())
        assert res["sent"] is True  # delivery already happened; nothing may undo it

    def test_import_failure_does_not_break_a_delivered_send(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def _no_liveness(name, *a, **k):
            if name.startswith("framework.liveness"):
                raise ImportError("liveness package missing")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", _no_liveness)
        _runtime(monkeypatch)
        res = channel.send("hello", http_post=_Post())
        assert res["sent"] is True


class TestUnconfiguredIsInertOnTheRealPath:
    def test_real_emitter_makes_no_network_call_when_unconfigured(
            self, monkeypatch, tmp_path):
        """End-to-end with the REAL emitter (not the stub): a deployment that
        has not configured a watcher must send with zero heartbeat traffic."""
        monkeypatch.setenv(deadman.CONFIG_ENV, str(tmp_path / "absent.yml"))
        opened: list = []
        monkeypatch.setattr(deadman, "_default_opener",
                            lambda url, timeout: opened.append(url))
        _runtime(monkeypatch)
        res = channel.send("hello", http_post=_Post())
        assert res["sent"] is True
        assert opened == []
