#!/usr/bin/env python3.12
"""cog2-import-gate.py — the declarative boundary-manifest ENGINE (COG-4 §8).

C2 CONVERSION (Phase-4 contract §8.1-§8.3, byte-compatible): this gate began as
the COG-2 cortex shadow-boundary gate (contract §7.1 / M5), was extended IN
PLACE by COG-3 with the objectives boundary (§6.5), and is now the GENERIC
engine for `cabinet/config/boundary-manifest.yml` — every boundary is a declared
ROW there; phases add rows, never engine code. The name, the CLI contract
(check / --report / --json, exit 1 on breach), all nine pre-conversion rule ids,
and the scan semantics are preserved byte-compatibly: engine-over-repo output ==
pre-conversion output (both empty), and every pre-conversion negative-control
mutant still REDs (test_cog2_import_gate.py + test_cog3_import_gate.py run
unchanged; test_cog4_boundary_rows.py GENERATES a mutant per row so every
future row ships with its bite proven).

This gate stays MODULE-granular BY DESIGN: the narrow SYMBOL rule (which names
an importer may touch) is never expressed here — it lives in dedicated sibling
AST pins (test_cog3_objectives_ast_pin.py and the COG-4 pins, contract §8.4);
a row's `symbol_pin` field is a documentation-only pointer to that sibling,
never enforcement.

FIVE CHECK SHAPES, driven entirely by row data (§8.2):
  1 forbidden surface    a row's `forbidden_importers` (authority/action trees/
                         files) may neither import the row token — ANY spelling:
                         `import framework.cortex`, `from framework.cortex
                         import x`, the ordinary `from framework import cortex`
                         (alias name), a relative `from ..cortex import x` that
                         RESOLVES to the token (AST walk; rule
                         `rule_ids.forbidden_import`) — nor NAME it on a live
                         line (comment-safe grep backstop incl. dynamic-import
                         strings and the row's `token_backstop_extra` literals;
                         rule `rule_ids.forbidden_token`).
  2 falsifier ban        a row's `falsifier_exact` files may import NO module of
                         the token, however spelled — static, alias, or dynamic
                         import_module/__import__ (C-F17). NARROW matching only:
                         these files legitimately carry the token word as DATA
                         (rule `rule_ids.falsifier`).
  R reverse direction    files under a row's `internal_prefix` may never import
                         the row's `reverse_forbidden` trees — AST plus the
                         narrow dynamic complement (rule `rule_ids.reverse`).
  3 unallowlisted sweep  ANY file in the global `sweep_trees` that imports the
                         token (AST or narrow dynamic import_module/__import__)
                         but is neither row-internal nor a curated reader
                         (rule `rule_ids.unallowlisted`).
  D data-plane sweep     for `kind: data_plane` rows: a live line NAMING the
                         store path substring anywhere in `sweep_trees`, with
                         the row's internal tree + curated readers allowlisted —
                         the non-covert read the import sweep cannot see
                         (rule `rule_ids.data_plane`).

DYNAMIC-FORM RESOLUTION (shared machinery behind checks 1, 2, R and 3): the
narrow per-row regexes above see a dynamic import only when the module name is a
CONTIGUOUS literal on the call line. A second, AST-based pass
(`_dynamic_import_targets`) closes the two forms that slipped past that:
  * a CONSTANT-FOLDABLE argument — `import_module('framework' + '.x.y')`, an
    all-literal f-string — folded by `_fold_str` over str literals, `+`
    concatenation and literal-only JoinedStr;
  * an ALIASED binding of the import hook — `from importlib import import_module
    as _m; _m('framework.x.y')`, `import importlib as il; il.import_module(...)`,
    or the assignment form `_im = importlib.import_module; _im(...)`. Bindings
    are collected over a FULL walk BEFORE the call scan (so a call ABOVE its
    import still resolves), mirroring the COG-4 exec-pin idiom in
    cabinet/scripts/tests/lib_cog4_ast_pins.py.
The folded name/package pair is then resolved by the same stdlib rule the static
walk uses for `from ..x import y`, so the two-argument RELATIVE form resolves
through an alias too. Matching is BINDING-ACCURATE, not name-based: a file that
defines its own `def import_module(...)`, or rebinds the name, is not misread as
reaching importlib (it would NameError at runtime otherwise).

ADDITIVE, with one honest caveat. Every pre-existing regex is unchanged and
still fires wherever it fired, and engine-over-repo output is byte-identical
before and after (both empty, all three modes). The pass only ever ADDS a
DETECTION. It is NOT true that no attribution can ever move: check 1 marks a
file `flagged`, and the pre-existing `flagged` de-duplication then suppresses
the merely-un-curated sweep id for that file. So a file carrying TWO reaches —
one newly caught by check 1, one already caught by check 3 — can trade its
sweep rule id for the more specific forbidden id. The file still REDs and the
exit code is unchanged; only which id names it moves. That is the engine's
existing de-duplication working on a newly visible input, not new behaviour —
but a reader grepping for one specific id deserves to know it.

Only what is STATICALLY DECIDABLE is folded: a computed argument folds to None
and stays residual (below). This widens DYNAMIC-FORM detection ONLY — the gate
stays MODULE-granular and still never enforces symbols.

Baseline-zero, shrink-only: the accepted-violation set is EMPTY. Any violation
fails the gate. The forbidden surface only ever grows (a protection never
shrinks); allowlists are the curated per-row reader sets. A file DELIBERATELY
left off a row's allowlist (`deliberately_absent`) is a first-class protection:
any reach from it REDs as un-curated, and the loader fail-closes if such a file
is ever simultaneously allowlisted.

FAIL-CLOSED LOADING: a missing/unparseable manifest, an unknown key, a missing
or duplicate rule id, or a contradicted deliberate absence raises at load time
— a typo can never silently drop a protection. Regex fragments built from row
data are `re.escape`d (tokens are literals, never patterns).

Sweep coverage (the closed bridge-escape): the manifest's `sweep_trees` covers
EVERY first-party importable Python tree, so a PLAIN greppable forbidden import
is never invisible, wherever it lives — a one-hop bridge (authority file ->
`from shared.x_bridge import q`; the bridge -> the real import) is caught at
the bridge, which lives in a swept tree.

EXCLUDED trees (named per the fail-closed rule — none is an importable Python
namespace, so no import statement can hide in them): the non-code top-level
trees designs/, docs/, memory/, packs/, patches/, vault/ (design assets,
markdown, data, asset packs, patch files, the Obsidian vault) and the cabinet
non-code subtrees cache/, config/, cron/, dashboard/, deploy/, docs/, env/,
launchd/, logs/, loop-prompts/, mcp-overlays/, migrations/, officer-skills/,
runbooks/, sql/, starter-spaces/, tests/, world/ (data, config, plists, logs,
SQL, assets, prompt/skill markdown). They carry NO .py today. If Python is ever
added to any of them it MUST be added to the manifest's sweep_trees — the
completeness-invariant test (test_every_first_party_py_is_on_scan_surface)
fails loudly until it is, so this class of omission cannot recur silently.

Residuals (accepted pre-conversion, unchanged by it; revisited when the read
pointer flips off `none`):
(1) TRANSITIVE attribution. The gate is a per-file DIRECT-import detector, not a
    transitive import-graph analyzer. A multi-hop chain is caught at whichever
    file LITERALLY imports the token — always a swept first-party file — so the
    reach is NEVER silent; only attribution of upstream callers is out of scope.
(2) RUNTIME-COMPUTED assembly. NARROWED by the dynamic-form pass above — the
    residual set is now strictly smaller. Explicitly NOT residual any more (each
    is caught, per-form arms in test_boundary_dynamic_forms.py):
      - a constant-foldable argument: `import_module('framework' + '.x.y')`,
        adjacent-literal concatenation, an all-literal f-string;
      - an aliased import hook, in any binding order: `from importlib import
        import_module as _m`, `import importlib as il`, and the assignment
        `_im = importlib.import_module`;
      - the two-argument RELATIVE form (a dot-name handed to import_module with
        a package), which every row's narrow dynamic pattern already covered and
        which the folding pass now also resolves through an alias.
    What REMAINS residual, named precisely — this list is the protection's real
    boundary, and an unnamed gap here would be a false claim:
      (a) a module name computed at runtime: a variable, a function parameter, a
          call result, `%`/`.format()`/`.join()` assembly, a table or env
          lookup, an interpolated f-string field. Not decidable without
          executing the program.
      (b) an attribute walk that never names a module as a string: getattr
          chains, `sys.modules[...]` indexing, `__dict__` traversal.
      (c) STILL-DECIDABLE forms this pass deliberately does NOT resolve, listed
          so nobody mistakes silence for coverage:
            - the builtin's `fromlist` and `level` parameters —
              `__import__('framework', globals(), locals(), ['x'])` reaches
              framework.x, and `__import__('x', globals(), locals(), [], 1)`
              reaches the caller package's x. Both are decidable (level needs
              the importing file's own package, which `_import_from_targets`
              already computes for the static form) and are simply not wired
              yet;
            - an alias chain deeper than one hop (`a = importlib.import_module;
              b = a; b(...)`), which resolves conservatively to nothing;
            - a concatenation nested past `_FOLD_MAX_DEPTH`.
      Closing any of (c) is a mechanical follow-up; until then it is documented,
      not hidden. Runtime detection remains the RUNTIME layer's job, not this
      gate's.

CHECK ORDER (one deliberate normalization, no legacy-visible change): checks
run 1, 2, R, 3, D. Pre-conversion code ran the reverse check between the two
sweeps; because reverse rows only scan their own `internal_prefix` tree and
sweeps always skip that tree for the same row, no input distinguishes the two
orders for the legacy rows — normalizing R before ALL sweeps simply lets a
reverse-flagged file skip un-curated sweep double-flagging uniformly.

Usage:
  python3.12 cabinet/scripts/cog2-import-gate.py             # check: exit 1 on breach
  python3.12 cabinet/scripts/cog2-import-gate.py --report    # list all, exit 0
  python3.12 cabinet/scripts/cog2-import-gate.py --json      # machine-readable
  python3.12 cabinet/scripts/cog2-import-gate.py --root PATH # scan another tree
  python3.12 cabinet/scripts/cog2-import-gate.py --manifest PATH  # alternate row law

Provenance: COG-2 gate authored + extended per the 2026-07-07 full-autonomy
grant; C2 engine conversion per the same grant + the 2026-07-20
cognitive-masterplan continuous grant (COG-4 contract §8).
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import re
import sys
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve()
REPO_DEFAULT = _HERE.parents[2]
MANIFEST_PATH = _HERE.parents[1] / "config" / "boundary-manifest.yml"

MANIFEST_SCHEMA = "cabinet/boundary-manifest/v1"
MODULE_KIND = "module"
DATA_PLANE_KIND = "data_plane"

_TOP_KEYS = {"schema", "sweep_trees", "rows"}
_ROW_KEYS = {
    "token", "kind", "forbidden_importers", "internal_prefix",
    "allowlist_exact", "allowlist_globs", "reverse_forbidden", "sweep",
    "rule_ids", "symbol_pin", "falsifier_exact", "token_backstop_extra",
    "deliberately_absent",
}
# module-row-only mechanism keys (fail-closed: meaningless on data_plane rows)
_MODULE_ONLY_KEYS = {
    "forbidden_importers", "reverse_forbidden", "falsifier_exact",
    "token_backstop_extra",
}
# the dynamic-call token, spelled so THIS file never matches its own pattern
# (the escaped `\(` means the contiguous call form never appears here — the
# pre-conversion SELF-FLAG-SAFE idiom, kept).
_DYN_CALL = r"(?:import_module|__import__)\("
# the dynamic-import hook names, for the AST pass. Held as bare identifiers
# (never followed by `(` in this source) so the SELF-FLAG-SAFE idiom above still
# holds: the contiguous call form appears nowhere in this file.
_IMPORTLIB_MODULE = "importlib"
_IMPORT_MODULE_FUNC = "import_module"
_BUILTIN_IMPORT = "__import__"


class ManifestError(ValueError):
    """A boundary-manifest defect. ALWAYS fatal — the gate fails closed."""


# ---------------------------------------------------------------------------
# rows — validated + compiled from the yml (tokens are literals: re.escape'd)
# ---------------------------------------------------------------------------
# Plain __slots__ classes, deliberately NOT dataclasses: the existing suites
# load this hyphen-named file via spec_from_file_location, sometimes WITHOUT a
# sys.modules registration — under `from __future__ import annotations` the
# dataclass machinery resolves string annotations through sys.modules[__module__]
# and crashes in exactly that loader shape. Plain classes are loader-agnostic.

class BoundaryRow:
    """One validated + compiled manifest row. Immutable by convention."""

    __slots__ = (
        "token", "kind", "forbidden_importers", "internal_prefix",
        "allowlist_exact", "allowlist_globs", "reverse_forbidden", "sweep",
        "rule_ids", "symbol_pin", "falsifier_exact", "token_backstop_extra",
        "deliberately_absent", "backstop", "dynamic", "falsifier_import_line",
        "falsifier_dynamic", "reverse_modules", "reverse_dynamic",
    )

    def __init__(self, *, token, kind, forbidden_importers, internal_prefix,
                 allowlist_exact, allowlist_globs, reverse_forbidden, sweep,
                 rule_ids, symbol_pin, falsifier_exact, token_backstop_extra,
                 deliberately_absent, backstop, dynamic, falsifier_import_line,
                 falsifier_dynamic, reverse_modules, reverse_dynamic):
        self.token = token
        self.kind = kind
        self.forbidden_importers = forbidden_importers
        self.internal_prefix = internal_prefix
        self.allowlist_exact = allowlist_exact
        self.allowlist_globs = allowlist_globs
        self.reverse_forbidden = reverse_forbidden
        self.sweep = sweep
        self.rule_ids = rule_ids
        self.symbol_pin = symbol_pin
        self.falsifier_exact = falsifier_exact
        self.token_backstop_extra = token_backstop_extra
        self.deliberately_absent = deliberately_absent
        self.backstop = backstop
        self.dynamic = dynamic
        self.falsifier_import_line = falsifier_import_line
        self.falsifier_dynamic = falsifier_dynamic
        self.reverse_modules = reverse_modules
        self.reverse_dynamic = reverse_dynamic

    def is_module_of_token(self, name: str) -> bool:
        """True iff `name` is the row token module or a submodule of it —
        never a mere prefix (framework.cortextools is not framework.cortex)."""
        return name == self.token or name.startswith(self.token + ".")

    def is_reverse_module(self, name: str) -> bool:
        return any(name == m or name.startswith(m + ".")
                   for m in self.reverse_modules)

    def is_internal(self, rel: str) -> bool:
        return rel.startswith(self.internal_prefix)

    def is_allowlisted(self, rel: str) -> bool:
        if rel in self.allowlist_exact:
            return True
        return any(fnmatch.fnmatch(rel, g) for g in self.allowlist_globs)


class BoundaryConfig:
    """The loaded manifest: sweep surface + rows, in declaration order."""

    __slots__ = ("manifest_path", "sweep_trees", "rows")

    def __init__(self, *, manifest_path, sweep_trees, rows):
        self.manifest_path = manifest_path
        self.sweep_trees = sweep_trees
        self.rows = rows

    def module_rows(self) -> list[BoundaryRow]:
        return [r for r in self.rows if r.kind == MODULE_KIND]

    def data_plane_rows(self) -> list[BoundaryRow]:
        return [r for r in self.rows if r.kind == DATA_PLANE_KIND]

    def row_for_token(self, token: str) -> BoundaryRow:
        for r in self.rows:
            if r.token == token:
                return r
        raise ManifestError(f"no row declares token {token!r}")


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ManifestError(f"boundary-manifest: {msg}")


def _str_list(row: dict, key: str, token: str) -> list[str]:
    val = row.get(key) or []
    _require(isinstance(val, list) and all(isinstance(x, str) and x for x in val),
             f"row {token!r}: {key} must be a list of non-empty strings")
    return val


def _compile_module_patterns(token: str, extras: tuple[str, ...],
                             has_falsifier: bool):
    """Per-token regexes, built from ESCAPED literals only. For the legacy rows
    these compile to byte-identical patterns to the pre-conversion constants
    (_BACKSTOP, _DYNAMIC_CORTEX, _IMPORT_LINE, _FALSIFIER_DYNAMIC and the
    objectives twins)."""
    parts = token.split(".")
    parent, name = ".".join(parts[:-1]), parts[-1]
    e_token, e_parent, e_name = (re.escape(token), re.escape(parent),
                                 re.escape(name))
    # live-line backstop for the forbidden surface: the dotted/pathed module
    # ref (static OR dynamic string), any extra literals (e.g. the cortex
    # cache store), and the ordinary `from <parent> import <name>` spelling —
    # which names the token only via the imported NAME. Deliberately NOT a
    # bare-word scan (prose would false-positive).
    backstop_alts = [rf"{e_parent}[./]{e_name}"]
    backstop_alts += [re.escape(x) for x in extras]
    backstop_alts.append(rf"from[ \t]+{e_parent}[ \t]+import[^#]*\b{e_name}\b")
    backstop = re.compile("|".join(backstop_alts))
    # the NARROW dynamic reach swept repo-wide: a real import_module/__import__
    # call site on the token, or the two-arg relative form — near-zero
    # false-positive, never a bare-token scan.
    dynamic = re.compile(
        rf"{_DYN_CALL}[ \t]*['\"]{e_token}"
        rf"|{_DYN_CALL}[ \t]*['\"]\.{e_name}['\"][ \t]*,[ \t]*['\"]{e_parent}['\"]")
    falsifier_import_line = falsifier_dynamic = None
    if has_falsifier:
        # the falsifier's narrow ban: ONLY a real import however spelled — a
        # dotted import line, a dynamic call, the alias spelling, or a relative
        # '.name' module string (the two-arg import_module form).
        falsifier_import_line = re.compile(
            rf"^[ \t]*(import|from)[ \t]+{e_token}(\b|\.)")
        falsifier_dynamic = re.compile(
            rf"{_DYN_CALL}[ \t]*['\"]{e_token}"
            rf"|from[ \t]+{e_parent}[ \t]+import[^#]*\b{e_name}\b"
            rf"|['\"]\.{e_name}['\"]")
    return backstop, dynamic, falsifier_import_line, falsifier_dynamic


def _compile_reverse(reverse_forbidden: tuple[str, ...]):
    """Reverse-direction module set + the narrow dynamic complement. For the
    objectives row this compiles byte-identically to the pre-conversion
    _DYNAMIC_ACTION pattern."""
    modules = tuple(t.replace("/", ".") for t in reverse_forbidden)
    by_parent: dict[str, list[str]] = {}
    for mod in modules:
        parts = mod.split(".")
        _require(len(parts) >= 2,
                 f"reverse_forbidden entry {mod!r} must be tree-shaped (a/b)")
        by_parent.setdefault(".".join(parts[:-1]), []).append(parts[-1])
    branches = []
    for parent, names in by_parent.items():
        e_parent = re.escape(parent)
        alt = "|".join(re.escape(n) for n in names)
        branches.append(rf"{_DYN_CALL}[ \t]*['\"]{e_parent}\.(?:{alt})")
        branches.append(
            rf"{_DYN_CALL}[ \t]*['\"]\.(?:{alt})['\"][ \t]*,[ \t]*['\"]{e_parent}['\"]")
    return modules, re.compile("|".join(branches))


def _compile_row(raw: object) -> BoundaryRow:
    _require(isinstance(raw, dict), f"row must be a mapping, got {type(raw)}")
    unknown = set(raw) - _ROW_KEYS
    _require(not unknown, f"row {raw.get('token')!r}: unknown keys {sorted(unknown)}")
    token = raw.get("token")
    _require(isinstance(token, str) and token, "row without a non-empty token")
    kind = raw.get("kind")
    _require(kind in (MODULE_KIND, DATA_PLANE_KIND),
             f"row {token!r}: kind must be {MODULE_KIND}|{DATA_PLANE_KIND}")
    _require("internal_prefix" in raw and isinstance(raw["internal_prefix"], str)
             and raw["internal_prefix"].endswith("/"),
             f"row {token!r}: internal_prefix must be a 'tree/' prefix")
    _require(isinstance(raw.get("sweep"), bool), f"row {token!r}: sweep must be bool")
    symbol_pin = raw.get("symbol_pin")
    _require(symbol_pin is None or (isinstance(symbol_pin, str) and symbol_pin),
             f"row {token!r}: symbol_pin must be a path or null")
    rule_ids = raw.get("rule_ids")
    _require(isinstance(rule_ids, dict) and rule_ids
             and all(isinstance(k, str) and isinstance(v, str) and v
                     for k, v in rule_ids.items()),
             f"row {token!r}: rule_ids must be a non-empty str->str mapping")

    forbidden = tuple(_str_list(raw, "forbidden_importers", token))
    allow_exact = frozenset(_str_list(raw, "allowlist_exact", token))
    allow_globs = tuple(_str_list(raw, "allowlist_globs", token))
    rev_raw = raw.get("reverse_forbidden")
    _require(rev_raw is None or isinstance(rev_raw, list),
             f"row {token!r}: reverse_forbidden must be a list or null")
    reverse = tuple(_str_list(raw, "reverse_forbidden", token)) if rev_raw else ()
    falsifier = tuple(_str_list(raw, "falsifier_exact", token))
    extras = tuple(_str_list(raw, "token_backstop_extra", token))
    absent = tuple(_str_list(raw, "deliberately_absent", token))

    # rule-id coverage is EXACT per mechanism — no orphan ids, no missing ids.
    expected: set[str] = set()
    if kind == MODULE_KIND:
        _require("." in token, f"module row {token!r}: token must be dotted")
        if forbidden:
            expected |= {"forbidden_import", "forbidden_token"}
        if falsifier:
            expected.add("falsifier")
        if reverse:
            expected.add("reverse")
        if raw["sweep"]:
            expected.add("unallowlisted")
    else:
        present = _MODULE_ONLY_KEYS & set(raw)
        _require(not present,
                 f"data_plane row {token!r}: module-only keys {sorted(present)}")
        _require(raw["sweep"] is True,
                 f"data_plane row {token!r}: sweep must be true (a store row "
                 "that sweeps nothing protects nothing)")
        expected = {"data_plane"}
    _require(set(rule_ids) == expected,
             f"row {token!r}: rule_ids keys {sorted(rule_ids)} != required "
             f"{sorted(expected)} for its declared mechanisms")

    # a deliberate absence contradicted by the row's own allowlists is a
    # manifest defect (the protection would silently not exist).
    for path in absent:
        _require(path not in allow_exact
                 and not any(fnmatch.fnmatch(path, g) for g in allow_globs)
                 and not path.startswith(raw["internal_prefix"]),
                 f"row {token!r}: deliberately_absent {path!r} is allowlisted "
                 "— the absence is the protection; remove one or the other")

    backstop = dynamic = fal_line = fal_dyn = None
    rev_modules: tuple[str, ...] = ()
    rev_dyn = None
    if kind == MODULE_KIND:
        backstop, dynamic, fal_line, fal_dyn = _compile_module_patterns(
            token, extras, bool(falsifier))
        if reverse:
            rev_modules, rev_dyn = _compile_reverse(reverse)

    return BoundaryRow(
        token=token, kind=kind, forbidden_importers=forbidden,
        internal_prefix=raw["internal_prefix"], allowlist_exact=allow_exact,
        allowlist_globs=allow_globs, reverse_forbidden=reverse,
        sweep=raw["sweep"], rule_ids=dict(rule_ids), symbol_pin=symbol_pin,
        falsifier_exact=falsifier, token_backstop_extra=extras,
        deliberately_absent=absent, backstop=backstop, dynamic=dynamic,
        falsifier_import_line=fal_line, falsifier_dynamic=fal_dyn,
        reverse_modules=rev_modules, reverse_dynamic=rev_dyn)


def load_config(manifest_path: Path | str = MANIFEST_PATH) -> BoundaryConfig:
    """Parse + validate the boundary manifest, FAIL-CLOSED (ManifestError on
    any defect — the gate never runs on a law it cannot fully trust)."""
    manifest_path = Path(manifest_path)
    _require(manifest_path.is_file(), f"manifest missing: {manifest_path}")
    try:
        doc = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - exercised via tests
        raise ManifestError(f"boundary-manifest: unparseable yml: {exc}") from exc
    _require(isinstance(doc, dict), "top level must be a mapping")
    unknown = set(doc) - _TOP_KEYS
    _require(not unknown, f"unknown top-level keys {sorted(unknown)}")
    _require(doc.get("schema") == MANIFEST_SCHEMA,
             f"schema must be {MANIFEST_SCHEMA!r}, got {doc.get('schema')!r}")
    trees = doc.get("sweep_trees")
    _require(isinstance(trees, list) and trees
             and all(isinstance(t, str) and t for t in trees),
             "sweep_trees must be a non-empty list of strings")
    _require(len(set(trees)) == len(trees), "sweep_trees has duplicates")
    raw_rows = doc.get("rows")
    _require(isinstance(raw_rows, list) and raw_rows,
             "rows must be a non-empty list")
    rows = tuple(_compile_row(r) for r in raw_rows)
    tokens = [r.token for r in rows]
    _require(len(set(tokens)) == len(tokens), f"duplicate tokens in {tokens}")
    all_ids = [rid for r in rows for rid in r.rule_ids.values()]
    _require(len(set(all_ids)) == len(all_ids),
             f"duplicate rule ids across rows in {sorted(all_ids)}")
    return BoundaryConfig(manifest_path=manifest_path,
                          sweep_trees=tuple(trees), rows=rows)


# ---------------------------------------------------------------------------
# file mechanics (unchanged from the pre-conversion engine)
# ---------------------------------------------------------------------------

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


_FOLD_MAX_DEPTH = 40


def _fold_str(node: ast.AST | None, _depth: int = 0) -> str | None:
    """Constant-fold a string expression, or None if not statically decidable.

    Decides exactly the literal shapes: a `str` constant, `+` concatenation of
    foldable parts, a JoinedStr (f-string) whose every piece folds, and a walrus
    whose value folds. `ast.literal_eval` is deliberately NOT used — it rejects
    string concatenation outright, which is the very form this closes.

    Anything computed at runtime (a Name, a call, a subscript, `%`/`.format()`/
    `.join()`, a conversion/format-spec on an f-string field) folds to None and
    stays in the documented residual — this pass never GUESSES a module name.

    DEPTH-CAPPED: a pathologically nested expression returns None rather than
    raising RecursionError. `scan()` catches only SyntaxError/ValueError, so an
    uncaught RecursionError here would abort the WHOLE scan — a gate that dies
    is worse than one that declines to decide a 40-deep concatenation.
    """
    if _depth > _FOLD_MAX_DEPTH:
        return None
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.NamedExpr):          # (x := 'a.b') — the value binds
        return _fold_str(node.value, _depth + 1)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _fold_str(node.left, _depth + 1)
        if left is None:
            return None
        right = _fold_str(node.right, _depth + 1)
        return None if right is None else left + right
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for piece in node.values:
            if isinstance(piece, ast.FormattedValue):
                # a conversion (!r) or a format spec makes the result
                # undecidable from the literal alone.
                if piece.conversion != -1 or piece.format_spec is not None:
                    return None
                got = _fold_str(piece.value, _depth + 1)
            else:
                got = _fold_str(piece, _depth + 1)
            if got is None:
                return None
            parts.append(got)
        return "".join(parts)
    return None


def _resolve_dyn_target(name: str, package: str | None) -> str | None:
    """Absolute dotted module for a folded dynamic-import (name, package) pair.

    An absolute name passes through. A leading-dot name resolves against
    `package` by the SAME stdlib rule `_import_from_targets` applies to the
    static `from ..x import y` form (drop the last `level-1` parts). Undecidable
    (a relative name with no folded package, or one reaching past the top-level
    package) -> None."""
    if not name:
        return None
    if not name.startswith("."):
        return name
    if not package:
        return None
    level = len(name) - len(name.lstrip("."))
    rest = name[level:]
    parts = package.split(".")
    if not all(parts):
        # a MALFORMED package ('a..b', '.a', 'a.') — CPython does not normalize
        # it, so silently stripping the empty segments would resolve to a module
        # the program never imports. Undecidable, by design.
        return None
    keep = len(parts) - (level - 1)
    # `keep < 1` (not < 0) is the stdlib rule: importlib._bootstrap._resolve_name
    # raises "attempted relative import beyond top-level package" as soon as the
    # anchor would be EMPTY, so level must not exceed the package's own depth.
    # An empty anchor here would otherwise resolve `...c` against `a.b` to the
    # bare top-level `c` — a module the caller never named (a false positive).
    if keep < 1:
        return None
    base = parts[:keep]
    if rest:
        base = base + rest.split(".")
    return ".".join(p for p in base if p) or None


def _assign_target_names(node: ast.AST):
    """The plain Names an assignment/loop/with target binds (tuples flattened)."""
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, ast.Starred):
        yield from _assign_target_names(node.value)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            yield from _assign_target_names(elt)


# node types that can bind a name to a NON-hook value. Checked as one tuple
# isinstance before dispatching, so the hot walk does not pay a generator call
# per node (a per-node generator cost ~40% of scan wall time).
_SHADOW_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.arg,
                 ast.AugAssign, ast.AnnAssign, ast.For, ast.AsyncFor,
                 ast.comprehension, ast.withitem, ast.ExceptHandler)


def _shadowing_names(node: ast.AST):
    """Names a node binds to something that is NOT an import hook — a def, a
    class, a parameter, a loop/with/except target, an augmented or annotated
    assignment. Used to DISQUALIFY a name from hook status: a file that defines
    its own `def import_module(...)` is not calling importlib's."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        yield node.name
    elif isinstance(node, ast.arg):
        yield node.arg
    elif isinstance(node, ast.AugAssign):
        yield from _assign_target_names(node.target)
    elif isinstance(node, ast.AnnAssign):
        if node.value is not None:
            yield from _assign_target_names(node.target)
    elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
        yield from _assign_target_names(node.target)
    elif isinstance(node, ast.withitem):
        if node.optional_vars is not None:
            yield from _assign_target_names(node.optional_vars)
    elif isinstance(node, ast.ExceptHandler):
        if node.name:
            yield node.name


