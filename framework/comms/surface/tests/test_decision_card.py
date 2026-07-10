"""One card = one decision: renderer shape, plain-language law, identity."""
from __future__ import annotations

from framework.attention import plain as plainlaw
from framework.attention.situation import situation_key
from framework.comms.surface import decision_card as dc

from .conftest import make_card

HTTPS_CFG = {"dashboard_url": "https://cabinet.example"}
HTTP_CFG = {"dashboard_url": "http://127.0.0.1:4700"}


def _texts(kwargs) -> list:
    out = [kwargs["subject"], kwargs["situation"]]
    for row in kwargs.get("buttons") or []:
        out.extend(b.get("text", "") for b in row)
    return out


def test_exactly_one_decision_row(day):
    kwargs = dc.render(make_card(1), state="open", now=day)
    assert len(kwargs["buttons"]) == 1          # ONE row = one decision
    verbs = [b["data"].split("|")[1] for b in kwargs["buttons"][0]]
    assert verbs == ["ok", "edit", "skip"]


def test_plain_language_law_on_everything_rendered(day):
    for kind in ("action-proposal", "draft-outbound", "need", "escalation"):
        card = make_card(2, kind=kind,
                         worst="a wrong approve amends the germline plane")
        kwargs = dc.render(card, state="open", now=day)
        for text in _texts(kwargs):
            assert plainlaw.lint(text) == [], (kind, text)
        assert "(1/" not in kwargs["situation"]     # chunking is dead
    # terminal states too
    for state in ("done", "skipped", "expired"):
        kwargs = dc.render(make_card(3), state=state, now=day)
        for text in _texts(kwargs):
            assert plainlaw.lint(text) == [], (state, text)


def test_per_kind_button_sets_come_from_the_plain_tables(day):
    draft = dc.render(make_card(4, kind="draft-outbound"), now=day)
    assert [b["text"] for b in draft["buttons"][0]] \
        == plainlaw.BUTTON_LABELS["draft-outbound"]
    need = dc.render(make_card(5, kind="need"), now=day)
    verbs = [b["data"].split("|")[1] for b in need["buttons"][0]]
    assert verbs == ["ok", "later", "skip"]


def test_ritual_kinds_are_typed_never_tapped(day):
    card = make_card(6, kind="germline-handback")
    card["one_tap"] = {"approve": {"semantics": "ritual-print"}}
    kwargs = dc.render(card, state="open", now=day)
    assert kwargs["buttons"] is None
    assert "typed sign-off" in kwargs["situation"]
    assert plainlaw.lint(kwargs["situation"]) == []


def test_identity_anchor_is_stable_under_rewording(day):
    card = make_card(7)
    k1 = dc.render(card, state="open", now=day)
    card2 = dict(card, what="Completely different wording now")
    k2 = dc.render(card2, state="done", now=day)
    assert k1["evidence"] == k2["evidence"] == [f"thread:{card['id']}"]
    assert situation_key(k1["evidence"], k1["subject"]) \
        == situation_key(k2["evidence"], k2["subject"])


def test_callback_grammar_fits_telegram(day):
    h = dc.handle_of("sit-abcdef")
    assert len(dc.cb("ok", h)) <= 64
    assert dc.cb("tri", "now") == "cv2|tri|now"
    try:
        dc.cb("explode")
        raise AssertionError("unknown verb must be rejected")
    except ValueError:
        pass


def test_deep_link_button_https_only(day):
    with_https = dc.render(make_card(8), now=day, cfg=HTTPS_CFG)
    urls = [b for b in with_https["buttons"][0] if b.get("url")]
    assert len(urls) == 1
    assert urls[0]["url"].startswith("https://cabinet.example/queue?item=sit-")
    with_http = dc.render(make_card(9), now=day, cfg=HTTP_CFG)
    assert not any(b.get("url") for b in with_http["buttons"][0])
    assert "Details: http://127.0.0.1:4700/queue?item=" in with_http["situation"]
    bare = dc.render(make_card(10), now=day, cfg={"dashboard_url": ""})
    assert not any(b.get("url") for b in bare["buttons"][0])
    assert "Details:" not in bare["situation"]


