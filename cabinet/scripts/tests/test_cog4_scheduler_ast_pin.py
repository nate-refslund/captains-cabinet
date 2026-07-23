"""COG-4 §8.4 sibling pin #1 — the SCHEDULER (planner tree) symbol-level import
boundary + the cloned defaults-only as_of pin + the no-subprocess/no-socket pin.
Tests-first, gates-before-code (contract cognitive-core-phase-4-contract-2026-07-23
§8.4; the shipped seven-symbol `test_cog3_objectives_ast_pin` is the byte-untouched
sibling this clones, MR7).

The planner tree `framework/scheduler/` is a PURE fold. §8.4 pins WHICH names it may
import: stdlib | framework.projection (the C3 kernel) | framework.scheduler.* (internal)
| framework.organs.* | the seven cortex query-surface symbols | the four objectives
serve symbols (serve_graph, serve_objective, recommend, ServeRefused). Anything else is
RED — incl. load_beliefs, cortex engine/adapters, any authority/acting/frontdoor/
fidelity/missions/ovi module, the cortex or objectives query MODULE object, or a
third-party dep. Plus (§3) every as_of read is defaults-only, and (§7.2) the pure planner
never shells out or opens a socket.

VACUITY — retire when framework/scheduler/ lands (§13 law): the real-tree arms below
SKIP while the planner tree is absent, and each carries a COMPANION assertion that the
tree does not exist, so the skip cannot silently persist after the tree lands (the
companion goes RED the moment framework/scheduler/ appears, forcing the skip's
retirement and the real-tree scan's activation). The scratch-tree positive/negative
controls run NOW and prove the scanners bite (a gate without a biting mutant is
decoration — §12).

S0: python3.12, no DB, no network. Provenance: authored per the 2026-07-07 full-autonomy
grant + the 2026-07-20 cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):        # tests/ is a package: put it on the path
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog4_ast_pins as L  # noqa: E402


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


# ===========================================================================
# the symbol-level import pin
# ===========================================================================
class TestSchedulerImportPin:
    def test_real_tree_is_armed_and_absent(self):
        # VACUITY GUARD — RETIREMENT CONDITION: when framework/scheduler/ lands, delete
        # the skip and keep the green-by-vacuity assertion as the real-tree pin. The
        # companion assertion fails the instant the tree lands, so this cannot rot.
        tree = _REPO / L.SCHEDULER_TREE_REL
        assert not tree.exists(), (
            f"{L.SCHEDULER_TREE_REL}/ has LANDED — retire this vacuity skip and enable "
            "the real-tree scan per the docstring RETIREMENT CONDITION")
        assert L.scheduler_import_violations(_REPO) == []   # green over the absent tree
        pytest.skip(f"VACUITY: {L.SCHEDULER_TREE_REL}/ absent this phase — pin armed via "
                    "scratch-tree controls; retire when the planner tree lands.")

    def test_sanctioned_surface_folds_clean(self, tmp_path):
        _write(tmp_path, "framework/scheduler/fold.py",
               "from __future__ import annotations\n"
               "import json, hashlib\n"
               "from pathlib import Path\n"
               "from framework.cortex.query import (\n"
               "    load_beliefs_verified, as_of, BeliefView, AsOfResult,\n"
               "    ScopeError, StoreCorruptError, UNKNOWN)\n"
               "from framework.objectives.query import (\n"
               "    serve_graph, serve_objective, recommend, ServeRefused)\n"
               "from framework.projection.kernel import chained_rows_hash\n"
               "from framework.organs.registry import load_organ_registry\n"
               "from framework.organs.descriptor import resolve_descriptor\n"
               "from framework.scheduler import model\n"
               "from . import snapshot\n")
        assert L.scheduler_import_violations(tmp_path) == []

    def test_internal_relative_imports_fold_clean(self, tmp_path):
        _write(tmp_path, "framework/scheduler/adapters/roots.py",
               "from .. import model\n"
               "from ..fold import build_schedule\n"
               "from . import serve\n"
               "from framework.scheduler.snapshot import build_snapshot\n")
        assert L.scheduler_import_violations(tmp_path) == []

    def test_load_beliefs_symbol_is_red(self, tmp_path):
        # the named escape: load_beliefs is the trusted-bytes loader that bypasses the
        # verified read — RED even from the sanctioned query module.
        _write(tmp_path, "framework/scheduler/fold.py",
               "from framework.cortex.query import as_of, load_beliefs\n")
        v = L.scheduler_import_violations(tmp_path)
        assert any(x.split()[-1] == "load_beliefs" for x in v), v
        assert all(x.split()[-1] != "as_of" for x in v)   # as_of on the same line is fine

    def test_nonserve_objectives_symbol_is_red(self, tmp_path):
        _write(tmp_path, "framework/scheduler/fold.py",
               "from framework.objectives.query import serve_graph, load_bound\n")
        v = L.scheduler_import_violations(tmp_path)
        assert any(x.split()[-1] == "load_bound" for x in v), v
        assert all(x.split()[-1] != "serve_graph" for x in v)

    @pytest.mark.parametrize("stmt", [
        "from framework.cortex.query import load_beliefs\n",       # trusted-bytes loader
        "from framework.cortex import query\n",                    # query module object
        "from framework.cortex import engine\n",
        "from framework.cortex.engine import resolve_relationships\n",
        "from framework.cortex.adapters import build_consequence_protos\n",
        "import framework.cortex.query\n",                         # module object, dotted
        "import framework.cortex\n",
        "from framework.objectives import query\n",                # objectives module obj
        "from framework.objectives.graph import build_graph\n",    # non-serve module
        "from framework.objectives.model import Objective\n",
        "from framework.authority.classifier import ACTION_TYPES\n",
        "from framework.authority.policy_engine import risk_of\n",  # NO authority in planner
        "from framework.authority.matrix import RISK_CLASSES\n",
        "from framework.fidelity.graduation import evaluate\n",     # NO fidelity in planner
        "from framework.fidelity.consequence import _REVIEW_SOURCES\n",
        "from framework.acting import runner\n",
        "from framework.frontdoor import door\n",
        "from framework.missions import compile\n",
        "from framework.ovi.compute import composite\n",
        "from framework.learning.capability_gaps import HARD_CEILING_TOUCHES\n",
        "from framework import cortex\n",                          # alias spelling
        "import yaml\n",                                           # third-party dep
        "from ..cortex import query\n",                           # relative escape
    ])
    def test_forbidden_imports_are_red(self, tmp_path, stmt):
        _write(tmp_path, "framework/scheduler/x.py", stmt)
        assert L.scheduler_import_violations(tmp_path), stmt

    def test_stdlib_and_future_fold_clean(self, tmp_path):
        _write(tmp_path, "framework/scheduler/snapshot.py",
               "from __future__ import annotations\n"
               "import json, hashlib, os\n"
               "from dataclasses import dataclass\n"
               "from pathlib import Path\n"
               "from typing import Optional\n")
        assert L.scheduler_import_violations(tmp_path) == []


# ===========================================================================
# the cloned defaults-only as_of pin (§3 — scheduler cortex reads inherit COG-3)
# ===========================================================================
class TestSchedulerAsOfDefaultsOnly:
    def test_real_tree_is_armed_and_absent(self):
        # VACUITY GUARD — RETIREMENT CONDITION: enable the real-tree as_of scan when
        # framework/scheduler/ lands; companion absence assertion is the tripwire.
        tree = _REPO / L.SCHEDULER_TREE_REL
        assert not tree.exists(), (
            f"{L.SCHEDULER_TREE_REL}/ has LANDED — retire this vacuity skip and enable "
            "the real-tree as_of defaults-only scan")
        assert L.scheduler_asof_default_violations(_REPO) == []
        pytest.skip(f"VACUITY: {L.SCHEDULER_TREE_REL}/ absent this phase — as_of pin "
                    "armed via scratch-tree controls; retire when the planner tree lands.")

    def test_canonical_read_folds_clean(self, tmp_path):
        _write(tmp_path, "framework/scheduler/fold.py",
               "def build():\n"
               "    a = as_of(beliefs, subject_key, scope=sc, observation=cut)\n"
               "    b = as_of(beliefs, subject_key=sk, scope=sc, observation=cut)\n"
               "    return a, b\n")
        assert L.scheduler_asof_default_violations(tmp_path) == []

    @pytest.mark.parametrize("kwarg", [
        "rederive=False", "scope_mode='lenient'", "lineage='correlation'",
        "unknown_mode='implicit'", "supersession_order='ts'", "fence_axis='source'",
        "dimension='budget'", "source='2026-01-01T00:00:00Z'",
    ])
    def test_nondefault_kwarg_is_red(self, tmp_path, kwarg):
        _write(tmp_path, "framework/scheduler/fold.py",
               "def build():\n"
               f"    return as_of(beliefs, subject_key, scope=sc, {kwarg})\n")
        v = L.scheduler_asof_default_violations(tmp_path)
        assert v, kwarg
        assert all(L.RULE_SCHED_ASOF in x for x in v), v

    def test_kwargs_splat_is_red(self, tmp_path):
        _write(tmp_path, "framework/scheduler/fold.py",
               "def build():\n"
               "    return as_of(beliefs, subject_key, scope=sc, **opts)\n")
        assert any(x.endswith("**splat") for x in L.scheduler_asof_default_violations(tmp_path))

    def test_non_asof_call_with_those_kwargs_is_ignored(self, tmp_path):
        _write(tmp_path, "framework/scheduler/fold.py",
               "def build():\n"
               "    return some_other(rederive=False, lineage='x')\n")
        assert L.scheduler_asof_default_violations(tmp_path) == []


# ===========================================================================
# the no-subprocess/no-socket pin (§7.2 — the pure planner never shells out)
# ===========================================================================
class TestSchedulerNoSubprocessNoSocket:
    def test_real_tree_is_armed_and_absent(self):
        # VACUITY GUARD — RETIREMENT CONDITION: enable the real-tree exec scan when
        # framework/scheduler/ lands; companion absence assertion is the tripwire.
        tree = _REPO / L.SCHEDULER_TREE_REL
        assert not tree.exists(), (
            f"{L.SCHEDULER_TREE_REL}/ has LANDED — retire this vacuity skip and enable "
            "the real-tree no-subprocess/no-socket scan")
        assert L.scheduler_subprocess_socket_violations(_REPO) == []
        pytest.skip(f"VACUITY: {L.SCHEDULER_TREE_REL}/ absent this phase — exec pin "
                    "armed via scratch-tree controls; retire when the planner tree lands.")

    def test_pure_planner_folds_clean(self, tmp_path):
        _write(tmp_path, "framework/scheduler/fold.py",
               "import json, hashlib, os\n"
               "from pathlib import Path\n"
               "def build():\n"
               "    return os.path.join('a', 'b')\n")   # os.path.join is NOT an exec sink
        assert L.scheduler_subprocess_socket_violations(tmp_path) == []

    @pytest.mark.parametrize("body", [
        "import subprocess\n",
        "import socket\n",
        "import subprocess, json\n",
        "from subprocess import run\n",
        "from socket import socket\n",
        "import os\ndef f():\n    return os.system('echo hi')\n",
        "import os\ndef f():\n    return os.popen('ls').read()\n",
        "import os\ndef f():\n    return os.execv('/bin/sh', ['sh'])\n",
        "import os\ndef f():\n    return os.fork()\n",
    ])
    def test_exec_and_socket_uses_are_red(self, tmp_path, body):
        _write(tmp_path, "framework/scheduler/fold.py", body)
        assert L.scheduler_subprocess_socket_violations(tmp_path), body
