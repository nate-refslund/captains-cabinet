"""The clean-room SOURCE ratchet — framework/ CORE may not name screenpipe [SRC-5].

Source-adapter build: ``framework/`` is the universal base for any captain and
either flavor, so it must reach the captain's personal estate ONLY through the
launcher-neutral seam ``framework.sources.get_source()`` — never through a
screenpipe ``_shared`` lib import nor a ``~/.screenpipe`` / vault path literal.
A clean-room / Flavor-B box that binds ``NullPersonalSource`` (or an org source)
must be able to run the whole framework with no ``~/.screenpipe`` and no vault.

This module is the RATCHET that keeps it that way — the THIRD member of the same
family as ``test_no_launcher_hardcode.py`` (launcher identity) and
``test_axes_contract.py`` (axis branches). It text-walks every
``framework/**/*.py`` and goes RED on a screenpipe coupling that is not covered
by the documented, shrink-only allowlist below. After the seam migration lands,
a NEW screenpipe import / path in ``framework/`` is a CI failure — not a review
note. The end state is an EMPTY allowlist: the only code in the repo that may
name screenpipe lives in ``instance/flavor-a/``.

Design mirrors ``test_no_launcher_hardcode.py`` exactly: stdlib-only,
``import pytest`` guarded so it also runs under the system python, symlink-escape
refused via ``os.path.realpath`` containment (a file resolving outside the
scanned tree is itself a violation), and read-ONLY (files are ``read_text``
scanned, never imported or executed) — a text-walk, not an AST parse, so a
future-syntax file can never make the ratchet itself crash.

Two coupling families are detected, both on the CODE PORTION of each line
(comments and triple-quoted docstring/string BLOCKS are masked out first, so the
many legitimate screenpipe *mentions* in framework docstrings/comments — the
vendoring note in ``voice_charset.py``, the clean-room comment in ``retro.py``,
the ``_shared/.env`` docstring in ``probes/runner.py`` — never trip it; single
-line string CONTENTS are KEPT, because a runtime path literal lives inside one):

  * IMPORT — a line importing one of the screenpipe ``_shared`` libs
    (``draft_lib`` / ``commitments_lib`` / ``context_lib`` / ``me_signal`` /
    ``sp_lib`` / ``product_ops_lib`` / ``email_lib`` / ``teams_graph_lib`` /
    ``agent_reasoning``). Anchored to ``^\\s*(import|from)`` so it flags a real
    import, not a string that happens to contain the name, and — crucially — it
    does NOT flag importing the FRAMEWORK module ``framework.acting
    .screenpipe_adapter`` (an internal module, not a ``_shared`` lib): that is an
    indirect coupling the callers (``binder_wire`` / ``morning_synthesis``) shed
    when SRC-3 repoints them; the real coupling lives in the adapter file itself,
    which IS on the allowlist.
  * PATH — a runtime line constructing ``~/.screenpipe`` (or a ``".screenpipe"``
    Path component), ``screenpipe-brain`` (the vault dir), or ``OBSIDIAN_VAULT``
    (the vault env key). ``\\.screenpipe\\b`` is word-bounded so it flags
    ``".screenpipe"`` / ``~/.screenpipe/`` but NOT ``.screenpipe_adapter`` (the
    framework module).

Scope carve-outs (NOT scanned): ``framework/sources/`` — the seam package NAMES
the Protocol and describes the Flavor-A mapping in its docstrings; it is the one
place framework may say "screenpipe" (in prose), so it is excluded structurally,
exactly as ``instance/`` (where screenpipe belongs) is out of ``framework/``
entirely. ``tests/`` dirs, ``__pycache__``, and ``test_*`` / ``*_test.py`` are
skipped like the sister ratchet (fixtures legitimately carry the tokens).
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

# The screenpipe `_shared` libs framework CORE must never import directly (it
# reaches their data through framework.sources.get_source()). Anchored at line
# start so `import X` / `from X import ...` (incl. `as` aliases) match, but a
# string mentioning the name does not, and the FRAMEWORK module
# `screenpipe_adapter` (not in this list) is deliberately NOT caught.
_SHARED_LIBS: Tuple[str, ...] = (
    "draft_lib", "commitments_lib", "context_lib", "me_signal", "sp_lib",
    "product_ops_lib", "email_lib", "teams_graph_lib", "agent_reasoning",
)
_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+(%s)\b" % "|".join(_SHARED_LIBS))

# Runtime screenpipe path literals. `\.screenpipe\b` matches a `.screenpipe`
# Path component (`".screenpipe"`) or expanduser form (`~/.screenpipe/`) but the
# word boundary refuses `.screenpipe_adapter` (the framework module). The vault
# dir + env key round it out. Scanned on the masked code portion, so a mention
# inside a comment/docstring never trips.
_PATH_RE = re.compile(r"\.screenpipe\b|screenpipe-brain|OBSIDIAN_VAULT")

Violation = Tuple[str, int, str]  # (display_path, line_no, reason)


# ===========================================================================
# THE ALLOWLIST  (repo-relative posix paths).  EMPTY — the end state.
# ===========================================================================
#
# EMPTY — the P2-FLIP end state (SRC-5, 2026-07-06). Every Tier-1/Tier-2 coupler
# from the §3 census (docs/plans/source-adapter-boundary-2026-07-05.md) has been
# migrated off framework/: the screenpipe BODIES re-homed to
# instance/flavor-a/flavor_a/, every state/credential/vault PATH reparented to a
# framework.env resolver. What moved where (documentation, not entries):
#
#   * officer_runner.BrainAdapter  → instance/flavor-a/flavor_a/screenpipe_source
#     .py::ScreenpipeSource. The leak-fence (gather_cutoff_context) stays ABOVE
#     the adapter, in framework, in-process — it now defaults brain=get_source().
#   * acting/screenpipe_adapter.py → instance/flavor-a/flavor_a/acting.py; the
#     callers' pure loop-plumbing folded into framework.acting.lane_dedup.
#   * _vault_gather_runner.py (the py3.12 vault-search sidecar) re-homed WITH the
#     adapter to instance/flavor-a/flavor_a/.
#   * frontdoor egress (chair_drafts/daily_recap SEND + the vault daily-note
#     write) → instance/flavor-a/flavor_a/screenpipe_dispatch.py::ScreenpipeDispatch,
#     reached via framework.sources.get_dispatch() (daily-note golden hash kept).
#   * Tier-2 state/credential/vault PATHS (decision_cell / benchmark /
#     run_e2e_smoke / registry / retro / action_exec / actfirst_canary) →
#     framework.env.vault_dir() / state_dir() / shared_env_path() /
#     retro_pipe_dir() (instance-config-bound, byte-identical on this instance).
#     The two HOT-lane files (run_action_lane / run_draft_lane) reparent the same
#     way under SRC-4 (P2-ACT — the acting lane, behind its own draft-lane test
#     gate + byte-identity proof); once that reparent lands the main ratchet is
#     green with this empty allowlist. Until then it flags exactly those two —
#     the honest cross-lane signal, NOT a re-allowlist candidate.
#
# The doctrine now physically holds: the ONLY code in the repo that may name
# screenpipe lives in instance/flavor-a/ — never in framework/. framework/ CORE
# reaches the captain's estate ONLY through framework.sources.get_source() /
# get_dispatch(). The allowlist MUST stay empty: a NEW screenpipe `_shared`
# import or a ~/.screenpipe / vault PATH literal in framework/** is fixed by
# routing through the seam (or re-homing to instance/flavor-a) — NEVER by
# re-adding an entry here. The self-test `test_allowlisted_files_still_couple`
# still guards that any (future) entry must ACTUALLY couple, so a vacuous re-add
# is itself CI-red; the main ratchet is the strong gate on any uncovered coupling.
_ALLOWLISTED_FILES: Dict[str, str] = {}

# Shrink-only cap: the allowlist may only ever get SMALLER. The target is
# REACHED — 0 (framework/** names screenpipe nowhere). Raising it is forbidden —
# a NEW screenpipe coupling is fixed by routing through get_source(), never by
# widening this. The full ratchet-down lineage:
#   14 → 11  SRC-3 (P2-REHOME): officer_runner + _vault_gather_runner +
#            screenpipe_adapter re-homed to instance/flavor-a/ (fully decoupled).
#   11 →  8  SRC-4-germline + SRC-6 (P2-GERM + RETRO): action_exec +
#            actfirst_canary credential path → env.shared_env_path(); retro.py
#            scoring-lib path → env.retro_pipe_dir() (byte-identical here).
#    8 →  4  SRC-4 (P2-COLD): decision_cell + benchmark + run_e2e_smoke +
#            registry Tier-2 state/vault paths → env.state_dir()/vault_dir()
#            (+ the get_source().available() embeddings gate).
#    4 →  2  SRC-3 (P2-FRONT): chair_drafts + daily_recap frontdoor egress
#            re-homed to instance/flavor-a via get_dispatch() (golden hash kept).
#    2 →  0  SRC-5 / P2-FLIP: the allowlist FLIPS to empty (the end state). The
#            last two couplers — run_action_lane + run_draft_lane HOT-lane
#            ~/.screenpipe / vault PATH residuals — reparent to env.vault_dir()/
#            shared_env_path() under SRC-4 (P2-ACT, the acting lane, byte-identical
#            behind its draft-lane test gate); the main ratchet goes green the
#            moment that reparent lands. The baseline is 0 NOW — the surface can
#            only ever be empty; a residual is fixed at its source, never re-added.
_ALLOWLIST_BASELINE_MAX = 0


_HINT = ("framework/ CORE must reach the captain's estate only through "
         "framework.sources.get_source() — a screenpipe _shared import or a "
         "~/.screenpipe / vault path literal in framework/** is CI-red (the "
         "adapter that names screenpipe lives in instance/flavor-a/). See "
         "docs/plans/source-adapter-boundary-2026-07-05.md §7.")


# ---------------------------------------------------------------------------
# Code-portion masker (comments + triple-quoted BLOCKS removed; single-line
# string CONTENTS kept — a runtime path literal lives inside one). A best-effort
# text scanner (no ast/tokenize) so it stays parse-safe under the system python
# for any file, mirroring the sister ratchet's read-only text-walk.
# ---------------------------------------------------------------------------
def _code_portions(text: str) -> List[str]:
    """Return, per source line, the code portion with ``#`` comments (outside a
    string) dropped and triple-quoted string/docstring BLOCK interiors blanked,
    while ``'...'`` / ``"..."`` single-line string CONTENTS are preserved."""
    out: List[str] = []
    in_triple: Optional[str] = None  # the open triple delimiter, or None
    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        n = len(line)
        buf: List[str] = []
        j = 0
        if in_triple is not None:
            idx = line.find(in_triple)
            if idx == -1:
                out.append("")            # whole line inside a triple block
                continue
            j = idx + 3                    # resume as code after the close
            in_triple = None
        sq: Optional[str] = None           # single-line string delimiter, or None
        while j < n:
            c = line[j]
            if sq is not None:             # inside a single-line string: keep chars
                buf.append(c)
                if c == "\\" and j + 1 < n:
                    buf.append(line[j + 1])
                    j += 2
                    continue
                if c == sq:
                    sq = None
                j += 1
                continue
            two = line[j:j + 3]
            if two == '"""' or two == "'''":
                idx = line.find(two, j + 3)
                if idx == -1:              # opens a multi-line block; stop this line
                    in_triple = two
                    break
                j = idx + 3                # single-line triple string: blank interior
                continue
            if c == "#":                   # comment to end of line
                break
            if c == '"' or c == "'":
                sq = c
                buf.append(c)
                j += 1
                continue
            buf.append(c)
            j += 1
        out.append("".join(buf))
    return out


