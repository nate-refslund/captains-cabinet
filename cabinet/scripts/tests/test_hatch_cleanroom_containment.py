"""Regression tests for the hatch.sh --clean-room runtime-dir containment fix
(Perfect Cabinet Wave C, 2026-07-10; PC-B verifier follow-up (a)).

The seam: --clean-room used to leave CABINET_RUNTIME_DIR at its default, so
step 6 (load-preset.sh) OVERWROTE the live box's
/tmp/cabinet-runtime/{constitution.md,safety-boundaries.md} — the files
officers consume at boot (create-officer.sh / sync-agents.sh). The fix
exports CABINET_RUNTIME_DIR into the run's scratch area beside the flight
log (<log dir>/cabinet-runtime) BEFORE any step runs; load-preset.sh:27
already honors the override.

These tests pin, WITHOUT running the live chain:
  * the wiring — the exact guarded export exists in hatch.sh and precedes
    flight_init (i.e. every step);
  * the self-defeat refusals (adversarial fixes, 2026-07-10) — the routing
    must never write the live default itself: a --flight-log directly in
    /tmp (LOG_DIR=/tmp -> <log dir>/cabinet-runtime == the live dir), a
    --flight-log INSIDE /tmp/cabinet-runtime (fix-pass: the runtime dir
    routes to a nested scratch path while flight.log + step-*.log would
    land in the live governance dir), and an ambient CABINET_RUNTIME_DIR
    aimed at — or nested under — /tmp/cabinet-runtime are all REFUSED,
    exit 64, in every spelling the box can produce (/private/tmp alias,
    trailing slash, slash runs, '.' segments, '..' traversal: hatch.sh
    normalizes lexically, then resolves the deepest existing ancestor
    physically, before comparing). Every refusal fires before flight_init
    AND before the flight-log parent is created (fix-pass: the old
    pre-guard mkdir -p of a not-yet-existing flight-log parent is gone) —
    a refused run writes NOTHING. Pinned as wiring (both guards sit
    between the export and flight_init) AND functionally (the refusal
    probes exit at the guard, before any step could run);
  * the plan — --dry-run --clean-room advertises the routing; a plain
    --dry-run --defaults plan is untouched by the fix;
  * the containment itself — a focused probe of load-preset.sh under the
    env hatch.sh sets in clean-room mode (scratch CABINET_ROOT fixture,
    CABINET_RUNTIME_DIR routed beside a scratch flight-log dir, the
    deliberately-unused Redis port, no DB URLs): the scratch runtime dir
    receives the assembled files while the live /tmp/cabinet-runtime
    checksums + mtimes stay byte-for-byte untouched (read-only snapshot;
    absent-before == absent-after also passes, so the test is green on
    boxes that never hatched; one retry on live-snapshot mismatch absorbs
    a concurrent officer boot rewriting the twins mid-window — a real
    breach reproduces on the retry, so the check stays fail-closed).

Run: python3.12 -m pytest cabinet/scripts/tests/test_hatch_cleanroom_containment.py -q
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_HATCH = _SCRIPTS_DIR / "hatch.sh"
_LOAD_PRESET = _SCRIPTS_DIR / "load-preset.sh"

_LIVE_RUNTIME = Path("/tmp/cabinet-runtime")
_RUNTIME_FILES = ("constitution.md", "safety-boundaries.md")

# The exact containment contract in hatch.sh — drift breaks loudly.
_EXPORT_LINE = 'export CABINET_RUNTIME_DIR="${CABINET_RUNTIME_DIR:-$LOG_DIR/cabinet-runtime}"'
_GUARD_LINE = 'if [ "$CLEAN_ROOM" = "1" ]; then'
# The live-default refusals' case pattern — both macOS spellings, exact and
# nested; appears TWICE (the flight-log dir guard + the runtime dir guard).
_REFUSE_PIN = (
    "/tmp/cabinet-runtime|/tmp/cabinet-runtime/*"
    "|/private/tmp/cabinet-runtime|/private/tmp/cabinet-runtime/*)"
)


def _run_hatch(args, home: Path, extra_env: dict | None = None):
    env = dict(os.environ)
    # pin plan output against ambient overrides
    for k in ("CABINET_RUNTIME_DIR", "HATCH_CLEANROOM_REDIS_PORT"):
        env.pop(k, None)
    env["HOME"] = str(home)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(_HATCH), *args],
        cwd=_REPO_ROOT, env=env,
        capture_output=True, text=True, timeout=60,
    )


def _snapshot_live():
    """Read-only snapshot of the live runtime twins: existence + sha256 +
    mtime_ns per file. Never creates, touches, or reads-for-write."""
    if not _LIVE_RUNTIME.is_dir():
        return ("absent", {})
    state = {}
    for name in _RUNTIME_FILES:
        f = _LIVE_RUNTIME / name
        if f.is_file():
            state[name] = (
                hashlib.sha256(f.read_bytes()).hexdigest(),
                f.stat().st_mtime_ns,
            )
    return ("present", state)


def _scratch_root(tmp_path: Path) -> Path:
    """A minimal CABINET_ROOT tree load-preset.sh can run against (same
    fixture shape as test_load_preset_materialize): framework bases, one
    populated preset with NO agents/ dir (the Redis expected-active marking
    block never runs), the active-preset selector, and the shipped .example
    governance twins."""
    root = tmp_path / "root"
    (root / "framework").mkdir(parents=True)
    (root / "framework" / "constitution-base.md").write_text(
        "# Constitution base (containment fixture)\n", encoding="utf-8")
    (root / "framework" / "safety-boundaries-base.md").write_text(
        "# Safety base (containment fixture)\n", encoding="utf-8")
    preset = root / "presets" / "work"
    preset.mkdir(parents=True)
    (preset / "preset.yml").write_text("name: work\n", encoding="utf-8")
    cfg = root / "instance" / "config"
    cfg.mkdir(parents=True)
    (cfg / "active-preset").write_text("work\n", encoding="utf-8")
    for twin in ("posture.yml.example", "trust-ladder.yml.example"):
        src = _REPO_ROOT / "instance" / "config" / twin
        if src.is_file():
            shutil.copy(src, cfg / twin)
    return root


# ---------------------------------------------------------------------------
# Wiring — the guarded export exists and precedes every step
# ---------------------------------------------------------------------------

def test_hatch_exports_scratch_runtime_dir_in_clean_room():
    text = _HATCH.read_text(encoding="utf-8")
    assert _EXPORT_LINE in text, (
        "hatch.sh lost the clean-room CABINET_RUNTIME_DIR containment export "
        "— a scratch hatch would overwrite the live /tmp/cabinet-runtime"
    )
    # Exactly one occurrence: every positional pin below (and the guard-line
    # walk in the next test) anchors on this string, so a second occurrence
    # — even in a comment — could let a check pass against the wrong line.
    assert text.count(_EXPORT_LINE) == 1, (
        "the containment export line must stay unique in hatch.sh — the "
        "wiring pins anchor on it"
    )
    # The export must run before ANY step: flight_init "$LOG_DIR" opens the
    # run section, and every run_step call sits after it.
    assert text.index(_EXPORT_LINE) < text.index('flight_init "$LOG_DIR"'), (
        "the containment export must precede flight_init (i.e. every step)"
    )


def test_clean_room_live_default_refusal_is_wired_after_the_export():
    """The self-defeat guards: the refusal case pattern (both macOS
    spellings of the live dir, exact and nested) must appear exactly TWICE
    — the flight-log dir guard (fix-pass 2026-07-10) and the runtime dir
    guard — sitting AFTER the default expansion (they check RESOLVED
    values, ambient or defaulted) and BEFORE flight_init (a refused run
    must write nothing)."""
    text = _HATCH.read_text(encoding="utf-8")
    assert _REFUSE_PIN in text, (
        "hatch.sh lost the live-default refusal — a /tmp flight log (or an "
        "ambient override) would route the 'scratch' runtime dir onto the "
        "live /tmp/cabinet-runtime under a containment banner"
    )
    assert text.count(_REFUSE_PIN) == 2, (
        "expected exactly two refusal case patterns — the flight-log dir "
        "guard and the runtime dir guard (fix-pass 2026-07-10); a lone "
        "runtime-dir guard lets --flight-log /tmp/cabinet-runtime/flight.log "
        "write step logs into the live governance dir"
    )
    assert (
        text.index(_EXPORT_LINE)
        < text.index(_REFUSE_PIN)
        <= text.rindex(_REFUSE_PIN)
        < text.index('flight_init "$LOG_DIR"')
    ), "both refusals must check resolved values and fire before flight_init"


def test_export_is_guarded_by_the_clean_room_flag():
    lines = _HATCH.read_text(encoding="utf-8").splitlines()
    idx = next(i for i, ln in enumerate(lines) if _EXPORT_LINE in ln)
    # nearest preceding non-comment, non-blank line is the clean-room guard —
    # a non-clean-room hatch must keep the live default untouched
    for prev in reversed(lines[:idx]):
        stripped = prev.strip()
        if not stripped or stripped.startswith("#"):
            continue
        assert stripped == _GUARD_LINE, (
            f"containment export is no longer guarded by {_GUARD_LINE!r}; "
            f"found {stripped!r} instead"
        )
        break
    else:
        raise AssertionError("no line precedes the containment export")


# ---------------------------------------------------------------------------
# Plan honesty — clean-room advertises the routing; defaults plan untouched
# ---------------------------------------------------------------------------

def test_dry_run_clean_room_advertises_runtime_dir_routing(tmp_path):
    p = _run_hatch(["--dry-run", "--clean-room", "--defaults"], home=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "CABINET_RUNTIME_DIR" in p.stdout
    assert "the live /tmp/cabinet-runtime is never written" in p.stdout


def test_dry_run_defaults_plan_does_not_route_runtime_dir(tmp_path):
    p = _run_hatch(["--dry-run", "--defaults"], home=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "CABINET_RUNTIME_DIR" not in p.stdout, (
        "a non-clean-room plan must not claim runtime-dir routing"
    )


# ---------------------------------------------------------------------------
# Self-defeat refusal — the routing must never resolve to the live default.
# These probes RUN hatch.sh for real: the guard exits 64 before flight_init,
# before the python3.12 preflight, before any step — a refused run is
# side-effect-free by construction, and the asserts below pin that.
# ---------------------------------------------------------------------------

def test_clean_room_refuses_flight_log_directly_in_tmp(tmp_path):
    """--flight-log /tmp/<name>.log makes LOG_DIR=/tmp, so the scratch
    default <log dir>/cabinet-runtime would BE the live dir."""
    probe_log = Path(f"/tmp/hatch-containment-refusal-{os.getpid()}.log")
    assert not probe_log.exists(), f"stale probe artifact: {probe_log}"
    p = _run_hatch(["--clean-room", "--flight-log", str(probe_log)],
                   home=tmp_path)
    assert p.returncode == 64, (p.stdout, p.stderr)
    assert "refuses CABINET_RUNTIME_DIR" in p.stderr
    assert "live runtime dir" in p.stderr
    # the refusal fires before flight_init: no flight log, nothing under HOME
    assert not probe_log.exists(), "a refused run must not create its flight log"
    assert list(tmp_path.iterdir()) == [], "a refused run must write nothing under HOME"


def test_clean_room_refuses_ambient_live_runtime_dir(tmp_path):
    """An inherited CABINET_RUNTIME_DIR aimed at — or nested under — the
    live dir must be refused in every spelling the box can produce: /tmp
    and /private/tmp (macOS aliases of one directory), trailing slash,
    slash runs, '.' segments, '..' traversal through a not-yet-existing
    intermediate (lexically popped — a literal compare would miss it and
    load-preset's mkdir -p would then write the LIVE twins), and nested
    paths (scratch twins inside the live governance dir are pollution
    too)."""
    traversal_hop = Path(f"/tmp/hatch-probe-gone-{os.getpid()}")
    assert not traversal_hop.exists(), f"stale probe artifact: {traversal_hop}"
    for spelling in ("/tmp/cabinet-runtime",
                     "/tmp/cabinet-runtime/",
                     "/tmp//cabinet-runtime",
                     "/tmp/./cabinet-runtime",
                     f"{traversal_hop}/../cabinet-runtime",
                     "/tmp/cabinet-runtime/nested-scratch",
                     "/private/tmp/cabinet-runtime"):
        p = _run_hatch(
            ["--clean-room", "--flight-log", str(tmp_path / "flight.log")],
            home=tmp_path,
            extra_env={"CABINET_RUNTIME_DIR": spelling},
        )
        assert p.returncode == 64, (spelling, p.stdout, p.stderr)
        assert "refuses CABINET_RUNTIME_DIR" in p.stderr, spelling
    assert not traversal_hop.exists(), (
        "the '..' probe's intermediate dir must never be created"
    )
    assert not (tmp_path / "flight.log").exists(), (
        "a refused run must not create its flight log"
    )


def test_clean_room_refuses_flight_log_inside_live_runtime_dir(tmp_path):
    """The fix-pass seam (adversarial finding, 2026-07-10): a --flight-log
    INSIDE the live dir routes the runtime dir to a NESTED scratch path
    (…/cabinet-runtime/cabinet-runtime — the original exact-match guard
    passed it) while flight_init + run_step would write flight.log and
    step-*.log INTO the live governance dir under the banner claiming it
    is never written. The log-dir refusal must fire — naming the flight
    log, not the derived CABINET_RUNTIME_DIR — for the direct and nested
    spellings, creating and modifying nothing under the live dir."""
    live_existed = _LIVE_RUNTIME.is_dir()
    probe_sub = _LIVE_RUNTIME / f"probe-sub-{os.getpid()}"
    live_flight = _LIVE_RUNTIME / "flight.log"
    flight_existed = live_flight.exists()  # read-only tolerance; never delete
    for arg in (str(live_flight), str(probe_sub / "flight.log")):
        p = _run_hatch(["--clean-room", "--flight-log", arg], home=tmp_path)
        assert p.returncode == 64, (arg, p.stdout, p.stderr)
        assert "refuses a flight-log dir" in p.stderr, arg
        assert "live runtime dir" in p.stderr, arg
        assert "own directory" in p.stderr, arg
    assert _LIVE_RUNTIME.is_dir() == live_existed, (
        "a refused run must not create (or remove) the live-named dir"
    )
    assert not probe_sub.exists(), (
        "a refused run must not create a dir inside the live runtime dir"
    )
    assert live_flight.exists() == flight_existed, (
        "a refused run must not create its flight log in the live dir"
    )
    assert list(tmp_path.iterdir()) == [], (
        "a refused run must write nothing under HOME"
    )


def test_clean_room_refusal_creates_no_flight_log_parent(tmp_path):
    """A refused run writes NOTHING — the flight-log parent included
    (fix-pass 2026-07-10: hatch.sh used to mkdir -p a not-yet-existing
    flight-log parent BEFORE the guard could refuse; now flight_init
    creates it only after the guards pass). Probe: --flight-log in a
    not-yet-existing dir plus an ambient live override — the refusal must
    not leave the empty user-named dir behind."""
    parent = tmp_path / "hatch-logs-not-yet"
    p = _run_hatch(
        ["--clean-room", "--flight-log", str(parent / "flight.log")],
        home=tmp_path,
        extra_env={"CABINET_RUNTIME_DIR": str(_LIVE_RUNTIME)},
    )
    assert p.returncode == 64, (p.stdout, p.stderr)
    assert "refuses CABINET_RUNTIME_DIR" in p.stderr
    assert not parent.exists(), (
        "the refused run pre-created the flight-log parent dir"
    )
    assert list(tmp_path.iterdir()) == [], (
        "a refused run must write nothing under HOME"
    )


def test_clean_room_scratch_routing_is_not_refused(tmp_path):
    """Control: a genuinely scratch-routed clean-room plan stays green —
    the refusal must only fire on the live default. --dry-run exits before
    the guard, so pair it with the wiring pin above: this asserts the
    normal path is unaffected, the wiring pin asserts the guard exists."""
    p = _run_hatch(["--dry-run", "--clean-room", "--defaults"], home=tmp_path)
    assert p.returncode == 0, p.stderr
    assert "refuses CABINET_RUNTIME_DIR" not in p.stderr


# ---------------------------------------------------------------------------
# Containment — focused probe of load-preset under hatch's clean-room env
# ---------------------------------------------------------------------------

def _run_containment_probe(base: Path):
    """One full probe: scratch fixture + load-preset run under the env
    hatch.sh sets in clean-room mode. Hard-asserts the scratch side (never
    timing-dependent); the caller owns the live-side snapshot compare."""
    root = _scratch_root(base)
    # hatch.sh clean-room routing: CABINET_RUNTIME_DIR beside the flight log
    log_dir = base / "hatch-logs" / "hatch-fixture"
    log_dir.mkdir(parents=True)
    scratch_runtime = log_dir / "cabinet-runtime"

    env = dict(os.environ)
    env["CABINET_ROOT"] = str(root)
    env["CABINET_RUNTIME_DIR"] = str(scratch_runtime)
    # step 6's clean-room env: expected-active marks at the unused port
    env["REDIS_HOST"] = "127.0.0.1"
    env["REDIS_PORT"] = "6399"
    for k in ("NEON_CONNECTION_STRING", "DATABASE_URL",
              "CABINET_ID", "CABINET_MODE"):
        env.pop(k, None)

    p = subprocess.run(
        ["bash", str(_LOAD_PRESET)],
        cwd=_REPO_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )
    assert p.returncode == 0, p.stderr

    # the scratch runtime dir received the assembled files ...
    for name in _RUNTIME_FILES:
        f = scratch_runtime / name
        assert f.is_file(), f"{name} did not land in the scratch runtime dir"
        assert f.stat().st_size > 0, f"{name} landed empty"
    assert "containment fixture" in (scratch_runtime / "constitution.md").read_text(
        encoding="utf-8"), "constitution was not assembled from the fixture base"
    # ... and load-preset's own log names the scratch path as its target
    assert str(scratch_runtime) in p.stderr, (
        "load-preset did not report assembling into the routed scratch dir"
    )


def test_cleanroom_env_routes_writes_to_scratch_and_live_stays_untouched(tmp_path):
    # The live-side compare is mtime_ns-exact (mission-specified). On a live
    # box a CONCURRENT officer boot can rewrite the twins inside the probe
    # window; one retry with a fresh snapshot absorbs that flake without
    # weakening the check — every write in this probe is aimed at the routed
    # scratch dir, so a genuine containment breach reproduces on the retry
    # and still fails RED (fail-closed).
    mismatch = None
    for attempt in range(2):
        before = _snapshot_live()
        _run_containment_probe(tmp_path / f"attempt-{attempt}")
        after = _snapshot_live()
        if after == before:
            return
        mismatch = (before, after)
    raise AssertionError(
        "live /tmp/cabinet-runtime changed under a clean-room-routed run "
        f"(reproduced on retry): before={mismatch[0]} after={mismatch[1]}"
    )
