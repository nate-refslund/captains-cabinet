"""The runtime stays up: the fleet load is DURABLE and the door is SUPERVISED.

TWO DEFECTS, BOTH MEASURED ON THE CAPTAIN'S INSTALLED CABINET (2026-09-21,
eleven days after the first real update applied to it).

1. THE FLEET LOAD WAS NOT DURABLE. ``hatch.sh``'s move-in loaded the schedule
   by walking ``cabinet/launchd/generated/*.plist`` and bootstrapping each file
   WHERE IT LAY. launchd remembers a job by the path it was bootstrapped from
   and re-reads that path at login only for agents installed under the user's
   own ``LaunchAgents`` directory — nothing under the checkout is ever read
   again. One restart (~2026-08-29) therefore cleared all fifty scheduled jobs,
   and the fleet was dark for three weeks before anyone noticed. The durable
   verb already existed: ``deploy-mac.sh --all`` renders from ``services.yml``
   plus the roster, WRITES the user's ``LaunchAgents`` directory and reconciles
   launchd to exactly that set (it put 51 jobs back on 2026-09-21).

2. AN APPLY COULD LEAVE THE DOOR UNSUPERVISED AND SAY NOTHING. When no launchd
   job answered, ``cabinet_dash_restart`` started a DETACHED dashboard — an
   orphan that dies with its terminal or with the next restart. The dashboard
   the 2026-09-10 apply started was dead by 2026-09-21, the web door (the
   Captain's only no-terminal door) was gone, and ``status`` said nothing about
   it. An unsupervised door is sometimes the only thing possible; being
   unsupervised SILENTLY never is.

WHAT THESE ARMS PIN. A ratchet with an EMPTY allowlist over every shell script
that ships: none of them bootstraps a plist out of the generated directory. A
positive arm on the move-in, because a ratchet passes vacuously on a script
that stopped bootstrapping anything at all. Then the door: launchd takes it
(supervised, recorded) and launchd refuses it (the fallback still runs, and the
log, the state record and ``status`` all say the door is unsupervised and why).

NOTHING HERE TOUCHES THIS BOX'S LAUNCHD. Every arm runs with ``HOME`` pointed
at a temp directory, a fake ``launchctl`` first on ``PATH``, and — where a
label is involved at all — a throwaway label, never the system one.

Run: python3.12 -m pytest cabinet/scripts/tests/test_runtime_stays_up.py -q
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
_ROOT = _SCRIPTS.parent.parent
_HATCH = _SCRIPTS / "hatch.sh"
_ERRANDS = _SCRIPTS / "hatch-lib" / "errands.sh"
_DASH_LIB = _SCRIPTS / "lib" / "dashboard.sh"
_UPDATER = _SCRIPTS / "cabinet-update.sh"
_BUNDLE_PY = _SCRIPTS / "lib" / "update_bundle.py"

# A label that exists nowhere but in this file. The system one is never typed
# into an arm that could reach a real launchctl.
_TEST_LABEL = "com.cabinet.u8-drive-dashboard"

# The operator's real error text, so the fallback arm fails the way his Mac did.
_EIO = "Bootstrap failed: 5: Input/output error"


# ===========================================================================
# 1. The ratchet: nothing bootstraps a plist where it was rendered
# ===========================================================================

#: EMPTY, and it is meant to stay empty. A script that needs a line here needs
#: a reason in the same commit — "the schedule is loaded from the checkout" is
#: the defect, not an exception to it.
_BOOTSTRAP_ALLOWLIST: set[str] = set()

_GENERATED = "launchd/generated"


def _shell_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "cabinet/scripts", "cabinet/launchd"],
                         cwd=_ROOT, capture_output=True, text=True, check=True)
    return [_ROOT / rel for rel in out.stdout.split()
            if rel.endswith(".sh") and (_ROOT / rel).is_file()]


def _bootstrap_lines(text: str) -> list[tuple[int, str]]:
    """Every line that actually runs (or prints) a launchd bootstrap."""
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        if re.search(r"(launchctl|\$\{?LAUNCHCTL\}?|\$\{?CABINET_LAUNCHCTL[^}]*\}?)\"?\s+bootstrap\b",
                     line):
            hits.append((number, line))
    return hits


def _binds_to_generated(text: str, var: str) -> bool:
    """Is `var` bound, anywhere in this file, to something under the generated
    directory? Covers both shapes that have existed here: a `for` over the
    glob, and a plain assignment."""
    for pattern in (r"for\s+%s\s+in\s+([^\n;]*)" % re.escape(var),
                    r"^\s*%s=([^\n]*)" % re.escape(var)):
        for rhs in re.findall(pattern, text, re.M):
            if _GENERATED in rhs or "GENERATED_DIR" in rhs:
                return True
    return False


def test_no_shipped_script_bootstraps_a_plist_out_of_the_generated_directory():
    """THE RATCHET. A plist bootstrapped where it was rendered is a job that
    disappears at the next restart — the three-week blackout, in one line.

    Two shapes are caught: the path named on the bootstrap line itself (which
    also catches a command PRINTED for an operator to paste, and that half of
    the defect shipped too), and a variable the same file binds to the
    generated directory.

    WHAT THIS DOES NOT CATCH, said plainly: a bootstrap of some other
    non-durable path — a temp directory, say. `diagnose-calendar-tcc.sh` does
    exactly that on purpose, with a unique per-run label it boots out again in
    its own trap, and it is correct. The positive arm below is what keeps this
    from passing vacuously on the one script that matters."""
    findings = []
    for path in _shell_files():
        rel = str(path.relative_to(_ROOT))
        if rel in _BOOTSTRAP_ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8")
        for number, line in _bootstrap_lines(text):
            if _GENERATED in line:
                findings.append(f"{rel}:{number}: bootstraps a path under {_GENERATED}/: {line.strip()}")
                continue
            for var in re.findall(r'"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?"?\s*$', line.strip()):
                if _binds_to_generated(text, var):
                    findings.append(
                        f"{rel}:{number}: bootstraps ${var}, which this file binds to "
                        f"{_GENERATED}/: {line.strip()}")
    assert not findings, (
        "a launchd job bootstrapped from the checkout does not survive a restart "
        "— install it under the user's LaunchAgents directory first "
        "(cabinet_launchd_install, or deploy-mac.sh):\n  " + "\n  ".join(findings))


def test_the_allowlist_is_empty():
    """A ratchet with a growing allowlist is a ratchet that has been turned
    off. If a line is ever needed here, this arm is the one that makes the
    decision visible."""
    assert _BOOTSTRAP_ALLOWLIST == set()


# ===========================================================================
# 2. The move-in goes through the durable verb — and proves it landed
# ===========================================================================

def _movein_load_body() -> str:
    text = _HATCH.read_text(encoding="utf-8")
    start = text.index("do_movein_load() {")
    end = text.index("movein_step movein-load", start)
    return text[start:end]


def test_the_movein_load_step_runs_the_deploy_that_writes_launchagents():
    """The positive half of the ratchet. `deploy-mac.sh --all` is the verb that
    renders the fleet, WRITES the user's LaunchAgents directory and reconciles
    launchd to exactly that set; the move-in must go through it rather than
    walking the render directory itself."""
    body = _movein_load_body()
    assert "deploy-mac.sh" in body and "--all" in body, (
        "hatch's move-in does not load the schedule through deploy-mac.sh --all:\n" + body)
    assert "launchctl bootstrap" not in body, (
        "hatch's move-in still bootstraps plists itself:\n" + body)


def test_the_movein_load_step_verifies_the_schedule_is_where_a_restart_reads_it():
    """REPORTED IS NOT MEASURED. A deploy that exits 0 having written nothing
    durable is exactly the state this box was in for three weeks, so the step
    asks the filesystem, not the exit code."""
    body = _movein_load_body()
    assert "LaunchAgents" in body, (
        "the move-in never checks that a plist landed under the user's "
        "LaunchAgents directory, so a deploy that wrote nothing reads as green:\n" + body)


def test_the_paste_runnable_hints_name_the_durable_command():
    """Both places that hand an operator a command to run by hand. A hint that
    tells them to bootstrap out of the checkout reproduces the defect with
    their own hands."""
    for path in (_HATCH, _ERRANDS):
        text = path.read_text(encoding="utf-8")
        for number, line in _bootstrap_lines(text):
            assert _GENERATED not in line, (
                f"{path.name}:{number} hands the operator the non-durable load: {line.strip()}")
    hint = _movein_hint()
    assert "deploy-mac.sh" in hint, (
        "hatch's failure hint for the move-in load does not name the durable verb: " + hint)
    errands = _ERRANDS.read_text(encoding="utf-8")
    assert "deploy-mac.sh --all" in errands, (
        "the errand note does not hand the operator the durable command")


def _movein_hint() -> str:
    text = _HATCH.read_text(encoding="utf-8")
    match = re.search(r"do_movein_load\)\s*echo\s*'([^']*)'", text)
    assert match, "hatch.sh no longer carries a paste-runnable hint for do_movein_load"
    return match.group(1)


# ===========================================================================
# 3. The door after an apply
# ===========================================================================

def _fake_launchctl(bin_dir: Path, *, bootstrap_rc: int, loaded: bool = False) -> Path:
    """A launchctl that records its argv. `print` decides whether a job is
    already there; `bootstrap` decides whether launchd will take one."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    log = bin_dir / "launchctl.log"
    script = bin_dir / "launchctl"
    script.write_text(
        "#!/bin/bash\n"
        f'echo "$@" >> "{log}"\n'
        'case "$1" in\n'
        f'  print) {"printf \'\\tstate = running\\n\'; exit 0" if loaded else "exit 113"} ;;\n'
        '  bootout) exit 0 ;;\n'
        f'  bootstrap) [ {bootstrap_rc} -eq 0 ] || echo "{_EIO}" >&2; exit {bootstrap_rc} ;;\n'
        '  kickstart) exit 0 ;;\n'
        'esac\nexit 0\n', encoding="utf-8")
    script.chmod(0o755)
    return log


