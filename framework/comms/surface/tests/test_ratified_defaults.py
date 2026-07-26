"""A STRANGER gets the Captain-ratified surface (fix 2026-07-26).

Two settings the Captain ratified — briefing-as-card (2026-07-11) and the
``overview`` pin (2026-07-10) — lived ONLY in ``instance/config/comms-surface.yml``.
The egg export deletes that file (``cabinet/scripts/egg-export-manifest.txt``
rule "delete instance/config/comms-surface.yml"), and nothing in the hatch
regenerates it, so every fresh cabinet resolved the pre-ruling foundation
defaults and got the chunked text wall plus the old item-adopting pin.

A unit test on the DEFAULTS constant alone would not have caught that: the
constant was self-consistently False/"adopt" and every test agreed with it.
What was missing is this file's question — *with no instance config present at
all, what does the surface actually DO?* Every arm below therefore drives real
render/send/pin behaviour with the instance file absent, never the constant.
"""
from __future__ import annotations

from framework.attention import plain as plainlaw
from framework.comms.surface import briefing_card, config as scfg
from framework.comms.surface import pin_lifecycle as pin

from .conftest import make_card, make_census


def _stranger(monkeypatch, tmp_path):
    """The egg's condition: no instance/config/comms-surface.yml, no env."""
    monkeypatch.setenv("CABINET_SURFACE_CONFIG_PATH",
                       str(tmp_path / "instance/config/comms-surface.yml"))
    for var in ("CABINET_BRIEFING_CARD", "CABINET_SURFACE_PIN_MODE"):
        monkeypatch.delenv(var, raising=False)
    assert not scfg._instance_file().exists()      # the egg's actual shape


def test_stranger_has_no_instance_file_yet_resolves_ratified(monkeypatch,
                                                             tmp_path):
    _stranger(monkeypatch, tmp_path)
    cfg = scfg.load()
    assert cfg["briefing_card"] is True            # ratified 2026-07-11
    assert cfg["pin_mode"] == "overview"           # ratified 2026-07-10


def test_stranger_briefing_arrives_as_one_card_not_a_text_wall(
        monkeypatch, tmp_path, day, adapter, charter):
    """The defect made concrete: with no instance config the briefing must
    still go out as ONE card carrying the Triage control."""
    _stranger(monkeypatch, tmp_path)
    census = make_census([make_card(i) for i in range(3)])
    res = briefing_card.maybe_send("Quiet day; one deploy shipped.",
                                   census=census, now=day,
                                   adapter=adapter, ch=charter)
    assert res != {"status": "disabled"}           # was disabled pre-fix
    assert res["decision"]["action"] == "send"
    assert len(adapter.sends) == 1                 # ONE message, never chunked
    body = adapter.sends[0]["body"]
    assert "3 decision(s) ready" in body
    assert "(1/" not in body                       # no "(1/2)" chunk marker
    labels = [b["text"] for row in adapter.sends[0]["buttons"] for b in row]
    assert any(t.startswith("▶ Triage now") for t in labels)


def test_stranger_gets_the_standing_overview_pin(monkeypatch, tmp_path,
                                                 day, adapter):
    """With no instance config the 5-minute pin tick must maintain the ONE
    standing "⚑ N need you" card, not adopt the top item's own card."""
    _stranger(monkeypatch, tmp_path)
    state: dict = {}
    rep = pin.step(census=make_census([make_card(1), make_card(2)]),
                   now=day, state=state, adapter=adapter)
    assert rep["mode"] == "overview"               # was "adopt" pre-fix
    assert "⚑ 2 need you" in adapter.sends[0]["body"].splitlines()[0]
    assert adapter.pins == [state["message_id"]]   # pinned exactly once


def test_stranger_pin_is_edited_in_place_never_re_pinned(monkeypatch, tmp_path,
                                                         day, adapter):
    """The ratified property that makes it a *standing* card: the count
    changes by editing the same pinned message."""
    _stranger(monkeypatch, tmp_path)
    state: dict = {}
    pin.step(census=make_census([make_card(1)]), now=day, state=state,
             adapter=adapter)
    first = state["message_id"]
    pin.step(census=make_census([make_card(1), make_card(2), make_card(3)]),
             now=day, state=state, adapter=adapter)
    assert state["message_id"] == first
    assert adapter.pins == [first]                 # pinned once, not twice
    head = adapter.edits[-1]["body"].splitlines()[0]
    assert adapter.edits and "⚑ 3 need you" in head
    assert plainlaw.lint(head) == []


def test_stranger_briefing_runner_selects_the_card_path(monkeypatch, tmp_path):
    """The frontdoor consumer that actually swaps the send path — proving the
    flip reaches the runtime entry point, not just the config dict."""
    _stranger(monkeypatch, tmp_path)
    from framework.frontdoor import run_briefing
    assert run_briefing._briefing_card_mode() is True


def test_a_deployment_can_still_opt_out_of_both(monkeypatch, tmp_path):
    """Ratified-by-default must not mean unconfigurable: the documented
    opt-outs still bind, or the flip would take a choice away."""
    p = tmp_path / "comms-surface.yml"
    p.write_text("pin_mode: adopt\nbriefing_card: false\n", encoding="utf-8")
    monkeypatch.setenv("CABINET_SURFACE_CONFIG_PATH", str(p))
    for var in ("CABINET_BRIEFING_CARD", "CABINET_SURFACE_PIN_MODE"):
        monkeypatch.delenv(var, raising=False)
    cfg = scfg.load()
    assert cfg["briefing_card"] is False and cfg["pin_mode"] == "adopt"
