"""Overview pin (pin_mode: overview — Captain-ratified 2026-07-10):
ONE standing "⚑ N need you" card, pinned once, edited in place on census
change, all-clear face at N=0 (never unpinned), plain-language lawful."""
from __future__ import annotations

import json

from framework.attention import plain as plainlaw
from framework.comms.surface import overview_card as ov
from framework.comms.surface import pin_lifecycle as pin

from .conftest import make_card, make_census


def _cfg(**over):
    from framework.comms.surface import config as scfg
    cfg = scfg.load()
    cfg["pin_mode"] = "overview"
    cfg.update(over)
    return cfg


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def test_subject_counts_and_names_when_small(day):
    census = make_census([make_card(1), make_card(2), make_card(3)])
    kw = ov.render(census, now=day, cfg=_cfg(), whys={})
    assert kw["subject"] == "⚑ 3 need you"
    assert [s["title"] for s in kw["steps"]] == [
        "Decide thing number 1", "Decide thing number 2",
        "Decide thing number 3"]
    assert kw["evidence"] == ["thread:comms-surface-pin-overview"]
    assert kw["pid_marker"] is None and kw["buttons"] is None


def test_singular_and_all_clear_faces(day):
    one = ov.render(make_census([make_card(1)]), now=day, cfg=_cfg(), whys={})
    assert one["subject"] == "⚑ 1 needs you"
    dark = ov.render(make_census([]), now=day, cfg=_cfg(), whys={})
    assert dark["subject"] == plainlaw.COPY["masthead_dark"]
    assert dark["steps"] == [] and dark["state"] == "open"


def test_names_suppressed_above_five(day):
    cards = [make_card(i) for i in range(1, 7)]
    kw = ov.render(make_census(cards), now=day, cfg=_cfg(), whys={})
    assert kw["subject"] == "⚑ 6 need you"
    assert kw["steps"] == []          # ratified: top names only when N ≤ 5


def test_why_only_you_sentences_ride_their_item(day):
    cards = [make_card(1), make_card(2)]
    whys = {cards[0]["id"]: "only you can sign in and mint the new key"}
    kw = ov.render(make_census(cards), now=day, cfg=_cfg(), whys=whys)
    t0, t1 = [s["title"] for s in kw["steps"]]
    assert t0.endswith("— only you can sign in and mint the new key")
    assert "—" not in t1[len("Decide thing number 2"):]


def test_whys_file_is_fail_closed_and_scrubbed(tmp_path):
    p = tmp_path / "why-captain.json"
    assert ov.load_whys(p) == {}                       # absent
    p.write_text("{not json", encoding="utf-8")
    assert ov.load_whys(p) == {}                       # corrupt
    p.write_text(json.dumps({"sit-1": "a·b\nc", "sit-2": 7, "sit-3": "  "}),
                 encoding="utf-8")
    whys = ov.load_whys(p)
    assert whys == {"sit-1": "ab c"}                   # scrubbed, typed, non-empty


def test_render_is_plain_language_lawful(day):
    census = make_census([make_card(1), make_card(2)])
    kw = ov.render(census, now=day, cfg=_cfg(),
                   whys={make_card(1)["id"]: "it needs your signature"})
    text = " ".join([kw["subject"], kw["situation"]]
                    + [s["title"] for s in kw["steps"]])
    assert plainlaw.lint(text) == []                   # no org vocabulary
    assert "·" not in text                             # marker-hygiene law


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def test_first_tick_sends_and_pins_then_edits_in_place(adapter, day):
    state: dict = {}
    census = make_census([make_card(1), make_card(2)])
    rep = pin.overview_step(census=census, now=day, state=state,
                            cfg=_cfg(), adapter=adapter)
    assert state["mode"] == "overview"
    mid = state["message_id"]
    assert adapter.pins == [mid]
    assert "⚑ 2 need you" in adapter.sends[-1]["body"]
    assert rep["pinned_message_id"] == mid

    # queue change → the SAME message edits in place; no new pin, no new send
    census2 = make_census([make_card(2)])
    pin.overview_step(census=census2, now=day, state=state,
                      cfg=_cfg(), adapter=adapter)
    assert state["message_id"] == mid
    assert adapter.pins == [mid]                       # pinned exactly once
    assert adapter.edits[-1]["message_id"] == mid
    assert "⚑ 1 needs you" in adapter.edits[-1]["body"]


def test_no_change_suppresses_and_never_repins(adapter, day):
    state: dict = {}
    census = make_census([make_card(1)])
    pin.overview_step(census=census, now=day, state=state,
                      cfg=_cfg(), adapter=adapter)
    sends, edits, pins = (len(adapter.sends), len(adapter.edits),
                          len(adapter.pins))
    rep = pin.overview_step(census=census, now=day, state=state,
                            cfg=_cfg(), adapter=adapter)
    assert (len(adapter.sends), len(adapter.edits), len(adapter.pins)) == \
        (sends, edits, pins)                           # true no-op tick
    assert ("card", "suppress", state["message_id"]) in rep["ops"]


