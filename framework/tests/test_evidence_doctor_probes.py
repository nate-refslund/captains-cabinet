"""Doctor evidence-plane probes (Evidence Phase 2 Batch A, G3).

The probes live as PURE bash functions inside cabinet/scripts/cabinet-doctor.sh
between literal BEGIN/END markers (no doctor globals, one "OK|WARN|SKIP ..."
verdict line, always exit 0). These tests extract that block verbatim, source
it in a subprocess bash, and drive it against scratch evidence stores built in
tmp_path via the public framework.evidence API — never the live
instance/evidence store.

Laws pinned here:
  * AMBER-max — the doctor section never calls dead() and never uses the
    DEAD-capable stale_verdict; probes exit 0 on every input (a broken
    evidence plane must not crash or halt the fleet doctor: Phase-2
    observation-only).
  * Read-only — freshness/growth probes leave the store byte-identical; the
    chain probe never rewrites evidence bytes (the verifier's own signed
    watermark sidecar advance is the one sanctioned, protective side effect).
  * Pinned store root — the doctor section derives the store from
    $REPO_ROOT/instance/evidence/v1, never from the CABINET_EVIDENCE_DIR env
    fallback (the recorder's untrusted env seam, A10).

House interpreter: python3.12 (CI runs `pytest framework/`).
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from framework.evidence import EvidenceRecorder

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCTOR = REPO_ROOT / "cabinet" / "scripts" / "cabinet-doctor.sh"
PROBES_BEGIN = "# ---- EVIDENCE-PLANE PURE PROBES BEGIN ----"
PROBES_END = "# ---- EVIDENCE-PLANE PURE PROBES END ----"
SECTION_BEGIN = "# ---- EVIDENCE-PLANE SECTION BEGIN ----"
SECTION_END = "# ---- EVIDENCE-PLANE SECTION END ----"
PY = shutil.which("python3.12") or "python3.12"
TODAY = time.strftime("%Y%m%d", time.gmtime())


def _block(begin: str, end: str) -> str:
    text = DOCTOR.read_text(encoding="utf-8")
    assert begin in text and end in text, "evidence-plane markers missing from cabinet-doctor.sh"
    return text.split(begin, 1)[1].split(end, 1)[0]


def _ev_store_rel() -> str:
    """The store path the doctor pins, parsed FROM the section under test.

    Single source of truth: the framework layer never spells the
    instance-layer path itself (layer-separation rule) — the one place that
    pins it is the doctor section, and these tests follow it.
    """
    section = _block(SECTION_BEGIN, SECTION_END)
    match = re.search(r'(?m)^EV_STORE="\$REPO_ROOT/([^"]+)"', section)
    assert match, "EV_STORE pin missing from the evidence-plane section"
    return match.group(1)


@pytest.fixture()
def probes(tmp_path: Path) -> Path:
    path = tmp_path / "probes.sh"
    path.write_text(_block(PROBES_BEGIN, PROBES_END), encoding="utf-8")
    return path


def _run(probes_file: Path, fn: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", 'source "$1"; shift 2; "$0" "$@"', fn, str(probes_file), "_"] + list(args),
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
    )


def _mk_store(tmp_path: Path, *, appends: int = 3, trial: str | None = None) -> Path:
    store = tmp_path / "store"
    recorder = EvidenceRecorder(store)
    trial_id = trial or f"evt-doctorprobe-{TODAY}"
    for step in range(appends):
        recorder.append(
            recorder.trace(trial_id, surface="test"),
            phase="system",
            status="succeeded",
            actor={"kind": "system", "id": "doctor-probe-test"},
            component={"name": "doctor-probe-test", "version": "1", "commit": "unset"},
            detail={"action": "probe_fixture", "step_index": step},
        )
    return store


def _snapshot(store: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in sorted(store.rglob("*")):
        if item.is_file() and not item.is_symlink():
            out[str(item.relative_to(store))] = hashlib.sha256(item.read_bytes()).hexdigest()
    return out


# --- AMBER-max + wiring laws (static, no subprocess) -------------------------

def test_section_markers_present_and_never_dead():
    section = _block(SECTION_BEGIN, SECTION_END)
    # The whole evidence-plane section may ok/warn/skip but NEVER dead() and
    # never call the DEAD-capable stale_verdict helper.
    assert not re.search(r'(?m)^\s*dead ', section)
    assert not re.search(r'(?m)^\s*stale_verdict ', section)
    for helper in ("ok ", "warn ", "skip "):
        assert helper in section


def test_section_pins_store_root_and_ignores_env_seam():
    section = _block(SECTION_BEGIN, SECTION_END)
    assert 'EV_STORE="$REPO_ROOT/instance/evidence/v1"' in section
    # The untrusted env seam must not be consulted for the store root.
    assert "CABINET_EVIDENCE_DIR" not in section.replace(
        "NOT read from the CABINET_EVIDENCE_DIR env fallback", ""
    )
    for fn in ("evidence_probe_freshness", "evidence_probe_growth", "evidence_probe_chain"):
        assert f'{fn} "$EV_STORE"' in section, f"{fn} not wired to the pinned store"
    # The degradation-marker join is wired for BOTH marker ledgers: the
    # telemetry-mirror ledger (framework/evidence_mirror.py, probed OUTSIDE
    # the store-dir guard) and the act-class lifecycle sidecar.
    assert (
        'EV_MIRROR_MARKER="$REPO_ROOT/cabinet/logs/evidence-mirror-degradations.jsonl"'
        in section
    ), "the mirror degradation marker path is not pinned"
    assert 'evidence_probe_degradations "$EV_MIRROR_MARKER"' in section
    assert 'evidence_probe_degradations "$EV_STORE/degradations.jsonl"' in section


def test_doctor_cap_default_syncs_with_the_enforced_recorder_cap():
    """Seam law (Batch-A reconciliation): EV_CAP_DEFAULT tracks the
    recorder's ENFORCED MAX_TRIAL_EVENTS (the provisional 500) — the bench's
    measured recommendation (512) is recorded beside it in the runbook, and
    retuning is a ceremony follow-up, never a silent doctor-side edit."""
    from framework.evidence import recorder as recorder_mod

    section = _block(SECTION_BEGIN, SECTION_END)
    match = re.search(r"(?m)^EV_CAP_DEFAULT=(\d+)", section)
    assert match, "EV_CAP_DEFAULT missing from the evidence-plane section"
    assert int(match.group(1)) == recorder_mod.MAX_TRIAL_EVENTS


def test_pure_probe_block_uses_no_doctor_globals():
    block = _block(PROBES_BEGIN, PROBES_END)
    for token in ("N_OK", "N_WARN", "DEAD+=", "$REPO_ROOT", "stale_verdict",
                  "ok \"", "warn \"", "skip \"", "dead \""):
        assert token not in block, f"pure probe block leaks doctor coupling: {token}"


# --- behavior: absent / malformed stores -------------------------------------

@pytest.mark.parametrize("fn", ["evidence_probe_freshness", "evidence_probe_growth", "evidence_probe_chain"])
def test_missing_store_skips(probes, tmp_path, fn):
    result = _run(probes, fn, str(tmp_path / "absent"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("SKIP")


@pytest.mark.parametrize("fn", ["evidence_probe_freshness", "evidence_probe_growth", "evidence_probe_chain"])
def test_store_path_is_a_file_never_crashes(probes, tmp_path, fn):
    bogus = tmp_path / "bogus"
    bogus.write_text("not a directory", encoding="utf-8")
    result = _run(probes, fn, str(bogus))
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(("SKIP", "WARN"))


def test_freshness_empty_store_skips(probes, tmp_path):
    store = tmp_path / "store"
    EvidenceRecorder(store)  # store scaffold, zero trials
    result = _run(probes, "evidence_probe_freshness", str(store))
    assert result.returncode == 0
    assert result.stdout.startswith("SKIP no-trials")


# --- freshness ----------------------------------------------------------------

def test_freshness_fresh_store_ok(probes, tmp_path):
    store = _mk_store(tmp_path)
    result = _run(probes, "evidence_probe_freshness", str(store))
    assert result.returncode == 0
    assert result.stdout.startswith("OK age_s=")
    age = int(re.search(r"age_s=(\d+)", result.stdout).group(1))
    assert age < 3600


def test_freshness_stale_store_warns(probes, tmp_path):
    store = _mk_store(tmp_path)
    old = time.time() - 3 * 86400
    for trial_dir in (store / "trials").iterdir():
        for name in ("events.jsonl", "anchor.json"):
            target = trial_dir / name
            if target.exists():
                os.utime(target, (old, old))
    result = _run(probes, "evidence_probe_freshness", str(store))
    assert result.returncode == 0
    assert result.stdout.startswith("WARN stale")


# --- growth --------------------------------------------------------------------

def test_growth_fresh_store_ok(probes, tmp_path):
    store = _mk_store(tmp_path, appends=3)
    result = _run(probes, "evidence_probe_growth", str(store))
    assert result.returncode == 0
    assert result.stdout.startswith("OK kb=")
    assert "biggest_day_trial_events=3" in result.stdout


def test_growth_cap_approach_warns(probes, tmp_path):
    store = _mk_store(tmp_path, appends=5)
    # cap=5 -> warn_at=4; today's day-bounded trial has 5 events
    result = _run(probes, "evidence_probe_growth", str(store), "999999", "5")
    assert result.returncode == 0
    assert result.stdout.startswith("WARN cap-approach")
    # non-taxonomy trials never trip the cap-approach arm
    other = tmp_path / "other"
    recorder = EvidenceRecorder(other)
    for step in range(5):
        recorder.append(
            recorder.trace("plain-trial-doctorprobe", surface="test"),
            phase="system", status="succeeded",
            actor={"kind": "system", "id": "doctor-probe-test"},
            component={"name": "doctor-probe-test", "version": "1", "commit": "unset"},
            detail={"action": "probe_fixture", "step_index": step},
        )
    result = _run(probes, "evidence_probe_growth", str(other), "999999", "5")
    assert result.stdout.startswith("OK")


def test_growth_size_ceiling_warns(probes, tmp_path):
    store = _mk_store(tmp_path)
    result = _run(probes, "evidence_probe_growth", str(store), "0")
    assert result.returncode == 0
    assert result.stdout.startswith("WARN size")


# --- chain continuity -----------------------------------------------------------

def test_chain_fresh_store_ok(probes, tmp_path):
    store = _mk_store(tmp_path, appends=3)
    result = _run(probes, "evidence_probe_chain", str(store), PY)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("OK trial=evt-doctorprobe-"), result.stdout
    assert "events=3" in result.stdout


def test_chain_tampered_store_warns_never_crashes(probes, tmp_path):
    store = _mk_store(tmp_path, appends=3)
    ledger = store / "trials" / f"evt-doctorprobe-{TODAY}" / "events.jsonl"
    tampered = ledger.read_text(encoding="utf-8").replace(
        '"phase": "system"', '"phase": "intent"', 1
    )
    assert tampered != ledger.read_text(encoding="utf-8")
    ledger.write_text(tampered, encoding="utf-8")
    result = _run(probes, "evidence_probe_chain", str(store), PY)
    assert result.returncode == 0
    assert result.stdout.startswith("WARN verify-failed")


def test_chain_old_interpreter_skips(probes, tmp_path):
    store = _mk_store(tmp_path)
    fake = tmp_path / "oldpy"
    fake.write_text("#!/bin/bash\nexit 1\n", encoding="utf-8")
    fake.chmod(0o755)
    result = _run(probes, "evidence_probe_chain", str(store), str(fake))
    assert result.returncode == 0
    assert result.stdout.startswith("SKIP interpreter-too-old")


def test_chain_missing_interpreter_skips(probes, tmp_path):
    store = _mk_store(tmp_path)
    result = _run(probes, "evidence_probe_chain", str(store), "definitely-not-a-python-xyz")
    assert result.returncode == 0
    assert result.stdout.startswith("SKIP no-interpreter")


def test_chain_oversized_trial_bounded_warn(probes, tmp_path):
    store = tmp_path / "store"
    fat = store / "trials" / f"evt-fat-{TODAY}"
    fat.mkdir(parents=True)
    (fat / "events.jsonl").write_text("{}\n" * 10001, encoding="utf-8")
    result = _run(probes, "evidence_probe_chain", str(store), PY)
    assert result.returncode == 0
    assert result.stdout.startswith("WARN oversized")


# --- degradation markers (the mirror/lifecycle -> doctor join) --------------

def test_degradations_probe_absent_marker_ok(probes, tmp_path):
    result = _run(
        probes, "evidence_probe_degradations", str(tmp_path / "absent.jsonl")
    )
    assert result.returncode == 0
    assert result.stdout.startswith("OK no-marker")


def test_degradations_probe_empty_marker_ok(probes, tmp_path):
    marker = tmp_path / "empty.jsonl"
    marker.write_text("", encoding="utf-8")
    result = _run(probes, "evidence_probe_degradations", str(marker))
    assert result.returncode == 0
    assert result.stdout.startswith("OK empty-marker")


def test_degradations_probe_reads_the_real_mirror_marker(
    probes, tmp_path, monkeypatch,
):
    """The join, end-to-end: kill the recorder under the org-event
    chokepoint, let the telemetry mirror's LOUD degradation writer
    (framework/evidence_mirror.py) produce the marker ledger, then prove the
    doctor probe parses THOSE bytes (chokepoint/reason) and goes AMBER."""
    from framework import evidence_mirror
    from framework.events import emitter

    marker = tmp_path / "evidence-mirror-degradations.jsonl"
    store = tmp_path / "scratch-store"
    monkeypatch.setenv("CABINET_EVENT_LOG_DIR", str(tmp_path / "events"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("CABINET_FRAMEWORK_STORE_MIRROR", "0")
    # Pytest-fence overrides — the only way the mirror runs under pytest.
    monkeypatch.setenv("CABINET_EVIDENCE_MIRROR_STORE", str(store))
    monkeypatch.setenv("CABINET_EVIDENCE_MIRROR_MARKER", str(marker))
    evidence_mirror._reset_state()
    try:
        monkeypatch.setattr(
            evidence_mirror, "_recorder",
            lambda root: (_ for _ in ()).throw(RuntimeError("recorder down")),
        )
        event = emitter.emit(
            "need_filed", actor="system", payload={"need_id": "n-doctor"}
        )
        assert event["id"]  # the domain emit survived the dead recorder
    finally:
        evidence_mirror._reset_state()
    assert marker.is_file(), "the mirror did not write its degradation marker"

    result = _run(probes, "evidence_probe_degradations", str(marker))
    assert result.returncode == 0
    assert result.stdout.startswith("WARN degraded"), result.stdout
    assert "rows=1" in result.stdout
    assert "last=org/recorder_error" in result.stdout


def test_degradations_probe_reads_the_act_lifecycle_sidecar(probes, tmp_path):
    """The sibling join: the act-class lifecycle sidecar
    (<store>/degradations.jsonl, component/error_code vocabulary) parses
    through the same probe's fallback fields."""
    from framework.evidence import lifecycle as lifecycle_mod

    store = _mk_store(tmp_path)
    recorder = EvidenceRecorder(store)
    lifecycle_mod._note_degradation(
        recorder,
        trial_id=f"evt-doctorprobe-{TODAY}",
        component_name="doctor-probe-test",
        phase="receipt",
        error_code="io_error",
    )
    sidecar = store / "degradations.jsonl"
    assert sidecar.is_file()
    result = _run(probes, "evidence_probe_degradations", str(sidecar))
    assert result.returncode == 0
    assert result.stdout.startswith("WARN degraded"), result.stdout
    assert "last=doctor-probe-test/io_error" in result.stdout


