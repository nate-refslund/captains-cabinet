"""cabinet/scripts/card-flatline-probe.py — the FLEET half of the alarm.

The probe and the Captain-facing line read the same verdict under deliberately
different rules: the line is asked once per silent episode, the probe reports
for as long as the channel is dark. These arms pin that split (a probe that
went quiet with the line would leave the doctor blind to a standing outage),
the doctor's own case block, and the degenerate ends — a missing series file
must print a token and exit 0, never crash and never alarm.

No DB, no network, no Redis: the probe is invoked as a subprocess against
fixture files under tmp_path.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PROBE = ROOT / "cabinet" / "scripts" / "card-flatline-probe.py"
DOCTOR = ROOT / "cabinet" / "scripts" / "cabinet-doctor.sh"

# TIME IS AN INPUT. The probe runs in a subprocess against the REAL clock, so
# every fixture date is seeded relative to today — a hardcoded series is a
# calendar bomb that reads healthy this week and STALE next week.
TODAY = dt.datetime.now(dt.timezone.utc).date()


def _day(offset):
    """ISO date `offset` days back from today (0 = today)."""
    return (TODAY - dt.timedelta(days=offset)).isoformat()


def _row(date, cards, *, stamped=1000, acted=3):
    return {"date": date, "proactive_cards_7d": cards, "acted_7d": acted,
            "approved_7d": 0, "reversal_rate_7d": None,
            "stamped_rows_total": stamped, "cells_accumulating": 4,
            "cells_graduated": 1,
            "labels_7d": {"verdict": 2, "outcome_resolved": 0}}


def _live_then_silent(days_silent, *, first_live=None):
    """A live day, then `days_silent` consecutive zero days ending TODAY.
    stamped_rows_total advances so the org reads ACTIVE throughout."""
    first_live = first_live if first_live is not None else days_silent
    rows = [_row(_day(first_live), 20, stamped=1000)]
    for i in range(days_silent - 1, -1, -1):
        rows.append(_row(_day(i), 0, stamped=1000 + (days_silent - i)))
    return rows


def _series_file(tmp_path, rows):
    p = tmp_path / "falsifier-series.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def _run(*args):
    return subprocess.run([sys.executable, str(PROBE), *args],
                          capture_output=True, text=True, cwd=str(ROOT),
                          timeout=120)


def test_probe_prints_one_token_line_and_never_exits_nonzero(tmp_path):
    """A probe that exits non-zero turns a quality finding into a fleet-dead
    verdict — the doctor reads the TOKEN, never the exit code."""
    p = _series_file(tmp_path, _live_then_silent(3))
    r = _run("--probe", "--series", str(p))
    assert r.returncode == 0, r.stderr
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert lines[0].startswith(f"BREACH since={_day(2)}")


def test_probe_on_a_missing_series_is_measured_absence(tmp_path):
    r = _run("--probe", "--series", str(tmp_path / "nothing-here.jsonl"))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "NOSERIES"


def test_probe_on_a_corrupt_line_keeps_the_good_history(tmp_path):
    p = tmp_path / "falsifier-series.jsonl"
    p.write_text(json.dumps(_row(_day(1), 20)) + "\n"
                 + "{not json at all\n"
                 + json.dumps(_row(_day(0), 14)) + "\n", encoding="utf-8")
    r = _run("--probe", "--series", str(p), "--json")
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines()[0].startswith("OK cards_7d=14")


def test_probe_reports_a_standing_breach_after_the_question_was_asked(tmp_path):
    """The whole reason the fleet half exists: the Captain-facing line is
    once-per-episode, so a probe that mirrored it would go green while the
    channel was still dead."""
    p = _series_file(tmp_path, _live_then_silent(7))
    r = _run("--probe", "--series", str(p), "--json")
    assert r.returncode == 0, r.stderr
    token, payload = r.stdout.splitlines()[0], json.loads(r.stdout.splitlines()[1])
    assert token.startswith(f"BREACH since={_day(6)}")
    assert "announced=0" in token          # the question was asked days ago
    assert payload["announce"] is False and payload["state"] == "flatline"


def test_default_mode_is_scriptable_and_shows_the_captain_line(tmp_path):
    p = _series_file(tmp_path, _live_then_silent(3))
    r = _run("--series", str(p))
    assert r.returncode == 1                       # BREACH is scriptable
    assert "card-flatline: BREACH" in r.stdout
    # ...and on the crossing day it also shows the exact line the Captain gets.
    assert ("captain line (this run): the proactive-card channel has been "
            f"silent since {_day(2)} — deliberate?") in r.stdout
    r = _run("--series", str(tmp_path / "absent.jsonl"))
    assert r.returncode == 0
    assert "card-flatline: NOSERIES" in r.stdout


def test_probe_writes_nothing(tmp_path):
    """READ-ONLY by construction. A watchdog that mutates the thing it watches
    has no standing to report on it."""
    p = _series_file(tmp_path, _live_then_silent(3))
    before = {q.name: q.stat().st_mtime_ns for q in tmp_path.iterdir()}
    _run("--probe", "--series", str(p))
    after = {q.name: q.stat().st_mtime_ns for q in tmp_path.iterdir()}
    assert before == after


# ---------------------------------------------------------------------------
# the doctor case block — a probe with no caller is not a sensor
# ---------------------------------------------------------------------------

def _doctor_case() -> str:
    """The card-flatline ``case`` body ONLY — never the comment above it. A
    scan that includes the prose matches its own explanation and stops
    measuring the code (the sensor-tests-something-else failure class)."""
    body = DOCTOR.read_text(encoding="utf-8")
    assert "16. proactive-card CHANNEL FLATLINE" in body, \
        "the doctor lost its card-flatline check"
    assert 'case "$CFL_PROBE" in' in body, "the doctor lost the probe case block"
    return body.split('case "$CFL_PROBE" in', 1)[1].split("\nesac", 1)[0]


@pytest.mark.parametrize("token", ["OK", "NOSERIES", "NEVERACTIVE", "NOSYNC",
                                   "QUIET", "SILENT", "BREACH", "UNMEASURED",
                                   "STALE", "ERROR"])
def test_cabinet_doctor_handles_every_token_the_probe_can_print(token):
    """Every vocabulary word the probe emits has a case arm. A token with no
    arm falls through to the catch-all and reads as 'probe output
    unparseable' — a real signal rendered as a parse bug."""
    assert f"{token}*)" in _doctor_case()


def test_cabinet_doctor_calls_the_probe_and_never_deads_on_it():
    body = DOCTOR.read_text(encoding="utf-8")
    assert "cabinet/scripts/card-flatline-probe.py --probe" in body
    case = _doctor_case()
    # AMBER-max: a quiet captain channel is a quality finding, and a fresh
    # hatch (no series at all) must leave the doctor GREEN.
    assert "dead " not in case
    for green in ("NOSERIES*)", "NEVERACTIVE*)", "NOSYNC*)", "QUIET*)", "OK*)"):
        arm = case.split(green, 1)[1].split(";;", 1)[0]
        assert arm.strip().startswith("ok "), f"{green} must be a green arm"
    breach = case.split("BREACH*)", 1)[1].split(";;", 1)[0]
    assert breach.strip().startswith("warn ")