def _line_violations(code: str) -> List[str]:
    """Every screenpipe-coupling reason that fires on one code-portion line."""
    out: List[str] = []
    mi = _IMPORT_RE.search(code)
    if mi:
        out.append("imports screenpipe _shared lib '%s' — route through "
                   "framework.sources.get_source()" % mi.group(1))
    mp = _PATH_RE.search(code)
    if mp:
        out.append("screenpipe path literal '%s' — belongs in instance/flavor-a, "
                   "not framework/" % mp.group(0))
    return out


def _text_couples(text: str) -> bool:
    """True if any code-portion line of ``text`` carries a screenpipe coupling."""
    return any(_line_violations(code) for code in _code_portions(text))


# ---------------------------------------------------------------------------
# Tree walk (tests/ + __pycache__ + test_ files + the sources/ seam skipped;
# symlink-escape refused via realpath containment)
# ---------------------------------------------------------------------------
def iter_source_files(root: Path) -> Iterator[Path]:
    for p in sorted(Path(root).rglob("*.py")):
        parts = p.relative_to(root).parts
        if "__pycache__" in parts:
            continue
        if "tests" in parts[:-1]:                 # any tests/ DIRECTORY segment
            continue
        if parts and parts[0] == "sources":       # framework/sources = the seam
            continue
        if p.name.startswith("test_") or p.name.endswith("_test.py"):
            continue
        yield p


