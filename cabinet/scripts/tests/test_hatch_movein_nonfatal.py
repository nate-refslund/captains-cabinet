"""The front door always opens: a failed move-in never strands the operator.

THE FAILURE THIS FILE EXISTS FOR (2026-08-12, measured on a real operator's
Mac). He double-clicked Hatch Cabinet.app, which runs
``hatch.sh --defaults --with-launchd``. Every gate passed, the first briefing
was written — and then ``deploy-mac.sh --officer cos`` died with launchd's
``Bootstrap failed: 5: Input/output error``. Because the move-in steps were
hard ``run_step`` calls, ``step_fail`` printed a stack of paths and exited 1
*before* the verdict block and *before* the browser handover. No dashboard
started, no password reached the clipboard, nothing opened. Terminal said
"Process completed" and he had no idea what to do with a cabinet that was, in
fact, fully built.

THE RULE: the operator-facing product is the dashboard and onboarding.
Starting background helpers is the advanced step and the one most likely to
fail on an unfamiliar Mac, so it is NON-FATAL — recorded, said plainly, and
then the run carries on to open the front door. Real gates (host setup,
instance, activation, proofs, first receipt) still stop the run, because
without them there is nothing to open.

HOW IT IS TESTED. The full chain mutates ``instance/``, so — house style —
these drives never run it. Two slices of the real ``hatch.sh`` are extracted
by literal marker (the step machinery, so the REAL ``run_step_soft`` is what
runs, and everything from the move-in block to EOF) and executed under PATH
shims: a ``bash`` shim that fails only for ``deploy-mac.sh``, reproducing the
operator's exact error text, and fake ``curl``/``open``/``sleep``/``nohup``/
``plutil``/``launchctl``/``python3.12``. Nothing here touches launchd, a
clipboard, a browser or a port.

Run: python3.12 -m pytest cabinet/scripts/tests/test_hatch_movein_nonfatal.py -q
"""

from __future__ import annotations


import subprocess
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_HATCH = _SCRIPTS_DIR / "hatch.sh"

# Literal markers, never line numbers.
_MACHINERY_START = "# ---- step machinery ---"
_MACHINERY_END = "# ---- composite steps"
_MOVEIN_START = '# 6. background helpers (runbook section 6, "move-in")'
_PORT = "3178"
_URL = f"http://127.0.0.1:{_PORT}/"
_LANDING = f"{_URL}onboarding"
# The operator's real error, quoted so the drive fails the way his Mac did.
_LAUNCHD_EIO = "Bootstrap failed: 5: Input/output error"


def _source() -> str:
    return _HATCH.read_text(encoding="utf-8")


def _slice(text: str, start: str, end: str | None) -> str:
    assert start in text, f"hatch.sh lost the marker {start!r}"
    body = text[text.index(start):]
    if end is None:
        return body
    assert end in body, f"hatch.sh lost the marker {end!r}"
    return body[: body.index(end)]


def _shim(shim_dir: Path, name: str, body: str) -> Path:
    log = shim_dir / f"{name}.log"
    p = shim_dir / name
    p.write_text(f'#!/bin/bash\necho "$@" >> "{log}"\n{body}\n', encoding="utf-8")
    p.chmod(0o755)
    return log


def _calls(shim_dir: Path, name: str) -> list[str]:
    log = shim_dir / f"{name}.log"
    return log.read_text(encoding="utf-8").splitlines() if log.is_file() else []


