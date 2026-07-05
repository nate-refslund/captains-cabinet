"""AX-5 — Slack adapter: transport seam, token hygiene (env-only, never
logged/journaled), chat.postMessage / chat.delete, allow_sends gate."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.channels import contract as C
from framework.channels.slack import (
    DELETE_WINDOW_SECONDS,
    SlackAdapter,
    default_transport,
)
from framework.events.emitter import replay

TOKEN = "xoxb-test-secret-token-0000"
ORG = frozenset({"acme.com"})

OK_POST = {"ok": True, "channel": "C123", "ts": "1720.000042"}
OK_DELETE = {"ok": True, "channel": "C123", "ts": "1720.000042"}


class FakeTransport:
    def __init__(self, responses=None, exc=None):
        self.calls = []
        self.responses = list(responses or [])
        self.exc = exc

    def __call__(self, method, payload, token):
        self.calls.append(
            {"method": method, "payload": dict(payload), "token": token})
        if self.exc is not None:
            raise self.exc
        return self.responses.pop(0)


def make_adapter(monkeypatch, transport, token=TOKEN):
    if token is not None:
        monkeypatch.setenv("SLACK_BOT_TOKEN", token)
    return SlackAdapter(transport=transport, org_domains=ORG)


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------

def test_send_posts_chat_postmessage_and_returns_channel_ts(monkeypatch):
    t = FakeTransport(responses=[OK_POST])
    adapter = make_adapter(monkeypatch, t)
    art = adapter.send("C123", "hello")
    assert art == "C123:1720.000042"
    assert len(t.calls) == 1
    call = t.calls[0]
    assert call["method"] == "chat.postMessage"
    assert call["payload"] == {"channel": "C123", "text": "hello"}
    assert call["token"] == TOKEN
    events = replay(event_types=["outbox_dispatched"])
    assert len(events) == 1
    assert events[0]["payload"]["channel"] == "slack"
    assert events[0]["payload"]["artifact_id"] == "C123:1720.000042"


def test_send_threads_via_thread_ts(monkeypatch):
    t = FakeTransport(responses=[OK_POST])
    adapter = make_adapter(monkeypatch, t)
    adapter.send("C123", "hello", thread_id="1719.9")
    assert t.calls[0]["payload"]["thread_ts"] == "1719.9"


def test_missing_token_fails_closed_before_any_transport_call(monkeypatch):
    t = FakeTransport(responses=[OK_POST])
    adapter = make_adapter(monkeypatch, t, token=None)
    with pytest.raises(C.ChannelConfigError, match="SLACK_BOT_TOKEN"):
        adapter.send("C123", "hello")
    assert t.calls == []  # never reached the transport
    assert len(replay(event_types=["outbox_failed"])) == 1


def test_api_error_raises_and_journals(monkeypatch):
    t = FakeTransport(responses=[{"ok": False, "error": "channel_not_found"}])
    adapter = make_adapter(monkeypatch, t)
    with pytest.raises(C.ChannelSendError, match="channel_not_found"):
        adapter.send("CBAD", "hello")
    failed = replay(event_types=["outbox_failed"])
    assert len(failed) == 1
    assert "channel_not_found" in failed[0]["payload"]["error"]


def test_transport_exception_is_scrubbed_of_the_token(monkeypatch):
    t = FakeTransport(exc=RuntimeError("boom %s boom" % TOKEN))
    adapter = make_adapter(monkeypatch, t)
    with pytest.raises(C.ChannelSendError) as ei:
        adapter.send("C123", "hello")
    assert TOKEN not in str(ei.value)
    assert "[SLACK_BOT_TOKEN]" in str(ei.value)
    assert ei.value.__cause__ is None  # no token-bearing cause chain
    dump = json.dumps(replay(event_types=["outbox_failed"]))
    assert TOKEN not in dump


def test_token_is_never_stored_on_the_instance(monkeypatch):
    t = FakeTransport(responses=[OK_POST])
    adapter = make_adapter(monkeypatch, t)
    adapter.send("C123", "hello")
    assert TOKEN not in repr(vars(adapter))


@pytest.mark.parametrize("resp", [
    {"ok": True},                       # no channel/ts
    {"ok": True, "channel": "C1"},      # no ts
    {"ok": True, "channel": 1, "ts": 2},
])
def test_response_without_channel_ts_is_a_failed_send(monkeypatch, resp):
    adapter = make_adapter(monkeypatch, FakeTransport(responses=[resp]))
    with pytest.raises(C.ChannelSendError, match="channel/ts"):
        adapter.send("C123", "hello")


def test_non_mapping_response_is_a_failed_send(monkeypatch):
    adapter = make_adapter(monkeypatch, FakeTransport(responses=["nope"]))
    with pytest.raises(C.ChannelSendError, match="non-mapping"):
        adapter.send("C123", "hello")


# ---------------------------------------------------------------------------
# delete (pseudo-undo)
# ---------------------------------------------------------------------------

def test_delete_calls_chat_delete_with_parsed_artifact(monkeypatch):
    t = FakeTransport(responses=[OK_DELETE])
    adapter = make_adapter(monkeypatch, t)
    assert adapter.delete("C123:1720.000042") is True
    call = t.calls[0]
    assert call["method"] == "chat.delete"
    assert call["payload"] == {"channel": "C123", "ts": "1720.000042"}


@pytest.mark.parametrize("artifact", ["noseparator", "", ":ts-only",
                                      "chan:", None, 42])
def test_delete_rejects_malformed_artifact_ids(monkeypatch, artifact):
    t = FakeTransport(responses=[OK_DELETE])
    adapter = make_adapter(monkeypatch, t)
    with pytest.raises(C.ChannelDeleteError):
        adapter.delete(artifact)
    assert t.calls == []


def test_delete_api_error_raises_delete_error(monkeypatch):
    t = FakeTransport(responses=[{"ok": False, "error": "cant_delete_message"}])
    adapter = make_adapter(monkeypatch, t)
    with pytest.raises(C.ChannelDeleteError, match="cant_delete_message"):
        adapter.delete("C123:1720.000042")


# ---------------------------------------------------------------------------
# the LIVE default transport is hard-gated (no network outside runtime)
# ---------------------------------------------------------------------------

def test_default_transport_refuses_outside_runtime(monkeypatch):
    def no_network(*_a, **_k):  # any socket attempt fails the test
        raise AssertionError("network attempted from a non-runtime session")
    monkeypatch.setattr("urllib.request.urlopen", no_network)
    with pytest.raises(C.ChannelSendError, match="runtime"):
        default_transport("chat.postMessage", {"channel": "C1"}, TOKEN)


def test_default_transport_refuses_in_explicit_dev_env(monkeypatch):
    monkeypatch.setenv("CABINET_ENV", "dev")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_k: pytest.fail("network attempted in dev"))
    with pytest.raises(C.ChannelSendError, match="runtime"):
        default_transport("chat.postMessage", {"channel": "C1"}, TOKEN)


# ---------------------------------------------------------------------------
# contract surface
# ---------------------------------------------------------------------------

def test_slack_contract_surface(monkeypatch):
    assert SlackAdapter.name == "slack"
    assert SlackAdapter.capabilities == frozenset({"send", "delete"})
    assert str(SlackAdapter.undo_contract) == \
        "delete_window(%d)" % DELETE_WINDOW_SECONDS
    adapter = make_adapter(monkeypatch, FakeTransport(responses=[OK_POST]))
    assert adapter.classify("bob@acme.com") == C.INTERNAL
    assert adapter.classify("C123") == C.EXTERNAL  # opaque channel id
