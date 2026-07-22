#!/usr/bin/env python3.12
"""cog2-import-gate.py — the COG-2 shadow-boundary import gate (contract §7.1).

Mechanically enforces M5 ("zero calls from authority/action code"): NO module on
the authority/action surface may import framework.cortex, and the shadow-parity
falsifier may import NO cortex module at all (C-F17). Detection is a stdlib-`ast`
import-graph walk (precise, string-literal-blind) PLUS a grep backstop that
catches what an AST walk cannot — a dynamic `importlib.import_module(...)` or a
data-plane `open("cabinet/cache/cortex/...")` bypass (C-F20).

This mirrors the check-layer-separation.sh IDIOM (a tree scan, comment-safe
filtering, report/check/json modes, exit 1 on any new breach) but expresses an
INTRA-framework deny rule that check-layer-separation.sh structurally cannot —
that script only covers framework -> instance/presets coupling (per contract
§3 / O-B6, the "layer-sep idiom" characterization is withdrawn; this gate is
net-new).

COG-3 EXTENSION (Phase-3 contract §6.5, additive + byte-compatible): the same
gate now also fences the objectives graph (framework.objectives), a SECOND
shadow model. Authority/action code may not import it (FORBIDDEN_IMPORTS_OBJECTIVES
/ FORBIDDEN_OBJECTIVES_TOKEN); a framework/objectives/ file may not import the
action plane (FORBIDDEN_OBJECTIVES_IMPORTS_ACTION — the reverse direction); any
un-curated swept importer of framework.objectives REDs (UNALLOWLISTED_OBJECTIVES_IMPORTER
— how framework/missions consuming the graph is caught); and a live reference
to the objectives cache store anywhere in SWEEP_TREES REDs (FORBIDDEN_OBJECTIVES_DATAPLANE
— the non-covert data-plane read the import sweep cannot see). This gate stays
MODULE-granular; the narrow SYMBOL rule (which cortex names framework/objectives/
may import) is a separate net-new AST pin (test_cog3_objectives_ast_pin.py). All
COG-3 rules are green-by-vacuity until framework/objectives/ + the cog3 files land.

Baseline-zero, shrink-only: the accepted-violation set is EMPTY. Any violation
fails the gate. The forbidden surface only ever grows (a protection never
shrinks); the allowlist is the curated set of legitimate cortex readers.

RULES — one `<repo-relative-path>:<RULE>` per violation:
  FORBIDDEN_IMPORTS_CORTEX       an authority/action module imports framework.cortex —
                                 ANY spelling: `import framework.cortex`,
                                 `from framework.cortex import x`, the ordinary
                                 `from framework import cortex [as c]` (alias name), or
                                 a relative `from ..cortex import x` / `from .. import
                                 cortex` that RESOLVES to framework.cortex
  FORBIDDEN_CORTEX_TOKEN         a forbidden-tree file names framework.cortex, the
                                 `from framework import cortex` line, or the
                                 cabinet/cache/cortex store on a live (non-comment)
                                 line — the dynamic-import / data-plane backstop
  FALSIFIER_IMPORTS_CORTEX       cog2-parity-falsifier.py reaches ANY cortex module —
                                 static, `from framework import cortex`, or a dynamic
                                 import_module/__import__ of framework.cortex (C-F17 —
                                 the parity ground truth must never route through
                                 cortex's own adapters)
  UNALLOWLISTED_CORTEX_IMPORTER  a module in ANY swept first-party tree (framework/,
                                 shared/, instance/, presets/, the cabinet code
                                 subtrees + the repo-root conftest — see SWEEP_TREES)
                                 imports framework.cortex — statically or via a dynamic
                                 import_module — but is neither cortex-internal nor a
                                 curated cortex reader

FORBIDDEN authority/action surface (§7.1 / M5 — the "frontdoor / acting /
authority / action lanes / officer runners / live-verb scripts" set):
  framework/frontdoor/**                  the live front door + live-verb execution
  framework/acting/**                     capture->action lanes and their runners
  framework/authority/**                  authority / grant / policy / classifier
  framework/fidelity/officer_runner.py    the live officer runner
Plus the special importer:
  cabinet/scripts/cog2-parity-falsifier.py   (C-F17 — must import NO cortex)

ALLOWLIST (legitimate framework.cortex readers — the only modules that may):
  framework/cortex/**                     own package (internal)
  cabinet/scripts/cog2-rebuild.py         rebuild CLI
  cabinet/scripts/cog2-belief-hash.py     hash instrument
  cabinet/scripts/cog2-verifier.py        shadow verifier (query-only reader)
  cabinet/scripts/tests/test_cog2_*.py    the COG-2 test suites
  cabinet/scripts/tests/lib_cog2_*.py     COG-2 test libraries

The comment-safe filter (like check-layer-separation.sh) drops pure `#` comment
lines and triple-quote delimiter lines; a live line NAMING the cortex module or
its cache store inside a forbidden tree is treated as a coupling by design —
authority/action code has no business referencing the shadow model, even in a
docstring body.

Sweep coverage (§7.1 — the closed bridge-escape): Check 3's SWEEP_TREES covers
EVERY first-party importable Python tree, so a PLAIN greppable cortex import is
never invisible, wherever it lives. A prior gap swept only framework/ +
cabinet/{scripts,admin-bot,mcp-server}, omitting shared/, instance/, presets/,
cabinet/{adapters,channels,companion} (and cabinet/{evals,fixtures}, the repo-root
conftest.py): a stray `from framework.cortex import query` there exited rc=0,
letting authority/action code reach the shadow model through a one-hop bridge
(authority file -> `from shared.cortex_bridge import query`; the bridge ->
`from framework.cortex import query`). Now the bridge file — living in a swept
tree — is itself flagged, so the reach can never be silent.

EXCLUDED trees (named per the fail-closed rule — none is an importable Python
namespace, so no import statement can hide in them): the non-code top-level trees
designs/, docs/, memory/, packs/, patches/, vault/ (design assets, markdown,
data, asset packs, patch files, the Obsidian vault) and the cabinet non-code
subtrees cache/, config/, cron/, dashboard/, deploy/, docs/, env/, launchd/,
logs/, loop-prompts/, mcp-overlays/, migrations/, officer-skills/, runbooks/,
sql/, starter-spaces/, tests/, world/ (data, config, plists, logs, SQL, assets,
prompt/skill markdown). They carry NO .py today. If Python is ever added to any
of them it MUST be added to SWEEP_TREES — the completeness-invariant test
(test_every_first_party_py_is_on_scan_surface) fails loudly until it is, so this
class of omission cannot recur silently.

Residuals (§7.1 — accepted for this phase, read pointer `none`):
(1) TRANSITIVE attribution. The gate is a per-file DIRECT-import detector, not a
    transitive import-graph analyzer. A multi-hop chain (authority -> bridge_a ->
    bridge_b -> cortex) is caught at whichever file LITERALLY imports cortex —
    always a swept first-party file now — so the ultimate authority caller can
    name no cortex token yet the reach is NEVER silent (the importing bridge is
    flagged). What stays out of scope is only attribution: the gate flags the
    importer, not every transitive caller upstream of it.
(2) FULLY covert assembly. A bypass whose module name never appears as a greppable
    literal — a runtime string-assembled `import_module('framework' + '.cortex')`,
    or a getattr/attribute walk — stays out of scope (no AST import node, no
    greppable token). Revisited when the read pointer flips off `none`.
The two-argument RELATIVE dynamic form (a dot-cortex name handed to import_module
with a 'framework' package) is NOT residual: it bites on the falsifier via the
narrow dynamic ban and across the swept trees via the precise two-arg pattern.

Usage:
  python3.12 cabinet/scripts/cog2-import-gate.py            # check: exit 1 on breach
  python3.12 cabinet/scripts/cog2-import-gate.py --report   # list all, exit 0
  python3.12 cabinet/scripts/cog2-import-gate.py --json     # machine-readable
  python3.12 cabinet/scripts/cog2-import-gate.py --root PATH # scan another tree

Provenance: authored + self-ratified per the 2026-07-07 full-autonomy grant +
the 2026-07-20 cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import sys
from pathlib import Path

CORTEX = "framework.cortex"
# COG-3 (Phase-3 contract §6.5): the objectives graph is a SECOND shadow model
# with the SAME both-directions boundary — the authority/action surface may not
# import it, and it may read the cortex query surface but never the action plane.
# Enforced beside the cortex rules below; the symbol-level narrowing (which
# cortex symbols framework/objectives/ may import) is a SEPARATE net-new AST pin
# (test_cog3_objectives_ast_pin.py) — this module gate is path-granular only.
OBJECTIVES = "framework.objectives"

# --- forbidden authority/action surface (§7.1 / M5) -------------------------
# Also the ACTION-PLANE trees framework/objectives/ may NEVER import (§6.5
# reverse direction): the graph reads the cortex, never frontdoor/acting/authority.
FORBIDDEN_TREES = [
    "framework/frontdoor",
    "framework/acting",
    "framework/authority",
]
FORBIDDEN_FILES = [
    "framework/fidelity/officer_runner.py",
]
FALSIFIER = "cabinet/scripts/cog2-parity-falsifier.py"

# --- legitimate cortex readers ---------------------------------------------
CORTEX_INTERNAL = "framework/cortex/"
ALLOWLIST_EXACT = {
    "cabinet/scripts/cog2-rebuild.py",
    "cabinet/scripts/cog2-belief-hash.py",
    "cabinet/scripts/cog2-verifier.py",
}
ALLOWLIST_GLOBS = [
    "cabinet/scripts/tests/test_cog2_*.py",
    "cabinet/scripts/tests/lib_cog2_*.py",
]

# --- trees the global sweep (Check 3) scans for ANY stray cortex importer -----
# Must cover EVERY first-party importable Python tree so a plain
# `from framework.cortex import x` is never invisible, wherever it lives — the
# closed bridge-escape (a stray import in shared/instance/presets/cabinet-code
# lanes used to slip the net; see §7.1). Audited to enumerate ALL first-party
# .py in the repo (the completeness-invariant test guards 0-uncovered). The
# empty namespaces (shared, cabinet/{adapters,channels,companion}) carry no .py
# today but are swept as a forward-guard; conftest.py is the repo-root importable
# pytest fence (a file, which _py_files handles). Non-code trees are excluded by
# design — named in the §7.1 residual note above.
SWEEP_TREES = [
    "framework",          # the whole framework layer (authority/action + all)
    "shared",             # first-party bridge/interface namespace (the escape route)
    "instance",           # per-deployment instance code
    "presets",            # shipped preset packs
    "cabinet/scripts",    # build/verify/rebuild CLIs + cog2 tooling
    "cabinet/admin-bot",  # live runtime surface
    "cabinet/mcp-server", # live runtime surface
    "cabinet/adapters",   # cabinet code lane (forward-guard)
    "cabinet/channels",   # cabinet code lane (forward-guard)
    "cabinet/companion",  # cabinet code lane (forward-guard)
    "cabinet/evals",      # eval harnesses (importable python)
    "cabinet/fixtures",   # fixture generators (importable python)
    "conftest.py",        # repo-root pytest fence (imported at collection time)
]

RULE_FORBIDDEN = "FORBIDDEN_IMPORTS_CORTEX"
RULE_TOKEN = "FORBIDDEN_CORTEX_TOKEN"
RULE_FALSIFIER = "FALSIFIER_IMPORTS_CORTEX"
RULE_UNALLOWLISTED = "UNALLOWLISTED_CORTEX_IMPORTER"

# grep backstop for the FORBIDDEN trees: the dotted module ref (static OR
# dynamic string) or the cache-store path on a live line, PLUS the ordinary
# `from framework import cortex` spelling — which names cortex only via the
# imported NAME, so the dotted `framework.cortex` scan alone misses it.
# Deliberately NOT a bare-word "cortex" scan — that noise would false-positive
# on prose; C-F20's real vectors are the module import and the cache-path open().
_BACKSTOP = re.compile(
    r"framework[./]cortex"
    r"|cabinet/cache/cortex"
    r"|from[ \t]+framework[ \t]+import[^#]*\bcortex\b")
# the falsifier's narrow ban (C-F17): it legitimately carries "cortex" as DATA
# (dict keys, a _cortex_from_cmd reader), so the broad module/path scan would
# over-fence it. Match only a REAL cortex import, however spelled: a dotted
# `import/from framework.cortex` line, a dynamic import_module/__import__ of
# framework.cortex, the `from framework import cortex` spelling, or a relative
# '.cortex' module string (the two-arg import_module('.cortex','framework') form).
_IMPORT_LINE = re.compile(r"^[ \t]*(import|from)[ \t]+framework\.cortex(\b|\.)")
_FALSIFIER_DYNAMIC = re.compile(
    r"(?:import_module|__import__)\([ \t]*['\"]framework\.cortex"
    r"|from[ \t]+framework[ \t]+import[^#]*\bcortex\b"
    r"|['\"]\.cortex['\"]")
# the NARROW dynamic-import regex swept across SWEEP_TREES (Check 3): a dynamic
# reach into framework.cortex that the AST walk cannot see — a direct
# import_module/__import__('framework.cortex…'), or the two-arg relative
# import_module('.cortex', 'framework'). Requires a real call site, so it stays
# near-zero-false-positive (never the noisy bare-token backstop).
_DYNAMIC_CORTEX = re.compile(
    r"(?:import_module|__import__)\([ \t]*['\"]framework\.cortex"
    r"|(?:import_module|__import__)\([ \t]*['\"]\.cortex['\"][ \t]*,[ \t]*['\"]framework['\"]")

# ===========================================================================
# COG-3 objectives boundary (contract §6.5) — additive, byte-compatible with
# the cortex rules above. FOUR module-granular rules + one data-plane sweep:
#   FORBIDDEN_IMPORTS_OBJECTIVES     a forbidden authority/action file imports
#                                    framework.objectives (any spelling)
#   FORBIDDEN_OBJECTIVES_TOKEN       a forbidden file NAMES framework.objectives
#                                    on a live line (dynamic-import backstop)
#   FORBIDDEN_OBJECTIVES_IMPORTS_ACTION  a framework/objectives/ file imports the
#                                    action plane (frontdoor/acting/authority) —
#                                    the REVERSE direction (§6.5 "reverse")
#   UNALLOWLISTED_OBJECTIVES_IMPORTER  a swept first-party file imports
#                                    framework.objectives but is neither
#                                    objectives-internal nor a curated cog3 reader
#                                    (this is how framework/missions importing the
#                                    graph REDs — §6.2(5))
#   FORBIDDEN_OBJECTIVES_DATAPLANE   a swept file names the objectives cache path
#                                    on a live line (§6.5 bullet 6, C-M9): the
#                                    non-covert data-plane read the import sweep
#                                    cannot see, closed across the FULL SWEEP_TREES
# The action-plane trees objectives may never import (reverse) are exactly the
# FORBIDDEN_TREES set (frontdoor/acting/authority).
ACTION_PLANE = tuple(t.replace("/", ".") for t in FORBIDDEN_TREES)

# legitimate objectives readers (module-granular). framework/objectives/ reads
# the cortex query surface AND itself; the cog3 CLIs/instruments read the graph.
# cog3-ovi-parity.py is DELIBERATELY absent: the C-F17 falsifier analog (§6.5,
# a separate later bullet) bans it from importing objectives internals, so it is
# never a sanctioned objectives reader — leaving it off means any objectives
# import from it REDs as UNALLOWLISTED, enforcing that ban at the module level.
OBJECTIVES_INTERNAL = "framework/objectives/"
ALLOWLIST_EXACT_OBJECTIVES = {
    "cabinet/scripts/cog3-rebuild.py",       # rebuild CLI (owns roots injection)
    "cabinet/scripts/cog3-graph-hash.py",    # hash instrument
    "cabinet/scripts/cog3-staleness.py",     # staleness instrument (two fenced as_of)
}
ALLOWLIST_GLOBS_OBJECTIVES = [
    "cabinet/scripts/tests/test_cog3_*.py",
    "cabinet/scripts/tests/lib_cog3_*.py",
]

RULE_FORBIDDEN_OBJ = "FORBIDDEN_IMPORTS_OBJECTIVES"
RULE_TOKEN_OBJ = "FORBIDDEN_OBJECTIVES_TOKEN"
RULE_OBJ_IMPORTS_ACTION = "FORBIDDEN_OBJECTIVES_IMPORTS_ACTION"
RULE_UNALLOWLISTED_OBJ = "UNALLOWLISTED_OBJECTIVES_IMPORTER"
RULE_OBJ_DATAPLANE = "FORBIDDEN_OBJECTIVES_DATAPLANE"

# backstop for FORBIDDEN trees: the objectives module ref (static OR dynamic
# string) or the ordinary `from framework import objectives` spelling. The cache
# path is NOT here — it is the data-plane sweep's job across ALL swept trees.
_BACKSTOP_OBJ = re.compile(
    r"framework[./]objectives"
    r"|from[ \t]+framework[ \t]+import[^#]*\bobjectives\b")
# narrow dynamic reach into framework.objectives (AST-blind complement, sweep).
_DYNAMIC_OBJ = re.compile(
    r"(?:import_module|__import__)\([ \t]*['\"]framework\.objectives"
    r"|(?:import_module|__import__)\([ \t]*['\"]\.objectives['\"][ \t]*,[ \t]*['\"]framework['\"]")
# the objectives cache-path data-plane token. ASSEMBLED (not a contiguous
# literal) on purpose: unlike the cortex data-plane check (forbidden-trees only),
# THIS sweep covers the full SWEEP_TREES — which includes this gate file itself —
# so a contiguous literal here would self-flag. Nowhere in this module may the
# path appear contiguously on a non-comment line (docstring bodies count).
_OBJ_CACHE_TOKEN = "cabinet/cache/" + "objectives"


def _is_cortex_module(name: str) -> bool:
    """True iff `name` is the shadow-model package framework.cortex or a
    submodule of it — never a mere prefix like framework.cortextools."""
    return name == CORTEX or name.startswith(CORTEX + ".")


def _import_from_targets(node: ast.ImportFrom, rel: str) -> list[str]:
    """Absolute dotted module(s) a `from ... import ...` statement binds.
    Resolves RELATIVE imports (node.level > 0) against the importing file's
    package path — `rel` is repo-root-relative, e.g. 'framework/authority/x.py'
    — by the stdlib rule (drop the last `level-1` parts of the file's package).
    Returns the base module AND each `base.<alias>` candidate, so BOTH
    `from framework.cortex import q` (base) and `from framework import cortex`
    (alias name) are visible. Thus `from ..cortex import engine` and
    `from .. import cortex` inside framework/authority/ resolve to the real
    framework.cortex, while `from . import cortex` there correctly resolves to
    framework.authority.cortex — a DIFFERENT module, never over-fenced."""
    if node.level == 0:
        base_parts = node.module.split(".") if node.module else []
    else:
        stem = rel[:-3] if rel.endswith(".py") else rel
        pkg_parts = stem.split("/")[:-1]          # package dir containing the module
        keep = len(pkg_parts) - (node.level - 1)
        if keep < 0:                              # relative beyond top-level: dead import
            return []
        base_parts = pkg_parts[:keep]
        if node.module:
            base_parts = base_parts + node.module.split(".")
    base_parts = [p for p in base_parts if p]
    targets: list[str] = []
    if base_parts:
        targets.append(".".join(base_parts))
    for alias in node.names:
        targets.append(".".join(base_parts + [alias.name]))
    return targets


def _cortex_imports(source: str, rel: str = "") -> list[str]:
    """Every framework.cortex[.*] module reached by a REAL import statement
    (AST — string literals never count). Catches `import framework.cortex`,
    `from framework.cortex import x`, the ordinary `from framework import cortex`
    (via the imported name), AND relative imports resolved against `rel`'s
    package path. The §7.1 gate is exactly this walk; the grep backstops are
    separate. Unparseable files yield []. A level>0 import with no `rel` context
    cannot be resolved and is skipped (every real call site passes rel)."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_cortex_module(alias.name):
                    hits.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and not rel:
                continue
            for target in _import_from_targets(node, rel):
                if _is_cortex_module(target):
                    hits.append(target)
    return hits


def _live_lines(source: str):
    """Yield lines that are neither a pure `#` comment nor a triple-quote
    delimiter line (the check-layer-separation.sh comment heuristic)."""
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        yield line


def _backstop_hit(source: str) -> bool:
    return any(_BACKSTOP.search(line) for line in _live_lines(source))


def _import_line_hit(source: str) -> bool:
    return any(_IMPORT_LINE.search(line) for line in source.splitlines())


def _falsifier_dynamic_hit(source: str) -> bool:
    """The falsifier's narrow dynamic/alias cortex ban, comment-safe (C-F17)."""
    return any(_FALSIFIER_DYNAMIC.search(line) for line in _live_lines(source))


def _dynamic_cortex_hit(source: str) -> bool:
    """A narrow dynamic import_module/__import__ reach into framework.cortex,
    comment-safe — the Check-3 sweep's AST-blind complement."""
    return any(_DYNAMIC_CORTEX.search(line) for line in _live_lines(source))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _py_files(base: Path) -> list[Path]:
    if base.is_dir():
        return sorted(p for p in base.rglob("*.py") if p.is_file())
    if base.is_file() and base.suffix == ".py":
        return [base]
    return []


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_cortex_internal(rel: str) -> bool:
    return rel.startswith(CORTEX_INTERNAL)


def _is_allowlisted(rel: str) -> bool:
    if rel in ALLOWLIST_EXACT:
        return True
    return any(fnmatch.fnmatch(rel, glob) for glob in ALLOWLIST_GLOBS)


# --- COG-3 objectives helpers (mirror the cortex idioms; reuse the generic
#     relative-import resolver `_import_from_targets`) -----------------------

def _is_objectives_module(name: str) -> bool:
    """True iff `name` is framework.objectives or a submodule — never a mere
    prefix like framework.objectivestools."""
    return name == OBJECTIVES or name.startswith(OBJECTIVES + ".")


def _is_action_plane_module(name: str) -> bool:
    """True iff `name` is (a submodule of) the action plane the objectives graph
    may never import: framework.frontdoor / framework.acting / framework.authority."""
    return any(name == a or name.startswith(a + ".") for a in ACTION_PLANE)


def _matching_imports(source: str, rel: str, predicate) -> list[str]:
    """Every real-import target (AST — string literals never count) for which
    `predicate(dotted_name)` holds. Catches `import X`, `from X import y`, the
    `from pkg import name` alias spelling, and relative imports resolved against
    `rel`'s package path (via `_import_from_targets`)."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if predicate(alias.name):
                    hits.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and not rel:
                continue
            for target in _import_from_targets(node, rel):
                if predicate(target):
                    hits.append(target)
    return hits


def _objectives_imports(source: str, rel: str = "") -> list[str]:
    return _matching_imports(source, rel, _is_objectives_module)


def _action_plane_imports(source: str, rel: str = "") -> list[str]:
    return _matching_imports(source, rel, _is_action_plane_module)


def _backstop_obj_hit(source: str) -> bool:
    return any(_BACKSTOP_OBJ.search(line) for line in _live_lines(source))


def _dynamic_obj_hit(source: str) -> bool:
    return any(_DYNAMIC_OBJ.search(line) for line in _live_lines(source))


def _obj_dataplane_hit(source: str) -> bool:
    """A live-line reference to the objectives cache path — the non-covert
    data-plane read (an open()/Path of the graph store). Comment-safe."""
    return any(_OBJ_CACHE_TOKEN in line for line in _live_lines(source))


def _is_objectives_internal(rel: str) -> bool:
    return rel.startswith(OBJECTIVES_INTERNAL)


def _is_cog3_allowlisted(rel: str) -> bool:
    if rel in ALLOWLIST_EXACT_OBJECTIVES:
        return True
    return any(fnmatch.fnmatch(rel, glob) for glob in ALLOWLIST_GLOBS_OBJECTIVES)


def scan(root) -> list[str]:
    """Return the sorted list of `<rel-path>:<RULE>` violations under `root`.
    Empty list == shadow boundary intact."""
    root = Path(root)
    violations: set[str] = set()
    flagged: set[str] = set()          # paths already given a specific rule

    # --- Check 1: the forbidden authority/action surface --------------------
    forbidden: list[Path] = []
    for tree in FORBIDDEN_TREES:
        forbidden += _py_files(root / tree)
    for name in FORBIDDEN_FILES:
        forbidden += _py_files(root / name)
    for path in forbidden:
        rel = _rel(root, path)
        src = _read(path)
        if _cortex_imports(src, rel):
            violations.add(f"{rel}:{RULE_FORBIDDEN}")
            flagged.add(rel)
        if _backstop_hit(src):
            violations.add(f"{rel}:{RULE_TOKEN}")
            flagged.add(rel)
        # COG-3: the SAME forbidden surface may not import the objectives graph.
        if _objectives_imports(src, rel):
            violations.add(f"{rel}:{RULE_FORBIDDEN_OBJ}")
            flagged.add(rel)
        if _backstop_obj_hit(src):
            violations.add(f"{rel}:{RULE_TOKEN_OBJ}")
            flagged.add(rel)

    # --- Check 2: the falsifier import ban (C-F17) --------------------------
    fpath = root / FALSIFIER
    if fpath.is_file():
        rel = _rel(root, fpath)
        src = _read(fpath)
        if (_cortex_imports(src, rel) or _import_line_hit(src)
                or _falsifier_dynamic_hit(src)):
            violations.add(f"{rel}:{RULE_FALSIFIER}")
            flagged.add(rel)

    # --- Check 3: the global whitelist — any OTHER cortex importer ----------
    # COG-3 broadening: framework/objectives/ and the cog3 CLIs/tests are
    # LEGITIMATE cortex readers (the graph reads the cortex query surface), so
    # they fold clean here — the narrow SYMBOL restriction on which cortex names
    # they may import is the separate net-new AST pin, not this module gate.
    for tree in SWEEP_TREES:
        for path in _py_files(root / tree):
            rel = _rel(root, path)
            if (rel in flagged or _is_cortex_internal(rel) or _is_allowlisted(rel)
                    or _is_objectives_internal(rel) or _is_cog3_allowlisted(rel)):
                continue
            src = _read(path)
            if _cortex_imports(src, rel) or _dynamic_cortex_hit(src):
                violations.add(f"{rel}:{RULE_UNALLOWLISTED}")

    # --- Check R (COG-3 reverse): framework/objectives/ may read the cortex,
    #     never the action plane (frontdoor/acting/authority) -----------------
    for path in _py_files(root / OBJECTIVES_INTERNAL.rstrip("/")):
        rel = _rel(root, path)
        src = _read(path)
        if _action_plane_imports(src, rel):
            violations.add(f"{rel}:{RULE_OBJ_IMPORTS_ACTION}")
            flagged.add(rel)

    # --- Check O (COG-3): the objectives import sweep — any swept first-party
    #     file importing framework.objectives that is not objectives-internal
    #     nor a curated cog3 reader (this is how framework/missions REDs) ------
    for tree in SWEEP_TREES:
        for path in _py_files(root / tree):
            rel = _rel(root, path)
            if (rel in flagged or _is_objectives_internal(rel)
                    or _is_cog3_allowlisted(rel)):
                continue
            src = _read(path)
            if _objectives_imports(src, rel) or _dynamic_obj_hit(src):
                violations.add(f"{rel}:{RULE_UNALLOWLISTED_OBJ}")

    # --- Check D (COG-3, §6.5 bullet 6 / C-M9): the data-plane sweep — a live
    #     reference to the objectives cache path anywhere in SWEEP_TREES, with
    #     objectives-internal + cog3 readers allowlisted. Independent of the
    #     import rules (a file may both import AND open the cache) so `flagged`
    #     is NOT skipped here. ---------------------------------------------------
    for tree in SWEEP_TREES:
        for path in _py_files(root / tree):
            rel = _rel(root, path)
            if _is_objectives_internal(rel) or _is_cog3_allowlisted(rel):
                continue
            src = _read(path)
            if _obj_dataplane_hit(src):
                violations.add(f"{rel}:{RULE_OBJ_DATAPLANE}")

    return sorted(violations)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="COG-2/COG-3 shadow-boundary import gate (§7.1 cortex + §6.5 objectives).")
    parser.add_argument("--root", type=Path,
                        default=Path(__file__).resolve().parents[2],
                        help="repo root to scan (default: this script's repo).")
    parser.add_argument("--report", action="store_true",
                        help="list every violation and exit 0.")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON.")
    args = parser.parse_args(argv)

    violations = scan(args.root)

    if args.json:
        print(json.dumps({"violations": violations, "count": len(violations)},
                         indent=2))
    elif violations:
        stream = sys.stdout if args.report else sys.stderr
        print(f"[cog2-import-gate] {len(violations)} violation(s) — the shadow "
              "boundary is breached (authority/action code must not reach "
              "framework.cortex or framework.objectives; the objectives graph "
              "must not reach the action plane) — M5 / §7.1 / §6.5:", file=stream)
        for v in violations:
            print(f"  + {v}", file=stream)
        if not args.report:
            print("[cog2-import-gate] FAIL — remove the import/reference; the "
                  "cortex and objectives projections are read ONLY through their "
                  "rebuild/verify CLIs and tests.", file=sys.stderr)
    else:
        print("[cog2-import-gate] OK — no authority/action code imports the "
              "cortex or objectives shadow models (shadow boundary intact).")

    if args.report:
        return 0
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
