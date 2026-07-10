"""Tiered-escalation gate (captain-surface §3.9): a NEW captain-bound decision
card needs an exhaustion proof — "the lane tried X, the Chair tried Y, this
needs the captain because Z" — or it bounces back to the org with the reason.
Dark by default; floor classes, standing edits, closures, and non-decision
kinds are exempt."""
import json
from datetime import datetime, timezone

import pytest

from framework.attention import escalation, gate
from framework.comms import tools


CH = {
    "version": 1, "_source": "test", "verbosity": "terse", "ack_style": "silent-fyi",
    "quiet_hours": {"start": "21:00", "end": "07:00", "floor_classes": ["infra-page"]},
    "classes": [
        {"id": "infra-page", "matchers": {"kinds": ["infra-page"]},
         "route": "direct-now", "silent": False, "reaction": ["🚨"]},
        {"id": "action-card", "matchers": {"kinds": ["action-card"]},
         "route": "standing-card", "silent": True, "reaction": ["👀"]},
        {"id": "default", "route": "next-briefing", "silent": True},
    ],
}

NOON = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)

PROOF = {"lane_tried": "retried the deploy twice, rotated the token",
         "chair_tried": "cross-checked the Vercel project + reran from main",
         "needs_captain_because": "the billing credential is captain-held"}


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_ATTENTION_DIR", str(tmp_path / "attention"))
    monkeypatch.setenv("CABINET_CAPTAIN_TZ", "UTC")
    monkeypatch.setenv("CABINET_BRIEFING_TIMES", "07:30,19:30")
    monkeypatch.delenv("CABINET_ESCALATION_GATE", raising=False)
    monkeypatch.delenv("CABINET_ESCALATION_KINDS", raising=False)


def _item(**kw):
    base = {"kind": "action-card", "subject": "prod deploy is blocked",
            "situation": "needs the captain's billing approval",
            "evidence": ["deploy/log-ref-1"],
            "steps": [{"title": "Approve the charge"}]}
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# check() — the admission decision
# ---------------------------------------------------------------------------

def test_dark_by_default_admits_everything():
    assert escalation.check(_item())["admitted"] is True
    assert escalation.check(_item())["reason"] == "gate-dark"


def test_armed_without_proof_bounces_with_all_missing_fields(monkeypatch):
    monkeypatch.setenv("CABINET_ESCALATION_GATE", "1")
    res = escalation.check(_item())
    assert res["admitted"] is False
    assert res["reason"] == "escalation-unexhausted"
    assert res["missing"] == list(escalation.REQUIRED_FIELDS)
    assert "needs_captain_because" in res["fix"]


def test_partial_proof_names_exactly_what_is_missing(monkeypatch):
    monkeypatch.setenv("CABINET_ESCALATION_GATE", "1")
    res = escalation.check(_item(escalation={"lane_tried": "restarted it"}))
    assert res["admitted"] is False
    assert res["missing"] == ["chair_tried", "needs_captain_because"]
    # Whitespace-only counts as missing (no rubber-stamp blanks).
    res2 = escalation.check(_item(escalation={**PROOF, "chair_tried": "  "}))
    assert res2["missing"] == ["chair_tried"]


def test_full_proof_admits(monkeypatch):
    monkeypatch.setenv("CABINET_ESCALATION_GATE", "1")
    res = escalation.check(_item(escalation=dict(PROOF)))
    assert res["admitted"] is True
    assert res["reason"] == "exhaustion-proof-present"


def test_exemptions(monkeypatch):
    monkeypatch.setenv("CABINET_ESCALATION_GATE", "1")
    # Floor class — a safety page is never blocked by paperwork.
    assert escalation.check(_item(kind="infra-page"),
                            resolved={"floor": True})["reason"] == "floor-exempt"
    # Non-decision kind.
    assert escalation.check(_item(kind="fyi-note"))["reason"] == "not-a-decision-card"
    # Closure / acted report (telling, not asking).
    assert escalation.check(_item(state="done"))["reason"] == "not-a-new-decision"


# ---------------------------------------------------------------------------
# gate.decide / gate.deliver — wired where cards enter the gateway
# ---------------------------------------------------------------------------

def test_gate_dark_default_routes_unchanged():
    d = gate.decide(_item(), ch=CH, now=NOON, standing={})
    assert d["action"] == "send"


