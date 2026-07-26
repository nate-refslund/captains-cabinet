"""Cron-CI wave (2026-07-26) — cabinet/cron/ must be inside the CI shell gates.

THE DEFECT THESE PIN: until 2026-07-26 the string ``cabinet/cron`` appeared
ZERO times in ``.github/workflows/cabinet-ci.yml``. All four ``bash -n`` globs
were rooted at ``cabinet/scripts`` (the find-based one is ``-mindepth 2`` under
that same root), and the shellcheck step listed hooks + lib + scripts-root
only. So the 15 scripts / ~1.8k lines under ``cabinet/cron`` — the Captain's
briefing path, the limit-reset watchdog, the self-improvement driver — were
never syntax-checked or statically analysed by any gate. A stray brace merged
green and only failed at 03:00 under launchd.

HOW THESE TESTS WORK — round-trip, not a token sweep. A grep for
``cabinet/cron`` in the workflow would prove only that a string is present, not
that the gate has teeth. Instead each test EXTRACTS the real ``run:`` body from
the workflow, retargets its ``/opt/founders-cabinet`` root at a sandbox that
mirrors the repo layout, and executes it:

  * against a faithful copy of cabinet/cron  → must pass, and must NAME every
    one of the 15 scripts in its output (non-vacuity: a glob that silently
    matches nothing also "passes");
  * against the same copy plus one deliberately-defective script → must FAIL.

The defect payloads are deliberately independent: an unterminated ``if`` is a
``bash -n`` parse error that shellcheck-severity-error does not gate on its
own, and ``local`` at top level is SC2168 (error severity) which ``bash -n``
accepts. So neither arm can pass on the other's behalf.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[3]
_WORKFLOW = _REPO / ".github" / "workflows" / "cabinet-ci.yml"
_CRON = _REPO / "cabinet" / "cron"
_SCRIPTS = _REPO / "cabinet" / "scripts"

# The path the workflow mounts the checkout at (a symlink created by the
# "Mount checkout at /opt/founders-cabinet" step). Every gate body below is
# written against it, so retargeting it is how we run them anywhere.
_CI_ROOT = "/opt/founders-cabinet"

_BROKEN_SYNTAX = "#!/bin/bash\nif true; then\n  echo unterminated\n"
_BROKEN_LINT = "#!/bin/bash\nlocal leaked=1\necho \"$leaked\"\n"


def _ci_steps() -> list[dict]:
    doc = yaml.safe_load(_WORKFLOW.read_text())
    return doc["jobs"]["ci"]["steps"]


def _bodies(name_prefix: str) -> list[str]:
    out = [s["run"] for s in _ci_steps()
           if str(s.get("name", "")).startswith(name_prefix) and "run" in s]
    assert out, f"no CI step named {name_prefix!r} carries a run: body"
    return out


def _sandbox(tmp_path: Path, extra: dict[str, str] | None = None) -> Path:
    """Mirror enough of the repo for the gate bodies to run, with cabinet/cron
    materialised as real files so a defect can be injected into it."""
    root = tmp_path / "root"
    (root / "cabinet" / "scripts").mkdir(parents=True)
    # hooks/ and lib/ as directory symlinks: the globs expand through them.
    for sub in ("hooks", "lib"):
        (root / "cabinet" / "scripts" / sub).symlink_to(_SCRIPTS / sub)
    for sh in sorted(_SCRIPTS.glob("*.sh")):
        (root / "cabinet" / "scripts" / sh.name).symlink_to(sh)
    shutil.copytree(_CRON, root / "cabinet" / "cron")
    for name, body in (extra or {}).items():
        (root / "cabinet" / "cron" / name).write_text(body)
    return root


def _run(body: str, root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", body.replace(_CI_ROOT, str(root))],
        capture_output=True, text=True, timeout=300)


def _cron_names() -> list[str]:
    names = sorted(p.name for p in _CRON.glob("*.sh"))
    assert names, "cabinet/cron/*.sh vanished — this gate has nothing to pin"
    return names


# --------------------------------------------------------------------------
# bash -n coverage
# --------------------------------------------------------------------------

def test_syntax_gate_visits_every_cron_script(tmp_path):
    """Non-vacuity: the gate must NAME each cron script, not merely exit 0."""
    root = _sandbox(tmp_path)
    seen = ""
    for body in _bodies("Bash syntax check"):
        res = _run(body, root)
        assert res.returncode == 0, (
            f"a syntax-check step failed on a clean tree:\n{res.stdout}\n{res.stderr}")
        seen += res.stdout
    missing = [n for n in _cron_names() if f"cabinet/cron/{n}" not in seen]
    assert not missing, (
        f"cabinet/cron scripts never reached any `bash -n` step: {missing}. "
        f"Every syntax glob is rooted at cabinet/scripts — that was the defect.")


def test_syntax_gate_fails_on_a_broken_cron_script(tmp_path):
    """Teeth: an unparseable script under cabinet/cron must turn the gate red."""
    root = _sandbox(tmp_path, {"zz-guard-unparseable.sh": _BROKEN_SYNTAX})
    rcs = [_run(body, root).returncode for body in _bodies("Bash syntax check")]
    assert any(rc != 0 for rc in rcs), (
        "an unterminated `if` under cabinet/cron passed every syntax step — "
        "the directory is outside the gate's globs")


# --------------------------------------------------------------------------
# shellcheck coverage
# --------------------------------------------------------------------------

def _shellcheck_body() -> str:
    bodies = _bodies("shellcheck")
    assert len(bodies) == 1, "expected exactly one shellcheck step"
    return bodies[0]


@pytest.mark.skipif(shutil.which("shellcheck") is None,
                    reason="shellcheck not installed (present on ubuntu-latest, "
                           "where the gate itself runs)")
def test_shellcheck_gate_is_clean_on_the_real_cron_scripts(tmp_path):
    res = _run(_shellcheck_body(), _sandbox(tmp_path))
    assert res.returncode == 0, (
        f"shellcheck --severity=error is red on the current tree:\n"
        f"{res.stdout}\n{res.stderr}")


@pytest.mark.skipif(shutil.which("shellcheck") is None,
                    reason="shellcheck not installed (present on ubuntu-latest, "
                           "where the gate itself runs)")
def test_shellcheck_gate_fails_on_a_defective_cron_script(tmp_path):
    """Teeth: SC2168 (error severity, and NOT a `bash -n` failure) must be
    caught, proving the shellcheck argument list reaches cabinet/cron."""
    root = _sandbox(tmp_path, {"zz-guard-sc2168.sh": _BROKEN_LINT})
    assert subprocess.run(["bash", "-n", str(root / "cabinet" / "cron"
                                             / "zz-guard-sc2168.sh")],
                          capture_output=True).returncode == 0, \
        "payload must be syntactically valid, else the arms are not independent"
    res = _run(_shellcheck_body(), root)
    assert res.returncode != 0, (
        "SC2168 under cabinet/cron passed the shellcheck step — the argument "
        "list does not reach that directory")
