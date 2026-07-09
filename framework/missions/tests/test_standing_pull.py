"""SOV-8 standing-pull tests — R1-R6 ranking, the outcomes.yml never-touch
guarantee, sovereign gating, and idempotent writes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

_ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from framework.missions import standing_pull  # noqa: E402

NOW = "2026-07-05T12:00:00Z"


@pytest.fixture()
def root(tmp_path, monkeypatch):
    root = tmp_path / "cab"
    (root / "shared" / "interfaces").mkdir(parents=True)
    (root / "instance" / "config").mkdir(parents=True)
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
    monkeypatch.delenv("CABINET_NEEDS_WIRED", raising=False)
    return root


def _write_need(root, nid="NEED-11223344", *, blocking=False):
    row = {"id": nid, "kind": "credential", "status": "open",
           "why": "expired token", "count": 2,
           "cost_of_delay": "blocking" if blocking else "medium",
           "last_seen": NOW, "first_seen": NOW}
    p = root / "shared" / "interfaces" / "needs-ledger.jsonl"
    with open(p, "a") as fh:
        fh.write(json.dumps(row) + "\n")


class TestCollect:
    def test_r1_needs_ranked_first(self, root):
        _write_need(root, "NEED-11223344", blocking=True)
        # stale falsifier series ⇒ an R4 candidate too
        rows = standing_pull.collect(root, NOW)
        assert rows, "expected candidates"
        assert rows[0]["source"] == "R1"
        assert "NEED-11223344" in rows[0]["name"]
        assert any(r["source"] == "R4" for r in rows)

    def test_r4_quiet_when_series_fresh(self, root):
        series = root / "shared" / "interfaces" / "falsifier-series.jsonl"
        series.write_text(json.dumps({"date": "2026-07-05"}) + "\n")
        rows = standing_pull.collect(root, NOW)
        assert not any(r["source"] == "R4" for r in rows)

    def test_r5_draft_skills(self, root):
        sdir = root / "memory" / "skills" / "evolved"
        sdir.mkdir(parents=True)
        (sdir / "induced-x-y.md").write_text(
            "---\nname: x\nstatus: draft\n---\nbody")
        rows = standing_pull.collect(root, NOW)
        r5 = [r for r in rows if r["source"] == "R5"]
        assert r5 and "induced-x-y" in r5[0]["name"]

    def test_collect_never_raises_on_empty_root(self, tmp_path):
        assert standing_pull.collect(tmp_path / "ghost", NOW) is not None

    def test_deterministic_ids(self, root):
        _write_need(root)
        a = standing_pull.collect(root, NOW)
        b = standing_pull.collect(root, NOW)
        assert [r["id"] for r in a] == [r["id"] for r in b]
        assert all(r["id"].startswith("standing-") for r in a)


def _write_calibration(root, date, *, n_pred, n_truth):
    p = root / "shared" / "interfaces" / "prediction-calibration.jsonl"
    with open(p, "a") as fh:
        fh.write(json.dumps({"date": date, "n_predictions": n_pred,
                             "n_ground_truthed": n_truth}) + "\n")


class TestR6Labels:
    def test_unmeasured_when_series_absent(self, root):
        rows = [r for r in standing_pull.collect(root, NOW)
                if r["source"] == "R6"]
        assert len(rows) == 1
        assert "telemetry" in rows[0]["name"]

    def test_starved_zero_labels_on_flowing_predictions(self, root):
        _write_calibration(root, "2026-07-05", n_pred=12, n_truth=0)
        rows = [r for r in standing_pull.collect(root, NOW)
                if r["source"] == "R6"]
        assert len(rows) == 1
        assert rows[0]["name"] == "Repair label starvation"
        assert "0/12" in rows[0]["description"]

    def test_starved_low_ratio(self, root):
        _write_calibration(root, "2026-07-05", n_pred=20, n_truth=2)  # 10% < 20%
        rows = [r for r in standing_pull.collect(root, NOW)
                if r["source"] == "R6"]
        assert rows and rows[0]["name"] == "Repair label starvation"

    def test_quiet_when_fed(self, root):
        _write_calibration(root, "2026-07-05", n_pred=20, n_truth=8)
        assert not [r for r in standing_pull.collect(root, NOW)
                    if r["source"] == "R6"]

    def test_quiet_on_tiny_sample_with_some_labels(self, root):
        # 1/4 ground-truthed: under the floor but under min sample too — quiet
        _write_calibration(root, "2026-07-05", n_pred=4, n_truth=1)
        assert not [r for r in standing_pull.collect(root, NOW)
                    if r["source"] == "R6"]

    def test_stale_series_is_unmeasured_not_starved(self, root):
        _write_calibration(root, "2026-06-20", n_pred=12, n_truth=0)
        rows = [r for r in standing_pull.collect(root, NOW)
                if r["source"] == "R6"]
        assert len(rows) == 1 and "telemetry" in rows[0]["name"]

    def test_newest_line_wins(self, root):
        _write_calibration(root, "2026-07-04", n_pred=12, n_truth=0)
        _write_calibration(root, "2026-07-05", n_pred=12, n_truth=6)
        assert not [r for r in standing_pull.collect(root, NOW)
                    if r["source"] == "R6"]

    def test_r6_ranks_after_r1(self, root):
        _write_need(root, blocking=True)
        _write_calibration(root, "2026-07-05", n_pred=12, n_truth=0)
        rows = standing_pull.collect(root, NOW)
        srcs = [r["source"] for r in rows]
        assert srcs.index("R1") < srcs.index("R6")


class TestNeverTouchesOutcomes:
    def test_refuses_outcomes_paths(self, tmp_path):
        for bad in (tmp_path / "outcomes.yml",
                    tmp_path / "instance" / "config" / "outcomes.yml",
                    tmp_path / "instance" / "config" / "standing-missions.yml"):
            with pytest.raises(PermissionError):
                standing_pull._refuse_captain_paths(bad)

    def test_run_leaves_outcomes_yml_byte_identical(self, root, monkeypatch):
        outcomes = root / "instance" / "config" / "outcomes.yml"
        outcomes.write_text("outcomes:\n  - id: o1\n    name: Captain thing\n")
        before = outcomes.read_bytes()
        _write_need(root)
        report = standing_pull.run(root, now=NOW, posture="sovereign")
        assert report["written"] >= 1
        assert outcomes.read_bytes() == before
        # the ONLY yml written is standing-missions.yml under shared/
        written = {p.relative_to(root).as_posix()
                   for p in root.rglob("*.yml") if p.is_file()}
        assert written == {"instance/config/outcomes.yml",
                           "shared/interfaces/standing-missions.yml"}


class TestRun:
    def test_guardian_writes_nothing(self, root):
        _write_need(root)
        report = standing_pull.run(root, now=NOW, posture="guardian")
        assert report["skipped"] == "posture" and report["written"] == 0
        assert not standing_pull.standing_missions_path(root).exists()

    def test_default_posture_is_guardian_in_test_env(self, root, monkeypatch):
        monkeypatch.delenv("CABINET_POSTURE", raising=False)
        monkeypatch.setenv("CABINET_ROOT", str(root))
        report = standing_pull.run(root, now=NOW)
        assert report["posture"] == "guardian"
        assert not standing_pull.standing_missions_path(root).exists()

    def test_dry_run_writes_nothing(self, root):
        _write_need(root)
        report = standing_pull.run(root, now=NOW, posture="sovereign",
                                   dry_run=True)
        assert report["skipped"] == "dry_run"
        assert not standing_pull.standing_missions_path(root).exists()

    def test_sovereign_write_is_compilable_shape(self, root, monkeypatch):
        monkeypatch.setenv("CABINET_ID", "test-cab")
        _write_need(root, blocking=True)
        report = standing_pull.run(root, now=NOW, posture="sovereign", cap=3)
        path = standing_pull.standing_missions_path(root)
        doc = yaml.safe_load(path.read_text())
        assert doc["deployment"] == "test-cab"
        assert doc["generated_by"] == "framework.missions.standing_pull"
        assert 1 <= len(doc["outcomes"]) <= 3
        first = doc["outcomes"][0]
        assert set(first) == {"id", "name", "description",
                              "measurable_criteria", "status"}
        assert first["status"] == "active"
        assert report["path"] == str(path)
        # idempotent rewrite
        standing_pull.run(root, now=NOW, posture="sovereign", cap=3)
        assert yaml.safe_load(path.read_text())["outcomes"][0]["id"] == first["id"]
