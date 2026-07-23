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
never shells out or opens a socket — importing subprocess/socket, an os.<exec>() call (via
`os` or an alias), OR a `from os import system|popen|exec*|spawn*|fork` bind (a bare Name the
Attribute call-check can never see) is RED, symmetric to `from subprocess import run`. A
transitive-closure subprocess arm (cloned from the COG-3 shape, with the exact
consequence-import mutant) additionally pins at RUNTIME that the planner tree + the C3 kernel
(framework/projection) + the organs registry pull NOTHING from the action/authority/fidelity
planes — the backstop a static import scan cannot provide.

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

import json
import subprocess
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
        # aliased os module: `import os as o; o.system(...)` — the alias-binding escape the
        # cp1 review named. `func.value.id == "os"` alone missed it; the fix tracks every
        # `import os as <alias>` binding so the exec call REDs through the alias too.
        "import os as o\ndef f():\n    return o.system('echo hi')\n",
    ])
    def test_exec_and_socket_uses_are_red(self, tmp_path, body):
        _write(tmp_path, "framework/scheduler/fold.py", body)
        assert L.scheduler_subprocess_socket_violations(tmp_path), body

    @pytest.mark.parametrize("body", [
        "from os import system\ndef f():\n    return system('echo hi')\n",
        "from os import popen\ndef f():\n    return popen('ls').read()\n",
        "from os import system as s\ndef f():\n    return s('echo hi')\n",   # aliased
        "from os import execv\ndef f():\n    return execv('/bin/sh', ['sh'])\n",
        "from os import fork\ndef f():\n    return fork()\n",
    ])
    def test_from_os_import_exec_primitive_is_red(self, tmp_path, body):
        # MF1 (cp1 exec-pin gap): `from os import system|popen|exec*|spawn*|fork` statically
        # binds a shell/exec primitive as a BARE NAME the os.<attr> Attribute call-check can
        # never see (`from os import system; system(cmd)`). It must RED at the import site,
        # symmetric to how `from subprocess import run` already REDs. The aliased `as s`
        # spelling REDs too — the ORIGINAL imported name is the exec primitive; asname is
        # irrelevant. Without the lib fix these each scanned GREEN (the named §7.2 escape).
        _write(tmp_path, "framework/scheduler/fold.py", body)
        v = L.scheduler_subprocess_socket_violations(tmp_path)
        assert v, body
        assert all(L.RULE_SCHED_EXEC in x for x in v), v

    def test_from_os_import_innocuous_symbol_stays_green(self, tmp_path):
        # POSITIVE CONTROL (the fix must not over-broaden): `from os import path|getcwd|
        # environ` are legitimate stdlib names, NOT exec sinks — they must stay GREEN, or the
        # from-os arm would false-positive on ordinary planner code.
        _write(tmp_path, "framework/scheduler/fold.py",
               "from os import path, getcwd, environ\n"
               "def f():\n    return path.join(getcwd(), 'x')\n")
        assert L.scheduler_subprocess_socket_violations(tmp_path) == []


# ===========================================================================
# the transitive import-closure arm (§8.4 — cloned from the COG-3 shape,
# test_cog3_objectives_ast_pin.TestTransitiveClosure, WITH the exact
# consequence-import mutant). A static import pin cannot see a transitive edge
# (module A imports allowed B, B top-level-imports forbidden C); the runtime
# backstop is a sys.modules sweep after a subprocess import. The pure planner
# tree + the C3 kernel (framework/projection) + the organs registry must pull
# NOTHING from the action/authority/fidelity planes.
# ===========================================================================
# the pure planner's forbidden closure — IDENTICAL to the COG-3 objectives set:
# authority/acting/frontdoor/fidelity/missions/ovi. The planner legally reaches
# framework.cortex + framework.objectives (the sanctioned query/serve surfaces),
# so those are NOT forbidden; the action/authority/fidelity planes are. (Because
# framework.authority is in this real set, the COG-3 consequence→authority mutant
# trips it directly — no separate demonstration set is needed, unlike the parity
# comparator which legally reaches authority.)
_SCHED_FORBIDDEN_NS = ("framework.authority", "framework.acting", "framework.frontdoor",
                       "framework.fidelity", "framework.missions", "framework.ovi")
