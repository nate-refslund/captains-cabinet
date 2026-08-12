"""Tests for the hatch.sh app-feel tail (Perfect Cabinet Wave D, 2026-07-10;
browser handover 2026-08-02).

The tail is a CONVENIENCE step, never a gate: hatch.sh reaches EOF only on
the GREEN path (step_fail exits 1 earlier, --dry-run exits 0 at the plan
gate), and the tail must preserve that exit disposition no matter what fails
inside it (`app_feel || echo …` + per-branch `return 0`). These tests pin
that contract WITHOUT running the live chain (house style — the chain
mutates instance/, so full runs belong to clean-room verifiers in scratch
clones, not the shared tree):

  * --dry-run advertises the app-feel plan line and still executes nothing;
  * wiring pins — the clean-room guard is the function's FIRST branch (before
    any write, any start, any `open`), and the invocation carries the
    non-fatal fallback;
  * function-level branch drives — the tail extracted by its literal start
    marker into a temp script and run under PATH shims (fake
    open/curl/plutil/sleep/nohup/bash recording invocations, temp HOME): the
    DEFAULT --no-launchd path starts the dashboard, waits on /api/health,
    copies the password and opens /onboarding; --clean-room and --no-browser
    skip all of it; FORCED-FAILURE cases (open exit 1, plutil exit 1,
    password exit 1, probe timeout) keep exit 0 and print the honest fallback
    lines; SSH / HATCH_NO_OPEN skip only the auto-open;
  * MOVEIN_OK=0 (2026-08-12, never-strand): a --with-launchd run whose move-in
    FAILED has nothing serving, so the tail must start the dashboard itself
    rather than probe a port launchd never opened. Before this the tail
    trusted --with-launchd to mean "already running", which on a failed
    move-in meant a 2-minute wait, no browser, and a stranded operator.

The password script is invoked through a SHIMMED `bash` on purpose: the real
dashboard-password.sh would read the running checkout's cabinet/.env and put
a live password on the developer's clipboard. A test must never write the
clipboard.

Run: python3.12 -m pytest cabinet/scripts/tests/test_hatch_app_feel.py -q
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_HATCH = _SCRIPTS_DIR / "hatch.sh"

_START_MARKER = "# ---- app-feel (Wave D) — bookmark + auto-open; convenience tail, NEVER a gate ----"
_INVOCATION = "app_feel || echo"
_EXIT_LINE = 'exit "$HATCH_EXIT"'
_PLAN_LINE = "[open]          start your Cabinet (or reuse a running one / a successful move-in's),"
_PORT = "3177"
_URL = f"http://127.0.0.1:{_PORT}/"
_LANDING = f"{_URL}onboarding"


def _run_hatch(args, home: Path):
    env = dict(os.environ)
    env["HOME"] = str(home)
    return subprocess.run(
        ["bash", str(_HATCH), *args],
        cwd=_REPO_ROOT, env=env,
        capture_output=True, text=True, timeout=60,
    )


# ---------------------------------------------------------------------------
# Extraction harness — the tail from its literal start marker to EOF, driven
# branch-by-branch under shims. Never line numbers, never a live run.
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


def _make_curl_shim(shim_dir: Path, *, fail_first: int, exit_code: int) -> Path:
    """A counting curl shim: the first `fail_first` calls exit 1, the rest exit
    `exit_code`. Lets a drive distinguish "already serving" (call 1 succeeds)
    from "started it, then it came up" (call 1 fails, a later one succeeds)."""
    log = shim_dir / "curl.log"
    count = shim_dir / "curl.count"
    shim = shim_dir / "curl"
    shim.write_text(
        "#!/bin/bash\n"
        f"echo \"$@\" >> \"{log}\"\n"
        f"n=$(cat \"{count}\" 2>/dev/null || echo 0); n=$((n+1)); echo \"$n\" > \"{count}\"\n"
        f"if [ \"$n\" -le {fail_first} ]; then exit 1; fi\n"
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


def _run_tail(tmp_path: Path, *, clean_room="0", with_launchd="1", no_browser="0",
              movein_ok=None, curl_exit=0, curl_fail_first=0, open_exit=0,
              bash_exit=0, plutil_exit: int | None = None,
              extra_env: dict | None = None):
    """Run the extracted tail under set -euo pipefail with shims.

    plutil_exit None = the REAL plutil (macOS) stays on PATH; an int shims
    it. open/curl/sleep/nohup/bash are ALWAYS shimmed — a test must never
    launch a browser, wait minutes, start a dashboard server, or run the real
    dashboard-password.sh against the checkout's cabinet/.env.
    """
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    logdir = tmp_path / "logs"
    logdir.mkdir(exist_ok=True)
    shim_dir = tmp_path / "shims"
    shim_dir.mkdir(exist_ok=True)
    _make_shim(shim_dir, "open", open_exit)
    _make_curl_shim(shim_dir, fail_first=curl_fail_first, exit_code=curl_exit)
    _make_shim(shim_dir, "sleep", 0)  # timeout loop must not take minutes
    _make_shim(shim_dir, "nohup", 0)  # never actually start a dashboard
    _make_shim(shim_dir, "bash", bash_exit)  # the password script, never for real
    if plutil_exit is not None:
        _make_shim(shim_dir, "plutil", plutil_exit)

    # MOVEIN_OK left UNSET by default on purpose: the tail must read it as
    # "${MOVEIN_OK:-1}" so it is correct when driven on its own, and every
    # pre-2026-08-12 arm below exercises exactly that.
    movein_line = "" if movein_ok is None else f"MOVEIN_OK={movein_ok}\n"
    script = tmp_path / "app-feel-extract.sh"
    script.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        f"CLEAN_ROOM={clean_room}\n"
        f"WITH_LAUNCHD={with_launchd}\n"
        f"NO_BROWSER={no_browser}\n"
        # the tail's last line is `exit "$HATCH_EXIT"` — hatch.sh seeds it 0
        "HATCH_EXIT=0\n"
        + movein_line
        + f"DASH_PORT={_PORT}\n"
        f'DASH_URL="{_URL}"\n'
        f'HATCH_LOG_DIR="{logdir}"\n'
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
    # /bin/bash explicitly — plain `bash` on PATH is the shim.
    p = subprocess.run(
        ["/bin/bash", str(script)],
        cwd=_REPO_ROOT, env=env,
        capture_output=True, text=True, timeout=120,
    )
    return p, home, shim_dir


def _webloc(home: Path) -> Path:
    return home / "Applications" / "Captain's Cabinet.webloc"


def _password_calls(shim_dir: Path) -> list[str]:
    """Shimmed-`bash` invocations that targeted dashboard-password.sh."""
    return [c for c in _calls(shim_dir, "bash") if "dashboard-password.sh" in c]


def _start_calls(shim_dir: Path) -> list[str]:
    """Shimmed-`nohup` invocations that targeted start-dashboard.sh."""
    return [c for c in _calls(shim_dir, "nohup") if "start-dashboard.sh" in c]


# ---------------------------------------------------------------------------
# Syntax + wiring pins
# ---------------------------------------------------------------------------

def test_bash_syntax_clean():
    p = subprocess.run(["bash", "-n", str(_HATCH)], capture_output=True, text=True)
    assert p.returncode == 0, f"bash -n failed: {p.stderr}"


def test_tail_wiring_guards_precede_writes_and_open():
    tail = _tail_source()
    # The non-fatal invocation is the second-to-last COMMAND, and the ONLY
    # thing allowed after it is the exit-code selection (2026-08-12): the tail
    # must still be unable to change the run's disposition, but the run now
    # has two green dispositions to choose between (0 and 75).
    assert _INVOCATION in tail, "app_feel invocation lost its || fallback"
    code = [ln for ln in tail.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
    assert code[-1] == _EXIT_LINE, (
        f"the file must end with {_EXIT_LINE} — got {code[-1]!r}"
    )
    assert code[-2].startswith(_INVOCATION), (
        "the guarded invocation must be the last thing that RUNS; only the "
        f"exit-code selection may follow it — got {code[-2]!r}"
    )
    # clean-room guard is the first branch: before the webloc write, the
    # probe, the dashboard start, and the open
    clean_guard = tail.index('if [ "$CLEAN_ROOM" = "1" ]')
    assert clean_guard < tail.index("webloc="), "clean-room guard must precede the webloc write"
    assert clean_guard < tail.index("curl -fsS"), "clean-room guard must precede the probe"
    assert clean_guard < tail.index("nohup bash"), "clean-room guard must precede the dashboard start"
    assert clean_guard < tail.index("open "), "clean-room guard must precede auto-open"
    # --no-browser is the second guard: also before any start/write/open
    no_browser_guard = tail.index('if [ "$NO_BROWSER" = "1" ]')
    assert clean_guard < no_browser_guard < tail.index("nohup bash"), (
        "--no-browser must be checked before the dashboard is started"
    )
    # the start branch precedes the webloc write
    assert tail.index('if [ "$self_start" = "1" ]') < tail.index("webloc="), (
        "the self-start branch must precede the webloc write"
    )
    # …and who self-starts is decided from BOTH knobs: a --with-launchd run
    # whose move-in failed has nothing serving, so it must start one itself.
    # Reading MOVEIN_OK with a :-1 default keeps the tail correct standalone.
    assert 'if [ "$WITH_LAUNCHD" = "1" ] && [ "${MOVEIN_OK:-1}" = "1" ]' in tail, (
        "self_start must be 0 only when a SUCCESSFUL move-in already started "
        "the dashboard — a failed move-in must not suppress the start"
    )
    # validate-then-move: lint the tmp BEFORE mv
    assert tail.index('plutil -lint "$webloc.tmp"') < tail.index('mv "$webloc.tmp" "$webloc"'), (
        "the webloc tmp must be linted before it is moved into place"
    )
    # the password never reaches stdout: only --copy is ever asked for
    assert 'dashboard-password.sh" --copy' in tail, (
        "the password handover must go through dashboard-password.sh --copy"
    )
    assert "pbpaste" not in tail and "DASHBOARD_PASSWORD" not in tail, (
        "the tail must never read back or echo the dashboard password"
    )


def test_no_browser_flag_is_parsed_and_documented():
    text = _HATCH.read_text(encoding="utf-8")
    assert "--no-browser)   NO_BROWSER=1 ;;" in text, "--no-browser is not parsed"
    assert 'NO_BROWSER="${HATCH_NO_BROWSER:-0}"' in text, (
        "HATCH_NO_BROWSER must seed the flag so a headless caller can opt out"
    )
    assert "  --no-browser " in text, "--no-browser missing from usage()"


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


def test_dry_run_accepts_no_browser_and_records_it(tmp_path):
    p = _run_hatch(["--dry-run", "--defaults", "--no-browser"], home=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "no-browser=1" in p.stdout, "the plan's mode line must record --no-browser"
    assert list(tmp_path.iterdir()) == []


def test_dry_run_no_browser_defaults_off(tmp_path):
    p = _run_hatch(["--dry-run", "--defaults"], home=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "no-browser=0" in p.stdout, "the browser handover must be opt-OUT, not opt-in"


# ---------------------------------------------------------------------------
# Branch drives (extracted function under shims)
# ---------------------------------------------------------------------------

def test_clean_room_skips_everything(tmp_path):
    """Clean-room = CI = headless. Exactly the pre-2026-08-02 behavior:
    nothing started, nothing probed, no clipboard, no browser, no HOME write."""
    p, home, shims = _run_tail(tmp_path, clean_room="1", with_launchd="0")
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "clean-room: skipped" in p.stdout
    assert _calls(shims, "open") == [], "clean-room must never invoke open"
    assert _calls(shims, "curl") == [], "clean-room must never probe"
    assert _start_calls(shims) == [], "clean-room must never start the dashboard"
    assert _password_calls(shims) == [], "clean-room must never touch the clipboard"
    assert not (home / "Applications").exists(), (
        "clean-room must not write ~/Applications"
    )


def test_no_browser_skips_everything_but_says_where_to_go(tmp_path):
    p, home, shims = _run_tail(tmp_path, with_launchd="0", no_browser="1")
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "--no-browser" in p.stdout
    assert "start-dashboard.sh" in p.stdout, "must still say how to start it by hand"
    assert _LANDING in p.stdout, "must still say where the door is"
    assert _calls(shims, "open") == []
    assert _calls(shims, "curl") == []
    assert _start_calls(shims) == []
    assert _password_calls(shims) == []
    assert not (home / "Applications").exists()


def test_no_launchd_starts_dashboard_waits_copies_password_and_opens(tmp_path):
    """THE mission arm: the DEFAULT path ends in a browser at /onboarding.

    curl_fail_first=1 → the first probe (is one already serving?) fails, so
    the tail starts one; a later probe succeeds, so it really is up.

    plutil is SHIMMED here so the bookmark branch completes on Linux too:
    /usr/bin/plutil is macOS-only, and this arm is about the branch being
    REACHED on the --no-launchd path at all (it used to return before it), not
    about plist validity — that is the darwin-only sibling's job.
    """
    p, home, shims = _run_tail(tmp_path, with_launchd="0", curl_fail_first=1,
                               plutil_exit=0)
    assert p.returncode == 0, (p.stdout, p.stderr)
    started = _start_calls(shims)
    assert len(started) == 1, f"expected exactly one dashboard start, got {started}"
    assert "starting your Cabinet" in p.stdout
    assert "step-dashboard.log" in p.stdout, (
        "a backgrounded server must say where its log is"
    )
    assert "To stop it:" in p.stdout, (
        "a process that outlives the script must say how to stop it"
    )
    # waited on health, then handed the password over, then opened /onboarding
    assert "waiting for your Cabinet to answer" in p.stdout
    assert "You don't need to do anything" in p.stdout, (
        "a multi-minute wait must tell the person they are not blocking it"
    )
    assert len(_password_calls(shims)) == 1, "the password must be copied exactly once"
    assert _calls(shims, "open") == [_LANDING], (
        "the hatch must land the operator on /onboarding, not the dashboard root"
    )
    # the bookmark is honest now that a server really is running — the
    # --no-launchd path used to return before ever reaching this step
    assert _webloc(home).is_file()
    assert "shortcut saved:" in p.stdout


def test_no_launchd_reuses_an_already_serving_dashboard(tmp_path):
    """A second hatch (or a live box) must not stack a second server on the
    port — the first probe answering is proof one is already there."""
    p, _home, shims = _run_tail(tmp_path, with_launchd="0")  # first curl succeeds
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "already running" in p.stdout
    assert _start_calls(shims) == [], "must not start a second dashboard"
    assert _calls(shims, "open") == [_LANDING]


def test_wait_loop_says_what_it_waits_for_and_how_to_skip(tmp_path):
    """A silent multi-minute pause at the end of a hatch reads as a hang."""
    p, _home, shims = _run_tail(tmp_path, with_launchd="0", curl_exit=1)
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "still starting" in p.stdout
    assert "This is normal" in p.stdout, "a long silent wait reads as a hang"
    assert "--no-browser" in p.stdout, "the wait must say how to skip it next time"
    # the no-launchd wait is the long one (a first run compiles the dashboard)
    assert len(_calls(shims, "curl")) == 151, (
        "probe loop must be 1 liveness check + 150 tries on the --no-launchd path"
    )


@pytest.mark.skipif(sys.platform != "darwin",
                    reason="asserts the REAL plutil validation path "
                           "(/usr/bin/plutil is macOS-only; sibling tests "
                           "shim plutil and run anywhere)")
def test_with_launchd_writes_valid_webloc_and_opens(tmp_path):
    p, home, shims = _run_tail(tmp_path)  # real plutil validates the artifact
    assert p.returncode == 0, (p.stdout, p.stderr)
    webloc = _webloc(home)
    assert webloc.is_file(), "webloc bookmark missing"
    assert f"shortcut saved: {webloc}" in p.stdout
    # valid plist whose URL is the loopback dashboard HOME (not the landing)
    lint = subprocess.run(["/usr/bin/plutil", "-lint", str(webloc)],
                          capture_output=True, text=True)
    assert lint.returncode == 0, lint.stdout + lint.stderr
    with webloc.open("rb") as fh:
        assert plistlib.load(fh) == {"URL": _URL}
    assert not webloc.with_name(webloc.name + ".tmp").exists()
    # launchd already started it: never start a second one
    assert _start_calls(shims) == []
    # probe ok (shimmed curl exit 0) -> exactly one open of the landing
    assert _calls(shims, "open") == [_LANDING]
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
    assert "couldn't open your browser" in p.stdout
    assert f"go to {_LANDING} yourself" in p.stdout


def test_forced_password_failure_stays_green_with_honest_line(tmp_path):
    """dashboard-password.sh refuses on an absent / bad-permission .env. That
    is the operator's problem to fix, never a reason to recolor the hatch."""
    p, _home, shims = _run_tail(tmp_path, bash_exit=1)
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "password not copied" in p.stdout
    assert "dashboard-password.sh --copy" in p.stdout
    # …and it still finishes the handover
    assert _calls(shims, "open") == [_LANDING]


