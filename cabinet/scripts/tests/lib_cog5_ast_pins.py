"""lib_cog5_ast_pins.py — the symbol-level AST scanners for the three COG-5
sibling import pins (contract §7.3/§8.4/§10; cognitive-core-phase-5-contract-
2026-07-24). Pure stdlib `ast`; imports NO framework module (it must not itself
trip the import gate, and it must run in the hermetic HOME-pinned suite with no
third-party dep). Helper, not a test (pytest collects test_*.py, never lib_*.py).

The coarse module gate (`cog2-import-gate.py` boundary rows, §10) says WHICH
TREES may import which token; these scanners pin, at symbol/import granularity,
the three foundry surfaces the contract names as sibling AST pins (§10 "New
sibling pins"). Every scanner is green-by-vacuity while its target file/tree is
absent (this wave), so the pins land tests-first and arm for when the code lands
(W3 sandbox, W5 holdout_gen, W6 league) — each carries its RETIREMENT CONDITION
in its sibling test.

1. holdout_importer_violations(root) — the league-invisibility IMPORTER pin
   (§7.3): over framework/evolution/ EXCEPT holdout_gen itself. RED: any sibling
   module importing framework.evolution.holdout_gen, however spelled (dotted,
   the alias `from framework.evolution import holdout_gen`, or the module object
   `from framework.evolution.holdout_gen import x`). The oracle CLI + holdout
   tests live OUTSIDE framework/evolution/ and are naturally clean. This is the
   symbol-level twin of ROW 8's repo-wide module sweep (belt-and-braces — the
   contract's "an AST pin enforces the same at symbol level", §7.3).

2. league_import_violations(root) — over framework/evolution/league.py (§10).
   ALLOWED: stdlib | framework.evolution.* (internal) | the fidelity PUBLIC
   surfaces framework.fidelity.{scorer,leakguard,officer_runner}. Anything else
   is RED — the action/authority planes, framework.fidelity.oauth_llm (the
   credential holder), any OTHER fidelity module, a third-party dep. Plus (§10)
   league_subprocess_socket_violations pins that the pure ranking fold takes NO
   subprocess/socket import and makes no os.<exec> call — the arena/sandbox layer
   is the sanctioned subprocess site, never the league.

3. sandbox_forbidden_import_violations(root) — over framework/evolution/sandbox.py
   (§10). The harness legitimately imports git/subprocess machinery, so this is a
   DENY-list, not an allow-list, of exactly the two classes §10 names: RED on an
   import of the ARCHIVE WRITER (framework.evolution.archive — the harness
   executes candidates, it must never write the archive) or a credential store
   (framework.fidelity.oauth_llm — the §4.4 harness-holds-credentials holder must
   not be reachable from the candidate-visible exec surface). Everything else —
   subprocess, os, shutil, tempfile, pathlib, evolution-internal — is allowed.
   The action lanes framework.{frontdoor,acting} are fenced from sandbox.py (it
   lives under framework/evolution/) by ROW 10, the reverse row — NOT re-added
   here; the broader runtime env-scrub (no ~/.screenpipe/.env/keychain reach) is
   the BEHAVIORAL sim-7 escape battery (§4.4/§8.4, a later wave), not a static
   import pin.

HONEST LIMITATION (mirrors lib_cog4_ast_pins / EVAL-025 C2): a dynamically-
assembled import (getattr walks, importlib string assembly) evades a static AST
scan — evasion IS the violation; this scan is the tripwire, not the definition.
The behavioral backstops are ROW 8's dynamic-reach engine (holdout) and the
sim-6/sim-7 batteries (§12, later waves).

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-5 contract §7.3/§8.4/§10).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# target locations (all green-by-vacuity while absent this wave)
# ---------------------------------------------------------------------------
EVOLUTION_TREE_REL = "framework/evolution"
HOLDOUT_GEN_REL = "framework/evolution/holdout_gen.py"
LEAGUE_FILE_REL = "framework/evolution/league.py"
SANDBOX_FILE_REL = "framework/evolution/sandbox.py"

# the holdout module token — assembled from parts so this file never carries the
# contiguous dotted literal as a live-line token the boundary sweep might see
# (belt: this lib IS allowlisted on the holdout row's test glob only via
# test_cog5_holdout_*, NOT lib_cog5_*, so keep the assembled discipline).
HOLDOUT_TOKEN = "framework.evolution." + "holdout_gen"

# league allow-list: the fidelity PUBLIC surfaces (§10) + evolution-internal.
_LEAGUE_INTERNAL_ANY = (
    "framework.evolution",
    "framework.fidelity.scorer",
    "framework.fidelity.leakguard",
    "framework.fidelity.officer_runner",
)

# sandbox DENY set (§10): exactly the two classes §10 names — the archive writer
# and the credential holder. Prefix-matched (framework.evolution.archive and any
# submodule; framework.fidelity.oauth_llm). The action lanes frontdoor/acting are
# fenced by ROW 10 (the reverse row), not duplicated here.
_SANDBOX_FORBIDDEN = (
    "framework.evolution.archive",
    "framework.fidelity.oauth_llm",
)

# the no-subprocess/no-socket pin (league): importing any of these is RED.
_FORBIDDEN_EXEC_MODULES = frozenset({"subprocess", "socket", "_socket"})
# … and these os.<attr>(…) calls are RED (shelling out / exec-ing).
_FORBIDDEN_OS_CALL_ATTRS = frozenset({
    "system", "popen",
    "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp",
    "spawnvpe", "posix_spawn", "posix_spawnp", "fork", "forkpty",
})

_STDLIB = frozenset(sys.stdlib_module_names)

RULE_HOLDOUT_IMPORT = "HOLDOUT_IMPORT_FORBIDDEN"
RULE_LEAGUE_IMPORT = "LEAGUE_IMPORT_FORBIDDEN"
RULE_LEAGUE_EXEC = "LEAGUE_SUBPROCESS_SOCKET_FORBIDDEN"
RULE_SANDBOX_IMPORT = "SANDBOX_IMPORT_FORBIDDEN"


# ---------------------------------------------------------------------------
# shared AST machinery (self-contained — no cross-unit lib coupling, L1111)
# ---------------------------------------------------------------------------
def _py_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.py") if p.is_file())


def _top(name: str) -> str:
    return name.split(".", 1)[0]


def _matches_any(name: str, prefixes: tuple[str, ...]) -> bool:
    return any(name == p or name.startswith(p + ".") for p in prefixes)


def _resolve_relative(module: str | None, level: int, rel: str) -> str | None:
    """Resolve a `from ... import` module to its ABSOLUTE dotted name. `rel` is the
    repo-relative file path. level>0 resolves against the file's package by the
    stdlib rule. Returns None only for an import reaching beyond the top-level."""
    if level == 0:
        return module
    stem = rel[:-3] if rel.endswith(".py") else rel
    pkg_parts = stem.split("/")[:-1]              # dir holding the module = its package
    keep = len(pkg_parts) - (level - 1)
    if keep < 0:
        return None
    base = pkg_parts[:keep]
    if module:
        base = base + module.split(".")
    dotted = ".".join(p for p in base if p)
    return dotted or None


def _importfrom_targets(node: ast.ImportFrom, rel: str) -> list[str]:
    """The absolute dotted module AND each `base.<alias>` candidate a
    `from ... import ...` binds — so both `from a.b import c` (base a.b) and
    `from a import b` (alias name a.b) are visible. Returns [] for an unresolved
    relative import (dead beyond top-level)."""
    base = _resolve_relative(node.module, node.level, rel)
    if base is None and node.level:
        return []
    base_parts = base.split(".") if base else []
    targets: list[str] = []
    if base_parts:
        targets.append(".".join(base_parts))
    for alias in node.names:
        if alias.name == "*":
            continue
        targets.append(".".join(base_parts + [alias.name]))
    return targets


# ---------------------------------------------------------------------------
# 1. holdout importer pin (league-invisibility, symbol level)
# ---------------------------------------------------------------------------
def _holdout_importers_in_source(source: str, rel: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    out: list[str] = []

    def _is_holdout(name: str) -> bool:
        return name == HOLDOUT_TOKEN or name.startswith(HOLDOUT_TOKEN + ".")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_holdout(alias.name):
                    out.append(f"{rel}:{RULE_HOLDOUT_IMPORT}:import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            for tgt in _importfrom_targets(node, rel):
                if _is_holdout(tgt):
                    out.append(f"{rel}:{RULE_HOLDOUT_IMPORT}:from-import {tgt}")
    return out


def holdout_importer_violations(root) -> list[str]:
    """Sorted `<rel>:HOLDOUT_IMPORT_FORBIDDEN:<detail>` over framework/evolution/
    EXCEPT holdout_gen itself. Empty == no sibling module imports the frozen
    holdout generator (league-invisible), or the tree is absent."""
    repo = Path(root)
    base = repo / EVOLUTION_TREE_REL
    skip = {HOLDOUT_GEN_REL, "framework/evolution/holdout_gen/"}
    out: list[str] = []
    for path in _py_files(base):
        rel = path.relative_to(repo).as_posix()
        if rel == HOLDOUT_GEN_REL or rel.startswith("framework/evolution/holdout_gen/"):
            continue
        out += _holdout_importers_in_source(
            path.read_text(encoding="utf-8", errors="replace"), rel)
    return sorted(out)


# ---------------------------------------------------------------------------
# 2. league import pin (allow-list) + the no-subprocess/no-socket pin
# ---------------------------------------------------------------------------
def _allowlist_violations_in_source(source: str, rel: str, *, rule: str,
                                    internal_any: tuple[str, ...]) -> list[str]:
    """Allow-list symbol scan: stdlib + `internal_any` prefixes are clean; the
    module OBJECT and every symbol of an allowed prefix are clean; ANYTHING ELSE
    (a module outside the allow-set, a third-party dep) is RED."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if _top(name) in _STDLIB or _matches_any(name, internal_any):
                    continue
                out.append(f"{rel}:{rule}:import {name}")
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_relative(node.module, node.level, rel)
            names = [a.name for a in node.names]
            if resolved is None:
                out.append(f"{rel}:{rule}:from (unresolved level {node.level})")
                continue
            if _top(resolved) in _STDLIB or _matches_any(resolved, internal_any):
                continue
            out.append(f"{rel}:{rule}:from {resolved} import {','.join(names) or '*'}")
    return out


