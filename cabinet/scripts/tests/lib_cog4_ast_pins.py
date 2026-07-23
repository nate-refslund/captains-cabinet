"""lib_cog4_ast_pins.py — the symbol-level AST scanners for the three COG-4
sibling import pins (contract §8.4, cognitive-core-phase-4-contract-2026-07-23).
Pure stdlib `ast`; imports NO framework module (it must not itself trip the import
gate, and it must run in the hermetic HOME-pinned suite with no third-party dep).
Helper, not a test (pytest collects test_*.py, never lib_*.py).

The coarse module gate (`cog2-import-gate.py` boundary rows, §8.3) says the planner
tree / the two dual-plane CLIs MAY read certain trees; these scanners pin WHICH
SYMBOLS each may import — the sibling of the shipped `test_cog3_objectives_ast_pin`
seven-symbol pin, which stays byte-untouched and never weakens (MR7). Every scanner
is green-by-vacuity while its target tree/CLI is absent (this phase), so the pins
land tests-first and arm for when the code lands.

Three symbol allow-lists (contract §8.4 verbatim), plus the scheduler's two extra
disciplines:

1. scheduler_import_violations(root) — over framework/scheduler/**.py (the pure
   planner). Allowed: stdlib | framework.scheduler[.*] (internal) | framework.organs[.*]
   | framework.projection[.*] (the C3 kernel) | `from framework.cortex.query import
   <only the seven enumerated query-surface symbols>` | `from framework.objectives.query
   import <only serve_graph, serve_objective, recommend, ServeRefused>`. Anything else
   is RED — load_beliefs (the trusted-bytes loader), cortex engine/adapters, the cortex
   or objectives query MODULE object (a dot-into bypass), any objectives module other
   than the serve surface, any authority/acting/frontdoor/fidelity/missions/ovi module,
   or a third-party dep.
2. scheduler_asof_default_violations(root) — the defaults-only as_of pin cloned over
   the scheduler tree (§3: "the scheduler's cortex reads inherit the COG-3 disciplines
   ... defaults-only — pinned by a cloned AST test over the scheduler tree"). The only
   sanctioned as_of(...) keywords are beliefs / subject_key / scope / observation; any
   fold-control seam (rederive / scope_mode / lineage / …), dimension / source, or a
   **kwargs splat is RED.
3. scheduler_subprocess_socket_violations(root) — the no-subprocess/no-socket pin over
   the planner tree (§7.2: "no subprocess/os.system in the planner tree — AST pin; tests
   use subprocess, the planner never does"). Importing subprocess/socket, or an
   os.system/os.popen/os.exec*/os.spawn*/os.fork call, is RED.
4. dispatch_import_violations(root) — over cabinet/scripts/cog4-dispatch-shadow.py (the
   separate dispatcher, §7.3). Allowed: stdlib | `from framework.authority.policy_engine
   import <risk_of, resolve_verdict, read_cell_state, _act_with_undo_gap>` | `from
   framework.fidelity.graduation import evaluate` | the framework.scheduler.serve surface.
   So the dispatcher can never grow into an executor.
5. parity_import_violations(root) — over cabinet/scripts/cog4-parity.py (the ONE
   sanctioned dual-plane comparator, §5.3). Allowed: stdlib | `from
   framework.authority.classifier import classify_action` | the matrix mapping-surface
   read accessors (RISK_CLASSES + load_matrix / matrix_policy / ceiling_members, which
   expose the ceiling_frozenset_map policy key) | the same four policy_engine read-only
   symbols + graduation.evaluate the dispatcher pins | the organs PUBLIC registry /
   descriptor surface. Everything else is RED — the comparator stays a comparator,
   never a resolver anything in framework/ could grow to depend on.

HONEST LIMITATION (mirrors lib_cog3_import_ast / EVAL-025 C2): a dynamically-assembled
import (getattr walks, importlib string assembly) or an as_of reached through an aliased
indirection evades a static AST scan — evasion IS the violation; this scan is the
tripwire, not the definition. The parity pin's transitive-closure subprocess test (in
test_cog4_parity_ast_pin.py) is the runtime backstop for the comparator half.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# target locations (all green-by-vacuity while absent this phase)
# ---------------------------------------------------------------------------
SCHEDULER_TREE_REL = "framework/scheduler"
DISPATCH_CLI_REL = "cabinet/scripts/cog4-dispatch-shadow.py"
PARITY_CLI_REL = "cabinet/scripts/cog4-parity.py"

# the ONLY symbols the planner may import from the cortex query surface — the same
# seven the shipped objectives pin enumerates (contract §3 / §8.4).
ALLOWED_CORTEX_SYMBOLS = frozenset({
    "load_beliefs_verified", "as_of", "BeliefView", "AsOfResult",
    "ScopeError", "StoreCorruptError", "UNKNOWN",
})
# the ONLY symbols the planner may import from the objectives serve surface (§2.1/§8.4).
ALLOWED_OBJECTIVES_SERVE_SYMBOLS = frozenset({
    "serve_graph", "serve_objective", "recommend", "ServeRefused",
})
# the four read-only policy_engine symbols the dispatcher + parity comparator share (§8.4).
ALLOWED_POLICY_ENGINE_SYMBOLS = frozenset({
    "risk_of", "resolve_verdict", "read_cell_state", "_act_with_undo_gap",
})
# graduation exposes exactly the one shadow-evaluation entry point (§8.4).
ALLOWED_GRADUATION_SYMBOLS = frozenset({"evaluate"})
# the matrix mapping-surface read accessors the parity comparator may import: the risk
# vocabulary set + the load/policy/ceiling accessors that expose the ceiling_frozenset_map
# policy key (matrix.py — ceiling_frozenset_map is a policy-dict key, not a python symbol,
# read via load_matrix/matrix_policy/ceiling_members; §5.1/§5.3/§8.4).
ALLOWED_MATRIX_SYMBOLS = frozenset({
    "RISK_CLASSES", "load_matrix", "matrix_policy", "ceiling_members",
})
# the one classifier accessor the parity comparator may import (§5.3/§8.4).
ALLOWED_CLASSIFIER_SYMBOLS = frozenset({"classify_action"})

# the canonical as_of read passes exactly these keywords (beliefs+subject_key are the
# positional params, allowed by keyword too). Everything else is a fold seam.
ASOF_SANCTIONED_KWARGS = frozenset({"beliefs", "subject_key", "scope", "observation"})

# the no-subprocess/no-socket pin: importing any of these is RED in the planner tree.
FORBIDDEN_EXEC_IMPORT_MODULES = frozenset({"subprocess", "socket", "_socket"})
# … and these os.<attr>(…) calls are RED (shelling out / exec-ing from the pure planner).
FORBIDDEN_OS_CALL_ATTRS = frozenset({
    "system", "popen",
    "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
    "posix_spawn", "posix_spawnp", "fork", "forkpty",
})

_STDLIB = frozenset(sys.stdlib_module_names)

RULE_SCHED_IMPORT = "SCHED_IMPORT_FORBIDDEN"
RULE_SCHED_ASOF = "SCHED_ASOF_NONDEFAULT_KWARG"
RULE_SCHED_EXEC = "SCHED_SUBPROCESS_SOCKET_FORBIDDEN"
RULE_DISPATCH_IMPORT = "DISPATCH_IMPORT_FORBIDDEN"
RULE_PARITY_IMPORT = "PARITY_IMPORT_FORBIDDEN"


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
    repo-relative file path. level>0 resolves against the file's package by the stdlib
    rule. Returns None only for an import reaching beyond the top-level package."""
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