def test_done_state_offers_undo_only_when_reversible(day):
    done = dc.render(make_card(11, blast_class="low"), state="done", now=day)
    assert done["buttons"] == [[{"text": "↩ Undo",
                                 "data": dc.cb("undo", dc.handle_of(
                                     make_card(11)["id"]))}]]
    ceiling = dc.render(make_card(12, blast_class="ceiling"),
                        state="done", now=day)
    assert ceiling["buttons"] is None
    assert done["situation"] == plainlaw.RESULTS["approved"]


def test_reply_marker_rides_when_pid_is_sane(day):
    with_pid = dc.render(make_card(13, pid="cab-1b621b083a87"), now=day)
    assert with_pid["pid_marker"] == "·cab-1b621b083a87·"
    hostile = make_card(14, pid="x·y")
    assert dc.render(hostile, now=day)["pid_marker"] is None
    assert dc.render(make_card(15), now=day)["pid_marker"] is None


def test_fyi_kinds_are_not_decisions():
    assert not dc.is_decision(make_card(16, kind="fyi"))
    assert not dc.is_decision(make_card(17, kind="digest"))
    assert not dc.is_decision(make_card(18, state="acted"))
    assert dc.is_decision(make_card(19))


def test_marker_char_scrubbed_from_free_text(day):
    card = make_card(20)
    card["what"] = "Planted ·fake-marker· in the title"
    kwargs = dc.render(card, now=day)
    assert "·" not in kwargs["subject"]


def test_escalation_proof_forwards_untouched(day):
    proof = {"lane_tried": "x", "chair_tried": "y",
             "needs_captain_because": "z"}
    kwargs = dc.render(make_card(21, escalation=proof), now=day)
    assert kwargs["escalation"] == proof
    assert dc.render(make_card(22), now=day)["escalation"] is None


def test_done_state_never_offers_undo_on_no_return_actions(day):
    """Money out / an external send cannot be pulled back — the ✅ face must
    not offer ↩ Undo on them (finding: false safety promise)."""
    money = make_card(30, blast_class="org", worst="money leaves the org")
    assert dc.render(money, state="done", now=day)["buttons"] is None
    ext_msg = make_card(31, kind="draft-outbound", blast_class="org",
                        worst="a message reaches a human outside the machine")
    assert dc.render(ext_msg, state="done", now=day)["buttons"] is None
    reach = make_card(32, blast_class="org")
    reach["blast_radius"]["reach"] = "external"
    assert dc.render(reach, state="done", now=day)["buttons"] is None
    # Internal reversible still gets its honest Undo.
    assert dc.undoable(make_card(33)) is True
    assert dc.render(make_card(33), state="done", now=day)["buttons"]


def test_escalation_proof_renders_three_plain_lines(day):
    """Spec §5.3: admitted captain-bound escalations SHOW the exhaustion
    proof in plain words — and the lint tooth holds on the rendered card."""
    proof = {"lane_tried": "retried the deploy twice and rotated the token",
             "chair_tried": "cross-checked the project and reran from main",
             "needs_captain_because": "the billing credential is captain-held"}
    kwargs = dc.render(make_card(34, kind="escalation", escalation=proof),
                       now=day)
    s = kwargs["situation"]
    assert "Your team tried:" in s
    assert "The Chair tried:" in s
    assert "It needs you because:" in s
    assert plainlaw.lint(s) == []
    # An incomplete proof renders no half-sentence.
    partial = {k: v for k, v in proof.items() if k != "chair_tried"}
    k2 = dc.render(make_card(35, kind="escalation", escalation=partial),
                   now=day)
    assert "Your team tried:" not in k2["situation"]