def _dynamic_import_targets_from_nodes(nodes: list[ast.AST]) -> list[str]:
    """Every STATICALLY DECIDABLE module name handed to a dynamic-import call in
    this file — including through an aliased binding of the import hook.

    BINDING-ACCURATE, not name-matching. Alias tracking mirrors the COG-4
    exec-pin idiom (lib_cog4_ast_pins `os_names`): every binding is collected
    over a FULL walk BEFORE the call scan, so binding order never matters (a
    call written above its own import still resolves). But unlike a bare
    name-match, a name only counts as a hook if the file actually BINDS it to
    one and never rebinds it to anything else — so a file with its own
    `def import_module(...)`, or `importlib = SomeClass()`, is not misread as
    reaching importlib (it would NameError at runtime otherwise).

    Recognised hook bindings:
      * the importlib MODULE — `import importlib` / `import importlib.<sub>`
        (both bind the top-level name) and `import importlib as X`. A dotted
        `import importlib.util as Y` binds the SUBMODULE, which has no
        import_module, so it is NOT a module binding.
      * the CALLABLE — `from importlib import import_module [as X]`, an
        assignment `X = <importlib-binding>.import_module`, an assignment
        `X = __import__`, and the builtin `__import__` itself (always bound
        unless the file shadows it).
    Assignment aliases resolve in one extra pass, so a chain deeper than
    `X = importlib.import_module` (e.g. an alias of an alias of an alias)
    stays undecided — conservative by construction, never a guess.

    String LITERALS are never inspected — this is an AST call scan, so a test
    fixture that merely spells a call inside a string adds no target.

    The whole file is treated as ONE namespace (a function-local `import
    importlib` counts). That over-approximates scope, never under-approximates
    it, which is the safe direction for a boundary gate.
    """
    shadowed: set[str] = set()
    mod_binds: set[str] = set()
    hooks: dict[str, str] = {}                  # name -> "import_module"|"builtin"
    deferred: list[tuple[str, str]] = []        # (bound name, importlib-binding)
    calls: list[ast.Call] = []

    for node in nodes:
        if isinstance(node, _SHADOW_NODES):
            shadowed.update(_shadowing_names(node))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == _IMPORTLIB_MODULE:
                    mod_binds.add(alias.asname or _IMPORTLIB_MODULE)
                elif (alias.name.startswith(_IMPORTLIB_MODULE + ".")
                      and alias.asname is None):
                    mod_binds.add(_IMPORTLIB_MODULE)   # dotted import binds the root
                elif alias.asname:
                    shadowed.add(alias.asname)         # any other module alias
                else:
                    shadowed.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bound = alias.asname or alias.name
                if (node.level == 0 and node.module == _IMPORTLIB_MODULE
                        and alias.name == _IMPORT_MODULE_FUNC):
                    hooks[bound] = _IMPORT_MODULE_FUNC
                else:
                    shadowed.add(bound)
        elif isinstance(node, (ast.Assign, ast.NamedExpr)):
            targets = ([node.target] if isinstance(node, ast.NamedExpr)
                       else node.targets)
            names = [n for t in targets for n in _assign_target_names(t)]
            value = node.value
            if (isinstance(value, ast.Attribute)
                    and value.attr == _IMPORT_MODULE_FUNC
                    and isinstance(value.value, ast.Name)):
                for n in names:
                    deferred.append((n, value.value.id))
            elif isinstance(value, ast.Name) and value.id == _BUILTIN_IMPORT:
                for n in names:
                    hooks[n] = _BUILTIN_IMPORT
            else:
                shadowed.update(names)
        elif isinstance(node, ast.Call):
            calls.append(node)

    # the builtin is bound in every module unless the file shadows it
    hooks.setdefault(_BUILTIN_IMPORT, _BUILTIN_IMPORT)
    mod_binds -= shadowed
    for bound, src in deferred:                 # X = <importlib>.import_module
        if src in mod_binds:
            hooks[bound] = _IMPORT_MODULE_FUNC
        else:
            shadowed.add(bound)
    hooks = {k: v for k, v in hooks.items() if k not in shadowed}

    out: list[str] = []
    for call in calls:
        func = call.func
        if isinstance(func, ast.Attribute):
            if not (func.attr == _IMPORT_MODULE_FUNC
                    and isinstance(func.value, ast.Name)
                    and func.value.id in mod_binds):
                continue
            kind = _IMPORT_MODULE_FUNC
        elif isinstance(func, ast.Name):
            kind = hooks.get(func.id)
            if kind is None:
                continue
        else:
            continue
        kwargs = {k.arg: k.value for k in call.keywords if k.arg}
        name_node = call.args[0] if call.args else kwargs.get("name")
        name = _fold_str(name_node)
        if name is None:
            continue                   # genuinely dynamic -> residual, by design
        package = None
        if kind == _IMPORT_MODULE_FUNC:
            # ONLY import_module takes a package 2nd; the builtin's 2nd
            # positional is `globals` — reading it as a package would resolve a
            # module the program never imports. Keyed off the BINDING, not the
            # spelling, so `from importlib import import_module as __import__`
            # is still treated as import_module.
            pkg_node = (call.args[1] if len(call.args) > 1
                        else kwargs.get("package"))
            package = _fold_str(pkg_node)
        target = _resolve_dyn_target(name, package)
        if target:
            out.append(target)
    return out