def _door_root(tmp_path: Path, *, with_plist: bool = True) -> Path:
    """A scratch cabinet: a rendered dashboard plist, a start script that does
    nothing, and nothing else."""
    root = tmp_path / "cab"
    (root / "cabinet" / "launchd" / "generated").mkdir(parents=True)
    (root / "cabinet" / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "cabinet" / "logs").mkdir(parents=True, exist_ok=True)
    if with_plist:
        (root / "cabinet" / "launchd" / "generated" / f"{_TEST_LABEL}.plist").write_text(
            "<plist/>\n", encoding="utf-8")
    (root / "cabinet" / "scripts" / "start-dashboard.sh").write_text(
        "#!/bin/bash\nexit 0\n", encoding="utf-8")
    return root


def _restart(tmp_path: Path, root: Path, *, bootstrap_rc: int, loaded: bool = False,
             record: Path | None = None):
    """Drive the REAL `cabinet_dash_restart` out of the shipped library."""
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True, exist_ok=True)
    bin_dir = tmp_path / "bin"
    log = _fake_launchctl(bin_dir, bootstrap_rc=bootstrap_rc, loaded=loaded)
    # curl exit 7 = nothing is listening, which is the state an orphan that has
    # already died leaves behind.
    (bin_dir / "curl").write_text("#!/bin/bash\nexit 7\n", encoding="utf-8")
    (bin_dir / "curl").chmod(0o755)
    (bin_dir / "plutil").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    (bin_dir / "plutil").chmod(0o755)
    env = dict(os.environ)
    env.update({
        "HOME": str(home),
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "CABINET_DASH_LABEL": _TEST_LABEL,
        "CABINET_DASHBOARD_PORT": "3187",
    })
    if record is not None:
        env["CABINET_DASH_DOOR_RECORD"] = str(record)
    proc = subprocess.run(
        ["bash", "-c",
         f'set -u; . "{_DASH_LIB}"; cabinet_dash_restart "{root}" "a drive"'],
        capture_output=True, text=True, env=env, timeout=120)
    return proc, home, log


