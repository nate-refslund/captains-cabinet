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

TWO ARMS, one home. **Arm 1** (this docstring, the checks below) is the
launcher/product IDENTITY ratchet described here. **Arm 2** — the SPECIFICS
ratchet — is the second half of the same promise: the framework is the seed for
ANY captain, in ANY industry, with ANY tool, so no third-party VENDOR, SERVICE
or PRODUCT may enter ``framework/`` unrecorded either. Arm 1 is green over a
framework that hardcodes a dozen vendors, because its live patterns are the
launcher's own identity and a synthetic demo one; Arm 2 derives its vocabulary
FROM THE TREE (a self-join on the hosts the repository itself names) rather
than from any list. Its doctrine, its scan set, its one hand-maintained
exclusion and — read this before treating green as coverage — the class of
specific it CANNOT see are all documented at the ``ARM 2`` banner below.

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

import hashlib
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




# ===========================================================================
# ARM 2 — THE SPECIFICS RATCHET  (added 2026-07-28)
# ===========================================================================
#
# WHY A SECOND ARM. Arm 1 above is an IDENTITY ratchet: it keeps framework/
# clean of the LAUNCHER's own display name, home path, org domain, product
# slug and personal-source adapter. Exactly one of its live checks has
# launcher-independent teeth (the absolute home path); the rest are SYNTHETIC
# demo tokens (Testburg / bakery / *.example / examplesource), chosen so the
# shipped tree names no real person. That design is right for what it guards
# and it is why Arm 1 runs GREEN over a framework/ that hardcodes a Sentry
# REST base, a Monday GraphQL client, a Telegram control plane, a Redis store
# and a Vercel deploy enum: none of those literals is the demo identity.
#
# Arm 2 guards the OTHER half of the same promise. The framework is the seed
# for ANY captain, in ANY industry, using ANY tool — so it may know that
# things exist, have times, have actors and have volume, and it may NOT know
# that any particular vendor, service or product exists. A partly-agnostic
# framework is worse than an openly specific one: it reads as portable and is
# not, and the stranger inherits assumptions nobody declared.
#
# THE TWO RULES, both DERIVED FROM THE TREE — never a list of vendor names.
# A blocklist of vendors would be the very specific it is meant to prevent,
# one level up, and this program has deleted four hand-maintained lists in a
# week.
#
#   EXTERNAL_HOST  — a `https?://<host>` literal in framework/ whose host is
#       not reserved-for-documentation. It is a SHAPE: every third-party
#       endpoint matches it and the rule names none of them.
#
#   VENDOR_TOKEN   — a word-bounded occurrence, in framework/, of a vendor
#       label DERIVED by self-join: the registrable label of every non-reserved
#       host the repository itself mentions OUTSIDE framework/'s own scan set.
#       The tree teaches the gate its own vendor vocabulary; the gate then
#       forbids that vocabulary inside the universal layer. The vocabulary
#       grows on its own as the instance/cabinet layers name more tools, so
#       cleaning framework/ never blinds the rule (the seed does not live in
#       the thing being cleaned).
#
# TWO CLASSES OF URL, ONE DERIVED DISTINCTION. A URL in *namespace position*
# (`"$schema"`, `"$id"`, `"$ref"`, `xmlns`, a `!DOCTYPE ... PUBLIC` line) is a
# FORMAT IDENTIFIER, not a service call — a JSON-Schema draft URI (scheme
# omitted here on purpose: this file is itself a seed file, and writing a live
# URL in it would teach the gate a label out of thin air) binds nothing at
# runtime. Namespace-position URLs are skipped by
# EXTERNAL_HOST and their labels are subtracted from the vendor vocabulary.
# That single distinction is what keeps the repo's own `$id` namespace, the
# JSON-Schema meta-schema and a plist DOCTYPE out of the rules without naming
# any of them. (Cost, stated plainly: a vendor whose host appears ANYWHERE in
# namespace position is subtracted from the vocabulary — see WHAT THIS CANNOT
# SEE, item 6.)
#
# THE BASELINE IS A DEBT LEDGER, NOT A REGISTRY. `_SPECIFICS_BASELINE` (the
# tracked sidecar file) records one line per known finding as
# ``path:RULE:digest`` — a blake2s digest of the literal, never the literal.
# That is deliberate: a baseline that spelled the nouns would BE the
# hand-maintained vendor list this gate exists to prevent, and would read as
# sanction ("# monday - by design"). The digest keeps it a debt ledger. The
# offending literal is still shown, in full, in the failure message and in
# `--report`, where a human needs it.
#
# RATCHET SEMANTICS. Green iff the live finding set is a SUBSET of the
# baseline. A finding key is (path, rule, digest), so:
#   * a NEW file under framework/ carrying any vendor literal  -> RED
#   * a NEW vendor in an ALREADY-baselined file                -> RED
#   * more uses of a vendor a file already carries             -> green
# The last one is deliberate and is the whole false-positive story: ordinary
# work inside a module that already speaks to a vendor does not fire, while
# widening the framework's vendor surface always does. Line numbers are NOT
# recorded, mirroring check-layer-separation.sh, so moving code never churns
# the baseline.
#
# The baseline may only SHRINK: its size is capped by _SPECIFICS_BASELINE_MAX,
# so admitting a new specific requires raising that number in the same commit
# — visibly, in a diff, with a reviewer looking at it. There is no allowance
# and no per-entry exemption to hide behind.
#
# WHAT THIS CANNOT SEE — read this before treating green as coverage.
# The subtlest specifics carry no vendor name at all, and no mechanical check
# in this file reaches them:
#   1. A CLOSED ENUM whose members are one industry's verbs. 30 action types
#      built around deploys and pushes make every act in a law firm, a clinic
#      or a building site classify as `ambiguous` — permanently propose-only,
#      with the graduation ladder unreachable. No literal is wrong; the
#      TAXONOMY is. Only a direction gate catches that.
#   2. A CAPABILITY or ROLE NAME. A resolver is agnostic; a resolver called
#      `deploys_code_officer()` still asks a question about software. The seam
#      is clean and the VOCABULARY crossing it is not.
#   3. A UNIT baked into a schema key (`max_eur_per_day` beside
#      `daily_per_officer_usd`) — the framework disagreeing with itself on
#      currency is the tell that neither was decided. A key-shape rule needs
#      ISO-4217, i.e. a list, so it is not attempted here.
#   4. A CHARACTER, CADENCE or THRESHOLD encoding one operator's day —
#      quiet hours 21:00-07:00, a fortnight cooldown, seven rendered
#      decisions. Each is documented and reasonable; together they calibrate
#      the cabinet to somebody else's tempo, and nothing prompts a stranger
#      to look.
#   5. A VENDOR NAMED ONLY IN framework/ AND NOWHERE ELSE seeds only itself;
#      it is caught (the seed includes framework/'s own non-scanned files and
#      its scan-set URLs), but a vendor mentioned by TOKEN ONLY, with no URL
#      anywhere in the tree, is invisible to the self-join.
#   6. A VENDOR LAUNDERED THROUGH NAMESPACE POSITION. One `"$schema"` line
#      carrying a vendor host subtracts that label from the vocabulary.
#   7. Anything in `cabinet/scripts/**`, `cabinet/dashboard/**`, `packs/**`
#      or `presets/**`. This arm scans framework/ only — those layers are
#      allowed specifics, and their boundary is defended by other gates.
# Green here means "framework/ grew no NEW named third party". It does not
# mean "framework/ is agnostic".


