"""The fresh-hatch egress blocker: a dry render demanded a live proxy.

WHY THIS MODULE EXISTS
======================
``hatch.sh`` step proof-c1 is ``start-officer-mac.sh cos --dry-run`` — billed
in the chain as "officer boot command assembly (zero side effects)". On EVERY
fresh hatch it died with::

    egress-guard: FAIL-CLOSED — runtime state directory is absent or symlinked
    [ERROR] start-officer-mac.sh: cannot resolve egress runtime state — refusing officer boot

The guard was RIGHT. The launcher was wrong, and in a specific, provable way:

* ``$STATE_DIR/egress`` is created by exactly one thing — ``egress-guard.sh
  apply`` (its ``acquire_apply_lock`` / ``install_enforce``).
* A dry render deliberately SKIPS ``apply`` (the ``elif [ "$CABINET_MAC_DRY_RUN"
  != "1" ]`` arm), because applying bootstraps a LaunchAgent and clean-room
  never touches launchd.
* It then called ``runtime-state``, which REQUIRES that directory — plus four
  owned regular files and a live, ready, port-matching proxy.

So the block demanded the postcondition of a step it had just chosen not to
run. Nothing in ``hatch.sh`` arms egress (the script contains zero occurrences
of the word), so the state dir never exists at proof-c1 on a fresh machine.

This is Mac-only. The Linux twin never had it: ``start-officer.sh:105`` gates
the whole block on ``[ "${CABINET_TEST_DRY_RUN:-0}" != "1" ]``.

WHAT THE FIX IS, AND WHAT IT IS DELIBERATELY NOT
================================================
The guard is untouched and a REAL boot still refuses (exit 78) — fail-closed
is correct and is not weakened here. Only the dry render tolerates unattested
state, exactly as the arm eight lines below it ALREADY did for the very next
egress precondition (enforced-but-proxy-env-absent).

It is deliberately NOT the Linux twin's shape. Skipping the whole block in
dry-run would blind a real sensor: ``docs/runbooks/observe-only-dogfood.md``
requires ``egress_enforced=1`` to still appear in DRY-RUN output after a
manual ``egress-guard.sh apply``, as the verification that enforcement took.
``test_dry_run_still_reports_enforced_when_attested`` below is that sensor's
regression guard — it is the arm that fails if someone "simplifies" this fix
into a blanket skip.

WHY NO EXISTING TEST CAUGHT IT
==============================
``cabinet/scripts/lib/tests/test_bash32_empty_array.py`` boots an officer in a
sandbox, but neutralises egress there with ``enforce: false`` under a comment
claiming "a hatch arms it before proof-c1 runs". It does not. That false
premise let the neutralisation stand in for provisioning nobody performed, and
the class stayed invisible. (CI could not see it either: every CI job is
ubuntu, and a stranger's egg ships ``enforce: true`` via the export's
``egress-default`` transform.)
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

BIN_BASH = "/bin/bash"
ROOT = Path(__file__).resolve().parents[3]
LAUNCHER_REL = "cabinet/scripts/start-officer-mac.sh"
GUARD_REL = "cabinet/scripts/egress-guard.sh"

# A stub guard is the only honest way to drive these arms: standing up a real
# proxy would test the proxy, and the property under test is what the LAUNCHER
# does with each guard outcome. `apply` always succeeds (the dry path never
# calls it anyway); `runtime-state` is what each arm varies.
_STUB_FAILING = """#!/bin/bash
case "${1:-}" in
  apply) exit 0 ;;
  runtime-state)
    echo "egress-guard: FAIL-CLOSED — runtime state directory is absent or symlinked" >&2
    exit 1 ;;
  *) exit 0 ;;
esac
"""

_STUB_ATTESTED = """#!/bin/bash
case "${1:-}" in
  apply) exit 0 ;;
  runtime-state) printf '1\\t%s\\n' "$CABINET_TEST_ENV_FILE" ; exit 0 ;;
  *) exit 0 ;;
