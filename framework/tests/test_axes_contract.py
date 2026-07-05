"""The axis linter — "axes are data, never branches" made mechanical [AX-6].

Axes spec (docs/plans/cabinet-axes-spec-2026-07-05.md §6.1/§6.4/§6.5): the
three axes (autonomy_level, flavor, deployment_target) are DATA consumed
through resolvers and tables. This module is BOTH:

  * the linter ENGINE — an AST walk that flags any comparison (or match/case)
    binding an axis-named identifier (posture, posture_name, autonomy_level,
    flavor, deployment_target, level, postures — bare name, attribute,
    mapping subscript, or ``.get("...")`` call) to an axis value (earn_up,
    guardian, sovereign, personal, org, macbook, mac_mini, docker — a string
    literal, a canonical constant Name/Attribute like ``SOVEREIGN`` /
    ``P.GUARDIAN``, or a tuple/list/set/frozenset of those) outside the
    germline allowlist ``framework/policies/axes-allowlist.yml``;
  * the CI test suite that runs it over ``framework/`` (tests/ dirs skipped)
    plus the enforcing spine for golden eval-020 (linter + allowlist exist,
    tree green, allowlist ⊆ immutable-core with the pending-entry xfail) and
    the ``validate-extension.sh`` end-to-end probes.

FAIL-CLOSED (Corridor): a corrupt/unknown-keyed/malformed allowlist loads as
the EMPTY allowlist (maximum strictness — CI red rather than a silently
widened branching surface); an unparseable .py is a violation, not a skip.
Symlink/traversal-safe (Corridor): every scanned file must
``os.path.realpath``-resolve INSIDE the realpath of the scanned root — a
symlink escaping the tree is itself reported, never followed or ignored.

CLI mode (used by cabinet/scripts/validate-extension.sh to scan an extension
dir with the strict EMPTY allowlist — extensions receive resolved axis
values, they never read axis config):

    python3 framework/tests/test_axes_contract.py --scan <dir> \
        [--allowlist <yml>] [--rel-to <dir>]

The CLI must run under the system python3 (3.9, possibly without pytest), so
the pytest import is guarded and the engine is stdlib-only.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple

try:  # CLI mode (validate-extension.sh) runs without pytest installed
    import pytest
except ImportError:  # pragma: no cover — never the pytest-collected path
    pytest = None  # type: ignore[assignment]

_REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# The closed axis vocabulary (spec §0; lanes consume, never redefine)
# ---------------------------------------------------------------------------

AXIS_NAMES = frozenset({
    "posture", "posture_name", "autonomy_level", "flavor",
    "deployment_target", "level", "postures",
})
AXIS_VALUES = frozenset({
    "earn_up", "guardian", "sovereign",           # autonomy_level
    "personal", "org",                            # flavor
    "macbook", "mac_mini", "docker",              # deployment_target
})

ALLOWLIST_PATH = _REPO_ROOT / "framework" / "policies" / "axes-allowlist.yml"
_ALLOWLIST_ENTRY_KEYS = {"path", "why", "pending"}

# (display_path, lineno, message)
Violation = Tuple[str, int, str]


# ---------------------------------------------------------------------------
# AST predicates
# ---------------------------------------------------------------------------

def _terminal_identifier(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_axis_named(node: ast.AST) -> bool:
    """One comparison side "binds an axis" when it reads an axis-named
    identifier: bare/attribute name, ``x["posture"]``, or ``x.get("posture")``.
    """
    ident = _terminal_identifier(node)
    if ident is not None and ident in AXIS_NAMES:
        return True
    if isinstance(node, ast.Subscript):
        key = node.slice
        return (isinstance(key, ast.Constant) and isinstance(key.value, str)
                and key.value in AXIS_NAMES)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get" and node.args):
        first = node.args[0]
        return (isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and first.value in AXIS_NAMES)
    return False


def _is_axis_value(node: ast.AST) -> bool:
    """The other side references a concrete axis value: a string literal, a
    canonical constant name (``SOVEREIGN``, ``P.GUARDIAN``, ``MAC_MINI`` —
    branching via imported constants is exactly as much an axis branch), or a
    container of those (``in ("personal", "org")``)."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str) and node.value in AXIS_VALUES
    ident = _terminal_identifier(node)
    if ident is not None and ident.lower() in AXIS_VALUES:
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return any(_is_axis_value(e) for e in node.elts)
    if (isinstance(node, ast.Call) and node.args
            and _terminal_identifier(node.func) in (
                "frozenset", "set", "tuple", "list")):
        return any(_is_axis_value(a) for a in node.args)
    return False


