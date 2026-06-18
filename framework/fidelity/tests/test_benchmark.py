from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.fidelity import benchmark
from framework.fidelity.types import Case


def _write_outcomes(tmp_path) -> Path:
    rows = [
        {"ts": "2026-06-07T21:05:48+00:00", "lane": "send-1to1-reply",
         "action_id": "backfill-sent|MID1", "mode": "shadow", "source": "backfill",
         "would_text": "cut...", "nate_text": "cut...", "match": False},
        {"ts": "2026-06-07T21:05:49+00:00", "lane": "send-1to1-reply",
         "action_id": "backfill-sent|MID2", "mode": "shadow", "source": "backfill",
         "would_text": "cut...", "nate_text": "cut...", "match": True},
        {"ts": "2026-06-07T21:05:50+00:00", "lane": "some-other-lane",
         "action_id": "x", "mode": "shadow", "source": "backfill",
         "would_text": "t", "nate_text": "t", "match": False},
    ]
    p = tmp_path / "autonomy_outcomes.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


class TestAutonomyUniverse:
    def test_filters_to_lane(self, tmp_path):
        p = _write_outcomes(tmp_path)
        rows = benchmark.load_autonomy_rows(path=p)
        assert len(rows) == 2
        assert all(r["lane"] == "send-1to1-reply" for r in rows)

    def test_validation_count_is_universe_size(self, tmp_path):
        p = _write_outcomes(tmp_path)
        assert benchmark.validation_count(path=p) == 2

    def test_missing_file_is_zero(self, tmp_path):
        assert benchmark.validation_count(path=tmp_path / "nope.jsonl") == 0


class TestBuildCases:
    def test_maps_retro_cases_to_case_objects(self, monkeypatch):
        fake_rc = {
            "case_id": "c1", "reply_key": "k", "slug": "ulrik", "person": "Ulrik",
            "channel": "msgraph", "language": "da",
            "reply_ts": "2026-06-10T12:00:00+00:00", "subject": "s", "n_prior": 2,
            "thread_before": [{"date": "2026-06-09T00:00:00+00:00",
                               "direction": "received", "who": "Ulrik <u@x>",
                               "source": "msgraph", "text": "hej"}],
            "real_reply": "Ja.",
        }
        monkeypatch.setattr(benchmark.retro, "extract_cases",
                            lambda n_cases=24, people_dir=None: [fake_rc])
        cases = benchmark.build_cases(n=1)
        assert len(cases) == 1
        c = cases[0]
        assert isinstance(c, Case)
        assert c.lane == "send-1to1-reply"
        assert c.decision_type == "reply"
        assert c.cutoff_ts == "2026-06-10T12:00:00+00:00"
        assert c.real_reply == "Ja."

    def test_empty_extract_yields_no_cases(self, monkeypatch):
        monkeypatch.setattr(benchmark.retro, "extract_cases",
                            lambda n_cases=24, people_dir=None: [])
        assert benchmark.build_cases(n=0) == []

    def test_unsupported_cell_raises(self):
        with pytest.raises(NotImplementedError):
            benchmark.build_cases(lane="triage", decision_type="triage", n=1)