esac
"""


def _tree_files(root: Path) -> list[Path]:
    """Tracked files when this is a checkout; the whole walk in a gitless egg."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                             capture_output=True, text=True, check=True).stdout
        names = [n for n in out.split("\0") if n]
        if names:
            return [root / n for n in names if (root / n).is_file()]
    except (OSError, subprocess.CalledProcessError):
        pass
    return [p for p in root.rglob("*") if p.is_file() and ".git/" not in p.as_posix()]


def _sandbox(tmp_path: Path, stub: str) -> Path:
    sandbox = tmp_path / "repo"
    for src in _tree_files(ROOT):
        dst = sandbox / src.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    guard = sandbox / GUARD_REL
    guard.parent.mkdir(parents=True, exist_ok=True)
    guard.write_text(stub, encoding="utf-8")
    guard.chmod(0o755)
    return sandbox


def _run(sandbox: Path, scratch: Path, *, dry: bool, extra_env=None):
    home = scratch / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "LANG": "en_US.UTF-8",
        "TMPDIR": str(scratch),
        "PYTHONDONTWRITEBYTECODE": "1",
        "CABINET_ROOT": str(sandbox),
        "CABINET_SOURCE_REPO": str(sandbox),
    }
    env.update(extra_env or {})
    argv = [BIN_BASH, str(sandbox / LAUNCHER_REL), "cos"]
    if dry:
        argv.append("--dry-run")
    return subprocess.run(argv, text=True, capture_output=True, check=False,
                          env=env, cwd=str(sandbox))


@pytest.fixture(autouse=True)
def _needs_tools():
    if not os.path.exists(BIN_BASH):
        pytest.skip(f"no {BIN_BASH} on this host")
    for tool in ("python3.12", "jq"):
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} not on PATH — officer boot assembly needs it")


def test_dry_run_tolerates_unattested_egress(tmp_path):
    """proof-c1 on a fresh machine: no proxy has ever been applied."""
    sandbox = _sandbox(tmp_path, _STUB_FAILING)
    r = _run(sandbox, tmp_path / "scratch", dry=True)
    assert r.returncode != 78, (
        "the dry render still refuses on unattested egress — proof-c1 cannot "
        f"pass on a fresh hatch.\nstderr:\n{r.stderr}")
    assert r.returncode == 0, f"dry render failed: rc={r.returncode}\n{r.stderr}"
    # Honest, never silent, and never a reassuring fake 1.
    assert "egress runtime state unattested" in r.stderr
    assert "egress_enforced=0" in r.stdout


def test_real_boot_still_refuses_unattested_egress(tmp_path):
    """The guard's fail-closed is NOT weakened: a real boot still refuses."""
    sandbox = _sandbox(tmp_path, _STUB_FAILING)
    r = _run(sandbox, tmp_path / "scratch", dry=False)
    assert r.returncode == 78, (
        "a REAL officer boot must still refuse when egress runtime state "
        f"cannot be resolved — got rc={r.returncode}\n{r.stderr}")
    assert "cannot resolve egress runtime state" in r.stderr
    assert "refusing officer boot" in r.stderr


def test_dry_run_still_reports_enforced_when_attested(tmp_path):
    """THE ANTI-SHORTCUT ARM.

    When enforcement really is live, the dry render must STILL report
    ``egress_enforced=1`` — that line is the dogfood runbook's verification
    that a manual ``apply`` took effect. Copying the Linux twin's blanket
    ``&& [ dry != 1 ]`` skip would make this arm fail, which is the point.
    """
    sandbox = _sandbox(tmp_path, _STUB_ATTESTED)
    scratch = tmp_path / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    env_file = scratch / "proxy.env"
    env_file.write_text("HTTPS_PROXY=http://127.0.0.1:39999\n", encoding="utf-8")
    r = _run(sandbox, scratch, dry=True,
             extra_env={"CABINET_TEST_ENV_FILE": str(env_file)})
    assert r.returncode == 0, f"rc={r.returncode}\n{r.stderr}"
    assert "egress_enforced=1" in r.stdout, (
        "the dry render stopped reporting live enforcement — the dogfood "
        f"sensor is blind.\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}")
