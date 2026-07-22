"""lib_cog3_import_ast.py — the symbol-level AST scanners for the COG-3 objectives
boundary (contract §6.5 bullet 3 + §5.1 discipline 1). Pure stdlib `ast`; imports
NO framework module (it must not itself trip the import gate). Helper, not a test
(pytest collects test_*.py, never lib_*.py).

Two scanners over `framework/objectives/**.py`, both green-by-vacuity while the
package is absent:

1. objectives_import_violations(root) — the SYMBOL-level import pin the coarse
   module gate cannot express (attack O-M3/G-M1). Every import in the tree must be:
     * stdlib, OR
     * framework.objectives[.*] (internal, any symbols), OR
     * from framework.cortex.query import <only the seven enumerated symbols>.
   Anything else is RED — load_beliefs (the C-F15-bypassing loader),
   framework.cortex.engine/adapters, framework.fidelity.*, framework.ovi.*, any
   authority/action module, importing the cortex query MODULE object (which would
   let code dot into a forbidden symbol), or a third-party dep.

2. asof_default_violations(root) — the defaults-only pin (§5.1 discipline 1). The
   ONLY sanctioned as_of(...) call shape is the canonical build read
   `as_of(beliefs, subject_key, scope=..., observation=<canonical cutoff>)`; any
   OTHER keyword (the fold-control mutant seams fence_axis / rederive / scope_mode
   / unknown_mode / supersession_order / lineage, plus dimension / source, plus a
   **kwargs splat) is RED. This is stricter than "only the five mutant seams" on
   purpose — the contract's canonical call passes exactly scope + observation, so
   "defaults-only" is read as "nothing beyond the sanctioned inputs"; a later wave
   that genuinely needs dimension/source narrowing amends this pin consciously
   (the same posture the P12 ratchet's G-m4 note takes).

HONEST LIMITATION (mirrors EVAL-025 C2 / test_cog2_contradiction): a
dynamically-assembled import (getattr walks, importlib string assembly) or an
as_of call reached through an aliased indirection evades a static AST scan —
evasion IS the violation; this scan is the tripwire, not the definition. The
module gate's transitive-closure test is the runtime backstop for the import half.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

OBJECTIVES_PKG = "framework.objectives"
CORTEX_QUERY_MODULE = "framework.cortex.query"
# the ONLY symbols framework/objectives/ may import from the cortex query surface
# (contract §3 disposition table / §6.5 bullet 3).
ALLOWED_CORTEX_SYMBOLS = frozenset({
    "load_beliefs_verified", "as_of", "BeliefView", "AsOfResult",
    "ScopeError", "StoreCorruptError", "UNKNOWN",
})
# the canonical as_of read passes exactly these keywords (beliefs+subject_key are
# the positional params, allowed by keyword too). Everything else is a fold seam.
ASOF_SANCTIONED_KWARGS = frozenset({"beliefs", "subject_key", "scope", "observation"})

_STDLIB = frozenset(sys.stdlib_module_names)

RULE_IMPORT = "OBJECTIVES_IMPORT_FORBIDDEN"
RULE_ASOF = "ASOF_NONDEFAULT_KWARG"


def objectives_dir(root) -> Path:
    return Path(root) / "framework" / "objectives"


def _py_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.py") if p.is_file())


def _top(name: str) -> str:
    return name.split(".", 1)[0]


def _resolve_relative(module: str | None, level: int, rel: str) -> str | None:
    """Resolve a `from ... import` module to its ABSOLUTE dotted name. `rel` is
    the repo-relative file path (framework/objectives/adapters/roots.py). level>0
    resolves against the file's package by the stdlib rule. Returns None only for
    an import that reaches beyond the top-level package (a dead import)."""
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


def _is_internal(name: str) -> bool:
    return name == OBJECTIVES_PKG or name.startswith(OBJECTIVES_PKG + ".")


def _import_violations_in_source(source: str, rel: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        # an unparseable objectives file is itself a problem, but not this pin's
        # job — the pin reports on parseable imports; a syntax error surfaces in
        # the ordinary test collection/run.
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if _top(name) in _STDLIB or _is_internal(name):
                    continue
                # `import framework.cortex.query` imports the MODULE object — a
                # symbol-pin bypass (dot into anything). Forbidden like the rest.
                out.append(f"{rel}:{RULE_IMPORT}:import {name}")
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_relative(node.module, node.level, rel)
            names = [a.name for a in node.names]
            if resolved is None:
                out.append(f"{rel}:{RULE_IMPORT}:from (unresolved level {node.level})")
                continue
            if _is_internal(resolved) or _top(resolved) in _STDLIB:
                continue
            if resolved == CORTEX_QUERY_MODULE:
                bad = [n for n in names if n not in ALLOWED_CORTEX_SYMBOLS]
                for n in bad:
                    out.append(f"{rel}:{RULE_IMPORT}:from {resolved} import {n}")
                continue
            # anything else — cortex internals, fidelity, ovi, authority/action,
            # the cortex package object, a third-party dep — is RED.
            out.append(f"{rel}:{RULE_IMPORT}:from {resolved} import "
                       f"{','.join(names) or '*'}")
    return out


def objectives_import_violations(root) -> list[str]:
    """Sorted `<rel>:OBJECTIVES_IMPORT_FORBIDDEN:<detail>` list over
    framework/objectives/ under `root`. Empty == the symbol boundary is intact."""
    base = objectives_dir(root)
    repo = Path(root)
    out: list[str] = []
    for path in _py_files(base):
        rel = path.relative_to(repo).as_posix()
        out += _import_violations_in_source(path.read_text(encoding="utf-8",
                                                            errors="replace"), rel)
    return sorted(out)


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
                # a **kwargs splat could smuggle a fold seam — RED (tripwire).
                out.append(f"{rel}:{RULE_ASOF}:**splat")
            elif kw.arg not in ASOF_SANCTIONED_KWARGS:
                out.append(f"{rel}:{RULE_ASOF}:{kw.arg}")
    return out


def asof_default_violations(root) -> list[str]:
    """Sorted `<rel>:ASOF_NONDEFAULT_KWARG:<kwarg>` list over framework/objectives/
    under `root`. Empty == every as_of call uses defaults-only (§5.1 discipline 1)."""
    base = objectives_dir(root)
    repo = Path(root)
    out: list[str] = []
    for path in _py_files(base):
        rel = path.relative_to(repo).as_posix()
        out += _asof_violations_in_source(path.read_text(encoding="utf-8",
                                                         errors="replace"), rel)
    return sorted(out)
