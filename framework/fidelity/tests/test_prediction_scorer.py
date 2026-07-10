"""W9 / ledger A10 — prediction scorer (report-only Brier series), 2026-07-09.

Pins the join (Redis action records × ledger ground truth via correlation
cid), the conservative truth mapping (unknown rows score NOTHING; any
failed/wrong row falsifies the card), the Brier/calibration math, and the
idempotent-per-date series append. All offline — records/ledger injected.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest
import yaml

from pathlib import Path


# ledger cids must be well-formed uuid4 hex (correlation.is_cid) — mint
# deterministic 32-hex test cids from short tags.
def _cid(tag: str) -> str:
    return (tag.encode().hex() * 16)[:32]

from framework.fidelity import prediction_scorer as ps
from framework.probes import correlation

NOW = dt.datetime(2026, 7, 9, 8, 20, tzinfo=dt.timezone.utc)


def _rec(cid, conf, lane="bakery"):
    return {"cid": cid, "confidence": conf, "lane": lane,
            "subject": "s", "steps": []}


def _acted(cid, *, status=None, verdict=None):
    ev = {"ts": "2026-07-08T10:00:00Z",
          "actor": {"kind": "officer", "id": "cos"}, "lane": "bakery",
          "action": "acted-step", "subject": "s",
          "refs": [correlation.ref_for(cid)]}
    if status is not None:
        ev["outcome"] = {"status": status}
    if verdict is not None:
        ev["review"] = {"verdict": verdict}
    return ev


class TestGroundTruth:
    def test_ttl_ok_row_is_a_positive_label(self):
        truth = ps.ground_truth_by_cid([_acted(_cid("c1"), status="ok")])
        assert truth == {_cid("c1"): 1}

    def test_failed_and_wrong_are_negative_labels(self):
        truth = ps.ground_truth_by_cid([
            _acted(_cid("c1"), status="failed"),
            _acted(_cid("c2"), status="ok", verdict="wrong"),
        ])
        assert truth == {_cid("c1"): 0, _cid("c2"): 0}

    def test_unknown_rows_produce_no_label(self):
        truth = ps.ground_truth_by_cid([
            _acted(_cid("c1"), status="unknown"), _acted(_cid("c2"))])
        assert truth == {}

    def test_any_failed_row_falsifies_the_whole_card(self):
        truth = ps.ground_truth_by_cid([
            _acted(_cid("c1"), status="ok"), _acted(_cid("c1"), status="failed")])
        assert truth == {_cid("c1"): 0}
        # order-independent
        truth = ps.ground_truth_by_cid([
            _acted(_cid("c1"), status="failed"), _acted(_cid("c1"), status="ok")])
        assert truth == {_cid("c1"): 0}

    def test_rows_without_cid_are_ignored(self):
        ev = _acted(_cid("c1"), status="ok")
        ev["refs"] = ["monday:123"]
        assert ps.ground_truth_by_cid([ev]) == {}


class TestScoring:
    def test_brier_and_counts(self):
        records = [_rec(_cid("c1"), 0.9), _rec(_cid("c2"), 0.8), _rec(_cid("c3"), 0.5)]
        truth = {_cid("c1"): 1, _cid("c2"): 0}          # c3 not ground-truthed yet
        m = ps.score_predictions(records, truth)
        assert m["n_predictions"] == 3
        assert m["n_ground_truthed"] == 2
        assert m["brier"] == pytest.approx(((0.9 - 1) ** 2 + 0.8 ** 2) / 2,
                                           abs=1e-4)

    def test_no_ground_truth_is_unmeasured_not_zero(self):
        m = ps.score_predictions([_rec(_cid("c1"), 0.9)], {})
        assert m["brier"] is None           # honest unmeasured, never 0.0
        assert m["n_predictions"] == 1 and m["n_ground_truthed"] == 0

    def test_malformed_confidence_skipped_and_clamped(self):
        records = [_rec(_cid("c1"), "not-a-float"), _rec(_cid("c2"), 1.7), _rec(_cid("c3"), -2)]
        m = ps.score_predictions(records, {_cid("c2"): 1, _cid("c3"): 0})
        assert m["n_predictions"] == 2      # c1 dropped
        assert m["brier"] == pytest.approx(0.0)  # clamped to 1.0 / 0.0

    def test_calibration_bins_and_by_lane(self):
        records = [_rec(_cid("c1"), 0.95, lane="bakery"), _rec(_cid("c2"), 0.92, lane="bakery"),
                   _rec(_cid("c3"), 0.15, lane="newsletter")]
        truth = {_cid("c1"): 1, _cid("c2"): 0, _cid("c3"): 0}
        m = ps.score_predictions(records, truth)
        top = [b for b in m["calibration"] if b["lo"] == 0.9][0]
        assert top["n"] == 2 and top["empirical_rate"] == 0.5
        assert m["by_lane"]["bakery"]["n"] == 2
        assert m["by_lane"]["newsletter"]["n"] == 1


class TestEmitter:
    def test_appends_one_line_idempotent_per_date(self, tmp_path):
        out = tmp_path / "series.jsonl"
        line = ps.emit_daily_line(records=[_rec(_cid("c1"), 0.9)],
                                  ledger=[_acted(_cid("c1"), status="ok")],
                                  now=NOW, out_path=out)
        assert line and line["date"] == "2026-07-09"
        assert line["brier"] == pytest.approx(0.01)
        again = ps.emit_daily_line(records=[], ledger=[], now=NOW, out_path=out)
        assert again is None                 # idempotent per date
        rows = [json.loads(l) for l in out.read_text().splitlines()]
        assert len(rows) == 1

    def test_report_only_no_other_side_effects(self, tmp_path):
        out = tmp_path / "series.jsonl"
        before = sorted(p.name for p in tmp_path.iterdir())
        ps.emit_daily_line(records=[], ledger=[], now=NOW, out_path=out)
        after = sorted(p.name for p in tmp_path.iterdir())
        assert after == before + ["series.jsonl"]


def test_services_row_is_scheduled_daily():
    services = yaml.safe_load(
        (Path(ps.__file__).resolve().parents[2] / "cabinet/services.yml")
        .read_text())["services"]
    rows = [s for s in services if s.get("name") == "prediction-calibration"]
    assert len(rows) == 1, "prediction-calibration row lost — A10 unscheduled"
    row = rows[0]
    assert row["label"] == "com.cabinet.prediction-calibration"
    assert "prediction_scorer" in row["command"]
    assert row["schedule"]["calendar"], "must be a daily calendar row"
