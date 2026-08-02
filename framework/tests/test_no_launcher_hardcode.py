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

THREE ARMS, one home. **Arm 1** (this docstring, the checks below) is the
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

**Arm 3** — the PERSON ratchet — closes the hole Arm 1 left in ITSELF. Arm 1's
captain check pins ``Testburg``, a SYNTHETIC token, so it could only ever prove
the placeholder absent: fifteen occurrences of the launching deployment's REAL
operator name sat in framework/ with Arm 1 green over every one (measured
2026-07-30, the commit that added Arm 3 removed them). Arm 3 derives the
operator identity the way Arm 2 derives vendors — from what the repository and
its INSTANCE layer declare about themselves (the licence copyright holder, the
repository owner handle, the declared ``captain_name`` / onboarding identity)
— and forbids those tokens anywhere under framework/, tests and undated docs
included. Its doctrine, its three declaration surfaces, its capped exclusions
and the classes of person literal it CANNOT see are at the ``ARM 3`` banner.

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
import shutil
import subprocess
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
# recorded, mirroring check-layer-separation.sh, so moving code WITHIN a file
# never churns the baseline. Moving it BETWEEN files does, and RENAMING a
# baselined file goes RED on a diff that added no vendor at all — the key is
# (path, rule, digest), so the old key vanishes and a new one appears. That is
# the honest cost of a path-keyed ledger: the remedy is --update-baseline in
# the same commit, and because a rename trades one key for one key the CAP does
# not move, so the churn is visible but never buys headroom.
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
#   7. Anything outside framework/. The operating layer, the packs and the
#      presets are allowed their own suppliers and are not scanned here. Note
#      what that means for a stranger: those layers SHIP, so the egg a stranger
#      reads carries several times more named third parties than the surface
#      this arm polices. Widening the scan to them is a separate unit with a
#      separate baseline, not a tightening of this one.
#   8. framework/'s OWN TESTS. The scan set skips every `tests/` directory and
#      every `test_*` / `*_test` file (mirroring Arm 1, so both arms police the
#      same surface) — but unlike the dated design snapshots, the tests are NOT
#      archived out of the egg: ~280 of them ship, and they carry MORE vendor
#      mentions than the production surface next to them. Measured 2026-07-29:
#      two labels live in framework tests and in no scanned framework file, so
#      a NEW vendor arriving only through a fixture is invisible here. It is a
#      deliberate scope choice (a fixture is not a binding), not a claim that
#      the tests are clean.
#   9. A URL ON A NON-HTTP SCHEME. EXTERNAL_HOST matches `https?://` only, and
#      the self-join reads the same shape, so a service addressed over another
#      transport neither fires nor teaches the gate its label. A protocol-
#      relative `//host/path` is invisible for the same reason.
#  10. A LITERAL ASSEMBLED FROM FRAGMENTS. Both rules read source TEXT, so a
#      name that never appears whole on one line — split across concatenated
#      pieces, or interpolated from a variable defined elsewhere — is not seen.
#      The benign version of this is the pattern the gate WANTS (a host read
#      from config); the hostile version it simply cannot reach.
#  11. A LINE CARRYING A NAMESPACE MARKER. The namespace-position skip is a
#      LINE predicate, so any line that also contains one of those markers is
#      exempt from BOTH rules, whatever else is on it. In the tree today every
#      such line is a genuine schema/format identifier (verified 2026-07-29),
#      but the escape is wider than the case it exists for.
# Green here means "framework/ grew no NEW named third party". It does not
# mean "framework/ is agnostic".


# ---------------------------------------------------------------------------
# Arm 2 — shapes, reserved sets, and the ONE hand-maintained exclusion
# ---------------------------------------------------------------------------
_SPECIFICS_BASELINE_PATH = Path(__file__).resolve().parent / "framework-specifics-baseline.txt"

# The baseline may only SHRINK. Admitting a specific means raising this number
# in the same commit — visibly, in the diff, with a reviewer on it.
_SPECIFICS_BASELINE_MAX = 318

# THE SUBJECT FLOOR. A subset test passes trivially when the live finding set is
# EMPTY, so "no new specifics" and "the scan never ran" are the same green. The
# vocabulary already has a floor (an inert seed makes VENDOR_TOKEN a no-op); the
# SCAN had none, which left the ratchet's own degenerate end unguarded — a
# mis-rooted _REPO_ROOT, a renamed subject directory or a skip-list that
# swallowed the tree would all report OK. This floor is a WIRING check, not a
# debt measure: it is an order of magnitude below the live count (310 in the
# source tree, 311 in an egg cut, measured 2026-07-29) precisely so that PAYING
# the debt down to zero never trips it — the finding count is supposed to reach
# zero one day; the file count is not.
_SPECIFICS_SCAN_FLOOR = 100

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

# WHERE THE VOCABULARY MAY COME FROM. The seed walk takes every root-level file
# plus these top-level directories, and nothing else — an INCLUDE list of this
# repository's OWN layers, not an exclude list of things to dodge.
#
# The per-deployment layer is deliberately absent. A stranger's own suppliers
# live there legitimately, and letting them seed would make this gate go red on
# their own supplier's name appearing anywhere in framework/ prose. So is the
# preset layer, for the same reason at one remove. Omitting a root can only
# SHRINK the vocabulary, which can only shrink the finding set — it fails toward
# green, never toward a false red, so a root that does not exist in a hatched
# cabinet or an egg cut costs nothing.
#
# THE CORPUS IS THE SHIPPED TREE — the walk is filtered through tracked_paths()
# below, and this paragraph is the correction of a claim that shipped false.
#
# It used to read: "Determinism is the reason this is a walk over declared roots
# rather than a tracked-file listing: it must produce the same vocabulary in CI,
# in a hatched cabinet with no git metadata, and in a dirty dev checkout." The
# third clause was never true, and nothing tested it. A raw filesystem walk
# reads whatever is ON DISK, and a working checkout carries three classes of
# byte that no gate should ever be taught by, ALL of them absent from the
# `actions/checkout` tree that decides merges:
#
#   * BUILD OUTPUT — a generated, gitignored type-reference file under the
#     dashboard, rewritten by every dev/build invocation, whose one comment
#     line carries the generator's documentation URL.
#   * RUNTIME LOGS — the hook-fire JSONL under cabinet/logs/, ignored
#     wholesale, carrying whatever URLs the day's work mentioned.
#   * NESTED WORKTREES — other waves' checkouts of THIS repository under
#     .claude/worktrees/, i.e. the seed walk descending into a second copy of
#     the tree plus every doc that copy carries.
#
# Measured on the launching deployment 2026-08-02: 48 derived labels from the
# committed tree, 72 from the same commit's working checkout. The 24-label
# delta lit 19 VENDOR_TOKEN findings in framework/ that no baseline row covers
# — a RED that is unreproducible in CI, cannot be fixed by touching framework/,
# and is the exact pressure that gets a gate deleted. Reproduced from a SINGLE
# planted build artifact in a depth-1 clone (arm B of the CI-shape harness in
# the landing PR), so it is one `npm run dev` away for every contributor.
#
# So: when git metadata is available the seed is the TRACKED set; when it is
# not — a hatched cabinet, an egg cut, an unpacked tarball — everything present
# IS the delivered tree and the whole walk is correct. Same commit, same
# vocabulary, in CI, in a hatch, and in a dirty dev checkout: the property the
# old paragraph asserted, now actually held and pinned by
# TestSpecificsSeedCorpus.
#
# THE DIRECTION IT FAILS. Filtering can only SHRINK the vocabulary, so an
# untracked seed file no longer teaches the gate: a contributor who writes a new
# vendor URL and a new framework mention in the same uncommitted change sees
# green locally and RED in CI the moment both are committed. That asymmetry is
# deliberate and is the safe one — the gate's subject is what SHIPS, and being
# weaker than CI before a commit is recoverable, while a local-only red nobody
# can reproduce is not. The SCAN set (iter_specifics_files) deliberately does
# NOT get the same treatment: an uncommitted framework file should be scanned,
# because there the early warning is the whole point.
_SEED_ROOTS = (
    "framework", "cabinet", "docs", "packs", "memory", "shared",
    ".claude", ".claude-plugin", ".github",
)
# Never descended into even under a seed root: build output and dependency
# trees are not the repository's own vocabulary.
_SEED_SKIP_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".next", "dist", "build",
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