# ---------------------------------------------------------------------------
# Arm 2 — shapes, reserved sets, and the ONE hand-maintained exclusion
# ---------------------------------------------------------------------------
_SPECIFICS_BASELINE_PATH = Path(__file__).resolve().parent / "framework-specifics-baseline.txt"

# The baseline may only SHRINK. Admitting a specific means raising this number
# in the same commit — visibly, in the diff, with a reviewer on it.
_SPECIFICS_BASELINE_MAX = 318

_URL_RX = re.compile(r"https?://([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)")

# A URL in NAMESPACE position is a format identifier, not a service call.
_NS_CONTEXT_RX = re.compile(r'"\$(?:id|schema|ref|comment)"|xmlns|!DOCTYPE|\bPUBLIC\b')

# RFC 2606 / RFC 6761 reserved-for-documentation + loopback + mDNS. A host here
# names nobody, so it is neither a finding nor a source of vocabulary.
_RESERVED_HOSTS = frozenset({"localhost", "example.com", "example.org", "example.net"})
_RESERVED_HOST_SUFFIXES = (".example", ".invalid", ".test", ".localhost", ".local",
                           ".example.com", ".example.org", ".example.net")
_NUMERIC_HOST_RX = re.compile(r"[0-9.]+\Z")

# Dated design snapshots under framework/docs/ are archived OUT of the egg by
# cabinet/scripts/egg-export.sh (transform framework-docs-archive, rule R162):
# they are the launching deployment's own history and never reach a stranger,
# so policing them is churn with no stranger benefit. The predicate mirrors the
# exporter's, as a DATE SHAPE rather than the exporter's hardcoded year.
_DATED_DESIGN_DOC_RX = re.compile(r"-\d{4}-\d{2}-\d{2}\.md\Z")

