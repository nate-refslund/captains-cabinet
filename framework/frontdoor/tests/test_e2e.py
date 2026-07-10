"""End-to-end front-door send-path tests — drain → compose → channel.send.

Exercises the integrated runner (framework.frontdoor.run_frontdoor.run_send_path)
across the three urgency tiers:

  * the three fake intake items (one per tier) are drained, woven into ONE
    unified message, and that message carries each item's provenance
    (source + summary + why);
  * the send is MOCKED — no real network call ever happens;
  * in dev mode (the default, allow_sends() False) the channel gate short-
    circuits: NOTHING is sent (status 'blocked-dev', sent False), even though
    the message is composed;
  * forcing the env gate True (monkeypatched) routes the composed text to the
    mocked http_post, hitting api.telegram.org/sendMessage with
    chat_id == CAPTAIN_TELEGRAM_ID, and the token never appears in the result.

Two layers:
  - Seam-injected E2E (no Redis): passes drain_fn/ack_fn seams so the full
    drain→compose→send wiring runs deterministically in CI with no server.
  - Redis-backed E2E: when redis-cli can reach a server, enqueue the 3 items to
    a UNIQUE test-prefixed stream key and run the real intake.drain through the
    runner. Skips cleanly when no Redis is reachable (fakeredis not installed).
    Uses a test key (cabinet:frontdoor:intake:test:<uuid>) with teardown — never
    the production key.
"""
from __future__ import annotations

import uuid

import pytest

from framework import env
from framework.frontdoor import intake, run_frontdoor


# ---------------------------------------------------------------------------
# Fixtures: three fake intake items, one per urgency tier.
# ---------------------------------------------------------------------------
def _three_tier_items() -> list[dict]:
    """One item per tier, each with full provenance (source + summary + why)."""
    return [
        {
            "id": "1-0",
            "source": "deploy-alert",
            "kind": "deploy-alert",
            "ts": "2026-06-22T08:30:00Z",
            "urgency_tier": "ping-now",
            "payload": {"summary": "Acme prod deploy failed"},
            "context": {"why": "build broke on the impersonation-cookie fix"},
        },
        {
            "id": "2-0",
            "source": "morning-brief",
            "kind": "brief",
            "ts": "2026-06-22T07:00:00Z",
            "urgency_tier": "batch",
            "payload": {"summary": "3 critical checkout bugs still overdue"},
            "context": {"why": "due 2026-06-09, blocking the launch"},
        },
        {
            "id": "3-0",
            "source": "commitment-ledger",
            "kind": "fyi",
            "ts": "2026-06-22T06:45:00Z",
            "urgency_tier": "fyi",
            "payload": {"summary": "Robin wants a salary conversation"},
            "context": {"why": "raised on Teams, no date set yet"},
        },
    ]


class _RecordingPost:
    """A mock http_post that records calls and returns a canned Telegram 200.

    NEVER touches the network. Asserts (via the recorded call) that the runner
    routed to api.telegram.org with the captain chat id and the exact text.
    """

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url: str, data: dict) -> dict:
        self.calls.append((url, data))
        return {"ok": True, "result": {"message_id": 999}}


# ---------------------------------------------------------------------------
# 1. Seam-injected E2E — no Redis. The core integration assertion.
# ---------------------------------------------------------------------------
def test_e2e_dev_composes_one_unified_message_but_does_not_send():
    """Dev default: drain→compose yields ONE message with all 3 items'
    provenance; the send is gated (blocked-dev) so NOTHING leaves the machine."""
    items = _three_tier_items()
    acked: list = []

    def fake_drain(*, since=None, stream_key=None, count=100, consumer="chair"):
        return items

    def fake_ack(ids, *, stream_key=None):  # should never be called in dev
        acked.append(ids)
        return len(ids if isinstance(ids, list) else [ids])

    post = _RecordingPost()

    # Dev default — allow_sends() is False unless CABINET_ENV=runtime.
    assert env.allow_sends() is False

    out = run_frontdoor.run_send_path(
        drain_fn=fake_drain, ack_fn=fake_ack, http_post=post,
    )

    # ONE unified message containing every item's provenance.
    text = out["text"]
    assert text, "expected a composed message"
    for it in items:
        assert it["source"] in text          # provenance: source
        assert it["payload"]["summary"] in text
        assert it["context"]["why"] in text  # provenance: why
    # Exactly one message string (not three) — all three tiers woven together.
    assert "🔴" in text and "📋" in text and "💡" in text
    # ping-now section precedes batch precedes fyi (one ordered message).
    assert text.index("Acme prod deploy failed") < text.index(
        "3 critical checkout bugs still overdue")
    assert text.index("3 critical checkout bugs still overdue") < text.index(
        "Robin wants a salary conversation")

    # DEV GATE: nothing sent, no network call, no ack.
    assert out["allow_sends"] is False
    assert out["sent"] is False
    assert out["send"] == {"status": "blocked-dev", "sent": False}
    assert post.calls == [], "channel.send must NOT call http_post in dev"
    assert acked == [], "items must stay pending (no ack) when not sent"
    assert out["acked"] == 0
    # drained the 3, their ids surfaced for a later runtime drain.
    assert out["drained"] == 3
    assert out["item_ids"] == ["1-0", "2-0", "3-0"]


