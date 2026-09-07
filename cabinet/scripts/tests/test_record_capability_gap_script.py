"""The officer-facing gap recorder says what will actually happen next.

`record-capability-gap.sh` prints a one-line "what happens now" after
recording. Before the structural kinds existed its `else` branch was true by
exhaustion — every non-procedure kind was proposed to the Captain. Widening
`VALID_KINDS` (contract §3) made that branch a LIE for `skill`, `authority`
and `information`, which are surface-only and are proposed to nobody. An
officer acting on that line would wait for an approval that is never coming.

The script is also the one place a human picks the kind, and it runs under the
deployment box's bare `python3` (3.9) — so this doubles as the A0.3 arm for
the module on that path.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / "cabinet" / "scripts" / "record-capability-gap.sh"


def _run(need: str, kind: str, tmp_path: Path) -> str:
    env = os.environ.copy()
    env["CABINET_ROOT"] = str(_REPO)
    env["CABINET_EVENT_LOG_DIR"] = str(tmp_path / "events")
    env["CABINET_FRAMEWORK_STORE_MIRROR"] = "0"
    env["CABINET_PRODUCT_SLUG"] = "testprod"
    env["OFFICER_NAME"] = "tester"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("DATABASE_URL", None)
    cp = subprocess.run(["bash", str(_SCRIPT), "--need", need, "--kind", kind],
                        env=env, capture_output=True, text=True, timeout=120)
    assert cp.returncode == 0, cp.stderr
    return cp.stdout


@pytest.mark.parametrize("kind", ["skill", "authority", "information"])
def test_structural_kind_is_not_announced_as_a_proposal(kind, tmp_path):
    out = _run("no holder on the roster for task-001 of outcome-a", kind, tmp_path)
    assert "[%s]" % kind in out, out
    assert "surface-only" in out, out
    assert "propose" not in out, out
    assert "Captain" not in out, out


@pytest.mark.parametrize("kind", ["tool", "integration"])
def test_actionable_kind_still_announces_the_captain_proposal(kind, tmp_path):
    out = _run("query an external endpoint for the quarterly numbers", kind, tmp_path)
    assert "propose a fix to the Captain" in out, out
    assert "surface-only" not in out, out


def test_procedure_still_announces_the_auto_skill_lane(tmp_path):
    out = _run("the standard workflow for refining a task", "procedure", tmp_path)
    assert "auto-skill" in out, out


def test_the_script_runs_under_the_box_python3_not_the_suite_interpreter(tmp_path):
    """A0.3 arm on this path: the script execs bare `python3`, so the module it
    imports must be correct under whatever that resolves to — 3.9 on the
    deployment box, and never assumed to be the interpreter pytest runs on."""
    box = subprocess.run(["python3", "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                         capture_output=True, text=True, timeout=60)
    assert box.returncode == 0, box.stderr
    box_version = box.stdout.strip()
    out = _run("no holder on the roster for task-002 of outcome-a", "skill", tmp_path)
    assert "surface-only" in out, out
    # Recorded, not merely printed — and recorded by the interpreter the script
    # chose, which is the point of the arm.
    assert "capability gap recorded:" in out, out
    assert box_version != "" and sys.version_info[:2] >= (3, 9)