def _describe(node: ast.AST) -> str:
    values = sorted({
        n.value for n in ast.walk(node)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and n.value in AXIS_VALUES
    } | {
        ident.lower() for n in ast.walk(node)
        for ident in (_terminal_identifier(n),)
        if ident is not None and ident.lower() in AXIS_VALUES
    })
    return (
        "axis branch: compares an axis identifier to axis value(s) "
        "%s — axes are data; only the germline allowlist "
        "(framework/policies/axes-allowlist.yml) may branch" % values
    )


def scan_source(text: str, filename: str = "<source>") -> List[Tuple[int, str]]:
    """(lineno, message) for every axis branch in one python source."""
    tree = ast.parse(text, filename=filename)
    hits = []  # type: List[Tuple[int, str]]
    match_node = getattr(ast, "Match", None)  # absent on 3.9
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            sides = [node.left] + list(node.comparators)
            if any(_is_axis_named(s) for s in sides) and \
                    any(_is_axis_value(s) for s in sides):
                hits.append((node.lineno, _describe(node)))
        elif match_node is not None and isinstance(node, match_node):
            if _is_axis_named(node.subject) and any(
                isinstance(p, ast.MatchValue) and _is_axis_value(p.value)
                for case in node.cases for p in ast.walk(case.pattern)
            ):
                hits.append((node.lineno, _describe(node)))
    return hits


# ---------------------------------------------------------------------------
# Tree walk (tests/ skipped; symlink-escape refused)
# ---------------------------------------------------------------------------

def iter_source_files(root: Path) -> Iterator[Path]:
    for p in sorted(Path(root).rglob("*.py")):
        parts = p.relative_to(root).parts
        if "__pycache__" in parts:
            continue
        if "tests" in parts[:-1]:  # any tests/ DIRECTORY segment
            continue
        yield p


def scan_tree(
    root,  # type: str | Path
    allowlist=frozenset(),  # type: frozenset
    rel_to=None,  # type: Optional[str | Path]
) -> List[Violation]:
    """Lint every .py under `root`. `allowlist` holds paths relative to
    `rel_to` (default: `root` itself) that are sanctioned to branch."""
    root = Path(root)
    base = Path(rel_to) if rel_to is not None else root
    real_root = os.path.realpath(str(root))
    violations = []  # type: List[Violation]
    for p in iter_source_files(root):
        try:
            display = p.relative_to(base).as_posix()
        except ValueError:
            display = p.as_posix()
        rp = os.path.realpath(str(p))
        if rp != real_root and not rp.startswith(real_root + os.sep):
            violations.append((
                display, 0,
                "resolves outside the scanned tree (symlink escape) — refused",
            ))
            continue
        if display in allowlist:
            continue
        try:
            text = p.read_text()
            hits = scan_source(text, filename=str(p))
        except (SyntaxError, ValueError, OSError) as exc:
            violations.append(
                (display, 0, "unparseable python (fail-closed): %s" % exc))
            continue
        for lineno, msg in hits:
            violations.append((display, lineno, msg))
    return violations


# ---------------------------------------------------------------------------
# Allowlist (fail-closed: ANY malformation ⇒ empty ⇒ maximum strictness)
# ---------------------------------------------------------------------------

def load_allowlist_entries(path=None) -> Optional[List[dict]]:
    """The validated allowlist entries [{path, why, pending}], or None on any
    malformation — closed keys, repo-relative POSIX paths only (no absolute,
    no "..", no backslash). Callers must treat None as the empty allowlist."""
    p = Path(path) if path is not None else ALLOWLIST_PATH
    try:
        import yaml  # deferred — CLI --scan mode never needs it
        data = yaml.safe_load(p.read_text())
    except Exception:
        return None
    if not isinstance(data, dict) or set(data) != {"version", "allowed"}:
        return None
    if data["version"] != 1 or isinstance(data["version"], bool):
        return None
    if not isinstance(data["allowed"], list):
        return None
    out = []  # type: List[dict]
    for entry in data["allowed"]:
        if not isinstance(entry, dict):
            return None
        if set(entry) - _ALLOWLIST_ENTRY_KEYS or not {"path", "why"} <= set(entry):
            return None
        rel = entry["path"]
        if not isinstance(rel, str) or not rel.strip():
            return None
        if rel.startswith(("/", "~")) or "\\" in rel or ".." in Path(rel).parts:
            return None
        if not isinstance(entry["why"], str) or not entry["why"].strip():
            return None
        pend = entry.get("pending")
        if pend is not None and (not isinstance(pend, str) or not pend.strip()):
            return None
        out.append({"path": rel, "why": entry["why"], "pending": pend})
    return out


