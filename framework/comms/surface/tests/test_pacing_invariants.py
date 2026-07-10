"""Pacing invariants (ARM-B contract): never >cap active, advance-on-clear,
ask-first default honored, quiet-hours passthrough, urgent budget, ONE nudge."""
from __future__ import annotations

from datetime import timedelta

from framework.comms.surface import config as scfg
from framework.comms.surface import pacing

from .conftest import make_card, make_census

CFG = dict(scfg.DEFAULTS)
CFG.update({"cap": 5, "mode": "ask-first", "pileup": 3, "snooze_hours": 2.0,
            "urgent_interrupts": 2, "urgent_window_hours": 12.0,
            "hard_all_cap": 25})


def _ops(kind, ops):
    return [o for o in ops if o[0] == kind]


def fresh():
    return pacing.load_state()


# ---------------------------------------------------------------------------
# Ask-first default
# ---------------------------------------------------------------------------

def test_ask_first_default_never_presents_without_opt_in(day):
    census = make_census([make_card(i) for i in range(6)])
    ops, st = pacing.plan(census, fresh(), day, CFG)
    assert _ops("present", ops) == []          # nothing auto-dumped
    assert len(_ops("nudge", ops)) == 1        # exactly ONE nudge, count 6
    assert _ops("nudge", ops)[0][1] == 6
    assert st["active"] == {}


def test_config_default_mode_is_ask_first():
    assert scfg.DEFAULTS["mode"] == "ask-first"
    assert scfg.load(instance={})["mode"] == "ask-first"
    # an unknown configured mode narrows back to ask-first, never louder
    assert scfg.load(instance={"pacing": {"mode": "shout"}})["mode"] == "ask-first"


def test_below_pileup_threshold_stays_silent(day):
    census = make_census([make_card(1), make_card(2)])
    ops, st = pacing.plan(census, fresh(), day, CFG)
    assert ops == []


def test_nudge_is_one_standing_card_not_a_stream(day):
    census = make_census([make_card(i) for i in range(4)])
    ops1, st1 = pacing.plan(census, fresh(), day, CFG)
    assert len(_ops("nudge", ops1)) == 1
    # same census again → no second nudge op (same count, still open)
    ops2, st2 = pacing.plan(census, st1, day + timedelta(minutes=30), CFG)
    assert _ops("nudge", ops2) == []
    # count changed → the ONE card updates (an edit via the same identity)
    census2 = make_census([make_card(i) for i in range(5)])
    ops3, _ = pacing.plan(census2, st2, day + timedelta(hours=1), CFG)
    assert len(_ops("nudge", ops3)) == 1 and _ops("nudge", ops3)[0][1] == 5


# ---------------------------------------------------------------------------
# Cap + advance-on-clear
# ---------------------------------------------------------------------------

def test_never_more_than_cap_active(day):
    census = make_census([make_card(i) for i in range(12)])
    st = fresh()
    st["triage_open"] = True
    ops, st = pacing.plan(census, st, day, CFG)
    assert len(_ops("present", ops)) == 5
    assert len(st["active"]) == 5
    # replanning with nothing cleared presents nothing more
    ops2, st2 = pacing.plan(census, st, day + timedelta(minutes=5), CFG)
    assert _ops("present", ops2) == []
    assert len(st2["active"]) == 5


def test_advance_on_clear_refills_to_cap(day):
    cards = [make_card(i) for i in range(8)]
    census = make_census(cards)
    st = fresh()
    st["triage_open"] = True
    _, st = pacing.plan(census, st, day, CFG)
    assert len(st["active"]) == 5
    # two of the active items resolve (leave the census)
    active_ids = list(st["active"].keys())[:2]
    remaining = [c for c in cards if c["id"] not in active_ids]
    ops, st = pacing.plan(make_census(remaining), st,
                          day + timedelta(minutes=10), CFG)
    assert len(_ops("clear", ops)) == 2
    assert len(_ops("present", ops)) == 2      # the next two advance
    assert len(st["active"]) == 5              # …still holding the cap


def test_partial_clear_never_pauses_full_clear_offers_batch(day):
    cards = [make_card(i) for i in range(12)]
    st = fresh()
    st["triage_open"] = True
    _, st = pacing.plan(make_census(cards), st, day, CFG)
    # the Captain clears the WHOLE batch at once
    cleared = set(list(st["active"].keys()))
    remaining = [c for c in cards if c["id"] not in cleared]
    ops, st = pacing.plan(make_census(remaining), st,
                          day + timedelta(minutes=20), CFG)
    offers = _ops("batch_offer", ops)
    assert len(offers) == 1 and offers[0][1] == 7   # pause, don't auto-dump
    assert _ops("present", ops) == []
    assert st["batch_offered"] is True
    # "Show next" resumes the flow
    st, routing = pacing.on_control(st, "more", "", day + timedelta(minutes=21), CFG)
    assert routing["handled"]
    ops2, st = pacing.plan(make_census(remaining), st,
                           day + timedelta(minutes=22), CFG)
    assert len(_ops("present", ops2)) == 5


