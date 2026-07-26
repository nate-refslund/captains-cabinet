"""null-hatch.sh sandbox-staging parity (roster-authz, 2026-07-26).

null-hatch.sh proves ONE claim: "the egg boots with NO captain data". It
stages a sandbox copy of the tree and runs the proof there. It had TWO staging
paths, and they staged different trees:

  * git work tree  -> `git archive HEAD`      = tracked content only
  * gitless tree   -> `tar --exclude=./.git`  = tracked content PLUS every
                      deployment-local file .gitignore names (the roster,
                      active-preset, posture.yml, cabinet/.env, caches, logs)

So the same proof reached different verdicts on the same content depending
only on whether .git existed — and the gitless branch is the one a STRANGER's
delivered egg takes (egg-export.sh cuts a gitless tree) and the one
hatch.sh --clean-room takes (its scratch export is gitless). The proof that
claims there is no captain data ran over a tree that had captain data in it.
That is how framework/tests/test_roster_conf_lockstep.py's live arm could be
red for every stranger and green in every checkout at the same time, and it
also flipped two evidence-plane shadow-proof tests via a stray .pytest_cache.

The fix prunes the gitless copy of exactly what the tree's OWN .gitignore
names. These tests assert the PROPERTY (what ends up in the sandbox), by
running the real script and having a stub stage-1 test record the sandbox's
contents to a path outside the sandbox — the sandbox itself is deleted by
null-hatch's own EXIT trap, so recording from inside is the only honest way to
look at it.

Run: python3.12 -m pytest cabinet/scripts/tests/test_null_hatch_staging.py -q
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
NULL_HATCH = _SCRIPTS_DIR / "null-hatch.sh"

# The deployment-local file under test: gitignored, and the exact one whose
# accidental presence armed a gate the hatch could not satisfy.
LOCAL_REL = "instance/config/roster.yml"
SHIPPED_REL = "instance/config/roster.yml.example"

# The other half of the same question, and the one the first cut of the prune
# got wrong (2026-07-26): a path that .gitignore names but the repo FORCE-TRACKS
# (`git add -f`). This repo does that for real, shipped product source —
# cabinet/dashboard/src/app/(authenticated)/officers/*.tsx, memory/tier3/
# structure, shared/interfaces/deployment-status.md. `git archive HEAD` ships
# them; a fresh index in the gitless copy calls them "others + ignored" and the
# prune deleted them. The tree cannot tell the two cases apart, so the export
# ships the answer in KEEPLIST_REL and the prune honours it.
FORCED_REL = "cabinet/dashboard/officers-page.tsx"
KEEPLIST_REL = "cabinet/scripts/shipped-ignored-paths.txt"

_PROBE_TEMPLATE = """\
import os
from pathlib import Path

def test_record_sandbox_contents():
    # cwd is null-hatch's sandbox ($EGG). Record what actually got staged, to a
    # path OUTSIDE it — the sandbox is removed by null-hatch's EXIT trap.
    here = Path.cwd()
    listing = sorted(
        p.relative_to(here).as_posix()
        for p in here.rglob("*") if p.is_file()
    )
    Path({record!r}).write_text("\\n".join(listing), encoding="utf-8")