def _drive(tmp_path: Path, *, deploy_rc: int, with_launchd: str = "1",
           plists: bool = True):
    """Run [step machinery] + [move-in .. EOF] of the real hatch.sh.

    cwd is a scratch tree, never the checkout: the block globs
    ``cabinet/launchd/generated/*.plist`` relative to cwd, and a drive must
    neither read the developer's real generated plists nor write anything into
    the repo. ``plists=False`` reproduces the empty-glob refusal.
    """
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    cwd = tmp_path / "tree"
    (cwd / "cabinet" / "launchd" / "generated").mkdir(parents=True, exist_ok=True)
    if plists:
        (cwd / "cabinet" / "launchd" / "generated" / "dummy.plist").write_text(
            "<plist/>\n", encoding="utf-8")
    logdir = tmp_path / "logs"
    logdir.mkdir(exist_ok=True)
    shims = tmp_path / "shims"
    shims.mkdir(exist_ok=True)

    # `bash` fails ONLY for deploy-mac.sh — so the password handover (also a
    # `bash` call) still succeeds and the arm is about the move-in alone.
    _shim(shims, "bash", f'''case "$*" in
  *deploy-mac.sh*) echo "{_LAUNCHD_EIO}" >&2; exit {deploy_rc} ;;
esac
exit 0''')
    # "answers immediately" now means answers AS THE CABINET: the probe matches
    # the dashboard's identity marker, not a bare 200 (identity-probe area,
    # 2026-08-25). A shim that only exits 0 models a foreign app on the port,
    # which is a different branch entirely.
    _shim(shims, "curl",
          "printf '%s' '{\"ok\":true,\"service\":\"cabinet-dashboard\"}'; exit 0")
    _shim(shims, "open", "exit 0")
    _shim(shims, "sleep", "exit 0")
    _shim(shims, "nohup", "exit 0")
    _shim(shims, "plutil", "exit 0")
    _shim(shims, "launchctl", "exit 0")
    _shim(shims, "python3.12", "exit 0")

    text = _source()
    script = tmp_path / "movein-drive.sh"
    script.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        f'SCRIPT_DIR="{_SCRIPTS_DIR}"\n'
        f'. "{_SCRIPTS_DIR}/hatch-lib/flight-recorder.sh"\n'
        f'. "{_SCRIPTS_DIR}/hatch-lib/errands.sh"\n'
        f'flight_init "{logdir}" "{logdir}/flight.log"\n'
        "PY=python3.12\n"
        "CLEAN_ROOM=0\n"
        "NO_BROWSER=0\n"
        f"WITH_LAUNCHD={with_launchd}\n"
        "HATCH_EXIT=0\n"
        'RECEIPT_LANDING="/tmp/none/briefing.md"\n'
        f'RECEIPT_LOG="{logdir}/step-first-receipt.log"\n'
        'DEMO_LANDING="/tmp/none/demo.md"\n'
        f'DEMO_LOG="{logdir}/step-demo-receipt.log"\n'
        "telegram_named() { echo 0; }\n"
        + _slice(text, _MACHINERY_START, _MACHINERY_END)
        + "\n"
        + _slice(text, _MOVEIN_START, None),
        encoding="utf-8",
    )
    env = {
        "HOME": str(home),
        "PATH": f"{shims}:/usr/bin:/bin",
        "CABINET_DASHBOARD_PORT": _PORT,
    }
    p = subprocess.run(["/bin/bash", str(script)], cwd=cwd, env=env,
                       capture_output=True, text=True, timeout=120)
    return p, shims, logdir


# ---------------------------------------------------------------------------
# The drive: the exact failure the operator hit
# ---------------------------------------------------------------------------

def test_failed_movein_still_reaches_the_verdict_and_opens_the_browser(tmp_path):
    p, shims, _logdir = _drive(tmp_path, deploy_rc=1)

    # 1. it did NOT die where it used to
    assert "HATCH FAILED" not in p.stdout + p.stderr, (
        "a background-helper failure must never print the hard-failure block"
    )
    # 2. it reached the end-of-run surfaces
    assert "YOUR CHECKLIST" in p.stdout, "the checklist must still print"
    assert "FLIGHT SUMMARY" in p.stdout, "the flight summary must still print"
    assert "WHERE THINGS ARE" in p.stdout, "the where-things-are block must still print"
    assert "YOUR CABINET IS READY" in p.stdout, "the verdict must still print"
    # 3. it opened the front door
    assert _calls(shims, "open") == [_LANDING], (
        f"the operator must still land on {_LANDING}; got {_calls(shims, 'open')}"
    )
    assert any("dashboard-password.sh" in c for c in _calls(shims, "bash")), (
        "the password must still be handed over"
    )
    # 4. exit disposition: green front door, optional helper missing
    assert p.returncode == 75, (
        "a hatched cabinet with a failed OPTIONAL helper is not exit 1 and not "
        f"exit 0 — expected 75, got {p.returncode}"
    )


def test_failed_movein_says_it_plainly_and_hides_the_raw_launchd_error(tmp_path):
    p, _shims, _logdir = _drive(tmp_path, deploy_rc=1)
    verdict = p.stdout[p.stdout.index("YOUR CABINET IS READY"):]
    assert "a background helper didn't start on this Mac" in verdict
    assert "That's" in verdict and "fine" in verdict, (
        "the note must reassure, not alarm — this is an optional extra"
    )
    assert "bash cabinet/scripts/hatch.sh --with-launchd" in verdict, (
        "the note must say, in one line, how to try again later"
    )
    # the raw launchd string is honest DIAGNOSIS, not operator copy: it belongs
    # in the step log, never in the calm closing note
    assert _LAUNCHD_EIO not in verdict, (
        "the raw launchd error must not be dumped into the operator's closing note"
    )
    # `--with-launchd` survives because it is a flag the person has to TYPE;
    # everything else in this vocabulary is ours, not theirs.
    scrubbed = verdict.replace("--with-launchd", "")
    for word in ("launchd", "bootstrap", "plist", "errand note", "AMBER",
                 "move-in", "First Mate", "measurement-plane"):
        assert word not in scrubbed, (
            f"jargon in the operator's closing note: {word}"
        )