def league_import_violations(root) -> list[str]:
    """Sorted `<rel>:LEAGUE_IMPORT_FORBIDDEN:<detail>` over the league file (§10).
    Empty == league imports only stdlib | evolution-internal | the fidelity
    scorer/leakguard/officer_runner public surfaces (or the file is absent)."""
    repo = Path(root)
    path = repo / LEAGUE_FILE_REL
    if not path.is_file():
        return []
    return sorted(_allowlist_violations_in_source(
        path.read_text(encoding="utf-8", errors="replace"), LEAGUE_FILE_REL,
        rule=RULE_LEAGUE_IMPORT, internal_any=_LEAGUE_INTERNAL_ANY))


def _exec_violations_in_source(source: str, rel: str, *, rule: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    out: list[str] = []
    os_names: set[str] = {"os"}          # every binding of the os module
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _top(alias.name) in _FORBIDDEN_EXEC_MODULES:
                    out.append(f"{rel}:{rule}:import {alias.name}")
                if alias.name == "os":
                    os_names.add(alias.asname or "os")
        elif isinstance(node, ast.ImportFrom):
            if (node.level == 0 and node.module
                    and _top(node.module) in _FORBIDDEN_EXEC_MODULES):
                out.append(f"{rel}:{rule}:from {node.module} import "
                           f"{','.join(a.name for a in node.names) or '*'}")
            elif node.level == 0 and node.module == "os":
                for a in node.names:
                    if a.name == "*":
                        out.append(f"{rel}:{rule}:from os import * "
                                   "(star-import binds exec primitives; RED "
                                   "regardless of call site)")
                    elif a.name in _FORBIDDEN_OS_CALL_ATTRS:
                        out.append(f"{rel}:{rule}:from os import {a.name}")
        elif isinstance(node, ast.Call):
            calls.append(node)
    for node in calls:
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_OS_CALL_ATTRS
                and isinstance(func.value, ast.Name) and func.value.id in os_names):
            out.append(f"{rel}:{rule}:{func.value.id}.{func.attr}()")
    return out