def test_all_clear_when_everything_done(day):
    cards = [make_card(1), make_card(2), make_card(3)]
    st = fresh()
    st["triage_open"] = True
    _, st = pacing.plan(make_census(cards), st, day, CFG)
    ops, st = pacing.plan(make_census([]), st, day + timedelta(minutes=9), CFG)
    assert len(_ops("clear", ops)) == 3
    assert len(_ops("all_clear", ops)) == 1
    assert st["triage_open"] is False and st["active"] == {}


# ---------------------------------------------------------------------------
# Captain throttle controls
# ---------------------------------------------------------------------------

def test_triage_now_opens_presentation(day):
    census = make_census([make_card(i) for i in range(6)])
    ops, st = pacing.plan(census, fresh(), day, CFG)          # nudge only
    st, routing = pacing.on_control(st, "tri", "now", day, CFG)
    assert routing["handled"]
    ops2, st = pacing.plan(census, st, day + timedelta(minutes=1), CFG)
    assert len(_ops("present", ops2)) == 5


def test_snooze_quiets_the_nudge_until_expiry(day):
    census = make_census([make_card(i) for i in range(4)])
    _, st = pacing.plan(census, fresh(), day, CFG)
    st, _ = pacing.on_control(st, "tri", "snz", day, CFG)
    ops, st = pacing.plan(census, st, day + timedelta(hours=1), CFG)
    assert ops == []                                          # snoozed
    ops2, _ = pacing.plan(census, st, day + timedelta(hours=3), CFG)
    assert len(_ops("nudge", ops2)) == 1                      # snooze expired


def test_at_next_briefing_rides_quietly(day):
    census = make_census([make_card(i) for i in range(4)])
    _, st = pacing.plan(census, fresh(), day, CFG)
    st, _ = pacing.on_control(st, "tri", "brief", day, CFG)
    ops, _ = pacing.plan(census, st, day + timedelta(hours=2), CFG)
    assert ops == []          # 14:00 — still before the 19:30 briefing


def test_give_me_all_and_top1_override_the_cap(day):
    census = make_census([make_card(i) for i in range(9)])
    st, _ = pacing.on_control(fresh(), "all", "", day, CFG)
    ops, st = pacing.plan(census, st, day, CFG)
    assert len(_ops("present", ops)) == 9
    st2, _ = pacing.on_control(fresh(), "top1", "", day, CFG)
    ops2, st2 = pacing.plan(census, st2, day, CFG)
    assert len(_ops("present", ops2)) == 1


def test_later_parks_one_card_until_next_briefing(day):
    cards = [make_card(i) for i in range(3)]
    st = fresh()
    st["triage_open"] = True
    _, st = pacing.plan(make_census(cards), st, day, CFG)
    victim = list(st["active"].keys())[0]
    h = st["active"][victim]["h"]
    st, routing = pacing.on_control(st, "later", h, day, CFG)
    assert routing.get("later") and routing["item_id"] == victim
    assert victim in st["holds"]
    # while held it never re-presents…
    ops, st = pacing.plan(make_census(cards), st, day + timedelta(hours=1), CFG)
    assert all(o[1].get("id") != victim for o in _ops("present", ops))
    # …after the briefing horizon the hold expires and it may return
    ops2, _ = pacing.plan(make_census(cards), st, day + timedelta(hours=9), CFG)
    assert any(o[1].get("id") == victim for o in _ops("present", ops2))


# ---------------------------------------------------------------------------
# Auto-push mode (the one knob, non-default)
# ---------------------------------------------------------------------------

def test_auto_push_presents_without_asking(day):
    cfg = dict(CFG, mode="auto-push")
    census = make_census([make_card(i) for i in range(7)])
    ops, st = pacing.plan(census, fresh(), day, cfg)
    assert len(_ops("present", ops)) == 5      # still capped
    assert _ops("nudge", ops) == []


# ---------------------------------------------------------------------------
# Urgent jumps — bounded per rolling window
# ---------------------------------------------------------------------------

def test_urgent_jump_budget_per_window(day):
    cards = [make_card(i, cod="blocking") for i in range(3)]
    census = make_census(cards)
    ops, st = pacing.plan(census, fresh(), day, CFG)
    assert len(_ops("urgent", ops)) == 2       # budget 2/window
    # same window: the third still waits
    ops_same, st_same = pacing.plan(census, st, day + timedelta(hours=1), CFG)
    assert _ops("urgent", ops_same) == []
    # window rolls → the third jumps
    later = day + timedelta(hours=13)
    remaining = [c for c in cards if c["id"] not in st_same["active"]]
    ops2, _ = pacing.plan(make_census(remaining), st_same, later, CFG)
    assert len(_ops("urgent", ops2)) == 1


def test_urgent_eligibility_is_structural(day):
    assert pacing.urgent_eligible(make_card(1, cod="blocking"), day)
    assert pacing.urgent_eligible(
        make_card(2, deadline="2026-07-10T14:00:00Z"), day)   # before 19:30
    assert not pacing.urgent_eligible(
        make_card(3, deadline="2026-07-12T14:00:00Z"), day)
    assert not pacing.urgent_eligible(make_card(4), day)
    # prose urgency alone can never jump (no keyword path exists)
    c = make_card(5)
    c["what"] = "URGENT!!! today asap"
    assert not pacing.urgent_eligible(c, day)


