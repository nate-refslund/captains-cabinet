"""Tests for the hatch.sh app-feel tail (Perfect Cabinet Wave D, 2026-07-10).

The tail is a CONVENIENCE step, never a gate: hatch.sh reaches EOF only on
the GREEN path (step_fail exits 1 earlier, --dry-run exits 0 at the plan
gate), and the tail must preserve that exit disposition no matter what fails
inside it (`app_feel || echo …` + per-branch `return 0`). These tests pin
that contract WITHOUT running the live chain (house style — the chain
mutates instance/, so full runs belong to clean-room verifiers in scratch
clones, not the shared tree):

  * --dry-run advertises the app-feel plan line and still executes nothing;
  * wiring pins — the clean-room guard is the function's FIRST branch (before
    any write or `open`), and the invocation carries the non-fatal fallback;
  * function-level branch drives — insertion C extracted by its literal
    start marker into a temp script and run under PATH shims (fake
    open/curl/plutil/sleep recording invocations, temp HOME): the
    --no-launchd hint drops no file; the webloc branch renders a valid plist
    with the 127.0.0.1 URL (idempotent overwrite); FORCED-FAILURE cases
    (open exit 1, plutil exit 1, probe timeout) keep exit 0 and print the
    honest fallback lines; SSH / HATCH_NO_OPEN skip the auto-open.

Run: python3.12 -m pytest cabinet/scripts/tests/test_hatch_app_feel.py -q
"""

from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_HATCH = _SCRIPTS_DIR / "hatch.sh"

_START_MARKER = "# ---- app-feel (Wave D) — bookmark + auto-open; convenience tail, NEVER a gate ----"
_INVOCATION = "app_feel || echo"
_PLAN_LINE = "[app-feel]      dashboard URL + Add-to-Dock hints; --with-launchd: probe + open + .webloc"
_PORT = "3177"
_URL = f"http://127.0.0.1:{_PORT}/"


def _run_hatch(args, home: Path):
    env = dict(os.environ)
    env["HOME"] = str(home)
    return subprocess.run(
        ["bash", str(_HATCH), *args],
        cwd=_REPO_ROOT, env=env,
        capture_output=True, text=True, timeout=60,
    )


# ---------------------------------------------------------------------------
# Extraction harness — insertion C from its literal start marker to EOF,
# driven branch-by-branch under shims. Never line numbers, never a live run.
# ---------------------------------------------------------------------------

def _tail_source() -> str:
    text = _HATCH.read_text(encoding="utf-8")
    assert _START_MARKER in text, "hatch.sh lost the app-feel start marker"
    return text[text.index(_START_MARKER):]


def _make_shim(shim_dir: Path, name: str, exit_code: int = 0) -> Path:
    """A recording shim: appends its argv to <shim_dir>/<name>.log."""
    log = shim_dir / f"{name}.log"
    shim = shim_dir / name
    shim.write_text(
        "#!/bin/bash\n"
        f"echo \"$@\" >> \"{log}\"\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return log


def _calls(shim_dir: Path, name: str) -> list[str]:
    log = shim_dir / f"{name}.log"
    if not log.is_file():
        return []
    return log.read_text(encoding="utf-8").splitlines()


def _run_tail(tmp_path: Path, *, clean_room="0", with_launchd="1",
              curl_exit=0, open_exit=0, plutil_exit: int | None = None,
              extra_env: dict | None = None):
    """Run the extracted tail under set -euo pipefail with shims.

    plutil_exit None = the REAL plutil (macOS) stays on PATH; an int shims
    it. open/curl/sleep are ALWAYS shimmed (a test must never launch a
    browser or wait 120s).
    """
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    shim_dir = tmp_path / "shims"
    shim_dir.mkdir(exist_ok=True)
    _make_shim(shim_dir, "open", open_exit)
    _make_shim(shim_dir, "curl", curl_exit)
    _make_shim(shim_dir, "sleep", 0)  # timeout loop must not take 120s
    if plutil_exit is not None:
        _make_shim(shim_dir, "plutil", plutil_exit)

    script = tmp_path / "app-feel-extract.sh"
    script.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        f"CLEAN_ROOM={clean_room}\n"
        f"WITH_LAUNCHD={with_launchd}\n"
        f"DASH_PORT={_PORT}\n"
        f'DASH_URL="{_URL}"\n'
        + _tail_source(),
        encoding="utf-8",
    )

    env = {
        "HOME": str(home),
        "PATH": f"{shim_dir}:/usr/bin:/bin",
    }
    for k in ("SSH_CONNECTION", "HATCH_NO_OPEN"):
        env.pop(k, None)
    if extra_env:
        env.update(extra_env)
    p = subprocess.run(
        ["bash", str(script)],
        cwd=_REPO_ROOT, env=env,
        capture_output=True, text=True, timeout=60,
    )
    return p, home, shim_dir


