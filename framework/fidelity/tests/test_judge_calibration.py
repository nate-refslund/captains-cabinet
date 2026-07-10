"""Tests — framework/fidelity/judge_calibration.py (flywheel step 3).

The precondition under test: verdict_judge rows may count toward demotion
ONLY behind a fresh >=80%-agreement proof over >=MIN_PAIRS human/judge pairs.
Every failure mode (missing/corrupt/stale/insufficient/below-bar/tampered
proof) must read as flag CLOSED — fail-closed, no error path grants power.

Ledger-reading tests point CABINET_EVENT_LOG_DIR at a per-test tmp dir
(monkeypatch) on top of the repo-root session fence; the live ledger is never
touched.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from framework.fidelity.judge_calibration import (
    DEFAULT_SINCE,
    JUDGE_HARD_BAR,
    MIN_PAIRS,
    STATUS_MAX_AGE_DAYS,
    calibration_status,
    collect_pairs,
    compute_agreement,
    iter_raw_rows,
    judge_verdicts_may_demote,
    status_path,
    write_status,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI = REPO_ROOT / "cabinet" / "scripts" / "judge-calibration.py"

NOW = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# row builders
# ---------------------------------------------------------------------------

def _vrow(subject, verdict, source, ts, action="fidelity-case-scored", sim=False):
    row = {
        "ts": ts,
        "actor": {"kind": "officer", "id": "officer:cos"},
        "lane": "bakery",
        "action": action,
        "subject": subject,
        "refs": [subject],
        "review": {"verdict": verdict, "source": source},
    }
    if sim:
        row["sim"] = True
    return row


def _human(subject, verdict, ts="2026-06-20T10:00:00Z"):
    return _vrow(subject, verdict, "verdict_human", ts, action="action-card")


def _judge(subject, verdict, ts="2026-06-21T10:00:00Z"):
    return _vrow(subject, verdict, "verdict_judge", ts)


# ---------------------------------------------------------------------------
# pairing
# ---------------------------------------------------------------------------

def test_pairs_cross_identity_same_subject():
    rows = [_human("c1", "confirmed"), _judge("c1", "confirmed"),
            _human("c2", "wrong"), _judge("c2", "confirmed")]
    pairs = collect_pairs(rows=rows)
    assert [(p["subject"], p["agree"]) for p in pairs] == [("c1", True),
                                                           ("c2", False)]


def test_pairs_same_identity_supersede_history():
    # RAW read requirement: a judge verdict later superseded by a human verdict
    # on the SAME identity tuple is a legitimate pair (dedup would erase it).
    ident = dict(ts="2026-06-20T10:00:00Z", subject="c-super")
    judge_first = _vrow(ident["subject"], "wrong", "verdict_judge", ident["ts"],
                        action="acted-card")
    human_later = _vrow(ident["subject"], "confirmed", "verdict_human", ident["ts"],
                        action="acted-card")
    pairs = collect_pairs(rows=[judge_first, human_later])
    assert len(pairs) == 1
    assert pairs[0]["agree"] is False  # judge said wrong, human said confirmed


def test_latest_verdict_per_side_wins():
    rows = [
        _judge("c1", "wrong", ts="2026-06-21T10:00:00Z"),
        _judge("c1", "confirmed", ts="2026-06-22T10:00:00Z"),  # judge's final
        _human("c1", "confirmed", ts="2026-06-20T10:00:00Z"),
        _human("c1", "wrong", ts="2026-06-23T10:00:00Z"),      # human's final
    ]
    pairs = collect_pairs(rows=rows)
    assert pairs[0]["judge"] == "confirmed"
    assert pairs[0]["human"] == "wrong"
    assert pairs[0]["agree"] is False


def test_unknown_and_unattributed_verdicts_score_neither_side():
    rows = [
        _vrow("c1", "unknown", "verdict_human", "2026-06-20T10:00:00Z"),
        _vrow("c1", "confirmed", "verdict_judge", "2026-06-21T10:00:00Z"),
        _vrow("c2", "wrong", None, "2026-06-20T10:00:00Z"),        # no source
        _vrow("c2", "wrong", "verdict_judge", "2026-06-21T10:00:00Z"),
        _vrow("c3", "confirmed", "system", "2026-06-20T10:00:00Z"),
        _vrow("c3", "confirmed", "verdict_judge", "2026-06-21T10:00:00Z"),
    ]
    assert collect_pairs(rows=rows) == []


def test_window_filters_on_the_human_side_only():
    rows = [
        _human("c-in", "confirmed", ts="2026-06-15T10:00:00Z"),
        _judge("c-in", "confirmed", ts="2026-07-04T10:00:00Z"),  # judge late: OK
        _human("c-before", "confirmed", ts="2026-05-30T10:00:00Z"),  # pre-window
        _judge("c-before", "confirmed", ts="2026-06-02T10:00:00Z"),
        _human("c-after", "confirmed", ts="2026-07-02T10:00:00Z"),   # post-until
        _judge("c-after", "confirmed", ts="2026-07-02T11:00:00Z"),
    ]
    pairs = collect_pairs(rows=rows, since="2026-06-01", until="2026-07-01")
    assert [p["subject"] for p in pairs] == ["c-in"]


def test_sim_rows_are_dropped_by_the_raw_reader(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    rows = [_human("c1", "confirmed"),
            _vrow("c1", "confirmed", "verdict_judge",
                  "2026-06-21T10:00:00Z", sim=True)]
    with open(tmp_path / "consequence-events-2026-06-21.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
        f.write("junk line not json\n")  # never crashes the reader
    raw = iter_raw_rows()
    assert len(raw) == 1  # sim row + junk line both dropped
    assert collect_pairs(rows=raw) == []  # no judge side left -> no pair


def test_default_since_is_the_june_window():
    assert DEFAULT_SINCE == "2026-06-01"


# ---------------------------------------------------------------------------
# agreement math
# ---------------------------------------------------------------------------

def test_agreement_rate_and_confusion():
    pairs = collect_pairs(rows=[
        _human("a", "confirmed"), _judge("a", "confirmed"),   # hc_jc agree
        _human("b", "wrong"), _judge("b", "wrong"),           # hw_jw agree
        _human("c", "confirmed"), _judge("c", "wrong"),       # hc_jw disagree
        _human("d", "wrong"), _judge("d", "confirmed"),       # hw_jc disagree
    ])
    rep = compute_agreement(pairs)
    assert rep["pairs"] == 4
    assert rep["agreements"] == 2 and rep["disagreements"] == 2
    assert rep["agreement_rate"] == 0.5
    assert rep["confusion"] == {"hc_jc": 1, "hc_jw": 1, "hw_jc": 1, "hw_jw": 1}
    assert rep["bar_met"] is False


def test_zero_pairs_is_visible_none_not_zero():
    rep = compute_agreement([])
    assert rep["agreement_rate"] is None  # no-silent-caps: unmeasured is None
    assert rep["bar_met"] is False


def _pairs(n_agree, n_disagree):
    rows = []
    for i in range(n_agree):
        rows += [_human(f"a{i}", "confirmed"), _judge(f"a{i}", "confirmed")]
    for i in range(n_disagree):
        rows += [_human(f"d{i}", "wrong"), _judge(f"d{i}", "confirmed")]
    return collect_pairs(rows=rows)


def test_bar_met_at_exactly_80_percent_and_min_pairs():
    # 8/10 = 0.80 exactly -> the >= bar passes (task: ">=80%").
    rep = compute_agreement(_pairs(8, 2))
    assert rep["pairs"] == 10 and rep["agreement_rate"] == 0.8
    assert rep["bar_met"] is True
    # 7/10 < bar.
    assert compute_agreement(_pairs(7, 3))["bar_met"] is False
    # 100% agreement but BELOW the pair floor: not evidence.
    assert compute_agreement(_pairs(MIN_PAIRS - 1, 0))["bar_met"] is False


# ---------------------------------------------------------------------------
# the flag — fail-closed ladder
# ---------------------------------------------------------------------------

def test_flag_closed_when_no_status_file(tmp_path):
    p = tmp_path / "judge-calibration-status.json"
    assert judge_verdicts_may_demote(path=p, now=NOW) is False
    st = calibration_status(path=p, now=NOW)
    assert st["allowed"] is False and "no readable" in st["reason"]


def test_flag_open_only_on_fresh_passing_proof(tmp_path):
    p = tmp_path / "status.json"
    rep = compute_agreement(_pairs(9, 1))          # 0.9 over 10
    write_status(rep, since="2026-06-01", until=None, path=p, now=NOW)
    assert judge_verdicts_may_demote(path=p, now=NOW) is True
    st = calibration_status(path=p, now=NOW)
    assert st["allowed"] is True and "0.900" in st["reason"]


def test_flag_closed_on_below_bar_proof(tmp_path):
    p = tmp_path / "status.json"
    write_status(compute_agreement(_pairs(7, 3)), since=None, until=None,
                 path=p, now=NOW)
    assert judge_verdicts_may_demote(path=p, now=NOW) is False
    assert "below hard bar" in calibration_status(path=p, now=NOW)["reason"]


def test_flag_closed_on_insufficient_pairs(tmp_path):
    p = tmp_path / "status.json"
    write_status(compute_agreement(_pairs(5, 0)), since=None, until=None,
                 path=p, now=NOW)
    assert judge_verdicts_may_demote(path=p, now=NOW) is False
    assert "insufficient pairs" in calibration_status(path=p, now=NOW)["reason"]


def test_flag_closed_on_stale_proof(tmp_path):
    p = tmp_path / "status.json"
    old = NOW - timedelta(days=STATUS_MAX_AGE_DAYS + 1)
    write_status(compute_agreement(_pairs(10, 0)), since=None, until=None,
                 path=p, now=old)
    assert judge_verdicts_may_demote(path=p, now=NOW) is False
    assert "stale" in calibration_status(path=p, now=NOW)["reason"]


def test_flag_closed_on_future_dated_proof(tmp_path):
    p = tmp_path / "status.json"
    future = NOW + timedelta(days=2)
    write_status(compute_agreement(_pairs(10, 0)), since=None, until=None,
                 path=p, now=future)
    assert judge_verdicts_may_demote(path=p, now=NOW) is False
    assert "future" in calibration_status(path=p, now=NOW)["reason"]


def test_flag_closed_on_tampered_bar_met(tmp_path):
    # A hand-edited bar_met:true with failing numbers must NOT open the flag
    # (the reader re-derives from stored numbers — belt + braces).
    p = tmp_path / "status.json"
    write_status(compute_agreement(_pairs(7, 3)), since=None, until=None,
                 path=p, now=NOW)
    body = json.loads(p.read_text())
    body["bar_met"] = True                          # lie about the verdict
    p.write_text(json.dumps(body))
    assert judge_verdicts_may_demote(path=p, now=NOW) is False

    # And the inverse tamper: numbers pass but bar_met says false -> refuse
    # (writer/number disagreement is an integrity alarm, not a pass).
    write_status(compute_agreement(_pairs(10, 0)), since=None, until=None,
                 path=p, now=NOW)
    body = json.loads(p.read_text())
    body["bar_met"] = False
    p.write_text(json.dumps(body))
    assert judge_verdicts_may_demote(path=p, now=NOW) is False


@pytest.mark.parametrize("mutate", [
    lambda b: b.__setitem__("format", 99),
    lambda b: b.__setitem__("pairs", "ten"),
    lambda b: b.__setitem__("pairs", True),          # bool is not a count
    lambda b: b.__setitem__("agreement_rate", "high"),
    lambda b: b.__setitem__("agreement_rate", True),
    lambda b: b.__setitem__("computed_at", "not-a-time"),
    lambda b: b.pop("computed_at"),
])
def test_flag_closed_on_malformed_status(tmp_path, mutate):
    p = tmp_path / "status.json"
    write_status(compute_agreement(_pairs(10, 0)), since=None, until=None,
                 path=p, now=NOW)
    body = json.loads(p.read_text())
    mutate(body)
    p.write_text(json.dumps(body))
    assert judge_verdicts_may_demote(path=p, now=NOW) is False


def test_flag_closed_on_corrupt_json(tmp_path):
    p = tmp_path / "status.json"
    p.write_text("{ definitely not json")
    assert judge_verdicts_may_demote(path=p, now=NOW) is False


def test_status_path_follows_ledger_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path))
    assert status_path() == tmp_path / "judge-calibration-status.json"
    # And the basename can never collide with the ledger glob families.
    assert not status_path().name.startswith("consequence-events-")
    assert not status_path().name.startswith("events-")


# ---------------------------------------------------------------------------
# CLI smoke (subprocess, explicitly fenced env)
# ---------------------------------------------------------------------------

def _fenced_env(ledger_dir: Path) -> dict:
    env = dict(os.environ)
    env["CABINET_EVENT_LOG_DIR"] = str(ledger_dir)
    return env


def _write_ledger(ledger_dir: Path, rows) -> None:
    ledger_dir.mkdir(parents=True, exist_ok=True)
    with open(ledger_dir / "consequence-events-2026-06-21.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_cli_bar_met_exit_0_and_flag_opens(tmp_path):
    ledger = tmp_path / "events"
    rows = []
    for i in range(10):
        rows += [_human(f"c{i}", "confirmed"), _judge(f"c{i}", "confirmed")]
    _write_ledger(ledger, rows)

    proc = subprocess.run(
        [sys.executable, str(CLI), "--json"],
        env=_fenced_env(ledger), capture_output=True, text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["pairs"] == 10 and out["agreement_rate"] == 1.0
    assert out["bar_met"] is True
    assert out["judge_verdicts_may_demote"] is True
    status_file = ledger / "judge-calibration-status.json"
    assert status_file.exists()
    assert json.loads(status_file.read_text())["bar_met"] is True


def test_cli_insufficient_pairs_exit_1_flag_stays_closed(tmp_path):
    ledger = tmp_path / "events"
    _write_ledger(ledger, [_human("only", "confirmed"),
                           _judge("only", "confirmed")])
    proc = subprocess.run(
        [sys.executable, str(CLI), "--json"],
        env=_fenced_env(ledger), capture_output=True, text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["pairs"] == 1 and out["bar_met"] is False
    assert out["judge_verdicts_may_demote"] is False
    # The failing proof IS written (a fresh honest fail closes the flag).
    assert (ledger / "judge-calibration-status.json").exists()


def test_cli_no_write_leaves_no_status(tmp_path):
    ledger = tmp_path / "events"
    _write_ledger(ledger, [_human("only", "confirmed"),
                           _judge("only", "confirmed")])
    proc = subprocess.run(
        [sys.executable, str(CLI), "--json", "--no-write"],
        env=_fenced_env(ledger), capture_output=True, text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 1
    assert not (ledger / "judge-calibration-status.json").exists()
    assert json.loads(proc.stdout)["written"] is False


def test_cli_empty_ledger_exit_1_honest_unmeasured(tmp_path):
    ledger = tmp_path / "events"
    ledger.mkdir()
    proc = subprocess.run(
        [sys.executable, str(CLI), "--json"],
        env=_fenced_env(ledger), capture_output=True, text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 1
    out = json.loads(proc.stdout)
    assert out["pairs"] == 0 and out["agreement_rate"] is None
    assert out["judge_verdicts_may_demote"] is False