def test_gate_armed_bounces_an_unproofed_decision_card(monkeypatch):
    monkeypatch.setenv("CABINET_ESCALATION_GATE", "1")
    d = gate.decide(_item(), ch=CH, now=NOON, standing={})
    assert d["action"] == "bounce"
    assert d["reason"] == "escalation-unexhausted"
    assert d["bounce"]["missing"] == list(escalation.REQUIRED_FIELDS)


def test_gate_armed_admits_a_proofed_card_and_floor_pages(monkeypatch):
    monkeypatch.setenv("CABINET_ESCALATION_GATE", "1")
    d = gate.decide(_item(escalation=dict(PROOF)), ch=CH, now=NOON, standing={})
    assert d["action"] == "send"
    p = gate.decide(_item(kind="infra-page", subject="db is down"),
                    ch=CH, now=NOON, standing={})
    assert p["action"] == "send"     # floor-exempt, never bounced


def test_gate_armed_standing_edit_is_exempt(monkeypatch):
    """An update to an already-admitted situation edits in place — the
    identity path returns before the escalation check."""
    monkeypatch.setenv("CABINET_ESCALATION_GATE", "1")
    it = _item()
    standing = {}
    # Admit while dark (simulates a card admitted before arming).
    monkeypatch.delenv("CABINET_ESCALATION_GATE", raising=False)
    d1 = gate.decide(it, ch=CH, now=NOON, standing=standing)
    gate.deliver(d1, send_fn=lambda t, **k: {"sent": True, "message_ids": [7]},
                 edit_fn=lambda m, t, **k: {"sent": True}, standing=standing)
    monkeypatch.setenv("CABINET_ESCALATION_GATE", "1")
    it2 = _item(state="acted", steps=[{"title": "Approve the charge"},
                                      {"title": "Done"}])
    d2 = gate.decide(it2, ch=CH, now=NOON, standing=standing)
    assert d2["action"] == "edit" and d2["message_id"] == 7


def test_deliver_bounce_journals_and_returns_the_fix(monkeypatch):
    monkeypatch.setenv("CABINET_ESCALATION_GATE", "1")
    it = _item(lane="polads")
    d = gate.decide(it, ch=CH, now=NOON, standing={})
    sent = []
    res = gate.deliver(d, send_fn=lambda t, **k: sent.append(t) or {"sent": True},
                       edit_fn=lambda m, t, **k: {"sent": True},
                       standing={}, item=it)
    assert res["status"] == "bounced" and res["sent"] is False
    assert res["missing"] == list(escalation.REQUIRED_FIELDS)
    assert "escalation=" in res["fix"]
    assert sent == []                          # nothing reached the channel
    rows = escalation.bounce_rows()
    assert len(rows) == 1
    assert rows[0]["subject"] == "prod deploy is blocked"
    assert rows[0]["lane"] == "polads"
    assert rows[0]["missing"] == list(escalation.REQUIRED_FIELDS)


# ---------------------------------------------------------------------------
# tools.send_card — the officer-facing entry inherits the gate
# ---------------------------------------------------------------------------

class _Adapter:
    def __init__(self):
        self.sent, self.edited = [], []

    def send(self, text, **kw):
        self.sent.append(text)
        return {"sent": True, "message_ids": [11]}

    def edit(self, mid, text, **kw):
        self.edited.append((mid, text))
        return {"sent": True, "message_ids": [mid]}

    def capabilities(self):
        return {}


def test_send_card_bounces_back_to_the_officer_when_armed(monkeypatch):
    monkeypatch.setenv("CABINET_ESCALATION_GATE", "1")
    a = _Adapter()
    out = tools.send_card(subject="prod deploy is blocked",
                          situation="needs captain billing approval",
                          evidence=["deploy/log-ref-2"], adapter=a,
                          ch=CH, now=NOON)
    assert out["decision"]["action"] == "bounce"
    assert out["result"]["status"] == "bounced"
    assert a.sent == []


def test_send_card_with_proof_reaches_the_channel(monkeypatch):
    monkeypatch.setenv("CABINET_ESCALATION_GATE", "1")
    a = _Adapter()
    out = tools.send_card(subject="prod deploy is blocked",
                          situation="needs captain billing approval",
                          evidence=["deploy/log-ref-3"],
                          escalation=dict(PROOF), adapter=a, ch=CH, now=NOON)
    assert out["decision"]["action"] == "send"
    assert len(a.sent) == 1
