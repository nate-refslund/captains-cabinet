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
import pytest

import framework.env as env
import framework.frontdoor.channel as channel

TOKEN = "123456:SECRET-BOT-TOKEN-do-not-leak"
CAPTAIN = "98765432"


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch):
    """Neutralize the transport-retry backoff sleep for EVERY test so the suite
    never pays real wall-clock waits. The retry *logic* (attempt count, ordering,
    end state) is asserted through the injected ``http_post`` mock; the actual
    backoff *durations* are asserted explicitly in TestTransportRetry via a
    recording fake sleep passed to ``_post_one``. This keeps the send() tests
    fast while still proving both behaviors."""
    monkeypatch.setattr(channel.time, "sleep", lambda *_a, **_k: None)


def _set_env(monkeypatch, *, token=TOKEN, captain=CAPTAIN):
    monkeypatch.setenv("TELEGRAM_COS_TOKEN", token)
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", captain)


def _no_threading(monkeypatch):
    """Neutralize the Redis-backed reply-threading lookup so a test is hermetic
    (no redis-cli subprocess, no dependency on host Redis state). Tests that
    exercise threading override this with their own stub."""
    monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: None)


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
        _no_threading(monkeypatch)
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
        _no_threading(monkeypatch)
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
        _no_threading(monkeypatch)
        post = _RecordingPost()
        result = channel.send("hi", http_post=post)
        assert TOKEN not in str(result)
        # also: the token-bearing URL must not be surfaced in the result
        for v in result.values():
            assert TOKEN not in str(v)

    def test_token_absent_from_error_result_on_http_failure(self, monkeypatch):
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        _no_threading(monkeypatch)
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
        _no_threading(monkeypatch)
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


# ---------------------------------------------------------------------------
# (5) REPLY-THREADING: when the inbound watchdog has recorded the Captain's
#     latest message_id (in Redis), send() threads the reply onto it via
#     reply_parameters. Unknown id => plain send, exactly as before. Driven
#     through the _last_captain_msg_id seam — NEVER hits Redis or the network.
# ---------------------------------------------------------------------------
class TestReplyThreading:
    def test_payload_includes_reply_parameters_when_id_known(self, monkeypatch):
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: 777)
        post = _RecordingPost()
        result = channel.send("threaded reply", http_post=post)
        data = post.calls[0]["data"]
        assert data["reply_parameters"] == {
            "message_id": 777,
            "allow_sending_without_reply": True,
        }
        # threading does not disturb the core payload
        assert str(data.get("chat_id")) == CAPTAIN
        assert data.get("text") == "threaded reply"
        assert result["sent"] is True

    def test_payload_omits_reply_parameters_when_id_unknown(self, monkeypatch):
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: None)
        post = _RecordingPost()
        channel.send("plain reply", http_post=post)
        assert "reply_parameters" not in post.calls[0]["data"]

    def test_redis_failure_degrades_to_plain_send(self, monkeypatch):
        """If the Redis lookup itself errors, send() must still deliver — plain."""
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)

        def boom():
            raise RuntimeError("redis unreachable")

        # The helper swallows internally, but even if a future refactor let an
        # error through, send() should not be derailed. Here we assert the
        # SHIPPED helper is degrade-safe: a dead redis-cli => None => plain send.
        monkeypatch.setenv("REDIS_HOST", "203.0.113.1")  # TEST-NET-1, unroutable
        # Force the subprocess to fail fast instead of timing out the suite.
        import subprocess as _sp
        monkeypatch.setattr(
            channel.subprocess, "run",
            lambda *a, **k: (_ for _ in ()).throw(_sp.SubprocessError("no redis")),
        )
        post = _RecordingPost()
        result = channel.send("still sends", http_post=post)
        assert "reply_parameters" not in post.calls[0]["data"]
        assert result["sent"] is True

    def test_threading_on_does_not_leak_token(self, monkeypatch):
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: 555)
        post = _RecordingPost()
        result = channel.send("hi", http_post=post)
        assert TOKEN not in str(result)
        assert "api.telegram.org/bot" not in str(result)

    def test_blocked_dev_never_reads_redis_for_threading(self, monkeypatch):
        """The gate is FIRST: a blocked-dev send must not even consult Redis."""
        monkeypatch.delenv("CABINET_ENV", raising=False)  # dev default
        _set_env(monkeypatch)
        called = {"n": 0}

        def _tripwire():
            called["n"] += 1
            return 999

        monkeypatch.setattr(channel, "_last_captain_msg_id", _tripwire)
        post = _RecordingPost()
        result = channel.send("x", http_post=post)
        assert result["status"] == "blocked-dev"
        assert post.calls == []
        assert called["n"] == 0  # threading lookup never reached past the gate