def scan_tree(
    root,  # type: str | Path
    files_allowlist=None,  # type: Optional[Dict[str, str]]
    rel_to=None,  # type: Optional[str | Path]
) -> List[Violation]:
    """Read-only scan of every non-test .py under ``root`` (excluding the
    ``sources/`` seam) for a screenpipe coupling (a ``_shared`` import or a
    ``~/.screenpipe`` / vault path literal) outside ``files_allowlist``.

    ``files_allowlist`` maps a whole (rel_to-relative) path to a justification;
    it defaults to the module allowlist, but the engine self-tests inject their
    own so they stay hermetic. Symlink escapes are reported, never followed
    (Corridor: realpath containment); an unreadable file fails closed."""
    root = Path(root)
    base = Path(rel_to) if rel_to is not None else root
    files_allowlist = _ALLOWLISTED_FILES if files_allowlist is None else files_allowlist
    real_root = os.path.realpath(str(root))
    violations: List[Violation] = []
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
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:  # unreadable -> fail-closed, mirror sister ratchet
            violations.append((display, 0, "unreadable: %s" % e))
            continue
        for i, code in enumerate(_code_portions(text), 1):
            for reason in _line_violations(code):
                violations.append((display, i, reason))
    return violations


# ---------------------------------------------------------------------------
# The ratchet + its self-tests
# ---------------------------------------------------------------------------
class TestNoScreenpipeInCore:
    def test_framework_core_has_no_screenpipe_coupling(self):
        """THE RATCHET: no screenpipe `_shared` import and no `~/.screenpipe` /
        vault path literal in framework/** outside the shrink-only allowlist."""
        violations = scan_tree(_REPO_ROOT / "framework", rel_to=_REPO_ROOT)
        assert violations == [], (
            "%s\nOffenders: %s"
            % (_HINT, ["%s:%d (%s)" % (v[0], v[1], v[2]) for v in violations]))


