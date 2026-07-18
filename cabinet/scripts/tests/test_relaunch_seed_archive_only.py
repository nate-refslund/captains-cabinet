"""Contract tests for the archive-only relaunch seeder + the Wave-2 deploy
hardening (Captain 100%-SCRATCH ruling, 2026-07-18).

relaunch-seed.sh no longer seeds ANY live content into a runtime root — the
fresh instance inherits nothing (it is produced by hatch.sh --defaults). This
script's one job is a full, restorable pre-cutover safety archive. These tests
pin:
  * the seed target stays EMPTY of live content (nothing carried forward);
  * the archive CONTAINS the vault (org-brain/memory) + every lane's tier2 +
    the governance ledgers + the real cabinet/.env — nothing lost;
  * no secret VALUE ever leaks to stdout/stderr;
  * the --archive-path containment fix: a RELATIVE archive path is absolutized
    BEFORE the nesting guards, so one resolving into old-root is refused
    (exit 64) and one resolving elsewhere lands there, not inside old-root.

And, for cabinet-deploy.sh's Wave-2 hardening (bounded behavioral smoke):
  * restart_fleet SKIPS an officer_type: consultant role (on-demand, never a
    persistent restart);
  * a NON-canonical --runtime-root never `launchctl kickstart`s a colliding
    live LaunchAgent; the canonical live root does (positive control);
  * the lib_roster label-allowlist gate rejects an unsafe roster-derived
    officer label instead of returning it as a shell token;
  * `bash -n` stays clean on all three edited scripts.

Hermetic by construction: HOME is pinned at a pytest tmp dir, all paths are
explicit, the appsupport archive half is skipped, and the deploy tests shim
`launchctl` + the slot's own start-officer-mac.sh on PATH so no real launchd
state is read or touched (same read-only posture as the sibling script tests).
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SEED = REPO / "cabinet" / "scripts" / "relaunch-seed.sh"
DEPLOY = REPO / "cabinet" / "scripts" / "cabinet-deploy.sh"
PROVISION = REPO / "cabinet" / "scripts" / "runtime-provision.sh"
LIB_ROSTER = REPO / "cabinet" / "scripts" / "lib_roster.py"

FAKE_SECRET = "supersecret-value-do-not-leak-42"


# --------------------------------------------------------------------------
# relaunch-seed.sh — archive-only fixture + runner
# --------------------------------------------------------------------------
def _build_old_root(base: Path) -> Path:
    """A temp old-root carrying live-content bait across every class the old
    seeder used to copy: secrets, per-lane memory, capability config, the
    regression corpus, a product-spec, and a governance ledger."""
    old = base / "old-cabinet"
    (old / "cabinet").mkdir(parents=True)
    (old / "cabinet" / ".env").write_text(
        f"SOME_SECRET={FAKE_SECRET}\nTELEGRAM_COS_TOKEN=abc123\n", encoding="utf-8"
    )
    (old / "instance" / "memory" / "tier2" / "polads-ceo").mkdir(parents=True)
    (old / "instance" / "memory" / "tier2" / "polads-ceo" / "working-notes.md").write_text(
        "# polads-ceo working notes\n", encoding="utf-8"
    )
    (old / "instance" / "config").mkdir(parents=True)
    (old / "instance" / "config" / "extensions.yml").write_text("ext: []\n", encoding="utf-8")
    (old / "instance" / "config" / "extra-mcps.json").write_text("{}\n", encoding="utf-8")
    (old / "instance" / "fidelity" / "regression_corpus" / "cases").mkdir(parents=True)
    (old / "instance" / "fidelity" / "regression_corpus" / "cases" / "x.json").write_text(
        "{}\n", encoding="utf-8"
    )
    (old / "shared" / "interfaces" / "product-specs").mkdir(parents=True)
    (old / "shared" / "interfaces" / "product-specs" / "060-stephie-banner.md").write_text(
        "spec\n", encoding="utf-8"
    )
    (old / "shared" / "interfaces" / "world-chronicle.jsonl").write_text(
        '{"e":"boot"}\n', encoding="utf-8"
    )
    # regenerable noise the archive must exclude
    (old / "instance" / "__pycache__").mkdir(parents=True)
    (old / "instance" / "__pycache__" / "junk.pyc").write_text("junk\n", encoding="utf-8")
    return old


def _run_seed(args: list[str], home: Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run(
        ["bash", str(SEED), *args],
        env=env,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.fixture()
def old_root(tmp_path: Path) -> Path:
    return _build_old_root(tmp_path)


def test_seed_dir_stays_empty_of_live_content(tmp_path: Path, old_root: Path):
    rt = tmp_path / "rt"
    archive = tmp_path / "safety.tar.gz"
    proc = _run_seed(
        ["--old-root", str(old_root), "--runtime-root", str(rt),
         "--archive-path", str(archive), "--skip-appsupport-archive"],
        home=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    # The archive is written OUTSIDE rt; rt itself must hold no seeded file.
    seeded_files = [p for p in rt.rglob("*") if p.is_file()]
    assert seeded_files == [], f"archive-only seeder wrote into the runtime root: {seeded_files}"
    # Named absences the old seeder would have produced.
    assert not (rt / "shared" / "cabinet.env").exists()
    assert not (rt / "shared" / "instance" / "memory").exists()
    assert not (rt / "shared" / "instance" / "config" / "extensions.yml").exists()
    assert not (rt / "shared" / "instance" / "config" / "extra-mcps.json").exists()
    assert not (rt / "shared" / "instance" / "fidelity").exists()
    assert not (rt / "shared" / "shared" / "interfaces" / "product-specs").exists()


def test_archive_contains_vault_lanes_ledgers_secrets(tmp_path: Path, old_root: Path):
    rt = tmp_path / "rt"
    archive = tmp_path / "safety.tar.gz"
    proc = _run_seed(
        ["--old-root", str(old_root), "--runtime-root", str(rt),
         "--archive-path", str(archive), "--skip-appsupport-archive"],
        home=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    assert archive.exists(), "archive not written"
    base = old_root.name  # member prefix = old-root basename
    with tarfile.open(archive, "r:gz") as tf:
        names = set(tf.getnames())
    # vault / org-brain memory + lane tier2 + governance ledger + real secret
    assert f"{base}/instance/memory/tier2/polads-ceo/working-notes.md" in names
    assert f"{base}/shared/interfaces/world-chronicle.jsonl" in names
    assert f"{base}/cabinet/.env" in names
    # regenerable noise excluded
    assert not any("__pycache__" in n for n in names), "archive kept __pycache__"
    assert not any(n.endswith(".pyc") for n in names), "archive kept .pyc"


def test_archive_is_mode_restricted(tmp_path: Path, old_root: Path):
    rt = tmp_path / "rt"
    archive = tmp_path / "safety.tar.gz"
    proc = _run_seed(
        ["--old-root", str(old_root), "--runtime-root", str(rt),
         "--archive-path", str(archive), "--skip-appsupport-archive"],
        home=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    mode = stat.S_IMODE(archive.stat().st_mode)
    assert mode == 0o600, f"archive holds the real .env; expected 0600, got {oct(mode)}"


def test_no_secret_value_leaks_to_output(tmp_path: Path, old_root: Path):
    rt = tmp_path / "rt"
    archive = tmp_path / "safety.tar.gz"
    proc = _run_seed(
        ["--old-root", str(old_root), "--runtime-root", str(rt),
         "--archive-path", str(archive), "--skip-appsupport-archive"],
        home=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    assert FAKE_SECRET not in proc.stdout
    assert FAKE_SECRET not in proc.stderr


def test_relative_archive_path_inside_old_root_is_refused(tmp_path: Path, old_root: Path):
    """cwd inside old-root + a RELATIVE --archive-path resolves into the
    read-only source. The absolutize-before-guard fix must refuse it (64) and
    write no tar anywhere under old-root."""
    rt = tmp_path / "rt"  # safe runtime root (separate tree)
    proc = _run_seed(
        ["--old-root", str(old_root), "--runtime-root", str(rt),
         "--archive-path", "sneaky.tar.gz", "--skip-appsupport-archive"],
        home=tmp_path,
        cwd=old_root,
    )
    assert proc.returncode == 64, (proc.stdout, proc.stderr)
    assert "archive-path" in proc.stderr
    strays = list(old_root.rglob("*.tar.gz"))
    assert strays == [], f"a refused run still wrote a tar inside old-root: {strays}"


def test_relative_archive_path_outside_old_root_is_absolutized(tmp_path: Path, old_root: Path):
    """cwd OUTSIDE old-root + a relative --archive-path is absolutized to
    $PWD/... and lands there, never inside old-root."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    rt = tmp_path / "rt"
    proc = _run_seed(
        ["--old-root", str(old_root), "--runtime-root", str(rt),
         "--archive-path", "out.tar.gz", "--skip-appsupport-archive"],
        home=tmp_path,
        cwd=workdir,
    )
    assert proc.returncode == 0, proc.stderr
    assert (workdir / "out.tar.gz").exists(), "relative archive did not land at $PWD"
    assert list(old_root.rglob("*.tar.gz")) == [], "archive leaked into old-root"


