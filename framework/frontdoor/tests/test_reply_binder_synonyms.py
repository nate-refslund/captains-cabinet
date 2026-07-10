"""§3.6 plain-verb synonyms: typed replies ride the same paths as buttons.

Verdict leg: a bare typed "no" is normalized onto the org's skip grammar
before routing (yes/ok already parse as approve). Throttle leg: typed
"pause"/"later"/"all of them"/"top 1" re-pace the surface via
pacing.on_control — never the ledger. Everything else passes through
byte-identical (Telegram text is untrusted; exact whole-reply matches only).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from framework.acting import loop
from framework.comms.surface import pacing
from framework.frontdoor import reply_binder as rb

NOW = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_ATTENTION_DIR", str(tmp_path / "attention"))
    monkeypatch.setenv("CABINET_CAPTAIN_TZ", "UTC")
    monkeypatch.setenv("CABINET_BRIEFING_TIMES", "07:30,19:30")


def test_bare_no_rides_the_skip_grammar():
    for t in ("no", "No", "no.", "nope", "nej", " NO! "):
        norm = rb.normalize_plain_reply(t)
        assert norm.startswith("skip:"), t
        assert loop.route_captain_response(norm).primary == "skip"


def test_non_bare_text_passes_through_byte_identical():
    for t in ("no, wait until Monday", "yes", "ok send it",
              "skip: not this week", "notify the team", ""):
        assert rb.normalize_plain_reply(t) == t
    # free text never widens: a sentence CONTAINING a throttle word is not one
    assert rb.throttle_of("pause the deploy until Bob confirms") is None


def test_typed_throttles_route_to_pacing_not_the_ledger():
    st = pacing.load_state()
    out = rb.route_plain_reply("all of them", now=NOW, state=st,
                               save=lambda s: st.update(s))
    assert out["handled"] and out["throttle"] == "all"
    assert st["cap_override"] is not None and st["triage_open"]

    out = rb.route_plain_reply("top 1", now=NOW, state=st,
                               save=lambda s: st.update(s))
    assert out["throttle"] == "top1" and st["cap_override"] == 1

    out = rb.route_plain_reply("pause", now=NOW, state=st,
                               save=lambda s: st.update(s))
    assert out["throttle"] == "tri" and st["snooze_until"]

    out = rb.route_plain_reply("later", now=NOW, state=st,
                               save=lambda s: st.update(s))
    assert out["throttle"] == "tri" and st["ride_briefing_until"]


def test_non_throttle_returns_none_for_the_bind_path():
    assert rb.route_plain_reply("approve", now=NOW, state={}) is None
    assert rb.route_plain_reply("what is pending?", now=NOW, state={}) is None


def test_bind_normalizes_a_bare_no_into_a_recorded_skip():
    prop = loop.proposal_event(actor={"kind": "officer", "id": "cos"},
                               lane="send-1to1-reply",
                               subject="reply to Dana re DPA",
                               ts="2026-07-10T10:00:00Z",
                               action="draft-reply")
    emitted = []
    res = rb.bind(
        "no",
        [{"correlation_id": loop.proposal_id(prop), "id": "1-1"}],
        emit=lambda **kw: emitted.append(kw),
        pending_source=lambda: [prop],
        ack=lambda ids: None,
    )
    assert res["routed"].primary == "skip"
    assert res["status"] in ("decided", "expired")
    assert emitted, "the skip must land on the ledger"
