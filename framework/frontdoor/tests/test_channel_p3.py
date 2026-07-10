"""channel.py — attention-gateway P3 additions (spec §4.3/§4.4/§13).

Covers the new transport surface layered onto the existing send path:
  * send(reply_to=, silent=, reply_markup=, markdown=) payload shaping
  * message_ids capture (single + multipart)
  * edit_message (success, blocked, not-modified no-op)
  * answer_callback (gate + token scrub)
  * render_markdown (escape-first, tokens → Telegram HTML)
  * feed journal at the transport layer (rows written; JOURNAL-GAP on failure)

Every send is mocked (http_post injected) — nothing touches the network, Redis,
or the real feed journal. The feed module is faked via sys.modules so the lazy
``from framework.attention import feed`` binds our recorder.
"""
from __future__ import annotations

import json
import sys
import types

import pytest

import framework.attention as attn_pkg
import framework.env as env
import framework.frontdoor.channel as channel

TOKEN = "123456:SECRET-BOT-TOKEN-do-not-leak"
CAPTAIN = "98765432"


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    """No real backoff sleep, no Redis threading lookup, fresh feed-warn flag."""
    monkeypatch.setattr(channel.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: None)
    monkeypatch.setattr(channel, "_feed_import_warned", False, raising=False)


def _set_env(monkeypatch, *, token=TOKEN, captain=CAPTAIN):
    monkeypatch.setenv("TELEGRAM_COS_TOKEN", token)
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", captain)


def _runtime(monkeypatch):
    monkeypatch.setattr(env, "allow_sends", lambda: True)
    _set_env(monkeypatch)


class RecordingPost:
    """Records each call; returns a canned 200 body (or raises)."""

    def __init__(self, response=None, raises=None):
        self.calls = []
        self._response = response if response is not None else {"ok": True, "result": {"message_id": 42}}
        self._raises = raises

    def __call__(self, url, data):
        self.calls.append({"url": url, "data": data})
        if self._raises is not None:
            raise self._raises
        return self._response


