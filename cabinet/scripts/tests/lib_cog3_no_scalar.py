"""lib_cog3_no_scalar.py — the P12 no-scalar ratchet scanners (contract §6.6 P12 /
N3), pure stdlib `ast` + `json`. Helper, not a test.

The standing law: a value surface that can NEVER collapse to a scalar. Scans
framework/objectives/**.py and (when present) framework/schemas/domains/objectives/*.json
for the named scalar-leakage patterns, all green-by-vacuity while the package is
absent:

  SCALAR_ACCESSOR      a def named total / total_value / score / __float__ /
                       composite / composite_score / aggregate / overall / fitness
                       / … — a bare single-number valuation of node/edge/graph or a
                       scorecard aggregation-to-one-number
  OVI_COMPOSITE        framework/objectives/ovi_view.py referencing composite_score
                       / composite / weights / weight — the per-instrument projection
                       structurally REFUSES any composite/weighted aggregate (attack C-M4)
  NUMERIC_EDGE_WEIGHT  a numeric edge-weight field — an `edge_weight`/`numeric_weight`
                       identifier or a `{"weight": <number>}` literal in code, or a
                       schema property weight/edge_weight/numeric_weight typed number/integer

HONEST LIMITATION (attack G-m4, mirroring EVAL-025 C2 / test_cog2_contradiction
verbatim-in-spirit): token/AST scans are evadable by dynamically-constructed
accessors (getattr walks, a scalar assembled at runtime, an aggregate built
through a helper). Evasion IS the violation; this scan is the TRIPWIRE, not the
definition. The later reader-wiring phase inherits the ratchet and must amend it
CONSCIOUSLY — never widen it silently.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

RULE_SCALAR = "SCALAR_ACCESSOR"
RULE_OVI = "OVI_COMPOSITE"
RULE_WEIGHT = "NUMERIC_EDGE_WEIGHT"

# a def with any of these names is a bare scalar valuation / aggregation-to-one.
FORBIDDEN_ACCESSOR_NAMES = frozenset({
    "total", "total_value", "score", "scalar", "scalar_value", "__float__",
    "fitness", "composite", "composite_score", "aggregate", "aggregate_value",
    "overall", "overall_score", "weighted_sum", "sum_value", "sort_by_fitness",
    "rank_by_fitness", "to_scalar", "as_scalar",
})
# in ovi_view.py the per-instrument projection refuses any composite/weight.
OVI_FORBIDDEN = frozenset({"composite_score", "composite", "weights", "weight"})
# numeric edge-weight identifiers in code.
WEIGHT_IDENTS = frozenset({"edge_weight", "numeric_weight"})
# schema property names that would carry a numeric edge weight.
WEIGHT_SCHEMA_PROPS = frozenset({"weight", "edge_weight", "numeric_weight"})
NUMERIC_JSON_TYPES = frozenset({"number", "integer"})


def objectives_dir(root) -> Path:
    return Path(root) / "framework" / "objectives"


def schemas_dir(root) -> Path:
    return Path(root) / "framework" / "schemas" / "domains" / "objectives"


def _py_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.py") if p.is_file())


def _parse(source: str):
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError):
        return None


def _rel(repo: Path, path: Path) -> str:
    return path.relative_to(repo).as_posix()


# --- SCALAR_ACCESSOR --------------------------------------------------------

def scalar_accessor_violations(root) -> list[str]:
    repo = Path(root)
    out: list[str] = []
    for path in _py_files(objectives_dir(root)):
        tree = _parse(path.read_text(encoding="utf-8", errors="replace"))
        if tree is None:
            continue
        rel = _rel(repo, path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in FORBIDDEN_ACCESSOR_NAMES:
                    out.append(f"{rel}:{RULE_SCALAR}:{node.name}")
    return out


# --- OVI_COMPOSITE ----------------------------------------------------------

def _idents_used(tree) -> set[str]:
    """Every structural identifier that could NAME a composite/weight: Name ids,
    Attribute attrs, keyword/arg names, def names, and dict STRING keys. Docstrings
    and comments are NOT structural here, so they never false-positive."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg:
            found.add(node.arg)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.add(node.name)
        elif isinstance(node, ast.Dict):
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    found.add(k.value)
    return found


def ovi_composite_violations(root) -> list[str]:
    repo = Path(root)
    ovi = objectives_dir(root) / "ovi_view.py"
    if not ovi.is_file():
        return []
    tree = _parse(ovi.read_text(encoding="utf-8", errors="replace"))
    if tree is None:
        return []
    rel = _rel(repo, ovi)
    hits = sorted(_idents_used(tree) & OVI_FORBIDDEN)
    return [f"{rel}:{RULE_OVI}:{h}" for h in hits]


# --- NUMERIC_EDGE_WEIGHT ----------------------------------------------------

def _numeric_weight_in_code(tree, rel: str) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        # an assignment/annotation/def that NAMES a numeric weight identifier.
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id in WEIGHT_IDENTS:
                    out.append(f"{rel}:{RULE_WEIGHT}:{tgt.id}")
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id in WEIGHT_IDENTS:
                out.append(f"{rel}:{RULE_WEIGHT}:{node.target.id}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in WEIGHT_IDENTS:
                out.append(f"{rel}:{RULE_WEIGHT}:{node.name}")
        # a `{"weight": <number>}` literal — a numeric edge weight by construction.
        elif isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if (isinstance(k, ast.Constant) and isinstance(k.value, str)
                        and k.value in WEIGHT_SCHEMA_PROPS
                        and isinstance(v, ast.Constant)
                        and isinstance(v.value, (int, float))
                        and not isinstance(v.value, bool)):
                    out.append(f"{rel}:{RULE_WEIGHT}:{k.value}={v.value}")
    return out


def _numeric_weight_in_schema(obj, rel: str) -> list[str]:
    """Recurse a JSON schema for a `properties` object whose key is a weight name
    typed number/integer."""
    out: list[str] = []
    if isinstance(obj, dict):
        props = obj.get("properties")
        if isinstance(props, dict):
            for name, spec in props.items():
                if name in WEIGHT_SCHEMA_PROPS and isinstance(spec, dict):
                    t = spec.get("type")
                    types = {t} if isinstance(t, str) else set(t or [])
                    if types & NUMERIC_JSON_TYPES:
                        out.append(f"{rel}:{RULE_WEIGHT}:schema:{name}")
        for v in obj.values():
            out += _numeric_weight_in_schema(v, rel)
    elif isinstance(obj, list):
        for v in obj:
            out += _numeric_weight_in_schema(v, rel)
    return out


def numeric_weight_violations(root) -> list[str]:
    repo = Path(root)
    out: list[str] = []
    for path in _py_files(objectives_dir(root)):
        tree = _parse(path.read_text(encoding="utf-8", errors="replace"))
        if tree is not None:
            out += _numeric_weight_in_code(tree, _rel(repo, path))
    sd = schemas_dir(root)
    if sd.is_dir():
        for path in sorted(sd.rglob("*.json")):
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            out += _numeric_weight_in_schema(obj, _rel(repo, path))
    return out


def ratchet_violations(root) -> list[str]:
    """The full P12 ratchet: every scalar-leakage pattern, sorted. Empty == the
    no-scalar law holds over framework/objectives/ (+ its schemas when present)."""
    return sorted(scalar_accessor_violations(root)
                  + ovi_composite_violations(root)
                  + numeric_weight_violations(root))