# ---------------------------------------------------------------------------
# Executor: through the real gate — quiet hours pass through
# ---------------------------------------------------------------------------

def test_quiet_hours_passthrough_no_sends_no_actives(night, adapter, charter,
                                                     briefing_intake):
    census = make_census([make_card(i) for i in range(6)])
    state = pacing.load_state()
    state["triage_open"] = True
    report = pacing.step(census=census, now=night, state=state,
                         cfg=CFG, adapter=adapter, ch=charter)
    assert adapter.sends == []                 # nothing pierced quiet hours
    assert state["active"] == {}               # deferred ≠ active
    assert len(briefing_intake) == 5           # the presented cap rode to the briefing
    assert report["active"] == 0


def test_daytime_step_sends_capped_cards_with_buttons(day, adapter, charter):
    census = make_census([make_card(i) for i in range(7)])
    state = pacing.load_state()
    state["triage_open"] = True
    pacing.step(census=census, now=day, state=state,
                cfg=CFG, adapter=adapter, ch=charter)
    assert len(adapter.sends) == 5
    assert len(state["active"]) == 5
    for s in adapter.sends:
        assert s["buttons"], "every decision card carries its control row"
        assert all(len(b.get("data", "")) <= 64 for b in s["buttons"][0])
    # message ids recorded for edit-in-place
    assert all(e.get("message_id") for e in state["active"].values())


def test_step_clear_edits_card_in_place(day, adapter, charter):
    cards = [make_card(i) for i in range(3)]
    state = pacing.load_state()
    state["triage_open"] = True
    pacing.step(census=make_census(cards), now=day, state=state,
                cfg=CFG, adapter=adapter, ch=charter)
    assert len(adapter.sends) == 3
    # first two resolve; the census shrinks
    gone = list(state["active"].keys())[:2]
    remaining = [c for c in cards if c["id"] not in gone]
    pacing.step(census=make_census(remaining), now=day + timedelta(minutes=30),
                state=state, cfg=CFG, adapter=adapter, ch=charter)
    assert len(adapter.edits) >= 2             # ✅ edit-in-place, not new sends
    assert len(state["active"]) == 1


def test_urgent_budget_burns_only_on_real_send(night, adapter, charter):
    # quiet hours + a non-piercing "blocking" card: the gate demotes it, so
    # the urgent budget is refunded (a demoted jump costs nothing).
    census = make_census([make_card(1, cod="blocking")])
    state = pacing.load_state()
    pacing.step(census=census, now=night, state=state,
                cfg=CFG, adapter=adapter, ch=charter)
    assert adapter.sends == []
    assert state["urgent_sends"] == []


def test_state_round_trip_via_files(day, adapter, charter):
    census = make_census([make_card(i) for i in range(4)])
    st, _ = pacing.on_control(pacing.load_state(), "tri", "now", day, CFG)
    pacing.save_state(st)
    pacing.step(census=census, now=day, cfg=CFG, adapter=adapter, ch=charter)
    loaded = pacing.load_state()
    assert len(loaded["active"]) == 4
    assert loaded["updated_at"]


def test_nudge_card_buttons_single_source_and_own_link_row():
    """The nudge labels come from plain.BUTTON_LABELS (one source of truth —
    'Snooze 2h' keeps its duration) and the 🔎 link rides its OWN row so no
    row exceeds three buttons on a phone."""
    from framework.attention import plain as plainlaw
    from framework.comms.surface import pacing

    bare = pacing._nudge_kwargs(("nudge", 3), {"dashboard_url": ""})
    assert [b["text"] for b in bare["buttons"][0]] \
        == plainlaw.BUTTON_LABELS["nudge"]

    linked = pacing._nudge_kwargs(
        ("nudge", 3), {"dashboard_url": "https://cabinet.example"})
    assert len(linked["buttons"]) == 2
    assert all(len(row) <= 3 for row in linked["buttons"])
    assert linked["buttons"][1][0].get("url")


def test_nudge_lifecycle_wording_holds_at_a_glance():
    """Neutral standing identity: the subject must contradict neither the
    pending face nor the all-clear face; no process vocabulary ('batch')."""
    from framework.comms.surface import pacing

    assert pacing.NUDGE_SUBJECT == "Your decisions"
    ac = pacing._nudge_kwargs(("all_clear",), {"dashboard_url": ""})
    assert ac["subject"] == pacing.NUDGE_SUBJECT
    assert "All clear" in ac["situation"]
    batch = pacing._nudge_kwargs(("batch_offer", 2), {"dashboard_url": ""})
    assert "round done" in batch["situation"]
    assert "Batch" not in batch["situation"]
    linked = pacing._nudge_kwargs(
        ("batch_offer", 2), {"dashboard_url": "https://cabinet.example"})
    assert all(len(row) <= 3 for row in linked["buttons"])
