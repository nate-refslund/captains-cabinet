"""Comms C0 — the Telegram primitives (pins, forum topics, message effects,
thread routing) added for the foundational Comms MCP (spec
docs/plans/cabinet-comms-mcp-spec-2026-07-09.md §5/§8). Same gate + scrub +
fake-http_post discipline as the P3 channel tests."""
from framework import env
from framework.frontdoor import channel
from framework.frontdoor.tests.test_channel_p3 import (
    RecordingPost, _runtime)  # reuse harness


def _payload(post):
    return post.calls[-1]["data"]


class TestPin:
    def test_pin_gates_in_dev(self, monkeypatch):
        monkeypatch.setattr(env, "allow_sends", lambda: False)
        assert channel.pin(968)["status"] == "blocked-dev"

    def test_pin_posts_pinchatmessage_silent(self, monkeypatch):
        _runtime(monkeypatch)
        monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: None)
        monkeypatch.setattr(channel.time, "sleep", lambda *a, **k: None)
        post = RecordingPost()
        r = channel.pin(968, http_post=post)
        assert r["sent"] and "pinChatMessage" in post.calls[-1]["url"]
        d = _payload(post)
        assert d["message_id"] == 968 and d["disable_notification"] is True

    def test_unpin_with_and_without_id(self, monkeypatch):
        _runtime(monkeypatch)
        monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: None)
        monkeypatch.setattr(channel.time, "sleep", lambda *a, **k: None)
        post = RecordingPost()
        channel.unpin(968, http_post=post)
        assert _payload(post).get("message_id") == 968
        channel.unpin(http_post=post)
        assert "message_id" not in _payload(post)   # unpins most-recent
        assert "unpinChatMessage" in post.calls[-1]["url"]


class TestForumTopic:
    def test_open_thread_returns_thread_id(self, monkeypatch):
        _runtime(monkeypatch)
        monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: None)
        monkeypatch.setattr(channel.time, "sleep", lambda *a, **k: None)
        post = RecordingPost(response={"ok": True,
                                       "result": {"message_thread_id": 77, "name": "polads"}})
        r = channel.open_thread("polads", http_post=post)
        assert r["sent"] and "createForumTopic" in post.calls[-1]["url"]
        assert r["thread_id"] == 77
        assert _payload(post)["name"] == "polads"

    def test_open_thread_gates_in_dev(self, monkeypatch):
        monkeypatch.setattr(env, "allow_sends", lambda: False)
        assert channel.open_thread("x")["status"] == "blocked-dev"


class TestSendRouting:
    def test_send_thread_id_and_effect_in_payload(self, monkeypatch):
        _runtime(monkeypatch)
        monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: None)
        monkeypatch.setattr(channel.time, "sleep", lambda *a, **k: None)
        post = RecordingPost()
        channel.send("lane card", thread_id=77, effect_id="5104841245755180586",
                     http_post=post)
        d = _payload(post)
        assert d["message_thread_id"] == 77
        assert d["message_effect_id"] == "5104841245755180586"

    def test_send_without_new_kwargs_is_unchanged(self, monkeypatch):
        _runtime(monkeypatch)
        monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: None)
        monkeypatch.setattr(channel.time, "sleep", lambda *a, **k: None)
        post = RecordingPost()
        channel.send("plain", http_post=post)
        d = _payload(post)
        assert "message_thread_id" not in d and "message_effect_id" not in d
