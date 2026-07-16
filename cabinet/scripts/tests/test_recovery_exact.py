"""Hermetic contracts for the exact Mac recovery drill.

All launchd, tmux, Redis, egress, observe-only, and Doctor calls terminate in
tmpdir fakes.  The suite never reads or mutates the host runtime.
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "cabinet" / "scripts" / "test-recovery.sh"


def _executable(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def _plist(path: Path, label: str) -> None:
    path.write_bytes(plistlib.dumps({"Label": label, "ProgramArguments": ["/usr/bin/true"]}))


@pytest.fixture()
def rig(tmp_path: Path) -> dict[str, Path | dict[str, str]]:
    root = tmp_path / "root"
    (root / "cabinet/scripts").mkdir(parents=True)
    (root / "instance/config").mkdir(parents=True)
    shutil.copy2(REPO / "cabinet/scripts/lib_roster.py", root / "cabinet/scripts/lib_roster.py")
    (root / "cabinet/services.yml").write_text(
        """services:
  - name: alpha
    label: com.cabinet.alpha
    kind: daemon
    schedule: keepalive
  - name: retired
    label: com.cabinet.retired
    kind: daemon
    schedule: keepalive
    disabled: true
""",
        encoding="utf-8",
    )
    (root / "instance/config/roster.yml").write_text(
        """roster:
  chair:
    title: Chair
    type: fulltime
""",
        encoding="utf-8",
    )
    (root / "instance/config/posture-narrow").write_text("earn_up\n", encoding="utf-8")

    home = tmp_path / "home"
    launch_agents = home / "Library/LaunchAgents"
    launch_agents.mkdir(parents=True)
    for label in ("com.cabinet.alpha", "com.cabinet.officer.chair", "com.cabinet.retired"):
        _plist(launch_agents / f"{label}.plist", label)

    state = tmp_path / "labels"
    state.write_text(
        "com.cabinet.alpha\ncom.cabinet.egress-proxy\ncom.cabinet.officer.chair\n",
        encoding="utf-8",
    )
    sessions = tmp_path / "sessions"
    sessions.write_text("officer-chair\n", encoding="utf-8")
    ops = tmp_path / "ops"
    ops.write_text("", encoding="utf-8")

    launchctl = _executable(
        tmp_path / "launchctl",
        """#!/usr/bin/env python3
import os, pathlib, plistlib, sys
state = pathlib.Path(os.environ["FAKE_LABELS"])
sessions = pathlib.Path(os.environ["FAKE_SESSIONS"])
ops = pathlib.Path(os.environ["FAKE_OPS"])
labels = {x for x in state.read_text().splitlines() if x}
argv = sys.argv[1:]
if argv == ["list"]:
    for label in sorted(labels): print(f"123\\t0\\t{label}")
    raise SystemExit(0)
if len(argv) == 2 and argv[0] == "print":
    label = argv[1].rsplit("/", 1)[-1]
    raise SystemExit(0 if label in labels else 1)
if len(argv) == 2 and argv[0] == "bootout":
    label = argv[1].rsplit("/", 1)[-1]
    ops.write_text(ops.read_text() + f"bootout {label}\\n")
    if label not in labels: raise SystemExit(1)
    labels.remove(label)
    state.write_text("".join(f"{x}\\n" for x in sorted(labels)))
    drift = os.environ.get("FAKE_EGRESS_DRIFT_FILE")
    if drift: pathlib.Path(drift).write_text("drift\\n")
    raise SystemExit(0)