"""


def _fake_tree(root: Path, record: Path, keeplist: bool = True) -> None:
    """A minimal tree shaped like the real repo where null-hatch cares: the
    script at its real relative path, a .gitignore, one ignored deployment-local
    file, one ignored-but-FORCE-TRACKED file (with the keep-list that declares
    it shipped), one plain shipped file, and stage-1's two test targets (stubs
    that record the sandbox listing). Stages 2+ will fail for want of a real
    framework — irrelevant: the claim under test is what the sandbox CONTAINS.

    `keeplist=False` drops the declaration, which is the documented fail-safe:
    with no list the prune keeps nothing extra, i.e. exactly the old behaviour."""
    (root / "cabinet/scripts").mkdir(parents=True)
    (root / "cabinet/dashboard").mkdir(parents=True)
    (root / "instance/config").mkdir(parents=True)
    (root / "framework/tests").mkdir(parents=True)
    shutil.copy(NULL_HATCH, root / "cabinet/scripts/null-hatch.sh")
    (root / ".gitignore").write_text(
        f"{LOCAL_REL}\n{FORCED_REL}\n", encoding="utf-8")
    (root / LOCAL_REL).write_text("roster:\n  ghost-ceo: {}\n", encoding="utf-8")
    (root / SHIPPED_REL).write_text("# shipped twin\n", encoding="utf-8")
    (root / FORCED_REL).write_text(
        "export default function Officers() { return null }\n", encoding="utf-8")
    if keeplist:
        (root / KEEPLIST_REL).write_text(
            f"# shipped despite .gitignore\n{FORCED_REL}\n", encoding="utf-8")
    probe = _PROBE_TEMPLATE.format(record=str(record))
    (root / "framework/tests/test_clean_room.py").write_text(probe, encoding="utf-8")
    (root / "framework/tests/test_no_launcher_hardcode.py").write_text(
        "def test_noop():\n    pass\n", encoding="utf-8")


def _run_null_hatch(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(root / "cabinet/scripts/null-hatch.sh")],
        cwd=str(root), capture_output=True, text=True, timeout=300,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
             "HOME": str(root / ".fakehome"), "PYTHON": sys.executable},
    )


def _staged(tmp_path: Path, as_git_tree: bool, keeplist: bool = True,
            tag: str = "") -> list:
    name = ("git" if as_git_tree else "gitless") + tag
    root = tmp_path / name
    root.mkdir()
    record = tmp_path / f"staged-{name}.txt"
    _fake_tree(root, record, keeplist=keeplist)
    if as_git_tree:
        env_git = ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=T"]
        subprocess.run([*env_git, "init", "-q"], cwd=str(root), check=True)
        subprocess.run([*env_git, "add", "-A"], cwd=str(root), check=True)
        # the whole point of the force-tracked case: `add -A` skips an ignored
        # path, `add -f` is what makes it shipped content in the first place
        subprocess.run([*env_git, "add", "-f", "--", FORCED_REL],
                       cwd=str(root), check=True)
        subprocess.run([*env_git, "commit", "-qm", "seed"], cwd=str(root), check=True)
    proc = _run_null_hatch(root)
    assert record.is_file(), (
        "the stage-1 probe never ran, so staging was never observed:\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    return record.read_text(encoding="utf-8").splitlines()


@pytest.fixture(scope="module", autouse=True)
def _require_git():
    if shutil.which("git") is None:
        pytest.skip("git not available")


def test_gitless_staging_excludes_deployment_local_files(tmp_path):
    """The bug, stated as the property: on a GITLESS tree (a delivered egg, or
    hatch.sh --clean-room's scratch export) the sandbox must not contain the
    deployment-local files .gitignore names. Before the fix it did, and a
    freshly-hatched roster.yml there armed a gate the hatch could not pass."""
    staged = _staged(tmp_path, as_git_tree=False)
    assert LOCAL_REL not in staged, (
        f"{LOCAL_REL} is gitignored deployment-local state and must never enter "
        f"the clean-room sandbox — the proof claims the egg carries NO captain "
        f"data. Staged: {staged}")


def test_gitless_staging_keeps_shipped_files(tmp_path):
    """Pruning must not overshoot: shipped (non-ignored) content still stages,
    or the proof would pass by having nothing left to prove."""
    staged = _staged(tmp_path, as_git_tree=False)
    assert SHIPPED_REL in staged, f"shipped content was pruned. Staged: {staged}"


def test_both_staging_paths_agree(tmp_path):
    """THE parity claim: a git work tree and a gitless copy of the same content
    stage the same sandbox. Any divergence means 'proof-a passed here' does not
    imply 'proof-a passes there' — exactly the asymmetry that let this bug be
    red for strangers and green in every checkout."""
    gitless = set(_staged(tmp_path, as_git_tree=False))
    git_tree = set(_staged(tmp_path, as_git_tree=True))
    assert gitless == git_tree, (
        f"staging paths disagree — only in gitless: {sorted(gitless - git_tree)}; "
        f"only in git tree: {sorted(git_tree - gitless)}")


def test_gitless_staging_keeps_force_tracked_shipped_content(tmp_path):
    """The over-prune, stated as the property: content the repo SHIPS must
    survive the clean-room staging even when .gitignore names it. `git ls-files
    --others --ignored` in a fresh index cannot see a force-add, so the prune
    deleted real product source (the dashboard officers pages) out of the proof
    sandbox — a proof running on a tree the egg does not have."""
    staged = _staged(tmp_path, as_git_tree=False)
    assert FORCED_REL in staged, (
        f"{FORCED_REL} is force-tracked and ships in `git archive HEAD`, but the "
        f"gitless prune deleted it — the sandbox is not the egg. Staged: {staged}")


def test_force_tracked_content_needs_the_keep_list_to_survive(tmp_path):
    """Non-vacuity + the documented fail-safe boundary. The file really is
    ignored (so the arm above is not passing for free), and an ABSENT keep-list
    keeps nothing extra — a plain git work tree is therefore untouched by all
    of this."""
    staged = _staged(tmp_path, as_git_tree=False, keeplist=False, tag="-nokeep")
    assert FORCED_REL not in staged, (
        "the fixture's force-tracked file is not actually gitignored, so the "
        "keep-list arm proves nothing")


def test_both_staging_paths_agree_on_force_tracked_content(tmp_path):
    """THE parity claim, now over the case that broke it. `git archive HEAD`
    ships a force-added ignored path; the gitless copy must stage the same
    tree. The pre-existing parity arm could not catch this — its fixture had no
    force-added file, so both branches agreed on a set that never contained
    one."""
    gitless = set(_staged(tmp_path, as_git_tree=False))
    git_tree = set(_staged(tmp_path, as_git_tree=True))
    assert FORCED_REL in git_tree, "git archive must ship the force-added path"
    assert gitless == git_tree, (
        f"staging paths disagree — only in gitless: {sorted(gitless - git_tree)}; "
        f"only in git tree: {sorted(git_tree - gitless)}")


def test_gitless_staging_still_prunes_local_state_beside_kept_content(tmp_path):
    """The keep-list must not become a blanket amnesty: deployment-local state
    is still pruned in the same run that keeps shipped content."""
    staged = _staged(tmp_path, as_git_tree=False)
    assert FORCED_REL in staged
    assert LOCAL_REL not in staged, f"local state survived: {staged}"


def test_gitless_staging_reports_the_keep_list_it_honoured(tmp_path):
    """Same reason the prune count is printed: a reader must be able to see
    which of the two rules moved a given file."""
    root = tmp_path / "gitless"
    root.mkdir()
    _fake_tree(root, tmp_path / "record.txt")
    proc = _run_null_hatch(root)
    assert "honours 1 shipped-ignored path" in proc.stdout, (
        f"no keep-list line in the output:\n{proc.stdout}")


def test_gitless_staging_reports_what_it_pruned(tmp_path):
    """Silent pruning would be its own trap: a reader must be able to see that
    the sandbox is not the tree they are standing in."""
    root = tmp_path / "gitless"
    root.mkdir()
    _fake_tree(root, tmp_path / "record.txt")
    proc = _run_null_hatch(root)
    assert "gitless staging pruned" in proc.stdout, (
        f"no staging-parity line in the output:\n{proc.stdout}")
