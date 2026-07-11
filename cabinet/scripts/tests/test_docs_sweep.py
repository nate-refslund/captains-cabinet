"""Contract tests for cabinet/scripts/docs-track-code-sweep.sh (NORTH-STAR G6
"docs must track the code", made mechanically checkable).

What is pinned here:

  * the two check classes against a tiny fixture repo in tmp_path
    (filesystem-oracle mode — the fixture is deliberately NOT a git repo):
      - a dead repo-path reference in a living doc is CAUGHT,
      - a dead relative markdown link is CAUGHT,
      - a live reference PASSES,
      - an allowlisted runtime reference (cabinet/.env) PASSES,
      - a dated docs/plans/ archive containing a dead ref is EXCLUDED by
        scope (archives are records, not living docs).
  * the flag surface: --list-scope exits 0 and never lists archives; unknown
    flags refuse with 64 (the sibling-script convention).
  * the calibration contract: the REAL script against the REAL repo exits 0
    (repo-dependent — skipped when the checkout has no .git, e.g. egg cuts).

Run shape mirrors the sibling script tests: subprocess against the real
script with real bash, no network.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "cabinet" / "scripts" / "docs-track-code-sweep.sh"

repo_required = pytest.mark.skipif(
    not (REPO / ".git").exists(),
    reason="calibration contract needs the real git checkout (egg cuts and "
           "bare doc trees have no HEAD to sweep against)",
)


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=120)


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    """A minimal doc tree exercising every check class (fs-oracle mode)."""
    root = tmp_path / "repo"
    (root / "cabinet" / "scripts").mkdir(parents=True)
    (root / "docs" / "runbooks").mkdir(parents=True)
    (root / "docs" / "plans").mkdir(parents=True)

    # a live target for the passing reference
    (root / "cabinet" / "scripts" / "real.sh").write_text(
        "#!/bin/bash\n", encoding="utf-8")

    # living doc, path-ref class: one live ref, one dead ref, one
    # allowlisted runtime ref (cabinet/.env does not exist on disk here)
    (root / "README.md").write_text(
        "Run `cabinet/scripts/real.sh` before anything.\n"
        "Then run `cabinet/scripts/ghost.sh` to finish.\n"
        "Secrets land in `cabinet/.env` (wizard-created).\n",
        encoding="utf-8")

    # living doc, link class: one live relative link, one dead one
    (root / "docs" / "runbooks" / "run.md").write_text(
        "See [the readme](../../README.md) first.\n"
        "Then read [the missing page](../missing-doc.md#setup).\n",
        encoding="utf-8")

    # dated archive: contains a dead ref that must NOT be reported
    (root / "docs" / "plans" / "plan-2026-01-01.md").write_text(
        "We will build `cabinet/scripts/never-existed.sh` next week.\n",
        encoding="utf-8")

    # allowlist at the conventional in-tree path (picked up by default)
    (root / "cabinet" / "scripts" / "docs-sweep-allowlist.txt").write_text(
        "# runtime secrets file, created by the wizard\n"
        "cabinet/.env\n",
        encoding="utf-8")
    return root


class TestFlagSurface:
    def test_bash_syntax_clean(self):
        proc = subprocess.run(["bash", "-n", str(SCRIPT)],
                              capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, proc.stderr

    def test_unknown_flag_refuses_64(self):
        proc = _run("--frobnicate")
        assert proc.returncode == 64
        assert "unknown argument" in proc.stderr

    def test_allowlist_flag_missing_file_refuses_64(self, tmp_path):
        proc = _run("--allowlist", str(tmp_path / "nope.txt"))
        assert proc.returncode == 64
        assert "allowlist not found" in proc.stderr

    def test_list_scope_exits_zero_and_excludes_archives(self, fixture_repo):
        proc = _run("--root", str(fixture_repo), "--list-scope")
        assert proc.returncode == 0, proc.stderr
        scope = proc.stdout.splitlines()
        assert "README.md" in scope
        assert "docs/runbooks/run.md" in scope
        assert not any("docs/plans" in line for line in scope), (
            "dated archives are records, never scope")


class TestFixtureSweep:
    def test_dead_path_ref_is_caught(self, fixture_repo):
        proc = _run("--root", str(fixture_repo))
        assert proc.returncode == 1
        assert "README.md:2 -> cabinet/scripts/ghost.sh" in proc.stdout

    def test_dead_relative_link_is_caught(self, fixture_repo):
        proc = _run("--root", str(fixture_repo))
        assert proc.returncode == 1
        assert "docs/runbooks/run.md:2 -> docs/missing-doc.md" in proc.stdout, (
            "anchor must be stripped, path resolved against the doc dir")

    def test_live_ref_and_live_link_pass(self, fixture_repo):
        proc = _run("--root", str(fixture_repo))
        assert "real.sh" not in proc.stdout
        assert "README.md:1" not in proc.stdout
        assert "docs/runbooks/run.md:1" not in proc.stdout

    def test_allowlisted_runtime_ref_passes(self, fixture_repo):
        proc = _run("--root", str(fixture_repo))
        assert "cabinet/.env" not in proc.stdout

    def test_dated_plan_doc_is_excluded_by_scope(self, fixture_repo):
        proc = _run("--root", str(fixture_repo))
        assert "never-existed.sh" not in proc.stdout
        assert "docs/plans" not in proc.stdout

    def test_summary_counts_findings(self, fixture_repo):
        proc = _run("--root", str(fixture_repo))
        assert "DOCS_SWEEP FINDINGS (n=2 files=2)" in proc.stdout

    def test_clean_tree_is_green_exit_zero(self, fixture_repo):
        (fixture_repo / "README.md").write_text(
            "Only `cabinet/scripts/real.sh` here.\n", encoding="utf-8")
        (fixture_repo / "docs" / "runbooks" / "run.md").write_text(
            "See [the readme](../../README.md).\n", encoding="utf-8")
        proc = _run("--root", str(fixture_repo))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "DOCS_SWEEP GREEN (files=2 findings=0)" in proc.stdout

    def test_empty_allowlist_flags_the_runtime_ref(self, fixture_repo, tmp_path):
        empty = tmp_path / "empty-allowlist.txt"
        empty.write_text("# nothing waived\n", encoding="utf-8")
        proc = _run("--root", str(fixture_repo), "--allowlist", str(empty))
        assert proc.returncode == 1
        assert "README.md:3 -> cabinet/.env" in proc.stdout


class TestRealTreeCalibration:
    @repo_required
    def test_real_script_green_on_real_repo(self):
        """G6 gate contract: the living docs of THIS checkout are clean.

        A failure here is either fresh doc rot (fix the doc) or a new
        legitimate runtime reference (allowlist it WITH a why-comment in
        cabinet/scripts/docs-sweep-allowlist.txt) — never a reason to relax
        the scanner.
        """
        proc = _run()
        assert proc.returncode == 0, (
            "docs-track-code sweep found rot:\n" + proc.stdout + proc.stderr)
        assert "DOCS_SWEEP GREEN" in proc.stdout