def _dynamic_import_targets(tree: ast.AST) -> list[str]:
    """`_dynamic_import_targets_from_nodes` over a freshly walked tree (the
    direct-from-source entry point; `_FileFacts` reuses its own single walk)."""
    return _dynamic_import_targets_from_nodes(list(ast.walk(tree)))


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


class _FileFacts:
    """Per-file scan facts, computed ONCE per scan() call: every real-import
    target (AST — string literals never count; relative imports resolved
    against the file's package path), every statically decidable DYNAMIC-import
    target (constant-folded, alias-aware), the comment-safe live lines, and the
    raw lines. Unparseable files yield zero imports (same as pre-conversion)."""

    __slots__ = ("imports", "live", "raw", "dyn_targets")

    def __init__(self, source: str, rel: str):
        self.raw: tuple[str, ...] = tuple(source.splitlines())
        self.live: tuple[str, ...] = tuple(_live_lines(source))
        imports: list[str] = []
        dyn: list[str] = []
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            tree = None
        if tree is not None:
            # ONE walk feeds both passes — the dynamic collector reuses these
            # nodes rather than re-walking (a second walk cost ~27% of scan
            # wall time on the ~1k-file repo surface).
            nodes = list(ast.walk(tree))
            for node in nodes:
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.level and not rel:
                        continue
                    imports.extend(_import_from_targets(node, rel))
            # SHORT-CIRCUIT: every hook form this pass resolves must spell
            # `import_module` or `__import__` LITERALLY somewhere in the source
            # — the call site for the plain spellings, the binding line for
            # every alias. So a source containing neither can have no target,
            # and the walk is skipped. Semantics-free, ~40% of scan time back.
            if _IMPORT_MODULE_FUNC in source or _BUILTIN_IMPORT in source:
                dyn = _dynamic_import_targets_from_nodes(nodes)
        self.imports = tuple(imports)
        self.dyn_targets = tuple(dyn)


