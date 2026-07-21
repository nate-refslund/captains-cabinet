"""Tests for cabinet/scripts/world-port-calls.py fold functions.

Pure fixture blobs — no live git, no repo state dependency (the extraction
half is the proven backtest pattern; the FOLD is what this suite pins:
first-achieved-date wins, lane attribution, malformed-row honesty, artifact
shape)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "world-port-calls.py"

spec = importlib.util.spec_from_file_location("world_port_calls", SCRIPT)
wpc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wpc)


def _doc(*outcomes):
    return {"outcomes": list(outcomes)}


def _o(oid, status, lane=None):
    o = {"id": oid, "status": status}
    if lane is not None:
        o["lane"] = lane
    return o


# ── lane_of (byte-mirror of the backtest rule) ──────────────────────────────

def test_lane_of_explicit_lane_wins():
    assert wpc.lane_of({"id": "outcome-bakery-001", "lane": "system-self"}) == "system-self"


def test_lane_of_from_id():
    assert wpc.lane_of({"id": "outcome-bakery-003"}) == "bakery"
    assert wpc.lane_of({"id": "outcome-newsletter-orchard-001"}) == "newsletter-orchard"
    assert wpc.lane_of({"id": "outcome-world-onboarding-v1b-001"}) == "world-onboarding-v1b"


def test_lane_of_unparseable():
    assert wpc.lane_of({"id": "not-an-outcome-id"}) is None
    assert wpc.lane_of({}) is None


# ── outcome_statuses ────────────────────────────────────────────────────────

def test_outcome_statuses_skips_malformed_rows():
    doc = {"outcomes": [_o("outcome-a-001", "active"), "junk", {"status": "achieved"}, None]}
    st = wpc.outcome_statuses(doc)
    assert list(st) == ["outcome-a-001"]
    assert st["outcome-a-001"]["status"] == "active"


def test_outcome_statuses_non_dict_doc():
    assert wpc.outcome_statuses(None) == {}
    assert wpc.outcome_statuses([1, 2]) == {}
    assert wpc.outcome_statuses({"outcomes": None}) == {}


# ── fold_port_calls: first achieved-flip date wins ──────────────────────────

def test_first_flip_date_wins():
    snaps = [
        ("2026-06-10", _doc(_o("outcome-bakery-003", "active"))),
        ("2026-07-02", _doc(_o("outcome-bakery-003", "achieved"))),
        ("2026-07-09", _doc(_o("outcome-bakery-003", "achieved"))),
    ]
    lanes = wpc.fold_port_calls(snaps)
    assert lanes == {"bakery": [{"date": "2026-07-02", "outcome_id": "outcome-bakery-003"}]}


def test_never_achieved_never_stamps():
    snaps = [
        ("2026-06-10", _doc(_o("outcome-bakery-001", "active"))),
        ("2026-07-02", _doc(_o("outcome-bakery-001", "active"),
                            _o("outcome-orchard-001", "retired"))),
    ]
    assert wpc.fold_port_calls(snaps) == {}


def test_revert_then_reachieve_keeps_first_date():
    snaps = [
        ("2026-07-01", _doc(_o("outcome-x-001", "achieved"))),
        ("2026-07-05", _doc(_o("outcome-x-001", "active"))),
        ("2026-07-09", _doc(_o("outcome-x-001", "achieved"))),
    ]
    lanes = wpc.fold_port_calls(snaps)
    assert lanes["x"] == [{"date": "2026-07-01", "outcome_id": "outcome-x-001"}]


def test_multi_lane_grouping_and_sort():
    snaps = [
        ("2026-07-02", _doc(_o("outcome-bakery-003", "achieved"),
                            _o("outcome-newsletter-001", "achieved"))),
        ("2026-07-10", _doc(_o("outcome-bakery-003", "achieved"),
                            _o("outcome-newsletter-001", "achieved"),
                            _o("outcome-bakery-001", "achieved"))),
    ]
    lanes = wpc.fold_port_calls(snaps)
    assert lanes["bakery"] == [
        {"date": "2026-07-02", "outcome_id": "outcome-bakery-003"},
        {"date": "2026-07-10", "outcome_id": "outcome-bakery-001"},
    ]
    assert lanes["newsletter"] == [{"date": "2026-07-02", "outcome_id": "outcome-newsletter-001"}]


def test_unattributable_lane_buckets_unknown():
    snaps = [("2026-07-02", _doc({"id": "weird-id", "status": "achieved"}))]
    assert "unknown" in wpc.fold_port_calls(snaps)


# ── artifact shape ──────────────────────────────────────────────────────────

def test_build_artifact_shape_and_counts():
    lanes = {
        "bakery": [{"date": "2026-07-02", "outcome_id": "outcome-bakery-003"}],
        "newsletter": [{"date": "2026-07-04", "outcome_id": "outcome-newsletter-001"}],
    }
    art = wpc.build_artifact(lanes, generated_at="2026-07-17T00:00:00+00:00",
                             source_git_head="deadbeef")
    assert art["schema"] == "cabinet.world.port-calls/v1"
    assert art["port_calls_total"] == 2
    assert art["last_port_call_date"] == "2026-07-04"
    assert list(art["lanes"]) == ["bakery", "newsletter"]  # sorted keys
    json.dumps(art)  # JSON-serializable


def test_build_artifact_empty_is_honest():
    art = wpc.build_artifact({}, generated_at="2026-07-17T00:00:00+00:00",
                             source_git_head=None)
    assert art["port_calls_total"] == 0
    assert art["last_port_call_date"] is None
    assert art["lanes"] == {}


# ── end-to-end against a THROWAWAY fixture git repo (hermetic, tmp_path) ────

def test_e2e_fixture_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "instance" / "config").mkdir(parents=True)
    env_git = ["git", "-C", str(repo)]

    def git(*args):
        subprocess.run(env_git + list(args), check=True, capture_output=True,
                       env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                            "PATH": "/usr/bin:/bin:/usr/local/bin",
                            "HOME": str(tmp_path)})

    git("init", "-q")
    out_yml = repo / "instance" / "config" / "outcomes.yml"
    out_yml.write_text(yaml.safe_dump(_doc(_o("outcome-demo-001", "active"))))
    git("add", "instance/config/outcomes.yml")
    git("commit", "-q", "-m", "c1")
    out_yml.write_text(yaml.safe_dump(_doc(_o("outcome-demo-001", "achieved"))))
    git("add", "instance/config/outcomes.yml")
    git("commit", "-q", "-m", "c2")

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), "--stdout"],
        capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    art = json.loads(proc.stdout)
    assert art["port_calls_total"] == 1
    assert art["lanes"]["demo"][0]["outcome_id"] == "outcome-demo-001"
    assert art["source_git_head"]