if len(argv) == 3 and argv[0] == "bootstrap":
    plist = pathlib.Path(argv[2])
    with plist.open("rb") as fh: label = plistlib.load(fh)["Label"]
    ops.write_text(ops.read_text() + f"bootstrap {label}\\n")
    fail = os.environ.get("FAKE_BOOTSTRAP_FAIL_ONCE")
    marker = pathlib.Path(fail) if fail else None
    target = os.environ.get("FAKE_BOOTSTRAP_FAIL_LABEL")
    if target == label and marker is not None and not marker.exists():
        marker.write_text("failed\\n")
        raise SystemExit(1)
    labels.add(label)
    state.write_text("".join(f"{x}\\n" for x in sorted(labels)))
    if label.startswith("com.cabinet.officer."):
        names = {x for x in sessions.read_text().splitlines() if x}
        names.add("officer-" + label.removeprefix("com.cabinet.officer."))
        sessions.write_text("".join(f"{x}\\n" for x in sorted(names)))
    raise SystemExit(0)
raise SystemExit(64)
""",
    )
    tmux = _executable(
        tmp_path / "tmux",
        """#!/usr/bin/env python3
import os, pathlib, sys
sessions = pathlib.Path(os.environ["FAKE_SESSIONS"])
ops = pathlib.Path(os.environ["FAKE_OPS"])
names = {x for x in sessions.read_text().splitlines() if x}
argv = sys.argv[1:]
if argv[:1] == ["list-sessions"]:
    print("\\n".join(sorted(names)))
    raise SystemExit(0)
if len(argv) == 3 and argv[:2] == ["kill-session", "-t"]:
    name = argv[2].removeprefix("=")
    ops.write_text(ops.read_text() + f"tmux-kill {name}\\n")
    if name not in names: raise SystemExit(1)
    names.remove(name)
    sessions.write_text("".join(f"{x}\\n" for x in sorted(names)))
    raise SystemExit(0)
raise SystemExit(64)
""",
    )
    redis = _executable(tmp_path / "redis-cli", "#!/bin/sh\necho PONG\n")
    observe = _executable(tmp_path / "observe", "#!/bin/sh\necho active\n")
    kill_switch = _executable(
        tmp_path / "kill-switch", "#!/bin/sh\necho 'Kill switch: ACTIVE (all operations halted)'\n"
    )
    egress = _executable(
        tmp_path / "egress",
        """#!/bin/sh
case "$1" in
  runtime-state) printf '1\\t/tmp/fake-proxy.env\\n' ;;
  status)
    if [ -n "${FAKE_EGRESS_DRIFT_FILE:-}" ] && [ -s "$FAKE_EGRESS_DRIFT_FILE" ]; then
      echo 'egress-guard status: DRIFTED'
    else
      echo 'egress-guard status: RUNNING ATTESTED pid=77'
    fi ;;
  *) exit 64 ;;
esac
""",
    )
    doctor = _executable(
        tmp_path / "doctor",
        """#!/bin/sh
count=0
[ ! -f "$FAKE_DOCTOR_COUNT" ] || count=$(cat "$FAKE_DOCTOR_COUNT")
count=$((count + 1))
echo "$count" > "$FAKE_DOCTOR_COUNT"
checks=2
[ "${FAKE_DOCTOR_DRIFT:-0}" = 1 ] && [ "$count" -gt 1 ] && checks=3
if [ "${FAKE_DOCTOR_SUBJECT_DRIFT:-0}" = 1 ]; then
  if [ "$count" -eq 1 ]; then
    echo 'OK     service alpha — running (pid 1)'
    echo 'WARN   service beta — stale 1s'
  else
    echo 'WARN   service alpha — stale 2s'
    echo 'OK     service beta — running (pid 2)'
  fi