# ---------------------------------------------------------------------------
# the scan — five generic check shapes over the rows
# ---------------------------------------------------------------------------

def scan(root, config: BoundaryConfig | None = None) -> list[str]:
    """Return the sorted list of `<rel-path>:<RULE>` violations under `root`.
    Empty list == every declared boundary intact."""
    cfg = config if config is not None else _CONFIG
    root = Path(root)
    violations: set[str] = set()
    flagged: set[str] = set()          # paths already given a specific rule
    facts_cache: dict[str, _FileFacts] = {}

    def facts_for(path: Path, rel: str) -> _FileFacts:
        got = facts_cache.get(rel)
        if got is None:
            got = facts_cache[rel] = _FileFacts(_read(path), rel)
        return got

    module_rows = cfg.module_rows()

    # --- Check 1: each row's forbidden authority/action surface -------------
    for row in module_rows:
        for entry in row.forbidden_importers:
            for path in _py_files(root / entry):
                rel = _rel(root, path)
                f = facts_for(path, rel)
                if any(row.is_module_of_token(n) for n in f.imports):
                    violations.add(f"{rel}:{row.rule_ids['forbidden_import']}")
                    flagged.add(rel)
                # the token backstop, plus the folded/aliased dynamic forms the
                # contiguous-literal regex cannot see. Same rule id the literal
                # dynamic spelling already carries here — attribution unmoved.
                if (any(row.backstop.search(l) for l in f.live)
                        or any(row.is_module_of_token(n) for n in f.dyn_targets)):
                    violations.add(f"{rel}:{row.rule_ids['forbidden_token']}")
                    flagged.add(rel)

    # --- Check 2: per-row falsifier total-import bans (C-F17) ---------------
    for row in module_rows:
        for fal in row.falsifier_exact:
            fpath = root / fal
            if not fpath.is_file():
                continue
            rel = _rel(root, fpath)
            f = facts_for(fpath, rel)
            if (any(row.is_module_of_token(n) for n in f.imports)
                    or any(row.falsifier_import_line.search(l) for l in f.raw)
                    or any(row.falsifier_dynamic.search(l) for l in f.live)
                    or any(row.is_module_of_token(n) for n in f.dyn_targets)):
                violations.add(f"{rel}:{row.rule_ids['falsifier']}")
                flagged.add(rel)

    # --- Check R: reverse direction — a row's internal tree may never import
    #     its reverse_forbidden trees (AST + the narrow dynamic complement) ---
    for row in module_rows:
        if not row.reverse_forbidden:
            continue
        for path in _py_files(root / row.internal_prefix.rstrip("/")):
            rel = _rel(root, path)
            f = facts_for(path, rel)
            if (any(row.is_reverse_module(n) for n in f.imports)
                    or any(row.reverse_dynamic.search(l) for l in f.live)
                    or any(row.is_reverse_module(n) for n in f.dyn_targets)):
                violations.add(f"{rel}:{row.rule_ids['reverse']}")
                flagged.add(rel)

    # --- the global sweep surface, enumerated once --------------------------
    swept: list[tuple[str, Path]] = []
    for tree in cfg.sweep_trees:
        for path in _py_files(root / tree):
            swept.append((_rel(root, path), path))

    # --- Check 3: per-row un-curated importer sweeps ------------------------
    # A file already carrying a specific rule (flagged) is not double-flagged
    # as merely un-curated; row-internal files and curated readers fold clean.
    for row in module_rows:
        if not row.sweep:
            continue
        for rel, path in swept:
            if rel in flagged or row.is_internal(rel) or row.is_allowlisted(rel):
                continue
            f = facts_for(path, rel)
            if (any(row.is_module_of_token(n) for n in f.imports)
                    or any(row.dynamic.search(l) for l in f.live)
                    or any(row.is_module_of_token(n) for n in f.dyn_targets)):
                violations.add(f"{rel}:{row.rule_ids['unallowlisted']}")

    # --- Check D: data-plane store sweeps -----------------------------------
    # Independent of `flagged` (a file may both import AND open a store).
    for row in cfg.data_plane_rows():
        for rel, path in swept:
            if row.is_internal(rel) or row.is_allowlisted(rel):
                continue
            f = facts_for(path, rel)
            if any(row.token in l for l in f.live):
                violations.add(f"{rel}:{row.rule_ids['data_plane']}")

    return sorted(violations)