def _import_violations_in_source(source: str, rel: str, *, rule: str,
                                 internal_any: tuple[str, ...],
                                 symbol_restricted: dict[str, frozenset[str]]) -> list[str]:
    """Generic symbol-level import scan. `internal_any` prefixes allow the module object
    and every symbol (the tree's own package + sanctioned whole-surface deps).
    `symbol_restricted` maps a module to the ONLY symbols importable via `from`; its
    MODULE OBJECT (`import <that module>` or `from <pkg> import <that module>`) is RED —
    it would let code dot into a forbidden symbol."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        # an unparseable target is a problem, but not this pin's job — a syntax error
        # surfaces in ordinary test collection.
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if _top(name) in _STDLIB or _matches_any(name, internal_any):
                    continue
                # module-object import of a symbol-restricted module (or anything else)
                # is a dot-into bypass — RED.
                out.append(f"{rel}:{rule}:import {name}")
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_relative(node.module, node.level, rel)
            names = [a.name for a in node.names]
            if resolved is None:
                out.append(f"{rel}:{rule}:from (unresolved level {node.level})")
                continue
            if _top(resolved) in _STDLIB or _matches_any(resolved, internal_any):
                continue
            if resolved in symbol_restricted:
                allowed = symbol_restricted[resolved]
                for n in names:
                    if n not in allowed:
                        out.append(f"{rel}:{rule}:from {resolved} import {n}")
                continue
            # anything else — a non-serve cortex/objectives module, the query module
            # object, an authority/action module, a third-party dep — is RED.
            out.append(f"{rel}:{rule}:from {resolved} import {','.join(names) or '*'}")
    return out


def _scan_tree(root, tree_rel: str, *, rule: str, internal_any: tuple[str, ...],
               symbol_restricted: dict[str, frozenset[str]]) -> list[str]:
    repo = Path(root)
    base = repo / tree_rel
    out: list[str] = []
    for path in _py_files(base):
        rel = path.relative_to(repo).as_posix()
        out += _import_violations_in_source(
            path.read_text(encoding="utf-8", errors="replace"), rel,
            rule=rule, internal_any=internal_any, symbol_restricted=symbol_restricted)
    return sorted(out)


def _scan_single_file(root, file_rel: str, *, rule: str, internal_any: tuple[str, ...],
                      symbol_restricted: dict[str, frozenset[str]]) -> list[str]:
    repo = Path(root)
    path = repo / file_rel
    if not path.is_file():
        return []
    return sorted(_import_violations_in_source(
        path.read_text(encoding="utf-8", errors="replace"), file_rel,
        rule=rule, internal_any=internal_any, symbol_restricted=symbol_restricted))


# ---------------------------------------------------------------------------
# 1. scheduler import pin (planner tree)
# ---------------------------------------------------------------------------
_SCHED_INTERNAL_ANY = ("framework.scheduler", "framework.organs", "framework.projection")
_SCHED_SYMBOL_RESTRICTED = {
    "framework.cortex.query": ALLOWED_CORTEX_SYMBOLS,
    "framework.objectives.query": ALLOWED_OBJECTIVES_SERVE_SYMBOLS,
}


def scheduler_import_violations(root) -> list[str]:
    """Sorted `<rel>:SCHED_IMPORT_FORBIDDEN:<detail>` list over framework/scheduler/.
    Empty == the planner's symbol boundary is intact (or the tree is absent)."""
    return _scan_tree(root, SCHEDULER_TREE_REL, rule=RULE_SCHED_IMPORT,
                      internal_any=_SCHED_INTERNAL_ANY,
                      symbol_restricted=_SCHED_SYMBOL_RESTRICTED)