class SeqPost:
    """Returns a distinct message_id per call (100+n)."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, data):
        self.calls.append({"url": url, "data": data})
        return {"ok": True, "result": {"message_id": 100 + len(self.calls)}}


def _install_fake_feed(monkeypatch, *, raises=None):
    """Bind a recording fake at ``framework.attention.feed`` for the lazy import."""
    rows: list = []

    def append_event(row):
        rows.append(row)
        if raises is not None:
            raise raises
        return row

    fake = types.SimpleNamespace(append_event=append_event)
    monkeypatch.setitem(sys.modules, "framework.attention.feed", fake)
    monkeypatch.setattr(attn_pkg, "feed", fake, raising=False)
    return rows


# ---------------------------------------------------------------------------
# send() new kwargs
# ---------------------------------------------------------------------------
class TestSendKwargs:
    def test_reply_to_threads_to_the_given_message(self, monkeypatch):
        _runtime(monkeypatch)
        # Tripwire: reply_to must NOT consult the Redis last-message fallback.
        called = {"n": 0}
        monkeypatch.setattr(channel, "_last_captain_msg_id",
                            lambda: called.__setitem__("n", called["n"] + 1) or 111)
        post = RecordingPost()
        channel.send("hi", http_post=post, reply_to=778)
        rp = post.calls[0]["data"]["reply_parameters"]
        assert rp == {"message_id": 778, "allow_sending_without_reply": True}
        assert called["n"] == 0  # explicit reply_to bypasses the fallback lookup

    def test_silent_sets_disable_notification(self, monkeypatch):
        _runtime(monkeypatch)
        post = RecordingPost()
        channel.send("quiet", http_post=post, silent=True)
        assert post.calls[0]["data"]["disable_notification"] is True

    def test_not_silent_omits_disable_notification(self, monkeypatch):
        _runtime(monkeypatch)
        post = RecordingPost()
        channel.send("loud", http_post=post)
        assert "disable_notification" not in post.calls[0]["data"]

    def test_reply_markup_is_json_encoded(self, monkeypatch):
        _runtime(monkeypatch)
        markup = {"inline_keyboard": [[{"text": "OK", "callback_data": "ok:1"}]]}
        post = RecordingPost()
        channel.send("tap", http_post=post, reply_markup=markup)
        assert post.calls[0]["data"]["reply_markup"] == json.dumps(markup)

    def test_markdown_sets_parse_mode_and_renders(self, monkeypatch):
        _runtime(monkeypatch)
        post = RecordingPost()
        channel.send("**bold**", http_post=post, markdown=True)
        data = post.calls[0]["data"]
        assert data["parse_mode"] == "HTML"
        assert data["text"] == "<b>bold</b>"

    def test_markdown_false_is_plain_no_parse_mode(self, monkeypatch):
        _runtime(monkeypatch)
        post = RecordingPost()
        channel.send("**bold**", http_post=post)  # markdown defaults off
        data = post.calls[0]["data"]
        assert "parse_mode" not in data
        assert data["text"] == "**bold**"  # verbatim


# ---------------------------------------------------------------------------
# message_ids capture
# ---------------------------------------------------------------------------
class TestMessageIds:
    def test_single_send_captures_message_id(self, monkeypatch):
        _runtime(monkeypatch)
        post = RecordingPost(response={"ok": True, "result": {"message_id": 4242}})
        result = channel.send("hi", http_post=post)
        assert result["message_ids"] == [4242]

    def test_multipart_captures_all_ids(self, monkeypatch):
        _runtime(monkeypatch)
        text = "\n".join(f"line {i} " + "x" * 80 for i in range(200))  # > 4096 → chunks
        post = SeqPost()
        result = channel.send(text, http_post=post)
        assert result["sent"] is True
        assert len(result["message_ids"]) == len(post.calls) > 1
        assert result["message_ids"] == [100 + i for i in range(1, len(post.calls) + 1)]

    def test_partial_failure_returns_ids_so_far(self, monkeypatch):
        _runtime(monkeypatch)

        class FailSecond:
            def __init__(self):
                self.calls = []

            def __call__(self, url, data):
                self.calls.append(1)
                if len(self.calls) == 1:
                    return {"ok": True, "result": {"message_id": 7}}
                raise RuntimeError("telegram transport error: URLError")

        text = "\n".join(f"line {i} " + "x" * 80 for i in range(200))
        result = channel.send(text, http_post=FailSecond())
        assert result["sent"] is False
        assert result["message_ids"] == [7]  # first chunk's id, then it failed


# ---------------------------------------------------------------------------
# edit_message
# ---------------------------------------------------------------------------
class TestEditMessage:
    def test_edit_posts_to_editmessagetext_with_captain(self, monkeypatch):
        _runtime(monkeypatch)
        post = RecordingPost(response={"ok": True, "result": {"message_id": 55}})
        result = channel.edit_message(55, "new text", http_post=post)
        call = post.calls[0]
        assert call["url"].endswith("/editMessageText")
        assert call["data"]["message_id"] == 55
        assert str(call["data"]["chat_id"]) == CAPTAIN
        assert call["data"]["text"] == "new text"
        assert result["status"] == "sent" and result["sent"] is True
        assert result["message_ids"] == [55]

    def test_message_id_falls_back_when_result_is_true(self, monkeypatch):
        # editMessageText can answer bare `true`; the journal/return still carries
        # the target message_id we were handed.
        _runtime(monkeypatch)
        post = RecordingPost(response={"ok": True, "result": True})
        result = channel.edit_message(77, "x", http_post=post)
        assert result["message_ids"] == [77]

    def test_not_modified_is_noop_not_error(self, monkeypatch):
        _runtime(monkeypatch)
        boom = RuntimeError("telegram HTTP 400: Bad Request: message is not modified")
        post = RecordingPost(raises=boom)
        result = channel.edit_message(9, "same", http_post=post)
        assert result == {"status": "noop", "sent": False}

    def test_other_400_is_error(self, monkeypatch):
        _runtime(monkeypatch)
        boom = RuntimeError("telegram HTTP 400: Bad Request: message to edit not found")
        post = RecordingPost(raises=boom)
        result = channel.edit_message(9, "x", http_post=post)
        assert result["status"] == "error" and result["sent"] is False

    def test_edit_blocked_in_dev(self, monkeypatch):
        monkeypatch.delenv("CABINET_ENV", raising=False)
        _set_env(monkeypatch)
        post = RecordingPost()
        result = channel.edit_message(1, "x", http_post=post)
        assert result == {"status": "blocked-dev", "sent": False}
        assert post.calls == []

    def test_edit_reply_markup_json_encoded(self, monkeypatch):
        _runtime(monkeypatch)
        markup = {"inline_keyboard": [[{"text": "Undo", "callback_data": "undo:1"}]]}
        post = RecordingPost(response={"ok": True, "result": {"message_id": 5}})
        channel.edit_message(5, "acted ✓", http_post=post, reply_markup=markup)
        assert post.calls[0]["data"]["reply_markup"] == json.dumps(markup)

    def test_edit_never_leaks_token_on_error(self, monkeypatch):
        _runtime(monkeypatch)
        boom = RuntimeError(f"https://api.telegram.org/bot{TOKEN}/editMessageText 400")
        post = RecordingPost(raises=boom)
        result = channel.edit_message(3, "x", http_post=post)
        assert TOKEN not in str(result)
        assert "api.telegram.org/bot" not in str(result)


# ---------------------------------------------------------------------------
# answer_callback
# ---------------------------------------------------------------------------
class TestAnswerCallback:
    def test_answers_with_callback_query_id(self, monkeypatch):
        _runtime(monkeypatch)
        post = RecordingPost(response={"ok": True, "result": True})
        result = channel.answer_callback("cbq-1", "done", http_post=post)
        call = post.calls[0]
        assert call["url"].endswith("/answerCallbackQuery")
        assert call["data"]["callback_query_id"] == "cbq-1"
        assert call["data"]["text"] == "done"
        assert result["sent"] is True

    def test_scrubs_token_from_toast_text(self, monkeypatch):
        _runtime(monkeypatch)
        post = RecordingPost(response={"ok": True, "result": True})
        channel.answer_callback("cbq-2", f"leak {TOKEN} here", http_post=post)
        assert TOKEN not in json.dumps(post.calls[0]["data"])

    def test_blocked_in_dev(self, monkeypatch):
        monkeypatch.delenv("CABINET_ENV", raising=False)
        _set_env(monkeypatch)
        post = RecordingPost()
        result = channel.answer_callback("cbq", "x", http_post=post)
        assert result == {"status": "blocked-dev", "sent": False}
        assert post.calls == []

    def test_empty_text_omits_field(self, monkeypatch):
        _runtime(monkeypatch)
        post = RecordingPost(response={"ok": True, "result": True})
        channel.answer_callback("cbq", http_post=post)
        assert "text" not in post.calls[0]["data"]


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------
class TestRenderMarkdown:
    def test_plain_text_unchanged(self):
        assert channel.render_markdown("just plain text") == ("just plain text", None)

    def test_bold_and_code_convert(self):
        out, mode = channel.render_markdown("**b** and `c`")
        assert mode == "HTML"
        assert "<b>b</b>" in out and "<code>c</code>" in out

    def test_script_escaped_when_html_active(self):
        out, mode = channel.render_markdown("**hi** <script>alert(1)</script>")
        assert mode == "HTML"
        assert "<b>hi</b>" in out
        assert "&lt;script&gt;" in out
        assert "<script>" not in out  # raw tag never survives

    def test_script_without_markdown_is_inert_plain(self):
        # No token → returned verbatim with parse_mode=None; Telegram renders it
        # literally (no entity parsing), so an un-escaped <script> is safe.
        assert channel.render_markdown("<script>x</script>") == ("<script>x</script>", None)

    def test_fenced_block_and_link(self):
        out, mode = channel.render_markdown("see ```code**not bold**``` and [x](https://e.co)")
        assert mode == "HTML"
        assert "<pre>code**not bold**</pre>" in out  # markup inside code stays literal
        assert '<a href="https://e.co">x</a>' in out


# ---------------------------------------------------------------------------
# feed journal at the transport layer
# ---------------------------------------------------------------------------
class TestFeedJournal:
    def test_send_writes_one_out_row(self, monkeypatch):
        _runtime(monkeypatch)
        rows = _install_fake_feed(monkeypatch)
        post = RecordingPost(response={"ok": True, "result": {"message_id": 321}})
        channel.send("hello", http_post=post,
                     feed_meta={"situation_key": "sk1", "class": "commit", "urgency": "batch"})
        assert len(rows) == 1
        row = rows[0]
        assert row["direction"] == "out"
        assert row["kind"] == "message"
        assert row["telegram_message_id"] == 321
        assert str(row["chat"]) == CAPTAIN
        assert row["content_len"] == len("hello")
        assert row["content_hash"] == channel.hashlib.sha1(b"hello").hexdigest()
        # feed_meta situation context is merged in
        assert row["situation_key"] == "sk1" and row["class"] == "commit"

    def test_edit_writes_edit_kind_row(self, monkeypatch):
        _runtime(monkeypatch)
        rows = _install_fake_feed(monkeypatch)
        post = RecordingPost(response={"ok": True, "result": {"message_id": 55}})
        channel.edit_message(55, "acted ✓", http_post=post, feed_meta={"situation_key": "sk9"})
        assert rows[-1]["kind"] == "edit"
        assert rows[-1]["telegram_message_id"] == 55
        assert rows[-1]["situation_key"] == "sk9"

    def test_feed_meta_can_override_kind(self, monkeypatch):
        _runtime(monkeypatch)
        rows = _install_fake_feed(monkeypatch)
        channel.send("x", http_post=RecordingPost(), feed_meta={"kind": "card"})
        assert rows[-1]["kind"] == "card"

    def test_journal_gap_is_loud_but_send_succeeds(self, monkeypatch, capsys):
        _runtime(monkeypatch)
        _install_fake_feed(monkeypatch, raises=RuntimeError("disk full"))
        post = RecordingPost()
        result = channel.send("still delivered", http_post=post)
        assert result["sent"] is True  # delivery beats journaling
        err = capsys.readouterr().err
        assert "JOURNAL-GAP" in err

    def test_missing_feed_module_is_tolerated(self, monkeypatch, capsys):
        _runtime(monkeypatch)
        # Force the lazy import to fail even though the real feed.py exists: a
        # None entry in sys.modules is the documented "block this import" signal.
        monkeypatch.delattr(attn_pkg, "feed", raising=False)
        monkeypatch.setitem(sys.modules, "framework.attention.feed", None)
        post = RecordingPost()
        result = channel.send("bootstrap", http_post=post)
        assert result["sent"] is True  # send unaffected by missing journal
        assert "bootstrap" in capsys.readouterr().err  # noted once, not raised

    def test_real_feed_module_accepts_our_rows(self, monkeypatch):
        # Integration: with NO fake installed, the REAL feed.append_event runs
        # (frontdoor conftest sandboxes CABINET_FEED_DIR to a tmp dir), proving
        # our transport rows pass the real schema. Read them back by seq.
        _runtime(monkeypatch)
        from framework.attention import feed
        channel.send("hello real feed", http_post=RecordingPost(
            response={"ok": True, "result": {"message_id": 4444}}),
            feed_meta={"situation_key": "sk-real", "class": "commit"})
        rows, _ = feed.feed_since(0)
        assert rows, "the real feed journal recorded nothing"
        last = rows[-1]
        assert last["direction"] == "out" and last["kind"] == "message"
        assert last["telegram_message_id"] == 4444
        assert last["situation_key"] == "sk-real"
        assert "seq" in last and "ts" in last  # stamped by the real feed

    def test_transport_facts_not_forgeable_by_feed_meta(self, monkeypatch):
        _runtime(monkeypatch)
        rows = _install_fake_feed(monkeypatch)
        post = RecordingPost(response={"ok": True, "result": {"message_id": 999}})
        channel.send("real", http_post=post,
                     feed_meta={"telegram_message_id": 1, "chat": "attacker", "direction": "in"})
        row = rows[-1]
        assert row["telegram_message_id"] == 999   # transport wins
        assert str(row["chat"]) == CAPTAIN
        assert row["direction"] == "out"
