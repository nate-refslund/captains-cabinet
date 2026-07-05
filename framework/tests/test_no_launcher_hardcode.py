"""The clean-room RATCHET — framework/ must carry no launcher identity [DN-6].

De-Nate foundation build: framework/ is the universal base shared by every
preset and every deployment, so it may not hardcode THIS launcher's captain
(``Nate``) or home path (``/Users/nate``). The one sanctioned way for framework
code to address the captain is ``framework.env.captain_name()`` (resolved from
``instance/config/platform.yml``); the one sanctioned way to find the repo is
``CABINET_ROOT`` / a file-relative ``parents[N]`` root.

This module is the RATCHET that keeps it that way. It text-walks every
``framework/**/*.py`` (``tests/`` dirs, ``__pycache__`` and ``test_*``/``*_test``
files skipped) and goes RED on any bare ``\\bNate\\b`` (case-sensitive) or any
``/Users/nate`` literal that is not covered by the documented allowlist below.
After the launcher-agnostic sweep, a NEW hardcoded ``Nate`` in framework is a CI
failure — not a review note.

Design mirrors ``framework/tests/test_axes_contract.py`` (the sister ratchet for
the axis-branch linter): stdlib-only, ``import pytest`` guarded so it also runs
under the system python, symlink-escape refused via ``os.path.realpath``
containment (a file resolving outside the scanned tree is itself a violation),
and read-ONLY (files are ``read_text``-scanned, never imported or executed).

Scope of the ratchet, deliberately narrow — it is a DISPLAY-NAME + PATH ratchet:

  * ``\\bNate\\b`` is CASE-SENSITIVE and word-bounded on purpose. It flags the
    captain's display name; it deliberately does NOT trip the legitimate
    Flavor-A brain-artifact compounds the sweep KEPT — lowercase identifiers
    like ``nate_model`` / ``nate-model`` / ``me_signal`` / ``voice``-profile
    refs, or ``copy_to_nate`` / ``nate_copy`` (see ``_BRAIN_ARTIFACTS_KEPT``).
    Those are real external artifact names, not the launcher's name, so they
    need no exemption at all — the regex simply never matches them.
  * ``/Users/nate`` flags a hardcoded home path (a launcher leak).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

try:  # also runnable under the system python without pytest (CLI mode below)
    import pytest
except ImportError:  # pragma: no cover — never the pytest-collected path
    pytest = None  # type: ignore[assignment]

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The two patterns the ratchet enforces (see module docstring for why each is
# scoped the way it is). Case-sensitive display name + literal home path.
_NATE = re.compile(r"\bNate\b")
_PATH_LITERAL = "/Users/nate"

Violation = Tuple[str, int, str]  # (display_path, line_no, reason)


# ===========================================================================
# THE ALLOWLIST  (repo-relative posix paths).  It may only ever SHRINK.
# ===========================================================================
#
# Every entry is justified in a comment. Two tiers:
#   * _ALLOWLISTED_FILES  — the WHOLE file is exempt from the scan. Reserved for
#     instance-specific fixtures the sweep flagged to move to instance/ (a file
#     that is Flavor-A by construction, not launcher-neutral framework base).
#   * _ALLOWLISTED_LINES  — only lines containing one of the given needles are
#     exempt (the rest of the file stays guarded). Reserved for a legit
#     doc-example that NAMES the anti-pattern in order to warn against it.
#
# It carries NO temporary residual entries: DN-6 initially found 29 bare-'Nate'
# occurrences across 11 framework files (incl. a category-1 RUNTIME PROMPT string
# in action_lane.py PROPOSER_SYSTEM), but the parallel launcher-agnostic sweep
# lanes cleared ALL of them in-worktree before this ratchet finalized. The
# _TEMPORARY_RESIDUALS mechanism below is the sanctioned home for any FUTURE
# stopgap; today it is empty, and a NEW hardcoded 'Nate' is a CI failure.

_ALLOWLISTED_FILES: Dict[str, str] = {
    # PERMANENT — instance-specific fixture (flagged to MOVE to instance/).
    # kristoffer_uat.py is the scoped Kristoffer-Møller-Nielsen auto-reply cell:
    # named after a specific colleague and carrying instance-only identifiers
    # (copy_to_nate / nate_copy params, nate_model, KRISTOFFER_* slugs). It is
    # Flavor-A-instance-specific by construction, so it is exempt from the
    # launcher-agnostic ratchet. TODO(DN): MOVE to instance/ (or a fixture) — a
    # colleague-scoped auto-reply is deployment config, not framework base.
    # (Carries no bare-Nate / path today — the entry documents the instance-
    # specific flag and pre-authorizes the file's Flavor-A identity.)
    "framework/autoreply/kristoffer_uat.py":
        "instance-specific (colleague-scoped auto-reply; copy_to_nate/nate_model) — MOVE to instance/",
}

_ALLOWLISTED_LINES: Dict[str, Tuple[str, ...]] = {
    # Line-scoped exemptions (not whole-file): only lines containing one of the
    # given needles are exempt, so any OTHER launcher leak in the same file is
    # still caught — important, since env.py is the resolver itself. Reserved for
    # a legit doc-example that must NAME the anti-pattern (a launcher home path)
    # in order to warn against it.
    #
    # EMPTY today: env.py's _cabinet_root() docstring and measure_intent.py's
    # namespace-shadowing comment each USED to cite a literal launcher home path
    # as the anti-pattern they warn against; both were reworded to describe it
    # WITHOUT the literal (an absolute home path / a hardcoded absolute repo
    # path), so neither line trips the ratchet and no exemption is needed. This
    # stays the sanctioned home for a FUTURE doc-example that cannot avoid the
    # literal — admitting one is a REVIEWED entry (needle + justification), never
    # a silent widening. The allowlist may only ever SHRINK.
}

# The TEMPORARY subset of _ALLOWLISTED_FILES — residual pre-sweep misses an owner
# lane had not yet de-Nated. It may only ever SHRINK.
#
# EMPTY today: the parallel sweep cleared all 11 initial residual files in-
# worktree (they now interpolate captain_name() / say "the Captain"), so the
# non-vacuous forcing-function below (``test_temporary_entries_still_needed``)
# required dropping every temporary entry. This stays as the sanctioned home for
# any FUTURE residual: admitting one is a REVIEWED stopgap — raise
# _TEMP_BASELINE_MAX WITH a justification + a FIXME + a DN deviations flag, then
# drive it back to 0. It must NEVER grow silently: a new hardcoded 'Nate' in
# framework is a CI failure, not an allowlist addition.
_TEMPORARY_RESIDUALS = frozenset()  # type: frozenset
_TEMP_BASELINE_MAX = 0  # target is always 0; raising it is a reviewed stopgap, not a fix

# Documentation only — the legitimate Flavor-A brain-artifact identifiers the
# sweep lanes KEPT (they flag these under their deviations; DN-6 records them).
# These are LOWERCASE / hyphenated external artifact names, NOT the captain's
# display name, so the case-sensitive `\bNate\b` ratchet never matches them and
# they need no active allowlist entry. Kept here as the audit trail.
_BRAIN_ARTIFACTS_KEPT: Tuple[str, ...] = (
    "Judgment call (no rename): kept internal fn nate_replied_since rather than "
    "renaming to captain_replied_since — not a runtime string/path/brain-artifact; "
    "rename is cross-file scope-creep; byte-identical either way; flagged for a "
    "coordinated rename.",
    "Did NOT rename internal identifiers copy_to_nate / nate_copy — evidence the "
    "ratchet is an allowlist-based DISPLAY-NAME ratchet, not a blunt substring "
    "grep: decision_cell.py keeps a literal 'nate' stopword AND pervasive "
    "nate_model, so a \\bNate\\b / paths ratchet does not trip these lowercase "
    "compounds. Optional coordinated rename copy_to_nate->copy_to_captain if a "
    "substring ratchet is ever adopted.",
    "brain-artifact 'voice' (voice-profile) is co-located with nate_model on "
    "kristoffer_uat.py; kept together as a category-(4) brain-artifact keep.",
)


# ---------------------------------------------------------------------------
# Tree walk (tests/ + __pycache__ + test_ files skipped; symlink-escape refused)
# ---------------------------------------------------------------------------
def iter_source_files(root: Path) -> Iterator[Path]:
    for p in sorted(Path(root).rglob("*.py")):
        parts = p.relative_to(root).parts
        if "__pycache__" in parts:
            continue
        if "tests" in parts[:-1]:  # any tests/ DIRECTORY segment
            continue
        if p.name.startswith("test_") or p.name.endswith("_test.py"):
            continue
        yield p


def scan_tree(
    root,  # type: str | Path
    files_allowlist=None,  # type: Optional[Dict[str, str]]
    lines_allowlist=None,  # type: Optional[Dict[str, Tuple[str, ...]]]
    rel_to=None,  # type: Optional[str | Path]
) -> List[Violation]:
    """Read-only scan of every non-test .py under ``root`` for a bare ``Nate``
    or a ``/Users/nate`` literal outside the allowlists.

    ``files_allowlist`` maps a whole (rel_to-relative) path to a justification;
    ``lines_allowlist`` maps a path to needles that exempt only the lines that
    contain them. Both default to the module allowlists; the engine self-tests
    inject their own so they stay hermetic. Symlink escapes are reported, never
    followed (Corridor: realpath containment); a file DISPLAY inside the
    allowlist is skipped whole."""
    root = Path(root)
    base = Path(rel_to) if rel_to is not None else root
    files_allowlist = _ALLOWLISTED_FILES if files_allowlist is None else files_allowlist
    lines_allowlist = _ALLOWLISTED_LINES if lines_allowlist is None else lines_allowlist
    real_root = os.path.realpath(str(root))
    violations = []  # type: List[Violation]
    for p in iter_source_files(root):
        try:
            display = p.relative_to(base).as_posix()
        except ValueError:
            display = p.as_posix()
        rp = os.path.realpath(str(p))
        if rp != real_root and not rp.startswith(real_root + os.sep):
            violations.append(
                (display, 0, "resolves outside the scanned tree (symlink escape) — refused"))
            continue
        if display in files_allowlist:
            continue
        needles = lines_allowlist.get(display, ())
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:  # unreadable -> fail-closed, mirror axes ratchet
            violations.append((display, 0, "unreadable: %s" % e))
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if needles and any(n in line for n in needles):
                continue
            if _NATE.search(line):
                violations.append((display, i, "bare 'Nate' — not launcher-agnostic"))
            if _PATH_LITERAL in line:
                violations.append((display, i, "hardcoded '/Users/nate' path"))
    return violations


_HINT = ("framework/ must be launcher-agnostic — use framework.env.captain_name() "
         "(see .claude/rules or docs/plans/cabinet-axes-spec)")


# ---------------------------------------------------------------------------
# The ratchet + its self-tests
# ---------------------------------------------------------------------------
class TestNoLauncherHardcode:
    def test_framework_tree_has_no_launcher_hardcode(self):
        """THE RATCHET: no bare 'Nate' / '/Users/nate' in framework/ outside the
        documented, shrink-only allowlist."""
        violations = scan_tree(_REPO_ROOT / "framework", rel_to=_REPO_ROOT)
        assert violations == [], (
            "%s\nOffenders: %s"
            % (_HINT, ["%s:%d (%s)" % (v[0], v[1], v[2]) for v in violations]))


class TestAllowlistDiscipline:
    def test_every_allowlisted_path_exists(self):
        """No dead allowlist paths — a stale entry is a silent hole."""
        missing = [rel for rel in list(_ALLOWLISTED_FILES) + list(_ALLOWLISTED_LINES)
                   if not (_REPO_ROOT / rel).exists()]
        assert missing == [], "allowlist references non-existent files: %s" % missing

    def test_line_allowlist_needles_are_actually_present(self):
        """A line-scoped exemption whose needle no longer appears is dead cover —
        it silently un-guards nothing (or, worse, masks a moved leak). Require the
        exempting text to still exist in the file."""
        stale = []
        for rel, needles in _ALLOWLISTED_LINES.items():
            f = _REPO_ROOT / rel
            if not f.exists():
                continue  # covered by test_every_allowlisted_path_exists
            text = f.read_text(encoding="utf-8", errors="replace")
            for n in needles:
                if n not in text:
                    stale.append("%s :: %r" % (rel, n))
        assert stale == [], "line-allowlist needles no longer present: %s" % stale

    def test_temporary_residuals_are_registered(self):
        """Consistency: every temporary residual is a file-tier allowlist entry."""
        stray = sorted(_TEMPORARY_RESIDUALS - set(_ALLOWLISTED_FILES))
        assert stray == [], "_TEMPORARY_RESIDUALS not in _ALLOWLISTED_FILES: %s" % stray

    def test_temporary_allowlist_only_shrinks(self):
        """Intent lock: the temporary allowlist may only SHRINK. Raising
        _TEMP_BASELINE_MAX to admit a new launcher leak is forbidden — fix the
        code (captain_name()) instead."""
        assert len(_TEMPORARY_RESIDUALS) <= _TEMP_BASELINE_MAX, (
            "temporary allowlist grew (%d > %d) — %s"
            % (len(_TEMPORARY_RESIDUALS), _TEMP_BASELINE_MAX, _HINT))

    def test_temporary_entries_still_needed(self):
        """Shrink forcing-function: a temporary entry whose file no longer
        contains any bare 'Nate' / '/Users/nate' has served its purpose and MUST
        be deleted (from both _ALLOWLISTED_FILES and _TEMPORARY_RESIDUALS). This
        is how the ratchet tightens as owner lanes de-Nate their files."""
        vacuous = []
        for rel in sorted(_TEMPORARY_RESIDUALS):
            f = _REPO_ROOT / rel
            if not f.exists():
                continue  # covered by test_every_allowlisted_path_exists
            text = f.read_text(encoding="utf-8", errors="replace")
            if not (_NATE.search(text) or _PATH_LITERAL in text):
                vacuous.append(rel)
        assert vacuous == [], (
            "these files are now clean — DELETE their temporary allowlist entries "
            "(the allowlist may only shrink): %s" % vacuous)


class TestScannerEngine:
    """Hermetic proofs that the engine itself is trustworthy (own tmp trees +
    injected allowlists — never the real framework allowlist)."""

    @staticmethod
    def _write(p: Path, body: str) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def test_flags_bare_nate_and_home_path(self, tmp_path):
        self._write(tmp_path / "pkg" / "m.py",
                    "# Nate owns this\nHOME = '/Users/nate/x'\n")
        v = scan_tree(tmp_path, files_allowlist={}, lines_allowlist={})
        assert len(v) == 2 and {r[2].split(" ")[1] for r in v} == {"'Nate'", "'/Users/nate'"}

    def test_ignores_lowercase_brain_artifacts(self, tmp_path):
        # nate_model / copy_to_nate are lowercase compounds — the display-name
        # ratchet must NOT match them (no /Users/nate here).
        self._write(tmp_path / "pkg" / "m.py",
                    "nate_model = 1\ndef copy_to_nate(): pass\nx = 'me_signal'\n")
        assert scan_tree(tmp_path, files_allowlist={}, lines_allowlist={}) == []

    def test_skips_tests_dirs_and_test_files(self, tmp_path):
        self._write(tmp_path / "pkg" / "tests" / "test_x.py", "Nate\n")
        self._write(tmp_path / "pkg" / "test_top.py", "Nate\n")
        self._write(tmp_path / "pkg" / "__pycache__" / "c.py", "Nate\n")
        assert scan_tree(tmp_path, files_allowlist={}, lines_allowlist={}) == []

    def test_whole_file_allowlist_skips(self, tmp_path):
        self._write(tmp_path / "pkg" / "m.py", "Nate here\n")
        assert scan_tree(tmp_path, files_allowlist={"pkg/m.py": "ok"},
                         lines_allowlist={}) == []

    def test_line_needle_exempts_only_that_line(self, tmp_path):
        self._write(tmp_path / "pkg" / "m.py",
                    "Nate — the anti-pattern doc\nNate elsewhere\n")
        v = scan_tree(tmp_path, files_allowlist={},
                      lines_allowlist={"pkg/m.py": ("anti-pattern doc",)})
        assert [r[1] for r in v] == [2]  # only line 2 flagged

    def test_symlink_escape_is_refused(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.py").write_text("Nate\n", encoding="utf-8")
        root = tmp_path / "root"
        root.mkdir()
        link = root / "link.py"
        try:
            link.symlink_to(outside / "secret.py")
        except (OSError, NotImplementedError):  # pragma: no cover — FS w/o symlinks
            if pytest is not None:
                pytest.skip("symlinks unsupported on this filesystem")
            return
        v = scan_tree(root, files_allowlist={}, lines_allowlist={})
        assert any("symlink escape" in r[2] for r in v)


# CLI mode: `python3 framework/tests/test_no_launcher_hardcode.py` prints every
# offender and exits non-zero — usable under the system python without pytest.
if __name__ == "__main__":  # pragma: no cover
    import sys
    offenders = scan_tree(_REPO_ROOT / "framework", rel_to=_REPO_ROOT)
    for d, i, why in offenders:
        print("%s:%d  %s" % (d, i, why))
    print(("FAIL: %s" % _HINT) if offenders else "OK: framework/ is launcher-agnostic")
    sys.exit(1 if offenders else 0)
