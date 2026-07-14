"""officer-inbound-poller.py — instant-ack + mechanical tap pipeline
(tap-pipeline fix 2026-07-11).

Pins the poller half of the contract (tap_wire's own semantics are pinned in
framework/comms/surface/tests/test_tap_wire.py):
  * the ack fires FIRST — before the mechanical apply, before any relay;
  * an EXPIRED callback id (Telegram's ~15s answer window lapsed behind a
    long-poll timeout storm) is logged once and NEVER retried; a transient
    blip gets exactly one retry;
  * a mechanically-handled defer injects NOTHING into the officer pane
    (no LLM in the loop); a decision receipt relays WITH the ⚙ note;
  * every failure fail-opens to the pre-wire bracket-line relay;
  * getUpdates timing derives from ONE constant pair (read > long-poll).

Run: python3.12 -m pytest cabinet/scripts/tests/test_inbound_poller_taps.py -q
"""
from __future__ import annotations

import importlib.util
import io
import urllib.error
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
POLLER = REPO / "cabinet/scripts/officer-inbound-poller.py"

_spec = importlib.util.spec_from_file_location("officer_inbound_poller_taps", POLLER)
poller = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(poller)


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    """Never touch the live feed/attention estate from these tests."""
    monkeypatch.setenv("CABINET_FEED_DIR", str(tmp_path / "feed"))
    monkeypatch.setenv("CABINET_ATTENTION_DIR", str(tmp_path / "attention"))


def _noop_log(*_a, **_k):
    pass


def _http_400(description: str) -> urllib.error.HTTPError:
    body = ('{"ok":false,"error_code":400,"description":"%s"}'
            % description).encode("utf-8")
    return urllib.error.HTTPError("https://api.telegram.org/botX/answerCallbackQuery",
                                  400, "Bad Request", {}, io.BytesIO(body))


# ---------------------------------------------------------------------------
# getUpdates timing — one source, honest margin
# ---------------------------------------------------------------------------

def test_read_timeout_exceeds_long_poll():
    assert poller.READ_TIMEOUT_S > poller.LONG_POLL_S
    assert poller.READ_TIMEOUT_S == poller.LONG_POLL_S + 10
    assert 0 < poller.ACK_TIMEOUT_S <= 10


# ---------------------------------------------------------------------------
# _ack_expired — expired-id classification
# ---------------------------------------------------------------------------

def test_ack_expired_matches_telegram_400_phrases():
    assert poller._ack_expired(_http_400(
        "Bad Request: query is too old and response timeout expired "
        "or query ID is invalid")) is True
    assert poller._ack_expired(_http_400("Bad Request: QUERY ID IS INVALID")) is True


def test_ack_expired_rejects_other_errors():
    assert poller._ack_expired(_http_400("Bad Request: message not found")) is False
    err500 = urllib.error.HTTPError("u", 500, "boom", {}, io.BytesIO(b"{}"))
    assert poller._ack_expired(err500) is False
    assert poller._ack_expired(RuntimeError("query is too old")) is False  # no .code


# ---------------------------------------------------------------------------
# answer_callback_now — instant, toast-bearing, expired-grace
# ---------------------------------------------------------------------------

def test_ack_ok_carries_toast():
    calls = []
    state = poller.answer_callback_now(
        lambda p, payload: calls.append((p, payload)), "cq1",
        "⏸ Deferred to next briefing", log=_noop_log)
    assert state == "ok"
    assert calls == [("answerCallbackQuery",
                      {"callback_query_id": "cq1",
                       "text": "⏸ Deferred to next briefing"})]


def test_ack_expired_logged_once_never_retried():
    calls, logs = [], []

    def _post(_p, _payload):
        calls.append(1)
        raise _http_400("Bad Request: query is too old and response "
                        "timeout expired or query ID is invalid")

    state = poller.answer_callback_now(_post, "cq2", "", log=logs.append)
    assert state == "expired"
    assert len(calls) == 1                       # NEVER retried
    assert len([l for l in logs if "expired" in l]) == 1   # logged once


def test_ack_transient_gets_exactly_one_retry():
    calls, logs = [], []

    def _post(_p, _payload):
        calls.append(1)
        raise RuntimeError("network blip")

    state = poller.answer_callback_now(_post, "cq3", "t", log=logs.append)
    assert state == "failed" and len(calls) == 2
    assert any("failed after retry" in l for l in logs)