# ---------------------------------------------------------------------------
# module-level law + back-compat surface (derived from the manifest — the
# pre-conversion constant names stay importable for the existing suites)
# ---------------------------------------------------------------------------

_CONFIG = load_config()

_CORTEX_ROW = _CONFIG.row_for_token("framework.cortex")
_OBJECTIVES_ROW = _CONFIG.row_for_token("framework.objectives")
# the objectives store row, selected structurally (its token never appears
# contiguously in this file — the assembled-token discipline, kept).
_OBJ_DATAPLANE_ROW = next(
    r for r in _CONFIG.data_plane_rows()
    if r.internal_prefix == _OBJECTIVES_ROW.internal_prefix)

CORTEX = _CORTEX_ROW.token
OBJECTIVES = _OBJECTIVES_ROW.token

SWEEP_TREES = list(_CONFIG.sweep_trees)
FORBIDDEN_TREES = [e for e in _CORTEX_ROW.forbidden_importers
                   if not e.endswith(".py")]
FORBIDDEN_FILES = [e for e in _CORTEX_ROW.forbidden_importers
                   if e.endswith(".py")]
FALSIFIER = _CORTEX_ROW.falsifier_exact[0]

CORTEX_INTERNAL = _CORTEX_ROW.internal_prefix
ALLOWLIST_EXACT = set(_CORTEX_ROW.allowlist_exact)
ALLOWLIST_GLOBS = list(_CORTEX_ROW.allowlist_globs)