def test_degradations_probe_old_marker_quiet(probes, tmp_path):
    marker = tmp_path / "m.jsonl"
    marker.write_text(
        '{"ts": "2026-07-01T00:00:00.000000Z", "chokepoint": "org", '
        '"reason": "recorder_error", "message": "x"}\n',
        encoding="utf-8",
    )
    old = time.time() - 30 * 86400
    os.utime(marker, (old, old))
    result = _run(probes, "evidence_probe_degradations", str(marker))
    assert result.returncode == 0
    assert result.stdout.startswith("OK quiet"), result.stdout
    assert "rows=1" in result.stdout
    assert "last=org/recorder_error" in result.stdout


# --- full section wiring (stubbed doctor harness) --------------------------------

def _run_section(tmp_path: Path, fake_root: Path) -> subprocess.CompletedProcess:
    """Execute the whole doctor section with stubbed counters; dead() aborts."""
    script = tmp_path / "section.sh"
    script.write_text(
        "set -u\n"
        f'REPO_ROOT="{fake_root}"\n'
        f'PY="{PY}"\n'
        "SECS_SINCE_WAKE=999999\n"
        "WAKE_GRACE_S=1800\n"
        'ok() { echo "OK     $1"; }\n'
        'warn() { echo "WARN   $1"; }\n'
        'skip() { echo "SKIP   $1"; }\n'
        'waived() { echo "WAIVED $1"; }\n'
        'dead() { echo "DEAD   $1"; exit 97; }\n'
        + _block(SECTION_BEGIN, SECTION_END),
        encoding="utf-8",
    )
    return subprocess.run(
        ["bash", str(script)], capture_output=True, text=True,
        cwd=REPO_ROOT, timeout=120,
    )


