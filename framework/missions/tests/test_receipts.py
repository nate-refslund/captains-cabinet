"""WORK RECEIPTS — the read model over the ledger.

Arms cover the shape (pure, no ledger), the read (through the real emitter on
a sandboxed ledger), and the degenerate ends: an empty ledger, a row of a kind
this surface does not carry, and a row whose payload is missing every field.

The vocabulary arm is the one that matters most: the kind table is DECLARED,
so a phase-1 event type that never reaches this surface is a receipt nobody
will ever see, and the assertion is against the contract's list rather than
against the table restating itself.
"""

from __future__ import annotations

import json

import pytest

from framework.events import emitter
from framework.missions import receipts as receipts_mod
from framework.missions.receipts import KIND_BY_EVENT, KINDS, receipts, shape


@pytest.fixture(autouse=True)
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path / "events"


def test_kind_vocabulary_is_the_contracts():
    assert set(KINDS) == set(KIND_BY_EVENT.values())
    # The phase-1 vocabulary, written out rather than derived from the table
    # under test — a table that grades itself grades nothing.
    assert set(KINDS) == {
        "ratified", "started", "renewed", "released", "completed", "failed",
        "verified", "gap", "update_applied", "update_refused",
        "update_rolled_back",
    }


def test_shape_is_none_for_a_kind_this_surface_does_not_carry():
    assert shape({"event_type": "role_created", "payload": {}}) is None
    assert shape({}) is None
    assert shape(None) is None


def test_shape_of_a_payloadless_row_is_all_absent_never_invented():
    row = shape({"event_type": "work_item_started", "actor": "coordinator",
                 "created_at": "2026-09-01T00:00:00Z", "id": "e1"})
    assert row is not None
    assert row["kind"] == "started" and row["actor"] == "coordinator"
    for field in ("outcome_id", "task_id", "claim_id", "holder", "door",
                  "evidence_path", "name"):
        assert row[field] is None, field


def test_a_gap_row_carries_its_own_id_as_the_reference():
    row = shape({"event_type": "capability_gap_recorded", "actor": "coordinator",
                 "payload": {"gap_id": "gap-0000abcd"}})
    assert row["kind"] == "gap" and row["task_id"] == "gap-0000abcd"


def test_empty_ledger_is_an_honest_empty():
    assert receipts() == []


def test_receipts_reads_the_real_ledger_in_order():
    emitter.emit("captain_outcome_ratified", actor="captain", payload={
        "outcome_id": "acme-001", "proposal_id": "acme-001", "door": "web",
        "principal": "session-1", "name": "Ship the storefront"})
    emitter.emit("work_item_started", actor="coordinator", payload={
        "outcome_id": "acme-001", "task_id": "acme-001-task-001",
        "holder": "coordinator", "claim_id": "c-1"})
    emitter.emit("role_created", actor="captain", payload={"slug": "x"})
    emitter.emit("work_item_completed", actor="coordinator", payload={
        "outcome_id": "acme-001", "task_id": "acme-001-task-001",
        "evidence_path": "shared/interfaces/proof.md"})

    rows = receipts()
    assert [r["kind"] for r in rows] == ["ratified", "started", "completed"], (
        "role_created is not on this surface and must not appear")
    assert rows[0]["door"] == "web" and rows[0]["actor"] == "captain"
    # A1.7 — the name a home-card line renders rides on the receipt.
    assert rows[0]["name"] == "Ship the storefront"
    assert rows[1]["holder"] == "coordinator" and rows[1]["claim_id"] == "c-1"
    assert rows[2]["evidence_path"] == "shared/interfaces/proof.md"


def test_cli_json(capsys):
    emitter.emit("captain_outcome_ratified", actor="captain",
                 payload={"outcome_id": "acme-001", "proposal_id": "acme-001"})
    assert receipts_mod.main(["--json"]) == 0
    rows = json.loads(capsys.readouterr().out.strip())
    assert len(rows) == 1 and rows[0]["kind"] == "ratified"


def test_cli_plain_says_empty_rather_than_printing_nothing(capsys):
    assert receipts_mod.main([]) == 0
    assert "honestly empty" in capsys.readouterr().out
