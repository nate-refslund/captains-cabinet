"""Comms C2 — the LLM-native tool surface (spec §4). Each tool routes through
the gate + the bound adapter + the feed; dispatch is fail-soft; a tool whose
capability the adapter lacks degrades to the adapter's unsupported no-op."""
import pytest

from framework.comms import tools


class FakeAdapter:
    """Records what the tools push at the channel, with a full capability set."""
    def __init__(self, caps=None):
        self._caps = caps if caps is not None else {
            c: True for c in ("send", "edit", "react", "poll", "set_status",
                              "pin", "thread", "answer_tap", "draft", "rich",
                              "observe_reply_current", "observe_react_current")}
        self.calls = []

    def capabilities(self):
        return dict(self._caps)

    def send(self, body, **kw):
        self.calls.append(("send", body, kw))
        return {"sent": True, "message_ids": [11]}

    def edit(self, message_id, body, **kw):
        self.calls.append(("edit", message_id, body, kw))
        return {"sent": True, "message_ids": [message_id]}

    def react(self, message_id, emoji):
        self.calls.append(("react", message_id, emoji))
        return {"sent": True, "reaction": emoji}

    def observe_reply_current(self, text):
        self.calls.append(("observe_reply_current", text))
        return {"sent": True, "message_ids": [14]}

    def observe_react_current(self, emoji):
        self.calls.append(("observe_react_current", emoji))
        return {"sent": True, "reaction": emoji}

    def poll(self, question, options, **kw):
        self.calls.append(("poll", question, options, kw))
        return {"sent": True, "message_ids": [12]}

    def set_status(self, kind="typing"):
        self.calls.append(("set_status", kind))
        return {"sent": True, "status": "ok"}

    def pin(self, message_id, **kw):
        self.calls.append(("pin", message_id))
        return {"sent": True}

    def unpin(self, message_id=None):
        self.calls.append(("unpin", message_id))
        return {"sent": True}

    def open_thread(self, name):
        self.calls.append(("open_thread", name))
        return {"sent": True, "thread_id": 99}

    def answer_tap(self, tap_id, toast=""):
        self.calls.append(("answer_tap", tap_id, toast))
        return {"sent": True}

    def send_draft(self, draft_id, text="", *, thread_id=None):
        self.calls.append(("send_draft", draft_id, text, thread_id))
        return {"sent": True, "status": "sent"}

    def send_rich(self, markdown=None, *, html=None, silent=False, buttons=None, feed_meta=None):
        self.calls.append(("send_rich", markdown, html, feed_meta))
        return {"sent": True, "message_ids": [13]}


def test_dispatch_unknown_tool_is_error_not_raise():
    r = tools.dispatch("nope", {})
    assert r["status"] == "error" and "unknown comms tool" in r["error"]


def test_dispatch_bad_args_is_error_not_raise():
    # send_card requires subject (keyword-only); missing it → caught TypeError
    r = tools.dispatch("send_card", {"situation": "x"})
    assert r["status"] == "error" and "bad args" in r["error"]


def test_send_card_routes_through_gate_with_adapter_send(monkeypatch):
    from framework.attention import gate
    seen = {}

    def fake_submit(item, **kw):
        seen["item"] = item
        seen["send_fn"] = kw.get("send_fn")
        seen["edit_fn"] = kw.get("edit_fn")
        seen["chair_review"] = kw.get("chair_review")
        return {"status": "sent", "message_ids": [11]}

    monkeypatch.setattr(gate, "submit", fake_submit)
    a = FakeAdapter()
    r = tools.send_card(subject="Deploy failing", situation="prod 500s",
                        lane="bakery", steps=[{"do": "rollback"}],
                        chair_review=True, adapter=a)
    assert r["status"] == "sent"
    # the gate got the STRUCTURED item and the ADAPTER's send/edit as the backend
    assert seen["item"]["subject"] == "Deploy failing"
    assert seen["item"]["lane"] == "bakery"
    assert seen["send_fn"] == a.send and seen["edit_fn"] == a.edit
    assert seen["chair_review"] is True


def test_send_card_forwards_state_to_item(monkeypatch):
    """The gate renders state into the card, so state MUST reach the item —
    without it, edit_card's state-flip is a silent no-op (gauntlet MEDIUM)."""
    from framework.attention import gate
    seen = {}
    monkeypatch.setattr(gate, "submit", lambda item, **kw: seen.update(item=item) or {"status": "sent"})
    tools.send_card(subject="Deploy", evidence=["m:1"], state="done", adapter=FakeAdapter())
    assert seen["item"]["state"] == "done"


def test_edit_card_reuses_identity_and_flips_state(monkeypatch):
    """edit_card must re-drive the gate with the SAME identity (subject+evidence)
    so the gate's identity path finds the existing card and edits it — NOT emit a
    fresh card. It must NOT depend on a situation_key it ignores (gauntlet HIGH)."""
    from framework.attention import gate
    seen = {}
    monkeypatch.setattr(gate, "submit", lambda item, **kw: seen.update(item=item) or {"status": "edited"})
    tools.edit_card(subject="Deploy Bakery", evidence=["monday:42424242"],
                    state="done", steps=[{"title": "rolled out"}], adapter=FakeAdapter())
    # identity fields forwarded verbatim → same situation_key as the original send
    assert seen["item"]["subject"] == "Deploy Bakery"
    assert seen["item"]["evidence"] == ["monday:42424242"]
    assert seen["item"]["state"] == "done"
    # edit_card no longer takes a situation_key it would ignore
    import inspect
    assert "situation_key" not in inspect.signature(tools.edit_card).parameters