OBJECTIVES_INTERNAL = _OBJECTIVES_ROW.internal_prefix
ALLOWLIST_EXACT_OBJECTIVES = set(_OBJECTIVES_ROW.allowlist_exact)
ALLOWLIST_GLOBS_OBJECTIVES = list(_OBJECTIVES_ROW.allowlist_globs)
ACTION_PLANE = tuple(t.replace("/", ".")
                     for t in _OBJECTIVES_ROW.reverse_forbidden)

RULE_FORBIDDEN = _CORTEX_ROW.rule_ids["forbidden_import"]
RULE_TOKEN = _CORTEX_ROW.rule_ids["forbidden_token"]
RULE_FALSIFIER = _CORTEX_ROW.rule_ids["falsifier"]
RULE_UNALLOWLISTED = _CORTEX_ROW.rule_ids["unallowlisted"]
RULE_FORBIDDEN_OBJ = _OBJECTIVES_ROW.rule_ids["forbidden_import"]
RULE_TOKEN_OBJ = _OBJECTIVES_ROW.rule_ids["forbidden_token"]
RULE_OBJ_IMPORTS_ACTION = _OBJECTIVES_ROW.rule_ids["reverse"]
RULE_UNALLOWLISTED_OBJ = _OBJECTIVES_ROW.rule_ids["unallowlisted"]
RULE_OBJ_DATAPLANE = _OBJ_DATAPLANE_ROW.rule_ids["data_plane"]


