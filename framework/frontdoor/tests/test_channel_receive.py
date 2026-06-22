"""channel.receive — inbound getUpdates: CAPTAIN-only, offset-managed, fail-safe.

http_get is injected, so no network is touched.
"""
import json

from framework.frontdoor import channel


def _resp(updates):
    return {"ok": True, "result": updates}


def _upd(update_id, chat_id, text, message_id=1, date=100):
    return {"update_id": update_id,
            "message": {"message_id": message_id, "date": date,
                        "text": text, "chat": {"id": chat_id}}}


def test_keeps_captain_ignores_others(monkeypatch):
    monkeypatch.setenv("TELEGRAM_COS_TOKEN", "tok")
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", "999")

    def fake_get(url, params, timeout):
        return _resp([_upd(10, 999, "from captain"),
                      _upd(11, 555, "from stranger")])

    msgs, off = channel.receive(http_get=fake_get)
    assert [m["text"] for m in msgs] == ["from captain"]   # stranger ignored
    assert off == 12                                        # advanced past BOTH
    assert all("tok" not in json.dumps(m) for m in msgs)   # token never in output


def test_offset_passed_and_unchanged_when_empty(monkeypatch):
    monkeypatch.setenv("TELEGRAM_COS_TOKEN", "tok")
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", "999")
    seen = {}

    def fake_get(url, params, timeout):
        seen["offset"] = params.get("offset")
        return _resp([])

    msgs, off = channel.receive(offset=42, http_get=fake_get)
    assert seen["offset"] == 42
    assert msgs == [] and off == 42


def test_no_token_returns_empty(monkeypatch):
    monkeypatch.delenv("TELEGRAM_COS_TOKEN", raising=False)
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", "999")
    assert channel.receive(offset=5) == ([], 5)


def test_transport_error_fails_safe(monkeypatch):
    monkeypatch.setenv("TELEGRAM_COS_TOKEN", "tok")
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", "999")

    def boom(url, params, timeout):
        raise RuntimeError("network down")

    assert channel.receive(offset=7, http_get=boom) == ([], 7)


def test_ignores_nontext_and_advances(monkeypatch):
    monkeypatch.setenv("TELEGRAM_COS_TOKEN", "tok")
    monkeypatch.setenv("CAPTAIN_TELEGRAM_ID", "999")

    def fake_get(url, params, timeout):
        return _resp([{"update_id": 20, "message": {"chat": {"id": 999}}},  # no text
                      _upd(21, 999, "real")])

    msgs, off = channel.receive(http_get=fake_get)
    assert [m["text"] for m in msgs] == ["real"]
    assert off == 22
