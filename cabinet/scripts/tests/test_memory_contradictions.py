"""§4.2 belief invalidation — propose-only contradiction pass.

Fixture-driven (rows injected; no psql, no Neon). Pins: near-duplicate and
contradiction-cue detection with the newer row superseding, cross-bucket
isolation, propose-NEVER-apply (status field + zero UPDATE surface),
skip-known idempotence, per-run cap, unmeasurable honesty, dry-run
zero-write, services row.
"""
from __future__ import annotations

import datetime as dt
import importlib.util as _ilu
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[3]
_spec = _ilu.spec_from_file_location(
    "memory_contradictions",
    _REPO / "cabinet" / "scripts" / "memory-contradictions.py")
mc = _ilu.module_from_spec(_spec)
sys.modules["memory_contradictions"] = mc
_spec.loader.exec_module(mc)


def _row(id, content, ts="2026-07-01T10:00:00Z", stype="captain_decision"):
    return {"id": str(id), "source_type": stype, "officer": "cos",
            "content": content, "ts": ts}


class TestPropose:
    def test_near_duplicate_newer_supersedes_older(self):
        rows = [
            _row(1, "Todos board 42424242 is the authoritative to-do store "
                    "since June ninth replacing Apple Reminders entirely",
                 ts="2026-06-09T10:00:00Z"),
            _row(2, "The Todos board 42424242 is the authoritative to-do "
                    "store since June ninth replacing Apple Reminders",
                 ts="2026-07-01T10:00:00Z"),
        ]
        props = mc.propose(rows)
        assert len(props) == 1
        p = props[0]
        assert p["reason"] == "near-duplicate"
        assert p["new"]["id"] == "2" and p["old"]["id"] == "1"
        assert p["status"] == "proposed"

    def test_contradiction_cue_fires_on_shared_topic(self):
        rows = [
            _row(1, "Monday People board 42424243 is the CRM store for all "
                    "people and relationship data",
                 ts="2026-06-01T10:00:00Z"),
            _row(2, "Monday People board 42424243 is retired and replaced — "
                    "people and relationship data moved to the vault CRM",
                 ts="2026-07-05T10:00:00Z"),
        ]
        props = mc.propose(rows)
        assert len(props) == 1
        p = props[0]
        assert p["reason"] == "contradiction-cue"
        assert "retired" in p["cues"]
        assert p["new"]["id"] == "2"

    def test_unrelated_rows_stay_quiet(self):
        rows = [_row(1, "Bakery VIES autofill shipped for sponsor numbers"),
                _row(2, "Cabinet world tileset uses LimeZu modern interiors")]
        assert mc.propose(rows) == []

    def test_cue_without_overlap_stays_quiet(self):
        rows = [_row(1, "Bakery VIES autofill shipped for sponsors"),
                _row(2, "Never route calendar writes through AppleScript")]
        assert mc.propose(rows) == []

    def test_buckets_isolate_source_types(self):
        rows = [
            _row(1, "the same identical belief text about the todos board",
                 stype="captain_decision"),
            _row(2, "the same identical belief text about the todos board",
                 stype="telegram_dm"),
        ]
        assert mc.propose(rows) == []   # cross-type pairs never compared

    def test_per_run_cap(self, monkeypatch):
        monkeypatch.setattr(mc, "MAX_PROPOSALS_PER_RUN", 3)
        base = "identical repeated belief text about the vault crm store"
        rows = [_row(i, base, ts=f"2026-07-0{1 + i % 8}T10:00:00Z")
                for i in range(10)]
        assert len(mc.propose(rows)) == 3


class TestRunPass:
    def _dup_rows(self):
        return [
            _row(1, "the todos board is the authoritative store for tasks",
                 ts="2026-06-09T10:00:00Z"),
            _row(2, "the todos board is the authoritative store for tasks",
                 ts="2026-07-01T10:00:00Z"),
        ]

    def test_appends_and_skips_known(self, tmp_path):
        out = tmp_path / "proposals.jsonl"
        s1 = mc.run_pass(rows=self._dup_rows(), out_path=out)
        assert s1["new"] == 1 and s1["measurable"]
        s2 = mc.run_pass(rows=self._dup_rows(), out_path=out)
        assert s2["new"] == 0 and s2["known"] == 1
        rows = [json.loads(l) for l in out.read_text().splitlines()]
        assert len(rows) == 1 and rows[0]["proposed_at"]

    def test_propose_never_apply(self, tmp_path):
        """The organ's entire write surface is the proposals file — the
        module source must carry no SQL UPDATE statement at all."""
        src = (_REPO / "cabinet" / "scripts" /
               "memory-contradictions.py").read_text()
        assert not re.search(r"(?i)\bUPDATE\s+cabinet_memory\b", src)
        assert not re.search(r"(?i)\bSET\s+superseded_by\b", src)
        out = tmp_path / "p.jsonl"
        mc.run_pass(rows=self._dup_rows(), out_path=out)
        row = json.loads(out.read_text().splitlines()[0])
        assert row["status"] == "proposed"

    def test_dry_run_writes_nothing(self, tmp_path):
        out = tmp_path / "p.jsonl"
        s = mc.run_pass(rows=self._dup_rows(), out_path=out, dry_run=True)
        assert s["new"] == 1 and not out.exists()

    def test_unmeasurable_is_honest(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mc, "load_live_rows", lambda: None)
        s = mc.run_pass(out_path=tmp_path / "p.jsonl")
        assert s["measurable"] is False and s["rows"] == 0


def test_sql_is_readonly_select():
    sql = mc._ROWS_SQL.strip().upper()
    assert sql.startswith("SELECT")
    for verb in ("UPDATE", "DELETE", "INSERT", "DROP", "ALTER", ";"):
        assert verb not in sql


def test_services_row_is_scheduled():
    services = yaml.safe_load(
        (_REPO / "cabinet" / "services.yml").read_text())["services"]
    rows = [s for s in services if s.get("name") == "memory-contradictions"]
    assert len(rows) == 1, "memory-contradictions row lost — pass unscheduled"
    row = rows[0]
    assert row["label"] == "com.cabinet.memory-contradictions"
    assert "memory-contradictions.py" in row["command"]
    assert row["schedule"]["calendar"] and not row.get("disabled")