def load_allowlist(path=None) -> frozenset:
    entries = load_allowlist_entries(path)
    if entries is None:
        return frozenset()
    return frozenset(e["path"] for e in entries)


# ---------------------------------------------------------------------------
# CLI (validate-extension.sh: strict scan of an extension dir)
# ---------------------------------------------------------------------------

def _main(argv: List[str]) -> int:
    scan_dir = None
    allowlist_file = None
    rel_to = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--scan" and i + 1 < len(argv):
            scan_dir = argv[i + 1]
            i += 2
        elif arg == "--allowlist" and i + 1 < len(argv):
            allowlist_file = argv[i + 1]
            i += 2
        elif arg == "--rel-to" and i + 1 < len(argv):
            rel_to = argv[i + 1]
            i += 2
        else:
            scan_dir = None
            break
    if scan_dir is None or not os.path.isdir(scan_dir):
        sys.stderr.write(
            "usage: test_axes_contract.py --scan <dir> "
            "[--allowlist <yml>] [--rel-to <dir>]\n")
        return 2
    allowlist = load_allowlist(allowlist_file) if allowlist_file else frozenset()
    violations = scan_tree(scan_dir, allowlist=allowlist, rel_to=rel_to)
    for path, lineno, msg in violations:
        sys.stderr.write("%s:%d: %s\n" % (path, lineno, msg))
    return 1 if violations else 0


if __name__ == "__main__":  # pragma: no cover — CLI entrypoint
    sys.exit(_main(sys.argv[1:]))


# ===========================================================================
# Tests (pytest-only from here down; the CLI path never reaches them)
# ===========================================================================

_SCHEMA_PATH = _REPO_ROOT / "framework" / "schemas" / "extension-manifest.schema.json"
_VALIDATE_SH = _REPO_ROOT / "cabinet" / "scripts" / "validate-extension.sh"
_IMMUTABLE_CORE = _REPO_ROOT / "framework" / "policies" / "immutable-core.yml"
_EVAL_020 = _REPO_ROOT / "memory" / "golden-evals" / "eval-020-axes-contract.md"


def _write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


class TestAxisLinterEngine:
    def test_detects_literal_and_constant_axis_branches(self, tmp_path):
        src = (
            'MAC_MINI = "mac_mini"\n'
            'def f(posture, flavor, cfg, deployment_target):\n'
            '    if posture == "sovereign":\n'                       # 3
            '        pass\n'
            '    ok = flavor in ("personal", "org")\n'               # 5
            '    if cfg["deployment_target"] == "docker":\n'         # 6
            '        pass\n'
            '    if cfg.get("posture") == "earn_up":\n'              # 8
            '        pass\n'
            '    if deployment_target != MAC_MINI:\n'                # 10
            '        pass\n'
            '    return ok\n'
        )
        _write(tmp_path / "bad.py", src)
        violations = scan_tree(tmp_path)
        linenos = sorted(v[1] for v in violations)
        assert linenos == [3, 5, 6, 8, 10], violations

    def test_match_case_on_axis_value_detected(self, tmp_path):
        _write(tmp_path / "m.py", (
            "def f(posture):\n"
            "    match posture:\n"
            '        case "sovereign":\n'
            "            return 1\n"
            "        case _:\n"
            "            return 0\n"
        ))
        assert len(scan_tree(tmp_path)) == 1

    def test_ignores_benign_comparisons(self, tmp_path):
        _write(tmp_path / "ok.py", (
            'def f(posture, state, level, kind, known_tables):\n'
            '    if state == "graduated":\n'
            '        pass\n'
            '    if posture in known_tables:\n'      # no literal value side
            '        pass\n'
            '    if level >= 3:\n'
            '        pass\n'
            '    if kind == "channel":\n'            # not an axis identifier
            '        pass\n'
            '    return posture\n'
        ))
        assert scan_tree(tmp_path) == []

    def test_skips_tests_dirs_and_flags_unparseable(self, tmp_path):
        _write(tmp_path / "pkg" / "tests" / "test_x.py",
               'def f(posture):\n    return posture == "sovereign"\n')
        _write(tmp_path / "broken.py", "def (\n")
        violations = scan_tree(tmp_path)
        assert len(violations) == 1
        assert violations[0][0] == "broken.py"
        assert "unparseable" in violations[0][2]

    def test_symlink_escape_is_refused_not_followed(self, tmp_path):
        outside = _write(tmp_path / "outside" / "evil.py", "x = 1\n")
        root = tmp_path / "ext"
        root.mkdir()
        os.symlink(outside, root / "linked.py")
        violations = scan_tree(root)
        assert len(violations) == 1
        assert "symlink escape" in violations[0][2]

    def test_allowlisted_path_is_skipped(self, tmp_path):
        _write(tmp_path / "sub" / "kernel.py",
               'def f(posture):\n    return posture == "guardian"\n')
        assert scan_tree(tmp_path) != []
        assert scan_tree(tmp_path, allowlist=frozenset({"sub/kernel.py"})) == []