_MIN_LABEL_LEN = 4  # below this a host label is URL grammar (api, www, io, x), not a name

# Directories the seed walk never descends into. Build output and dependency
# trees are not the repository's own vocabulary, and `instance/` is the
# PER-DEPLOYMENT layer: a stranger's own vendors live there legitimately and
# must not bind the framework gate (it would go red on their own supplier's
# name). Determinism matters — this walk must produce the same vocabulary in
# CI, in a hatched cabinet and in a dirty dev checkout.
_SEED_SKIP_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".next", "dist", "build", "instance",
})
_SEED_MAX_BYTES = 512 * 1024  # lockfiles and bundles carry no doctrine

# THE ONE HAND-MAINTAINED ELEMENT IN ARM 2, stated plainly because the standard
# says to. These are vendor labels the self-join DERIVES correctly and that the
# TOKEN rule cannot use, because the label is also an ordinary English word in
# this repository's own prose. Excluding a label narrows enforcement to
# EXTERNAL_HOST (its URL is still forbidden); it does not bless the vendor.
# The set may only SHRINK (_COLLISION_TOKENS_MAX) and every entry carries the
# measurement that justifies it. It is an EXCLUSION list, so growing it weakens
# the gate — the opposite pressure from a blocklist, which is why it is capped.
_COLLISION_TOKENS: Dict[str, str] = {
    "make": "English verb and identifier prefix — 84 lines across 48 framework "
            "files (make_resolve_step, 'build|make|create'). Collides with make.com.",
    "linear": "English adjective — 4 of its 7 framework files are 'a single "
              "linear scan' / 'one linear chain' / 'pre-compiled and linear'. "
              "Collides with linear.app.",
    "acme": "the universal documentation placeholder company (acme.example, "
            "'Suggestion - acme:'), not a vendor this framework binds to. "
            "Collides with acme.com.",
    "evil": "English adjective carrying the threat-model prose ('/tmp/evil', "
            "'/dev/tcp/evil.example/25'). Collides with evil.com.",
}
_COLLISION_TOKENS_MAX = 4  # may only be LOWERED


SpecificsFinding = Tuple[str, str, str, int]  # (path, rule, literal, line_no)


def _host_is_reserved(host: str) -> bool:
    """True for a host that names nobody: RFC 2606 / 6761 documentation and
    special-use names, loopback/bare IPs, and a bare label (a placeholder or an
    interpolated variable, not a public host)."""
    h = host.lower().rstrip(".")
    if h in _RESERVED_HOSTS:
        return True
    if h.endswith(_RESERVED_HOST_SUFFIXES):
        return True
    if _NUMERIC_HOST_RX.match(h):
        return True
    return "." not in h


def _registrable_label(host: str) -> Optional[str]:
    """The label that names the operator of a host: the second-to-last label
    (`api.monday.com` -> `monday`, `sentry.io` -> `sentry`). Deliberately needs
    NO public-suffix list — over-long results on a multi-part TLD would simply
    be a label nobody writes in source, and under-matching costs a finding, not
    a false one."""
    parts = host.lower().rstrip(".").split(".")
    return parts[-2] if len(parts) >= 2 else None


def _read_text_file(path: Path) -> Optional[str]:
    """Read-only, total: returns None for unreadable or binary content (never
    raises, never imports, never executes)."""
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw[:8192]:
        return None
    return raw.decode("utf-8", "replace")


def iter_seed_files(root: Path) -> Iterator[Path]:
    """Every text file the vocabulary may be derived from (see _SEED_SKIP_DIRS)."""
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = sorted(d for d in dirnames if d not in _SEED_SKIP_DIRS)
        for name in sorted(filenames):
            p = Path(dirpath) / name
            try:
                if p.is_symlink() or p.stat().st_size > _SEED_MAX_BYTES:
                    continue
            except OSError:
                continue
            yield p


