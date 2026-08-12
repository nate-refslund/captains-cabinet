"""Hermetic contracts for deploy-mac.sh --all exact-fleet reconciliation.

The suite uses a synthetic repository, HOME and launchctl state. It never
reads or mutates the host's LaunchAgents.
"""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[3]
DEPLOY = REPO / "cabinet" / "scripts" / "deploy-mac.sh"
GENERATOR = REPO / "cabinet" / "scripts" / "generate-plists.py"
DOCTOR = REPO / "cabinet" / "scripts" / "cabinet-doctor.sh"


def _plist(path: Path, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        plistlib.dump({"Label": label, "ProgramArguments": ["/usr/bin/true"]}, fh)


def _seed(tmp_path: Path, *, invalid_kind: bool = False) -> tuple[Path, Path, dict[str, str]]:
    root = tmp_path / "repo"
    home = tmp_path / "home"
    scripts = root / "cabinet" / "scripts"
    launchd = root / "cabinet" / "launchd"
    generated = launchd / "generated"
    roster = root / "instance" / "config"
    fake_bin = tmp_path / "bin"
    for path in (scripts, launchd, generated, roster, fake_bin, home / "Library" / "LaunchAgents"):
        path.mkdir(parents=True, exist_ok=True)

    shutil.copy2(DEPLOY, scripts / DEPLOY.name)
    shutil.copy2(GENERATOR, scripts / GENERATOR.name)
    shutil.copy2(REPO / "cabinet" / "scripts" / "lib_roster.py", scripts / "lib_roster.py")
    sync = scripts / "sync-agents.sh"
    sync.write_text('#!/bin/sh\ntouch "$CABINET_ROOT/sync-ran"\n', encoding="utf-8")
    sync.chmod(0o755)

    (roster / "roster.yml").write_text(
        "roster:\n"
        "  cos:\n"
        "    officer_type: fulltime\n"
        "  builder:\n"
        "    officer_type: fulltime\n",
        encoding="utf-8",
    )
    (root / "instance" / "roles" / "active").mkdir(parents=True)

    kind = "unknown-kind" if invalid_kind else "daemon"
    services = {
        "services": [
            {
                "name": "alpha",
                "label": "com.cabinet.alpha",
                "kind": kind,
                "command": "bash cabinet/scripts/alpha.sh",
                "schedule": "keepalive",
            },
            {
                "name": "retired",
                "label": "com.cabinet.retired",
                "kind": "daemon",
                "command": "bash cabinet/scripts/retired.sh",
                "schedule": "keepalive",
                "disabled": True,
            },
        ]
    }
    (root / "cabinet" / "services.yml").write_text(
        yaml.safe_dump(services, sort_keys=False), encoding="utf-8"
    )
    (launchd / "com.cabinet.officer.template.plist").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.cabinet.officer.${OFFICER}</string>
<key>ProgramArguments</key><array><string>/usr/bin/true</string></array>
<key>WorkingDirectory</key><string>${REPO_ROOT}</string>
</dict></plist>
""",
        encoding="utf-8",
    )

    # A prior generator run and prior runtime both contain stale entries.
    _plist(generated / "com.cabinet.stale-generated.plist", "com.cabinet.stale-generated")
    agents = home / "Library" / "LaunchAgents"
    for label in ("com.cabinet.retired", "com.cabinet.legacy", "com.cabinet.egress-proxy"):
        _plist(agents / f"{label}.plist", label)

    state = tmp_path / "launchctl-state"
    state.write_text(
        "\n".join(
            (
                "com.cabinet.retired",
                "com.cabinet.legacy",
                "com.cabinet.fileless-legacy",
                "com.cabinet.egress-proxy",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    log = tmp_path / "launchctl-log"
    fake_launchctl = fake_bin / "launchctl"
    fake_launchctl.write_text(
        f"""#!{sys.executable}
import os, plistlib, sys
from pathlib import Path
state = Path(os.environ["FAKE_LAUNCHCTL_STATE"])
log = Path(os.environ["FAKE_LAUNCHCTL_LOG"])
args = sys.argv[1:]
labels = set(state.read_text().split()) if state.exists() else set()
with log.open("a") as fh: fh.write(" ".join(args) + "\\n")
def save(): state.write_text("\\n".join(sorted(labels)) + ("\\n" if labels else ""))
if args[0] == "list":
    for label in sorted(labels): print(f"123\\t0\\t{{label}}")
    raise SystemExit(0)
if args[0] == "print":
    label = args[-1].rsplit("/", 1)[-1]
    raise SystemExit(0 if label in labels else 113)
if args[0] == "bootstrap":
    with open(args[-1], "rb") as fh: label = plistlib.load(fh)["Label"]
    fail_label = os.environ.get("FAKE_FAIL_BOOTSTRAP_ONCE", "")
    fail_times = int(os.environ.get("FAKE_FAIL_BOOTSTRAP_TIMES", "1"))
    counter = state.with_suffix(".failed-count")
    seen = int(counter.read_text()) if counter.exists() else 0
    if label == fail_label and seen < fail_times:
        counter.write_text(str(seen + 1)); raise SystemExit(5)
    labels.add(label); save(); raise SystemExit(0)
if args[0] == "bootout":
    target = args[-1]
    if target.endswith(".plist") and Path(target).exists():
        with open(target, "rb") as fh: label = plistlib.load(fh)["Label"]
    else:
        label = target.rsplit("/", 1)[-1]
    labels.discard(label); save(); raise SystemExit(0)
raise SystemExit(64)
""",
        encoding="utf-8",
    )
    fake_launchctl.chmod(0o755)
    fake_plutil = fake_bin / "plutil"
    fake_plutil.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_plutil.chmod(0o755)

    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "CABINET_ROOT": str(root),
        "CABINET_SOURCE_REPO": str(root),
        "CABINET_PYTHON": sys.executable,
        "CABINET_LAUNCHCTL": str(fake_launchctl),
        "CABINET_DEPLOY_BOOTOUT_DELAY_S": "0",
        "FAKE_LAUNCHCTL_STATE": str(state),
        "FAKE_LAUNCHCTL_LOG": str(log),
    }
    return root, home, env


def _run(root: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(root / "cabinet" / "scripts" / "deploy-mac.sh"), *args],
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )


def test_all_installs_exact_enabled_manifest_and_roster_and_preserves_egress(tmp_path: Path):
    root, home, env = _seed(tmp_path)
    egress = home / "Library" / "LaunchAgents" / "com.cabinet.egress-proxy.plist"
    egress_before = egress.read_bytes()

    proc = _run(root, env, "--all")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    agents = home / "Library" / "LaunchAgents"
    expected = {
        "com.cabinet.alpha",
        "com.cabinet.officer.cos",
        "com.cabinet.officer.builder",
        "com.cabinet.egress-proxy",
    }
    assert set(Path(env["FAKE_LAUNCHCTL_STATE"]).read_text().split()) == expected
    assert {p.stem for p in agents.glob("com.cabinet.*.plist")} == expected
    assert (agents / "com.cabinet.retired.plist.disabled").exists()
    assert (agents / "com.cabinet.legacy.plist.disabled").exists()
    assert egress.read_bytes() == egress_before
    assert "bootout gui/" not in "\n".join(
        line for line in Path(env["FAKE_LAUNCHCTL_LOG"]).read_text().splitlines()
        if "egress-proxy" in line
    )

    generated = root / "cabinet" / "launchd" / "generated"
    assert {p.name for p in generated.glob("com.cabinet.*.plist")} == {
        "com.cabinet.alpha.plist"
    }
    assert (root / "sync-ran").exists()
    assert "exact fleet reconciled (3 manifest+roster jobs)" in proc.stdout


def test_all_invalid_manifest_fails_before_any_runtime_or_generated_mutation(tmp_path: Path):
    root, home, env = _seed(tmp_path, invalid_kind=True)
    agents = home / "Library" / "LaunchAgents"
    before_files = {p.name: p.read_bytes() for p in agents.iterdir()}
    before_state = Path(env["FAKE_LAUNCHCTL_STATE"]).read_bytes()
    stale = root / "cabinet" / "launchd" / "generated" / "com.cabinet.stale-generated.plist"

    proc = _run(root, env, "--all")
    assert proc.returncode != 0
    assert "unknown kind" in proc.stdout + proc.stderr
    assert {p.name: p.read_bytes() for p in agents.iterdir()} == before_files
    assert Path(env["FAKE_LAUNCHCTL_STATE"]).read_bytes() == before_state
    assert stale.exists(), "failed preflight must not publish or prune generated output"
    assert not (root / "sync-ran").exists()
    assert not Path(env["FAKE_LAUNCHCTL_LOG"]).exists()


def test_all_dry_run_is_write_free_but_shows_exact_reconciliation(tmp_path: Path):
    root, home, env = _seed(tmp_path)
    agents = home / "Library" / "LaunchAgents"
    before_files = {p.name: p.read_bytes() for p in agents.iterdir()}
    before_state = Path(env["FAKE_LAUNCHCTL_STATE"]).read_bytes()
    stale = root / "cabinet" / "launchd" / "generated" / "com.cabinet.stale-generated.plist"

    proc = _run(root, env, "--all", "--dry-run")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.count("WOULD-BOOTSTRAP") == 3
    assert "WOULD-BOOTOUT unexpected com.cabinet.retired" in proc.stdout
    assert "WOULD-BOOTOUT unexpected com.cabinet.legacy" in proc.stdout
    assert "unexpected com.cabinet.egress-proxy" not in proc.stdout
    assert {p.name: p.read_bytes() for p in agents.iterdir()} == before_files
    assert Path(env["FAKE_LAUNCHCTL_STATE"]).read_bytes() == before_state
    assert stale.exists()
    assert not (root / "sync-ran").exists()


def test_bootstrap_failure_restores_previous_plist_and_loaded_job(tmp_path: Path):
    """A PERSISTENT bootstrap failure still rolls back, unchanged.

    TIMES=2 since 2026-08-12: install_plist_file now retries once after an
    unconditional bootout, so a single failure is recovered (the sibling test
    below) and only a failure that survives the retry reaches the rollback.
    The rollback's own bootstrap — the third — succeeds, as before.
    """
    root, home, env = _seed(tmp_path)
    alpha = home / "Library" / "LaunchAgents" / "com.cabinet.alpha.plist"
    _plist(alpha, "com.cabinet.alpha")
    alpha_before = alpha.read_bytes()
    state = Path(env["FAKE_LAUNCHCTL_STATE"])
    state.write_text(state.read_text() + "com.cabinet.alpha\n", encoding="utf-8")
    env["FAKE_FAIL_BOOTSTRAP_ONCE"] = "com.cabinet.alpha"
    env["FAKE_FAIL_BOOTSTRAP_TIMES"] = "2"

    proc = _run(root, env, "--all")
    assert proc.returncode == 2
    assert "attempting per-service rollback" in proc.stderr
    assert alpha.read_bytes() == alpha_before
    assert "com.cabinet.alpha" in state.read_text().split()
    assert "ROLLBACK FAILED" not in proc.stderr


def test_transient_bootstrap_failure_recovers_via_bootout_retry(tmp_path: Path):
    """The measured operator failure, end to end through the real script.

    launchd's `Bootstrap failed: 5` on an already-loaded label used to fail the
    whole officer deploy — which, on the app path, ended the hatch before the
    browser handover. One bootout-first retry recovers it; the NEW plist is
    what stays installed, and no rollback runs.
    """
    root, home, env = _seed(tmp_path)
    alpha = home / "Library" / "LaunchAgents" / "com.cabinet.alpha.plist"
    _plist(alpha, "com.cabinet.alpha")
    alpha_before = alpha.read_bytes()
    state = Path(env["FAKE_LAUNCHCTL_STATE"])
    state.write_text(state.read_text() + "com.cabinet.alpha\n", encoding="utf-8")
    env["FAKE_FAIL_BOOTSTRAP_ONCE"] = "com.cabinet.alpha"  # TIMES defaults to 1

    proc = _run(root, env, "--all")
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "after a bootout-first retry" in proc.stdout
    assert "attempting per-service rollback" not in proc.stderr
    assert "com.cabinet.alpha" in state.read_text().split(), "job must end up loaded"
    assert alpha.read_bytes() != alpha_before, (
        "the freshly rendered plist must be what survives a recovered deploy"
    )


def test_generator_refuses_runtime_launchagents_output_without_touching_it(tmp_path: Path):
    root, home, env = _seed(tmp_path)
    agents = home / "Library" / "LaunchAgents"
    before = {p.name: p.read_bytes() for p in agents.iterdir()}
    proc = subprocess.run(
        [
            sys.executable,
            str(root / "cabinet" / "scripts" / "generate-plists.py"),
            "--output-dir",
            str(agents),
        ],
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode != 0
    assert "refusing --output-dir ~/Library/LaunchAgents" in proc.stderr
    assert {p.name: p.read_bytes() for p in agents.iterdir()} == before


def test_generator_custom_staging_never_prunes_existing_cabinet_plists(tmp_path: Path):
    root, _home, env = _seed(tmp_path)
    staging = tmp_path / "operator-staging"
    _plist(staging / "com.cabinet.officer.keep.plist", "com.cabinet.officer.keep")
    before = (staging / "com.cabinet.officer.keep.plist").read_bytes()
    proc = subprocess.run(
        [
            sys.executable,
            str(root / "cabinet" / "scripts" / "generate-plists.py"),
            "--output-dir",
            str(staging),
        ],
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (staging / "com.cabinet.officer.keep.plist").read_bytes() == before
    assert (staging / "com.cabinet.alpha.plist").exists()
    assert "custom output dir: stale-prune skipped" in proc.stdout


def test_doctor_fails_closed_on_unexpected_loaded_or_installed_cabinet_jobs():
    text = DOCTOR.read_text(encoding="utf-8")
    assert "service-set — unexpected Cabinet launchd label" in text
    assert 'EXPECTED_FLEET_LABELS="${EXPECTED_FLEET_LABELS}"' in text
    assert "com.cabinet.egress-proxy" in text