class TestAllowlistFailClosed:
    def test_absent_and_unparseable_load_empty(self, tmp_path):
        assert load_allowlist(tmp_path / "nope.yml") == frozenset()
        p = _write(tmp_path / "bad.yml", "allowed: [unclosed")
        assert load_allowlist(p) == frozenset()

    @pytest.mark.parametrize("payload", [
        # unknown top-level key
        {"version": 1, "allowed": [], "extra": True},
        # missing version
        {"allowed": [{"path": "a.py", "why": "x"}]},
        # unknown entry key
        {"version": 1, "allowed": [{"path": "a.py", "why": "x", "who": "me"}]},
        # missing why
        {"version": 1, "allowed": [{"path": "a.py"}]},
        # absolute path
        {"version": 1, "allowed": [{"path": "/etc/passwd", "why": "x"}]},
        # traversal
        {"version": 1, "allowed": [{"path": "../escape.py", "why": "x"}]},
        # non-dict entry
        {"version": 1, "allowed": ["a.py"]},
    ])
    def test_any_malformation_loads_empty(self, tmp_path, payload):
        import yaml
        p = _write(tmp_path / "list.yml", yaml.safe_dump(payload))
        assert load_allowlist(p) == frozenset()
        assert load_allowlist_entries(p) is None

    def test_valid_allowlist_loads_paths(self, tmp_path):
        import yaml
        p = _write(tmp_path / "list.yml", yaml.safe_dump({
            "version": 1,
            "allowed": [
                {"path": "a/b.py", "why": "sanctioned"},
                {"path": "c.py", "why": "sanctioned", "pending": "AX-9"},
            ],
        }))
        assert load_allowlist(p) == frozenset({"a/b.py", "c.py"})

    def test_shipped_allowlist_entry_existence_discipline(self):
        """Non-pending entries must exist on disk (a vanished sanctioned
        module is allowlist rot); `pending:` entries — whose Ring-0 wiring is
        still owed (see the subset test) — may be forward declarations."""
        entries = load_allowlist_entries()
        assert entries, "shipped allowlist must load (fail-closed loader)"
        for e in entries:
            if e["pending"] is None:
                assert (_REPO_ROOT / e["path"]).exists(), (
                    "allowlist entry missing on disk: %s" % e["path"])


class TestFrameworkTreeContract:
    def test_engine_fires_on_the_sanctioned_kernels(self):
        """Sanity: with an EMPTY allowlist the linter finds the known axis
        branches (posture.py at least), and every hit is an allowlisted path —
        guards against a broken engine passing vacuously."""
        strict = scan_tree(_REPO_ROOT / "framework", rel_to=_REPO_ROOT)
        hit_paths = {v[0] for v in strict}
        assert "framework/authority/posture.py" in hit_paths
        assert hit_paths <= load_allowlist(), (
            "framework files branching on axis values outside the allowlist: "
            "%s" % sorted(hit_paths - load_allowlist())
        )

    def test_framework_tree_green_with_allowlist(self):
        violations = scan_tree(
            _REPO_ROOT / "framework",
            allowlist=load_allowlist(),
            rel_to=_REPO_ROOT,
        )
        assert violations == [], (
            "axis branches outside framework/policies/axes-allowlist.yml "
            "(axes are data — spec §6.1): %s"
            % ["%s:%d" % (v[0], v[1]) for v in violations]
        )


