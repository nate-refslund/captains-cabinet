"""judge-calibration scheduling lock (W2 / ledger row A2, D5 step 1a).

Grep-level, offline locks (yaml parse + render smoke; no launchctl, no
network) pinning the 2026-07-09 arming of com.cabinet.judge-calibration:

  * cabinet/services.yml carries an ENABLED judge-calibration cron row that
    runs the existing offline CLI (cabinet/scripts/judge-calibration.py) on a
    daily calendar — the proof it maintains has a 14-day max-age, so any
    cadence sparser than a few days can never keep it fresh;
  * the row renders through generate-plists.py (the INSTALL SOURCE pipeline)
    into a lintable plist dict — a manifest row that cannot render is exactly
    the never-rendered retro-trigger failure mode this manifest documents;
  * the stale "NOT armed here: judge-calibration" comment is gone (the
    docs-track-code rule: the manifest must not claim the row is future work).

Run: python3 -m pytest cabinet/scripts/tests/test_judge_calibration_scheduling.py -q
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
SERVICES_YML = _REPO_ROOT / "cabinet/services.yml"
CLI = _SCRIPTS_DIR / "judge-calibration.py"


def _load_services() -> list[dict]:
    data = yaml.safe_load(SERVICES_YML.read_text())
    assert isinstance(data.get("services"), list), "services.yml: no services list"
    return data["services"]


def _row() -> dict:
    rows = [s for s in _load_services() if s.get("name") == "judge-calibration"]
    assert rows, (
        "cabinet/services.yml lost the judge-calibration row — D5 step 1a "
        "(ledger A2) is unscheduled again and the 14-day calibration clock stops"
    )
    assert len(rows) == 1, "duplicate judge-calibration rows"
    return rows[0]


def test_row_is_enabled_cron_on_daily_calendar() -> None:
    svc = _row()
    assert svc.get("label") == "com.cabinet.judge-calibration"
    assert svc.get("kind") == "cron"
    assert not svc.get("disabled"), "judge-calibration row is disabled — not armed"
    sched = svc.get("schedule")
    assert isinstance(sched, dict) and "calendar" in sched, (
        f"expected a daily calendar schedule, got {sched!r}"
    )
    for entry in sched["calendar"]:
        assert "day" not in entry and "weekday" not in entry, (
            "judge-calibration must run DAILY: the status proof expires after "
            "14 days, so weekly/monthly rows let judge_verdicts_may_demote() "
            f"flap on staleness alone (got calendar entry {entry!r})"
        )


def test_row_runs_the_existing_offline_cli() -> None:
    svc = _row()
    assert "cabinet/scripts/judge-calibration.py" in svc["command"]
    assert CLI.exists(), "the CLI the row schedules does not exist"
    # The CLI's own header contract: offline + deterministic. Pin the two
    # phrases so a future rewrite that adds network/LLM calls has to face
    # this lock (and the manifest row's no-credentials claim) consciously.
    head = CLI.read_text()[:2500]
    assert "OFFLINE" in head and "NO LLM" in head


def test_row_renders_through_generate_plists() -> None:
    spec = importlib.util.spec_from_file_location(
        "generate_plists", _SCRIPTS_DIR / "generate-plists.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    pl = mod.render(_row(), Path("/repo"), Path("/home/x"))
    assert pl["Label"] == "com.cabinet.judge-calibration"
    assert "StartCalendarInterval" in pl
    assert any(
        "judge-calibration.py" in a for a in pl["ProgramArguments"]
    ), pl["ProgramArguments"]


def test_stale_future_b5_comment_is_gone() -> None:
    text = SERVICES_YML.read_text()
    assert "NOT armed here: judge-calibration" not in text, (
        "services.yml still claims judge-calibration is unarmed future-B5 work"
    )