def test_forced_plutil_failure_skips_bookmark_and_stays_green(tmp_path):
    p, home, shims = _run_tail(tmp_path, plutil_exit=1)
    assert p.returncode == 0, (
        "a failing plutil must never change hatch's exit code",
        p.stdout, p.stderr,
    )
    assert "shortcut skipped" in p.stdout
    webloc = _webloc(home)
    assert not webloc.exists(), "an unvalidated webloc must not be installed"
    assert not webloc.with_name(webloc.name + ".tmp").exists(), (
        "the failed tmp file must be cleaned up"
    )
    # the step continues to the probe/open despite the bookmark failure
    assert _calls(shims, "open") == [_LANDING]


def test_probe_timeout_prints_amber_and_stays_green(tmp_path):
    p, _home, shims = _run_tail(tmp_path, curl_exit=1)  # sleep shimmed: fast
    assert p.returncode == 0, (p.stdout, p.stderr)
    # Plain, not "AMBER" (2026-08-12): the person reading this line did not
    # ask for a traffic-light vocabulary, and a slow first build is not an
    # emergency. It must still be HONEST and say where to look.
    assert "taking longer than expected" in p.stdout
    assert "Nothing is broken" in p.stdout
    assert _LANDING in p.stdout, "must still say where the door is"
    assert "AMBER" not in p.stdout, "operator copy must not carry gate jargon"
    assert len(_calls(shims, "curl")) == 60, "probe loop must try 60 times"
    assert _calls(shims, "open") == [], "never open a dead URL"
    assert _password_calls(shims) == [], "never hand a password to a dead server"
    # a slow dashboard is the tail's honesty, not a chain failure
    assert "HATCH FAILED" not in p.stdout + p.stderr


