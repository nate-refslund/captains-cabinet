"""Pin lifecycle (§5): one pin, auto-advance on engagement, conservative
replace, horizon fold, closed clears."""
from __future__ import annotations

from datetime import timedelta

from framework.comms.surface import pin_lifecycle as pin

from .conftest import make_card, make_census


def fresh():
    return pin.load_state()


def test_sets_the_top_item_as_pin(day):
    census = make_census([make_card(1), make_card(2)])
    ops, st = pin.sync(census, fresh(), day)
    assert [o[0] for o in ops] == ["pin"]
    assert st["item_id"] == make_card(1)["id"]


def test_engagement_unpins_and_advances(day):
    cards = [make_card(1), make_card(2)]
    census = make_census(cards)
    _, st = pin.sync(census, fresh(), day)
    st["message_id"] = 555
    ops, st2 = pin.sync(census, st, day + timedelta(minutes=5),
                        engaged={cards[0]["id"]})
    assert ops[0] == ("unpin", 555, "engaged")
    assert ops[1][0] == "pin" and ops[1][1]["id"] == cards[1]["id"]
    assert st2["item_id"] == cards[1]["id"]


def test_closed_situation_clears_the_pin(day):
    cards = [make_card(1), make_card(2)]
    _, st = pin.sync(make_census(cards), fresh(), day)
    st["message_id"] = 556
    ops, st2 = pin.sync(make_census([cards[1]]), st, day + timedelta(hours=1))
    assert ops[0] == ("unpin", 556, "closed")
    assert st2["item_id"] == cards[1]["id"]


def test_horizon_passed_folds_to_briefing(day):
    card = make_card(1, deadline="2026-07-10T13:00:00Z")
    _, st = pin.sync(make_census([card]), fresh(), day)
    st["message_id"] = 557
    ops, st2 = pin.sync(make_census([card]), st, day + timedelta(hours=2))
    assert ("unpin", 557, "expired") in ops
    # the expired item is NOT re-pinned (the briefing owns it now)
    assert st2["item_id"] is None


def test_replace_only_on_strict_urgency_upgrade(day):
    medium = make_card(1)
    other = make_card(2)
    _, st = pin.sync(make_census([medium, other]), fresh(), day)
    st["message_id"] = 558
    # rank jitter (same severity) never thrashes the pin
    ops, st2 = pin.sync(make_census([other, medium]), st,
                        day + timedelta(minutes=10))
    assert ops == [] and st2["item_id"] == medium["id"]
    # a genuinely more urgent newcomer replaces in place
    urgent = make_card(3, cod="blocking")
    ops2, st3 = pin.sync(make_census([urgent, medium, other]), st2,
                         day + timedelta(minutes=20))
    assert ops2[0] == ("unpin", 558, "replaced")
    assert ops2[1][1]["id"] == urgent["id"]
    assert st3["item_id"] == urgent["id"]


def test_step_adopts_standing_card_when_available(day, adapter, charter):
    card = make_card(1, standing=4242)
    report = pin.step(census=make_census([card]), now=day,
                      state=pin.load_state(), adapter=adapter, ch=charter)
    assert adapter.pins == [4242]
    assert adapter.sends == []                 # adopted, not duplicated
    assert report["pinned"] == card["id"]


def test_step_mints_and_pins_when_no_standing_card(day, adapter, charter):
    card = make_card(2)
    state = pin.load_state()
    pin.step(census=make_census([card]), now=day, state=state,
             adapter=adapter, ch=charter)
    assert len(adapter.sends) == 1
    assert adapter.pins == [adapter.sends[0]["message_id"]]
    assert state["own_card"] is True


def test_step_quiet_hours_defers_instead_of_pinning(night, adapter, charter,
                                                    briefing_intake):
    card = make_card(3)
    state = pin.load_state()
    report = pin.step(census=make_census([card]), now=night, state=state,
                      adapter=adapter, ch=charter)
    assert adapter.pins == [] and adapter.sends == []
    assert report["pinned"] is None
    assert len(briefing_intake) == 1           # rode to the briefing instead


def test_engaged_step_unpins_via_adapter(day, adapter, charter):
    cards = [make_card(1, standing=91), make_card(2, standing=92)]
    state = pin.load_state()
    pin.step(census=make_census(cards), now=day, state=state,
             adapter=adapter, ch=charter)
    assert adapter.pins == [91]
    pin.step(census=make_census(cards), now=day + timedelta(minutes=5),
             state=state, engaged={cards[0]["id"]}, adapter=adapter, ch=charter)
    assert adapter.unpins == [91]
    assert adapter.pins == [91, 92]            # advanced to the next item
    assert state["item_id"] == cards[1]["id"]


def test_state_round_trip(day, adapter, charter):
    card = make_card(9, standing=77)
    pin.step(census=make_census([card]), now=day, adapter=adapter, ch=charter)
    loaded = pin.load_state()
    assert loaded["item_id"] == card["id"]
    assert loaded["message_id"] == 77
