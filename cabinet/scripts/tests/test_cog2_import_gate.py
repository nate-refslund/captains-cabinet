"""COG-2 UNIT 5 (lane A) — the net-new AST import-gate (§7.1, tests-first).

The mechanical proof of the shadow boundary M5 ("zero calls from authority/
action code"): NO module on the authority/action surface may import
framework.cortex, and the shadow-parity falsifier may import NO cortex module
at all (C-F17). The gate is a stdlib-`ast` import-graph walk (precise) + a grep
backstop (dynamic-import / data-plane `open()` bypass, C-F20). It mirrors the
check-layer-separation.sh idiom (tree scan, comment-safe, report/check/json
modes, exit 1 on any breach) but expresses an INTRA-framework deny rule that
check-layer-separation.sh structurally cannot.

Tests-first. Pins the gate contract AND every negative-control mutant the §7.1
gate names — each MUST bite:

  * a forbidden-tree module (frontdoor / acting / authority / the officer
    runner) that imports framework.cortex — the shadow-boundary breach.
  * cog2-parity-falsifier.py importing a cortex adapter (C-F17).
  * a dynamic / data-plane bypass invisible to an AST walk — `open()` on the
    cortex cache path, or an `importlib.import_module("framework.cortex...")`
    string — caught by the grep backstop (C-F20).
  * an UNALLOWLISTED importer anywhere in a swept first-party tree (framework/,
    shared/, instance/, presets/, the cabinet code subtrees, root conftest — see
    SWEEP_TREES) that is neither cortex-internal nor a curated cortex reader.

And the anti-over-fencing controls (must NOT flag): the real committed tree is
clean ([]); a legitimate cortex reader on the allowlist (cog2-rebuild /
-belief-hash / -verifier CLIs + the cog2 test suites) folds; a bare `# cortex`
comment mention is comment-safe; the falsifier's legitimate "cortex" DATA
references (dict keys, `_cortex_from_cmd`) are not import bans.

S0: interpreter python3.12. No DB — a pure text/AST scan over scratch trees.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import importlib.util as _ilu
import json
import subprocess
import sys
from pathlib import Path

import pytest

# hyphenated filename -> importlib (the cog2 CLI-under-test idiom, test_cog2_parity)
_GATE = Path(__file__).resolve().parents[1] / "cog2-import-gate.py"
_REPO = Path(__file__).resolve().parents[3]

_spec = _ilu.spec_from_file_location("cog2_import_gate", _GATE)
gate = _ilu.module_from_spec(_spec)
sys.modules["cog2_import_gate"] = gate
_spec.loader.exec_module(gate)

_IMPORT = "from framework.cortex import query  # leak\n"

# the first-party importable trees added to SWEEP_TREES to close the bridge-escape
# (a plain cortex import in any of these used to exit rc=0). Each must now bite.
NEWLY_SWEPT_TREES = [
    "shared",
    "instance",
    "presets",
    "cabinet/adapters",
    "cabinet/channels",
    "cabinet/companion",
    "cabinet/evals",
    "cabinet/fixtures",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _paths_for(violations, rule: str) -> set[str]:
    return {v.rsplit(":", 1)[0] for v in violations if v.rsplit(":", 1)[1] == rule}


def _rules_for(violations, path: str) -> set[str]:
    return {v.rsplit(":", 1)[1] for v in violations if v.rsplit(":", 1)[0] == path}


# ===========================================================================
# the load-bearing pair: real tree is clean; a forbidden import bites
# ===========================================================================

class TestRealTreeClean:
    def test_committed_tree_has_zero_violations(self):
        # baseline-zero: no authority/action code imports framework.cortex on
        # the real committed tree. THE anchor assertion of the whole gate.
        assert gate.scan(_REPO) == []

    def test_gate_is_not_a_no_op_forbidden_surface_exists(self):
        # a gate that scans nothing is silently green forever — pin that every
        # declared forbidden surface actually exists in the tree it guards.
        for tree in gate.FORBIDDEN_TREES:
            assert (_REPO / tree).is_dir(), f"forbidden tree vanished: {tree}"
        for f in gate.FORBIDDEN_FILES:
            assert (_REPO / f).is_file(), f"forbidden file vanished: {f}"
        assert (_REPO / gate.FALSIFIER).is_file()

    def test_falsifier_is_deliberately_not_allowlisted(self):
        # C-F17 only holds if the falsifier is NOT a legit cortex reader.
        assert gate.FALSIFIER not in gate.ALLOWLIST_EXACT
        assert not gate._is_allowlisted(gate.FALSIFIER)


# ===========================================================================
# forbidden authority/action surface — every named surface bites (§7.1 / M5)
# ===========================================================================

class TestForbiddenSurface:
    @pytest.mark.parametrize("rel", [
        "framework/frontdoor/leak.py",
        "framework/acting/leak.py",
        "framework/authority/leak.py",
        "framework/fidelity/officer_runner.py",   # a forbidden FILE, not a tree
    ])
    def test_forbidden_module_importing_cortex_is_flagged(self, tmp_path, rel):
        _write(tmp_path, rel, "import os\n" + _IMPORT)
        viol = gate.scan(tmp_path)
        assert rel in _paths_for(viol, gate.RULE_FORBIDDEN), viol

    @pytest.mark.parametrize("stmt", [
        "import framework.cortex\n",
        "import framework.cortex.engine as e\n",
        "from framework.cortex import adapters\n",
        "from framework.cortex.belief import Belief\n",
        # MUST-FIX 1: `from framework import cortex` — the single most ordinary
        # spelling — binds framework.cortex via the ALIAS name, invisible to a
        # check that only inspects node.module.
        "from framework import cortex\n",
        "from framework import cortex as c\n",
    ])
    def test_all_import_spellings_caught(self, tmp_path, stmt):
        _write(tmp_path, "framework/authority/x.py", stmt)
        assert "framework/authority/x.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_FORBIDDEN), stmt

    @pytest.mark.parametrize("stmt", [
        "from ..cortex import engine\n",         # level-2 dotted  -> framework.cortex
        "from ..cortex import engine as e\n",    # level-2 dotted, aliased
        "from .. import cortex\n",               # level-2 bare-name -> framework.cortex
    ])
    def test_relative_cortex_import_from_forbidden_tree_bites(self, tmp_path, stmt):
        # MUST-FIX 2: framework/authority/ is EXACTLY one level under framework/,
        # so `..` reaches framework and `..cortex` / `.. import cortex` resolve to
        # the shadow model framework.cortex at runtime. These were invisible to
        # the AST walk (node.module is 'cortex' or None with level>0) and to the
        # backstop (no 'framework' token on the line). The gate must resolve the
        # relative anchor from the file's package path and bite.
        _write(tmp_path, "framework/authority/x.py", "import os\n" + stmt)
        assert "framework/authority/x.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_FORBIDDEN), stmt

    def test_single_dot_relative_from_framework_root_bites(self, tmp_path):
        # `from . import cortex` reaches framework.cortex ONLY when the importer
        # sits directly in framework/ (package == framework). There it is a real
        # stray cortex reader — proves the level-1 single-dot resolver works.
        _write(tmp_path, "framework/leaky.py", "from . import cortex\n")
        assert "framework/leaky.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_UNALLOWLISTED)

    def test_single_dot_relative_to_sibling_module_not_overfenced(self, tmp_path):
        # NO over-fencing: `from . import cortex` INSIDE framework/authority/
        # resolves to framework.authority.cortex — a DIFFERENT module, not the
        # shadow model — so it must NOT be flagged. (Any real re-export shim it
        # could point at, e.g. a framework/authority/cortex.py doing
        # `from framework.cortex import *`, is itself caught directly.)
        _write(tmp_path, "framework/authority/x.py", "from . import cortex\n")
        assert gate.scan(tmp_path) == []

    def test_forbidden_tree_scan_ignores_pure_comment_mention(self, tmp_path):
        # NO over-fencing: authority code that merely NAMES cortex in a `#`
        # comment (no import, no path) is not a boundary breach.
        _write(tmp_path, "framework/acting/note.py",
               "# this module has nothing to do with the cortex projection\n"
               "import os  # noqa\n")
        assert gate.scan(tmp_path) == []

    def test_non_forbidden_fidelity_module_is_not_forbidden_class(self, tmp_path):
        # only officer_runner.py is forbidden in framework/fidelity — a sibling
        # (e.g. consequence.py, the legit source) importing cortex is caught,
        # but as the UNALLOWLISTED class, never the FORBIDDEN authority class.
        _write(tmp_path, "framework/fidelity/consequence.py", _IMPORT)
        rules = _rules_for(gate.scan(tmp_path), "framework/fidelity/consequence.py")
        assert rules == {gate.RULE_UNALLOWLISTED}


# ===========================================================================
# C-F17 — the falsifier import ban
# ===========================================================================

class TestFalsifierImportBan:
    def test_injected_cortex_adapter_import_bites(self, tmp_path):
        _write(tmp_path, gate.FALSIFIER,
               '"""falsifier."""\nimport json\n'
               "from framework.cortex import adapters  # MUTANT\n")
        assert gate.FALSIFIER in _paths_for(gate.scan(tmp_path), gate.RULE_FALSIFIER)

    @pytest.mark.parametrize("body", [
        # SHOULD-FIX 3: dynamic imports the AST walk cannot see. C-F17 makes the
        # falsifier the STRICTEST surface — the parity ground truth must reach NO
        # cortex module at all, however it is spelled.
        '"""falsifier."""\nimport importlib\n'
        "m = importlib.import_module('framework.cortex.query')  # MUTANT dynamic\n",
        # the two-argument RELATIVE form: import_module(name='.cortex', package='framework')
        '"""falsifier."""\nimport importlib\n'
        "m = importlib.import_module('.cortex', 'framework')  # MUTANT rel two-arg\n",
        # the `from framework import cortex` spelling, defended even if AST parse fails
        '"""falsifier."""\nfrom framework import cortex  # MUTANT\n',
    ])
    def test_dynamic_and_alias_cortex_import_bites(self, tmp_path, body):
        _write(tmp_path, gate.FALSIFIER, body)
        assert gate.FALSIFIER in _paths_for(
            gate.scan(tmp_path), gate.RULE_FALSIFIER), body

    def test_falsifier_data_references_to_cortex_are_not_a_ban(self, tmp_path):
        # the real falsifier legitimately carries "cortex" as DATA (dict keys,
        # a `_cortex_from_cmd` reader, docstrings). C-F17 bans IMPORTS, not the
        # word — a falsifier that only mentions cortex must fold clean.
        _write(tmp_path, gate.FALSIFIER,
               '"""cortex shadow-parity falsifier."""\n'
               'import json\n'
               'def _cortex_from_cmd():\n'
               '    return {"cortex": {}}  # cortex answers, as data\n')
        assert gate.scan(tmp_path) == []


# ===========================================================================
# C-F20 — the grep backstop: dynamic + data-plane bypasses an AST walk misses
# ===========================================================================

class TestGrepBackstop:
    def test_dataplane_open_of_cache_path_bites_without_a_static_import(self, tmp_path):
        # the covert bypass: no `import`, just open() the cortex store directly.
        # AST sees no import; the backstop MUST still fire.
        _write(tmp_path, "framework/acting/sneaky.py",
               "import json\n"
               "def read():\n"
               "    with open('cabinet/cache/cortex/beliefs.jsonl') as fh:\n"
               "        return json.load(fh)\n")
        rules = _rules_for(gate.scan(tmp_path), "framework/acting/sneaky.py")
        assert gate.RULE_TOKEN in rules                       # backstop fired
        assert gate.RULE_FORBIDDEN not in rules               # AST correctly silent

    def test_dynamic_import_string_bites(self, tmp_path):
        _write(tmp_path, "framework/authority/dyn.py",
               "import importlib\n"
               "m = importlib.import_module('framework.cortex.query')\n")
        assert gate.RULE_TOKEN in _rules_for(
            gate.scan(tmp_path), "framework/authority/dyn.py")

    def test_backstop_is_comment_safe(self, tmp_path):
        # a `#`-comment naming the module/path is not a live coupling.
        _write(tmp_path, "framework/frontdoor/c.py",
               "# never touch cabinet/cache/cortex from here\n"
               "# and never import framework.cortex\n"
               "import os  # noqa\n")
        assert gate.scan(tmp_path) == []


# ===========================================================================
# Check 4 — global whitelist: any other cortex importer + the allowlist
# ===========================================================================

class TestAllowlist:
    def test_unallowlisted_framework_importer_bites(self, tmp_path):
        _write(tmp_path, "framework/evidence/leak.py", _IMPORT)
        assert "framework/evidence/leak.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_UNALLOWLISTED)

    @pytest.mark.parametrize("rel", [
        "cabinet/scripts/cog2-rebuild.py",
        "cabinet/scripts/cog2-belief-hash.py",
        "cabinet/scripts/cog2-verifier.py",
        "cabinet/scripts/tests/test_cog2_smoke.py",
        "cabinet/scripts/tests/lib_cog2_helper.py",
    ])
    def test_allowlisted_readers_fold_clean(self, tmp_path, rel):
        _write(tmp_path, rel, "from framework.cortex import engine\n")
        assert gate.scan(tmp_path) == [], rel

    def test_cortex_internal_imports_fold_clean(self, tmp_path):
        _write(tmp_path, "framework/cortex/query.py",
               "from framework.cortex import engine as _engine\n")
        assert gate.scan(tmp_path) == []


# ===========================================================================
# CLI contract — exit codes, --report, --json (mirrors check-layer-separation)
# ===========================================================================

class TestCLI:
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(_GATE), *args],
            capture_output=True, text=True)

    def test_clean_root_exits_zero(self):
        r = self._run("--root", str(_REPO))
        assert r.returncode == 0, r.stderr

    def test_dirty_root_exits_one(self, tmp_path):
        _write(tmp_path, "framework/authority/leak.py", _IMPORT)
        r = self._run("--root", str(tmp_path))
        assert r.returncode == 1
        assert "framework/authority/leak.py" in (r.stdout + r.stderr)

    def test_report_mode_lists_but_exits_zero(self, tmp_path):
        _write(tmp_path, "framework/authority/leak.py", _IMPORT)
        r = self._run("--root", str(tmp_path), "--report")
        assert r.returncode == 0
        assert gate.RULE_FORBIDDEN in r.stdout

    def test_json_mode_is_machine_readable(self, tmp_path):
        _write(tmp_path, "framework/acting/leak.py", _IMPORT)
        r = self._run("--root", str(tmp_path), "--json")
        payload = json.loads(r.stdout)
        assert payload["count"] == len(payload["violations"]) >= 1
        assert any(v.endswith(gate.RULE_FORBIDDEN) for v in payload["violations"])


# ===========================================================================
# SHOULD-FIX 4 — live runtime surfaces are swept + a narrow dynamic reach bites
# ===========================================================================

class TestSweepTrees:
    def test_runtime_surfaces_are_in_sweep(self):
        # the admin bot + MCP server are live action/runtime python; a stray
        # cortex reach there must not be invisible to the global whitelist.
        for tree in ("cabinet/admin-bot", "cabinet/mcp-server"):
            assert tree in gate.SWEEP_TREES, tree

    @pytest.mark.parametrize("rel", [
        "cabinet/admin-bot/x.py",
        "cabinet/mcp-server/x.py",
    ])
    def test_dynamic_cortex_reach_in_runtime_surface_bites(self, tmp_path, rel):
        # AST-invisible dynamic import in a runtime surface OUTSIDE any forbidden
        # tree — the narrow sweep regex (not the noisy bare-token backstop) fires.
        _write(tmp_path, rel,
               "import importlib\n"
               "m = importlib.import_module('framework.cortex.query')\n")
        assert rel in _paths_for(gate.scan(tmp_path), gate.RULE_UNALLOWLISTED), rel

    def test_static_cortex_import_in_runtime_surface_bites(self, tmp_path):
        _write(tmp_path, "cabinet/mcp-server/y.py", _IMPORT)
        assert "cabinet/mcp-server/y.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_UNALLOWLISTED)

    def test_runtime_surface_bare_cortex_word_is_not_overfenced(self, tmp_path):
        # narrowness: the word "cortex" as prose/data in a runtime surface (no
        # import, no import_module call) must NOT trip the sweep regex.
        _write(tmp_path, "cabinet/admin-bot/z.py",
               "CACHE = 'beliefs'  # the cortex projection is read elsewhere\n"
               "def run():\n    return {'cortex': 0}\n")
        assert gate.scan(tmp_path) == []


# ===========================================================================
# BRIDGE-ESCAPE CLOSED — every first-party importable tree is swept, so a
# plain cortex import is never invisible wherever it lives (§7.1)
# ===========================================================================

class TestBridgeEscapeClosed:
    def test_newly_swept_trees_are_registered(self):
        # the trees the escape slipped through must all be in SWEEP_TREES now.
        for tree in NEWLY_SWEPT_TREES + ["conftest.py"]:
            assert tree in gate.SWEEP_TREES, tree

    @pytest.mark.parametrize("tree", NEWLY_SWEPT_TREES)
    def test_stray_cortex_import_in_newly_swept_tree_bites(self, tmp_path, tree):
        # THE fix: a plain `from framework.cortex import query` written into any
        # previously-omitted first-party tree now bites (RULE_UNALLOWLISTED) — it
        # is not forbidden-class, not the falsifier, but a stray reader.
        rel = f"{tree}/leak.py"
        _write(tmp_path, rel, _IMPORT)
        assert rel in _paths_for(gate.scan(tmp_path), gate.RULE_UNALLOWLISTED), rel

    def test_stray_cortex_import_in_root_conftest_bites(self, tmp_path):
        # conftest.py is the repo-root importable pytest fence (loaded at
        # collection time); a stray cortex import there must be visible too.
        _write(tmp_path, "conftest.py", _IMPORT)
        assert "conftest.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_UNALLOWLISTED)

    def test_two_hop_bridge_is_caught_at_the_bridge(self, tmp_path):
        # The verified escape, now closed: authority/action code reaches the
        # shadow model through a bridge in a (now-swept) first-party tree. The
        # authority file names NO cortex token — it imports the bridge — so it is
        # correctly NOT flagged (direct-import detector, not a transitive graph;
        # the residual is attribution only). The BRIDGE, which literally imports
        # framework.cortex, IS flagged in the swept shared/ tree, so the reach can
        # never be silent.
        _write(tmp_path, "framework/authority/act.py",
               "from shared.cortex_bridge import query  # names no cortex token\n")
        _write(tmp_path, "shared/cortex_bridge.py",
               "from framework.cortex import query  # the real one-hop reach\n")
        viol = gate.scan(tmp_path)
        assert "shared/cortex_bridge.py" in _paths_for(
            viol, gate.RULE_UNALLOWLISTED), viol
        assert _rules_for(viol, "framework/authority/act.py") == set(), viol

    def test_bare_cortex_word_in_newly_swept_tree_is_not_overfenced(self, tmp_path):
        # narrowness: ordinary code in a newly-swept tree that merely mentions
        # "cortex" as prose/data (no import) must NOT trip the sweep.
        _write(tmp_path, "instance/flavor-a/thing.py",
               "CFG = {'cortex': 'read elsewhere'}  # the cortex projection is shadow-only\n"
               "def run():\n    return CFG\n")
        _write(tmp_path, "presets/work/preset.py", "import os\n\nVALUE = 1\n")
        assert gate.scan(tmp_path) == []

    def test_dynamic_cortex_reach_in_newly_swept_tree_bites(self, tmp_path):
        # the AST-blind dynamic form is caught in the newly-swept trees too.
        _write(tmp_path, "cabinet/adapters/dyn.py",
               "import importlib\n"
               "m = importlib.import_module('framework.cortex.query')\n")
        assert "cabinet/adapters/dyn.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_UNALLOWLISTED)


# ===========================================================================
# ANTI-RECURRENCE — the sweep must enumerate EVERY first-party .py, so an
# omitted code namespace (the escape's root cause) fails loudly, not silently
# ===========================================================================

class TestScanSurfaceCompleteness:
    def test_every_first_party_py_is_on_scan_surface(self):
        # The bridge-escape's root cause was a SWEEP_TREES that omitted importable
        # trees. This pins the inverse invariant on the committed repo: every
        # first-party .py must be enumerated by the gate's scan surface
        # (SWEEP_TREES + the forbidden trees/files/falsifier), so no importable
        # module can silently escape the cortex check. A new code namespace with
        # no SWEEP_TREES entry fails HERE — before it can host an invisible import.
        def _rels(base: str) -> set[str]:
            b = _REPO / base
            if b.is_dir():
                return {p.relative_to(_REPO).as_posix()
                        for p in b.rglob("*.py") if p.is_file()}
            if b.is_file() and b.suffix == ".py":
                return {b.relative_to(_REPO).as_posix()}
            return set()

        surface = (list(gate.SWEEP_TREES) + list(gate.FORBIDDEN_TREES)
                   + list(gate.FORBIDDEN_FILES) + [gate.FALSIFIER])
        scanned: set[str] = set()
        for entry in surface:
            scanned |= _rels(entry)

        all_py = {p.relative_to(_REPO).as_posix()
                  for p in _REPO.rglob("*.py")
                  if p.is_file() and "__pycache__" not in p.parts}
        uncovered = sorted(all_py - scanned)
        assert uncovered == [], (
            "first-party .py NOT on the gate scan surface — add its tree to "
            f"SWEEP_TREES (silent-escape risk): {uncovered}")
