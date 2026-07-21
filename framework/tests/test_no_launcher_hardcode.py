"""The clean-room RATCHET — framework/ must carry no launcher OR product
identity.

``framework/`` is the universal base shared by every preset and every
deployment, so it may not hardcode ANY launcher's captain display name, home
path, employer/org domains, external board/tracker ids, or a specific
PRODUCT/lane name (and its ``-ceo`` officer / ``.<tld>`` domain forms). The one
sanctioned way for framework code to address the captain is
``framework.env.captain_name()`` (resolved from ``instance/config/platform.yml``);
the one sanctioned way to find the repo is ``CABINET_ROOT`` / a file-relative
``parents[N]`` root; org domains live in ``instance/config`` and reach framework
code only through resolvers (mirroring ``captain_name()``); product/lane names
are resolved the same way, via ``framework.env.officers()`` /
``framework.env.lane_default()`` — the product/captain-agnostic foundation.

This module is the RATCHET that keeps it that way. It text-walks every
``framework/**/*.py`` (``tests/`` dirs, ``__pycache__`` and ``test_*``/``*_test``
files skipped) and goes RED on any launcher literal that is not covered by the
documented, shrink-only allowlist below. A NEW hardcoded launcher literal in
framework is a CI failure — not a review note.

Two enforcement halves, by design:

  * THIS module is the tracked, captain-AGNOSTIC half. Every pattern below is
    either a STRUCTURAL shape (an absolute home path — launcher-independent) or
    a SYNTHETIC example-identity token (the demo captain **Testburg** / its demo
    lane **bakery** / its demo domain ``testburg.example`` / a placeholder
    personal-source adapter) so the shipped source names no real person, org, or
    product. The self-tests below plant those synthetic tokens to prove the
    scanner engine (tree walk, per-line multi-check, allowlist masking,
    symlink-escape refusal) is trustworthy.
  * The per-DEPLOYMENT half — the real name/employer/product literals of a
    concrete deployment — lives in the UNTRACKED, gitignored
    ``instance/config/publish-scan-patterns.local`` and is enforced by the
    publish gate (``cabinet/scripts/egg-publish-gate.sh`` gate (d), which also
    runs THIS pytest as gate (c)) + the generic ``id:[0-9]{9,}`` board/chat-id
    run it carries tracked. That is where a deployment keeps full teeth; a
    public egg cut ships neither the file nor a real token.

Design mirrors ``framework/tests/test_axes_contract.py`` (the sister ratchet for
the axis-branch linter): stdlib-only, ``import pytest`` guarded so it also runs
under the system python, symlink-escape refused via ``os.path.realpath``
containment (a file resolving outside the scanned tree is itself a violation),
and read-ONLY (files are ``read_text``-scanned, never imported or executed).
Every pattern is a STATIC module regex (no dynamic/user-controlled construction,
so no ReDoS surface) matched against repo source text.

Scope of the ratchet, deliberately narrow — a launcher-IDENTITY ratchet over
these literal families:

  * ``\\bTestburg\\b`` is CASE-SENSITIVE and word-bounded on purpose: it stands
    for the captain display name. Word-bounding deliberately does NOT trip the
    legitimate lowercase brain-artifact compounds (identifiers like
    ``testburg_model`` / ``copy_to_testburg`` / ``me_signal``) — an underscore is
    a ``\\w`` character (no boundary either side), so the regex simply never
    matches them (see ``_BRAIN_ARTIFACTS_KEPT``).
  * ``/Users/<name>`` and ``/home/<name>`` flag a hardcoded absolute home path
    (a launcher leak) — STRUCTURAL, so ANY launcher's home dir trips it.
    ``/Users/`` case-sensitive (macOS), ``/home/`` (Linux). This is the one
    check whose teeth are launcher-independent, not example-token based.
  * ``testburg.example`` / ``bakery.example`` (case-insensitive) stand for the
    employer/lane domain literals a deployment must reach via a resolver, never
    hardcode.
  * ``bakery`` (case-insensitive, word-bounded) stands for a hardcoded
    PRODUCT/lane identity. Word-bounding still catches ``-ceo`` officer forms and
    ``.<tld>`` domain forms because ``-``/``.`` are non-word characters (a
    boundary exists on either side of the bare token). Product/lane names live in
    ``instance/config`` and reach framework only through
    ``framework.env.officers()`` / ``framework.env.lane_default()``.
  * a placeholder personal-source-adapter token (``examplesource`` /
    ``examplevault``, case-insensitive, word-bounded) stands for a hardcoded
    PERSONAL-SOURCE-ADAPTER identity leaking into framework/ prose. The framework
    SEAM is adapter-agnostic — a *personal-source* Protocol
    (``framework.sources.base``), never a hardcoded product name; the concrete,
    opt-in adapter lives ENTIRELY in ``instance/flavor-a/`` (outside this
    ratchet's scan tree, guarded more narrowly by the sister import/path-coupling
    ratchet for the personal-source seam) and is free to keep its own name there;
    framework/ itself may only say "the personal-source adapter" / "Flavor-A".
  * bare ``testburg`` (case-INSENSITIVE and word-bounded) closes the gap the
    case-sensitive ``\\bTestburg\\b`` display-name check leaves open: an ALL-CAPS
    convention tag and a lowercase prose mention. Word-bounding still means the
    UNDERSCORE compounds never match, case-insensitive or not (verified by
    ``test_ignores_adapter_and_captain_lookalikes`` below); a HYPHENATED compound
    WOULD (a hyphen IS a boundary), and one appearing would correctly go RED.

External board/tracker id runs are NOT a family here: they are a generic numeric
SHAPE, not a launcher identity, and are covered captain-agnostically by the
publish gate's tracked ``id:[0-9]{9,}`` scan — duplicating a source-specific
``50\\d{8}`` shape in this tracked ratchet would only re-introduce a
deployment-flavoured literal.
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
# Tokens below are the SYNTHETIC demo identity (captain Testburg / lane bakery /
# domain ``*.example`` / placeholder adapter) — no real name/org/product is
# tracked here; a deployment's real literals live in the untracked publish-scan
# file the gate loads (module docstring). Board/chat-id runs are a generic
# numeric SHAPE, covered captain-agnostically by the gate's tracked
# ``id:[0-9]{9,}`` scan rather than a source-flavoured ``50\d{8}`` literal here.
_CAPTAIN = re.compile(r"\bTestburg\b")                       # case-sensitive display name
_HOME_PATH = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+")  # absolute home dir (STRUCTURAL)
_ORG_DOMAIN = re.compile(r"\btestburg\.example\b|\bbakery\.example\b", re.IGNORECASE)
_PRODUCT_TOKEN = re.compile(r"\bbakery\b", re.IGNORECASE)    # product/lane token
_ADAPTER = re.compile(r"\b(?:examplesource|examplevault)\b", re.IGNORECASE)  # personal-source adapter
_CAPTAIN_TOKEN = re.compile(r"\btestburg\b", re.IGNORECASE)  # any-case bare captain token

_CHECKS: Tuple[Tuple["re.Pattern[str]", str], ...] = (
    (_CAPTAIN, "bare '%s' — not launcher-agnostic"),
    (_HOME_PATH, "hardcoded home path '%s'"),
    (_ORG_DOMAIN, "hardcoded org-domain literal '%s'"),
    (_PRODUCT_TOKEN, "hardcoded product/lane token '%s' — not product-agnostic"),
    (_ADAPTER, "hardcoded personal-source-adapter token '%s' — not adapter-agnostic"),
    (_CAPTAIN_TOKEN, "bare '%s' (any case) — not launcher-agnostic"),
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
#   * _TEMPORARY_LINE_RESIDUALS — TEMPORARY line-scoped exemptions: a source
#     literal an owner extraction lane has not YET reworded out of a docstring /
#     comment (the runtime code is already launcher-agnostic — the value travels
#     as a resolver / CONFIG lookup / parameter; only the doc CITATION leaks the
#     literal). Shrink-only (capped by _TEMP_LINE_BASELINE_MAX); the
#     needle-presence test auto-forces each entry's deletion the moment the owner
#     lane rewords, because the needle IS the literal.
#
# All three tiers are EMPTY: framework/ carries no launcher literal, so nothing
# needs exempting. They stay as the sanctioned, shrink-only home for a FUTURE
# stopgap — a NEW hardcoded launcher literal is a CI failure, not a silent
# allowlist growth.

_ALLOWLISTED_FILES: Dict[str, str] = {
    # EMPTY. The only sanctioned reason to add a whole-file entry is an
    # instance-specific fixture that must transiently live under framework/ — a
    # REVIEWED addition (path + justification), never a silent widening. The
    # allowlist may only SHRINK.
}

_ALLOWLISTED_LINES: Dict[str, Tuple[str, ...]] = {
    # PERMANENT line-scoped exemptions — only lines containing one of the given
    # needles are exempt, so any OTHER launcher leak in the same file is still
    # caught. Reserved for a legit doc-example that must NAME an anti-pattern (a
    # launcher home path, an org domain) in order to warn against it. EMPTY —
    # admitting one is a REVIEWED entry (needle + justification), never a silent
    # widening. The allowlist may only ever SHRINK.
}

# TEMPORARY line residuals — the sanctioned home for a per-line stopgap when an
# owner extraction lane has not YET reworded a source literal out of a framework
# docstring/comment (the runtime code already resolves the value via
# env.captain_name() / env.officers() / env.lane_default(); only the doc CITATION
# would leak the literal). Each entry would be {path: (needle, ...)} exempting
# ONLY the lines that contain a needle, leaving the rest of the file guarded.
# EMPTY: framework/ carries no such residual. Admitting one is a REVIEWED entry
# (path + needle + justification) that RAISES _TEMP_LINE_BASELINE_MAX with a
# FIXME; test_line_allowlist_needles_are_actually_present auto-forces its
# deletion the moment the owner lane rewords, because the needle IS the literal
# (the allowlist may only ever shrink).
_TEMPORARY_LINE_RESIDUALS: Dict[str, Tuple[str, ...]] = {}
_TEMP_LINE_BASELINE_MAX = 0  # target is always 0; may only be LOWERED (shrink-only), never raised

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
    "The ratchet is an allowlist-based DISPLAY-NAME ratchet, not a blunt "
    "substring grep: the word-bounded checks deliberately do NOT trip lowercase "
    "UNDERSCORE compounds (an underscore is a \\w char, so there is no boundary "
    "on either side) — identifiers like testburg_model / copy_to_testburg / "
    "me_signal stay green even under the any-case captain-token check "
    "(test_ignores_adapter_and_captain_lookalikes proves it). A coordinated "
    "rename to a resolver-derived name (copy_to_testburg -> copy_to_captain) is "
    "optional and would only matter if a substring ratchet were ever adopted.",
    "A personal-source ADAPTER may keep its own product name inside "
    "instance/flavor-a/ (outside this framework-only ratchet's scan tree); "
    "framework/ core speaks only the resolver contract (captain_replied_since, "
    "framework.env.captain_name()), never a launcher-flavoured literal.",
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
    """Read-only scan of every non-test .py under ``root`` for a launcher,
    product, OR personal-source-adapter literal (the captain display name any
    case, an absolute home path, an org/lane domain, a product/lane token, or a
    personal-source-adapter token) outside the allowlists.

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