def tracked_paths(root) -> "Optional[frozenset[str]]":
    """The SHIPPED corpus of ``root``: every path git tracks there, as POSIX
    relatives — or ``None`` when this tree carries no usable git metadata, which
    is the honest answer for a hatched cabinet, an egg cut or an unpacked
    tarball, and means "take the whole walk" (everything present is what was
    delivered). See the _SEED_ROOTS comment for the defect this exists for.

    TOTAL BY CONSTRUCTION — six ways to have no answer, one return value. A
    missing `git` binary, a directory that is not a repository, a directory
    whose toplevel is an ANCESTOR repository (a tmp fixture under a checkout,
    or a hatch unpacked inside one — that index says nothing about THIS tree),
    a non-zero `ls-files`, a timeout, and an EMPTY listing all yield ``None``.
    The empty case is the one that matters: a `frozenset()` is falsy but is NOT
    None, and letting it through would blank the vocabulary and hand Arm 2 the
    inert green that `test_the_live_vocabulary_is_derived_and_non_empty` exists
    to refuse — the sensor reporting on nothing, one layer down.

    DELIBERATELY UNCACHED. A memo keyed on the path would be read-once state in
    a process that plants files and re-derives inside a single test; this file's
    own hermetic arms add a file and re-ask in the next statement, and a warm
    cache would certify the pre-change answer. `git ls-files` is one process on
    a tree this size; correctness is worth more than the milliseconds.
    """
    key = os.path.realpath(str(root))
    if shutil.which("git") is None:
        return None
    try:
        top = subprocess.run(["git", "-C", key, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=60)
        if top.returncode != 0 or os.path.realpath(top.stdout.strip()) != key:
            return None
        ls = subprocess.run(["git", "-C", key, "ls-files", "-z", "--cached"],
                            capture_output=True, text=True, timeout=60)
        if ls.returncode != 0:
            return None
        names = frozenset(n for n in ls.stdout.split("\0") if n)
        return names or None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def iter_seed_files(root: Path) -> Iterator[Path]:
    """Every text file the vocabulary may be derived from: root-level files plus
    the declared _SEED_ROOTS (see the comment there for why it is an include
    list, which layers are deliberately absent, and why the result is filtered
    to the SHIPPED tree)."""
    root = Path(root)
    tracked = tracked_paths(root)

    def _ships(p: Path) -> bool:
        if tracked is None:  # no git metadata: everything present was delivered
            return True
        try:
            return p.relative_to(root).as_posix() in tracked
        except ValueError:  # outside the root entirely — never ours to seed
            return False

    def _files_under(base: Path, recurse: bool) -> Iterator[Path]:
        if not base.is_dir():
            return
        for dirpath, dirnames, filenames in os.walk(str(base)):
            dirnames[:] = ([] if not recurse
                           else sorted(d for d in dirnames if d not in _SEED_SKIP_DIRS))
            for name in sorted(filenames):
                p = Path(dirpath) / name
                try:
                    if p.is_symlink() or p.stat().st_size > _SEED_MAX_BYTES:
                        continue
                except OSError:
                    continue
                if not _ships(p):
                    continue
                yield p
    for p in _files_under(root, recurse=False):
        yield p
    for rel in _SEED_ROOTS:
        for p in _files_under(root / rel, recurse=True):
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
    "Route the specific to the per-deployment layer, reach it through an "
    "adapter seam (the channel-adapter protocol under framework/channels/, "
    "framework.sources.get_source), or read it from config — the DOTTED "
    "module path for the channel seam is deliberately not written here: a "
    "sibling tripwire fences every file that can bind it. If the coupling "
    "is genuinely unavoidable TODAY, it "
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

    def test_the_live_scan_actually_visits_the_subject(self):
        """Non-vacuity of the SUBJECT, the other half of the pair above. The
        ratchet asserts a SUBSET, and the empty set is a subset of everything:
        a scan that visited no file reports exactly the same green as a clean
        framework. That makes 'the walk is wired' a thing to prove, not assume
        — the sensor-tests-something-other-than-the-control failure, aimed at
        this file. A FLOOR on files visited (never on findings, which are meant
        to reach zero) is what separates the two greens."""
        subject = _REPO_ROOT / "framework"
        assert subject.is_dir(), (
            "the scan subject %s does not exist — every specifics assertion "
            "below it is vacuously true" % subject)
        visited = sum(1 for _ in iter_specifics_files(subject))
        assert visited >= _SPECIFICS_SCAN_FLOOR, (
            "the specifics scan visited only %d files (floor %d) — the walk is "
            "broken (wrong root? skip-dirs?), and a SUBSET assertion over an "
            "empty finding set passes no matter what the tree contains"
            % (visited, _SPECIFICS_SCAN_FLOOR))


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

    def test_a_layer_outside_the_seed_roots_never_seeds(self, tmp_path):
        # A stranger's OWN suppliers live in the per-deployment layer
        # legitimately; letting them bind the framework gate would go red on
        # their supplier's name. That layer is not a seed root, so a URL under
        # any non-root directory contributes nothing.
        self._write(tmp_path / "not-a-seed-root" / "config" / "x.yml",
                    "url: https://api.vendorx.io/v2\n")
        assert "vendorx" not in derive_vendor_vocabulary(tmp_path)
        # ...and the control: the SAME file under a seed root does seed, so the
        # arm above cannot pass by the walk being broken.
        self._write(tmp_path / "cabinet" / "config" / "x.yml",
                    "url: https://api.vendorx.io/v2\n")
        assert "vendorx" in derive_vendor_vocabulary(tmp_path)

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


_GIT = shutil.which("git")


class TestSpecificsSeedCorpus:
    """THE CORPUS MUST BE THE SHIPPED TREE, identically in every environment.

    The defect these pin, measured 2026-08-02 and reproduced from ONE planted
    file in a depth-1 clone: the seed walk read the filesystem, so a working
    checkout's build output, runtime logs and nested worktrees taught the gate
    24 labels the committed tree does not carry, and 19 framework/ lines went
    RED in a way CI could not reproduce and framework/ could not fix. The
    counterpart failure — a filter so eager it seeds nothing — is pinned too:
    an empty listing must degrade to the walk, never to an empty vocabulary.
    """

    @staticmethod
    def _git(cwd: Path, *args: str) -> None:
        env = dict(os.environ,
                   HOME=str(cwd), GIT_CONFIG_NOSYSTEM="1",
                   GIT_TERMINAL_PROMPT="0")
        subprocess.run(["git", "-C", str(cwd)] + list(args), check=True,
                       capture_output=True, text=True, timeout=60, env=env)

    def _repo(self, tmp_path: Path) -> Path:
        """A real git tree. `git add` alone is enough — `ls-files --cached`
        reads the INDEX, so no commit and no identity config is needed, which
        keeps the fixture usable on a runner with no git user configured."""
        self._git(tmp_path, "init", "-q")
        return tmp_path

    @staticmethod
    def _write(p: Path, body: str) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    @pytest.mark.skipif(_GIT is None, reason="no git binary in this environment")
    def test_an_untracked_seed_file_does_not_teach_the_gate(self, tmp_path):
        """The arm, and its control in the same test so neither can pass alone:
        the SAME bytes seed or do not seed purely on whether git tracks them."""
        repo = self._repo(tmp_path)
        self._write(repo / "cabinet" / "shipped.md", "https://api.vendorx.io/v2\n")
        self._git(repo, "add", "cabinet/shipped.md")
        self._write(repo / "cabinet" / "scratch.md", "https://api.vendory.io/v2\n")
        v = derive_vendor_vocabulary(repo)
        assert "vendorx" in v, "a TRACKED seed file stopped seeding — the filter ate the corpus"
        assert "vendory" not in v, (
            "an UNTRACKED seed file taught the gate a label the shipped tree "
            "does not carry — the corpus is the filesystem again")
        # CONTROL: track the very same bytes; the label must appear.
        self._git(repo, "add", "cabinet/scratch.md")
        assert "vendory" in derive_vendor_vocabulary(repo)

    @pytest.mark.skipif(_GIT is None, reason="no git binary in this environment")
    def test_a_gitignored_build_artifact_cannot_red_the_framework(self, tmp_path):
        """The measured defect END TO END, as a regression: a generated,
        gitignored file under a seed root carries a vendor's documentation URL,
        and a framework module mentions that label as an ordinary word. Before
        the corpus filter this was a finding; after it, it is not — and the
        control proves the pair would still fire if the artifact SHIPPED."""
        repo = self._repo(tmp_path)
        self._write(repo / ".gitignore", "generated/\n")
        self._write(repo / "framework" / "detect.py", "STACKS = ('vendorz',)\n")
        self._git(repo, "add", ".gitignore", "framework/detect.py")
        self._write(repo / "cabinet" / "generated" / "artifact.d.ts",
                    "// see https://vendorz.io/docs for more information\n")
        v = derive_vendor_vocabulary(repo)
        assert scan_specifics(repo / "framework", vocabulary=v, rel_to=repo) == [], (
            "a gitignored build artifact still reds framework/ — the RED that "
            "cannot be reproduced in CI is back")
        # CONTROL: the identical URL in a file that SHIPS must still fire, or
        # this arm is passing because the engine stopped working.
        self._write(repo / "cabinet" / "shipped.md",
                    "// see https://vendorz.io/docs for more information\n")
        self._git(repo, "add", "cabinet/shipped.md")
        v2 = derive_vendor_vocabulary(repo)
        assert [x[1] for x in scan_specifics(repo / "framework", vocabulary=v2,
                                             rel_to=repo)] == ["VENDOR_TOKEN"]

    def test_without_git_metadata_the_whole_walk_is_the_corpus(self, tmp_path):
        """The hatch / egg / tarball path: nothing is "tracked" there, and
        everything present was delivered. A filter that returned an empty set
        here would silently empty the vocabulary — the inert-sensor green — so
        the fallback is asserted, not assumed."""
        assert not (tmp_path / ".git").exists()
        self._write(tmp_path / "cabinet" / "notes.md", "https://api.vendorx.io/v2\n")
        assert tracked_paths(tmp_path) is None
        assert "vendorx" in derive_vendor_vocabulary(tmp_path)

    @pytest.mark.skipif(_GIT is None, reason="no git binary in this environment")
    def test_a_repository_with_an_empty_index_falls_back_to_the_walk(self, tmp_path):
        """THE DEGENERATE END, and the one place where "empty" must not mean
        "nothing ships". A tree that is a repository but stages nothing yields
        an EMPTY listing; honouring it would filter the seed down to zero files
        and leave VENDOR_TOKEN matching against an empty vocabulary — green,
        forever, over any tree. The fallback fails toward MORE vocabulary, i.e.
        toward a red somebody has to look at, which is the only acceptable
        direction for a sensor's degenerate case. Deliberately in tension with
        test_an_untracked_seed_file_does_not_teach_the_gate above: there the
        index says what ships, here it says nothing at all."""
        repo = self._repo(tmp_path)
        self._write(repo / "cabinet" / "notes.md", "https://api.vendorx.io/v2\n")
        assert tracked_paths(repo) is None, (
            "an empty index was treated as the shipped corpus — the seed walk "
            "now yields nothing and Arm 2 matches against an empty vocabulary")
        assert "vendorx" in derive_vendor_vocabulary(repo)

    @pytest.mark.skipif(_GIT is None, reason="no git binary in this environment")
    def test_an_ancestor_repository_never_speaks_for_a_nested_tree(self, tmp_path):
        """A hatch unpacked inside a checkout, or a fixture under one: the
        ancestor's index tracks none of those paths, so a naive `ls-files` would
        report "tracked: nothing" and seed NOTHING. The toplevel check makes
        that case the fallback instead of an empty corpus."""
        repo = self._repo(tmp_path)
        nested = repo / "unpacked"
        self._write(nested / "cabinet" / "notes.md", "https://api.vendorx.io/v2\n")
        assert tracked_paths(nested) is None
        assert "vendorx" in derive_vendor_vocabulary(nested)

    def test_the_live_seed_corpus_carries_nothing_the_tree_does_not_ship(self):
        """THE LIVE WIRING ARM — the one that was red on the launching
        deployment and green in CI, which is the whole point. Every file the
        vocabulary is derived from must be a file the repository ships."""
        tracked = tracked_paths(_REPO_ROOT)
        if tracked is None:  # an egg cut or a hatch: the walk IS the corpus
            return
        strays = []
        for p in iter_seed_files(_REPO_ROOT):
            rel = p.relative_to(_REPO_ROOT).as_posix()
            if rel not in tracked:
                strays.append(rel)
        assert strays == [], (
            "the vendor vocabulary is being derived from %d file(s) this "
            "repository does not ship — build output, runtime logs or a nested "
            "worktree are teaching a gate that decides merges: %s"
            % (len(strays), strays[:10]))

    def test_the_corpus_filter_is_live_wherever_it_can_be(self):
        """Non-vacuity of the filter itself, stated as a biconditional so there
        is no environment in which it quietly does nothing: git metadata plus a
        git binary means the shipped corpus is RESOLVED, and the absence of
        either means the documented fallback — never a silent third state."""
        resolvable = (_REPO_ROOT / ".git").exists() and _GIT is not None
        tracked = tracked_paths(_REPO_ROOT)
        assert (tracked is not None) == resolvable, (
            "shipped-corpus resolution disagrees with the environment "
            "(.git present=%s, git binary=%s, resolved=%s)"
            % ((_REPO_ROOT / ".git").exists(), _GIT is not None, tracked is not None))
        if tracked is not None:
            assert "LICENSE" in tracked, (
                "the tracked listing resolved but does not contain the one file "
                "every cut of this repository carries — it is not this tree's")


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


# ===========================================================================
# ARM 3 — THE PERSON RATCHET  (added 2026-07-30)
# ===========================================================================
# THE DEFECT THIS EXISTS FOR, stated plainly because this file was itself
# guilty of it. Arm 1 pins a SYNTHETIC placeholder — the demo captain
# `Testburg`. That token is not, and never was, the launching deployment's
# operator, so the sensor guarding agnosticism was blind to the exact thing it
# exists to catch: measured 2026-07-30, FIFTEEN occurrences of the real
# operator's name sat inside framework/ — a module docstring, five lines of one
# test, the authority classifier, its tests, the acting tests, the env resolver
# and two further test modules — with Arm 1 green over every one of them. A
# gate that can only see the placeholder proves the placeholder is absent.
#
# THE RULE, DERIVED — never a list of names. A list of names inside framework/
# would BE the leak this arm prevents, one level up, and it could only ever
# name the people somebody already thought of.
#
#   PERSON_LITERAL — a word-bounded occurrence, anywhere under framework/, of a
#       token from the OPERATOR IDENTITY that this repository and its instance
#       layer DECLARE about themselves. Three declaration surfaces, all
#       structured, all OUTSIDE framework/ — so cleaning framework can never
#       blind the rule (the seed does not live in the thing being cleaned;
#       Arm 2 earns its teeth the same way):
#         * THE LICENCE COPYRIGHT HOLDER. A licence must name its holder, so
#           this is the one place in a public tree where a real person's name
#           is not merely allowed but REQUIRED. That makes it the ideal seed
#           and framework/ the ideal subject: one name, one tree, one file
#           where it belongs and one layer where it never does.
#         * THE REPOSITORY OWNER HANDLE in the plugin/marketplace manifests
#           (`github.com/<owner>/…`, `"repo": "<owner>/…"`), split on its
#           separators — which is how a handle teaches the gate a diminutive
#           that no dictionary would derive from a legal name.
#         * THE INSTANCE LAYER, which is where an operator's identity belongs
#           and the surface this unit was told to derive from: a declared
#           `captain_name`, and `name` / `names` under a `captain:` or
#           `operator:` block of the onboarding answers record. In the scrubbed
#           public tree these are placeholders or absent, so they contribute
#           nothing HERE and everything in a live deployment. The asymmetry is
#           the point: the arm has teeth in CI from the LICENCE alone, and
#           grows more the moment a real cabinet declares whose it is.
#
# THE RESOLVER'S OWN DEFAULT IS NOT AN IDENTITY. `captain_name` falls back to a
# generic role word, and the tracked platform.yml carries exactly that word.
# Seeded, it would forbid the role vocabulary framework is SUPPOSED to speak,
# everywhere, and the arm would be unlandable. The default is read out of the
# resolver's own signature in framework/env.py and subtracted — derived, one
# value, no list — and `test_the_captain_name_default_is_still_derivable` goes
# RED if that read ever stops resolving, so the subtraction cannot silently
# widen into "seeds nothing".
#
# NO BASELINE, NO DEBT LEDGER, NO ALLOWLIST. Arm 2 ratchets against recorded
# debt because a framework already speaking to a dozen vendors cannot be
# cleaned in one commit. There is no equivalent here: the target is ZERO and
# the tree is AT zero as of this commit. A person literal in the universal
# layer is never acceptable debt, so there is nothing an exemption could hold.
#
# WHAT THIS CANNOT SEE — read this before treating green as coverage. Every
# number below was measured on the tree this arm landed with.
#   1. A PROPER NOUN THAT IS NOT THE OPERATOR'S. A colleague, a customer, a
#      counterparty. Nothing declares them, so nothing derives them, and no
#      shape separates a real first name from a synthetic one: framework's own
#      fidelity fixtures carry 27 display-name literals (`Otto <u@x>`,
#      `Ada <n@x>`, `Bo <b@x>`) this arm reads as green and could not tell from
#      real ones. Detecting an arbitrary person name needs a dictionary or a
#      model — the hand-maintained list, one level up.
#   2. A GLUED COMPOUND. The match is word-bounded, so an underscore or
#      camel-case compound never fires — deliberately, mirroring Arm 1, whose
#      docstring makes the same promise about `testburg_model`. Measured: 95
#      such occurrences across 23 framework files, every one an external
#      brain-artifact identifier. They ARE an agnosticism defect; they are a
#      coordinated-rename unit with a byte-compat surface, not something to
#      bury inside this scan's blast radius. Un-gluing one to hide it would be
#      caught the moment it was un-glued.
#   3. A NAME IN A NON-LATIN SCRIPT, or a transliteration of one. Tokens are
#      `[A-Za-z]` runs on BOTH sides of the join, so a Cyrillic, CJK, Hebrew or
#      Arabic identity derives nothing AND matches nothing — it fails silent,
#      not loud. `test_a_non_latin_identity_is_invisible_and_says_so` pins that
#      honestly, and proves it WITHOUT reusing this module's own splitter.
#   4. A NAME ASSEMBLED FROM FRAGMENTS. This reads source TEXT; a name that
#      never appears whole on one line is not seen.
#   5. A NAME IN A DATED DESIGN SNAPSHOT under framework/docs/. Excluded on the
#      predicate Arm 2 already uses, for the reason the egg manifest ratified
#      (R162 + R145): those files are the launching deployment's own minutes,
#      they are archived OUT of the egg, and rewording a dated record falsifies
#      it. Measured: 70 operator-name occurrences live in the three of them. A
#      stranger never receives those bytes; a reader of the public repository
#      does.
#   6. A TOKEN SHORTER THAN _PERSON_MIN_TOKEN_LEN, in any position.
#   7. A DECLARATION THE KEY-LINE READER CANNOT SEE. The instance seed reads
#      declared key LINES (stdlib only — this module still imports nothing and
#      executes nothing). A flow-style `captain: {name: X}`, a quoted
#      multi-line scalar, an identity under a key this gate does not name, or a
#      `handles:` value that is an account rather than a name, derive nothing.
#   8. ANYTHING OUTSIDE framework/. The operating layer, the presets and the
#      packs are the deployment's own and are entitled to name it.
#   9. A DECLARATION SURFACE THAT STOPS YIELDING. The non-vacuity floor is on
#      the UNION of the three surfaces, so a surface can go quiet — a fork or
#      an org move retargets the owner handle, a licence line is reworded —
#      and the tokens it ALONE contributed stop being policed while the floor
#      still passes and nothing goes red. Measured on the tree this arm landed
#      with: the owner handle is the sole source of the short diminutive, and
#      it is the token 15 of the 15 original literals used. There is no honest
#      per-surface floor to add — a repository legitimately owned by an
#      organisation yields no person-shaped handle, and reddening that is a
#      false alarm on a correct tree — so this is a limit to KNOW, not one to
#      close: after any change to the licence line or the manifests, re-read
#      what `derive_operator_identity` returns.
#      `test_a_surface_that_stops_declaring_narrows_the_arm_silently` pins it
#      in both directions so the narrowing is at least a measured property.
#
# WHAT IT CAN GET WRONG, the mirror of the above, stated because a stranger
# will meet it before I do: a deployment whose operator's name collides with
# ordinary framework vocabulary — or with one of framework's own synthetic
# fixture people — goes RED on a tree they never touched. The remedy is the
# capped exclusion set below (EMPTY today), exactly as in Arm 2, and the
# failure message names both the token and the surface it was derived FROM, so
# the diagnosis is one read long.
#
# Green here means "framework/ does not name the operator this deployment
# declares". It does not mean "framework/ names nobody".

_PERSON_MIN_TOKEN_LEN = 4  # below this a token is initials or grammar, not a name

# THE SUBJECT FLOOR, Arm 2's law again: a scan that visited nothing reports the
# same green as a clean tree. An order of magnitude below the live count (624
# files walked, measured 2026-07-30) because the FINDING count is meant to stay
# at zero forever while the file count is not.
_PERSON_SCAN_FLOOR = 200

# The identity DECLARATION surfaces, by path: root-level files plus the
# instance layer, never framework/ itself — the subject cannot be allowed to
# teach the gate what to forgive.
_LICENSE_FILES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")
_OWNER_MANIFESTS = (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json")
_INSTANCE_CONFIG_DIR = "instance/config"
_CAPTAIN_NAME_RESOLVER = "framework/env.py"

_COPYRIGHT_RX = re.compile(
    r"\bCopyright\b\s*(?:\((?:c|C)\)|©)?\s*(?:\d{4}(?:\s*[-–,]\s*\d{4})*)?\s*(.+)")
_OWNER_URL_RX = re.compile(r"github\.com[/:]([A-Za-z0-9][A-Za-z0-9._-]*)/")
_OWNER_FIELD_RX = re.compile(r'"repo"\s*:\s*"([A-Za-z0-9][A-Za-z0-9._-]*)/')
_NAME_WORD_RX = re.compile(r"[A-Za-z]+")
_TOP_KEY_RX = re.compile(r"\A([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)\Z")
_LEAF_KEY_RX = re.compile(r"\A\s+([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)\Z")
_LIST_ITEM_RX = re.compile(r"\A\s*-\s*(.+)\Z")
# The resolver's own fallback, read from its signature rather than repeated.
_CAPTAIN_DEFAULT_RX = re.compile(
    r"def\s+captain_name\s*\(\s*default\s*:\s*str\s*=\s*[\"']([^\"']+)[\"']")

_IDENTITY_TOP_KEYS = ("captain", "operator")
_IDENTITY_LEAF_KEYS = ("name", "names")
_IDENTITY_SCALAR_KEYS = ("captain_name",)

# GRAMMAR, NOT NAMES. The tail of a copyright line is as often prose as a
# person ("Copyright (c) 2026 The Cabinet Contributors"), and an entity suffix
# names an organisation rather than the operator. Every member is an article or
# a legal-entity/collective word — none is anybody's name, which is what keeps
# this from being the list this arm forbids. It SUBTRACTS, so growing it
# weakens the gate: capped and shrink-only, like the collision set below.
_NON_IDENTITY_WORDS = frozenset({
    "gmbh", "corp", "corporation", "company", "contributors", "contributor",
    "authors", "author", "project", "team", "rights", "reserved", "holders",
    "holder", "foundation",
})
_NON_IDENTITY_WORDS_MAX = 15  # may only be LOWERED

# THE ONE NAME-SHAPED HAND-MAINTAINED ELEMENT IN ARM 3 — and it is an
# EXCLUSION, so growing it WEAKENS the gate; hence the cap and the required
# justification, mirroring Arm 2's _COLLISION_TOKENS. An entry belongs here
# only when a DERIVED identity token is also ordinary vocabulary in this
# repository's own prose. EMPTY: no derived token collides today.
_PERSON_COLLISION_TOKENS: Dict[str, str] = {}
_PERSON_COLLISION_TOKENS_MAX = 0  # may only be LOWERED

PersonFinding = Tuple[str, int, str]  # (display_path, line_no, token)


def _scalar(value: str) -> str:
    """A declared scalar, minus a trailing comment and matched quotes."""
    v = value.split(" #", 1)[0].strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v.strip()


def _name_tokens(text: str) -> "frozenset[str]":
    """The name-shaped tokens of a declared identity string. Latin letters only
    — WHAT THIS CANNOT SEE item 3, which is measured rather than assumed."""
    return frozenset(
        w.lower() for w in _NAME_WORD_RX.findall(text)
        if len(w) >= _PERSON_MIN_TOKEN_LEN and w.lower() not in _NON_IDENTITY_WORDS)


def _declared_identity_values(text: str) -> List[str]:
    """Values declared under an identity key, read as DECLARED KEY LINES rather
    than parsed as YAML: this module imports nothing and executes nothing, and
    a second code path behind a `try: import yaml` would be a second behaviour
    to keep true. Item 7 above states exactly what this reader cannot see."""
    out = []  # type: List[str]
    top = None  # type: Optional[str]
    leaf = None  # type: Optional[str]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m_top = _TOP_KEY_RX.match(raw)
        if m_top:
            top, leaf = m_top.group(1).lower(), None
            if top in _IDENTITY_SCALAR_KEYS:
                out.append(_scalar(m_top.group(2)))
            continue
        if top not in _IDENTITY_TOP_KEYS:
            continue
        m_leaf = _LEAF_KEY_RX.match(raw)
        if m_leaf:
            leaf = m_leaf.group(1).lower()
            if leaf in _IDENTITY_LEAF_KEYS:
                out.append(_scalar(m_leaf.group(2)))
            continue
        m_item = _LIST_ITEM_RX.match(raw)
        if m_item and leaf in _IDENTITY_LEAF_KEYS:
            out.append(_scalar(m_item.group(1)))
    return [v for v in out if v]


def captain_name_default(root) -> Optional[str]:
    """The generic fallback `framework.env.captain_name()` returns when a
    deployment declares nothing — read out of the resolver's own signature so
    this file never repeats it. None when the read stops resolving, which
    subtracts nothing and so fails toward a NOISIER gate, never a quieter one;
    the live test pins that it still resolves."""
    txt = _read_text_file(Path(root) / _CAPTAIN_NAME_RESOLVER)
    if txt is None:
        return None
    m = _CAPTAIN_DEFAULT_RX.search(txt)
    return m.group(1) if m else None


def derive_operator_identity(root) -> Dict[str, str]:
    """THE DERIVATION: token -> the surface that declared it. Nothing here is a
    list of names; every token comes from a structured declaration this
    repository or its instance layer makes ABOUT ITSELF, and every surface sits
    outside framework/ so the subject cannot teach the gate to forgive it."""
    root = Path(root)
    vocab = {}  # type: Dict[str, str]

    def _add(tokens, why: str) -> None:
        for t in tokens:
            vocab.setdefault(t, why)

    for rel in _LICENSE_FILES:
        txt = _read_text_file(root / rel)
        if txt is None:
            continue
        for line in txt.splitlines():
            m = _COPYRIGHT_RX.search(line)
            if m:
                _add(_name_tokens(m.group(1)), "%s copyright holder" % rel)

    for rel in _OWNER_MANIFESTS:
        txt = _read_text_file(root / rel)
        if txt is None:
            continue
        for rx in (_OWNER_URL_RX, _OWNER_FIELD_RX):
            for m in rx.finditer(txt):
                _add(_name_tokens(m.group(1).replace("-", " ").replace("_", " ")),
                     "repository owner handle in %s" % rel)

    cfg = root / _INSTANCE_CONFIG_DIR
    default = (captain_name_default(root) or "").strip().lower()
    if cfg.is_dir():
        for p in sorted(cfg.iterdir()):
            # A shipped `*.example` is a placeholder, not a declaration.
            if not p.is_file() or p.suffix == ".example":
                continue
            if p.suffix not in (".yml", ".yaml"):
                continue
            txt = _read_text_file(p)
            if txt is None:
                continue
            for value in _declared_identity_values(txt):
                if default and value.strip().lower() == default:
                    continue  # the resolver's own role word declares nobody
                _add(_name_tokens(value),
                     "declared operator identity in %s/%s" % (_INSTANCE_CONFIG_DIR, p.name))

    for tok in _PERSON_COLLISION_TOKENS:
        vocab.pop(tok, None)
    return vocab


def _person_vocabulary_regex(vocabulary) -> "Optional[re.Pattern[str]]":
    """Word-bounded in the FULL identifier sense — `_` is inside the boundary
    class, not outside it, so a glued compound never matches (item 2). Arm 2's
    regex deliberately excludes `_` because a vendor label glued into an
    identifier still names the vendor; a person token glued into an artifact
    identifier is a different, separately-owned defect."""
    if not vocabulary:
        return None
    alts = "|".join(re.escape(v) for v in sorted(vocabulary, key=lambda s: (-len(s), s)))
    return re.compile(r"(?<![A-Za-z0-9_])(" + alts + r")(?![A-Za-z0-9_])", re.IGNORECASE)


def iter_person_files(root: Path) -> Iterator[Path]:
    """The scan set: every text file under the tree INCLUDING its tests — five
    of the fifteen literals this arm was built for lived in a single test file,
    framework tests SHIP in the egg, and a name in a fixture publishes exactly
    as widely as a name in a module. Each file's PATH is scanned as well as its
    content (a directory named after the operator publishes the name too).
    Dated design snapshots under docs/ are the one exclusion (item 5)."""
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = sorted(d for d in dirnames
                             if d != "__pycache__" and d not in _SEED_SKIP_DIRS)
        for name in sorted(filenames):
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            if rel.startswith("docs/") and _DATED_DESIGN_DOC_RX.search(name):
                continue
            yield p


def scan_person_literals(root, vocabulary=None, rel_to=None) -> List[PersonFinding]:
    """Read-only scan of ``root`` for a declared operator-identity token, in
    the file's PATH as well as its CONTENT. Returns (display_path, line_no,
    token), sorted, one entry per token per line; ``line_no`` 0 means the
    finding is the path itself, not a line in the file. Symlink escapes are
    refused, never followed (realpath containment, mirroring Arms 1 and 2)."""
    root = Path(root)
    base = Path(rel_to) if rel_to is not None else root
    if vocabulary is None:
        vocabulary = derive_operator_identity(base)
    rx = _person_vocabulary_regex(set(vocabulary))
    real_root = os.path.realpath(str(root))
    found = []  # type: List[PersonFinding]
    for p in iter_person_files(root):
        try:
            display = p.relative_to(base).as_posix()
        except ValueError:
            display = p.as_posix()
        rp = os.path.realpath(str(p))
        if rp != real_root and not rp.startswith(real_root + os.sep):
            found.append((display, 0, "symlink escape — refused"))
            continue
        if rx is None:
            continue
        # A PATH IS PUBLISHED TEXT TOO. A directory or a file NAMED after the
        # operator ships the name exactly as widely as a line inside it, and a
        # content-only scan calls that tree green — the gap this arm's own
        # summary sentence ("framework/ does not name the operator") would
        # otherwise be wrong about. Matched on the path relative to the SCAN
        # ROOT, never the display path, so the subject directory's own name can
        # never seed a finding (an operator called `Framework` would otherwise
        # red every file in the tree — pinned below).
        seen_path = set()  # type: set
        for m in rx.finditer(p.relative_to(root).as_posix()):
            tok = m.group(1).lower()
            if tok not in seen_path:
                seen_path.add(tok)
                found.append((display, 0, tok))
        txt = _read_text_file(p)
        if txt is None:
            continue
        for i, line in enumerate(txt.splitlines(), 1):
            seen = set()
            for m in rx.finditer(line):
                tok = m.group(1).lower()
                if tok not in seen:
                    seen.add(tok)
                    found.append((display, i, tok))
    return sorted(found)


_PERSON_HINT = (
    "framework/ is the universal layer — it may not name the person this "
    "deployment belongs to, in a line OR in a path (line 0 = the path itself). "
    "An EXAMPLE takes an obviously-synthetic "
    "placeholder (`<display>`, `abcd`, the demo identity); a value that has to "
    "be real lives in the instance layer and reaches framework only through a "
    "resolver (framework.env.captain_name()). There is no allowlist and no "
    "baseline here: a person literal in the universal layer is not debt to be "
    "recorded, it is a leak to be removed")


class TestPersonRatchet:
    """Arm 3 over the live tree."""

    def test_framework_names_no_person(self):
        """THE RATCHET: no token of the operator identity this repository and
        its instance layer DECLARE may appear anywhere under framework/."""
        vocabulary = derive_operator_identity(_REPO_ROOT)
        findings = scan_person_literals(_REPO_ROOT / "framework",
                                        vocabulary=vocabulary, rel_to=_REPO_ROOT)
        assert findings == [], "%s\nOffenders: %s\nDerived from: %s" % (
            _PERSON_HINT,
            ["%s:%d (%s)" % f for f in findings[:40]],
            sorted({vocabulary.get(f[2], "?") for f in findings}))

    def test_the_operator_identity_is_derived_and_non_empty(self):
        """Non-vacuity of the SEED. An empty vocabulary makes the ratchet a
        no-op that still reports green — the sensor-tests-nothing failure this
        program keeps finding, aimed at this file. A repository declaring no
        owner anywhere (no copyright holder, no owner handle, no instance
        identity) cannot be policed, and has to say so rather than pass."""
        vocabulary = derive_operator_identity(_REPO_ROOT)
        assert vocabulary, (
            "no operator identity could be derived — every declaration surface "
            "(%s, %s, %s) came back empty, so PERSON_LITERAL is inert while "
            "still reporting green. Name the copyright holder in the LICENCE."
            % (_LICENSE_FILES[0], _OWNER_MANIFESTS[0], _INSTANCE_CONFIG_DIR))
        assert all(len(t) >= _PERSON_MIN_TOKEN_LEN for t in vocabulary), vocabulary
        assert not (set(_PERSON_COLLISION_TOKENS) & set(vocabulary))

    def test_the_person_scan_actually_visits_the_subject(self):
        """Non-vacuity of the SUBJECT. The ratchet asserts an EMPTY finding
        set, and a walk that visited no file produces exactly that. A floor on
        files VISITED — never on findings, which are meant to stay at zero — is
        what separates the two greens."""
        subject = _REPO_ROOT / "framework"
        assert subject.is_dir(), (
            "the scan subject %s does not exist — every person assertion below "
            "it is vacuously true" % subject)
        visited = sum(1 for _ in iter_person_files(subject))
        assert visited >= _PERSON_SCAN_FLOOR, (
            "the person scan visited only %d files (floor %d) — the walk is "
            "broken (wrong root? skip-dirs?), and an EMPTY finding set is green "
            "no matter what the tree contains" % (visited, _PERSON_SCAN_FLOOR))

    def test_the_captain_name_default_is_still_derivable(self):
        """The subtraction's own wiring. The resolver's generic fallback is
        read out of framework/env.py so this file never repeats it; were that
        read to stop resolving, the role word would be seeded as an identity
        and the arm would go red everywhere. Silent is the failure mode worth
        pinning, so this goes RED on the rename instead."""
        default = captain_name_default(_REPO_ROOT)
        assert default and default.strip(), (
            "could not read the captain_name fallback out of %s — the "
            "role-word subtraction is unwired" % _CAPTAIN_NAME_RESOLVER)

    def test_person_exclusion_sets_only_shrink_and_are_justified(self):
        """Both subtracting sets are capped. They WEAKEN the gate as they grow,
        which is the opposite pressure from a blocklist, and is why neither may
        widen without lowering the other side of a visible diff."""
        assert len(_PERSON_COLLISION_TOKENS) <= _PERSON_COLLISION_TOKENS_MAX, (
            "person-collision exclusions grew (%d > %d) — reword the framework "
            "text or narrow the derivation; do not widen the exclusion"
            % (len(_PERSON_COLLISION_TOKENS), _PERSON_COLLISION_TOKENS_MAX))
        thin = [k for k, why in _PERSON_COLLISION_TOKENS.items() if len(why) < 40]
        assert thin == [], "unjustified person-collision exclusions: %s" % thin
        assert len(_NON_IDENTITY_WORDS) <= _NON_IDENTITY_WORDS_MAX, (
            "the copyright-grammar stop set grew (%d > %d) — it subtracts from "
            "the vocabulary, so growth is a quieter gate"
            % (len(_NON_IDENTITY_WORDS), _NON_IDENTITY_WORDS_MAX))
        dead = sorted(w for w in _NON_IDENTITY_WORDS if len(w) < _PERSON_MIN_TOKEN_LEN)
        assert dead == [], (
            "these stop words are already dropped by the length filter, so they "
            "are dead cover that makes the set look larger than it is: %s" % dead)


class TestPersonEngine:
    """Hermetic proofs on own tmp trees — never the live vocabulary."""

    @staticmethod
    def _write(p: Path, body: str) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def _tree(self, tmp_path, files: Dict[str, str], fw=None):
        for rel, body in files.items():
            self._write(tmp_path / rel, body)
        for rel, body in (fw or {}).items():
            self._write(tmp_path / "framework" / rel, body)
        return derive_operator_identity(tmp_path)

    def test_identity_is_derived_from_the_licence(self, tmp_path):
        v = self._tree(tmp_path, {
            "LICENSE": "MIT License\n\nCopyright (c) 2026 Quillon Marrowby\n"})
        assert set(v) == {"quillon", "marrowby"}
        assert "LICENSE" in v["quillon"]

    def test_identity_is_derived_from_the_repository_owner_handle(self, tmp_path):
        """The diminutive no dictionary derives from a legal name: the OWNER
        segment of the repository's own manifest, split on its separators."""
        v = self._tree(tmp_path, {
            ".claude-plugin/plugin.json":
                '{"homepage": "https://github.com/quill-marrowby/some-repo"}\n'})
        assert {"quill", "marrowby"} <= set(v)
        assert "some" not in v and "repo" not in v  # the OWNER segment, not the repo

    def test_identity_is_derived_from_the_instance_layer(self, tmp_path):
        """The surface this arm was told to derive from. Absent in a scrubbed
        public tree, present in a live cabinet — teeth exactly where the real
        name is."""
        v = self._tree(tmp_path, {
            "instance/config/cabinet-init.answers.yml":
                "version: 1\n\ncaptain:\n  name: Quillon   # display name\n"
                "  timezone: Europe/Madrid\n",
            "instance/config/platform.yml": "captain_role: Head-of-Something\n"})
        assert "quillon" in v and "instance/config" in v["quillon"]
        assert not ({"europe", "madrid", "version", "head", "something"} & set(v))

    def test_a_names_list_and_an_operator_block_are_read(self, tmp_path):
        v = self._tree(tmp_path, {
            "instance/config/who.yml":
                "operator:\n  names:\n    - Quillon Marrowby\n    - Marrow\n"})
        assert {"quillon", "marrowby", "marrow"} <= set(v)

    def test_the_resolver_default_is_not_an_identity(self, tmp_path):
        """The role word the resolver falls back to declares nobody. Seeding it
        would forbid framework's own agnostic vocabulary everywhere."""
        v = self._tree(tmp_path, {
            "framework/env.py":
                'def captain_name(default: str = "Skipper") -> str:\n    return default\n',
            "instance/config/platform.yml": "captain_name: Skipper\n"})
        assert "skipper" not in v
        v2 = self._tree(tmp_path, {"instance/config/platform.yml": "captain_name: Quillon\n"})
        assert "quillon" in v2  # a real declaration on the same key still derives

    def test_an_example_file_declares_no_identity(self, tmp_path):
        """A shipped `.example` is a placeholder, not a declaration."""
        v = self._tree(tmp_path, {
            "instance/config/platform.yml.example": "captain_name: Quillon\n"})
        assert "quillon" not in v

    def test_copyright_grammar_is_not_an_identity(self, tmp_path):
        v = self._tree(tmp_path, {"LICENSE": "Copyright (c) 2026 The Cabinet Contributors\n"})
        assert not ({"the", "contributors"} & set(v))
        assert "cabinet" in v  # a declared holder token still derives

    def test_flags_a_planted_person_literal_in_a_module(self, tmp_path):
        v = self._tree(tmp_path, {"LICENSE": "Copyright (c) 2026 Quillon Marrowby\n"},
                       fw={"m.py": "# ask Quillon before shipping\n"})
        f = scan_person_literals(tmp_path / "framework", vocabulary=v, rel_to=tmp_path)
        assert ("framework/m.py", 1, "quillon") in f

    def test_flags_a_planted_person_literal_in_a_test_and_in_a_doc(self, tmp_path):
        """The scan set Arms 1 and 2 deliberately skip. Five of the fifteen
        literals this arm was built for lived in ONE test file."""
        v = self._tree(tmp_path, {"LICENSE": "Copyright (c) 2026 Quillon Marrowby\n"},
                       fw={"tests/test_x.py": 'CASE = "Quillon <q@x.example>"\n',
                           "docs/work-model.md": "reviewed by Marrowby\n"})
        f = scan_person_literals(tmp_path / "framework", vocabulary=v, rel_to=tmp_path)
        assert ("framework/tests/test_x.py", 1, "quillon") in f
        assert ("framework/docs/work-model.md", 1, "marrowby") in f

    def test_case_and_punctuation_do_not_hide_a_literal(self, tmp_path):
        v = self._tree(tmp_path, {"LICENSE": "Copyright (c) 2026 Quillon Marrowby\n"},
                       fw={"m.py": "# QUILLON, quillon; (Quillon) -Quillon-\n"})
        f = scan_person_literals(tmp_path / "framework", vocabulary=v, rel_to=tmp_path)
        assert f == [("framework/m.py", 1, "quillon")]  # one per token per line

    def test_a_glued_compound_is_not_flagged_and_that_is_declared(self, tmp_path):
        """Item 2, pinned in BOTH directions so the limit is a measured
        property and not a hope: the glued form passes, the un-glued form on
        the very next line does not."""
        v = self._tree(tmp_path, {"LICENSE": "Copyright (c) 2026 Quillon Marrowby\n"},
                       fw={"m.py": "quillon_model = 1\nowed_to_quillon = 2\n"})
        assert scan_person_literals(tmp_path / "framework", vocabulary=v,
                                    rel_to=tmp_path) == []
        self._write(tmp_path / "framework" / "m.py", "quillon_model = 1\n# ask Quillon\n")
        assert scan_person_literals(tmp_path / "framework", vocabulary=v,
                                    rel_to=tmp_path) == [("framework/m.py", 2, "quillon")]

    def test_a_short_token_is_not_derived(self, tmp_path):
        """Item 6. A three-letter name is initials-shaped and would collide with
        grammar everywhere; it is not derived, and that is the trade stated."""
        v = self._tree(tmp_path, {"LICENSE": "Copyright (c) 2026 Ada Lovelace\n"})
        assert "ada" not in v and "lovelace" in v

    def test_a_non_latin_identity_is_invisible_and_says_so(self, tmp_path):
        """Item 3, proven WITHOUT reusing the module's own splitter — an
        honesty arm sharing the assumption it checks passes vacuously, which
        this program has paid for five times. The independent check is a raw
        substring read of the bytes on disk: the name IS in the file, and the
        scan still returns nothing."""
        name = "Квиллон"
        v = self._tree(tmp_path, {"LICENSE": "Copyright (c) 2026 %s\n" % name},
                       fw={"m.py": "# ask %s before shipping\n" % name})
        planted = (tmp_path / "framework" / "m.py").read_text(encoding="utf-8")
        assert name in planted, "the fixture never planted the name"
        assert v == {}, "a non-Latin identity derives nothing — say so, do not imply teeth"
        assert scan_person_literals(tmp_path / "framework", vocabulary=v,
                                    rel_to=tmp_path) == []

    def test_a_dated_design_snapshot_is_excluded(self, tmp_path):
        """Item 5 — the egg archives those bytes out (R162/R145), so policing
        them is churn a stranger never benefits from. Pinned in both
        directions: dated is skipped, undated beside it is not."""
        v = self._tree(tmp_path, {"LICENSE": "Copyright (c) 2026 Quillon Marrowby\n"},
                       fw={"docs/design-2026-06-19.md": "Quillon decided this\n",
                           "docs/work-model.md": "Quillon decided this\n"})
        f = scan_person_literals(tmp_path / "framework", vocabulary=v, rel_to=tmp_path)
        assert f == [("framework/docs/work-model.md", 1, "quillon")]

    def test_an_empty_vocabulary_scans_nothing_rather_than_everything(self, tmp_path):
        """The degenerate end. With no declared identity the rule is inert by
        construction; the live tree is protected from that state by
        test_the_operator_identity_is_derived_and_non_empty, not by hope."""
        v = self._tree(tmp_path, {}, fw={"m.py": "# anybody at all\n"})
        assert v == {}
        assert scan_person_literals(tmp_path / "framework", vocabulary=v,
                                    rel_to=tmp_path) == []

    def test_a_path_that_names_the_operator_is_flagged(self, tmp_path):
        """A directory or a file NAMED after the operator publishes the name as
        widely as a line inside it does, and a content-only scan called that
        tree green. Lopsided on purpose: two named paths whose CONTENT is
        spotless are found, and a clean path beside them is not — so the arm
        cannot pass by flagging everything."""
        v = self._tree(tmp_path, {"LICENSE": "Copyright (c) 2026 Quillon Marrowby\n"},
                       fw={"marrowby/helper.py": "x = 1\n",
                           "docs/Quillon-fixture.md": "nothing to see\n",
                           "clean/ok.py": "x = 1\n"})
        f = scan_person_literals(tmp_path / "framework", vocabulary=v, rel_to=tmp_path)
        assert ("framework/marrowby/helper.py", 0, "marrowby") in f
        assert ("framework/docs/Quillon-fixture.md", 0, "quillon") in f
        assert [x for x in f if x[0] == "framework/clean/ok.py"] == []

    def test_the_subject_directory_name_is_not_itself_a_finding(self, tmp_path):
        """Why the path is matched relative to the SCAN ROOT and not to the
        display base: an operator whose declared identity happens to contain
        the subject directory's own name would otherwise red every file in the
        tree, on a tree that names nobody."""
        v = self._tree(tmp_path, {"LICENSE": "Copyright (c) 2026 Framework Marrowby\n"},
                       fw={"m.py": "x = 1\n"})
        assert "framework" in v, "the fixture never derived the colliding token"
        assert scan_person_literals(tmp_path / "framework", vocabulary=v,
                                    rel_to=tmp_path) == []

    def test_a_surface_that_stops_declaring_narrows_the_arm_silently(self, tmp_path):
        """Item 9, pinned in BOTH directions because it is the failure this
        gate is least able to notice about itself: the non-vacuity floor is on
        the UNION, so a surface going quiet costs real teeth while every arm
        stays green. Before: the owner handle contributes a token no licence
        derives, and a line carrying it is found. After a fork/org retarget:
        the token is gone, the same line passes, and the vocabulary is still
        non-empty — so nothing anywhere reports the loss."""
        v = self._tree(tmp_path, {
            "LICENSE": "Copyright (c) 2026 Quillon Marrowby\n",
            ".claude-plugin/plugin.json":
                '{"homepage": "https://github.com/quill-marrowby/some-repo"}\n'},
            fw={"m.py": "# ask Quill before shipping\n"})
        assert scan_person_literals(tmp_path / "framework", vocabulary=v,
                                    rel_to=tmp_path) == [("framework/m.py", 1, "quill")]
        self._write(tmp_path / ".claude-plugin" / "plugin.json",
                    '{"homepage": "https://github.com/zzq-x1/some-repo"}\n')
        v2 = derive_operator_identity(tmp_path)
        assert "quill" not in v2, "the fixture never retargeted the handle"
        assert v2, "the union floor must still pass — that is what makes it silent"
        assert scan_person_literals(tmp_path / "framework", vocabulary=v2,
                                    rel_to=tmp_path) == []

    def test_a_symlink_escape_is_refused_not_followed(self, tmp_path):
        v = self._tree(tmp_path, {"LICENSE": "Copyright (c) 2026 Quillon Marrowby\n"},
                       fw={"m.py": "ok\n"})
        outside = tmp_path / "outside.py"
        outside.write_text("# Quillon\n", encoding="utf-8")
        try:
            os.symlink(str(outside), str(tmp_path / "framework" / "link.py"))
        except (OSError, NotImplementedError):  # pragma: no cover — no symlink support
            return
        f = scan_person_literals(tmp_path / "framework", vocabulary=v, rel_to=tmp_path)
        assert ("framework/link.py", 0, "symlink escape — refused") in f


# CLI mode: `python3 framework/tests/test_no_launcher_hardcode.py` prints every
# offender and exits non-zero — usable under the system python without pytest.
if __name__ == "__main__":  # pragma: no cover
    import sys

    argv = sys.argv[1:]
    mode = argv[0] if argv else "--check"
    if mode not in ("--check", "--report", "--update-baseline"):
        print("usage: test_no_launcher_hardcode.py [--check|--report|--update-baseline]")
        sys.exit(2)

    # The same subject floor the pytest arm enforces, so the CLI can never
    # print OK over a scan that visited nothing (see _SPECIFICS_SCAN_FLOOR).
    _visited = sum(1 for _ in iter_specifics_files(_REPO_ROOT / "framework"))
    if _visited < _SPECIFICS_SCAN_FLOOR:
        print("FAIL: the specifics scan visited only %d files (floor %d) — the "
              "walk is broken; a SUBSET check over an empty finding set is "
              "green no matter what the tree contains" % (_visited, _SPECIFICS_SCAN_FLOOR))
        sys.exit(1)

    # Arm 3's own two floors, for the same reason: an empty finding set is the
    # green a broken walk and an underived identity both print.
    _pvisited = sum(1 for _ in iter_person_files(_REPO_ROOT / "framework"))
    if _pvisited < _PERSON_SCAN_FLOOR:
        print("FAIL: the person scan visited only %d files (floor %d) — the walk "
              "is broken; an EMPTY finding set is green no matter what the tree "
              "contains" % (_pvisited, _PERSON_SCAN_FLOOR))
        sys.exit(1)
    identity = derive_operator_identity(_REPO_ROOT)
    if not identity:
        print("FAIL: no operator identity could be derived (licence holder, "
              "owner handle, instance declaration all empty) — PERSON_LITERAL "
              "is inert while still reporting green")
        sys.exit(1)

    offenders = scan_tree(_REPO_ROOT / "framework", rel_to=_REPO_ROOT)
    vocabulary = derive_vendor_vocabulary(_REPO_ROOT)
    specifics = scan_specifics(_REPO_ROOT / "framework", vocabulary=vocabulary,
                               rel_to=_REPO_ROOT)
    persons = scan_person_literals(_REPO_ROOT / "framework", vocabulary=identity,
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

    for path, line, token in persons:
        print("arm3 %s:%d  PERSON_LITERAL  %s  (declared by: %s)"
              % (path, line, token, identity.get(token, "symlink containment")))

    bad = bool(offenders) or bool(new_specifics) or bool(persons)
    if offenders:
        print("FAIL (arm1): %s" % _HINT)
    if new_specifics:
        print("FAIL (arm2): %s" % _SPECIFICS_HINT)
    if persons:
        print("FAIL (arm3): %s" % _PERSON_HINT)
    if not bad:
        print("OK: framework/ is launcher-agnostic, carries no NEW specific "
              "(%d known debt keys over %d occurrences, cap %d; vocabulary %d "
              "derived labels) and names no person (%d identity tokens derived "
              "over %d files)"
              % (len({specifics_key(f) for f in specifics}), len(specifics),
                 _SPECIFICS_BASELINE_MAX, len(vocabulary), len(identity), _pvisited))
    sys.exit(1 if (bad and mode != "--report") else 0)