def test_ssh_and_hatch_no_open_skip_auto_open(tmp_path):
    for extra in ({"SSH_CONNECTION": "10.0.0.1 1 10.0.0.2 22"},
                  {"HATCH_NO_OPEN": "1"}):
        sub = tmp_path / list(extra)[0].lower()
        sub.mkdir()
        p, _home, shims = _run_tail(sub, extra_env=extra)
        assert p.returncode == 0, (extra, p.stdout, p.stderr)
        assert "we didn't open a window for you" in p.stdout, extra
        assert _calls(shims, "open") == [], f"{extra} must suppress auto-open"
        # narrower than --no-browser: the password still changes hands
        assert len(_password_calls(shims)) == 1, extra


def test_where_things_live_hints_are_wired():
    """The hint lines + hoisted port resolution live before the tail: the
    dashboard URL must be resolved (env > cabinet/.env > 3100) BEFORE the
    WHERE-THINGS-ARE hints that print it."""
    text = _HATCH.read_text(encoding="utf-8")
    resolve = text.index('DASH_PORT="${CABINET_DASHBOARD_PORT:-}"')
    where = text.index("==== WHERE THINGS ARE")
    hint = text.index('echo "Your Cabinet:          ${DASH_URL}')
    assert resolve < where < hint < text.index(_START_MARKER)
    assert 'echo "Keep it in your Dock:' in text, "Add-to-Dock/Install hint line missing"
    # the briefing the hatch just wrote is reachable in the browser
    assert "${DASH_URL}briefing" in text, (
        "WHERE THINGS LIVE must point at the in-browser briefing reader"
    )