def derive_vendor_vocabulary(root) -> "frozenset[str]":
    """THE SELF-JOIN. Read every seed file; every non-reserved host in SERVICE
    position contributes its registrable label to the vendor vocabulary, and
    every host in NAMESPACE position subtracts its label (a format identifier
    binds nothing). Word-collision labels are removed last. Nothing here is a
    list of vendors: the tree teaches the gate its own vocabulary."""
    service = set()  # type: set
    namespace = set()  # type: set
    for p in iter_seed_files(Path(root)):
        txt = _read_text_file(p)
        if txt is None:
            continue
        for line in txt.splitlines():
            if "://" not in line:
                continue
            ns = _NS_CONTEXT_RX.search(line) is not None
            for m in _URL_RX.finditer(line):
                host = m.group(1)
                if _host_is_reserved(host):
                    continue
                lab = _registrable_label(host)
                if not lab or len(lab) < _MIN_LABEL_LEN:
                    continue
                (namespace if ns else service).add(lab)
    return frozenset(service - namespace - set(_COLLISION_TOKENS))


def iter_specifics_files(root: Path) -> Iterator[Path]:
    """The scan set: every text file under the tree EXCEPT tests (same skips as
    Arm 1, so the two arms police the same surface) and the dated design
    snapshots the egg export archives out."""
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in ("__pycache__", "tests") and d not in _SEED_SKIP_DIRS)
        for name in sorted(filenames):
            if name.startswith("test_") or name.endswith("_test.py"):
                continue
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            if rel.startswith("docs/") and _DATED_DESIGN_DOC_RX.search(name):
                continue
            yield p


def _strip_reserved_url_text(line: str) -> str:
    """Blank out documentation-host URLs before token matching, so a reserved
    host never contributes a token hit (`xtest.acme.example` is not a vendor)."""
    out, last = [], 0
    for m in _URL_RX.finditer(line):
        if _host_is_reserved(m.group(1)):
            out.append(line[last:m.start()])
            last = m.end()
    out.append(line[last:])
    return "".join(out)


def _vocabulary_regex(vocabulary) -> "Optional[re.Pattern[str]]":
    if not vocabulary:
        return None
    alts = "|".join(re.escape(v) for v in sorted(vocabulary, key=lambda s: (-len(s), s)))
    return re.compile(r"(?<![A-Za-z0-9])(" + alts + r")(?![A-Za-z0-9])", re.IGNORECASE)


def scan_specifics(root, vocabulary=None, rel_to=None) -> List[SpecificsFinding]:
    """Read-only scan of ``root`` for third-party specifics. Returns
    (display_path, RULE, literal, line_no), sorted. Symlink escapes are
    refused, never followed (realpath containment, mirroring Arm 1)."""
    root = Path(root)
    base = Path(rel_to) if rel_to is not None else root
    if vocabulary is None:
        vocabulary = derive_vendor_vocabulary(base)
    vrx = _vocabulary_regex(vocabulary)
    real_root = os.path.realpath(str(root))
    found = []  # type: List[SpecificsFinding]
    for p in iter_specifics_files(root):
        try:
            display = p.relative_to(base).as_posix()
        except ValueError:
            display = p.as_posix()
        rp = os.path.realpath(str(p))
        if rp != real_root and not rp.startswith(real_root + os.sep):
            found.append((display, "SYMLINK_ESCAPE", display, 0))
            continue
        txt = _read_text_file(p)
        if txt is None:
            continue
        for i, line in enumerate(txt.splitlines(), 1):
            ns = _NS_CONTEXT_RX.search(line) is not None
            if not ns and "://" in line:
                for m in _URL_RX.finditer(line):
                    host = m.group(1).lower()
                    if not _host_is_reserved(host):
                        found.append((display, "EXTERNAL_HOST", host, i))
            if vrx is not None and not ns:
                seen = set()
                for m in vrx.finditer(_strip_reserved_url_text(line)):
                    tok = m.group(1).lower()
                    if tok not in seen:
                        seen.add(tok)
                        found.append((display, "VENDOR_TOKEN", tok, i))
    return sorted(found)


def specifics_key(finding: SpecificsFinding) -> str:
    """The baseline key: ``path:RULE:digest``. The digest — never the literal —
    is what keeps the baseline a debt ledger instead of a vendor registry."""
    path, rule, literal, _line = finding
    return "%s:%s:%s" % (path, rule, hashlib.blake2s(
        literal.encode("utf-8"), digest_size=4).hexdigest())


def load_specifics_baseline(path=None) -> "frozenset[str]":
    p = Path(path) if path is not None else _SPECIFICS_BASELINE_PATH
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return frozenset()
    return frozenset(ln.strip() for ln in text.splitlines()
                     if ln.strip() and not ln.startswith("#"))