# ---------------------------------------------------------------------------
# 2. scheduler defaults-only as_of pin (cloned)
# ---------------------------------------------------------------------------
def _asof_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "as_of":
            yield node
        elif isinstance(func, ast.Attribute) and func.attr == "as_of":
            yield node


def _asof_violations_in_source(source: str, rel: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    out: list[str] = []
    for call in _asof_calls(tree):
        for kw in call.keywords:
            if kw.arg is None:
                out.append(f"{rel}:{RULE_SCHED_ASOF}:**splat")
            elif kw.arg not in ASOF_SANCTIONED_KWARGS:
                out.append(f"{rel}:{RULE_SCHED_ASOF}:{kw.arg}")
    return out


def scheduler_asof_default_violations(root) -> list[str]:
    """Sorted `<rel>:SCHED_ASOF_NONDEFAULT_KWARG:<kwarg>` list over framework/scheduler/.
    Empty == every as_of call is defaults-only."""
    repo = Path(root)
    base = repo / SCHEDULER_TREE_REL
    out: list[str] = []
    for path in _py_files(base):
        rel = path.relative_to(repo).as_posix()
        out += _asof_violations_in_source(path.read_text(encoding="utf-8",
                                                          errors="replace"), rel)
    return sorted(out)


# ---------------------------------------------------------------------------
# 3. scheduler no-subprocess/no-socket pin
# ---------------------------------------------------------------------------
def _exec_violations_in_source(source: str, rel: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    out: list[str] = []
    # names bound to the `os` module: the literal `os` ALWAYS counts (a bare os.system()
    # is caught with or without a visible import — no regression), plus every `import os
    # as <alias>` binding so os.<exec>() reached through an alias cannot evade the Call
    # check below (the alias case the cp1 review named). Collected across a FULL walk
    # before the call scan, so binding order in the AST never matters.
    os_names: set[str] = {"os"}
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _top(alias.name) in FORBIDDEN_EXEC_IMPORT_MODULES:
                    out.append(f"{rel}:{RULE_SCHED_EXEC}:import {alias.name}")
                if alias.name == "os":
                    os_names.add(alias.asname or "os")
        elif isinstance(node, ast.ImportFrom):
            # only absolute imports of the forbidden modules matter (a relative import
            # cannot reach the stdlib subprocess/socket).
            if node.level == 0 and node.module and _top(node.module) in FORBIDDEN_EXEC_IMPORT_MODULES:
                out.append(f"{rel}:{RULE_SCHED_EXEC}:from {node.module} import "
                           f"{','.join(a.name for a in node.names) or '*'}")
            # `from os import system|popen|exec*|spawn*|fork` is a FIRST-CLASS static
            # import of a shell/exec primitive: the call site is then a bare Name the
            # Attribute check below can never see, so it must RED HERE (§7.2 — the exact
            # `from os import system`/`from os import popen` escape the cp1 review proved).
            # asname is irrelevant — the ORIGINAL imported name is the exec primitive.
            elif node.level == 0 and node.module == "os":
                for a in node.names:
                    if a.name in FORBIDDEN_OS_CALL_ATTRS:
                        out.append(f"{rel}:{RULE_SCHED_EXEC}:from os import {a.name}")
        elif isinstance(node, ast.Call):
            calls.append(node)
    # os.system(...) / <alias>.popen(...) / os.exec*/spawn*/fork(...) — the root name is a
    # binding of the os module and the attribute is a shell/exec primitive.
    for node in calls:
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_OS_CALL_ATTRS
                and isinstance(func.value, ast.Name) and func.value.id in os_names):
            out.append(f"{rel}:{RULE_SCHED_EXEC}:{func.value.id}.{func.attr}()")
    return out


def scheduler_subprocess_socket_violations(root) -> list[str]:
    """Sorted `<rel>:SCHED_SUBPROCESS_SOCKET_FORBIDDEN:<detail>` list over
    framework/scheduler/. Empty == the pure planner never shells out or opens a socket."""
    repo = Path(root)
    base = repo / SCHEDULER_TREE_REL
    out: list[str] = []
    for path in _py_files(base):
        rel = path.relative_to(repo).as_posix()
        out += _exec_violations_in_source(path.read_text(encoding="utf-8",
                                                         errors="replace"), rel)
    return sorted(out)


# ---------------------------------------------------------------------------
# 4. dispatch CLI import pin (the separate dispatcher, never an executor)
# ---------------------------------------------------------------------------
_DISPATCH_INTERNAL_ANY = ("framework.scheduler.serve",)
_DISPATCH_SYMBOL_RESTRICTED = {
    "framework.authority.policy_engine": ALLOWED_POLICY_ENGINE_SYMBOLS,
    "framework.fidelity.graduation": ALLOWED_GRADUATION_SYMBOLS,
}


def dispatch_import_violations(root) -> list[str]:
    """Sorted `<rel>:DISPATCH_IMPORT_FORBIDDEN:<detail>` list over the dispatch CLI.
    Empty == the dispatcher imports only its sanctioned read-only surface (or is absent)."""
    return _scan_single_file(root, DISPATCH_CLI_REL, rule=RULE_DISPATCH_IMPORT,
                             internal_any=_DISPATCH_INTERNAL_ANY,
                             symbol_restricted=_DISPATCH_SYMBOL_RESTRICTED)


# ---------------------------------------------------------------------------
# 5. parity CLI import pin (the ONE sanctioned dual-plane comparator)
# ---------------------------------------------------------------------------
_PARITY_INTERNAL_ANY = ("framework.organs.registry", "framework.organs.descriptor")
_PARITY_SYMBOL_RESTRICTED = {
    "framework.authority.classifier": ALLOWED_CLASSIFIER_SYMBOLS,
    "framework.authority.matrix": ALLOWED_MATRIX_SYMBOLS,
    "framework.authority.policy_engine": ALLOWED_POLICY_ENGINE_SYMBOLS,
    "framework.fidelity.graduation": ALLOWED_GRADUATION_SYMBOLS,
}


def parity_import_violations(root) -> list[str]:
    """Sorted `<rel>:PARITY_IMPORT_FORBIDDEN:<detail>` list over the parity CLI.
    Empty == the comparator imports only its sanctioned dual-plane surface (or is absent)."""
    return _scan_single_file(root, PARITY_CLI_REL, rule=RULE_PARITY_IMPORT,
                             internal_any=_PARITY_INTERNAL_ANY,
                             symbol_restricted=_PARITY_SYMBOL_RESTRICTED)
