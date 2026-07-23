"""COG-3 STEP 0 — the objectives module gate + data-plane sweep (contract §6.5,
tests-first, gates-before-code).

Extends cog2-import-gate.py IN PLACE with a SECOND shadow-model boundary
(framework.objectives), byte-compatible with the cortex rules. Five mechanical
rules, each pinned here with the negative-control mutant it names (COG-2 §8 law
— a gate without a bitten mutant is decoration):

  FORBIDDEN_IMPORTS_OBJECTIVES        authority/action code imports the graph
  FORBIDDEN_OBJECTIVES_TOKEN          "     names framework.objectives on a live line
  FORBIDDEN_OBJECTIVES_IMPORTS_ACTION a framework/objectives/ file imports the
                                      action plane (reverse direction)
  UNALLOWLISTED_OBJECTIVES_IMPORTER   an un-curated swept file imports the graph
                                      (framework/missions consuming it — §6.2(5))
  FORBIDDEN_OBJECTIVES_DATAPLANE      a live reference to the objectives cache
                                      path anywhere in SWEEP_TREES (§6.5 bullet 6,
                                      attack C-M9 — the non-covert data-plane read)

Green-by-vacuity today: framework/objectives/ + the cog3 files do not exist, so
every mutant is written into a SCRATCH tmp tree — the gate must fold the real
committed tree ([]) yet bite the instant an offending file appears.

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

# hyphenated filename -> importlib (the cog2 CLI-under-test idiom)
_GATE = Path(__file__).resolve().parents[1] / "cog2-import-gate.py"
_REPO = Path(__file__).resolve().parents[3]

_spec = _ilu.spec_from_file_location("cog2_import_gate_cog3", _GATE)
gate = _ilu.module_from_spec(_spec)
sys.modules["cog2_import_gate_cog3"] = gate
_spec.loader.exec_module(gate)

_OBJ_IMPORT = "from framework.objectives import query  # leak\n"
# assembled so THIS test file never carries the contiguous cache literal outside
# a deliberate mutant body (defensive; the file is allowlisted regardless).
_CACHE = "cabinet/cache/" + "objectives"


# ---------------------------------------------------------------------------
# helpers (mirror test_cog2_import_gate.py)
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
# constants — the contract-named rule ids + the honestly-scoped allowlist
# ===========================================================================

class TestConstants:
    def test_the_three_named_rule_ids_plus_reverse_and_dataplane_exist(self):
        assert gate.OBJECTIVES == "framework.objectives"
        assert gate.RULE_FORBIDDEN_OBJ == "FORBIDDEN_IMPORTS_OBJECTIVES"
        assert gate.RULE_TOKEN_OBJ == "FORBIDDEN_OBJECTIVES_TOKEN"
        assert gate.RULE_UNALLOWLISTED_OBJ == "UNALLOWLISTED_OBJECTIVES_IMPORTER"
        # the reverse + data-plane rules the boundary also needs
        assert gate.RULE_OBJ_IMPORTS_ACTION == "FORBIDDEN_OBJECTIVES_IMPORTS_ACTION"
        assert gate.RULE_OBJ_DATAPLANE == "FORBIDDEN_OBJECTIVES_DATAPLANE"

    def test_action_plane_is_the_forbidden_trees_dotted(self):
        assert gate.ACTION_PLANE == (
            "framework.frontdoor", "framework.acting", "framework.authority")

    def test_cog3_allowlist_covers_the_reader_clis_only(self):
        # the curated graph readers are exact entries (§6.5 "exact entries") —
        # the three wave-1 instruments + the two WR riders, each grown
        # 2026-07-23 in lockstep with its gate entry (the lockstep this pin
        # exists to force): the R1 verdict inbox (BACKLOG :1559 — a
        # serve-surface-only reader) and the R3 shadow-dividend reporter
        # (COG-4 §18 — a read-only serve-surface consumer)...
        assert gate.ALLOWLIST_EXACT_OBJECTIVES == {
            "cabinet/scripts/cog3-rebuild.py",
            "cabinet/scripts/cog3-graph-hash.py",
            "cabinet/scripts/cog3-staleness.py",
            "cabinet/scripts/cog3-verdict-inbox.py",
            "cabinet/scripts/cog3-shadow-dividend.py",
        }
        # ...and the parity falsifier is DELIBERATELY absent (C-F17 analog: it
        # must import NO objectives internals, so it is never a sanctioned reader).
        assert "cabinet/scripts/cog3-ovi-parity.py" not in gate.ALLOWLIST_EXACT_OBJECTIVES

    def test_committed_tree_is_clean_under_the_extended_gate(self):
        # THE byte-compat anchor: extending the gate adds zero violations today.
        assert gate.scan(_REPO) == []


# ===========================================================================
# FORBIDDEN_IMPORTS_OBJECTIVES / FORBIDDEN_OBJECTIVES_TOKEN — the forbidden
# authority/action surface may not reach the graph either
# ===========================================================================

class TestForwardBoundary:
    @pytest.mark.parametrize("rel", [
        "framework/frontdoor/leak.py",
        "framework/acting/leak.py",
        "framework/authority/leak.py",
        "framework/fidelity/officer_runner.py",   # a forbidden FILE, not a tree
    ])
    def test_forbidden_surface_importing_objectives_bites(self, tmp_path, rel):
        _write(tmp_path, rel, "import os\n" + _OBJ_IMPORT)
        assert rel in _paths_for(gate.scan(tmp_path), gate.RULE_FORBIDDEN_OBJ)

    @pytest.mark.parametrize("stmt", [
        "import framework.objectives\n",
        "import framework.objectives.graph as g\n",
        "from framework.objectives import states\n",
        "from framework.objectives.query import serve\n",
        "from framework import objectives\n",            # alias spelling
        "from framework import objectives as o\n",
    ])
    def test_all_objectives_import_spellings_caught(self, tmp_path, stmt):
        _write(tmp_path, "framework/authority/x.py", stmt)
        assert "framework/authority/x.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_FORBIDDEN_OBJ), stmt

    @pytest.mark.parametrize("stmt", [
        "from ..objectives import graph\n",        # level-2 -> framework.objectives
        "from .. import objectives\n",             # level-2 bare-name
    ])
    def test_relative_objectives_import_from_forbidden_tree_bites(self, tmp_path, stmt):
        _write(tmp_path, "framework/authority/x.py", "import os\n" + stmt)
        assert "framework/authority/x.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_FORBIDDEN_OBJ), stmt

    def test_dynamic_objectives_import_in_forbidden_tree_bites_token(self, tmp_path):
        _write(tmp_path, "framework/authority/dyn.py",
               "import importlib\n"
               "m = importlib.import_module('framework.objectives.graph')\n")
        assert gate.RULE_TOKEN_OBJ in _rules_for(
            gate.scan(tmp_path), "framework/authority/dyn.py")

    def test_forbidden_tree_objectives_comment_is_comment_safe(self, tmp_path):
        _write(tmp_path, "framework/acting/note.py",
               "# nothing here reaches framework.objectives\n"
               "import os  # noqa\n")
        assert gate.scan(tmp_path) == []

    def test_forbidden_tree_reaching_both_shadow_models_flags_both(self, tmp_path):
        # a single file importing both cortex AND objectives earns both rules —
        # proves the objectives rule is ADDITIVE, not a replacement.
        _write(tmp_path, "framework/frontdoor/greedy.py",
               "from framework.cortex import query\n"
               "from framework.objectives import states\n")
        rules = _rules_for(gate.scan(tmp_path), "framework/frontdoor/greedy.py")
        assert gate.RULE_FORBIDDEN in rules
        assert gate.RULE_FORBIDDEN_OBJ in rules


# ===========================================================================
# FORBIDDEN_OBJECTIVES_IMPORTS_ACTION — the reverse: the graph reads the cortex,
# never the action plane
# ===========================================================================

class TestReverseBoundary:
    @pytest.mark.parametrize("stmt", [
        "import framework.frontdoor\n",
        "from framework.acting import runner\n",
        "from framework.authority.classifier import ACTION_TYPES\n",
        "from framework import authority\n",
        "from ..authority import classifier\n",   # objectives is one level under framework
    ])
    def test_objectives_importing_action_plane_bites(self, tmp_path, stmt):
        _write(tmp_path, "framework/objectives/leaky.py", "import os\n" + stmt)
        assert "framework/objectives/leaky.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_OBJ_IMPORTS_ACTION), stmt

    def test_objectives_reading_cortex_query_surface_folds_clean_at_module_gate(self, tmp_path):
        # the graph legitimately reads the cortex query surface — the MODULE gate
        # must NOT flag it (the narrow which-symbols rule is the separate AST pin).
        _write(tmp_path, "framework/objectives/query.py",
               "from framework.cortex.query import as_of, load_beliefs_verified\n")
        assert gate.scan(tmp_path) == []

    def test_objectives_internal_and_stdlib_imports_fold_clean(self, tmp_path):
        _write(tmp_path, "framework/objectives/graph.py",
               "import json\nfrom framework.objectives import model\n")
        assert gate.scan(tmp_path) == []

    def test_dynamic_objectives_importing_action_plane_bites(self, tmp_path):
        # THE reviewer's escape, reproduced exactly: a dynamic import_module of the
        # action plane from inside framework/objectives/. Invisible to the AST
        # static check (_action_plane_imports) — the dynamic complement must bite
        # it, mirroring how the FORWARD direction treats literal import_module
        # strings as mechanically reachable. RED with the reverse-direction id.
        _write(tmp_path, "framework/objectives/sneaky.py",
               "import importlib\n"
               'c = importlib.import_module("framework.authority.classifier")\n')
        assert "framework/objectives/sneaky.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_OBJ_IMPORTS_ACTION)
        # restore -> the clean tree folds green (no reverse violation lingers).
        (tmp_path / "framework/objectives/sneaky.py").unlink()
        assert gate.scan(tmp_path) == []

    def test_dunder_import_of_action_plane_from_objectives_bites(self, tmp_path):
        # the __import__ variant of the same escape is bitten too.
        _write(tmp_path, "framework/objectives/sneaky2.py",
               'm = __import__("framework.frontdoor.live")\n')
        assert "framework/objectives/sneaky2.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_OBJ_IMPORTS_ACTION)

    def test_dynamic_action_reach_from_objectives_is_comment_safe(self, tmp_path):
        # the _live_lines idiom: the same call inside a comment does NOT flag.
        _write(tmp_path, "framework/objectives/note.py",
               '# c = importlib.import_module("framework.authority.classifier")\n'
               "import os\n")
        assert gate.scan(tmp_path) == []


# ===========================================================================
# UNALLOWLISTED_OBJECTIVES_IMPORTER — the missions-consumes-the-graph escape
# and the curated-reader allowlist
# ===========================================================================

class TestUnallowlistedImporter:
    def test_missions_importing_objectives_bites(self, tmp_path):
        # §6.2(5): "objectives become authoritative mission input" is caught from
        # day one — framework/missions is swept, never allowlisted.
        _write(tmp_path, "framework/missions/consume.py", _OBJ_IMPORT)
        assert "framework/missions/consume.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_UNALLOWLISTED_OBJ)

    @pytest.mark.parametrize("rel", [
        "shared/bridge.py",
        "instance/flavor-a/thing.py",
        "cabinet/mcp-server/x.py",
        "cabinet/admin-bot/y.py",
    ])
    def test_stray_objectives_importer_in_any_swept_tree_bites(self, tmp_path, rel):
        _write(tmp_path, rel, _OBJ_IMPORT)
        assert rel in _paths_for(gate.scan(tmp_path), gate.RULE_UNALLOWLISTED_OBJ), rel

    def test_dynamic_objectives_reach_in_swept_tree_bites(self, tmp_path):
        _write(tmp_path, "cabinet/mcp-server/dyn.py",
               "import importlib\n"
               "m = importlib.import_module('framework.objectives.query')\n")
        assert "cabinet/mcp-server/dyn.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_UNALLOWLISTED_OBJ)

    @pytest.mark.parametrize("rel", [
        "cabinet/scripts/cog3-rebuild.py",
        "cabinet/scripts/cog3-graph-hash.py",
        "cabinet/scripts/cog3-staleness.py",
        "cabinet/scripts/tests/test_cog3_smoke.py",
        "cabinet/scripts/tests/lib_cog3_helper.py",
    ])
    def test_curated_cog3_readers_fold_clean(self, tmp_path, rel):
        _write(tmp_path, rel, "from framework.objectives import graph\n")
        assert gate.scan(tmp_path) == [], rel

    def test_objectives_internal_importing_itself_folds_clean(self, tmp_path):
        _write(tmp_path, "framework/objectives/states.py",
               "from framework.objectives import model as _m\n")
        assert gate.scan(tmp_path) == []

    def test_parity_falsifier_importing_objectives_is_NOT_allowlisted(self, tmp_path):
        # C-F17 analog enforced at the module level: cog3-ovi-parity.py is not a
        # curated objectives reader, so any objectives import from it REDs.
        _write(tmp_path, "cabinet/scripts/cog3-ovi-parity.py",
               "from framework.objectives import ovi_view\n")
        assert "cabinet/scripts/cog3-ovi-parity.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_UNALLOWLISTED_OBJ)

    def test_bare_objectives_word_is_not_overfenced(self, tmp_path):
        _write(tmp_path, "cabinet/admin-bot/z.py",
               "CFG = {'objectives': 'read elsewhere'}  # the objectives graph is shadow-only\n"
               "def run():\n    return CFG\n")
        assert gate.scan(tmp_path) == []


# ===========================================================================
# FORBIDDEN_OBJECTIVES_DATAPLANE — the SWEEP-wide cache-path sweep (attack C-M9)
# ===========================================================================

class TestDataPlaneSweep:
    def test_missions_opening_the_cache_path_bites(self, tmp_path):
        # THE C-M9 escape: missions/admin-bot/mcp-server open() the graph store
        # with no import at all. The import sweep is blind to it; the data-plane
        # sweep — widened to the full SWEEP_TREES — must fire.
        _write(tmp_path, "framework/missions/peek.py",
               "import json\n"
               "def read():\n"
               f"    with open('{_CACHE}/graph.jsonl') as fh:\n"
               "        return json.load(fh)\n")
        rules = _rules_for(gate.scan(tmp_path), "framework/missions/peek.py")
        assert gate.RULE_OBJ_DATAPLANE in rules            # data-plane fired
        assert gate.RULE_UNALLOWLISTED_OBJ not in rules    # no import, correctly silent

    @pytest.mark.parametrize("rel", [
        "cabinet/admin-bot/reader.py",
        "cabinet/mcp-server/reader.py",
        "shared/peek.py",
    ])
    def test_cache_path_reference_in_any_swept_tree_bites(self, tmp_path, rel):
        _write(tmp_path, rel, f"PATH = '{_CACHE}/graph-manifest.json'\n")
        assert rel in _paths_for(gate.scan(tmp_path), gate.RULE_OBJ_DATAPLANE), rel

    def test_objectives_internal_may_reference_its_own_cache(self, tmp_path):
        _write(tmp_path, "framework/objectives/graph.py",
               f"CACHE = '{_CACHE}'\n")
        assert gate.scan(tmp_path) == []

    @pytest.mark.parametrize("rel", [
        "cabinet/scripts/cog3-rebuild.py",
        "cabinet/scripts/tests/test_cog3_x.py",
    ])
    def test_cog3_readers_may_reference_the_cache(self, tmp_path, rel):
        _write(tmp_path, rel, f"CACHE = '{_CACHE}/predictions'\n")
        assert gate.scan(tmp_path) == [], rel

    def test_dataplane_sweep_is_comment_safe(self, tmp_path):
        _write(tmp_path, "framework/missions/c.py",
               f"# never touch {_CACHE} from here\n"
               "import os  # noqa\n")
        assert gate.scan(tmp_path) == []

    def test_the_gate_file_does_not_self_flag(self):
        # the data-plane sweep covers cabinet/scripts (this gate lives there). The
        # cache token is assembled, never contiguous — so the gate never flags
        # itself. Proven at repo scale by the clean-tree anchor; pinned explicitly.
        rel = "cabinet/scripts/cog2-import-gate.py"
        assert _rules_for(gate.scan(_REPO), rel) == set()


# ===========================================================================
# NO REGRESSION — the cortex boundary still bites, unchanged
# ===========================================================================

class TestCortexBoundaryUnregressed:
    def test_cortex_forbidden_import_still_bites(self, tmp_path):
        _write(tmp_path, "framework/authority/leak.py",
               "from framework.cortex import query\n")
        assert "framework/authority/leak.py" in _paths_for(
            gate.scan(tmp_path), gate.RULE_FORBIDDEN)

    def test_falsifier_still_not_allowlisted(self):
        assert not gate._is_allowlisted(gate.FALSIFIER)

    def test_cog3_reader_reaching_cortex_folds_clean(self, tmp_path):
        # the Check-3 broadening: a cog3 CLI reading the cortex query surface is a
        # legitimate reader, not an UNALLOWLISTED_CORTEX_IMPORTER.
        _write(tmp_path, "cabinet/scripts/cog3-staleness.py",
               "from framework.cortex.query import as_of\n")
        assert gate.scan(tmp_path) == []


# ===========================================================================
# CLI contract — the extended gate still exits 1 on an objectives breach
# ===========================================================================

class TestCLI:
    def _run(self, *args):
        return subprocess.run([sys.executable, str(_GATE), *args],
                              capture_output=True, text=True)

    def test_objectives_breach_exits_one(self, tmp_path):
        _write(tmp_path, "framework/authority/leak.py", _OBJ_IMPORT)
        r = self._run("--root", str(tmp_path))
        assert r.returncode == 1
        assert gate.RULE_FORBIDDEN_OBJ in (r.stdout + r.stderr)

    def test_json_lists_the_objectives_rule(self, tmp_path):
        _write(tmp_path, "framework/missions/consume.py", _OBJ_IMPORT)
        r = self._run("--root", str(tmp_path), "--json")
        payload = json.loads(r.stdout)
        assert any(v.endswith(gate.RULE_UNALLOWLISTED_OBJ)
                   for v in payload["violations"])

    def test_clean_real_tree_still_exits_zero(self):
        r = self._run("--root", str(_REPO))
        assert r.returncode == 0, r.stderr