def _webloc(home: Path) -> Path:
    return home / "Applications" / "Founder's Cabinet.webloc"


# ---------------------------------------------------------------------------
# Syntax + wiring pins
# ---------------------------------------------------------------------------

def test_bash_syntax_clean():
    p = subprocess.run(["bash", "-n", str(_HATCH)], capture_output=True, text=True)
    assert p.returncode == 0, f"bash -n failed: {p.stderr}"


def test_tail_wiring_guards_precede_writes_and_open():
    tail = _tail_source()
    # non-fatal invocation is the LAST line of the file
    assert _INVOCATION in tail, "app_feel invocation lost its || fallback"
    assert tail.rstrip().splitlines()[-1].startswith(_INVOCATION), (
        "the guarded invocation must end the file — nothing may run after it"
    )
    # clean-room guard is the first branch: before the webloc write, the
    # probe, and the open
    clean_guard = tail.index('if [ "$CLEAN_ROOM" = "1" ]')
    assert clean_guard < tail.index("webloc="), "clean-room guard must precede the webloc write"
    assert clean_guard < tail.index("curl -fsS"), "clean-room guard must precede the probe"
    assert clean_guard < tail.index("open "), "clean-room guard must precede auto-open"
    # no-launchd guard precedes the webloc write too
    assert tail.index('if [ "$WITH_LAUNCHD" != "1" ]') < tail.index("webloc="), (
        "no-launchd hint branch must precede the webloc write"
    )
    # validate-then-move: lint the tmp BEFORE mv
    assert tail.index('plutil -lint "$webloc.tmp"') < tail.index('mv "$webloc.tmp" "$webloc"'), (
        "the webloc tmp must be linted before it is moved into place"
    )


# ---------------------------------------------------------------------------
# --dry-run: plan line present, still executes nothing
# ---------------------------------------------------------------------------

def test_dry_run_advertises_app_feel_and_executes_nothing(tmp_path):
    p = _run_hatch(["--dry-run", "--defaults"], home=tmp_path)
    assert p.returncode == 0, p.stderr
    assert _PLAN_LINE in p.stdout, "--dry-run plan lost the app-feel line"
    assert "nothing was executed" in p.stdout
    assert list(tmp_path.iterdir()) == [], (
        "dry-run must create nothing under HOME — ~/Applications included"
    )


def test_dry_run_clean_room_also_advertises_app_feel(tmp_path):
    p = _run_hatch(["--dry-run", "--clean-room", "--defaults"], home=tmp_path)
    assert p.returncode == 0, p.stderr
    assert _PLAN_LINE in p.stdout


# ---------------------------------------------------------------------------
# Branch drives (extracted function under shims)
# ---------------------------------------------------------------------------

def test_clean_room_skips_and_never_opens(tmp_path):
    p, home, shims = _run_tail(tmp_path, clean_room="1", with_launchd="0")
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "clean-room: skipped" in p.stdout
    assert _calls(shims, "open") == [], "clean-room must never invoke open"
    assert not (home / "Applications").exists(), (
        "clean-room must not write ~/Applications"
    )


def test_no_launchd_hint_drops_no_file(tmp_path):
    p, home, shims = _run_tail(tmp_path, with_launchd="0")
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "dashboard not started (--no-launchd default)" in p.stdout
    assert "start-dashboard.sh" in p.stdout
    assert "no bookmark dropped" in p.stdout
    assert _calls(shims, "open") == []
    assert not (home / "Applications").exists(), (
        "a bookmark to a server that isn't running violates honest-empties"
    )