def league_subprocess_socket_violations(root) -> list[str]:
    """Sorted `<rel>:LEAGUE_SUBPROCESS_SOCKET_FORBIDDEN:<detail>` over the league
    file. Empty == the pure ranking fold never shells out or opens a socket (§10;
    the arena/sandbox layer is the sanctioned subprocess site) — or it is absent."""
    repo = Path(root)
    path = repo / LEAGUE_FILE_REL
    if not path.is_file():
        return []
    return sorted(_exec_violations_in_source(
        path.read_text(encoding="utf-8", errors="replace"), LEAGUE_FILE_REL,
        rule=RULE_LEAGUE_EXEC))


# ---------------------------------------------------------------------------
# 3. sandbox forbidden-import pin (deny-list)
# ---------------------------------------------------------------------------
def _forbidden_violations_in_source(source: str, rel: str, *, rule: str,
                                    forbidden: tuple[str, ...]) -> list[str]:
    """Deny-list scan: RED on any import (dotted, alias, or module-object) whose
    absolute module matches a `forbidden` prefix. Everything else is clean —
    the harness legitimately imports stdlib subprocess/git machinery."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _matches_any(alias.name, forbidden):
                    out.append(f"{rel}:{rule}:import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            for tgt in _importfrom_targets(node, rel):
                if _matches_any(tgt, forbidden):
                    out.append(f"{rel}:{rule}:from-import {tgt}")
    return out


def sandbox_forbidden_import_violations(root) -> list[str]:
    """Sorted `<rel>:SANDBOX_IMPORT_FORBIDDEN:<detail>` over the sandbox harness
    file (§10). Empty == the harness imports NO archive writer, NO credential
    store, and NO action/authority plane (git/subprocess machinery stays fine) —
    or the file is absent."""
    repo = Path(root)
    path = repo / SANDBOX_FILE_REL
    if not path.is_file():
        return []
    return sorted(_forbidden_violations_in_source(
        path.read_text(encoding="utf-8", errors="replace"), SANDBOX_FILE_REL,
        rule=RULE_SANDBOX_IMPORT, forbidden=_SANDBOX_FORBIDDEN))