def test_full_section_healthy_store_all_ok_lines(tmp_path):
    fake_root = tmp_path / "repo"
    store = fake_root / _ev_store_rel()
    recorder = EvidenceRecorder(store)
    for step in range(2):
        recorder.append(
            recorder.trace(f"evt-doctorprobe-{TODAY}", surface="test"),
            phase="system", status="succeeded",
            actor={"kind": "system", "id": "doctor-probe-test"},
            component={"name": "doctor-probe-test", "version": "1", "commit": "unset"},
            detail={"action": "probe_fixture", "step_index": step},
        )
    result = _run_section(tmp_path, fake_root)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    # mirror-degradations + freshness + growth + chain + act-degradations.
    assert len(lines) == 5, lines
    assert all(line.startswith("OK") for line in lines), lines
    assert any("mirror-degradations" in line for line in lines), lines
    assert any("act-degradations" in line for line in lines), lines
    assert "DEAD" not in result.stdout


def test_full_section_absent_store_skips_with_marker_probe(tmp_path):
    # The store SKIP still fires exactly once; the mirror degradation-marker
    # probe runs OUTSIDE the store guard (a degradation with no store is
    # exactly the loud case) and reads clean on an empty repo.
    result = _run_section(tmp_path, tmp_path / "empty-repo")
    assert result.returncode == 0, result.stdout + result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 2, lines
    assert lines[0].startswith("OK") and "mirror-degradations" in lines[0], lines
    assert lines[1].startswith("SKIP"), lines
    assert "evidence plane not yet activated" in lines[1]


# --- read-only law ---------------------------------------------------------------

def test_freshness_and_growth_probes_are_read_only(probes, tmp_path):
    store = _mk_store(tmp_path)
    before = _snapshot(store)
    for fn, args in (
        ("evidence_probe_freshness", ()),
        ("evidence_probe_growth", ("999999", "512")),
    ):
        result = _run(probes, fn, str(store), *args)
        assert result.returncode == 0
    assert _snapshot(store) == before


def test_chain_probe_never_rewrites_evidence_bytes(probes, tmp_path):
    store = _mk_store(tmp_path, appends=2)
    protected = ("events.jsonl", "anchor.json", "control.json", ".signing-key")
    before = {k: v for k, v in _snapshot(store).items() if k.split("/")[-1] in protected}
    result = _run(probes, "evidence_probe_chain", str(store), PY)
    assert result.returncode == 0
    after = {k: v for k, v in _snapshot(store).items() if k.split("/")[-1] in protected}
    # The verifier's watermark sidecar may appear (protective, sanctioned);
    # evidence bytes must be byte-identical.
    assert after == before