_SPECIFICS_BASELINE_HEADER = (
    "# framework-specifics-baseline.txt — the DEBT LEDGER for Arm 2 of\n"
    "# framework/tests/test_no_launcher_hardcode.py (the specifics ratchet).\n"
    "#\n"
    "# One line per known third-party specific already inside framework/, as\n"
    "#     <path>:<RULE>:<blake2s-4 digest of the literal>\n"
    "# The digest is deliberate. Spelling the vendor here would make THIS FILE\n"
    "# the hand-maintained list of vendors the gate exists to prevent, and each\n"
    "# line would read as sanction. It is debt, not design. Run\n"
    "#     python3 framework/tests/test_no_launcher_hardcode.py --report\n"
    "# to see every entry with its literal, path and line.\n"
    "#\n"
    "# Machine-generated: `--update-baseline`. It may only SHRINK — the size cap\n"
    "# _SPECIFICS_BASELINE_MAX must be raised, in the same commit, to admit one.\n"
)


def render_specifics_baseline(keys) -> str:
    return _SPECIFICS_BASELINE_HEADER + "".join(k + "\n" for k in sorted(keys))




_SPECIFICS_HINT = (
    "framework/ may not name a third-party vendor, service or product — the "
    "framework is the seed for ANY captain, in ANY industry, with ANY tool. "
    "Route the specific to the instance/ layer, reach it through an adapter "
    "seam (framework.channels.contract / framework.sources.get_source), or "
    "read it from config. If the coupling is genuinely unavoidable TODAY, it "
    "is DEBT, not design: run\n"
    "    python3 framework/tests/test_no_launcher_hardcode.py --update-baseline\n"
    "and RAISE _SPECIFICS_BASELINE_MAX in the same commit so the admission is "
    "visible in the diff")


class TestSpecificsRatchet:
    """Arm 2 over the live tree."""

    def test_framework_carries_no_new_specific(self):
        """THE RATCHET: the live finding set must be a SUBSET of the tracked
        debt baseline. A new file carrying a vendor literal, or a NEW vendor in
        an already-known file, is a CI failure — not a review note."""
        vocabulary = derive_vendor_vocabulary(_REPO_ROOT)
        findings = scan_specifics(_REPO_ROOT / "framework", vocabulary=vocabulary,
                                  rel_to=_REPO_ROOT)
        baseline = load_specifics_baseline()
        new = [f for f in findings if specifics_key(f) not in baseline]
        assert new == [], "%s\nNEW specifics: %s" % (
            _SPECIFICS_HINT,
            ["%s:%d (%s %s)" % (f[0], f[3], f[1], f[2]) for f in new[:40]])

    def test_baseline_only_shrinks(self):
        """Intent lock: the debt ledger may only SHRINK. Admitting a specific
        means raising _SPECIFICS_BASELINE_MAX in the same commit — visibly, in
        the diff. There is no per-entry allowance to hide an admission in."""
        baseline = load_specifics_baseline()
        assert len(baseline) <= _SPECIFICS_BASELINE_MAX, (
            "specifics baseline grew (%d > %d) — %s"
            % (len(baseline), _SPECIFICS_BASELINE_MAX, _SPECIFICS_HINT))

    def test_baseline_is_a_debt_ledger_not_a_vendor_registry(self):
        """The forcing function on the baseline's SHAPE: every line must end in
        an opaque digest. The moment someone writes the noun there ("# monday —
        by design") the file has become the hand-maintained vendor list this
        gate exists to prevent, one level up. This test makes that unlandable."""
        bad = [ln for ln in load_specifics_baseline()
               if not re.match(r"\A[^:]+:[A-Z_]+:[0-9a-f]{8}\Z", ln)]
        assert bad == [], (
            "baseline lines must be '<path>:<RULE>:<digest>' — a spelled-out "
            "vendor noun turns the debt ledger into a registry: %s" % bad[:10])

    def test_collision_exclusions_only_shrink_and_are_justified(self):
        """The ONE hand-maintained element in Arm 2 is capped and documented.
        Growing it WEAKENS the gate (it is an exclusion list), so it may only
        shrink, and every entry must carry the measurement that justifies it."""
        assert len(_COLLISION_TOKENS) <= _COLLISION_TOKENS_MAX, (
            "word-collision exclusions grew (%d > %d) — narrow the token or fix "
            "the code; do not widen the exclusion"
            % (len(_COLLISION_TOKENS), _COLLISION_TOKENS_MAX))
        thin = [k for k, why in _COLLISION_TOKENS.items() if len(why) < 40]
        assert thin == [], "unjustified collision exclusions: %s" % thin

    def test_the_live_vocabulary_is_derived_and_non_empty(self):
        """Non-vacuity of the SEED: a vocabulary that came back empty would make
        VENDOR_TOKEN a no-op while still reporting green — the exact
        sensor-tests-nothing failure this program keeps finding. It is derived
        from the tree, so it is asserted to be non-trivial, never listed."""
        vocabulary = derive_vendor_vocabulary(_REPO_ROOT)
        assert len(vocabulary) >= 10, (
            "the self-join derived only %d vendor labels — the seed walk is "
            "broken (skip-dirs? size cap?), and VENDOR_TOKEN is inert"
            % len(vocabulary))
        assert not (set(_COLLISION_TOKENS) & vocabulary)


