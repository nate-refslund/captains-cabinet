"""Tests for cabinet/scripts/world-census.py (E0a census keyframe writer).

Pins the falsifier-series discipline the kickoff doc makes binding:
append-only + flock, idempotent per date, PII-free ints/enums ONLY (the
validator refuses free text — the census structurally cannot leak), honest
None for absent sources (never fake zeros), fenced local reads.
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "world-census.py"

# world-census.py is hyphenated — load via importlib (same pattern as
# test_gen_officer_mcp_config.py).
spec = _ilu.spec_from_file_location("world_census", _SCRIPT)
wc = _ilu.module_from_spec(spec)
sys.modules["world_census"] = wc
spec.loader.exec_module(wc)


def _fixture_line(**overrides):
    """A fully-fixtured keyframe (no live reads)."""
    line = wc.compute_census(
        org_events={"org_events_total": 147007, "actors_distinct": 9,
                    "events_today": 120, "ev_work_item_completed": 6708,
                    "ev_skill_promoted": 4},
        ledgers={"consequence_ledger_lines": 549, "undo_journal_lines": 12,
                 "canary_receipt_lines": 3, "falsifier_series_lines": 8},
        falsifier={"cells_accumulating": 12, "cells_graduated": 0,
                   "stamped_rows_total": 14, "acted_7d": 1, "approved_7d": 3,
                   "proactive_cards_7d": 33, "memory_rows_total": 619,
                   "memory_source_types": 9},
        commits=967,
        files={"evolved_skills": 9, "golden_evals": 22,
               "golden_evals_delta_vs_seed": -3, "tier2_note_files": 32,
               "tier3_files": 5, "remember_files": 221, "packs_dirs": 5,
               "captain_rules": 38, "captain_vetoes_total": 0,
               "outcomes_total": 10},
        manifest={"services_rows_total": 30, "services_rows_disabled": 2},
        posture="guardian",
        chronicle_prior=0,
    )
    line.update(overrides)
    return line


class TestSchemaFence:
    def test_valid_line_passes(self):
        wc.validate_census(_fixture_line())

    def test_free_text_refused(self):
        line = _fixture_line()
        line["ev_work_item_completed"] = "Reply to kristoffer@stepnetwork.dk"
        with pytest.raises(wc.CensusSchemaError):
            wc.validate_census(line)

    def test_token_shaped_string_refused(self):
        line = _fixture_line()
        line["commits_total"] = "ghp_abc123SECRET"
        with pytest.raises(wc.CensusSchemaError):
            wc.validate_census(line)

    def test_bool_refused(self):
        # bool is an int subclass — an easy smuggle; the fence rejects it.
        line = _fixture_line()
        line["acted_7d"] = True
        with pytest.raises(wc.CensusSchemaError):
            wc.validate_census(line)

    def test_float_refused(self):
        line = _fixture_line()
        line["acted_7d"] = 0.5
        with pytest.raises(wc.CensusSchemaError):
            wc.validate_census(line)

    def test_enum_outside_closed_set_refused(self):
        line = _fixture_line(org_posture="yolo")
        with pytest.raises(wc.CensusSchemaError):
            wc.validate_census(line)

    def test_bad_key_shape_refused(self):
        line = _fixture_line()
        line["Injected Key!"] = 1
        with pytest.raises(wc.CensusSchemaError):
            wc.validate_census(line)

    def test_none_is_honest_fog(self):
        # Absent source = None, and None validates (honest unmeasured).
        line = _fixture_line()
        line["remember_files"] = None
        wc.validate_census(line)

    def test_invalid_line_never_appends(self, tmp_path):
        series = tmp_path / "world-chronicle.jsonl"
        line = _fixture_line()
        line["ev_skill_promoted"] = "free text"
        with pytest.raises(wc.CensusSchemaError):
            wc.append_keyframe(line, path=series)
        assert not series.exists() or series.read_text() == ""


class TestAppendDiscipline:
    def test_append_then_idempotent_same_date(self, tmp_path):
        series = tmp_path / "world-chronicle.jsonl"
        line = _fixture_line()
        assert wc.append_keyframe(line, path=series) is True
        assert wc.append_keyframe(line, path=series) is False  # same date no-op
        rows = [json.loads(l) for l in series.read_text().splitlines()]
        assert len(rows) == 1
        assert rows[0]["date"] == line["date"]

    def test_append_only_two_dates_accumulate(self, tmp_path):
        series = tmp_path / "world-chronicle.jsonl"
        import datetime as dt
        d1 = dt.datetime(2026, 7, 7, 8, 15, tzinfo=dt.timezone.utc)
        d2 = dt.datetime(2026, 7, 8, 8, 15, tzinfo=dt.timezone.utc)
        assert wc.append_keyframe(_fixture_line(date=d1.strftime("%Y-%m-%d")),
                                  path=series)
        assert wc.append_keyframe(_fixture_line(date=d2.strftime("%Y-%m-%d")),
                                  path=series)
        rows = [json.loads(l) for l in series.read_text().splitlines()]
        assert [r["date"] for r in rows] == ["2026-07-07", "2026-07-08"]

    def test_corrupt_line_never_blocks_append(self, tmp_path):
        series = tmp_path / "world-chronicle.jsonl"
        series.write_text("{corrupt\n")
        assert wc.append_keyframe(_fixture_line(), path=series) is True
        assert len(series.read_text().splitlines()) == 2

    def test_sorted_keys_stable_serialization(self, tmp_path):
        series = tmp_path / "world-chronicle.jsonl"
        wc.append_keyframe(_fixture_line(), path=series)
        raw = series.read_text().splitlines()[0]
        assert raw == json.dumps(json.loads(raw), sort_keys=True)


class TestFencedReads:
    def test_absent_db_reads_none_not_zero(self, monkeypatch, tmp_path):
        monkeypatch.setattr(wc, "SQLITE_DB", tmp_path / "missing.sqlite3")
        out = wc.read_org_events()
        assert out["org_events_total"] is None
        assert out["ev_work_item_completed"] is None

    def test_absent_ledger_none_empty_ledger_zero(self, monkeypatch, tmp_path):
        monkeypatch.setattr(wc, "EVENT_LOG_DIR", tmp_path / "absent")
        monkeypatch.setattr(wc, "UNDO_DIR", tmp_path / "undo")
        (tmp_path / "undo").mkdir()
        (tmp_path / "undo" / "canary-receipts.jsonl").write_text("")
        out = wc.read_ledger_counts()
        assert out["consequence_ledger_lines"] is None   # absent source
        assert out["canary_receipt_lines"] == 0          # present, empty

    def test_posture_fail_closed_guardian(self, monkeypatch, tmp_path):
        monkeypatch.setattr(wc, "_REPO_ROOT", tmp_path)
        assert wc.read_org_posture() == "guardian"       # absent
        cfg = tmp_path / "instance" / "config"
        cfg.mkdir(parents=True)
        (cfg / "posture.yml").write_text("autonomy_level: banana\n")
        assert wc.read_org_posture() == "guardian"       # unknown → narrow
        (cfg / "posture.yml").write_text("autonomy_level: sovereign\n")
        assert wc.read_org_posture() == "sovereign"

    def test_falsifier_block_lifts_ints_only(self, monkeypatch, tmp_path):
        monkeypatch.setattr(wc, "_REPO_ROOT", tmp_path)
        si = tmp_path / "shared" / "interfaces"
        si.mkdir(parents=True)
        (si / "falsifier-series.jsonl").write_text(json.dumps({
            "date": "2026-07-07", "cells_graduated": 0,
            "cells_accumulating": 12, "stamped_rows_total": 14,
            "acted_7d": 1, "approved_7d": 3, "proactive_cards_7d": 33,
            "reversal_rate_7d": None,   # float-typed field — never lifted
            "memory_ingestion": {"skill": {"n": 12, "latest": "x"},
                                 "reflection": {"n": 7, "latest": "y"}},
        }) + "\n")
        out = wc.read_falsifier_block()
        assert out["cells_graduated"] == 0
        assert out["memory_rows_total"] == 19
        assert out["memory_source_types"] == 2
        assert "reversal_rate_7d" not in out

    def test_compute_census_fully_fixtured_is_pure(self):
        a = _fixture_line()
        b = _fixture_line()
        assert a == b