def test_an_unsupervised_door_is_put_back_under_supervision(tmp_path):
    """THE FIX. No job is loaded, the rendered plist is right there, and
    launchd will take it — so the door comes back SUPERVISED: the plist is
    copied to where a restart reads it, and the COPY is what gets loaded."""
    root = _door_root(tmp_path)
    record = tmp_path / "door-last"
    proc, home, log = _restart(tmp_path, root, bootstrap_rc=0, record=record)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    installed = home / "Library" / "LaunchAgents" / f"{_TEST_LABEL}.plist"
    assert installed.is_file(), (
        "the plist was never installed where a restart reads it; launchctl saw:\n"
        + (log.read_text() if log.is_file() else "(nothing)") + proc.stderr)
    calls = log.read_text(encoding="utf-8")
    assert f"bootstrap gui/{os.getuid()} {installed}" in calls, (
        "the bootstrap did not name the INSTALLED copy:\n" + calls)
    assert record.is_file() and "supervised=1" in record.read_text(encoding="utf-8"), (
        "the restart recorded no door verdict: "
        + (record.read_text() if record.is_file() else "(no record)"))


def test_a_door_launchd_will_not_take_falls_back_and_says_so(tmp_path):
    """The officer's measured case: a non-GUI launchd manager answers the
    bootstrap with an I/O error. The detached start still happens — a door
    nobody supervises beats no door — but it is never silent again."""
    root = _door_root(tmp_path)
    record = tmp_path / "door-last"
    proc, _home, _log = _restart(tmp_path, root, bootstrap_rc=1, record=record)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "door is UNSUPERVISED" in proc.stderr, (
        "a door nothing supervises must say so: " + proc.stderr)
    assert f"gui/{os.getuid()}" in proc.stderr and _EIO in proc.stderr, (
        "the reason launchd gave must survive into the log: " + proc.stderr)
    assert record.is_file(), "no door verdict was recorded"
    text = record.read_text(encoding="utf-8")
    assert "supervised=0" in text and _EIO in text, text