fi
echo "CABINET_DOCTOR GREEN (checks=$checks warn=0 waived=0 skip=0)"
""",
    )

    env = {
        **os.environ,
        "HOME": str(home),
        "CABINET_ROOT": str(root),
        "RECOVERY_PYTHON": "python3.12",
        "RECOVERY_LAUNCHCTL": str(launchctl),
        "RECOVERY_TMUX": str(tmux),
        "RECOVERY_REDIS_CLI": str(redis),
        "RECOVERY_OBSERVE_CONTROL": str(observe),
        "RECOVERY_KILL_SWITCH_CONTROL": str(kill_switch),
        "RECOVERY_EGRESS_GUARD": str(egress),
        "RECOVERY_DOCTOR": str(doctor),
        "RECOVERY_LAUNCH_AGENTS_DIR": str(launch_agents),
        "RECOVERY_POLL_INTERVAL": "0",
        "FAKE_LABELS": str(state),
        "FAKE_SESSIONS": str(sessions),
        "FAKE_OPS": str(ops),
        "FAKE_DOCTOR_COUNT": str(tmp_path / "doctor-count"),
    }
    return {
        "root": root,
        "home": home,
        "launch_agents": launch_agents,
        "state": state,
        "sessions": sessions,
        "ops": ops,
        "env": env,
        "tmp": tmp_path,
    }


def _run(rig: dict[str, Path | dict[str, str]], *args: str, extra: dict[str, str] | None = None):
    env = {**rig["env"], **(extra or {})}  # type: ignore[arg-type]
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_exact_drill_restores_only_enabled_fleet_and_preserves_egress(rig):
    evidence = rig["tmp"] / "evidence"
    proc = _run(rig, "--timeout", "5", "--evidence-dir", str(evidence))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "RECOVERY DRILL PASSED" in proc.stdout
    assert rig["state"].read_text().splitlines() == [
        "com.cabinet.alpha",
        "com.cabinet.egress-proxy",
        "com.cabinet.officer.chair",
    ]
    assert rig["sessions"].read_text() == "officer-chair\n"
    operations = rig["ops"].read_text().splitlines()
    assert operations == [
        "bootout com.cabinet.alpha",
        "bootout com.cabinet.officer.chair",
        "tmux-kill officer-chair",
        "bootstrap com.cabinet.alpha",
        "bootstrap com.cabinet.officer.chair",
    ]
    assert all("retired" not in x and "egress-proxy" not in x for x in operations)
    assert (evidence / "pre.doctor-result").read_text() == (
        evidence / "post.doctor-result"
    ).read_text()
    assert (evidence / "result.txt").read_text().startswith("RECOVERY DRILL PASSED")


def test_dry_run_is_a_verified_non_mutating_snapshot(rig):
    proc = _run(rig, "--dry-run")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DRY-RUN PASS" in proc.stdout
    assert rig["ops"].read_text() == ""


@pytest.mark.parametrize("unexpected", ["com.cabinet.retired", "com.cabinet.legacy"])
def test_loaded_disabled_or_legacy_label_is_refused_before_mutation(rig, unexpected):
    rig["state"].write_text(rig["state"].read_text() + unexpected + "\n")
    proc = _run(rig)
    assert proc.returncode != 0
    assert "disabled/legacy/missing activation refused" in proc.stderr
    assert rig["ops"].read_text() == ""


def test_missing_enabled_label_is_refused_before_mutation(rig):
    rig["state"].write_text(
        "com.cabinet.egress-proxy\ncom.cabinet.officer.chair\n", encoding="utf-8"
    )
    proc = _run(rig)
    assert proc.returncode != 0
    assert "disabled/legacy/missing activation refused" in proc.stderr
    assert rig["ops"].read_text() == ""


def test_officer_session_drift_is_refused_before_mutation(rig):
    rig["sessions"].write_text("officer-chair\nofficer-retired\n", encoding="utf-8")
    proc = _run(rig)
    assert proc.returncode != 0
    assert "sessions do not exactly equal roster" in proc.stderr
    assert rig["ops"].read_text() == ""


def test_egress_change_during_teardown_fails_and_trap_restores_enabled_only(rig):
    drift = rig["tmp"] / "egress-drift"
    proc = _run(rig, extra={"FAKE_EGRESS_DRIFT_FILE": str(drift)})
    assert proc.returncode != 0
    assert "egress status during teardown changed" in proc.stderr
    assert sorted(rig["state"].read_text().splitlines()) == [
        "com.cabinet.alpha",
        "com.cabinet.egress-proxy",
        "com.cabinet.officer.chair",
    ]
    operations = rig["ops"].read_text().splitlines()
    assert "bootstrap com.cabinet.alpha" in operations
    assert "bootstrap com.cabinet.officer.chair" in operations
    assert all("retired" not in x and "egress-proxy" not in x for x in operations)


def test_one_bootstrap_failure_uses_allowlisted_trap_recovery(rig):
    marker = rig["tmp"] / "fail-once"
    proc = _run(
        rig,
        extra={
            "FAKE_BOOTSTRAP_FAIL_LABEL": "com.cabinet.alpha",
            "FAKE_BOOTSTRAP_FAIL_ONCE": str(marker),
        },
    )
    assert proc.returncode != 0
    assert "bootstrap failed for enabled label com.cabinet.alpha" in proc.stderr
    assert sorted(rig["state"].read_text().splitlines()) == [
        "com.cabinet.alpha",
        "com.cabinet.egress-proxy",
        "com.cabinet.officer.chair",
    ]
    operations = rig["ops"].read_text().splitlines()
    assert operations.count("bootstrap com.cabinet.alpha") == 2
    assert operations.count("bootstrap com.cabinet.officer.chair") == 1
    assert all("retired" not in x and "egress-proxy" not in x for x in operations)


def test_doctor_semantic_result_must_be_exact_after_recovery(rig):
    proc = _run(rig, extra={"FAKE_DOCTOR_DRIFT": "1"})
    assert proc.returncode != 0
    assert "Cabinet Doctor semantic result changed" in proc.stderr


def test_doctor_equal_counts_cannot_hide_changed_check_classification(rig):
    proc = _run(rig, extra={"FAKE_DOCTOR_SUBJECT_DRIFT": "1"})
    assert proc.returncode != 0
    assert "Cabinet Doctor semantic result changed" in proc.stderr


def test_invalid_installed_plist_fails_before_runtime_read_or_mutation(rig):
    plist = rig["launch_agents"] / "com.cabinet.alpha.plist"
    plist.write_text("not a plist", encoding="utf-8")
    proc = _run(rig)
    assert proc.returncode != 0
    assert "installed plist is invalid" in proc.stderr
    assert rig["ops"].read_text() == ""


def test_wrong_observe_posture_refuses_drill(rig):
    (rig["root"] / "instance/config/posture-narrow").write_text("guardian\n")
    proc = _run(rig)
    assert proc.returncode != 0
    assert "PRE snapshot/attestation failed" in proc.stderr
    assert rig["ops"].read_text() == ""


def test_inactive_kill_switch_refuses_before_mutation(rig):
    inactive = _executable(
        rig["tmp"] / "inactive-kill-switch",
        "#!/bin/sh\necho 'Kill switch: INACTIVE (normal operation)'\n",
    )
    proc = _run(rig, extra={"RECOVERY_KILL_SWITCH_CONTROL": str(inactive)})
    assert proc.returncode != 0
    assert "PRE snapshot/attestation failed" in proc.stderr
    assert rig["ops"].read_text() == ""


def test_evidence_directory_must_be_empty_and_is_not_overwritten(rig):
    evidence = rig["tmp"] / "existing-evidence"
    evidence.mkdir()
    sentinel = evidence / "sentinel"
    sentinel.write_text("keep\n")
    proc = _run(rig, "--dry-run", "--evidence-dir", str(evidence))
    assert proc.returncode == 73
    assert "evidence directory must be empty" in proc.stderr
    assert sentinel.read_text() == "keep\n"
    assert rig["ops"].read_text() == ""


def test_help_prints_only_the_header_comment_and_never_leaks_code(rig):
    # --help must exit before any live check, so it is safe to run with a
    # completely bare environment (no fakes needed).
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Usage:" in proc.stdout
    assert "exact, non-reboot recovery drill" in proc.stdout
    for leaked in ("set -uo pipefail", "SCRIPT_DIR=", "CABINET_ROOT=", "#!/bin/bash"):
        assert leaked not in proc.stdout, f"help output leaked a code line: {leaked!r}"
