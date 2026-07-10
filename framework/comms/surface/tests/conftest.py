"""Hermetic fixtures for the TG-engine suite.

Every test runs against a tmp CABINET_ATTENTION_DIR (durable state + the
gate's standing-card map land there, never in the live estate), a UTC captain
clock, the REAL framework charter (so the triage-nudge / action-card classes
and quiet hours are the production rules), a fake ChannelAdapter (records
sends/edits/pins — no transport), and a recorded briefing intake (no Redis).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture(autouse=True)
def _surface_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_ATTENTION_DIR", str(tmp_path / "attention"))
    monkeypatch.setenv("CABINET_CAPTAIN_TZ", "UTC")
    monkeypatch.setenv("CABINET_BRIEFING_TIMES", "07:30,19:30")
    for var in ("CABINET_SURFACE_CAP", "CABINET_SURFACE_MODE",
                "CABINET_SURFACE_PILEUP", "CABINET_SURFACE_SNOOZE_H",
                "CABINET_SURFACE_URGENT_N", "CABINET_SURFACE_URGENT_WINDOW_H",
                "CABINET_SURFACE_ALL_CAP", "CABINET_DASHBOARD_URL",
                "CABINET_BRIEFING_CARD", "CABINET_ESCALATION_GATE"):
        monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture(autouse=True)
def briefing_intake(monkeypatch):
    """The gate's briefing route enqueues into the front-door intake — record
    it instead (no Redis in unit tests)."""
    rows: list = []
    from framework.attention import gate

    def _record(item, decision):
        rows.append({"item": item, "decision": decision})

    monkeypatch.setattr(gate, "_default_briefing", _record)
    return rows


class FakeAdapter:
    """A ChannelAdapter double that records everything and supports the full
    capability surface (message ids increment from 1000)."""

    name = "fake"

    def __init__(self):
        self.sends: list = []
        self.edits: list = []
        self.pins: list = []
        self.unpins: list = []
        self._next_id = 1000

    def capabilities(self):
        return {c: True for c in ("send", "edit", "react", "poll", "set_status",
                                  "pin", "thread", "answer_tap", "draft", "rich")}

    def send(self, body, *, silent=False, reply_to=None, thread_id=None,
             effect_id=None, buttons=None, markdown=False, feed_meta=None):
        self._next_id += 1
        self.sends.append({"body": body, "silent": silent, "buttons": buttons,
                           "feed_meta": feed_meta, "message_id": self._next_id})
        return {"status": "ok", "sent": True, "message_ids": [self._next_id]}

    def edit(self, message_id, body, *, buttons=None, markdown=False,
             feed_meta=None):
        self.edits.append({"message_id": message_id, "body": body,
                           "buttons": buttons, "feed_meta": feed_meta})
        return {"status": "ok", "sent": True, "message_ids": [message_id]}

    def react(self, message_id, emoji):
        return {"status": "ok", "sent": True}

    def poll(self, question, options, *, multi=False, silent=False,
             feed_meta=None):
        self._next_id += 1
        return {"status": "ok", "sent": True, "message_ids": [self._next_id]}

    def set_status(self, kind="typing"):
        return {"status": "ok", "sent": False}

    def send_draft(self, draft_id, text="", *, thread_id=None):
        return {"status": "ok", "sent": False}

    def send_rich(self, markdown=None, *, html=None, silent=False,
                  buttons=None, feed_meta=None):
        self._next_id += 1
        return {"status": "ok", "sent": True, "message_ids": [self._next_id]}

    def pin(self, message_id, *, silent=True):
        self.pins.append(message_id)
        return {"status": "ok", "sent": False, "pinned": message_id}

    def unpin(self, message_id=None):
        self.unpins.append(message_id)
        return {"status": "ok", "sent": False}

    def open_thread(self, name):
        return {"status": "ok", "thread_id": 7}

    def answer_tap(self, tap_id, toast=""):
        return {"status": "ok"}

    def download_inbound(self, ref):
        return {"status": "unsupported", "sent": False}


@pytest.fixture
def adapter():
    return FakeAdapter()


@pytest.fixture
def charter():
    """The real framework-default charter (validated), so tests exercise the
    production classes: triage-nudge (direct), action-card (standing),
    briefing (direct), quiet hours 21:00–07:00."""
    from framework.attention import charter as charter_mod
    return charter_mod.load_default()


DAY = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)      # midday UTC
NIGHT = datetime(2026, 7, 10, 23, 30, tzinfo=timezone.utc)   # quiet hours


@pytest.fixture
def day():
    return DAY


@pytest.fixture
def night():
    return NIGHT


def make_card(i: int, *, kind: str = "action-proposal", state: str = "open",
              cod: str = "medium", deadline: "str | None" = None,
              pid: "str | None" = None, standing: "int | None" = None,
              lane: "str | None" = "polads", worst: "str | None" = None,
              blast_class: str = "low",
              escalation: "dict | None" = None) -> dict:
    """A RAW census decision-card in the build_queue shape."""
    return {
        "id": f"sit-{i:016x}", "pid": pid, "revision": 1,
        "kind": kind, "state": state,
        "what": f"Decide thing number {i}",
        "why_now": {"cost_of_delay": cod, "decay": f"waiting {i}h; 0 demotions",
                    "deadline_iso": deadline},
        "evidence": [], "options": [], "recommended": {},
        "one_tap": {"approve": {"semantics": "direct"}},
        "expiry": {"stage": "full"},
        "blast_radius": {"class": blast_class, "reach": "internal",
                         "worst_case": worst or
                         "a reversible internal artifact needs undoing"},
        "charter_class": None, "urgency": "batch",
        "standing_message_id": standing,
        "created_ts": "2026-07-10T08:00:00Z", "last_surfaced_ts": None,
        "filed_by": "officer:test", "harm_class": "none", "harm_at": deadline,
        "blocked_leverage": 0, "steps": None, "injection_suspect": False,
        "lane": lane, "aliases": [f"sit-{i:016x}"],
        **({"escalation": escalation} if escalation else {}),
    }


def make_census(cards: list, *, cap: int = 7) -> dict:
    decisions = [c for c in cards if str(c.get("state", "open")) in
                 ("open", "pending")]
    return {
        "generated_at": "2026-07-10T12:00:00Z",
        "decisions": decisions,
        "directions": [], "overflow": 0, "overflow_cards": [],
        "org_routed": [], "parked": [],
        "pending_captain_items": len(decisions),
        "pending_total": len(decisions),
        "by_class": {}, "cap": cap, "admission_enforced": False,
    }