def test_a_supervised_door_is_still_restarted_by_kickstart(tmp_path):
    """The arm that must NOT change. A loaded job is restarted as a job —
    killing the process would just make KeepAlive start the old build again."""
    root = _door_root(tmp_path)
    proc, home, log = _restart(tmp_path, root, bootstrap_rc=0, loaded=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "kickstart" in log.read_text(encoding="utf-8")
    assert not (home / "Library" / "LaunchAgents" / f"{_TEST_LABEL}.plist").exists(), (
        "a door that was already supervised must not be reinstalled underneath itself")


def test_no_rendered_plist_is_a_reason_not_a_crash(tmp_path):
    """The degenerate end: nothing to install. The fallback runs and the
    recorded reason says what was missing."""
    root = _door_root(tmp_path, with_plist=False)
    record = tmp_path / "door-last"
    proc, _home, _log = _restart(tmp_path, root, bootstrap_rc=0, record=record)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "door is UNSUPERVISED" in proc.stderr, proc.stderr
    assert record.is_file() and "supervised=0" in record.read_text(encoding="utf-8")


# ===========================================================================
# 4. status says what the door is doing, at read time
# ===========================================================================

def _status_install(tmp_path: Path, *, state: dict | None = None) -> Path:
    root = tmp_path / "install"
    (root / "cabinet" / "scripts" / "lib").mkdir(parents=True)
    (root / ".updates").mkdir(parents=True)
    for src, rel in ((_UPDATER, "cabinet/scripts/cabinet-update.sh"),
                     (_BUNDLE_PY, "cabinet/scripts/lib/update_bundle.py"),
                     (_DASH_LIB, "cabinet/scripts/lib/dashboard.sh")):
        (root / rel).write_bytes(src.read_bytes())
    (root / "egg-manifest.json").write_text(
        json.dumps({"source_commit": "c" * 40}), encoding="utf-8")
    if state is not None:
        (root / ".updates" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return root


def _status(tmp_path: Path, root: Path, *, loaded: bool, as_json: bool = True):
    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True, exist_ok=True)
    bin_dir = tmp_path / "bin"
    _fake_launchctl(bin_dir, bootstrap_rc=0, loaded=loaded)
    env = dict(os.environ)
    env.update({
        "HOME": str(home),
        "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "CABINET_ROOT": str(root),
        "CABINET_DASH_LABEL": _TEST_LABEL,
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    args = ["status", "--json"] if as_json else ["status"]
    return subprocess.run(
        ["bash", str(root / "cabinet" / "scripts" / "cabinet-update.sh"), *args],
        cwd=str(root), capture_output=True, text=True, env=env, timeout=180)


def test_status_json_reports_the_doors_launchd_state_at_read_time(tmp_path):
    """A dead orphan is invisible until something asks. `status` asks — every
    time it is read, not once at apply time."""
    root = _status_install(tmp_path)
    proc = _status(tmp_path, root, loaded=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["door_supervised"] is False, report
    assert report["door_launchd"] == "not-loaded", report
    assert report["door_label"] == _TEST_LABEL, report


def test_status_json_says_supervised_when_the_job_is_there(tmp_path):
    """The inverse arm: without it, a hardcoded False would pass the one
    above."""
    root = _status_install(tmp_path)
    report = json.loads(_status(tmp_path, root, loaded=True).stdout)
    assert report["door_supervised"] is True, report
    assert report["door_launchd"] == "running", report


def test_status_carries_the_recorded_reason_the_door_is_unsupervised(tmp_path):
    """The live read says THAT the door is unsupervised; the record from the
    last restart says WHY, and the two are different facts."""
    root = _status_install(tmp_path, state={
        "phase": "applied", "to_sha": "d" * 40,
        "door_supervised": False, "door_reason": _EIO,
    })
    report = json.loads(_status(tmp_path, root, loaded=False).stdout)
    assert report["door_supervised"] is False
    assert _EIO in report["door_reason"], report


def test_human_status_prints_the_door(tmp_path):
    """The terminal door reads the same fact as the json one."""
    root = _status_install(tmp_path)
    proc = _status(tmp_path, root, loaded=False, as_json=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "door" in proc.stdout, proc.stdout
    assert "not being served" in proc.stdout.lower() or "not supervised" in proc.stdout.lower(), (
        "the human status says nothing about a door nothing supervises:\n" + proc.stdout)


def test_status_never_writes_anything_while_reporting_the_door(tmp_path):
    """A5.17.6: a report that changes the thing it reports is not a report.
    Reading the door must not install, load or record anything."""
    root = _status_install(tmp_path)
    before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    _status(tmp_path, root, loaded=False)
    after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))
    assert before == after, set(after) ^ set(before)
    home = tmp_path / "home" / "Library" / "LaunchAgents"
    assert list(home.iterdir()) == [], "status installed a launchd job"


# ===========================================================================
# 5. The acceptance drill stays hermetic
# ===========================================================================

def test_the_restart_seam_returns_before_any_launchd_work():
    """P7 drives the updater with `CABINET_UPDATE_TEST_RESTART_CMD`. If the
    seam ever stopped short-circuiting the real path, the drill would start
    installing launchd jobs on whatever box ran it."""
    text = _UPDATER.read_text(encoding="utf-8")
    start = text.index("restart_dashboard() {")
    end = text.index("\n}", start)
    # CODE ONLY. This function's comments name `cabinet_dash_restart` several
    # times before the seam, and an index into the raw text would read a
    # comment as the call — a sensor measuring prose instead of control flow.
    body = "\n".join(line for line in text[start:end].splitlines()
                     if not line.lstrip().startswith("#"))
    seam = body.index("CABINET_UPDATE_TEST_RESTART_CMD")
    real = body.index("cabinet_dash_restart \"$ROOT\"")
    assert seam < real, "the test seam no longer precedes the real restart path"
    returned = body.index("return $?", seam)
    assert returned < real, (
        "the test seam falls through to the real restart path, so the drill "
        "would touch the box's launchd")
    assert "cabinet_launchd_install" not in body[:returned], (
        "the seam path itself now does launchd work")