# ---------------------------------------------------------------------------
# A FAILED move-in must not suppress the front door (never-strand, 2026-08-12)
# ---------------------------------------------------------------------------

def test_failed_movein_still_starts_the_dashboard_and_opens_the_browser(tmp_path):
    """--with-launchd + MOVEIN_OK=0: launchd never started anything, so the
    tail must start the dashboard itself and still land the browser.

    Before the fix the tail read --with-launchd as "something is already
    serving", so a failed move-in meant 60 dead probes, no start, no password
    and no browser — on top of a hatch.sh that had already exited 1 before
    reaching here. This arm is the second half of that failure.
    """
    p, home, shims = _run_tail(tmp_path, with_launchd="1", movein_ok="0",
                               curl_fail_first=1, plutil_exit=0)
    assert p.returncode == 0, (p.stdout, p.stderr)
    started = _start_calls(shims)
    assert len(started) == 1, (
        f"a failed move-in must self-start the dashboard, got {started}"
    )
    assert len(_password_calls(shims)) == 1, "the password must still change hands"
    assert _calls(shims, "open") == [_LANDING], (
        "the operator must still land on /onboarding after a failed move-in"
    )
    assert _webloc(home).is_file()


def test_successful_movein_does_not_start_a_second_dashboard(tmp_path):
    """The inverse arm — without it the test above would pass on a tail that
    simply always starts one, stacking a second server on the port."""
    p, _home, shims = _run_tail(tmp_path, with_launchd="1", movein_ok="1",
                                plutil_exit=0)
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert _start_calls(shims) == [], (
        "a successful move-in already started it — never stack a second one"
    )
    assert _calls(shims, "open") == [_LANDING]


def test_failed_movein_wait_advice_points_at_the_log_it_started(tmp_path):
    """Degenerate end: the dashboard the tail started never answers. The
    advice must name the log of THAT process, not a launchd job that was
    never loaded."""
    p, _home, shims = _run_tail(tmp_path, with_launchd="1", movein_ok="0",
                                curl_exit=1, plutil_exit=0)
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "step-dashboard.log" in p.stdout, (
        "after self-starting, the fallback must point at the started process's log"
    )
    assert "launchctl" not in p.stdout, (
        "a move-in that failed left no launchd job to inspect — do not send "
        "the operator to one"
    )