def test_dry_run_writes_nothing(tmp_path: Path, old_root: Path):
    rt = tmp_path / "rt"
    archive = tmp_path / "safety.tar.gz"
    proc = _run_seed(
        ["--old-root", str(old_root), "--runtime-root", str(rt),
         "--archive-path", str(archive), "--skip-appsupport-archive", "--dry-run"],
        home=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    assert not archive.exists()
    assert "DRY RUN" in proc.stdout
    assert "would tar" in proc.stdout


# --------------------------------------------------------------------------
# cabinet-deploy.sh — Wave-2 hardening (bounded behavioral smoke)
# --------------------------------------------------------------------------
def _make_slot(slot: Path, roster: str, roles: dict[str, str]) -> None:
    (slot / "cabinet" / "scripts").mkdir(parents=True)
    # real lib_roster so officer_service_rows() runs for-real
    (slot / "cabinet" / "scripts" / "lib_roster.py").write_text(
        LIB_ROSTER.read_text(encoding="utf-8"), encoding="utf-8"
    )
    # start-officer-mac.sh shim: records which officers were (re)started
    starter = slot / "cabinet" / "scripts" / "start-officer-mac.sh"
    starter.write_text(
        '#!/bin/bash\necho "START-OFFICER $1" >> "$STARTED_LOG"\n', encoding="utf-8"
    )
    starter.chmod(0o755)
    (slot / "instance" / "config").mkdir(parents=True)
    (slot / "instance" / "config" / "roster.yml").write_text(roster, encoding="utf-8")
    (slot / "instance" / "roles" / "active").mkdir(parents=True)
    for name, otype in roles.items():
        (slot / "instance" / "roles" / "active" / f"{name}.yml").write_text(
            f"officer_type: {otype}\n", encoding="utf-8"
        )


def _make_runtime_root(rt: Path, slot: Path) -> None:
    (rt / "repo.git").mkdir(parents=True)
    (rt / "releases").mkdir(parents=True)
    # rollback swaps current<->previous; point both at the one slot so the
    # post-swap `current` still resolves to it.
    (rt / "current").symlink_to(slot)
    (rt / "previous").symlink_to(slot)


def _make_fake_launchctl(bindir: Path) -> None:
    bindir.mkdir(parents=True, exist_ok=True)
    lc = bindir / "launchctl"
    # logs every invocation; `print` exit code is controllable via env so a
    # test can simulate "agent loaded" (0) vs "not loaded" (non-zero).
    lc.write_text(
        '#!/bin/bash\n'
        'echo "$*" >> "$LAUNCHCTL_LOG"\n'
        'case "$1" in\n'
        '  print) exit "${FAKE_PRINT_RC:-1}" ;;\n'
        '  *) exit 0 ;;\n'
        'esac\n',
        encoding="utf-8",
    )
    lc.chmod(0o755)


def _run_deploy(action: str, rt: Path, home: Path, extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    bindir = home / "shimbin"
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{bindir}:{os.environ.get('PATH', '')}",
        "CABINET_PYTHON": sys.executable,  # hermetic: same interpreter (has yaml)
        **extra_env,
    }
    return subprocess.run(
        ["bash", str(DEPLOY), action, "--runtime-root", str(rt)],
        env=env, capture_output=True, text=True, timeout=120,
    )


ROSTER_TWO = "roster:\n  cos:\n    title: Chief of Staff\n  polads-ceo:\n    title: PolAds CEO\n"


def test_restart_fleet_skips_consultant(tmp_path: Path):
    home = tmp_path
    slot = tmp_path / "slot"
    rt = tmp_path / "rt"
    _make_slot(slot, ROSTER_TWO, {"cos": "standing", "polads-ceo": "consultant"})
    _make_runtime_root(rt, slot)
    _make_fake_launchctl(home / "shimbin")
    started_log = tmp_path / "started.log"
    lc_log = tmp_path / "launchctl.log"
    proc = _run_deploy(
        "rollback", rt, home,
        {"STARTED_LOG": str(started_log), "LAUNCHCTL_LOG": str(lc_log), "FAKE_PRINT_RC": "1"},
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "skipping polads-ceo" in proc.stdout
    started = started_log.read_text(encoding="utf-8") if started_log.exists() else ""
    assert "START-OFFICER cos" in started
    assert "polads-ceo" not in started, "consultant was restarted — guard failed"


def test_non_canonical_root_never_kickstarts_live_agent(tmp_path: Path):
    home = tmp_path
    slot = tmp_path / "slot"
    rt = tmp_path / "rt"  # NOT ~/.cabinet/runtime → non-canonical
    _make_slot(slot, "roster:\n  cos:\n    title: Chief of Staff\n", {"cos": "standing"})
    _make_runtime_root(rt, slot)
    _make_fake_launchctl(home / "shimbin")
    lc_log = tmp_path / "launchctl.log"
    proc = _run_deploy(
        "rollback", rt, home,
        {"STARTED_LOG": str(tmp_path / "s.log"), "LAUNCHCTL_LOG": str(lc_log), "FAKE_PRINT_RC": "0"},
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "[non-canonical runtime root] would kickstart" in proc.stdout
    lc = lc_log.read_text(encoding="utf-8") if lc_log.exists() else ""
    assert "kickstart" not in lc, "a scratch root SIGKILLed a live LaunchAgent"


def test_canonical_root_kickstarts_live_agent(tmp_path: Path):
    """Positive control: when --runtime-root IS the canonical live root, a
    loaded agent IS kickstarted (the confinement is a gate, not a blanket off)."""
    home = tmp_path
    rt = home / ".cabinet" / "runtime"  # == CANONICAL_RUNTIME_ROOT (HOME-relative)
    rt.mkdir(parents=True)
    slot = tmp_path / "slot"
    _make_slot(slot, "roster:\n  cos:\n    title: Chief of Staff\n", {"cos": "standing"})
    _make_runtime_root(rt, slot)
    _make_fake_launchctl(home / "shimbin")
    lc_log = tmp_path / "launchctl.log"
    proc = _run_deploy(
        "rollback", rt, home,
        {"STARTED_LOG": str(tmp_path / "s.log"), "LAUNCHCTL_LOG": str(lc_log), "FAKE_PRINT_RC": "0"},
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "kickstarted live LaunchAgent com.cabinet.officer.cos" in proc.stdout
    lc = lc_log.read_text(encoding="utf-8") if lc_log.exists() else ""
    assert "kickstart -k gui/" in lc


def test_roster_derivation_rejects_unsafe_label(tmp_path: Path):
    """The lib_roster label allowlist (re.fullmatch) must reject a roster slug
    that would synthesize an unsafe officer label rather than emit it as a
    shell token."""
    home = tmp_path
    slot = tmp_path / "slot"
    rt = tmp_path / "rt"
    _make_slot(
        slot,
        "roster:\n  ../evil:\n    title: nope\n",
        {},
    )
    _make_runtime_root(rt, slot)
    _make_fake_launchctl(home / "shimbin")
    proc = _run_deploy(
        "rollback", rt, home,
        {"STARTED_LOG": str(tmp_path / "s.log"), "LAUNCHCTL_LOG": str(tmp_path / "l.log"), "FAKE_PRINT_RC": "1"},
    )
    assert proc.returncode != 0
    assert "unsafe roster-derived officer label" in proc.stderr


# --------------------------------------------------------------------------
# static: bash -n on every edited script
# --------------------------------------------------------------------------
@pytest.mark.parametrize("script", [SEED, DEPLOY, PROVISION])
def test_bash_n_clean(script: Path):
    proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
