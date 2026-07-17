"""The canonical-task-surface RATCHET — no direct external-tracker writes
outside ``cabinet/scripts/task_adapters/``.

Doctrine (constitution-base Work Principle 9 + CLAUDE.md / CLAUDE-egg
"Keep the trackers honest", 2026-07-17): ``officer_tasks`` (the ``/tasks``
board) is the Cabinet's CANONICAL coordination surface. External trackers are
projections synced by the task adapters; an officer never writes coordination
state directly to an external tracker. This module is the CI forcing function
that keeps the codebase shaped that way: it text-walks every
``framework/**/*.py`` and ``cabinet/scripts/**/*.{py,sh}`` (task_adapters/,
``tests/`` dirs, ``test_*``/``*_test`` files and ``__pycache__`` skipped) and
goes RED on any tracker-WRITE fingerprint outside the documented, shrink-only
BY-DESIGN allowlist below. Seeded at live count 0 outside the allowlist
(verified 2026-07-17) — a new hit is a CI failure, not a review note.

Design mirrors ``framework/tests/test_no_launcher_hardcode.py`` (the sister
identity ratchet): stdlib-only, ``import pytest`` guarded so it also runs
under the system python (CLI mode below), symlink-escape refused via
``os.path.realpath`` containment, and read-ONLY (files are ``read_text``-
scanned, never imported or executed). Every pattern is a STATIC module regex
(no dynamic/user-controlled construction, so no ReDoS surface).

THE PATTERN LIST IS DERIVED FROM THE ADAPTERS THEMSELVES — each family cites
the adapter write call it fingerprints, so the ratchet can only claim what
the sanctioned seam actually does:

  * Linear (``task_adapters/linear.py`` push/delete): the GraphQL WRITE
    mutations ``issueCreate`` / ``issueUpdate`` / ``issueArchive``.
    Deliberately NOT the bare ``api.linear.app`` endpoint — Linear is the
    read-only audit archive post Spec-039 cutover and sanctioned READERS
    exist (``import-linear-to-library.sh``, the dashboard's Captain column);
    reads are compliant, only writes are banned.
  * Jira (``task_adapters/jira.py`` push/delete/link): the issue WRITE
    endpoint ``rest/api/3/issue`` (create/update/delete land there; the
    adapter's READ goes to ``rest/api/3/search/jql``, which does not match).
  * Asana (``task_adapters/asana.py``): the API base ``app.asana.com/api``
    (all task writes ride it; the token-page HELP url
    ``app.asana.com/0/my-apps`` printed by setup-env.sh does not match).
  * GitHub Issues (``task_adapters/github_issues.py`` push/delete): the gh
    WRITE subcommands ``gh issue create`` / ``gh issue edit`` /
    ``gh issue close`` (``gh issue list``/``view`` reads do not match).
  * Monday (adapter REMOVED per ``task_adapters/base.py`` — Monday rides a
    dev-tasks-style plugin now, so ANY direct client is suspect): the
    endpoint ``api.monday.com`` plus the GraphQL WRITE op names
    ``create_item`` / ``create_update`` / ``change_column_value`` /
    ``change_multiple_column_values`` / ``delete_item`` / ``archive_item``.
  * Azure Boards (NO adapter exists): ``dev.azure.com`` as a forward guard —
    the door is closed BEFORE the first ad-hoc client appears; an Azure
    integration must arrive as a task adapter.

Word-bounding notes: ``\\bcreate_item\\b`` does NOT match ``create_items``
(no boundary inside a word), so plural helper names never false-positive;
``rest/api/3/issue\\b`` does not match ``.../issues`` either.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Iterator, List, Tuple

try:  # also runnable under the system python without pytest (CLI mode below)
    import pytest
except ImportError:  # pragma: no cover — never the pytest-collected path
    pytest = None  # type: ignore[assignment]

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The tracker-WRITE fingerprints (derivation per family in the module
# docstring). Static compiled regexes; the scanner reports ``m.group(0)``.
_LINEAR_WRITE = re.compile(r"\b(?:issueCreate|issueUpdate|issueArchive)\b")
_JIRA_ISSUE_WRITE = re.compile(r"rest/api/3/issue\b")
_ASANA_API = re.compile(r"app\.asana\.com/api")
_GH_ISSUE_WRITE = re.compile(r"\bgh issue (?:create|edit|close)\b")
_MONDAY_API = re.compile(r"api\.monday\.com")
_MONDAY_WRITE_OPS = re.compile(
    r"\b(?:create_item|create_update|change_column_value"
    r"|change_multiple_column_values|delete_item|archive_item)\b")
_AZURE_BOARDS = re.compile(r"dev\.azure\.com")

_CHECKS: Tuple[Tuple["re.Pattern[str]", str], ...] = (
    (_LINEAR_WRITE, "Linear write mutation '%s' outside task_adapters/"),
    (_JIRA_ISSUE_WRITE, "Jira issue write endpoint '%s' outside task_adapters/"),
    (_ASANA_API, "Asana API client '%s' outside task_adapters/"),
    (_GH_ISSUE_WRITE, "gh issue write '%s' outside task_adapters/"),
    (_MONDAY_API, "direct Monday client '%s' outside task_adapters/"),
    (_MONDAY_WRITE_OPS, "Monday write op '%s' outside task_adapters/"),
    (_AZURE_BOARDS, "Azure Boards client '%s' outside task_adapters/ (no adapter exists)"),
)

Violation = Tuple[str, int, str]  # (display_path, line_no, reason)


# ===========================================================================
# THE BY-DESIGN ALLOWLIST (repo-relative posix paths). It may only ever
# SHRINK — growing it is a reviewed doctrine ruling, never a silent widening.
# ===========================================================================
# Every entry is a WHOLE-FILE exemption with its standing justification.
# Two sanctioned classes exist, and only these two:
#
#   (a) The act-first Captain-action seam. framework's frontdoor/acting lane
#       writes the CAPTAIN'S OWN tracker through ratified, journaled,
#       undoable act cards (policy-engine-gated, TOCTOU-re-checked,
#       instance/config/act-first-surfaces.yml-scoped — most of these files
#       are germline-locked). That is Captain work-tracking, NOT officer
#       coordination state; Work Principle 9 explicitly names it a separate
#       door. The classifier/undo/reconcile TABLES that govern those writes
#       carry the same op-name tokens and ride the same justification.
#   (b) The framework-backlog feedback door. cabinet-feedback.sh files an
#       issue on the CANONICAL FRAMEWORK repo — the sanctioned "GitHub
#       Issues = framework backlog" surface of the trackers law; it is not
#       coordination state and not a product tracker.
#
# FORCING FUNCTION: test_allowlist_entries_still_hit goes RED the moment an
# entry stops matching any pattern (e.g. the act-first Monday leg is retired)
# — forcing that entry's deletion. test_allowlist_only_shrinks pins the size.
_ALLOWLISTED_FILES: Dict[str, str] = {
    "framework/frontdoor/action_exec.py":
        "act-first executor — Monday act-card writes (class a)",
    "framework/frontdoor/action_undo.py":
        "act-first undo journal — archive/restore inverses (class a)",
    "framework/frontdoor/actfirst_canary.py":
        "act-first canary — synthetic probe write + cleanup (class a)",
    "framework/frontdoor/action_reconcile.py":
        "act-first reconcile — write-op name tables (class a)",
    "framework/authority/classifier.py":
        "authority classifier — Monday write-op classification tables (class a)",
    "cabinet/scripts/cabinet-feedback.sh":
        "framework-backlog feedback door — gh issue create on the canonical repo (class b)",
}
_ALLOWLIST_MAX = 6  # shrink-only: this number may only ever be LOWERED.

_SKIP_DIR_NAMES = {"tests", "__pycache__", "task_adapters", "node_modules"}


def _is_test_file(name: str) -> bool:
    stem = name.rsplit(".", 1)[0]
    return stem.startswith("test_") or stem.endswith("_test")


def iter_source_files(root: Path) -> Iterator[Path]:
    """Yield the scanned tree: framework/**/*.py + cabinet/scripts/**/*.{py,sh}
    under ``root``, skipping task_adapters/, tests/ dirs, test files and
    caches. Symlink escape is refused in scan_tree via realpath containment."""
    trees = (
        (root / "framework", (".py",)),
        (root / "cabinet" / "scripts", (".py", ".sh")),
    )
    for base, exts in trees:
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES]
            for fn in sorted(filenames):
                if not fn.endswith(exts) or _is_test_file(fn):
                    continue
                yield Path(dirpath) / fn


def _line_violations(line: str) -> List[str]:
    reasons: List[str] = []
    for pattern, template in _CHECKS:
        m = pattern.search(line)
        if m:
            reasons.append(template % m.group(0))
    return reasons


def scan_tree(root: Path, allowlist: "Dict[str, str] | None" = None) -> List[Violation]:
    """Scan ``root`` and return violations outside ``allowlist`` (defaults to
    the module allowlist). Read-only; a file whose realpath resolves outside
    ``root`` is itself reported (symlink escape refused, mirroring the
    launcher-hardcode sibling)."""
    allow = _ALLOWLISTED_FILES if allowlist is None else allowlist
    root_real = os.path.realpath(root)
    out: List[Violation] = []
    for path in iter_source_files(root):
        rel = path.relative_to(root).as_posix()
        real = os.path.realpath(path)
        if os.path.commonpath([root_real, real]) != root_real:
            out.append((rel, 0, "symlink escapes the scanned tree"))
            continue
        if rel in allow:
            continue
        try:
            text = Path(real).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            for reason in _line_violations(line):
                out.append((rel, i, reason))
    return out


def _fmt(violations: List[Violation]) -> str:
    return "\n".join(f"  {p}:{ln}: {r}" for p, ln, r in violations)


# ===========================================================================
# pytest surface
# ===========================================================================
class TestCanonicalTasksRatchet:
    def test_live_tree_has_no_direct_tracker_writes(self):
        violations = scan_tree(_REPO_ROOT)
        assert not violations, (
            "Direct external-tracker write fingerprints outside "
            "cabinet/scripts/task_adapters/ (officer_tasks is the canonical "
            "coordination surface — constitution-base Work Principle 9; "
            "route the write through a task adapter or, for a genuinely new "
            "by-design seam, get a reviewed allowlist ruling):\n"
            + _fmt(violations))

    def test_every_allowlisted_path_exists(self):
        missing = [p for p in _ALLOWLISTED_FILES if not (_REPO_ROOT / p).is_file()]
        assert not missing, f"stale allowlist entries (delete them): {missing}"

    def test_allowlist_entries_still_hit(self):
        """Forcing function: an allowlisted file that no longer matches any
        pattern is a stale exemption — delete its entry (shrink-only)."""
        stale = []
        for rel in _ALLOWLISTED_FILES:
            p = _REPO_ROOT / rel
            if not p.is_file():
                continue  # covered by test_every_allowlisted_path_exists
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if not any(pat.search(text) for pat, _ in _CHECKS):
                stale.append(rel)
        assert not stale, (
            f"allowlisted files no longer hit any tracker-write pattern — "
            f"delete their entries (the allowlist may only shrink): {stale}")

    def test_allowlist_only_shrinks(self):
        assert len(_ALLOWLISTED_FILES) <= _ALLOWLIST_MAX, (
            "the BY-DESIGN allowlist grew — growing it requires a reviewed "
            "doctrine ruling AND raising _ALLOWLIST_MAX in the same commit "
            "with that ruling cited; it may only ever shrink otherwise")


class TestScannerControls:
    """Planted-violation + exclusion controls over a synthetic tree — proof
    the scanner has teeth and the exclusions do not over-reach."""

    @staticmethod
    def _write(root: Path, rel: str, body: str) -> None:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def test_flags_planted_monday_curl_in_sh(self, tmp_path):
        self._write(tmp_path, "cabinet/scripts/rogue-sync.sh",
                    "#!/bin/bash\n"
                    "curl -s https://api.monday.com/v2 "
                    "-d '{\"query\":\"mutation { create_item(board_id: 1) { id } }\"}'\n")
        violations = scan_tree(tmp_path, allowlist={})
        assert any("rogue-sync.sh" in v[0] and "Monday" in v[2] for v in violations)
        # both the endpoint AND the write op are independently reported
        assert sum(1 for v in violations if v[0].endswith("rogue-sync.sh")) >= 2

    def test_flags_planted_linear_mutation_in_py(self, tmp_path):
        self._write(tmp_path, "framework/rogue/linear_writer.py",
                    'QUERY = "mutation { issueCreate(input: $i) { id } }"\n')
        violations = scan_tree(tmp_path, allowlist={})
        assert any("linear_writer.py" in v[0] and "issueCreate" in v[2]
                   for v in violations)

    def test_flags_planted_jira_asana_azure_gh(self, tmp_path):
        self._write(tmp_path, "cabinet/scripts/rogue.py",
                    'A = "POST https://x.atlassian.net/rest/api/3/issue"\n'
                    'B = "https://app.asana.com/api/1.0/tasks"\n'
                    'C = "https://dev.azure.com/org/proj/_apis"\n')
        self._write(tmp_path, "cabinet/scripts/rogue-gh.sh",
                    "gh issue edit 7 --title done\n")
        violations = scan_tree(tmp_path, allowlist={})
        reasons = "\n".join(v[2] for v in violations)
        assert "Jira" in reasons and "Asana" in reasons
        assert "Azure" in reasons and "gh issue" in reasons

    def test_task_adapters_dir_is_excluded(self, tmp_path):
        self._write(tmp_path, "cabinet/scripts/task_adapters/linear.py",
                    'Q = "mutation { issueCreate }"  # the sanctioned seam\n')
        assert scan_tree(tmp_path, allowlist={}) == []

    def test_tests_dirs_and_test_files_are_excluded(self, tmp_path):
        self._write(tmp_path, "framework/x/tests/helper.py", 'Q = "issueCreate"\n')
        self._write(tmp_path, "cabinet/scripts/test_planted.py", 'Q = "create_item"\n')
        assert scan_tree(tmp_path, allowlist={}) == []

    def test_reads_and_lookalikes_do_not_trip(self, tmp_path):
        self._write(tmp_path, "cabinet/scripts/benign.sh",
                    "gh issue list --repo o/r\n"
                    "gh issue view 12\n"
                    "echo linear thinking\n"
                    'curl -s "https://x.atlassian.net/rest/api/3/search/jql"\n')
        self._write(tmp_path, "framework/benign.py",
                    "def create_items(rows): ...  # plural — no boundary match\n"
                    "monday = 'weekday'\n")
        assert scan_tree(tmp_path, allowlist={}) == []

    def test_allowlisted_file_is_skipped_but_others_still_scanned(self, tmp_path):
        self._write(tmp_path, "framework/sanctioned.py", 'Q = "create_item"\n')
        self._write(tmp_path, "framework/rogue.py", 'Q = "delete_item"\n')
        violations = scan_tree(
            tmp_path, allowlist={"framework/sanctioned.py": "test ruling"})
        assert [v[0] for v in violations] == ["framework/rogue.py"]

    def test_symlink_escape_is_refused(self, tmp_path):
        outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
        outside.write_text('Q = "issueCreate"\n', encoding="utf-8")
        (tmp_path / "framework").mkdir(parents=True)
        link = tmp_path / "framework" / "escape.py"
        try:
            link.symlink_to(outside)
        except OSError:
            if pytest is not None:
                pytest.skip("symlinks unavailable on this filesystem")
            return
        violations = scan_tree(tmp_path, allowlist={})
        assert violations == [("framework/escape.py", 0,
                               "symlink escapes the scanned tree")]


if __name__ == "__main__":  # pragma: no cover — CLI mode for the system python
    found = scan_tree(_REPO_ROOT)
    if found:
        print("canonical-tasks ratchet: VIOLATIONS\n" + _fmt(found))
        raise SystemExit(1)
    print("canonical-tasks ratchet: clean "
          f"({len(_ALLOWLISTED_FILES)} by-design allowlisted files)")
