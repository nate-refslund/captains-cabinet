"""THE CHAT DOOR of the tap: the typed verb `ratify <id>`.

The gate is structural rather than a branch: the verb is routed only from the
Captain-verified path, so an unverified sender never reaches the writer at all.
That is asserted from BOTH sides here — the verified reply ratifies, and the
unverified one leaves the files untouched and the ledger empty.

The other two arms are the ones a "does it work" test would miss: a door that
cannot name a principal must refuse rather than record an anonymous
ratification, and every non-matching reply must route byte-identically to what
it did before this verb existed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from framework.events import emitter
from framework.frontdoor import binder_wire
from framework.onboarding import genesis

OUTCOMES_REL = "instance/config/outcomes.yml"

ANSWERS = {"version": 1, "cabinet": {"id": "acme-hq"}}


@pytest.fixture
def hatched(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_ROOT", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    genesis.merge_proposals(
        [{"id": "acme-001", "name": "Card acme-001", "lane": None,
          "what": "ship it", "why": "asked", "proof_expected": "a receipt",
          "proposed_by": "onboarding-genesis"}],
        tmp_path, answers=ANSWERS, now="2026-09-01T00:00:00Z")
    return tmp_path


def _events():
    return emitter.replay(event_types=["captain_outcome_ratified"])


def _call(text, *, verified=True, principal="captain-id-1", said=None):
    return binder_wire.handle_captain_update(
        text, "", captain_verified=verified, principal=principal,
        pending_source=lambda: [], redis_get=lambda _k: "",
        present=(said.append if said is not None else (lambda _m: None)),
        log=lambda _m: None)


def test_verified_ratify_verb_ratifies(hatched):
    said = []
    res = _call("ratify acme-001", said=said)
    assert res["handled"] is True and res["ratify"] == "ratified"
    assert res["outcome_id"] == "acme-001"
    rows = yaml.safe_load((hatched / OUTCOMES_REL).read_text(encoding="utf-8"))
    row = rows["outcomes"][0]
    assert row["id"] == "acme-001" and row["status"] == "active"
    assert row["ratified_via"] == "chat" and row["ratified_by"] == "captain"
    events = _events()
    assert len(events) == 1
    assert events[0]["payload"]["principal"] == "captain-id-1"
    assert any("Taking on" in m for m in said), said


def test_unverified_sender_writes_nothing(hatched):
    said = []
    res = _call("ratify acme-001", verified=False, said=said)
    assert res["handled"] is False, res
    assert not (hatched / OUTCOMES_REL).exists()
    assert _events() == []
    assert said == [], "an unverified sender is relayed, never answered as a tap"
    proposals = yaml.safe_load(
        (hatched / genesis.PROPOSALS_REL).read_text(encoding="utf-8"))
    assert proposals["outcomes"][0]["status"] == "draft"


def test_a_door_that_cannot_name_a_principal_refuses(hatched):
    said = []
    res = _call("ratify acme-001", principal=None, said=said)
    assert res["handled"] is True and res["ratify"] == "refused"
    assert not (hatched / OUTCOMES_REL).exists()
    assert _events() == []
    assert any("could not name who you are" in m for m in said), said


def test_unknown_id_is_reported_and_writes_nothing(hatched):
    said = []
    res = _call("ratify nope-999", said=said)
    assert res["ratify"] == "not_found"
    assert not (hatched / OUTCOMES_REL).exists()
    assert _events() == []
    assert any("No proposed card" in m for m in said), said


def test_a_second_verb_is_idempotent(hatched):
    _call("ratify acme-001")
    said = []
    res = _call("ratify acme-001", said=said)
    assert res["ratify"] == "already_ratified"
    assert len(_events()) == 1
    assert any("already ratified" in m for m in said), said


@pytest.mark.parametrize("text", [
    "ratify",
    "please ratify acme-001 when you can",
    "I will ratify acme-001",
    "ratify acme-001 acme-002",
    "approve",
    "",
])
def test_non_matching_replies_route_byte_identically(text, hatched):
    """The verb is anchored at both ends: a sentence that merely contains the
    word must not bind a card the Captain never named."""
    res = _call(text)
    assert "ratify" not in res, res
    assert not (hatched / OUTCOMES_REL).exists()
    assert _events() == []


def test_the_verb_pattern_itself(hatched):
    assert binder_wire._RATIFY_RE.match("ratify acme-001")
    assert binder_wire._RATIFY_RE.match("  RATIFY  acme-001  ")
    assert binder_wire._RATIFY_RE.match("ratify acme/001") is None
    assert binder_wire._RATIFY_RE.match("ratify a" * 40) is None
