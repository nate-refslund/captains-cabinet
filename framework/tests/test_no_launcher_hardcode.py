"""The clean-room RATCHET — framework/ must carry no launcher OR product
identity [DN-6, E4/I4, PCA-P1].

De-Nate foundation build: framework/ is the universal base shared by every
preset and every deployment, so it may not hardcode THIS launcher's captain
(``Nate``), home path (``/Users/nate``), org domains (``stepnetwork`` / ``jfm``
/ ``jfmedier`` / ``step.dk``), Monday board ids (``50xxxxxxxx``), or a specific
PRODUCT/lane name (``polads`` / ``stephie`` and their ``-ceo`` officer forms).
The one sanctioned way for framework code to address the captain is
``framework.env.captain_name()`` (resolved from ``instance/config/platform.yml``);
the one sanctioned way to find the repo is ``CABINET_ROOT`` / a file-relative
``parents[N]`` root; org domains and board ids live in ``instance/config`` and
reach framework code only through resolvers (mirroring ``captain_name()``);
product/lane names are resolved the same way, via ``framework.env.officers()``
/ ``framework.env.lane_default()`` (read from ``instance/config/roster.yml`` /
``platform.yml`` — the Product/captain-agnostic foundation, Captain directive
2026-07-14: "polads should not be referenced in the repo... product/captain-
agnostic ALWAYS").

This module is the RATCHET that keeps it that way. It text-walks every
``framework/**/*.py`` (``tests/`` dirs, ``__pycache__`` and ``test_*``/``*_test``
files skipped) and goes RED on any launcher literal that is not covered by the
documented, shrink-only allowlist below. After the launcher-agnostic sweep, a
NEW hardcoded launcher literal in framework is a CI failure — not a review note.

Design mirrors ``framework/tests/test_axes_contract.py`` (the sister ratchet for
the axis-branch linter): stdlib-only, ``import pytest`` guarded so it also runs
under the system python, symlink-escape refused via ``os.path.realpath``
containment (a file resolving outside the scanned tree is itself a violation),
and read-ONLY (files are ``read_text``-scanned, never imported or executed).
Every pattern is a STATIC module regex (no dynamic/user-controlled construction,
so no ReDoS surface) matched against repo source text.

Scope of the ratchet, deliberately narrow — it is a launcher-IDENTITY ratchet
over five literal families:

  * ``\\bNate\\b`` is CASE-SENSITIVE and word-bounded on purpose. It flags the
    captain's display name; it deliberately does NOT trip the legitimate
    Flavor-A brain-artifact compounds the sweep KEPT — lowercase identifiers
    like ``nate_model`` / ``nate-model`` / ``me_signal`` / ``voice``-profile
    refs, or ``copy_to_nate`` / ``nate_copy`` (see ``_BRAIN_ARTIFACTS_KEPT``).
    Those are real external artifact names, not the launcher's name, so they
    need no exemption at all — the regex simply never matches them.
  * ``/Users/<name>`` and ``/home/<name>`` flag a hardcoded absolute home path
    (a launcher leak) — generalized beyond ``/Users/nate`` so ANY launcher's
    home dir trips it. ``/Users/`` case-sensitive (macOS), ``/home/`` (Linux).
  * ``stepnetwork`` / ``jfmedier`` / ``jfm`` / ``step.dk`` (case-insensitive,
    word-bounded) flag THIS org's domain literals — extracted this run (E4 lane
    I2) to ``instance/config``; framework must reach them via a resolver, never
    a literal. Word-bounding keeps ``jfm`` from matching inside ``jfmedier`` and
    keeps bare ``step`` (a common word) from ever tripping.
  * ``50`` + 8 digits (a 10-digit Monday BOARD id) flags an instance board id.
    Anchored to exactly ten digits so it does not match inside a longer number
    (ms timestamps, item ids) and does not match non-``50`` Monday item ids.
  * ``polads`` / ``stephie`` (case-insensitive, word-bounded — added PCA-P1,
    Captain directive 2026-07-14) flag a hardcoded PRODUCT/lane identity.
    Word-bounding still catches the ``-ceo`` officer forms and the ``.eu``
    domain form because ``-``/``.`` are non-word characters (a boundary exists
    on either side of the bare token), the same mechanism ``jfm`` relies on
    above. Product/lane names live in ``instance/config`` and reach framework
    only through ``framework.env.officers()`` / ``framework.env.lane_default()``.
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

# The launcher-literal patterns the ratchet enforces (see module docstring for
# why each is scoped the way it is). Each is a STATIC compiled regex; the scanner
# reports ``m.group(0)`` (the exact literal) in the violation reason so a real
# miss is precise. ``_CHECKS`` pairs each regex with a ``%s`` reason template.
_NATE = re.compile(r"\bNate\b")                       # case-sensitive display name
_HOME_PATH = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+")  # absolute home dir
_ORG_DOMAIN = re.compile(r"\b(?:stepnetwork|jfmedier|jfm|step\.dk)\b", re.IGNORECASE)
_BOARD_ID = re.compile(r"\b50\d{8}\b")                # 10-digit Monday board id
_PRODUCT_TOKEN = re.compile(r"\b(?:polads|stephie)\b", re.IGNORECASE)  # PCA-P1

_CHECKS: Tuple[Tuple["re.Pattern[str]", str], ...] = (
    (_NATE, "bare '%s' — not launcher-agnostic"),
    (_HOME_PATH, "hardcoded home path '%s'"),
    (_ORG_DOMAIN, "hardcoded org-domain literal '%s'"),
    (_BOARD_ID, "hardcoded Monday board-id '%s'"),
    (_PRODUCT_TOKEN, "hardcoded product/lane token '%s' — not product-agnostic"),
)

Violation = Tuple[str, int, str]  # (display_path, line_no, reason)


# ===========================================================================
# THE ALLOWLIST  (repo-relative posix paths).  It may only ever SHRINK.
# ===========================================================================
#
# Every entry is justified in a comment. Three tiers:
#   * _ALLOWLISTED_FILES  — the WHOLE file is exempt from the scan. Reserved for
#     instance-specific fixtures the sweep flagged to move to instance/ (a file
#     that is Flavor-A by construction, not launcher-neutral framework base).
#   * _ALLOWLISTED_LINES  — PERMANENT line-scoped exemptions: only lines
#     containing one of the given needles are exempt (the rest of the file stays
#     guarded). Reserved for a legit doc-example that NAMES an anti-pattern in
#     order to warn against it.
#   * _TEMPORARY_LINE_RESIDUALS — TEMPORARY line-scoped exemptions: an instance
#     literal an owner extraction lane has not YET reworded out of a docstring /
#     comment (the runtime code is already launcher-agnostic — the value travels
#     as a resolver / CONFIG lookup / parameter; only the doc CITATION leaks the
#     literal). Shrink-only (capped by _TEMP_LINE_BASELINE_MAX); the
#     needle-presence test auto-forces each entry's deletion the moment the owner
#     lane rewords, because the needle IS the literal.
#
# It carries NO permanent launcher residual: DN-6 initially found 29 bare-'Nate'
# occurrences across 11 framework files (incl. a category-1 RUNTIME PROMPT string
# in action_lane.py PROPOSER_SYSTEM), but the parallel launcher-agnostic sweep
# lanes cleared ALL of them in-worktree before this ratchet finalized. The
# temporary mechanisms below are the sanctioned home for any FUTURE stopgap; a
# NEW hardcoded launcher literal is a CI failure, not a silent allowlist growth.

_ALLOWLISTED_FILES: Dict[str, str] = {
    # EMPTY today. kristoffer_uat.py (the colleague-scoped auto-reply cell, named
    # for a specific colleague and carrying instance-only identifiers) was
    # the sole whole-file entry; E4 lane I3 MOVED it OUT of framework to
    # instance/flavor-a/autoreply/kristoffer_uat.py, so the launcher-agnostic base
    # no longer carries it and the exemption is gone with the file. A future
    # instance-specific fixture that must transiently live under framework/ is the
    # only sanctioned reason to re-add a whole-file entry — a REVIEWED addition
    # (path + justification), never a silent widening. The allowlist may only SHRINK.
}

_ALLOWLISTED_LINES: Dict[str, Tuple[str, ...]] = {
    # PERMANENT line-scoped exemptions — only lines containing one of the given
    # needles are exempt, so any OTHER launcher leak in the same file is still
    # caught. Reserved for a legit doc-example that must NAME an anti-pattern (a
    # launcher home path, an org domain) in order to warn against it.
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

# TEMPORARY line residuals — E4 lane I4 (board ids) + PCA-P1 (product/lane
# tokens, added 2026-07-15). Each entry is a literal (board id OR product/
# officer token) that is EITHER (a) an owner extraction lane has not YET
# reworded out of a DOCSTRING — I4's original case: the RUNTIME code is
# already launcher-agnostic, only the doc CITATION leaks the literal — OR (b)
# lives in a file on cabinet/scripts/germline-lock.sh's schg FILES[] list
# (verified via `germline-lock.sh` + `ls -lO` on the live tree — schg is a
# live-tree-only filesystem flag, invisible in a worktree, so it must be
# checked on the deployment, never assumed), where the real fix is verified
# and STAGED DARK pending the next Captain-sudo germline ceremony. A germline
# path is NEVER edited or worked around (cabinet-meta CLAUDE.md "Germline
# etiquette") — a tracked, forcing-function-backed residual entry here is the
# sanctioned handback, not a workaround.
#
# board id (I4, unchanged): actfirst_canary.py's docstring citation of "board
# 5091706356" — the board id travels as a function parameter
# (actfirst_canary._discover_probe_target(board=...)); only the docstring
# names it. FIXME(I2/board-id-sweep): reword the docstring, then delete.
#
# product/lane tokens (PCA-P1, Captain directive 2026-07-14 "product/captain-
# agnostic ALWAYS" — all five entries below are germline, confirmed schg on
# the live tree 2026-07-15):
#   * action_lane.py: PROPOSER_SYSTEM officer-enum literal (@158) and
#     lane_default="polads" (@470) — the resolver-based fix (env.officers() /
#     env.lane_default() at compose/call time) is VERIFIED and staged dark on
#     feat/wave-g-lockstep; see ledger row CG-25 + docs/proposals/germline-
#     lockstep-lane-resolver-addendum-2026-07-12.md. The @117 dataclass
#     comment is dated design rationale CG-25 records as "recon disposition
#     (leave-with-reason)". Applies at the next germline ceremony.
#   * action_exec.py: _DELEGATE_OFFICERS whitelist literal (@848) — the same
#     CG-25 staged patch (call-time frozenset(env.officers())).
#   * run_action_lane.py (@185/232/249): dated design-rationale comments
#     citing the same officer names — CG-25's note records this as "recon
#     disposition (leave-with-reason)" too, kept as historical record, not
#     part of the staged patch.
#   * situation.py (@87) + graduation.py (@13): germline (both confirmed in
#     germline-lock.sh FILES[]); product-token doc citations not covered by a
#     prior named ledger row — filed as ledger row PCA-P1-RATCHET in the same
#     commit as this entry.
#
# The needle IS the literal in every case, so the exemption is surgical — it
# un-guards ONLY the cited line and leaves the rest of each file fully guarded
# for every check, including this one. FORCING FUNCTION: the moment a lane
# rewords a doc line to drop the literal (I4-style) or a germline ceremony
# lands the resolver-based fix, the needle vanishes and
# test_line_allowlist_needles_are_actually_present goes RED — forcing that
# entry's deletion (the allowlist may only shrink). (The daily_recap.py entry
# left 2026-07-07 with egg row R023 is the precedent: the Monday Reflections
# leg and its board-id docstring citation were DELETED from the module, so the
# needle — and the exemption — went with the code.)
# FIXME(I2/board-id-sweep): reword the actfirst_canary docstring, then delete that entry.
# FIXME(CG-25/germline-ceremony): once the ceremony applies the staged patch,
# delete the action_lane.py + action_exec.py entries below.
# FIXME(PCA-P1-RATCHET/germline-ceremony): once a ceremony reworks the doc
# citations, delete the run_action_lane.py + situation.py + graduation.py entries.
_TEMPORARY_LINE_RESIDUALS: Dict[str, Tuple[str, ...]] = {
    "framework/frontdoor/actfirst_canary.py": ("5091706356",),
    "framework/acting/action_lane.py": ('"polads"', '"polads-ceo"'),
    "framework/frontdoor/action_exec.py": ('"polads-ceo"',),
    "framework/acting/run_action_lane.py": ("'polads-ceo'",),
    "framework/attention/situation.py": ("polads.eu",),
    "framework/fidelity/graduation.py": ('"polads"',),
}
_TEMP_LINE_BASELINE_MAX = 7  # target is always 0; this may only be LOWERED (shrink-only), never raised

# The whole-file temporary residual mechanism (residual pre-sweep misses an owner
# lane had not yet cleaned, exempted at WHOLE-FILE granularity). EMPTY today — the
# parallel sweep cleared all initial residual files, and I4's board-id residuals
# are line-scoped (above), not whole-file. Kept as the sanctioned home for any
# FUTURE whole-file residual: admitting one is a REVIEWED stopgap — raise
# _TEMP_BASELINE_MAX WITH a justification + a FIXME + a DN deviations flag, then
# drive it back to 0. It must NEVER grow silently.
_TEMPORARY_RESIDUALS = frozenset()  # type: frozenset
_TEMP_BASELINE_MAX = 0  # target is always 0; raising it is a reviewed stopgap, not a fix

# The line-allowlist the real ratchet + CLI scan with: the PERMANENT doc-example
# tier merged with the TEMPORARY residual tier (needles concatenated per path).
# Self-tests inject their own allowlists, never this merged one.
def _merge_line_allowlists(*sources: Dict[str, Tuple[str, ...]]) -> Dict[str, Tuple[str, ...]]:
    merged = {}  # type: Dict[str, Tuple[str, ...]]
    for src in sources:
        for rel, needles in src.items():
            merged[rel] = merged.get(rel, ()) + tuple(needles)
    return merged


_LINE_ALLOWLIST = _merge_line_allowlists(_ALLOWLISTED_LINES, _TEMPORARY_LINE_RESIDUALS)

# Documentation only — the legitimate Flavor-A brain-artifact identifiers the
# sweep lanes KEPT (they flag these under their deviations; DN-6 records them).
# These are LOWERCASE / hyphenated external artifact names, NOT the captain's
# display name, so the case-sensitive `\bNate\b` ratchet never matches them and
# they need no active allowlist entry. Kept here as the audit trail.
_BRAIN_ARTIFACTS_KEPT: Tuple[str, ...] = (
    "RESOLVED (T1 protocol widen, 2026-07-07): the flagged coordinated rename "
    "landed at the CONTRACT surface — framework core + base.PersonalSource now "
    "speak captain_replied_since; the lowercase nate_replied_since survives "
    "only in instance/flavor-a (the acting impl + a thin adapter back-compat "
    "alias), outside this framework-only ratchet's scan tree either way.",
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
# Per-line detection (shared by the scanner and the still-needed forcing test)
# ---------------------------------------------------------------------------
def _line_violations(line: str) -> List[str]:
    """Every launcher-literal reason that fires on a single source line (one per
    matching check; each reason embeds the exact matched literal)."""
    out = []  # type: List[str]
    for rx, tmpl in _CHECKS:
        m = rx.search(line)
        if m:
            out.append(tmpl % m.group(0))
    return out


def _text_has_any_leak(text: str) -> bool:
    """True if any line of ``text`` carries a launcher literal (any check)."""
    return any(_line_violations(line) for line in text.splitlines())


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
    """Read-only scan of every non-test .py under ``root`` for a launcher OR
    product literal (bare ``Nate``, an absolute home path, an org domain, a
    Monday board id, or a ``polads``/``stephie`` product/lane token) outside
    the allowlists.

    ``files_allowlist`` maps a whole (rel_to-relative) path to a justification;
    ``lines_allowlist`` maps a path to needles that exempt only the lines that
    contain them. Both default to the module allowlists (the line default is the
    MERGED permanent+temporary view); the engine self-tests inject their own so
    they stay hermetic. Symlink escapes are reported, never followed (Corridor:
    realpath containment); a file DISPLAY inside the allowlist is skipped whole."""
    root = Path(root)
    base = Path(rel_to) if rel_to is not None else root
    files_allowlist = _ALLOWLISTED_FILES if files_allowlist is None else files_allowlist
    lines_allowlist = _LINE_ALLOWLIST if lines_allowlist is None else lines_allowlist
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
            for reason in _line_violations(line):
                violations.append((display, i, reason))
    return violations


_HINT = ("framework/ must be launcher- AND product-agnostic — address the captain via "
         "framework.env.captain_name(), officers/lanes via framework.env.officers() / "
         "framework.env.lane_default(), and read org domains / board ids from "
         "instance/config resolvers (see .claude/rules or docs/plans/cabinet-axes-spec)")


# ---------------------------------------------------------------------------
# The ratchet + its self-tests
# ---------------------------------------------------------------------------
class TestNoLauncherHardcode:
    def test_framework_tree_has_no_launcher_hardcode(self):
        """THE RATCHET: no launcher OR product literal (Nate / home path / org
        domain / board id / polads-stephie product token) in framework/
        outside the documented, shrink-only allowlist."""
        violations = scan_tree(_REPO_ROOT / "framework", rel_to=_REPO_ROOT)
        assert violations == [], (
            "%s\nOffenders: %s"
            % (_HINT, ["%s:%d (%s)" % (v[0], v[1], v[2]) for v in violations]))


class TestAllowlistDiscipline:
    def test_every_allowlisted_path_exists(self):
        """No dead allowlist paths — a stale entry is a silent hole."""
        referenced = list(_ALLOWLISTED_FILES) + list(_LINE_ALLOWLIST)
        missing = [rel for rel in referenced if not (_REPO_ROOT / rel).exists()]
        assert missing == [], "allowlist references non-existent files: %s" % missing

    def test_line_allowlist_needles_are_actually_present(self):
        """A line-scoped exemption whose needle no longer appears is dead cover —
        it silently un-guards nothing (or, worse, masks a moved leak). Require the
        exempting text to still exist in the file. This is ALSO the forcing
        function for the temporary board-id residuals: when the owner lane rewords
        the docstring, the board-id needle vanishes and this goes RED, forcing the
        temporary entry's deletion (the allowlist may only shrink)."""
        stale = []
        for rel, needles in _LINE_ALLOWLIST.items():
            f = _REPO_ROOT / rel
            if not f.exists():
                continue  # covered by test_every_allowlisted_path_exists
            text = f.read_text(encoding="utf-8", errors="replace")
            for n in needles:
                if n not in text:
                    stale.append("%s :: %r" % (rel, n))
        assert stale == [], "line-allowlist needles no longer present: %s" % stale

    def test_temporary_line_allowlist_only_shrinks(self):
        """Intent lock: the temporary LINE residual set may only SHRINK. Admitting
        a new residual raises the count past the baseline — forbidden without
        LOWERING nothing; fix the code (resolver / reword the docstring) instead of
        widening. The baseline itself may only be lowered."""
        count = sum(len(v) for v in _TEMPORARY_LINE_RESIDUALS.values())
        assert count <= _TEMP_LINE_BASELINE_MAX, (
            "temporary line-residual allowlist grew (%d > %d) — %s"
            % (count, _TEMP_LINE_BASELINE_MAX, _HINT))

    def test_temporary_residuals_are_registered(self):
        """Consistency: every whole-file temporary residual is a file-tier entry."""
        stray = sorted(_TEMPORARY_RESIDUALS - set(_ALLOWLISTED_FILES))
        assert stray == [], "_TEMPORARY_RESIDUALS not in _ALLOWLISTED_FILES: %s" % stray

    def test_temporary_allowlist_only_shrinks(self):
        """Intent lock: the whole-file temporary allowlist may only SHRINK. Raising
        _TEMP_BASELINE_MAX to admit a new launcher leak is forbidden — fix the code
        (captain_name() / a resolver) instead."""
        assert len(_TEMPORARY_RESIDUALS) <= _TEMP_BASELINE_MAX, (
            "temporary allowlist grew (%d > %d) — %s"
            % (len(_TEMPORARY_RESIDUALS), _TEMP_BASELINE_MAX, _HINT))

    def test_temporary_entries_still_needed(self):
        """Shrink forcing-function: a whole-file temporary entry whose file no
        longer contains ANY launcher literal has served its purpose and MUST be
        deleted (from both _ALLOWLISTED_FILES and _TEMPORARY_RESIDUALS). This is how
        the ratchet tightens as owner lanes clean their files."""
        vacuous = []
        for rel in sorted(_TEMPORARY_RESIDUALS):
            f = _REPO_ROOT / rel
            if not f.exists():
                continue  # covered by test_every_allowlisted_path_exists
            if not _text_has_any_leak(f.read_text(encoding="utf-8", errors="replace")):
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
        reasons = " ".join(r[2] for r in v)
        assert len(v) == 2
        assert "'Nate'" in reasons and "launcher-agnostic" in reasons
        assert "home path" in reasons and "/Users/nate" in reasons

    def test_flags_generic_home_paths(self, tmp_path):
        # a DIFFERENT launcher's home dir (not /Users/nate) and a Linux /home/
        # both trip the generalized path check.
        self._write(tmp_path / "pkg" / "m.py",
                    "A = '/Users/anders/repo'\nB = '/home/bob/cabinet'\n")
        v = scan_tree(tmp_path, files_allowlist={}, lines_allowlist={})
        reasons = " ".join(r[2] for r in v)
        assert len(v) == 2
        assert "/Users/anders" in reasons and "/home/bob" in reasons

    def test_flags_org_domain_literals(self, tmp_path):
        self._write(tmp_path / "pkg" / "m.py",
                    "EMAIL = 'x@stepnetwork.dk'\nORG = 'jysk.jfmedier.dk'\nAI = 'ai.step.dk'\n")
        v = scan_tree(tmp_path, files_allowlist={}, lines_allowlist={})
        reasons = " ".join(r[2] for r in v)
        assert len(v) == 3
        assert "org-domain" in reasons
        assert "stepnetwork" in reasons and "jfmedier" in reasons and "step.dk" in reasons

    def test_flags_monday_board_id(self, tmp_path):
        self._write(tmp_path / "pkg" / "m.py", "BOARD = 5091706356\n")
        v = scan_tree(tmp_path, files_allowlist={}, lines_allowlist={})
        assert len(v) == 1
        assert "board-id" in v[0][2] and "5091706356" in v[0][2]

    def test_flags_product_token_literals(self, tmp_path):
        # Both bare tokens and their hyphenated -ceo/.eu forms must trip the
        # check (word-bounding, not whole-token matching — mirrors how `jfm`
        # is still caught inside `jfmedier` above).
        self._write(tmp_path / "pkg" / "m.py",
                    "OFFICER = 'polads-ceo'\nLANE = \"Stephie\"\nURL = 'stephie.dk'\n")
        v = scan_tree(tmp_path, files_allowlist={}, lines_allowlist={})
        reasons = " ".join(r[2] for r in v)
        assert len(v) == 3
        assert "product/lane token" in reasons
        assert "polads" in reasons and "Stephie" in reasons

    def test_ignores_non_launcher_lookalikes(self, tmp_path):
        # Critical false-positive guard for a ratchet: bare 'step', a non-50
        # Monday item id, a 9- and 11-digit number, '/usr/local', and lowercase
        # nate_* compounds must ALL stay green.
        self._write(tmp_path / "pkg" / "m.py",
                    "for step in range(10): pass\n"      # bare 'step' != stepnetwork
                    "ITEM = 2712412402\n"                # Monday ITEM id (starts 2) — out of scope
                    "NINE = 509170635\n"                 # 9 digits
                    "ELEVEN = 50917063560\n"             # 11 digits (no 10-digit boundary)
                    "P = '/usr/local/bin'\n"             # not a home path
                    "nate_model = 1\n"                   # lowercase brain artifact
                    "poladsboard_other = 1\n")           # NOT polads-* — no boundary, must stay green
        assert scan_tree(tmp_path, files_allowlist={}, lines_allowlist={}) == []

    def test_ignores_lowercase_brain_artifacts(self, tmp_path):
        # nate_model / copy_to_nate are lowercase compounds — the display-name
        # ratchet must NOT match them (and no other check trips either).
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

    def test_board_id_needle_exempts_the_doc_citation(self, tmp_path):
        # Proves the temporary-residual shape: a board-id needle exempts the
        # docstring line that cites it, while a bare Nate on another line is still
        # caught (the exemption is surgical, not whole-file).
        self._write(tmp_path / "pkg" / "m.py",
                    "# board 5091706356 LACKS column status\nNATE = 'Nate'\n")
        v = scan_tree(tmp_path, files_allowlist={},
                      lines_allowlist={"pkg/m.py": ("5091706356",)})
        assert len(v) == 1 and v[0][1] == 2 and "'Nate'" in v[0][2]

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
