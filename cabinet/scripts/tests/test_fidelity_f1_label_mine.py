"""F1 label-mine scheduling lock (W3 / §4.3-5, 2026-07-09).

Grep-level, offline locks (yaml parse + render smoke; no launchctl, no
network) pinning the reframe of the F1 fidelity batch from monthly cost
canary to WEEKLY LABEL MINE:

  * cabinet/services.yml carries the fidelity-f1 cron row on a WEEKLY
    (weekday) calendar with the Captain-authorized D1 knobs ON in the row env
    (F1_WITH_INTENT=1, F1_EMIT_SCORED=1, F1_GATHER=1) and an explicit
    F1_ROLES roster;
  * the row still renders through generate-plists.py (INSTALL SOURCE);
  * the stale "MONTHLY because a batch is expensive" cost-canary framing is
    gone from the wrapper (docs-track-code rule);
  * labels stay calibration INPUT — nothing here touches graduation/CG-10.

Run: python3 -m pytest cabinet/scripts/tests/test_fidelity_f1_label_mine.py -q
"""

from __future__ import annotations

import importlib.util
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
SERVICES_YML = _REPO_ROOT / "cabinet/services.yml"
WRAPPER = _SCRIPTS_DIR / "run-fidelity-f1.sh"
PLIST = _REPO_ROOT / "cabinet/launchd/com.cabinet.fidelity-f1.plist"


def _row() -> dict:
    data = yaml.safe_load(SERVICES_YML.read_text())
    rows = [s for s in data["services"] if s.get("name") == "fidelity-f1"]
    assert len(rows) == 1, "expected exactly one fidelity-f1 row"
    return rows[0]


def test_row_is_weekly_with_label_mine_knobs() -> None:
    svc = _row()
    assert svc.get("label") == "com.cabinet.fidelity-f1"
    assert svc.get("kind") == "cron"
    cal = svc["schedule"]["calendar"]
    assert len(cal) == 1
    entry = cal[0]
    assert "weekday" in entry, (
        "fidelity-f1 fell back to a monthly day-N calendar — the label mine "
        "is starved again (W3/§4.3-5 reframe 2026-07-09)")
    assert "day" not in entry
    env = svc.get("env") or {}
    assert env.get("F1_WITH_INTENT") == "1", "D1 knob with_intent OFF in manifest"
    assert env.get("F1_EMIT_SCORED") == "1", "D1 knob emit_scored OFF in manifest"
    assert env.get("F1_GATHER") == "1", (
        "scheduled F1 is context-starved — gather-first behavior is not tested")
    assert env.get("F1_ROLES"), "no lane roster — F1_ROLES must be explicit"


