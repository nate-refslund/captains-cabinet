"""Observe-only Captain comms: current-message-only, fixed recipient, dev-safe."""

from __future__ import annotations

import json

import framework.env as env
from framework.frontdoor import channel


class RecordingPost:
    def __init__(self):
        self.calls = []

    def __call__(self, url, data):
        self.calls.append((url, data))
        return {"ok": True, "result": {"message_id": 9001}}


def _observe_dev(monkeypatch):
    monkeypatch.setenv("CABINET_OBSERVE_ONLY", "1")
    monkeypatch.setenv("CABINET_ENV", "dev")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:observe-secret")
    monkeypatch.delenv("TELEGRAM_COS_TOKEN", raising=False)
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", "4242")
    monkeypatch.setattr(env, "allow_sends", lambda: False)
    monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: 777)


def test_reply_current_is_the_only_persisted_send_in_observe_dev(monkeypatch):
    _observe_dev(monkeypatch)
    post = RecordingPost()

    ordinary = channel.send("arbitrary new message", http_post=post)
    assert ordinary == {"status": "blocked-dev", "sent": False}
    assert post.calls == []

    reply = channel.reply_current_observe_only("bounded reply", http_post=post)
    assert reply["sent"] is True
    _, payload = post.calls[-1]
    assert payload["chat_id"] == "4242"
    assert payload["reply_parameters"] == {
        "message_id": 777,
        "allow_sending_without_reply": True,
    }
    assert "observe-secret" not in repr(reply)


def test_react_current_uses_watchdog_message_and_fixed_chat(monkeypatch):
    _observe_dev(monkeypatch)
    post = RecordingPost()
    result = channel.react_current_observe_only("👀", http_post=post)
    assert result["sent"] is True
    _, payload = post.calls[-1]
    assert payload["chat_id"] == "4242"
    assert payload["message_id"] == 777
    assert json.loads(payload["reaction"]) == [{"type": "emoji", "emoji": "👀"}]


def test_current_door_refuses_outside_exact_observe_dev_posture(monkeypatch):
    post = RecordingPost()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:secret")
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", "4242")
    monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: 777)

    monkeypatch.delenv("CABINET_OBSERVE_ONLY", raising=False)
    monkeypatch.setattr(env, "allow_sends", lambda: False)
    assert channel.reply_current_observe_only("x", http_post=post)["sent"] is False

    monkeypatch.setenv("CABINET_OBSERVE_ONLY", "1")
    monkeypatch.setattr(env, "allow_sends", lambda: True)
    assert channel.react_current_observe_only("👀", http_post=post)["sent"] is False
    assert post.calls == []


def test_current_door_refuses_without_watchdog_anchor(monkeypatch):
    _observe_dev(monkeypatch)
    monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: None)
    post = RecordingPost()
    result = channel.reply_current_observe_only("x", http_post=post)
    assert result["sent"] is False
    assert result["error"] == "no current Captain inbound message"
    assert post.calls == []


def test_current_door_rejects_multi_message_reply_without_network(monkeypatch):
    _observe_dev(monkeypatch)
    post = RecordingPost()
    result = channel.reply_current_observe_only("x" * 3901, http_post=post)
    assert result["sent"] is False
    assert "one message" in result["error"]
    assert post.calls == []


def test_current_door_rejects_unsupported_reaction_without_network(monkeypatch):
    _observe_dev(monkeypatch)
    post = RecordingPost()
    result = channel.react_current_observe_only("👀👀", http_post=post)
    assert result["sent"] is False
    assert result["error"] == "unsupported Telegram reaction"
    assert post.calls == []
