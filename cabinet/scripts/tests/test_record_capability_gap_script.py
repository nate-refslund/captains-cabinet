"""The officer-facing gap recorder says what will actually happen next.

`record-capability-gap.sh` prints a one-line "what happens now" after
recording. Before the structural kinds existed its `else` branch was true by
exhaustion — every non-procedure kind was proposed to the Captain. Widening
`VALID_KINDS` (contract §3) made that branch a LIE for `skill`, `authority`
and `information`, which are surface-only and are proposed to nobody. An
officer acting on that line would wait for an approval that is never coming.

The script is also the one place a human picks the kind, so this file carries
both A0.3 arms for the recorder path, separated: the script PINS
`${CABINET_PYTHON:-python3.12}` (it is unlocked), and the module it imports is
still exercised LIVE under the box's bare `python3` — 3.9.6 here and on the
deployment box — because the schg-locked hook, which cannot be pinned, imports
the same module.
"""

from __future__ import annotations

import os
import re
import subprocess
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


def test_the_script_pins_the_interpreter_it_execs(tmp_path):
    """A0.3, unlocked half: this script is not schg-locked, so it pins.

    It USED to exec a bare `python3`, and this file's A0.3 arm rode on that —
    the live-3.9 proof below was a side effect of the script's interpreter
    choice rather than a property anyone asserted. That coupling is the defect
    it sounds like: pinning the script (correct under A0.3) would have silently
    turned the 3.9 arm into a 3.12 arm and left the suite green. The two are
    separated here — this arm owns the pin, the next owns 3.9.
    """
    source = _SCRIPT.read_text()
    assert "${CABINET_PYTHON:-python3.12}" in source, source[:400]
    # ...and no bare token survives anywhere outside a whole-line comment.
    code = "\n".join("" if ln.lstrip().startswith("#") else ln
                     for ln in source.split("\n"))
    bare = [n for n, ln in enumerate(code.split("\n"), 1)
            if re.search(r"(?<![\w.])python3(?![\w.\-])", ln)]
    assert bare == [], "bare `python3` still on lines %s" % bare
    # The pin is not decoration: the script still records through it.
    out = _run("no holder on the roster for task-002 of outcome-a", "skill", tmp_path)
    assert "capability gap recorded:" in out, out


def test_the_module_records_under_the_box_bare_python3(tmp_path):
    """A0.3, locked half, LIVE — not an AST proxy.

    The schg-locked hook execs whatever `python3` resolves to (3.9.6 on the
    deployment box, contract "Measured on the Captain's box"), and it can
    import this module. So the module is exercised here under that exact
    interpreter — importing it, recording a keyed structural gap, and reading
    the row back — rather than only parsed with `feature_version=(3, 9)`,
    which cannot see an evaluated 3.10 union or a 3.10 stdlib call.

    SKIPs only if the box has no `python3` at all; a 3.12-or-newer `python3`
    is reported in the failure text rather than silently accepted, because a
    green arm on 3.12 here would be testing the wrong interpreter.
    """
    probe = subprocess.run(
        ["python3", "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
        capture_output=True, text=True, timeout=60)
    if probe.returncode != 0:
        pytest.skip("no `python3` on PATH: %s" % probe.stderr.strip())
    box_version = tuple(int(p) for p in probe.stdout.strip().split("."))

    env = os.environ.copy()
    env["CABINET_EVENT_LOG_DIR"] = str(tmp_path / "events")
    env["CABINET_FRAMEWORK_STORE_MIRROR"] = "0"
    env["CABINET_PRODUCT_SLUG"] = "testprod"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(_REPO)
    env.pop("DATABASE_URL", None)
    program = (
        "from framework.learning.capability_gaps import "
        "record_gap, project_gaps, gap_id_for_key, STRUCTURAL_KINDS;"
        "g = record_gap('no holder on the roster for task-003 of outcome-a',"
        " kind='skill', recorded_by='supervisor',"
        " dedup_key='holder:outcome-a:task-003');"
        "rows = project_gaps(product_slug='testprod');"
        "print(g['gap_id'], g['kind'], len(rows),"
        " gap_id_for_key('holder:outcome-a:task-003'),"
        " 'skill' in STRUCTURAL_KINDS)"
    )
    cp = subprocess.run(["python3", "-c", program], env=env,
                        capture_output=True, text=True, timeout=180)
    assert cp.returncode == 0, "python%d.%d could not run the widened module:\n%s" % (
        box_version[0], box_version[1], cp.stderr)
    gap_id, kind, rows, keyed_id, structural = cp.stdout.split()
    assert kind == "skill" and rows == "1" and structural == "True", cp.stdout
    assert gap_id == keyed_id, "the keyed id is not the recorded id: %s" % cp.stdout
    assert box_version >= (3, 9), box_version