def test_with_launchd_writes_valid_webloc_and_opens(tmp_path):
    p, home, shims = _run_tail(tmp_path)  # real plutil validates the artifact
    assert p.returncode == 0, (p.stdout, p.stderr)
    webloc = _webloc(home)
    assert webloc.is_file(), "webloc bookmark missing"
    assert f"bookmark: {webloc}" in p.stdout
    # valid plist whose URL is the loopback dashboard URL
    lint = subprocess.run(["/usr/bin/plutil", "-lint", str(webloc)],
                          capture_output=True, text=True)
    assert lint.returncode == 0, lint.stdout + lint.stderr
    with webloc.open("rb") as fh:
        assert plistlib.load(fh) == {"URL": _URL}
    assert not webloc.with_name(webloc.name + ".tmp").exists()
    # probe ok (shimmed curl exit 0) -> exactly one open of the URL
    assert _calls(shims, "open") == [_URL]
    # idempotent overwrite: a second run stays green and re-renders
    p2, home2, _ = _run_tail(tmp_path)
    assert p2.returncode == 0, (p2.stdout, p2.stderr)
    assert _webloc(home2).is_file()


def test_forced_open_failure_stays_green_with_honest_line(tmp_path):
    p, _home, _shims = _run_tail(tmp_path, open_exit=1)
    assert p.returncode == 0, (
        "a failing `open` must never change hatch's exit code",
        p.stdout, p.stderr,
    )
    assert "auto-open failed" in p.stdout
    assert f"open {_URL} manually" in p.stdout


def test_forced_plutil_failure_skips_bookmark_and_stays_green(tmp_path):
    p, home, shims = _run_tail(tmp_path, plutil_exit=1)
    assert p.returncode == 0, (
        "a failing plutil must never change hatch's exit code",
        p.stdout, p.stderr,
    )
    assert "bookmark skipped" in p.stdout
    webloc = _webloc(home)
    assert not webloc.exists(), "an unvalidated webloc must not be installed"
    assert not webloc.with_name(webloc.name + ".tmp").exists(), (
        "the failed tmp file must be cleaned up"
    )
    # the step continues to the probe/open despite the bookmark failure
    assert _calls(shims, "open") == [_URL]


def test_probe_timeout_prints_amber_and_stays_green(tmp_path):
    p, _home, shims = _run_tail(tmp_path, curl_exit=1)  # sleep shimmed: fast
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "AMBER: dashboard not reachable yet" in p.stdout
    assert "api/health" in p.stdout
    assert len(_calls(shims, "curl")) == 60, "probe loop must try 60 times"
    assert _calls(shims, "open") == [], "never open a dead URL"
    # AMBER is the tail's honesty, not a chain failure
    assert "HATCH FAILED" not in p.stdout + p.stderr


def test_ssh_and_hatch_no_open_skip_auto_open(tmp_path):
    for extra in ({"SSH_CONNECTION": "10.0.0.1 1 10.0.0.2 22"},
                  {"HATCH_NO_OPEN": "1"}):
        sub = tmp_path / list(extra)[0].lower()
        sub.mkdir()
        p, _home, shims = _run_tail(sub, extra_env=extra)
        assert p.returncode == 0, (extra, p.stdout, p.stderr)
        assert "auto-open skipped" in p.stdout, extra
        assert _calls(shims, "open") == [], f"{extra} must suppress auto-open"


def test_where_things_live_hints_are_wired():
    """The hint lines + hoisted port resolution live before the tail: the
    dashboard URL must be resolved (env > cabinet/.env > 3100) BEFORE the
    WHERE-THINGS-LIVE hints that print it."""
    text = _HATCH.read_text(encoding="utf-8")
    resolve = text.index('DASH_PORT="${CABINET_DASHBOARD_PORT:-}"')
    where = text.index("==== WHERE THINGS LIVE")
    hint = text.index('echo "Dashboard:             ${DASH_URL}')
    assert resolve < where < hint < text.index(_START_MARKER)
    assert 'echo "App feel:' in text, "Add-to-Dock/Install hint line missing"