_HINT = ("framework/ must be launcher-, product-, AND adapter-agnostic — address the "
         "captain via framework.env.captain_name(), officers/lanes via "
         "framework.env.officers() / framework.env.lane_default(), read org domains / "
         "board ids from instance/config resolvers (see .claude/rules or "
         "docs/plans/cabinet-axes-spec), and reach the personal-source estate ONLY "
         "through framework.sources.get_source() / get_dispatch() — the concrete "
         "opt-in adapter lives entirely in instance/flavor-a/ and may keep its own "
         "name there, never in framework/")


# ---------------------------------------------------------------------------
# The ratchet + its self-tests
# ---------------------------------------------------------------------------
class TestNoLauncherHardcode:
    def test_framework_tree_has_no_launcher_hardcode(self):
        """THE RATCHET: no launcher, product, OR personal-source-adapter
        literal (captain display name any case / home path / org-lane domain /
        product/lane token / personal-source-adapter token) in framework/
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

    def test_flags_bare_captain_and_home_path(self, tmp_path):
        # 4, not 2: the any-case _CAPTAIN_TOKEN check ALSO fires on both lines —
        # "Testburg" on line 1 (already caught by the case-sensitive display-name
        # check too) and the lowercase "testburg" inside the /Users/testburg/x
        # home path on line 2 (already caught by the home-path check too). Two
        # independent checks legitimately firing on the same literal is correct,
        # not a bug — see test_line_needle_exempts_only_that_line /
        # test_home_path_needle_exempts_the_doc_citation below for the same recount.
        self._write(tmp_path / "pkg" / "m.py",
                    "# Testburg owns this\nHOME = '/Users/testburg/x'\n")
        v = scan_tree(tmp_path, files_allowlist={}, lines_allowlist={})
        reasons = " ".join(r[2] for r in v)
        assert len(v) == 4
        assert [r[1] for r in v] == [1, 1, 2, 2]
        assert "'Testburg'" in reasons and "launcher-agnostic" in reasons
        assert "home path" in reasons and "/Users/testburg" in reasons

    def test_flags_generic_home_paths(self, tmp_path):
        # a DIFFERENT launcher's home dir (not the demo captain's) and a Linux
        # /home/ both trip the generalized, launcher-independent path check.
        self._write(tmp_path / "pkg" / "m.py",
                    "A = '/Users/casey/repo'\nB = '/home/dana/cabinet'\n")
        v = scan_tree(tmp_path, files_allowlist={}, lines_allowlist={})
        reasons = " ".join(r[2] for r in v)
        assert len(v) == 2
        assert "/Users/casey" in reasons and "/home/dana" in reasons

    def test_flags_org_domain_literals(self, tmp_path):
        # An employer/lane domain literal. "testburg.example" trips the org-domain
        # check AND the any-case captain-token check (it contains the bare
        # "testburg" token) — two checks on one literal, like /Users/testburg
        # trips home-path + captain-token above.
        self._write(tmp_path / "pkg" / "m.py",
                    "EMAIL = 'x@testburg.example'\n")
        v = scan_tree(tmp_path, files_allowlist={}, lines_allowlist={})
        reasons = " ".join(r[2] for r in v)
        assert len(v) == 2
        assert "org-domain" in reasons and "testburg.example" in reasons

    def test_flags_product_token_literals(self, tmp_path):
        # Bare token AND its hyphenated -ceo / dotted domain forms must trip the
        # check (word-bounding, not whole-token matching — "-"/"." are non-word
        # chars, so a boundary exists on either side of the bare token).
        self._write(tmp_path / "pkg" / "m.py",
                    "OFFICER = 'bakery-ceo'\nLANE = \"Bakery\"\nURL = 'bakery.io'\n")
        v = scan_tree(tmp_path, files_allowlist={}, lines_allowlist={})
        reasons = " ".join(r[2] for r in v)
        assert len(v) == 3
        assert "product/lane token" in reasons
        assert "'bakery'" in reasons and "'Bakery'" in reasons

    def test_flags_adapter_tokens(self, tmp_path):
        # Case-insensitive, word-bounded — the placeholder personal-source-adapter
        # tokens (a capitalized runtime default, a lowercase docstring mention, a
        # capitalized vault reference). framework/ may only ever call it "the
        # personal-source adapter" / "Flavor-A" (the concrete adapter lives in
        # instance/flavor-a/, outside this scan tree).
        self._write(tmp_path / "pkg" / "m.py",
                    "LIST = 'ExampleSource Work'\n"
                    "# reads from examplesource pipes\n"
                    "VAULT = 'ExampleVault notes'\n")
        v = scan_tree(tmp_path, files_allowlist={}, lines_allowlist={})
        reasons = " ".join(r[2] for r in v)
        assert len(v) == 3
        assert "adapter-agnostic" in reasons
        assert ("ExampleSource" in reasons and "examplesource" in reasons
                and "ExampleVault" in reasons)

    def test_flags_captain_token_any_case(self, tmp_path):
        # The any-case bare-captain check (distinct from the case-sensitive
        # display-name _CAPTAIN above) catches an ALL-CAPS convention tag and a
        # lowercase prose mention — neither of which the case-sensitive check
        # alone would catch.
        self._write(tmp_path / "pkg" / "m.py",
                    "# TESTBURG-NOTE (2026-07-04): keep this gate narrow\n"
                    "# _CAP.lower() == 'testburg' here, so the stop set tracks it\n")
        v = scan_tree(tmp_path, files_allowlist={}, lines_allowlist={})
        assert len(v) == 2
        assert all(r[1] in (1, 2) for r in v)
        reasons = " ".join(r[2] for r in v)
        assert "any case" in reasons and "launcher-agnostic" in reasons

    def test_ignores_adapter_and_captain_lookalikes(self, tmp_path):
        # False-positive guards for the token checks: a longer identifier that
        # merely CONTAINS a token as a substring (no word boundary) must stay
        # green, and the UNDERSCORE compounds (testburg_model / copy_to_testburg /
        # me_signal — the SAME set _BRAIN_ARTIFACTS_KEPT documents) must ALSO stay
        # green under the any-case captain-token check — underscore is a `\w` char
        # (no boundary either side).
        self._write(tmp_path / "pkg" / "m.py",
                    "name = 'myexamplesourceclient'\n"   # substring, no boundary
                    "x = 'examplevaultish'\n"            # substring, no boundary
                    "testburg_model = 1\n"
                    "testburg_copy = 2\n"
                    "def copy_to_testburg(): pass\n"
                    "y = 'me_signal'\n")
        assert scan_tree(tmp_path, files_allowlist={}, lines_allowlist={}) == []

    def test_ignores_non_launcher_lookalikes(self, tmp_path):
        # Critical false-positive guard for a ratchet: a common word merely
        # CONTAINING a token as a substring (no boundary), '/usr/local' (not a
        # home path), a lowercase captain compound, and a bare English word must
        # ALL stay green.
        self._write(tmp_path / "pkg" / "m.py",
                    "bakeryboard_other = 1\n"           # NOT bakery-* — no boundary (bakery + 'b')
                    "P = '/usr/local/bin'\n"            # not a home path
                    "testburg_model = 1\n"              # lowercase compound (underscore)
                    "for step in range(10): pass\n")    # bare English word, no token
        assert scan_tree(tmp_path, files_allowlist={}, lines_allowlist={}) == []

    def test_ignores_lowercase_brain_artifacts(self, tmp_path):
        # testburg_model / copy_to_testburg are lowercase compounds — the
        # display-name ratchet must NOT match them (and no other check trips).
        self._write(tmp_path / "pkg" / "m.py",
                    "testburg_model = 1\ndef copy_to_testburg(): pass\nx = 'me_signal'\n")
        assert scan_tree(tmp_path, files_allowlist={}, lines_allowlist={}) == []

    def test_skips_tests_dirs_and_test_files(self, tmp_path):
        self._write(tmp_path / "pkg" / "tests" / "test_x.py", "Testburg\n")
        self._write(tmp_path / "pkg" / "test_top.py", "Testburg\n")
        self._write(tmp_path / "pkg" / "__pycache__" / "c.py", "Testburg\n")
        assert scan_tree(tmp_path, files_allowlist={}, lines_allowlist={}) == []

    def test_whole_file_allowlist_skips(self, tmp_path):
        self._write(tmp_path / "pkg" / "m.py", "Testburg here\n")
        assert scan_tree(tmp_path, files_allowlist={"pkg/m.py": "ok"},
                         lines_allowlist={}) == []

    def test_line_needle_exempts_only_that_line(self, tmp_path):
        # Line 2 trips BOTH the case-sensitive _CAPTAIN check and the any-case
        # _CAPTAIN_TOKEN check on the same "Testburg" literal — two entries, both
        # on line 2 — while line 1 stays fully exempt (the needle skips it before
        # either check runs).
        self._write(tmp_path / "pkg" / "m.py",
                    "Testburg — the anti-pattern doc\nTestburg elsewhere\n")
        v = scan_tree(tmp_path, files_allowlist={},
                      lines_allowlist={"pkg/m.py": ("anti-pattern doc",)})
        assert [r[1] for r in v] == [2, 2]  # only line 2, twice (two checks)

    def test_home_path_needle_exempts_the_doc_citation(self, tmp_path):
        # A line-scoped needle exempts the docstring line that CITES an
        # anti-pattern home path, while a bare captain literal on another line is
        # still caught (surgical, not whole-file). len==2, not 1: the any-case
        # _CAPTAIN_TOKEN check ALSO fires on line 2 (leftmost match "TESTBURG", the
        # variable name) alongside the case-sensitive _CAPTAIN hit on the same line
        # ("'Testburg'", the value) — see test_flags_bare_captain_and_home_path.
        self._write(tmp_path / "pkg" / "m.py",
                    "# see /Users/example/x for the anti-pattern\nTESTBURG = 'Testburg'\n")
        v = scan_tree(tmp_path, files_allowlist={},
                      lines_allowlist={"pkg/m.py": ("/Users/example/x",)})
        assert len(v) == 2 and all(r[1] == 2 for r in v)
        reasons = " ".join(r[2] for r in v)
        assert "'Testburg'" in reasons and "TESTBURG" in reasons

    def test_symlink_escape_is_refused(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.py").write_text("Testburg\n", encoding="utf-8")
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