def test_row_renders_through_generate_plists() -> None:
    spec = importlib.util.spec_from_file_location(
        "generate_plists", _SCRIPTS_DIR / "generate-plists.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rendered = mod.render(_row(), _REPO_ROOT, Path.home())
    cal = rendered["StartCalendarInterval"]
    entries = cal if isinstance(cal, list) else [cal]
    assert any("Weekday" in e for e in entries), (
        "weekly schedule did not render to launchd Weekday")
    assert all("Day" not in e for e in entries)
    env = rendered.get("EnvironmentVariables", {})
    for knob in ("F1_WITH_INTENT", "F1_EMIT_SCORED", "F1_GATHER"):
        assert env.get(knob) == "1", (
            f"row env knob {knob} missing from the rendered plist — what "
            "launchd runs must be manifest-visible")


def test_wrapper_lost_the_cost_canary_framing() -> None:
    text = WRAPPER.read_text()
    # the original live claim (verbatim per §4.3-5) must be gone; the
    # historical `(was: "MONTHLY because ...")` note is allowed to remain
    assert "# MONTHLY because a batch is expensive (n" not in text, (
        "§4.3-5: the cost-canary framing is back — the wrapper must describe "
        "the weekly label mine")
    assert "WEEKLY, KNOBS ON" in text
    assert "F1_ROLES" in text, "wrapper lost the multi-lane roster knob"
    assert 'F1_WITH_INTENT="${F1_WITH_INTENT:-1}"' in text, (
        "wrapper default for with_intent flipped off")
    assert 'F1_EMIT_SCORED="${F1_EMIT_SCORED:-1}"' in text, (
        "wrapper default for emit_scored flipped off")
    assert 'F1_GATHER="${F1_GATHER:-1}"' in text, (
        "wrapper default fell back to the context-starved arm")
    assert "F1_EMIT_SCORED=0" in text, (
        "context-starved diagnostics may bank indistinguishable labels")


def _wrapper_harness(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, str]]:
    root = tmp_path / "repo"
    scripts = root / "cabinet/scripts"
    (scripts / "lib").mkdir(parents=True)
    wrapper = scripts / WRAPPER.name
    shutil.copy2(WRAPPER, wrapper)
    shutil.copy2(_SCRIPTS_DIR / "lib/personal-env.sh",
                 scripts / "lib/personal-env.sh")
    capture = tmp_path / "env.txt"
    fake_python = tmp_path / "python"
    fake_python.write_text(
        "#!/bin/bash\n"
        "printf '%s|%s|%s|%s\\n' \"$F1_GATHER\" \"$F1_WITH_INTENT\" "
        "\"$F1_EMIT_SCORED\" \"$*\" > \"$F1_TEST_CAPTURE\"\n"
    )
    fake_python.chmod(0o755)
    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ["PATH"],
        "CABINET_PYTHON": str(fake_python),
        "CABINET_SHARED_ENV": str(tmp_path / "absent.env"),
        "F1_ROLES": "cos",
        "F1_CASES": "1",
        "F1_TEST_CAPTURE": str(capture),
    }
    return root, wrapper, capture, env


@pytest.mark.parametrize(
    ("gather", "emit_scored", "expected_gather", "expected_emit"),
    [(None, None, "1", "1"), ("0", "0", "0", "0")],
)
def test_wrapper_runtime_gather_contract(
        tmp_path: Path, gather: str | None, emit_scored: str | None,
        expected_gather: str, expected_emit: str) -> None:
    """Default is gather-first; 0/0 is the explicit safe diagnostic."""
    root, wrapper, capture, env = _wrapper_harness(tmp_path)
    if gather is not None:
        env["F1_GATHER"] = gather
    if emit_scored is not None:
        env["F1_EMIT_SCORED"] = emit_scored
    result = subprocess.run(
        ["bash", str(wrapper)], cwd=root, env=env,
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert capture.read_text().strip() == (
        f"{expected_gather}|1|{expected_emit}|framework/fidelity/run_f1.py cos 1")
    assert f"gather={expected_gather}" in result.stdout


def test_wrapper_refuses_starved_scored_run_before_python(tmp_path: Path) -> None:
    root, wrapper, capture, env = _wrapper_harness(tmp_path)
    env["F1_GATHER"] = "0"
    result = subprocess.run(
        ["bash", str(wrapper)], cwd=root, env=env,
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 64
    assert not capture.exists(), "invalid combination still launched Python"
    assert "refusing context-starved scored run" in result.stderr


def test_checked_in_plist_matches_weekly_label_mine() -> None:
    payload = plistlib.loads(PLIST.read_bytes())
    calendar = payload["StartCalendarInterval"]
    assert "Weekday" in calendar
    assert "Day" not in calendar, "checked-in plist still monthly"
    env = payload["EnvironmentVariables"]
    for knob in ("F1_ROLES", "F1_WITH_INTENT", "F1_EMIT_SCORED", "F1_GATHER"):
        expected = "cos" if knob == "F1_ROLES" else "1"
        assert env.get(knob) == expected, (
            f"checked-in plist has wrong env value for {knob}")