# the three protected trees this closure covers (all absent this phase, §8.4).
_SCHED_PROTECTED_TREES = ("framework/scheduler", "framework/organs", "framework/projection")
_SCHED_PROTECTED_MODULES = ("framework.scheduler", "framework.organs", "framework.projection")


def _closure_after_import(module_name: str, extra_path: Path | None = None):
    """Subprocess-import `module_name` (framework importable via cwd=_REPO) and return
    (returncode, stderr, forbidden_modules_loaded). Cloned from the COG-3 shape
    (test_cog3_objectives_ast_pin) so the COG-4 planner closure uses identical machinery."""
    lines = ["import sys, json"]
    if extra_path is not None:
        lines.append(f"sys.path.insert(0, {str(extra_path)!r})")
    lines += [
        f"import {module_name}",
        f"FZ = {_SCHED_FORBIDDEN_NS!r}",
        "loaded = sorted(m for m in sys.modules "
        "if any(m == f or m.startswith(f + '.') for f in FZ))",
        "print(json.dumps(loaded))",
    ]
    r = subprocess.run([sys.executable, "-c", "\n".join(lines)],
                       cwd=str(_REPO), capture_output=True, text=True)
    loaded = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else []
    return r.returncode, r.stderr, loaded


class TestSchedulerTransitiveClosure:
    def test_real_trees_are_armed_and_absent(self):
        # VACUITY GUARD — RETIREMENT CONDITION: when framework/scheduler/ (or organs/,
        # projection/) lands, delete the skip and enable the real-tree closure scan —
        # subprocess-import each protected package and assert its module closure excludes
        # the action/authority/fidelity planes (_SCHED_FORBIDDEN_NS). The companion
        # assertion fails the instant any protected tree lands, so this skip cannot silently
        # persist (§13). Retire the skip when framework/scheduler lands.
        for rel in _SCHED_PROTECTED_TREES:
            assert not (_REPO / rel).exists(), (
                f"{rel}/ has LANDED — retire this vacuity skip and enable the real-tree "
                "transitive-closure scan per the docstring RETIREMENT CONDITION")
        # genuinely armed: over the absent trees the subprocess import raises ModuleNotFound
        # (a vacuously clean closure) — it scans for real the moment a tree lands.
        for mod in _SCHED_PROTECTED_MODULES:
            rc, stderr, _ = _closure_after_import(mod)
            assert rc != 0 and "No module named" in stderr, (mod, rc, stderr)
        pytest.skip("VACUITY: framework/scheduler|organs|projection absent this phase — "
                    "transitive-closure gate armed via the consequence-import fixture; "
                    "retire the skip when framework/scheduler lands.")

    def test_consequence_mutant_loads_authority(self, tmp_path):
        # FIXTURE-TREE PROOF (the exact COG-3 consequence-import mutant): a scratch package
        # that imports framework.fidelity.consequence transitively loads framework.authority
        # (consequence.py:33 top-level import) — which is in the planner's forbidden closure.
        # The detector MUST see it, proving the closure machinery follows transitive edges and
        # bites NOW even while the real trees are absent (a gate without a biting mutant is
        # decoration — §12).
        _write(tmp_path, "_cog4_sched_scratch_leak/__init__.py",
               "import framework.fidelity.consequence  # MUTANT: pulls the action plane\n")
        rc, stderr, loaded = _closure_after_import("_cog4_sched_scratch_leak",
                                                   extra_path=tmp_path)
        assert rc == 0, stderr
        assert "framework.authority" in loaded, loaded

    def test_clean_scratch_pkg_closure_is_empty(self, tmp_path):
        # ANTI-NO-OP CONTROL: a scratch pkg importing only stdlib has an EMPTY forbidden
        # closure, so the backstop is genuinely discriminating (not always-RED).
        _write(tmp_path, "_cog4_sched_scratch_clean/__init__.py",
               "import json, hashlib  # only stdlib\n")
        rc, stderr, loaded = _closure_after_import("_cog4_sched_scratch_clean",
                                                   extra_path=tmp_path)
        assert rc == 0, stderr
        assert loaded == []