def test_failed_movein_keeps_the_honest_record(tmp_path):
    """Calm to the operator, complete in the log — both, or neither is worth
    anything."""
    p, _shims, logdir = _drive(tmp_path, deploy_rc=1)
    flight = (logdir / "flight.log").read_text(encoding="utf-8")
    assert "MOVEIN_FAILED [movein-chair]" in flight, (
        "the flight log must record WHICH move-in step failed"
    )
    assert "STEP_END [movein-chair] status=fail" in flight
    step_log = logdir / "step-movein-chair.log"
    assert step_log.is_file(), "the failed step's own log must exist"
    assert _LAUNCHD_EIO in step_log.read_text(encoding="utf-8"), (
        "the exact launchd error must survive in the step log for diagnosis"
    )
    # the closing note points the operator (or whoever helps them) at it
    assert str(step_log) in p.stdout


def test_first_movein_failure_skips_the_rest_of_the_sequence(tmp_path):
    """Each move-in step depends on the one before it: rendering and loading a
    schedule for a helper that never deployed is noise, not resilience."""
    _p, _shims, logdir = _drive(tmp_path, deploy_rc=1)
    flight = (logdir / "flight.log").read_text(encoding="utf-8")
    for later in ("movein-plists", "movein-load", "movein-health"):
        assert f"STEP_BEGIN [{later}]" not in flight, (
            f"{later} ran after an earlier move-in step had already failed"
        )


def test_green_movein_exits_zero(tmp_path):
    """The inverse arm. Without it, `exit 75` unconditionally would pass every
    assertion above."""
    p, shims, logdir = _drive(tmp_path, deploy_rc=0)
    assert p.returncode == 0, (
        f"a fully green run must still exit 0, got {p.returncode}", p.stdout[-2000:]
    )
    assert "MOVEIN_FAILED" not in (logdir / "flight.log").read_text(encoding="utf-8")
    assert "background helpers are running" in p.stdout
    assert _calls(shims, "open") == [_LANDING]


def test_empty_plist_dir_is_also_non_fatal(tmp_path):
    """The degenerate end of the glob: nothing to load. It used to be a hard
    failure two steps later; it must behave like any other soft failure."""
    p, shims, logdir = _drive(tmp_path, deploy_rc=0, plists=False)
    assert p.returncode == 75
    assert "MOVEIN_FAILED [movein-load]" in (logdir / "flight.log").read_text(
        encoding="utf-8")
    assert _calls(shims, "open") == [_LANDING], (
        "an empty schedule directory must not cost the operator the browser"
    )


def test_no_launchd_path_is_untouched(tmp_path):
    """The default path never enters the move-in block at all, and still
    exits 0."""
    p, shims, logdir = _drive(tmp_path, deploy_rc=1, with_launchd="0")
    assert p.returncode == 0
    assert "MOVEIN_FAILED" not in (logdir / "flight.log").read_text(encoding="utf-8")
    assert _calls(shims, "open") == [_LANDING]


# ---------------------------------------------------------------------------
# Source-level wiring pins — the drives above cannot see a step added later
# ---------------------------------------------------------------------------

def test_every_movein_step_is_soft():
    """A future move-in step added with `run_step` would re-arm the exact
    failure this file exists for, and no drive above would notice."""
    text = _source()
    movein = _slice(text, _MOVEIN_START, "# ---- verdict")
    assert "movein_step " in movein, "the move-in block lost its soft runner"
    for line in movein.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert not stripped.startswith("run_step "), (
            f"a move-in step uses the FATAL runner: {stripped!r} — every step "
            "in this block must go through movein_step"
        )
    assert "run_step_soft" in movein, (
        "movein_step must delegate to the shared soft runner, not reimplement it"
    )


def test_movein_step_cannot_end_the_run():
    """`movein_step` returns 0 on both paths; nothing in the block may exit."""
    text = _source()
    movein = _slice(text, _MOVEIN_START, "# ---- verdict")
    body = movein[movein.index("movein_step() {"):]
    body = body[: body.index("\n  }\n")]
    assert body.count("return 0") >= 2, (
        "movein_step must return 0 on the already-failed path AND the "
        "just-failed path"
    )
    assert "exit " not in body, "movein_step must never exit the run"


def test_exit_code_is_seeded_green_and_only_ever_becomes_75():
    text = _source()
    assert "\nHATCH_EXIT=0\n" in text, "HATCH_EXIT must be seeded green"
    assigns = sorted({ln.strip() for ln in text.splitlines()
                      if ln.strip().startswith("HATCH_EXIT=")})
    assert assigns == ["HATCH_EXIT=0", "HATCH_EXIT=75"], (
        f"unexpected HATCH_EXIT assignments: {assigns}"
    )
    # seeded before the move-in block can flip it
    assert text.index("\nHATCH_EXIT=0\n") < text.index("HATCH_EXIT=75")
    # and documented where a reader of this script looks for exit codes
    assert "75 = hatched and the front door opened" in text, (
        "an exit code nobody documented is an exit code nobody can rely on"
    )