class TestExtensionManifestSchema:
    def _schema(self) -> dict:
        return json.loads(_SCHEMA_PATH.read_text())

    def test_schema_shape_and_closed_keys(self):
        schema = self._schema()
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == {
            "name", "version", "kind", "action_types", "risk_classes",
            "undo_contract", "entrypoints",
        }
        assert set(schema["properties"]["kind"]["enum"]) == {
            "channel", "source", "skill", "mcp",
        }
        assert schema["properties"]["undo_contract"]["pattern"] == \
            r"^(none|delete_window\([0-9]+\))$"

    def test_risk_class_enum_pinned_to_matrix_vocab(self):
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        from framework.authority.matrix import RISK_CLASSES
        schema = self._schema()
        enum = schema["properties"]["risk_classes"]["items"]["enum"]
        assert set(enum) == set(RISK_CLASSES)
        assert enum == sorted(enum), "keep the enum sorted (drift-diffable)"

    def test_axis_compat_enums_pinned_to_posture_vocab(self):
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        from framework.authority.posture import (
            DEPLOYMENT_TARGETS, FLAVORS, POSTURES,
        )
        compat = self._schema()["properties"]["axis_compat"]
        assert compat["additionalProperties"] is False
        props = compat["properties"]
        assert set(props) == {"autonomy_level", "flavor", "deployment_target"}
        assert set(props["autonomy_level"]["items"]["enum"]) == set(POSTURES)
        assert set(props["flavor"]["items"]["enum"]) == set(FLAVORS)
        assert set(props["deployment_target"]["items"]["enum"]) == \
            set(DEPLOYMENT_TARGETS)


class TestValidateExtensionScript:
    """End-to-end probes of cabinet/scripts/validate-extension.sh (§6.4):
    manifest schema + realpath containment + strict axis lint."""

    def _ext(self, tmp_path: Path, manifest: Optional[dict] = None) -> Path:
        import yaml
        ext = tmp_path / "ext"
        _write(ext / "adapter.py", (
            "def send(recipient, body, thread_id, resolved_axes):\n"
            "    # extensions RECEIVE resolved axis values — no axis reads\n"
            "    return 'artifact-1'\n"
        ))
        if manifest is None:
            manifest = {
                "name": "slack-adapter",
                "version": "0.1.0",
                "kind": "channel",
                "action_types": ["internal_message"],
                "risk_classes": ["internal_comms"],
                "undo_contract": "delete_window(600)",
                "entrypoints": {"send": "adapter.py"},
            }
        _write(ext / "manifest.yml", yaml.safe_dump(manifest))
        return ext

    def _run(self, ext: Path) -> "subprocess.CompletedProcess":
        return subprocess.run(
            ["bash", str(_VALIDATE_SH), str(ext)],
            capture_output=True, text=True, timeout=120,
        )

    def test_valid_extension_passes(self, tmp_path):
        r = self._run(self._ext(tmp_path))
        assert r.returncode == 0, r.stdout + r.stderr

    def test_axis_branching_extension_refused(self, tmp_path):
        ext = self._ext(tmp_path)
        _write(ext / "adapter2.py", (
            "def pick(posture):\n"
            "    if posture == 'sovereign':\n"
            "        return 'wide'\n"
            "    return 'narrow'\n"
        ))
        r = self._run(ext)
        assert r.returncode != 0
        assert "axis" in (r.stdout + r.stderr).lower()

    def test_entrypoint_traversal_refused(self, tmp_path):
        _write(tmp_path / "outside.py", "x = 1\n")
        ext = self._ext(tmp_path)
        import yaml
        (ext / "manifest.yml").write_text(yaml.safe_dump({
            "name": "sneaky", "version": "0.1.0", "kind": "skill",
            "action_types": [], "risk_classes": [],
            "undo_contract": "none",
            "entrypoints": {"run": "../outside.py"},
        }))
        r = self._run(ext)
        assert r.returncode != 0
        assert "outside the extension dir" in (r.stdout + r.stderr)

    def test_symlinked_manifest_refused(self, tmp_path):
        import yaml
        real = _write(tmp_path / "elsewhere" / "manifest.yml", yaml.safe_dump({
            "name": "linked", "version": "0.1.0", "kind": "skill",
            "action_types": [], "risk_classes": [],
            "undo_contract": "none", "entrypoints": {"run": "adapter.py"},
        }))
        ext = self._ext(tmp_path)
        (ext / "manifest.yml").unlink()
        os.symlink(real, ext / "manifest.yml")
        r = self._run(ext)
        assert r.returncode != 0
        assert "symlink" in (r.stdout + r.stderr)

    def test_missing_manifest_refused(self, tmp_path):
        ext = self._ext(tmp_path)
        (ext / "manifest.yml").unlink()
        r = self._run(ext)
        assert r.returncode != 0
        assert "manifest" in (r.stdout + r.stderr)

    @pytest.mark.parametrize("mutate", [
        lambda m: m.update(kind="webhook"),                    # bad enum
        lambda m: m.update(extra_key="nope"),                  # unknown key
        lambda m: m.update(undo_contract="delete_window(x)"),  # bad pattern
        lambda m: m.update(risk_classes=["not_a_class"]),      # bad enum item
        lambda m: m.pop("version"),                            # missing key
    ])
    def test_schema_invalid_manifest_refused(self, tmp_path, mutate):
        manifest = {
            "name": "slack-adapter", "version": "0.1.0", "kind": "channel",
            "action_types": ["internal_message"],
            "risk_classes": ["internal_comms"],
            "undo_contract": "delete_window(600)",
            "entrypoints": {"send": "adapter.py"},
        }
        mutate(manifest)
        r = self._run(self._ext(tmp_path, manifest))
        assert r.returncode != 0
        assert "manifest" in (r.stdout + r.stderr)