class TestSpecificsEngine:
    """Hermetic proofs on own tmp trees — never the real baseline."""

    @staticmethod
    def _write(p: Path, body: str) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def _tree(self, tmp_path, seed: str = "", fw=None):
        """A miniature repo: a seed file OUTSIDE framework/ teaches the
        vocabulary, files under framework/ are what gets scanned."""
        self._write(tmp_path / "cabinet" / "notes.md", seed)
        for rel, body in (fw or {}).items():
            self._write(tmp_path / "framework" / rel, body)
        return derive_vendor_vocabulary(tmp_path)

    def test_vocabulary_is_derived_from_the_tree(self, tmp_path):
        v = self._tree(tmp_path, seed="see https://api.vendorx.io/v2 for the API\n")
        assert "vendorx" in v

    def test_flags_a_new_external_host(self, tmp_path):
        v = self._tree(tmp_path, fw={"m.py": "BASE = 'https://api.vendorx.io/v2'\n"})
        f = scan_specifics(tmp_path / "framework", vocabulary=v, rel_to=tmp_path)
        assert ("framework/m.py", "EXTERNAL_HOST", "api.vendorx.io", 1) in f

    def test_flags_a_derived_vendor_token(self, tmp_path):
        """The self-join with teeth: the URL lives OUTSIDE framework/, the bare
        NAME inside it, and the rule never spelled the vendor."""
        v = self._tree(tmp_path, seed="https://api.vendorx.io/v2\n",
                       fw={"m.py": "# push the card to VendorX when it lands\n"})
        f = scan_specifics(tmp_path / "framework", vocabulary=v, rel_to=tmp_path)
        assert ("framework/m.py", "VENDOR_TOKEN", "vendorx", 1) in f

    def test_ignores_reserved_documentation_hosts(self, tmp_path):
        """RFC 2606 / 6761 hosts name nobody: not a finding, and not vocabulary."""
        v = self._tree(tmp_path, seed="https://api.example.com/v2 https://x.invalid/\n",
                       fw={"m.py": "A = 'https://api.example.com/v2'\n"
                                   "B = 'https://box.acme.example/'\n"
                                   "C = 'http://localhost:8080/'\n"
                                   "D = 'http://127.0.0.1:6379'\n"})
        assert scan_specifics(tmp_path / "framework", vocabulary=v, rel_to=tmp_path) == []

    def test_ignores_namespace_position_urls(self, tmp_path):
        """A $schema / $id / DOCTYPE URI is a FORMAT identifier, not a service."""
        v = self._tree(tmp_path, fw={
            "s.json": '{\n  "$schema": "https://spec.vendorx.io/draft/2020-12/schema",\n'
                      '  "$id": "https://own.vendorx.io/schemas/thing"\n}\n'})
        assert scan_specifics(tmp_path / "framework", vocabulary=v, rel_to=tmp_path) == []

    def test_namespace_position_subtracts_from_the_vocabulary(self, tmp_path):
        """Stated cost, pinned: a label used anywhere as a format identifier is
        removed from the vendor vocabulary (see 'WHAT THIS CANNOT SEE', 6)."""
        v = self._tree(tmp_path,
                       seed='"$schema": "https://spec.vendorx.io/d"\nhttps://api.vendorx.io/v2\n')
        assert "vendorx" not in v

    def test_instance_layer_never_seeds_the_vocabulary(self, tmp_path):
        """A stranger's OWN suppliers live in instance/ legitimately; letting
        them bind the framework gate would go red on their supplier's name."""
        self._write(tmp_path / "instance" / "config" / "x.yml",
                    "url: https://api.vendorx.io/v2\n")
        assert "vendorx" not in derive_vendor_vocabulary(tmp_path)

    def test_skips_tests_and_dated_design_snapshots(self, tmp_path):
        v = self._tree(tmp_path, seed="https://api.vendorx.io/v2\n", fw={
            "tests/test_x.py": "VendorX\n",
            "test_top.py": "VendorX\n",
            "pkg/thing_test.py": "VendorX\n",
            "__pycache__/c.py": "VendorX\n",
            "docs/design-2026-06-19.md": "VendorX everywhere\n",
        })
        assert scan_specifics(tmp_path / "framework", vocabulary=v, rel_to=tmp_path) == []

    def test_living_docs_are_still_scanned(self, tmp_path):
        """Only the DATED snapshots the egg export archives out are skipped —
        the undated living contract docs still ship to a stranger."""
        v = self._tree(tmp_path, seed="https://api.vendorx.io/v2\n",
                       fw={"docs/work-model.md": "sync to VendorX\n"})
        f = scan_specifics(tmp_path / "framework", vocabulary=v, rel_to=tmp_path)
        assert [(x[0], x[1]) for x in f] == [("framework/docs/work-model.md", "VENDOR_TOKEN")]

    def test_non_python_files_are_scanned(self, tmp_path):
        """Arm 1 is .py-only; the specifics that bind hardest live in YAML and
        Markdown (a safety policy's deploy patterns, a constitution's tracker
        list), so Arm 2 walks every text file."""
        v = self._tree(tmp_path, seed="https://api.vendorx.io/v2\n", fw={
            "policies/base-safety.yml": "patterns: ['vendorx deploy']\n",
            "constitution-base.md": "External trackers (VendorX, ...)\n"})
        got = sorted({x[0] for x in scan_specifics(
            tmp_path / "framework", vocabulary=v, rel_to=tmp_path)})
        assert got == ["framework/constitution-base.md",
                       "framework/policies/base-safety.yml"]

    def test_word_collision_tokens_never_fire(self, tmp_path):
        """The measured false-positive class: an English word that is also a
        vendor label. Excluded from the TOKEN rule; its URL still fires."""
        for tok in _COLLISION_TOKENS:
            v = self._tree(tmp_path, seed="https://api.%s.io/v2\n" % tok,
                           fw={"m.py": "# an ordinary sentence using %s here\n" % tok})
            f = scan_specifics(tmp_path / "framework", vocabulary=v, rel_to=tmp_path)
            assert [x for x in f if x[1] == "VENDOR_TOKEN"] == [], tok

    def test_binary_and_oversized_seed_files_are_skipped(self, tmp_path):
        self._write(tmp_path / "cabinet" / "notes.md", "")
        (tmp_path / "cabinet" / "blob.bin").write_bytes(
            b"https://api.vendorx.io/v2\x00\x01\x02")
        assert "vendorx" not in derive_vendor_vocabulary(tmp_path)

    def test_symlink_escape_is_refused(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.py").write_text("x = 1\n", encoding="utf-8")
        root = tmp_path / "framework"
        root.mkdir()
        try:
            (root / "link.py").symlink_to(outside / "secret.py")
        except (OSError, NotImplementedError):  # pragma: no cover — FS w/o symlinks
            if pytest is not None:
                pytest.skip("symlinks unsupported on this filesystem")
            return
        f = scan_specifics(root, vocabulary=frozenset(), rel_to=tmp_path)
        assert any(x[1] == "SYMLINK_ESCAPE" for x in f)


class TestSpecificsRatchetIsNonVacuous:
    """The property that decides whether this gate is worth having: it must be
    SEEN to fail on a new specific, in both rules, against the REAL vocabulary
    and the REAL baseline. A gate never seen to fail proves nothing."""

    def test_a_new_specific_in_a_new_framework_file_is_red(self, tmp_path):
        vocabulary = derive_vendor_vocabulary(_REPO_ROOT)
        baseline = load_specifics_baseline()
        # A vendor the TREE itself names — resolved at runtime, so this test
        # spells no vendor either.
        token = sorted(vocabulary)[0]
        d = tmp_path / "framework" / "acting"
        d.mkdir(parents=True)
        (d / "brand_new_module.py").write_text(
            "BASE = 'https://api.brand-new-third-party.systems/v1'\n"
            "# also mentions %s by name\n" % token, encoding="utf-8")
        f = scan_specifics(tmp_path / "framework", vocabulary=vocabulary, rel_to=tmp_path)
        rules = {x[1] for x in f}
        assert rules == {"EXTERNAL_HOST", "VENDOR_TOKEN"}, f
        assert all(specifics_key(x) not in baseline for x in f), (
            "the live baseline already covers a path that does not exist — the "
            "ratchet would pass a planted specific")

    def test_a_new_vendor_inside_an_already_baselined_file_is_red(self, tmp_path):
        """The narrow case a presence-only baseline would miss: the file is
        already known debt, and a DIFFERENT vendor is added to it."""
        seed = "https://api.vendorx.io/1 https://api.vendory.io/1\n"
        (tmp_path / "cabinet").mkdir()
        (tmp_path / "cabinet" / "n.md").write_text(seed, encoding="utf-8")
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / "m.py").write_text("# talks to vendorx\n", encoding="utf-8")
        v = derive_vendor_vocabulary(tmp_path)
        known = {specifics_key(x) for x in
                 scan_specifics(fw, vocabulary=v, rel_to=tmp_path)}
        (fw / "m.py").write_text("# talks to vendorx\n# and now vendory too\n",
                                 encoding="utf-8")
        after = scan_specifics(fw, vocabulary=v, rel_to=tmp_path)
        assert [x for x in after if specifics_key(x) not in known], after

    def test_more_uses_of_a_vendor_the_file_already_carries_stay_green(self, tmp_path):
        """The deliberate false-positive floor: ordinary work inside a module
        that already speaks to a vendor must NOT fire, or the gate is disabled
        within a week."""
        (tmp_path / "cabinet").mkdir()
        (tmp_path / "cabinet" / "n.md").write_text("https://api.vendorx.io/1\n",
                                                   encoding="utf-8")
        fw = tmp_path / "framework"
        fw.mkdir()
        (fw / "m.py").write_text("# talks to vendorx\n", encoding="utf-8")
        v = derive_vendor_vocabulary(tmp_path)
        known = {specifics_key(x) for x in
                 scan_specifics(fw, vocabulary=v, rel_to=tmp_path)}
        (fw / "m.py").write_text(
            "# talks to vendorx\n" * 4 + "def more_vendorx_calls(): pass\n",
            encoding="utf-8")
        after = scan_specifics(fw, vocabulary=v, rel_to=tmp_path)
        assert [x for x in after if specifics_key(x) not in known] == []


