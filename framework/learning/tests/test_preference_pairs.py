"""Preference-pair miner (Rec, 2026-07-09) — captain_preferences store.

Fixture-driven, all sources injected. Pins: correction pairs from
action-lessons rows (edit carries verbatim captain_text as preferred;
undo/never/rejected mint REFRAIN preferences), ledger join for the
rejected-side subject, standing pairs from captain-patterns.md with
provenance kept, stable ids + append-only skip-known store, dry-run
zero-write, fail-harmless sources, services row.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from framework.learning import preference_pairs as pp


def _lesson(ref="lesson-001", verdict="edit", text="shorter, and in Danish",
            pid="p1", action_type="pm_write", lane="bakery"):
    return {"lesson_ref": ref, "ts": "2026-07-08T10:00:00Z", "pid": pid,
            "cid": None, "action_type": action_type, "lane": lane,
            "verdict": verdict, "captain_text": text,
            "taxonomy": "wrong-content"}


LEDGER = {"p1": {"subject": "Draft reply to Casper about VIES autofill",
                 "action": "action-card"}}

PATTERNS_MD = """# Captain patterns

### officer-note 2026-07-05 — replies short [trust:officer]
Ada prefers terse single-line replies. No padding.

### captain 2026-07-06 — never Reminders authority [trust:captain]
Todos board is authoritative; Reminders is one-way nudges only.
"""


class TestCorrectionPairs:
    def test_edit_pair_carries_verbatim_preferred(self):
        pairs = pp.mine_correction_pairs([_lesson()], LEDGER)
        assert len(pairs) == 1
        p = pairs[0]
        assert p["kind"] == "correction" and p["verdict"] == "edit"
        assert p["preferred"] == "shorter, and in Danish"
        assert p["captain_text"] == "shorter, and in Danish"
        assert p["rejected"]["subject"].startswith("Draft reply to Casper")
        assert p["rejected"]["action_type"] == "pm_write"
        assert p["source"] == "action-lessons:lesson-001"

    @pytest.mark.parametrize("verdict", ["undo", "never", "rejected"])
    def test_refrain_verdicts_mint_refrain_preference(self, verdict):
        pairs = pp.mine_correction_pairs(
            [_lesson(verdict=verdict, text="wrong")], LEDGER)
        assert len(pairs) == 1
        assert "preferred" in pairs[0] and pairs[0]["preferred"]
        assert pairs[0]["preferred"] != "wrong"    # refrain, not the text

    def test_unknown_verdict_and_missing_ref_skipped(self):
        assert pp.mine_correction_pairs(
            [_lesson(verdict="confirmed"), {"verdict": "edit"}], {}) == []

    def test_missing_ledger_row_still_mines(self):
        pairs = pp.mine_correction_pairs([_lesson(pid="ghost")], {})
        assert pairs[0]["rejected"]["subject"] == ""


class TestStandingPairs:
    def test_patterns_parsed_with_provenance(self):
        pairs = pp.mine_standing_pairs(PATTERNS_MD)
        assert len(pairs) == 2
        assert pairs[0]["kind"] == "standing-pattern"
        assert "[trust:officer]" in pairs[0]["heading"]
        assert "terse single-line" in pairs[0]["preferred"]
        assert "[trust:captain]" in pairs[1]["heading"]

    def test_absent_file_yields_nothing(self, monkeypatch):
        monkeypatch.setattr(pp, "_REPO_ROOT", Path("/nonexistent"))
        assert pp.mine_standing_pairs(None) == []


class TestHarvest:
    def test_append_only_skip_known(self, tmp_path):
        out = tmp_path / "pairs.jsonl"
        s1 = pp.harvest(lessons=[_lesson()], ledger_by_pid=LEDGER,
                        patterns_md=PATTERNS_MD, out_path=out)
        assert s1["new"] == 3 and s1["mined"] == 3
        assert s1["by_kind"] == {"correction": 1, "standing-pattern": 2}
        # second pass: same sources + one new lesson → only the new one lands
        s2 = pp.harvest(lessons=[_lesson(), _lesson(ref="lesson-002",
                                                    text="use the board")],
                        ledger_by_pid=LEDGER, patterns_md=PATTERNS_MD,
                        out_path=out)
        assert s2["new"] == 1 and s2["known"] == 3
        rows = [json.loads(l) for l in out.read_text().splitlines()]
        assert len(rows) == 4
        assert len({r["pair_id"] for r in rows}) == 4
        assert all(r.get("harvested_at") for r in rows)

    def test_dry_run_writes_nothing(self, tmp_path):
        out = tmp_path / "pairs.jsonl"
        s = pp.harvest(lessons=[_lesson()], ledger_by_pid=LEDGER,
                       patterns_md="", out_path=out, dry_run=True)
        assert s["new"] == 1 and not out.exists()

    def test_corrupt_store_lines_do_not_crash(self, tmp_path):
        out = tmp_path / "pairs.jsonl"
        out.write_text("not json\n")
        s = pp.harvest(lessons=[_lesson()], ledger_by_pid=LEDGER,
                       patterns_md="", out_path=out)
        assert s["new"] == 1


def test_services_row_is_scheduled():
    repo = Path(pp.__file__).resolve().parents[2]
    services = yaml.safe_load(
        (repo / "cabinet" / "services.yml").read_text())["services"]
    rows = [s for s in services if s.get("name") == "preference-pairs"]
    assert len(rows) == 1, "preference-pairs row lost — harvest unscheduled"
    row = rows[0]
    assert row["label"] == "com.cabinet.preference-pairs"
    assert "preference_pairs" in row["command"]
    assert row["schedule"]["calendar"] and not row.get("disabled")