def _is_allowlisted(rel: str) -> bool:
    """Back-compat: membership in the cortex row's curated-reader set (the
    pre-conversion Check-3 union of cog2 + cog3 readers, now declared on the
    row itself)."""
    return _CORTEX_ROW.is_allowlisted(rel)


# ---------------------------------------------------------------------------
# CLI (contract preserved: check / --report / --json, exit 1 on breach)
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Declarative boundary-manifest import gate (COG-4 §8; "
                    "COG-2 §7.1 cortex + COG-3 §6.5 objectives + COG-4 rows).")
    parser.add_argument("--root", type=Path, default=REPO_DEFAULT,
                        help="repo root to scan (default: this script's repo).")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH,
                        help="boundary manifest to enforce (default: the "
                             "repo's cabinet/config/boundary-manifest.yml).")
    parser.add_argument("--report", action="store_true",
                        help="list every violation and exit 0.")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON.")
    args = parser.parse_args(argv)

    config = (_CONFIG if Path(args.manifest) == MANIFEST_PATH
              else load_config(args.manifest))
    violations = scan(args.root, config=config)

    if args.json:
        print(json.dumps({"violations": violations, "count": len(violations)},
                         indent=2))
    elif violations:
        stream = sys.stdout if args.report else sys.stderr
        print(f"[cog2-import-gate] {len(violations)} violation(s) — a declared "
              "boundary row is breached (row law: "
              "cabinet/config/boundary-manifest.yml):", file=stream)
        for v in violations:
            print(f"  + {v}", file=stream)
        if not args.report:
            print("[cog2-import-gate] FAIL — remove the import/reference; "
                  "fenced stores and shadow models are read ONLY through "
                  "their curated CLIs and tests.", file=sys.stderr)
    else:
        print("[cog2-import-gate] OK — no authority/action code imports the "
              "cortex or objectives shadow models (shadow boundary intact).")

    if args.report:
        return 0
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
