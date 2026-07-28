"""world-asset-gate --committed-only: the tracked subset a pristine clone CAN check.

WHY THIS FILE EXISTS (2026-07-28). The world asset manifest is content-addressed
— every row declares a sha256 — and nothing ever checked it. The full gate needs
the licensed LimeZu packs on disk, which exist on exactly one machine, so it ran
in no CI job; `cabinet-ci.yml` ran only the forge test. The cost was found by
attack: `originals/iso/atlas-0` declared `425e9f93…` while the committed file
hashes `88dea7194171…`, and the declared value matches NO blob in that file's
history — it was wrong from the commit that wrote it and stayed wrong for weeks.

So the sensor here is deliberately aimed at what CI can actually see: the rows
whose file is tracked in git. Those are the owned, committable ones (20 owned
character sheets + the iso atlas today). Every arm below is proven to FAIL
against the defect it names, and the degenerate end — an empty or unanswerable
tracked set — is a RED, not a green sweep over nothing.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
GATE = REPO / "cabinet" / "scripts" / "world-asset-gate.py"
MANIFEST = (REPO / "cabinet" / "dashboard" / "public" / "world-assets"
            / "manifest.json")


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), *args],
        capture_output=True, text=True, timeout=300, cwd=str(cwd or REPO),
    )


def test_the_repos_own_committed_assets_are_conformant():
    """The live claim: every TRACKED manifest row's file matches its declared
    bytes and dimensions. This is the arm that was red on master."""
    proc = run("--committed-only")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "WORLD_ASSETS GREEN" in proc.stdout, proc.stdout


def _owned_sandbox(tmp_path: Path) -> Path:
    """A throwaway git repo holding ONLY the tracked owned assets.

    Deliberately not a clone of the real repo: `actions/checkout` is shallow and
    a shallow clone of a shallow clone is a fragile fixture. This copies the
    committable files, inits a repo and tracks them, which is the exact
    condition `--committed-only` reasons about, and it runs in milliseconds.
    """
    root = tmp_path / "sandbox" / "world-assets"
    (root / "originals").mkdir(parents=True)
    shutil.copy(MANIFEST, root / "manifest.json")
    shutil.copytree(MANIFEST.parent / "originals" / "iso", root / "originals" / "iso")
    shutil.copytree(MANIFEST.parent / "originals" / "characters",
                    root / "originals" / "characters")
    git = ["git", "-C", str(root)]
    subprocess.run(git + ["init", "-q"], check=True, timeout=60, capture_output=True)
    subprocess.run(git + ["add", "-A"], check=True, timeout=120, capture_output=True)
    return root


def test_a_wrong_declared_hash_is_caught(tmp_path: Path):
    """Proven to FAIL: flip one tracked row's sha256 and the gate must go red.

    Without this, a content-addressed manifest is a comment.
    """
    root = _owned_sandbox(tmp_path)
    man = root / "manifest.json"
    data = json.loads(man.read_text())
    target = next(r for r in data["assets"] if r["id"] == "originals/iso/atlas-0")
    target["sha256"] = "0" * 64
    man.write_text(json.dumps(data, indent=2))
    proc = run("--committed-only", str(man), cwd=root)
    assert proc.returncode == 1, proc.stdout
    assert "sha256 mismatch" in proc.stdout, proc.stdout
    assert "originals/iso/atlas-0" in proc.stdout, proc.stdout


def test_a_tracked_file_that_vanished_is_caught(tmp_path: Path):
    """Proven to FAIL: a row citing an absent tracked file is red, not skipped."""
    root = _owned_sandbox(tmp_path)
    victim = root / "originals" / "characters" / "Premade_Character_01.png"
    assert victim.exists(), "fixture assumption: the owned cast is tracked"
    victim.unlink()
    proc = run("--committed-only", str(root / "manifest.json"), cwd=root)
    assert proc.returncode == 1, proc.stdout
    assert "file missing" in proc.stdout, proc.stdout


def test_an_empty_tracked_universe_is_red_not_green(tmp_path: Path):
    """THE DEGENERATE END. A per-row gate over zero rows passes every row.

    Point the gate at a manifest whose asset root git knows nothing about and
    it must fail on the floor — the exact shape ("a check that could not run
    has not passed") this program has now paid for eleven times.
    """
    root = tmp_path / "loose" / "world-assets"
    root.mkdir(parents=True)
    shutil.copy(MANIFEST, root / "manifest.json")
    proc = run("--committed-only", str(root / "manifest.json"), cwd=tmp_path)
    assert proc.returncode == 1, proc.stdout
    assert "below the floor" in proc.stdout or "could not answer" in proc.stdout, \
        proc.stdout


def test_the_floor_is_a_real_floor(tmp_path: Path):
    """The floor must bind: ask for more tracked rows than exist and it fails.

    Guards the inverse mistake — a floor set so low that losing the whole owned
    cast still reads green.
    """
    proc = run("--committed-only", "--min-committed", "100000")
    assert proc.returncode == 1, proc.stdout
    assert "below the floor" in proc.stdout, proc.stdout


def test_committed_only_is_a_strict_subset_of_the_full_sweep():
    """The mode narrows the universe; it must never narrow the CHECKS.

    A row in the committed sweep gets the same sha256/dimension/containment
    treatment as in the full sweep — the only difference is which rows are in.
    """
    src = GATE.read_text()
    # one call site, one check function: the narrowing happens before the loop
    assert src.count("check_asset(entry, asset_root, problems)") == 1, \
        "committed-only must reuse the single check path, not fork it"
    assert "for entry in swept:" in src


@pytest.mark.parametrize("row_id", [
    "originals/iso/atlas-0",
    "originals/characters/Premade_Character_01",
    "originals/characters/Premade_Character_20",
])
def test_the_owned_set_is_actually_in_the_swept_universe(row_id: str):
    """A sweep is only as good as its membership. Pin the rows by NAME so the
    set cannot silently shrink to something trivially green — the completeness
    failure ('a check that cannot detect removal from the set it checks')."""
    data = json.loads(MANIFEST.read_text())
    row = next((r for r in data["assets"] if r["id"] == row_id), None)
    assert row is not None, f"{row_id} left the manifest"
    path = (MANIFEST.parent / row["path"])
    assert path.exists(), f"{row_id} names a file that is not on disk"
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", str(path)],
        capture_output=True, text=True, cwd=str(REPO), timeout=60,
    )
    assert tracked.returncode == 0, f"{row_id} is no longer git-tracked"