def test_ack_transient_then_success():
    calls = []

    def _post(_p, _payload):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("blip")

    assert poller.answer_callback_now(_post, "cq4", "", log=_noop_log) == "ok"
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# handle_callback_query — ordering + mechanical semantics
# ---------------------------------------------------------------------------

def _cbq(data="cv2|tri|brief", mid=1061, frm=999, cq="cq9"):
    return {"id": cq, "from": {"id": frm},
            "message": {"message_id": mid}, "data": data}


def test_instant_ack_fires_before_apply_and_inject():
    events = []

    def _apply(data, *, message_id=None):
        events.append(("apply", data, message_id))
        return {"handled": True, "relay": True, "mode": "decision:ok",
                "summary": "approved via the verdict door"}

    poller.handle_callback_query(
        _cbq(data="cv2|ok|abc123abc123"), captain="999",
        api_post=lambda p, payload: events.append(("ack", p)),
        inject=lambda line: events.append(("inject", line)),
        feed_append=lambda row: events.append(("feed", row)),
        log=_noop_log, apply_tap=_apply)

    kinds = [e[0] for e in events]
    assert kinds.index("ack") < kinds.index("apply") < kinds.index("inject")


def test_defer_tap_is_mechanical_no_llm_injection():
    injected, feeds, acked = [], [], []

    def _apply(data, *, message_id=None):
        return {"handled": True, "relay": False, "mode": "pacing:tri|brief",
                "summary": "pacing control tri|brief applied", "marked": True}

    poller.handle_callback_query(
        _cbq(), captain="999",
        api_post=lambda p, payload: acked.append(payload),
        inject=injected.append, feed_append=feeds.append,
        log=_noop_log, apply_tap=_apply)

    assert injected == []                        # NO officer turn for a defer
    assert acked[0]["text"] == "⏸ Deferred to next briefing"   # instant toast
    assert feeds[0]["kind"] == "callback" and feeds[0]["ack"] == "ok"
    assert feeds[0]["mode"] == "pacing:tri|brief"


def test_decision_receipt_relays_with_gear_note():
    injected = []
    poller.handle_callback_query(
        _cbq(data="cv2|ok|abc123abc123", mid=42), captain="999",
        api_post=lambda p, payload: None,
        inject=injected.append, feed_append=lambda row: None,
        log=_noop_log,
        apply_tap=lambda d, *, message_id=None: {
            "handled": True, "relay": True, "mode": "decision:ok",
            "item_id": "sit-9", "outcome": "approved",
            "summary": "approved via the verdict door pid=x"})
    assert len(injected) == 1
    assert injected[0].startswith("[tg-callback message_id=42 data=cv2|ok|abc123abc123]")
    assert "[⚙ approved via the verdict door" in injected[0]


def test_expired_ack_still_applies_mechanically():
    applied, injected, feeds = [], [], []

    def _post(_p, _payload):
        raise _http_400("Bad Request: query is too old and response "
                        "timeout expired or query ID is invalid")

    poller.handle_callback_query(
        _cbq(), captain="999", api_post=_post,
        inject=injected.append, feed_append=feeds.append, log=_noop_log,
        apply_tap=lambda d, *, message_id=None: applied.append(d) or {
            "handled": True, "relay": False, "mode": "pacing:tri|brief",
            "summary": "applied"})
    assert applied == ["cv2|tri|brief"]          # tap DATA outlives the ack
    assert feeds[0]["ack"] == "expired"
    assert injected == []


def test_stray_tap_acked_but_never_applied():
    applied, injected, feeds, acked = [], [], [], []
    poller.handle_callback_query(
        _cbq(frm=555), captain="999",
        api_post=lambda p, payload: acked.append(p),
        inject=injected.append, feed_append=feeds.append, log=_noop_log,
        apply_tap=lambda d, **k: applied.append(d) or {"handled": True})
    assert acked == ["answerCallbackQuery"]      # spinner still cleared
    assert applied == [] and injected == [] and feeds == []


def test_apply_failure_falls_open_to_bare_relay():
    injected, logs = [], []

    def _apply(_d, *, message_id=None):
        raise RuntimeError("tap wire down")

    poller.handle_callback_query(
        _cbq(data="cv2|later|abc123abc123", mid=7), captain="999",
        api_post=lambda p, payload: None,
        inject=injected.append, feed_append=lambda row: None,
        log=logs.append, apply_tap=_apply)
    assert injected == ["[tg-callback message_id=7 data=cv2|later|abc123abc123]"]
    assert any("falling back to relay" in l for l in logs)
