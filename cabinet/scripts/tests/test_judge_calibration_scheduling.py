"""judge-calibration scheduling lock (W2 / ledger row A2, D5 step 1a).

Grep-level, offline locks (yaml parse + render smoke; no launchctl, no
network) pinning the 2026-07-09 arming of judge calibration.

RE-ANCHORED 2026-07-24 (COG-4 W6 landing; routed surgery
feat-cog4-w6-e2-cp1.md §6.7): the dedicated com.cabinet.judge-calibration
row was COMPOSED into the cog4-organ-runner wake vehicle (C4). The lock's
STATED INTENT — the 14-day proof stays fresh — now binds the composed
vehicle:

  * cabinet/services.yml carries an ENABLED cog4-organ-runner cron row on a
    fixed interval <= 172800s (actual 43200) that NAMES the judge organ
    manifest (§9.5 declared association); the manifest's entrypoint keeps
    the existing offline CLI (cabinet/scripts/judge-calibration.py — the
    OFFLINE / NO LLM head pins unchanged);
  * the RUNNER row renders through generate-plists.py (the INSTALL SOURCE
    pipeline) into a lintable plist dict — a manifest row that cannot render
    is exactly the never-rendered retro-trigger failure mode;
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
    """RE-ANCHORED to the composed vehicle (W6 landing 2026-07-24, §6.7):
    the runner row is the schedulable unit; it must NAME the judge organ
    manifest or the 14-day calibration clock stops."""
    rows = [s for s in _load_services() if s.get("name") == "cog4-organ-runner"]
    assert rows, (
        "cabinet/services.yml lost the cog4-organ-runner row — D5 step 1a "
        "(ledger A2) is unscheduled again and the 14-day calibration clock stops"
    )
    assert len(rows) == 1, "duplicate cog4-organ-runner rows"
    row = rows[0]
    assert "cabinet/config/organs/judge-calibration.yml" in (row.get("organs") or []), (
        "the composed wake vehicle no longer NAMES the judge-calibration organ "
        "manifest (§9.5 declared association) — the calibration clock stops"
    )
    return row


def test_row_is_enabled_cron_on_daily_calendar() -> None:
    svc = _row()
    assert svc.get("label") == "com.cabinet.cog4-organ-runner"
    assert svc.get("kind") == "cron"
    assert not svc.get("disabled"), "the composed runner row is disabled — not armed"
    sched = svc.get("schedule")
    assert isinstance(sched, dict) and isinstance(sched.get("interval_s"), int), (
        f"expected a fixed-interval schedule on the composed vehicle, got {sched!r}"
    )
    assert sched["interval_s"] <= 172800, (
        "the composed vehicle wakes sparser than every 2 days: the status "
        "proof expires after 14 days, so judge_verdicts_may_demote() would "
        f"flap on staleness alone (interval_s={sched['interval_s']})"
    )


def test_row_runs_the_existing_offline_cli() -> None:
    _row()  # the composed vehicle is armed and NAMES the judge manifest
    man = yaml.safe_load(
        (_REPO_ROOT / "cabinet/config/organs/judge-calibration.yml").read_text()
    )
    assert "cabinet/scripts/judge-calibration.py" in man["entrypoints"]["run"]
    assert CLI.exists(), "the CLI the organ manifest schedules does not exist"
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
    assert pl["Label"] == "com.cabinet.cog4-organ-runner"
    assert "StartInterval" in pl
    assert any(
        "cog4-organ-runner.py" in a for a in pl["ProgramArguments"]
    ), pl["ProgramArguments"]


def test_stale_future_b5_comment_is_gone() -> None:
    text = SERVICES_YML.read_text()
    assert "NOT armed here: judge-calibration" not in text, (
        "services.yml still claims judge-calibration is unarmed future-B5 work"
    )
