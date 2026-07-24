"""COG-5 §5.4 — the Evolutionary-Foundry runtime-data .gitignore row + its
`git check-ignore` assertion (the phase-twin check named in §14.2 W1 / rev-1
SF-2). Tests-first, gates-before-code.

The immutable trajectory archive (segments + seals + manifests + pending.json)
and the league's own run artifacts land under shared/interfaces/foundry/ —
append-only per-cabinet runtime data that must NEVER be tracked (the archive
doubles as an R5 training set: sealed, unbounded, never a git object; rollback =
verified RESTORE, never cache-delete, §5.2). This wave ADDS the `.gitignore` row
`shared/interfaces/foundry/`; this test proves the row is present AND actually
ignores foundry paths, and that it is DISCRIMINATING (a normal source path is
not swept up). S0 verified the pre-state: the dir is absent and had no row (§6).

Egg interaction (rev-1 SF-2): the export cuts from git HEAD (tracked files
only), so untracked foundry data never reaches the archive; R116's
interfaces-header-only transform fail-closes on any OTHER tracked file under
shared/interfaces/ — belt and braces, so NO egg expect-absent row is needed for
this untracked data (unlike the holdout_gen.py module exclusion, which IS a
tracked-file concern — test_cog5_holdout_pin.py).

S0: python3.12, git (check-ignore needs no HOME/config). Provenance: authored per
the 2026-07-07 full-autonomy grant + the 2026-07-20 cognitive-masterplan grant.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
_GITIGNORE = _REPO / ".gitignore"
_FOUNDRY_ROW = "shared/interfaces/foundry/"


def _check_ignored(rel: str) -> bool:
    # exit 0 == path is ignored by a .gitignore rule; 1 == not ignored.
    r = subprocess.run(["git", "-C", str(_REPO), "check-ignore", "-q", rel])
    return r.returncode == 0


class TestFoundryGitignore:
    def test_gitignore_carries_the_foundry_row(self):
        lines = {ln.strip() for ln in _GITIGNORE.read_text(encoding="utf-8").splitlines()}
        assert _FOUNDRY_ROW in lines, (
            ".gitignore is missing the shared/interfaces/foundry/ row (§5.4)")

    def test_archive_and_league_runtime_paths_are_ignored(self):
        # the archive store + its seals/manifests/heal-file + league run artifacts
        # under the foundry root are all untracked runtime data (§5.2/§5.4/§8.3).
        for rel in (
            "shared/interfaces/foundry/archive/seg-0001.jsonl",
            "shared/interfaces/foundry/archive/manifest.json",
            "shared/interfaces/foundry/archive/pending.json",
            "shared/interfaces/foundry/league/run-0001/results.jsonl",
        ):
            assert _check_ignored(rel), f"{rel} is NOT gitignored — it would track"

    def test_row_is_discriminating_not_a_blanket_ignore(self):
        # anti-no-op: check-ignore genuinely discriminates — a normal tracked
        # source path (outside the foundry tree) is NOT swept up by this row.
        assert not _check_ignored("framework/evolution/contracts.py")

    def test_the_foundry_dir_itself_is_the_pre_state_absent(self):
        # S0 pin (§6): the foundry tree does not exist yet — the row protects a
        # dir that lands only when the archive is first written (W4 runtime).
        assert not (_REPO / "shared/interfaces/foundry").exists(), (
            "shared/interfaces/foundry/ exists in the tracked tree — runtime data "
            "must never be committed; verify the ignore row + purge the tracked copy")