class TestAllowlistDiscipline:
    def test_every_allowlisted_path_exists(self):
        """No dead allowlist paths — a stale entry is a silent hole."""
        missing = [rel for rel in _ALLOWLISTED_FILES
                   if not (_REPO_ROOT / rel).exists()]
        assert missing == [], "allowlist references non-existent files: %s" % missing

    def test_allowlisted_files_still_couple(self):
        """Shrink forcing-function: an allowlisted file that no longer couples to
        screenpipe has been migrated and MUST have its entry deleted (the
        allowlist may only shrink). Re-scan every path with NO allowlist and
        require it still flags — the moment a caller routes through get_source()
        (or is re-homed to instance/flavor-a), its entry goes vacuous and this
        goes RED."""
        flagged = {v[0] for v in scan_tree(
            _REPO_ROOT / "framework", files_allowlist={}, rel_to=_REPO_ROOT)}
        vacuous = [rel for rel in sorted(_ALLOWLISTED_FILES) if rel not in flagged]
        assert vacuous == [], (
            "these framework files no longer couple to screenpipe — DELETE their "
            "allowlist entries (the allowlist may only shrink): %s" % vacuous)

    def test_allowlist_only_shrinks(self):
        """Intent lock: the allowlist may only SHRINK. Admitting a new coupler
        past the baseline is forbidden — route it through get_source() instead of
        widening. The baseline itself may only be lowered."""
        assert len(_ALLOWLISTED_FILES) <= _ALLOWLIST_BASELINE_MAX, (
            "screenpipe allowlist grew (%d > %d) — %s"
            % (len(_ALLOWLISTED_FILES), _ALLOWLIST_BASELINE_MAX, _HINT))


