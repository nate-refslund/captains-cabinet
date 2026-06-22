"""channel.py — the ONLY front-door Telegram send path.

Security contract under test (non-negotiable, from the security review):
  (1) dev default => allow_sends() False => ZERO network call (the fail-safe).
  (2) outbound goes ONLY to CAPTAIN_TELEGRAM_ID, only when allow_sends() True;
      recipient is NOT a parameter (no third-party recipients).
  (3) the bot token (TELEGRAM_COS_TOKEN) NEVER appears in any returned dict nor
      in any raised/propagated exception message — even on HTTP error — because
      the request URL embeds the token.
  (4) NO real network send: http_post is always a mock here.

All env-dependent behaviour is monkeypatched; nothing here touches the network,
Redis, or the consequence ledger.
"""
import framework.env as env
import framework.frontdoor.channel as channel

TOKEN = "123456:SECRET-BOT-TOKEN-do-not-leak"
CAPTAIN = "987654321"


def _set_env(monkeypatch, *, token=TOKEN, captain=CAPTAIN):
    monkeypatch.setenv("TELEGRAM_COS_TOKEN", token)
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", captain)


class _RecordingPost:
    """Mock http_post: records the call and returns a canned 200 body."""

    def __init__(self, response=None, raises=None):
        self.calls = []
        self._response = response if response is not None else {"ok": True, "result": {"message_id": 42}}
        self._raises = raises

    def __call__(self, url, data):
        self.calls.append({"url": url, "data": data})
        if self._raises is not None:
            raise self._raises
        return self._response


# ---------------------------------------------------------------------------
# (1) THE CRITICAL FAIL-SAFE: dev default never sends, never touches the network
# ---------------------------------------------------------------------------
class TestDevNeverSends:
    def test_dev_default_returns_blocked_and_makes_no_http_call(self, monkeypatch):
        monkeypatch.delenv("CABINET_ENV", raising=False)  # dev default
        _set_env(monkeypatch)
        assert env.allow_sends() is False  # precondition
        post = _RecordingPost()
        result = channel.send("hello captain", http_post=post)
        assert post.calls == []                  # ZERO network call
        assert result["sent"] is False
        assert result["status"] == "blocked-dev"

    def test_blocked_even_with_token_set(self, monkeypatch):
        """Gate is allow_sends(), not presence of a token."""
        monkeypatch.setenv("CABINET_ENV", "prod")  # anything != runtime -> dev
        _set_env(monkeypatch)
        post = _RecordingPost()
        result = channel.send("x", http_post=post)
        assert post.calls == []
        assert result["sent"] is False
        assert result["status"] == "blocked-dev"

    def test_gate_checked_first_does_not_read_token_when_blocked(self, monkeypatch):
        """Blocked path must not even require the token to be present."""
        monkeypatch.delenv("CABINET_ENV", raising=False)
        monkeypatch.delenv("TELEGRAM_COS_TOKEN", raising=False)
        monkeypatch.delenv("CAPTAIN_TELEGRAM_ID", raising=False)
        post = _RecordingPost()
        result = channel.send("x", http_post=post)  # must not raise
        assert post.calls == []
        assert result["status"] == "blocked-dev"


# ---------------------------------------------------------------------------
# (2) RUNTIME: sends to api.telegram.org sendMessage, chat_id == CAPTAIN only
# ---------------------------------------------------------------------------
class TestRuntimeSend:
    def test_runtime_posts_to_telegram_sendmessage_with_captain_chat_id(self, monkeypatch):
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        post = _RecordingPost()
        result = channel.send("the exact text", http_post=post)
        assert len(post.calls) == 1
        call = post.calls[0]
        assert "api.telegram.org" in call["url"]
        assert call["url"].endswith("/sendMessage")
        # payload carries the captain id and the exact text
        assert str(call["data"].get("chat_id")) == CAPTAIN
        assert call["data"].get("text") == "the exact text"
        assert result["sent"] is True
        assert result["status"] == "sent"

    def test_recipient_cannot_be_overridden(self, monkeypatch):
        """send() exposes no recipient parameter — only text + http_post."""
        import inspect

        sig = inspect.signature(channel.send)
        params = set(sig.parameters)
        assert "text" in params
        assert "http_post" in params
        # No recipient-ish parameter is exposed
        for forbidden in ("chat_id", "recipient", "to", "captain_id", "chat"):
            assert forbidden not in params

    def test_url_targets_api_telegram_org_host(self, monkeypatch):
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        post = _RecordingPost()
        channel.send("hi", http_post=post)
        url = post.calls[0]["url"]
        assert url.startswith("https://api.telegram.org/")


# ---------------------------------------------------------------------------
# (3) TOKEN MUST NEVER LEAK — not in the return value, not in any exception
# ---------------------------------------------------------------------------
class TestTokenNeverLeaks:
    def test_token_absent_from_successful_result(self, monkeypatch):
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        post = _RecordingPost()
        result = channel.send("hi", http_post=post)
        assert TOKEN not in str(result)
        # also: the token-bearing URL must not be surfaced in the result
        for v in result.values():
            assert TOKEN not in str(v)

    def test_token_absent_from_error_result_on_http_failure(self, monkeypatch):
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        # Simulate an HTTP error whose message embeds the token-bearing URL.
        boom = RuntimeError(
            f"HTTP 401 Unauthorized for url "
            f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        )
        post = _RecordingPost(raises=boom)
        result = channel.send("hi", http_post=post)
        # send() must catch + sanitize, never propagate the token-bearing message
        assert result["sent"] is False
        assert result["status"] == "error"
        assert TOKEN not in str(result)
        assert "api.telegram.org/bot" not in str(result)

    def test_token_absent_from_any_propagated_exception(self, monkeypatch):
        """If send ever raises, the message must not contain the token."""
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        boom = RuntimeError(f"https://api.telegram.org/bot{TOKEN}/sendMessage failed")
        post = _RecordingPost(raises=boom)
        try:
            result = channel.send("hi", http_post=post)
        except Exception as exc:  # pragma: no cover - should be caught internally
            assert TOKEN not in str(exc)
        else:
            assert TOKEN not in str(result)


# ---------------------------------------------------------------------------
# receive(): now implemented — full behavior in test_channel_receive.py
# ---------------------------------------------------------------------------
class TestReceiveSeam:
    def test_receive_unconfigured_returns_empty(self, monkeypatch):
        # With no bot token configured, receive() fails safe to ([], offset).
        monkeypatch.delenv("TELEGRAM_COS_TOKEN", raising=False)
        assert channel.receive(offset=3) == ([], 3)