def test_e2e_runtime_sends_one_message_to_captain_token_never_leaks(monkeypatch):
    """Force the env gate True: the SAME composed text is POSTed to Telegram's
    sendMessage with chat_id == CAPTAIN_TELEGRAM_ID; token never leaks; items
    are acked only after the confirmed send."""
    items = _three_tier_items()
    secret = "123456:SUPER-SECRET-BOT-TOKEN"
    acked: list = []

    def fake_drain(*, since=None, stream_key=None, count=100, consumer="chair"):
        return items

    def fake_ack(ids, *, stream_key=None):
        acked.append(ids)
        return len(ids)

    # Force runtime sends ON, and supply env the channel reads.
    monkeypatch.setattr(env, "allow_sends", lambda: True)
    monkeypatch.setenv("TELEGRAM_COS_TOKEN", secret)
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", "55500011")

    post = _RecordingPost()
    out = run_frontdoor.run_send_path(
        drain_fn=fake_drain, ack_fn=fake_ack, http_post=post,
    )

    assert out["allow_sends"] is True
    assert out["sent"] is True
    # exactly ONE send call, to the Telegram sendMessage endpoint.
    assert len(post.calls) == 1
    url, data = post.calls[0]
    assert "api.telegram.org" in url
    assert url.endswith("/sendMessage")
    # recipient is ALWAYS the captain id — never overridable.
    assert data["chat_id"] == "55500011"
    # the exact composed text was sent.
    assert data["text"] == out["text"]

    # TOKEN SAFETY: the secret appears nowhere in the surfaced result.
    assert secret not in str(out)
    assert secret not in str(out["send"])

    # ack happened exactly once, for all three ids, only after the send.
    assert acked == [["1-0", "2-0", "3-0"]]
    assert out["acked"] == 3


def test_e2e_empty_drain_sends_nothing(monkeypatch):
    """No items drained -> empty compose -> the Chair sends nothing (no call)."""
    def fake_drain(*, since=None, stream_key=None, count=100, consumer="chair"):
        return []

    post = _RecordingPost()
    # Even forcing runtime, an empty message must not be sent.
    monkeypatch.setattr(env, "allow_sends", lambda: True)
    monkeypatch.setenv("TELEGRAM_COS_TOKEN", "tok")
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", "1")

    out = run_frontdoor.run_send_path(drain_fn=fake_drain, http_post=post)
    assert out["text"] == ""
    assert out["sent"] is False
    assert out["send"] is None
    assert post.calls == []


def test_e2e_send_error_does_not_ack(monkeypatch):
    """A send that fails (sent False) must NOT ack — items stay recoverable."""
    items = _three_tier_items()
    acked: list = []

    def fake_drain(*, since=None, stream_key=None, count=100, consumer="chair"):
        return items

    def fake_ack(ids, *, stream_key=None):
        acked.append(ids)
        return len(ids)

    def failing_send(text, *, http_post=None):
        return {"status": "error", "sent": False, "error": "telegram HTTP 500"}

    out = run_frontdoor.run_send_path(
        drain_fn=fake_drain, ack_fn=fake_ack, send_fn=failing_send,
    )
    assert out["sent"] is False
    assert out["acked"] == 0
    assert acked == [], "no ack on a failed send — items must survive"


# ---------------------------------------------------------------------------
# 2. Redis-backed E2E — exercises the REAL intake.drain through the runner.
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
    key = f"cabinet:frontdoor:intake:test:{uuid.uuid4()}"
    assert key != "cabinet:frontdoor:intake"  # never production
    yield key
    try:
        intake._redis().delete(key)
    except Exception:
        pass


@redis_required
def test_e2e_real_intake_drain_compose_blocked_in_dev(stream_key):
    """Enqueue 3 tiered items to a real test stream, run the runner end-to-end
    against the REAL intake.drain. Dev gate blocks the send; the composed
    message still carries all three; items stay pending (no ack)."""
    items = _three_tier_items()
    # Producers MUST NOT supply 'id' — strip it; Redis assigns it.
    for it in items:
        it.pop("id", None)
        intake.enqueue(it, stream_key=stream_key)

    assert env.allow_sends() is False
    post = _RecordingPost()
    out = run_frontdoor.run_send_path(stream_key=stream_key, http_post=post)

    assert out["drained"] == 3
    text = out["text"]
    assert "Acme prod deploy failed" in text
    assert "3 critical checkout bugs still overdue" in text
    assert "Robin wants a salary conversation" in text
    # dev gate: nothing sent, nothing acked.
    assert out["sent"] is False
    assert out["send"] == {"status": "blocked-dev", "sent": False}
    assert post.calls == []
    assert out["acked"] == 0

    # The Redis-assigned ids round-tripped (not the producer placeholders).
    assert len(out["item_ids"]) == 3
    assert all(intake._looks_like_id(i) for i in out["item_ids"])


@redis_required
def test_e2e_real_intake_runtime_sends_and_acks(monkeypatch, stream_key):
    """Forcing runtime: the 3 enqueued items drain, compose, send (mocked), and
    are acked off the real stream so a re-drain does not re-yield them."""
    items = _three_tier_items()
    for it in items:
        it.pop("id", None)
        intake.enqueue(it, stream_key=stream_key)

    monkeypatch.setattr(env, "allow_sends", lambda: True)
    monkeypatch.setenv("TELEGRAM_COS_TOKEN", "999:tok")
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", "42")

    post = _RecordingPost()
    out = run_frontdoor.run_send_path(stream_key=stream_key, http_post=post)

    assert out["sent"] is True
    assert out["acked"] == 3
    assert len(post.calls) == 1
    assert post.calls[0][1]["chat_id"] == "42"
    assert "999:tok" not in str(out)

    # Acked items are gone from the new-delivery view.
    again = intake.drain(stream_key=stream_key)
    assert again == []