class TestEval020AxesContract:
    """Enforcing spine for memory/golden-evals/eval-020-axes-contract.md."""

    def test_eval_doc_exists_with_required_sections(self):
        text = _EVAL_020.read_text()
        for token in ("Category:", "## Scenario", "## Expected Behavior",
                      "## Failure Condition"):
            assert token in text, "eval-020 missing section: %s" % token

    def test_linter_and_allowlist_exist_and_are_green(self):
        assert ALLOWLIST_PATH.exists()
        entries = load_allowlist_entries()
        assert entries, "allowlist must load non-empty via the fail-closed loader"
        assert scan_tree(
            _REPO_ROOT / "framework",
            allowlist=load_allowlist(),
            rel_to=_REPO_ROOT,
        ) == []

    def test_allowlist_subset_of_immutable_core(self):
        """Every allowlisted branching module is Ring-0 (immutable-core):
        hard-asserted for non-pending entries; `pending:` entries
        (trust_ladder — landed with AX-2, Ring-0 wiring owed to AX-8)
        xfail-soften (strict=False) until wired, and a STALE flag (pending
        but already covered) hard-fails — the wiring lane deletes the flag
        in the same change."""
        import yaml
        core = yaml.safe_load(_IMMUTABLE_CORE.read_text())
        files = {e["path"] for e in core.get("files", [])}
        dir_prefixes = tuple(
            e["path"].rstrip("/") + "/" for e in core.get("dirs", [])
        )

        def covered(path: str) -> bool:
            return path in files or path.startswith(dir_prefixes)

        entries = load_allowlist_entries()
        assert entries is not None
        missing_hard = [e["path"] for e in entries
                        if e["pending"] is None and not covered(e["path"])]
        assert missing_hard == [], (
            "non-pending allowlist entries must be Ring-0 (immutable-core): "
            "%s" % missing_hard
        )
        stale = [e["path"] for e in entries
                 if e["pending"] is not None and covered(e["path"])]
        assert stale == [], (
            "already Ring-0-covered — delete the stale pending flag: %s"
            % stale
        )
        missing_pending = [e["path"] for e in entries
                           if e["pending"] is not None and not covered(e["path"])]
        if missing_pending:
            pytest.xfail(
                "pending allowlist entries not yet in immutable-core "
                "(AX-8 wires the lock set): %s" % missing_pending
            )
