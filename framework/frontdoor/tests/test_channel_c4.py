"""Comms C4 — the streaming-draft ("Thinking…") + Rich Message primitives
(spec §8; Bot API sendMessageDraft 9.5/10.0, sendRichMessage 10.1). Same gate +
scrub + fake-http_post discipline as the P3/C0 channel tests."""
import json

from framework import env
from framework.frontdoor import channel
from framework.frontdoor.tests.test_channel_p3 import RecordingPost, _runtime


def _payload(post):
    return post.calls[-1]["data"]


class TestSendDraft:
    def test_gates_in_dev(self, monkeypatch):
        monkeypatch.setattr(env, "allow_sends", lambda: False)
        assert channel.send_draft(1)["status"] == "blocked-dev"

    def test_empty_text_is_thinking_placeholder(self, monkeypatch):
        _runtime(monkeypatch)
        monkeypatch.setattr(channel.time, "sleep", lambda *a, **k: None)
        post = RecordingPost()
        r = channel.send_draft(7, http_post=post)
        assert r["sent"] and "sendMessageDraft" in post.calls[-1]["url"]
        d = _payload(post)
        assert d["draft_id"] == 7 and d["text"] == ""   # empty ⇒ "Thinking…"

    def test_stream_reuses_draft_id_and_carries_text(self, monkeypatch):
        _runtime(monkeypatch)
        monkeypatch.setattr(channel.time, "sleep", lambda *a, **k: None)
        post = RecordingPost()
        channel.send_draft(7, "half a thought", thread_id=5, http_post=post)
        d = _payload(post)
        assert d["draft_id"] == 7 and d["text"] == "half a thought"
        assert d["message_thread_id"] == 5

    def test_zero_draft_id_coerced_nonzero(self, monkeypatch):
        _runtime(monkeypatch)
        monkeypatch.setattr(channel.time, "sleep", lambda *a, **k: None)
        post = RecordingPost()
        channel.send_draft(0, http_post=post)
        assert _payload(post)["draft_id"] == 1   # API requires non-zero


class TestSendRich:
    def test_gates_in_dev(self, monkeypatch):
        monkeypatch.setattr(env, "allow_sends", lambda: False)
        assert channel.send_rich(markdown="x")["status"] == "blocked-dev"

    def test_requires_exactly_one_body(self, monkeypatch):
        _runtime(monkeypatch)
        assert channel.send_rich()["status"] == "error"                      # neither
        assert channel.send_rich(markdown="a", html="b")["status"] == "error"  # both

    def test_posts_rich_message_json(self, monkeypatch):
        _runtime(monkeypatch)
        monkeypatch.setattr(channel.time, "sleep", lambda *a, **k: None)
        post = RecordingPost(response={"ok": True, "result": {"message_id": 314}})
        r = channel.send_rich(markdown="| a | b |\n|---|---|\n| 1 | 2 |", http_post=post)
        assert r["sent"] and "sendRichMessage" in post.calls[-1]["url"]
        assert r["message_ids"] == [314]
        rich = json.loads(_payload(post)["rich_message"])
        assert rich["markdown"].startswith("| a | b |") and "html" not in rich

    def test_html_body_routes_to_html_field(self, monkeypatch):
        _runtime(monkeypatch)
        monkeypatch.setattr(channel.time, "sleep", lambda *a, **k: None)
        post = RecordingPost(response={"ok": True, "result": {"message_id": 1}})
        channel.send_rich(html="<details><summary>x</summary>y</details>", http_post=post)
        rich = json.loads(_payload(post)["rich_message"])
        assert rich["html"].startswith("<details>") and "markdown" not in rich

    def test_journaled_as_rich(self, monkeypatch):
        _runtime(monkeypatch)
        monkeypatch.setattr(channel.time, "sleep", lambda *a, **k: None)
        rows = []
        import framework.attention.feed as feed
        monkeypatch.setattr(feed, "append_event", lambda row: rows.append(row))
        post = RecordingPost(response={"ok": True, "result": {"message_id": 9}})
        channel.send_rich(markdown="hi", http_post=post)
        assert rows and rows[-1]["kind"] == "rich" and rows[-1]["telegram_message_id"] == 9


class TestSendPollOptionShape:
    def test_options_are_inputpolloption_objects(self, monkeypatch):
        """Bot API 7.3+ requires options as InputPollOption objects ({"text": …}),
        not bare strings — a bare-string array is rejected (gauntlet HIGH)."""
        _runtime(monkeypatch)
        monkeypatch.setattr(channel.time, "sleep", lambda *a, **k: None)
        post = RecordingPost(response={"ok": True, "result": {"message_id": 5}})
        channel.send_poll("Ship it?", ["Ship", "Hold"], http_post=post)
        opts = json.loads(post.calls[-1]["data"]["options"])
        assert opts == [{"text": "Ship"}, {"text": "Hold"}]   # objects, not strings