class TestScannerEngine:
    """Hermetic proofs that the engine itself is trustworthy (own tmp trees +
    injected empty allowlists — never the real framework allowlist)."""

    @staticmethod
    def _write(p: Path, body: str) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    def test_flags_shared_lib_import(self, tmp_path):
        self._write(tmp_path / "pkg" / "m.py",
                    "import draft_lib as dl  # lazy screenpipe dep\n")
        v = scan_tree(tmp_path, files_allowlist={})
        assert len(v) == 1 and "draft_lib" in v[0][2] and "get_source" in v[0][2]

    def test_flags_from_import(self, tmp_path):
        self._write(tmp_path / "pkg" / "m.py", "from commitments_lib import load_all\n")
        v = scan_tree(tmp_path, files_allowlist={})
        assert len(v) == 1 and "commitments_lib" in v[0][2]

    def test_flags_screenpipe_path_forms(self, tmp_path):
        # all four runtime forms: expanduser tilde, Path-component, vault dir,
        # env key — each on its own line.
        self._write(tmp_path / "pkg" / "m.py",
                    'A = os.path.expanduser("~/.screenpipe/pipes")\n'
                    'B = Path.home() / ".screenpipe" / "state"\n'
                    'C = "Obsidian" / "screenpipe-brain"\n'
                    'D = os.environ.get("OBSIDIAN_VAULT_PATH")\n')
        v = scan_tree(tmp_path, files_allowlist={})
        assert [r[1] for r in v] == [1, 2, 3, 4]
        assert all("instance/flavor-a" in r[2] for r in v)

    def test_ignores_comment_mentions(self, tmp_path):
        # a `#` comment naming screenpipe libs + a ~/.screenpipe path must stay
        # green (post-migration measure_intent.py shape).
        self._write(tmp_path / "pkg" / "m.py",
                    "x = 1  # was: import context_lib from ~/.screenpipe/pipes\n"
                    "# sys.path.insert(0, '~/.screenpipe/pipes/_shared')\n")
        assert scan_tree(tmp_path, files_allowlist={}) == []

    def test_ignores_docstring_mentions(self, tmp_path):
        # module + interior docstring lines naming a lib and a path (the
        # voice_charset.py / probes/runner.py INERT shape) must stay green.
        self._write(tmp_path / "pkg" / "m.py",
                    '"""Vendored from ~/.screenpipe/pipes/_shared/voice_charset.py.\n'
                    '\n'
                    'Maps to context_lib.gather + draft_lib.person_intel; reads\n'
                    'OBSIDIAN_VAULT_PATH under ~/.screenpipe. ZERO runtime deps.\n'
                    '"""\n'
                    'CHARSET = "utf-8"\n')
        assert scan_tree(tmp_path, files_allowlist={}) == []

    def test_ignores_framework_adapter_module(self, tmp_path):
        # importing / referencing the FRAMEWORK module screenpipe_adapter is NOT a
        # `_shared` coupling and `.screenpipe_adapter` is not a path literal — the
        # binder_wire / morning_synthesis indirect shape stays green.
        self._write(tmp_path / "pkg" / "m.py",
                    "from framework.acting.screenpipe_adapter import normalize_voice\n"
                    "import framework.acting.screenpipe_adapter as spa\n"
                    "spa = framework.acting.screenpipe_adapter.gather\n")
        assert scan_tree(tmp_path, files_allowlist={}) == []

    def test_ignores_unrelated_lookalikes(self, tmp_path):
        # a different lib, a /usr path, and the bare word screenpipe in an
        # identifier without a leading-dot boundary must all stay green.
        self._write(tmp_path / "pkg" / "m.py",
                    "import json\n"
                    "P = '/usr/local/share/pipes'\n"
                    "name = 'myscreenpipeclient'\n")
        assert scan_tree(tmp_path, files_allowlist={}) == []

    def test_whole_file_allowlist_skips(self, tmp_path):
        self._write(tmp_path / "pkg" / "m.py", "import draft_lib\n")
        assert scan_tree(tmp_path, files_allowlist={"pkg/m.py": "ok, migrating"}) == []

    def test_skips_tests_dirs_and_test_files(self, tmp_path):
        self._write(tmp_path / "pkg" / "tests" / "test_x.py", "import draft_lib\n")
        self._write(tmp_path / "pkg" / "test_top.py", "import draft_lib\n")
        self._write(tmp_path / "pkg" / "conftest_x_test.py", "import me_signal\n")
        self._write(tmp_path / "pkg" / "__pycache__" / "c.py", "import sp_lib\n")
        assert scan_tree(tmp_path, files_allowlist={}) == []

    def test_skips_sources_seam_package(self, tmp_path):
        # framework/sources/ names the Protocol + describes the Flavor-A mapping
        # in docstrings; it is excluded structurally (like the sister skips
        # tests/), so a top-level sources/ dir is never scanned.
        self._write(tmp_path / "sources" / "base.py",
                    'CALL = context_lib.gather  # doc: ~/.screenpipe\nimport draft_lib\n')
        assert scan_tree(tmp_path, files_allowlist={}) == []

    def test_symlink_escape_is_refused(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.py").write_text("import draft_lib\n", encoding="utf-8")
        root = tmp_path / "root"
        root.mkdir()
        link = root / "link.py"
        try:
            link.symlink_to(outside / "secret.py")
        except (OSError, NotImplementedError):  # pragma: no cover — FS w/o symlinks
            if pytest is not None:
                pytest.skip("symlinks unsupported on this filesystem")
            return
        v = scan_tree(root, files_allowlist={})
        assert any("symlink escape" in r[2] for r in v)


# CLI mode: `python3 framework/tests/test_no_screenpipe_in_core.py` prints every
# offender and exits non-zero — usable under the system python without pytest.
if __name__ == "__main__":  # pragma: no cover
    import sys
    offenders = scan_tree(_REPO_ROOT / "framework", rel_to=_REPO_ROOT)
    for d, i, why in offenders:
        print("%s:%d  %s" % (d, i, why))
    print(("FAIL: %s" % _HINT) if offenders
          else "OK: framework/ CORE names no screenpipe (routes through get_source())")
    sys.exit(1 if offenders else 0)
