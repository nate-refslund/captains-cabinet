"""Engine callback grammar + the buttons seam through tools → gate → adapter."""
from __future__ import annotations

from datetime import timedelta

from framework.attention import gate
from framework.comms import tools
from framework.comms.adapters.telegram import TelegramAdapter
from framework.comms.surface import decision_card as dc
from framework.comms.surface import engine, pacing

from .conftest import make_card, make_census


# ---------------------------------------------------------------------------
# Callback parsing — strict allowlist
# ---------------------------------------------------------------------------

def test_parse_callback_strict():
    assert engine.parse_callback("cv2|tri|now") == ("tri", "now")
    assert engine.parse_callback("cv2|more") == ("more", "")
    assert engine.parse_callback("") is None
    assert engine.parse_callback("evil|tri|now") is None
    assert engine.parse_callback("cv2|rm -rf|x") is None
    assert engine.parse_callback("cv2|tri|has space") is None
    assert engine.parse_callback("cv2|unknownverb|x") is None


def test_on_callback_ignores_foreign_buttons(day):
    assert engine.on_callback("othersurface|go", now=day) == {"status": "ignored"}


def test_on_callback_triage_now_presents(day, adapter, charter):
    census = make_census([make_card(i) for i in range(4)])
    # seed: the nudge went out earlier
    _, st = pacing.plan(census, pacing.load_state(), day)
    pacing.save_state(st)
    res = engine.on_callback("cv2|tri|now", now=day + timedelta(minutes=1),
                             census=census, adapter=adapter, ch=charter)
    assert res["status"] == "ok" and res["routing"]["handled"]
    assert len([s for s in adapter.sends if s.get("buttons")]) >= 4


def test_on_callback_decision_routes_but_never_executes(day, adapter, charter):
    census = make_census([make_card(i) for i in range(2)])
    state = pacing.load_state()
    state["triage_open"] = True
    pacing.step(census=census, now=day, state=state, adapter=adapter, ch=charter)
    pacing.save_state(state)
    item_id = list(state["active"].keys())[0]
    h = state["active"][item_id]["h"]
    sends_before = len(adapter.sends)
    res = engine.on_callback(f"cv2|ok|{h}", now=day + timedelta(minutes=2),
                             census=census, adapter=adapter, ch=charter)
    # the tap ROUTES the decision to the org's door; nothing fires here
    assert res["routing"] == {"handled": True, "decision": "ok",
                              "item_id": item_id}
    assert len(adapter.sends) == sends_before


def test_report_outcome_flips_card_and_advances_pin(day, adapter, charter):
    cards = [make_card(1), make_card(2)]
    census = make_census(cards)
    state = pacing.load_state()
    state["triage_open"] = True
    pacing.step(census=census, now=day, state=state, adapter=adapter, ch=charter)
    pacing.save_state(state)
    item_id = cards[0]["id"]
    res = engine.report_outcome(item_id, "approved",
                                now=day + timedelta(minutes=3),
                                census=census, adapter=adapter, ch=charter)
    assert res["edited"] is True
    done_edits = [e for e in adapter.edits
                  if "Approved — done." in e["body"]]
    assert done_edits, "the card flipped in place, no new message"
    assert done_edits[0]["buttons"] == [[{"text": "↩ Undo",
                                          "data": dc.cb("undo", dc.handle_of(item_id))}]]
    # pacing forgot the item
    assert item_id not in pacing.load_state()["active"]


# ---------------------------------------------------------------------------
# The buttons seam: tools → gate → adapter (and legacy transports)
# ---------------------------------------------------------------------------

def test_send_card_delivers_buttons_through_the_gate(day, adapter, charter):
    row = [{"text": "✓ Approve", "data": "cv2|ok|abc"}]
    res = tools.send_card(subject="Choose", situation="", kind="briefing",
                          evidence=["thread:test-1"], buttons=[row],
                          adapter=adapter, ch=charter, now=day)
    assert res["decision"]["action"] == "send"
    assert adapter.sends[0]["buttons"] == [row]
    # the edit path re-renders buttons too
    res2 = tools.edit_card(subject="Choose", evidence=["thread:test-1"],
                           situation="picked", state="done",
                           buttons=[[{"text": "↩ Undo", "data": "cv2|undo|abc"}]],
                           adapter=adapter, ch=charter, now=day)
    assert res2["decision"]["action"] == "edit"
    assert adapter.edits[0]["buttons"] == [[{"text": "↩ Undo",
                                             "data": "cv2|undo|abc"}]]


def test_gate_falls_back_for_legacy_transports_without_buttons(day, charter):
    calls = []

    def legacy_send(text, *, silent=False, feed_meta=None):   # no buttons kwarg
        calls.append(text)
        return {"status": "ok", "sent": True, "message_ids": [1]}

    decision = gate.decide({"kind": "briefing", "subject": "s", "evidence": [],
                            "buttons": [[{"text": "b", "data": "cv2|more"}]]},
                           ch=charter, now=day, standing={})
    res = gate.deliver(decision, send_fn=legacy_send, standing={})
    assert res["sent"] is True and calls == [decision["text"]]


def test_telegram_kb_maps_url_and_tap_buttons():
    kb = TelegramAdapter._kb([[{"text": "Go", "data": "cv2|ok|x"},
                               {"text": "Open", "url": "https://cab.example/queue"}]])
    assert kb == {"inline_keyboard": [[
        {"text": "Go", "callback_data": "cv2|ok|x"},
        {"text": "Open", "url": "https://cab.example/queue"},
    ]]}
    assert TelegramAdapter._kb(None) is None
    flat = TelegramAdapter._kb([{"text": "One", "data": "d" * 99}])
    assert len(flat["inline_keyboard"][0][0]["callback_data"]) == 64


def test_null_adapter_tolerates_buttons(day):
    from framework.comms.adapters.null import NullAdapter
    res = NullAdapter().send("x", buttons=[[{"text": "b", "data": "d"}]])
    assert res["status"] == "unsupported"