# CLI mode: `python3 framework/tests/test_no_launcher_hardcode.py` prints every
# offender and exits non-zero — usable under the system python without pytest.
if __name__ == "__main__":  # pragma: no cover
    import sys

    argv = sys.argv[1:]
    mode = argv[0] if argv else "--check"
    if mode not in ("--check", "--report", "--update-baseline"):
        print("usage: test_no_launcher_hardcode.py [--check|--report|--update-baseline]")
        sys.exit(2)

    offenders = scan_tree(_REPO_ROOT / "framework", rel_to=_REPO_ROOT)
    vocabulary = derive_vendor_vocabulary(_REPO_ROOT)
    specifics = scan_specifics(_REPO_ROOT / "framework", vocabulary=vocabulary,
                               rel_to=_REPO_ROOT)
    baseline = load_specifics_baseline()

    if mode == "--update-baseline":
        keys = {specifics_key(f) for f in specifics}
        _SPECIFICS_BASELINE_PATH.write_text(render_specifics_baseline(keys),
                                            encoding="utf-8")
        print("wrote %s: %d entries (cap %d) from a vocabulary of %d derived labels"
              % (_SPECIFICS_BASELINE_PATH.name, len(keys),
                 _SPECIFICS_BASELINE_MAX, len(vocabulary)))
        if len(keys) > _SPECIFICS_BASELINE_MAX:
            print("RAISE _SPECIFICS_BASELINE_MAX to %d in this same commit — the "
                  "admission has to be visible in the diff." % len(keys))
        sys.exit(0)

    for d, i, why in offenders:
        print("arm1 %s:%d  %s" % (d, i, why))
    new_specifics = [f for f in specifics if specifics_key(f) not in baseline]
    show = specifics if mode == "--report" else new_specifics
    for path, rule, literal, line in show:
        mark = " " if specifics_key((path, rule, literal, line)) in baseline else "*"
        print("arm2%s%s:%d  %s  %s" % (mark, path, line, rule, literal))
    if mode == "--report":
        print("arm2: %d findings, %d baselined, %d NEW (* above); vocabulary %d labels"
              % (len(specifics), len(specifics) - len(new_specifics),
                 len(new_specifics), len(vocabulary)))

    bad = bool(offenders) or bool(new_specifics)
    if offenders:
        print("FAIL (arm1): %s" % _HINT)
    if new_specifics:
        print("FAIL (arm2): %s" % _SPECIFICS_HINT)
    if not bad:
        print("OK: framework/ is launcher-agnostic and carries no NEW specific "
              "(%d known debt keys over %d occurrences, cap %d; vocabulary %d "
              "derived labels)"
              % (len({specifics_key(f) for f in specifics}), len(specifics),
                 _SPECIFICS_BASELINE_MAX, len(vocabulary)))
    sys.exit(1 if (bad and mode != "--report") else 0)
