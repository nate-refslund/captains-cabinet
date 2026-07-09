"""Comms C1 — the channel-agnostic adapter seam (spec §3, §7). The resolver
binds an adapter from instance config; a clean-room box binds null and every
tool degrades to a no-op; the Telegram adapter delegates to the gated
channel.py without naming the Bot API itself."""
import pytest

from framework.comms import get_channel as gc
from framework.comms.channel_adapter import ChannelAdapter, CAPABILITIES, unsupported
from framework.comms.adapters.telegram import TelegramAdapter
from framework.comms.adapters.null import NullAdapter


def test_both_adapters_satisfy_the_protocol():
    assert isinstance(TelegramAdapter(), ChannelAdapter)
    assert isinstance(NullAdapter(), ChannelAdapter)


def test_resolver_env_override_binds_null(monkeypatch):
    monkeypatch.setenv("CABINET_CHANNEL", "null")
    a = gc.get_channel(force=True)
    assert isinstance(a, NullAdapter)


def test_resolver_default_is_telegram(monkeypatch):
    monkeypatch.delenv("CABINET_CHANNEL", raising=False)
    monkeypatch.setattr(gc, "_configured_channel", lambda: "telegram")
    assert isinstance(gc.get_channel(force=True), TelegramAdapter)


def test_resolver_unknown_channel_fails_closed_to_null(monkeypatch):
    monkeypatch.setenv("CABINET_CHANNEL", "carrier-pigeon")
    assert isinstance(gc.get_channel(force=True), NullAdapter)


def test_null_adapter_is_all_noops(capsys):
    a = NullAdapter()
    assert a.capabilities() == {}
    for call in (lambda: a.send("x"), lambda: a.poll("q", ["a"]),
                 lambda: a.react(1, "👍"), lambda: a.pin(1), lambda: a.open_thread("l")):
        r = call()
        assert r["sent"] is False and r["status"] == "unsupported"
    assert "no channel bound" in capsys.readouterr().err


def test_telegram_adapter_delegates_to_channel(monkeypatch):
    """The adapter must go THROUGH channel.py (the one door), not the Bot API."""
    from framework.frontdoor import channel
    seen = {}
    monkeypatch.setattr(channel, "send",
                        lambda body, **kw: seen.update(kw, body=body) or {"sent": True, "message_ids": [7]})
    a = TelegramAdapter()
    r = a.send("hi", silent=True, thread_id=5,
               buttons=[{"text": "ok", "data": "gw:ok"}])
    assert r["message_ids"] == [7]
    assert seen["silent"] is True and seen["thread_id"] == 5
    # channel-neutral buttons → telegram inline_keyboard
    assert seen["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "gw:ok"


def test_telegram_capabilities_full():
    caps = TelegramAdapter().capabilities()
    for c in ("send", "edit", "poll", "pin", "thread", "answer_tap"):
        assert caps.get(c) is True


def test_button_mapping_rows_and_single():
    a = TelegramAdapter()
    single = a._kb([{"text": "a", "data": "x"}])
    assert len(single["inline_keyboard"]) == 1 and len(single["inline_keyboard"][0]) == 1
    rows = a._kb([[{"text": "a", "data": "x"}], [{"text": "b", "data": "y"}]])
    assert len(rows["inline_keyboard"]) == 2
    assert a._kb(None) is None


def test_unsupported_shape():
    r = unsupported("react")
    assert r == {"status": "unsupported", "sent": False, "capability": "react"}
    assert set(CAPABILITIES) >= {"send", "edit", "poll", "react", "thread"}
