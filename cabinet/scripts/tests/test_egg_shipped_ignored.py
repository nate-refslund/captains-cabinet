"""egg-export.sh ships the shipped-ignored keep-list (roster-authz, 2026-07-26).

The egg has no `.git`, so nothing inside it can tell "shipped" from "written by
this deployment". `cabinet/scripts/null-hatch.sh` re-derives that distinction
from the tree's own `.gitignore` — and `git ls-files --others --ignored` in a
fresh index cannot see a force-add (`git add -f`). This repo force-tracks real
shipped content that `.gitignore` names: the dashboard officers pages (product
source `.tsx`), the `memory/tier3/` structure, and
`shared/interfaces/deployment-status.md` (a manifest `expect-present`). Those
ship in `git archive HEAD`, so the git staging branch keeps them, while the
gitless branch deleted them — the same content reaching two verdicts, which is
precisely the staging asymmetry null-hatch's parity block exists to close.

The tree cannot answer the question, so the export SHIPS the answer. These arms
pin the producer half (the list exists, is accurate, and is derived rather than
hand-maintained); `test_null_hatch_staging.py` pins the consumer half.

Deliberately NOT in test_egg_export.py: that file is inside the frozen COG-4
review scope (`cabinet/scripts/cognitive-phase4-review-scope.py`), so editing it
moves the Reviewed-Scope-Digest and BLOCKS verify-cognitive-phase4.sh. Re-blessing
a frozen review to fit an unrelated change would defeat the binding it exists to
enforce.

Run: python3.12 -m pytest cabinet/scripts/tests/test_egg_shipped_ignored.py -q
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_EXPORT_SH = _SCRIPTS_DIR / "egg-export.sh"
_KEEPLIST_REL = "cabinet/scripts/shipped-ignored-paths.txt"

_EXPORT_TIMEOUT = 300  # full archive cut + transform pass; seconds


@pytest.fixture(scope="module")
def export(tmp_path_factory) -> Path:
    """One real export of this repo's HEAD, shared by the arms below."""
    out = tmp_path_factory.mktemp("egg-shipped-ignored") / "export"
    proc = subprocess.run(
        ["bash", str(_EXPORT_SH), "--out", str(out)],
        cwd=_REPO_ROOT, capture_output=True, text=True, timeout=_EXPORT_TIMEOUT,
    )
    assert proc.returncode == 0, (
        f"egg-export.sh failed rc={proc.returncode}\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    assert "verify        : PASS" in proc.stdout, proc.stdout
    return out


def _entries(export: Path) -> list:
    keeplist = export / _KEEPLIST_REL
    assert keeplist.is_file(), (
        "the egg must declare which of its files a fresh clone's .gitignore "
        "would call ignorable, or the clean-room proof runs on a pruned tree")
    return [ln for ln in keeplist.read_text(encoding="utf-8").splitlines()
            if ln and not ln.startswith("#")]


def test_keeplist_ships_and_names_only_paths_the_egg_has(export: Path):
    """It exists, it is not empty (an empty list is a silent no-op), and every
    path on it is really in the export — a list naming absent paths would be
    indistinguishable from a list that works."""
    entries = _entries(export)
    assert entries, "an empty keep-list is a silent no-op"
    missing = [rel for rel in entries if not (export / rel).is_file()]
    assert not missing, f"keep-list names paths the export does not have: {missing}"


def test_keeplist_covers_the_force_tracked_product_source(export: Path):
    """Non-vacuity against the case that made this a bug: force-added dashboard
    `.tsx` product source, which the gitless prune deleted."""
    entries = _entries(export)
    assert any(rel.startswith("cabinet/dashboard/") and rel.endswith(".tsx")
               for rel in entries), (
        f"no force-tracked dashboard source on the keep-list: {entries}")


def test_keeplist_is_derived_from_head_not_hand_maintained(export: Path):
    """Exactly HEAD's force-tracked-ignored set intersected with what survived
    the packaging pass — so it cannot rot away from either `.gitignore` or the
    export manifest."""
    head = subprocess.run(
        ["git", "-c", "core.quotePath=false", "ls-files", "-c", "-i",
         "--exclude-standard"],
        cwd=_REPO_ROOT, capture_output=True, text=True, timeout=60, check=True)
    expected = {rel for rel in head.stdout.splitlines()
                if rel and (export / rel).is_file()}
    assert set(_entries(export)) == expected, (
        f"only on list: {sorted(set(_entries(export)) - expected)}; "
        f"only at HEAD: {sorted(expected - set(_entries(export)))}")