def test_react_uses_adapter_when_capable():
    a = FakeAdapter()
    r = tools.react(message_id=968, emoji="🤔", adapter=a)
    assert r["reaction"] == "🤔"
    assert ("react", 968, "🤔") in a.calls


def test_react_degrades_when_adapter_lacks_capability():
    a = FakeAdapter(caps={"send": True})  # no react capability
    r = tools.react(message_id=1, emoji="👍", adapter=a)
    assert r == {"status": "unsupported", "sent": False, "capability": "react"}
    assert a.calls == []  # never touched the adapter


def test_observe_current_tools_have_no_recipient_or_message_id_surface():
    a = FakeAdapter()
    assert tools.reply_current(text="hello", adapter=a)["sent"] is True
    assert tools.react_current(emoji="👀", adapter=a)["sent"] is True
    assert ("observe_reply_current", "hello") in a.calls
    assert ("observe_react_current", "👀") in a.calls


def test_observe_current_tools_reject_fanout_and_oversized_reaction():
    a = FakeAdapter()
    reply = tools.reply_current(
        text="x" * (tools.OBSERVE_REPLY_MAX_CHARS + 1), adapter=a)
    reaction = tools.react_current(
        emoji="x" * (tools.OBSERVE_REACTION_MAX_CHARS + 1), adapter=a)
    assert reply["sent"] is False
    assert reaction["sent"] is False
    assert a.calls == []


def test_poll_passes_options_and_multi():
    a = FakeAdapter()
    r = tools.poll(question="Ship it?", options=["yes", "no"], multi=True, adapter=a)
    assert r["message_ids"] == [12]
    kind, q, opts, kw = a.calls[0]
    assert kind == "poll" and opts == ["yes", "no"] and kw["multi"] is True


def test_set_status_degrades_without_capability():
    a = FakeAdapter(caps={})
    assert tools.set_status(kind="thinking", adapter=a)["sent"] is False


def test_open_thread_returns_thread_id():
    a = FakeAdapter()
    assert tools.open_thread(lane="bakery", adapter=a)["thread_id"] == 99


def test_read_feed_returns_rows_and_cursor(monkeypatch):
    from framework.attention import feed
    monkeypatch.setattr(feed, "feed_since", lambda cursor, max_n=200: ([{"row": 1}], cursor + 1))
    r = tools.read_feed(cursor=5)
    assert r["status"] == "ok" and r["rows"] == [{"row": 1}] and r["cursor"] == 6


def test_read_feed_is_fail_soft(monkeypatch):
    from framework.attention import feed
    def boom(cursor, max_n=200):
        raise RuntimeError("journal locked")
    monkeypatch.setattr(feed, "feed_since", boom)
    r = tools.read_feed(cursor=5)
    assert r["status"] == "error" and r["cursor"] == 5 and r["rows"] == []


def test_read_feed_consumer_auto_cursor(monkeypatch):
    """consumer mode auto-manages the durable cursor: load → feed_since → store,
    so the officer never tracks a cursor itself."""
    from framework.attention import feed
    calls = {}
    def fake_load(c): calls["loaded"] = c; return 5
    def fake_since(cur, max_n=200): calls["since_from"] = cur; return ([{"seq": 6}], 6)
    def fake_store(c, seq): calls["stored"] = (c, seq)
    monkeypatch.setattr(feed, "load_cursor", fake_load)
    monkeypatch.setattr(feed, "feed_since", fake_since)
    monkeypatch.setattr(feed, "store_cursor", fake_store)
    r = tools.read_feed(consumer="cos")
    assert r["status"] == "ok" and r["cursor"] == 6 and r["rows"] == [{"seq": 6}]
    assert calls["loaded"] == "cos"          # loaded cos's stored cursor
    assert calls["since_from"] == 5          # read from there
    assert calls["stored"] == ("cos", 6)     # persisted the advance (never re-read)


def test_stream_thinking_streams_via_draft():
    a = FakeAdapter()
    tools.stream_thinking(draft_id=7, text="half", adapter=a)
    assert ("send_draft", 7, "half", None) in a.calls


def test_stream_thinking_degrades_without_draft_cap():
    a = FakeAdapter(caps={"send": True})
    assert tools.stream_thinking(adapter=a)["capability"] == "draft"


def test_send_rich_card_routes_to_send_rich():
    a = FakeAdapter()
    r = tools.send_rich_card(markdown="| a | b |", adapter=a)
    assert r["message_ids"] == [13]
    kind, md, html, meta = a.calls[0]
    assert kind == "send_rich" and md == "| a | b |" and meta["kind"] == "rich"


def test_send_rich_card_degrades_without_rich_cap():
    a = FakeAdapter(caps={"send": True})
    assert tools.send_rich_card(markdown="x", adapter=a)["capability"] == "rich"


def test_registry_covers_every_tool():
    for name in ("reply_current", "react_current", "send_card", "edit_card", "react", "poll", "set_status",
                 "pin", "unpin", "open_thread", "answer_tap", "read_feed",
                 "stream_thinking", "send_rich_card"):
        assert name in tools.TOOLS