def test_all_clear_edits_face_but_keeps_the_pin(adapter, day):
    state: dict = {}
    pin.overview_step(census=make_census([make_card(1)]), now=day,
                      state=state, cfg=_cfg(), adapter=adapter)
    mid = state["message_id"]
    pin.overview_step(census=make_census([]), now=day, state=state,
                      cfg=_cfg(), adapter=adapter)
    assert state["message_id"] == mid
    assert adapter.unpins == []                        # all-clear face, still pinned
    assert plainlaw.COPY["masthead_dark"] in adapter.edits[-1]["body"]


def test_adopt_handoff_retires_the_single_item_pin(adapter, day):
    # legacy adopt-mode state: item pinned as message 555
    state = {"item_id": "sit-x", "message_id": 555, "own_card": True}
    pin.overview_step(census=make_census([make_card(1)]), now=day,
                      state=state, cfg=_cfg(), adapter=adapter)
    assert adapter.unpins == [555]                     # old pin retired once
    assert state["mode"] == "overview"
    assert state["message_id"] != 555 and adapter.pins == [state["message_id"]]


def test_quiet_hours_defer_the_first_pin(adapter, night):
    state: dict = {}
    rep = pin.overview_step(census=make_census([make_card(1)]), now=night,
                            state=state, cfg=_cfg(), adapter=adapter)
    assert adapter.pins == [] and adapter.sends == []  # charter routed it away
    assert ("pin", None, "deferred") in rep["ops"]
    assert state.get("message_id") is None


def test_step_dispatches_on_the_knob(adapter, day, monkeypatch):
    monkeypatch.setenv("CABINET_SURFACE_PIN_MODE", "overview")
    census = make_census([make_card(1)])
    rep = pin.step(census=census, now=day, state={}, adapter=adapter)
    assert rep.get("mode") == "overview"
    # adopt is still reachable — it is now the OPT-IN, not the default
    # (default flipped to the ratified "overview" 2026-07-26)
    monkeypatch.setenv("CABINET_SURFACE_PIN_MODE", "adopt")
    rep2 = pin.step(census=census, now=day, state={}, adapter=adapter)
    assert "mode" not in rep2 and "pinned" in rep2
    # and with NO knob at all a stranger dispatches to overview
    monkeypatch.delenv("CABINET_SURFACE_PIN_MODE")
    rep3 = pin.step(census=census, now=day, state={}, adapter=adapter)
    assert rep3.get("mode") == "overview"


def test_knob_round_trip_retires_each_designs_pin(adapter, day, monkeypatch):
    """overview → adopt → overview: each flip retires the other design's pin
    (review 2026-07-10 finding #1) — never a frozen pin, never two pins."""
    census = make_census([make_card(1), make_card(2)])
    state: dict = {}
    # overview pins the standing card
    monkeypatch.setenv("CABINET_SURFACE_PIN_MODE", "overview")
    pin.step(census=census, now=day, state=state, adapter=adapter)
    overview_mid = state["message_id"]
    assert adapter.pins == [overview_mid] and state["mode"] == "overview"
    # flip to adopt: the overview pin is retired, an item pin replaces it,
    # and the state is stamped adopt (no overview keys survive)
    monkeypatch.setenv("CABINET_SURFACE_PIN_MODE", "adopt")
    pin.step(census=census, now=day, state=state, adapter=adapter)
    assert adapter.unpins == [overview_mid]
    assert state["mode"] == "adopt" and "pinned" not in state
    assert state["item_id"] == make_card(1)["id"]
    adopt_mid = state["message_id"]
    assert adapter.pins == [overview_mid, adopt_mid]
    # flip back to overview: the adopt item pin is retired in turn
    monkeypatch.setenv("CABINET_SURFACE_PIN_MODE", "overview")
    pin.step(census=census, now=day, state=state, adapter=adapter)
    assert adapter.unpins == [overview_mid, adopt_mid]
    assert state["mode"] == "overview"
    assert adapter.pins[-1] == state["message_id"]


def test_failed_pin_retries_next_tick(adapter, day):
    """A pin the channel refuses is retried on the next tick via the
    pinned=False flag (review 2026-07-10 gap #8)."""
    state: dict = {}
    census = make_census([make_card(1)])
    real_pin = adapter.pin
    adapter.pin = lambda mid, silent=True: {"status": "error", "sent": False}
    pin.overview_step(census=census, now=day, state=state,
                      cfg=_cfg(), adapter=adapter)
    assert state["pinned"] is False and state["message_id"]
    adapter.pin = real_pin
    pin.overview_step(census=census, now=day, state=state,
                      cfg=_cfg(), adapter=adapter)
    assert state["pinned"] is True
    assert adapter.pins == [state["message_id"]]


def test_whys_that_trip_the_jargon_linter_are_dropped(tmp_path):
    p = tmp_path / "why-captain.json"
    p.write_text(json.dumps({
        "sit-ok": "only you can pay it",
        "sit-jargon": "the verdict needs your blast radius call",
    }), encoding="utf-8")
    whys = ov.load_whys(p)
    assert whys == {"sit-ok": "only you can pay it"}