# ---------------------------------------------------------------------------
# (6) CHUNKING: a message over Telegram's 4096-char limit is split into multiple
#     ≤-limit chunks sent sequentially (the 2026-06-29 hard-failure: a 77-item
#     briefing assembled into ONE over-limit body → HTTP 400 → message LOST).
#     A normal-length message is still ONE post, unchanged. Boundaries are
#     line/paragraph (never mid-line); ``sent`` is True only if ALL chunks land.
# ---------------------------------------------------------------------------
class _SeqRecordingPost:
    """Mock http_post that records every call and returns a per-call 200 body.

    Optionally fails (raises) for calls whose payload text exceeds ``fail_over``
    chars, or for the first ``fail_first_n`` calls, so a test can exercise the
    plain-text retry and the partial-failure report.
    """

    def __init__(self, *, fail_over=None, fail_first_n=0, fail_exc=None):
        self.calls = []
        self._fail_over = fail_over
        self._fail_first_n = fail_first_n
        self._fail_exc = fail_exc or RuntimeError("telegram HTTP 400")

    def __call__(self, url, data):
        self.calls.append({"url": url, "data": data})
        n = len(self.calls)
        text = str(data.get("text", ""))
        if n <= self._fail_first_n:
            raise self._fail_exc
        if self._fail_over is not None and len(text) > self._fail_over:
            raise self._fail_exc
        return {"ok": True, "result": {"message_id": 100 + n}}


def _long_lines(n_lines, line="x" * 80):
    """A multi-line body of n_lines (each well under the limit) joined by \\n —
    realistic shape of the briefing wall (many provenance bullets)."""
    return "\n".join(f"{line} {i}" for i in range(n_lines))


