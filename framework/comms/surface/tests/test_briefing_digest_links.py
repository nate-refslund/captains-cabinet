"""Briefing-as-card, FYI→digest fold, and deep-link resolution."""
from __future__ import annotations

from framework.attention import plain as plainlaw
from framework.comms.surface import briefing_card, digest, links

from .conftest import make_card, make_census


# ---------------------------------------------------------------------------
# Briefing as ONE card (§3.4)
# ---------------------------------------------------------------------------

def test_briefing_renders_one_card_with_triage_control(day):
    census = make_census([make_card(i) for i in range(4)])
    kwargs = briefing_card.render("Quiet day; one deploy shipped.",
                                  census, now=day, cfg={"dashboard_url": ""})
    assert kwargs["kind"] == "briefing"
    assert "4 decision(s) ready" in kwargs["situation"]
    labels = [b["text"] for b in kwargs["buttons"][0]]
    assert labels[0].startswith("▶ Triage now")
    datas = [b["data"] for b in kwargs["buttons"][0]]
    assert "cv2|tri|now" in datas and "cv2|tri|brief" in datas
    for text in (kwargs["subject"], kwargs["situation"], *labels):
        assert plainlaw.lint(text) == []
    assert "(1/" not in kwargs["situation"]        # never chunked


def test_briefing_card_empty_shelf_has_no_buttons(day):
    kwargs = briefing_card.render("All quiet.", make_census([]), now=day)
    assert kwargs["buttons"] is None
    assert "Nothing needs a decision" in kwargs["situation"]


def test_briefing_slot_identity_is_stable(day):
    census = make_census([make_card(1)])
    a = briefing_card.render("x", census, now=day)
    b = briefing_card.render("y (rerun)", census, now=day)
    assert a["evidence"] == b["evidence"]          # same slot = same card
    assert a["subject"] == "Morning briefing"


def test_maybe_send_is_dark_when_explicitly_opted_out(day, adapter, charter):
    # Was "dark by default" until 2026-07-26; the default is now the ratified
    # TRUE (Captain 2026-07-11), so this pins the explicit OPT-OUT instead.
    census = make_census([make_card(1)])
    res = briefing_card.maybe_send("head", census=census, now=day,
                                   cfg={"briefing_card": False},
                                   adapter=adapter, ch=charter)
    assert res == {"status": "disabled"}
    assert adapter.sends == []


def test_maybe_send_enabled_goes_through_the_gate(day, adapter, charter):
    census = make_census([make_card(i) for i in range(2)])
    cfg = {"briefing_card": True, "dashboard_url": ""}
    res = briefing_card.maybe_send("head", census=census, now=day,
                                   cfg=cfg, adapter=adapter, ch=charter)
    assert res["decision"]["action"] == "send"     # briefing class = direct
    assert len(adapter.sends) == 1
    assert adapter.sends[0]["buttons"]


# ---------------------------------------------------------------------------
# FYI → digest (§3.2)
# ---------------------------------------------------------------------------

def test_fyi_folds_into_one_intake_item(day):
    fyis = [make_card(i, kind="fyi") for i in range(5)]
    item = digest.fold_fyi(fyis, now=day)
    assert item["kind"] == "digest" and item["urgency_tier"] == "fyi"
    assert item["payload"]["count"] == 5
    assert item["payload"]["summary"].count("\n") == 5   # header + 5 lines
    assert plainlaw.lint(item["payload"]["summary"].split("\n")[0]) == []
    assert digest.fold_fyi([], now=day) is None


def test_split_fyi_partitions_the_pool():
    cards = [make_card(1), make_card(2, kind="fyi"), make_card(3)]
    decisions, fyis = digest.split_fyi(cards)
    assert [c["id"] for c in decisions] == [cards[0]["id"], cards[2]["id"]]
    assert [c["id"] for c in fyis] == [cards[1]["id"]]


def test_enqueue_uses_injected_fn_and_never_raises(day):
    seen = []
    res = digest.enqueue_fyi_digest([make_card(1, kind="fyi")],
                                    enqueue_fn=lambda item: seen.append(item)
                                    or "intake-1", now=day)
    assert res == {"id": "intake-1", "count": 1} and len(seen) == 1

    def boom(item):
        raise RuntimeError("redis down")
    res2 = digest.enqueue_fyi_digest([make_card(2, kind="fyi")],
                                     enqueue_fn=boom, now=day)
    assert res2["id"] is None and "redis down" in res2["error"]


# ---------------------------------------------------------------------------
# Deep links (fail-closed)
# ---------------------------------------------------------------------------

def test_links_fail_closed_when_unconfigured():
    cfg = {"dashboard_url": ""}
    assert links.dashboard_base(cfg) == ""
    assert links.queue_url(cfg) == ""
    assert links.queue_item_url("sit-1", cfg) == ""
    assert links.url_button("Open", "") is None
    assert links.details_line("") == ""


def test_links_encode_item_ids():
    cfg = {"dashboard_url": "https://cab.example/"}
    url = links.queue_item_url("sit a/b?c", cfg)
    assert url == "https://cab.example/queue?item=sit%20a%2Fb%3Fc"


def test_url_buttons_https_only():
    assert links.url_button("Open", "https://cab.example/queue") \
        == {"text": "Open", "url": "https://cab.example/queue"}
    assert links.url_button("Open", "http://127.0.0.1:4700/queue") is None
    assert links.dashboard_base({"dashboard_url": "ftp://nope"}) == ""