class TestChunking:
    def test_split_helper_never_splits_mid_line(self):
        # 200 lines of 80 chars ≈ 16k chars → several chunks, each ≤ budget, and
        # every line stays intact (no line is severed across a chunk boundary).
        text = _long_lines(200)
        chunks = channel._split_for_telegram(text)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c) <= channel._CHUNK_BUDGET
        # Reassembling the lines from all chunks reproduces every original line.
        original_lines = text.split("\n")
        got_lines = []
        for c in chunks:
            got_lines.extend(c.split("\n"))
        assert got_lines == original_lines  # nothing severed, nothing lost

    def test_short_message_is_single_chunk(self):
        chunks = channel._split_for_telegram("a short briefing")
        assert chunks == ["a short briefing"]

    def test_over_limit_message_sends_as_multiple_chunks_all_ok(self, monkeypatch):
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        _no_threading(monkeypatch)
        text = _long_lines(200)  # ~16k chars → multiple chunks
        post = _SeqRecordingPost()
        result = channel.send(text, http_post=post)
        assert result["sent"] is True
        assert result["status"] == "sent"
        assert result["chunks"] == len(post.calls) > 1
        # every chunk went to the Captain on sendMessage, each within the limit
        for call in post.calls:
            assert str(call["data"]["chat_id"]) == CAPTAIN
            assert call["url"].endswith("/sendMessage")
            assert len(call["data"]["text"]) <= channel._TELEGRAM_LIMIT
        # chunks are numbered so ordering is visible
        assert post.calls[0]["data"]["text"].startswith("(1/")

    def test_normal_message_still_one_post_no_marker(self, monkeypatch):
        """Regression guard: a normal-length message is sent EXACTLY as before —
        one call, verbatim text, single-`response` result shape."""
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        _no_threading(monkeypatch)
        post = _SeqRecordingPost()
        result = channel.send("the exact text", http_post=post)
        assert len(post.calls) == 1
        assert post.calls[0]["data"]["text"] == "the exact text"  # no "(1/1)" marker
        assert result["status"] == "sent" and result["sent"] is True
        assert "response" in result and "chunks" not in result

    def test_threading_anchor_applied_to_every_chunk(self, monkeypatch):
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        monkeypatch.setattr(channel, "_last_captain_msg_id", lambda: 321)
        post = _SeqRecordingPost()
        channel.send(_long_lines(200), http_post=post)
        assert len(post.calls) > 1
        for call in post.calls:
            assert call["data"]["reply_parameters"] == {
                "message_id": 321, "allow_sending_without_reply": True}

    def test_partial_failure_reports_not_false_success(self, monkeypatch):
        """If a later chunk 400s even after the plain-text retry, send() reports
        status='error'/sent=False with how many chunks landed — so the caller
        leaves the intake PENDING instead of ACKing a partial briefing away."""
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        _no_threading(monkeypatch)

        class _FailFromSecond:
            """First send OK; every subsequent attempt (incl. the plain retry)
            raises a non-400 transport error → a genuine, unrecoverable failure
            on the 2nd chunk."""
            def __init__(self):
                self.calls = []

            def __call__(self, url, data):
                self.calls.append({"url": url, "data": data})
                if len(self.calls) == 1:
                    return {"ok": True, "result": {"message_id": 1}}
                raise RuntimeError("telegram transport error: URLError")

        post = _FailFromSecond()
        result = channel.send(_long_lines(200), http_post=post)
        assert result["sent"] is False
        assert result["status"] == "error"
        assert result["sent_chunks"] == 1  # first chunk landed, then it failed
        assert TOKEN not in str(result)

    def test_chunk_400_retries_as_plain_text_then_succeeds(self, monkeypatch):
        """A single chunk that 400s on the first attempt is retried once as plain
        text; if the retry succeeds the send still reports success (a formatting
        glitch never silently drops the message)."""
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        _no_threading(monkeypatch)
        # Short message → single chunk. First attempt 400s, retry succeeds.
        post = _SeqRecordingPost(fail_first_n=1)
        result = channel.send("a short briefing", http_post=post)
        assert result["sent"] is True
        assert len(post.calls) == 2  # initial 400 + plain-text retry
        assert post.calls[1]["data"]["text"] == "a short briefing"

    def test_over_limit_send_never_leaks_token(self, monkeypatch):
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        _no_threading(monkeypatch)
        boom = RuntimeError(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage 400")
        post = _SeqRecordingPost(fail_first_n=99, fail_exc=boom)
        result = channel.send(_long_lines(200), http_post=post)
        assert result["sent"] is False
        assert TOKEN not in str(result)
        assert "api.telegram.org/bot" not in str(result)


# ---------------------------------------------------------------------------
# (7) TRANSPORT RETRY: a TRANSIENT network failure (the request never got a real
#     HTTP response — URLError / socket timeout / ConnectionError) is retried
#     with short exponential backoff. The 2026-06-30 07:30 briefing failed with
#     "telegram transport error: URLError" (chunks:1, sent_chunks:0): the Mac
#     slept 02:28→08:04, launchd ran the calendar-scheduled briefing the instant
#     it woke, and api.telegram.org would not resolve until mDNSResponder/the
#     network came up. The send was NOT retried (only HTTP 400 was) → the
#     briefing was LOST. This suite proves: a transient blip that then clears
#     retries+succeeds; a persistent blip fails cleanly after N attempts (no
#     infinite loop); an HTTP 400 still takes the plain-text fallback (NOT the
#     transport-retry path); and a normal first-try send is one post, unchanged.
# ---------------------------------------------------------------------------
class _TransientThenOK:
    """http_post that raises a transport error for the first ``fail_n`` calls,
    then returns a 200 body — models a not-yet-ready resolver clearing."""

    def __init__(self, *, fail_n=1, exc=None):
        self.calls = []
        self._fail_n = fail_n
        self._exc = exc or RuntimeError("telegram transport error: URLError")

    def __call__(self, url, data):
        self.calls.append({"url": url, "data": data})
        if len(self.calls) <= self._fail_n:
            raise self._exc
        return {"ok": True, "result": {"message_id": 200 + len(self.calls)}}


class _AlwaysTransient:
    """http_post that raises a transport error on EVERY call — a persistent
    outage (e.g. network never comes back during the whole retry budget)."""

    def __init__(self, exc=None):
        self.calls = []
        self._exc = exc or RuntimeError("telegram transport error: URLError")

    def __call__(self, url, data):
        self.calls.append({"url": url, "data": data})
        raise self._exc


class TestTransportRetry:
    def test_transient_then_success_returns_sent(self, monkeypatch):
        """(1) A transport URLError on the first attempt, success on the retry →
        the send recovers and reports sent=True (exactly the 07:30 wake case)."""
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        _no_threading(monkeypatch)
        post = _TransientThenOK(fail_n=1)
        result = channel.send("the briefing", http_post=post)
        assert result["sent"] is True
        assert result["status"] == "sent"
        assert len(post.calls) == 2  # 1st failed (transport) + retry delivered
        # the same payload was re-posted (not mutated) and went to the Captain
        assert post.calls[1]["data"]["text"] == "the briefing"
        assert str(post.calls[1]["data"]["chat_id"]) == CAPTAIN

    def test_transient_recovers_within_attempt_budget(self, monkeypatch):
        """Two transient failures then success still recovers (3-attempt budget)."""
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        _no_threading(monkeypatch)
        post = _TransientThenOK(fail_n=2)
        result = channel.send("hi", http_post=post)
        assert result["sent"] is True
        assert len(post.calls) == channel._TRANSPORT_RETRY_ATTEMPTS == 3

    def test_persistent_transport_error_fails_cleanly_after_n(self, monkeypatch):
        """(2) A persistent URLError → status='error'/sent=False after exactly N
        attempts (no infinite loop), returning the same error shape as today so
        the caller leaves the intake PENDING and the watchdog still catches it."""
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        _no_threading(monkeypatch)
        post = _AlwaysTransient()
        result = channel.send("the briefing", http_post=post)
        assert result["sent"] is False
        assert result["status"] == "error"
        # bounded: tried exactly the attempt budget, then gave up
        assert len(post.calls) == channel._TRANSPORT_RETRY_ATTEMPTS == 3
        # single-chunk failure carries the same fields as before the retry change
        assert result["chunks"] == 1
        assert result["sent_chunks"] == 0
        assert "transport error" in result["error"]
        assert TOKEN not in str(result)

    def test_backoff_sequence_is_short_and_bounded(self, monkeypatch):
        """The backoff waits are exactly the declared short sequence (1s, 3s) and
        there are attempts-1 of them — proving the retry is bounded in time and
        cannot wedge the launchd briefing slot. Asserted by injecting a recording
        fake sleep straight into _post_one (the autouse fixture no-ops the real
        one for the rest of the suite)."""
        slept = []
        post = _AlwaysTransient()
        ok, resp, err = channel._post_one(
            post, "https://api.telegram.org/bot<t>/sendMessage",
            {"chat_id": CAPTAIN, "text": "x"}, "<t>", sleep=slept.append)
        assert ok is False
        assert slept == list(channel._TRANSPORT_BACKOFF_S)  # (1, 3): no extra wait
        assert len(slept) == channel._TRANSPORT_RETRY_ATTEMPTS - 1
        # total backoff budget is a few seconds — comfortably under any deadline
        assert sum(slept) <= 10

    def test_socket_timeout_is_treated_as_transient(self, monkeypatch):
        """A raw socket.timeout (a directly-injected transport error, not the
        string-wrapped default) is classified transient and retried."""
        import socket as _socket
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        _no_threading(monkeypatch)
        post = _TransientThenOK(fail_n=1, exc=_socket.timeout("timed out"))
        result = channel.send("hi", http_post=post)
        assert result["sent"] is True
        assert len(post.calls) == 2

    def test_http_400_takes_plaintext_fallback_not_transport_retry(self, monkeypatch):
        """(3) An HTTP 400 must take the EXISTING plain-text fallback (one retry,
        parse_mode stripped) — NOT the transport-retry path. A 400 reached
        Telegram (a payload bug); transport-retrying it would be wrong."""
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        _no_threading(monkeypatch)
        # First call 400s, second (plain-text) succeeds. If the code mistakenly
        # treated 400 as transient it would retry the SAME payload up to 3x; here
        # exactly 2 calls prove the 400→plain path, and the retry stripped any
        # parse_mode (none set today, but the path is the 400 handler).
        post = _SeqRecordingPost(fail_first_n=1)  # raises "telegram HTTP 400"
        result = channel.send("a short briefing", http_post=post)
        assert result["sent"] is True
        assert len(post.calls) == 2  # 400 + ONE plain-text retry (not 3 transport)

    def test_persistent_http_400_fails_after_single_fallback(self, monkeypatch):
        """A 400 that persists through the plain-text retry fails after exactly
        2 calls (initial + one fallback) — the 400 path is NOT amplified by the
        transport-retry budget."""
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        _no_threading(monkeypatch)
        post = _SeqRecordingPost(fail_first_n=99)  # every call raises HTTP 400
        result = channel.send("a short briefing", http_post=post)
        assert result["sent"] is False
        assert result["status"] == "error"
        assert len(post.calls) == 2  # initial 400 + one plain-text retry, then stop

    def test_normal_first_try_success_is_one_post_unchanged(self, monkeypatch):
        """(4) A normal first-try success is EXACTLY one post with the identical
        single-`response` return shape — the retry machinery adds nothing to the
        happy path."""
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        _no_threading(monkeypatch)
        post = _RecordingPost()
        result = channel.send("the exact text", http_post=post)
        assert len(post.calls) == 1
        assert post.calls[0]["data"]["text"] == "the exact text"
        assert result["status"] == "sent" and result["sent"] is True
        assert "response" in result and "chunks" not in result

    def test_classifier_excludes_http_status_errors(self):
        """Unit guard on the discriminator: HTTPError and any 'HTTP 4xx/5xx'
        message are NOT transport; URLError / socket errors / the transport-error
        marker ARE. This is the line that keeps 400 off the retry path."""
        import socket as _socket
        import urllib.error as _ue
        # NOT transient (reached Telegram / has a status):
        http_err = _ue.HTTPError("u", 400, "Bad Request", {}, None)
        assert channel._is_transient_transport(http_err, "telegram HTTP 400") is False
        assert channel._is_transient_transport(
            RuntimeError("telegram HTTP 400"), "telegram HTTP 400") is False
        assert channel._is_transient_transport(
            RuntimeError("telegram HTTP 503"), "telegram HTTP 503") is False
        # IS transient (no HTTP response received):
        assert channel._is_transient_transport(
            RuntimeError("telegram transport error: URLError"),
            "telegram transport error: urlerror") is True
        assert channel._is_transient_transport(
            _ue.URLError("name resolution failed"), "urlopen error") is True
        assert channel._is_transient_transport(
            _socket.timeout("timed out"), "timed out") is True

    def test_transport_retry_never_leaks_token(self, monkeypatch):
        """A persistent transport failure whose raw message embeds the token-
        bearing URL is scrubbed in the returned error, exactly as the 400 path."""
        monkeypatch.setattr(env, "allow_sends", lambda: True)
        _set_env(monkeypatch)
        _no_threading(monkeypatch)
        boom = RuntimeError(
            f"<urlopen error> for https://api.telegram.org/bot{TOKEN}/sendMessage")
        post = _AlwaysTransient(exc=boom)
        result = channel.send("hi", http_post=post)
        assert result["sent"] is False
        assert TOKEN not in str(result)
        assert "api.telegram.org/bot" not in str(result)
