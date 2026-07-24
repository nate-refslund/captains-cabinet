"""COG-4 §8.4 sibling pin #3 — the PARITY CLI import boundary + a transitive-closure
backstop. Tests-first, gates-before-code (contract cognitive-core-phase-4-contract-
2026-07-23 §8.4/§5.3).

`cabinet/scripts/cog4-parity.py` is the ONE sanctioned dual-plane importer (§5.3): it
independently computes the ACTION_TYPES-path tuple AND the descriptor-path tuple and
compares them (the N9 parity gate). §8.4 pins that it may import EXACTLY:
  * `classify_action` from framework.authority.classifier
  * the matrix mapping-surface read accessors — RISK_CLASSES + load_matrix / matrix_policy
    / ceiling_members (which expose the ceiling_frozenset_map policy key)
  * the same four read-only policy_engine symbols + graduation.evaluate the dispatcher pins
  * the organs PUBLIC registry / descriptor surface
— so the comparator stays a comparator, never a resolver anything in framework/ could
grow to depend on, and never an executor. Everything else is RED (a module-object import
of any symbol-restricted module is a dot-into bypass; the scheduler serve surface is the
DISPATCHER's, not the comparator's; framework.acting/frontdoor and a direct
framework.fidelity.consequence import are RED).

Plus a transitive-closure subprocess backstop cloned from the COG-3 shape: the comparator
must never REACH the executor doors (framework.acting / framework.frontdoor). The exact
COG-3 consequence-import mutant proves the closure detector follows transitive edges; an
executor-reach mutant proves the parity-forbidden set bites; a clean scratch control
proves it is not always-RED.

VACUITY — retire when cabinet/scripts/cog4-parity.py lands (§13 law): the real-target arms
SKIP while the CLI is absent, each with a COMPANION assertion that the file does not exist
so the skip cannot silently persist after the CLI lands. The scratch controls run NOW and
prove the pin + closure bite.
RETIREMENTS (integrator corpus surgery per §13 + the unit contradictions[] routes,
W4 landing 2026-07-24): cabinet/scripts/cog4-parity.py landed (W4 v2, 9df66b12 +
dc14c0e6) — both real-target vacuity guards are converted per their own RETIREMENT
CONDITIONS: the import pin now runs the live parity_import_violations scan over the
real file, and the closure arm RUNS the real CLI hermetically (runpy) and asserts
its module closure excludes the executor doors. The scratch controls stay, proving
the pin + closure machinery bites.

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
for _p in (str(_HERE), str(_REPO)):
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
class TestParityImportPin:
    # RETIRED vacuity skip (integrator corpus surgery per §13 + the unit
    # contradictions[] routes, W4 landing 2026-07-24): the guard's RETIREMENT
    # CONDITION — "when cog4-parity.py lands, delete the skip and keep the
    # green-by-vacuity assertion as the real pin" — was discharged by W4 v2
    # (9df66b12, the parity CLI). The companion absence assertion tripped RED as
    # designed; the assertion below is now the REAL-FILE §8.4 symbol-level import
    # pin over the landed comparator (the scratch-file controls below keep proving
    # it bites).
    def test_real_cli_scans_clean(self):
        cli = _REPO / L.PARITY_CLI_REL
        assert cli.is_file(), (
            f"{L.PARITY_CLI_REL} vanished — the real-file pin lost its subject")
        assert L.parity_import_violations(_REPO) == []

    def test_sanctioned_dual_plane_surface_folds_clean(self, tmp_path):
        _write(tmp_path, L.PARITY_CLI_REL,
               "from __future__ import annotations\n"
               "import json, argparse\n"
               "from pathlib import Path\n"
               "from framework.authority.classifier import classify_action\n"
               "from framework.authority.matrix import (\n"
               "    RISK_CLASSES, load_matrix, matrix_policy, ceiling_members)\n"
               "from framework.authority.policy_engine import (\n"
               "    risk_of, resolve_verdict, read_cell_state, _act_with_undo_gap)\n"
               "from framework.fidelity.graduation import evaluate\n"
               "from framework.organs.registry import load_organ_registry\n"
               "from framework.organs.descriptor import resolve_descriptor\n"
               "import framework.organs.registry\n")
        assert L.parity_import_violations(tmp_path) == []

    @pytest.mark.parametrize("stmt", [
        # classifier beyond `classify_action`, and its module object
        "from framework.authority.classifier import ACTION_TYPES\n",
        "import framework.authority.classifier\n",
        "from framework.authority import classifier\n",
        # matrix beyond the mapping-surface accessors, and its module object
        "from framework.authority.matrix import validate_matrix\n",
        "from framework.authority.matrix import no_ceiling_or_prod_auto\n",
        "import framework.authority.matrix\n",
        # policy_engine beyond the four, and its module object
        "from framework.authority.policy_engine import _apply\n",
        "import framework.authority.policy_engine\n",
        # graduation beyond `evaluate`
        "from framework.fidelity.graduation import _promote\n",
        # a DIRECT consequence import (parity reaches it only transitively via graduation)
        "from framework.fidelity.consequence import append_event\n",
        # the executor doors — never
        "from framework.acting import run_action_lane\n",
        "from framework.frontdoor.door import post\n",
        # the scheduler serve surface is the DISPATCHER's, not the comparator's
        "from framework.scheduler.serve import serve_schedule\n",
        "from framework.scheduler.fold import build_schedule\n",
        # the organs PACKAGE root (not the registry/descriptor modules) is not the surface
        "from framework.organs import registry\n",
        "import framework.organs\n",
        # third-party dep
        "import requests\n",
    ])
    def test_forbidden_imports_are_red(self, tmp_path, stmt):
        _write(tmp_path, L.PARITY_CLI_REL, stmt)
        assert L.parity_import_violations(tmp_path), stmt

    def test_matrix_accessors_fold_but_a_nonaccessor_reds(self, tmp_path):
        _write(tmp_path, L.PARITY_CLI_REL,
               "from framework.authority.matrix import "
               "RISK_CLASSES, load_matrix, matrix_policy, ceiling_members, validate_matrix\n")
        v = L.parity_import_violations(tmp_path)
        assert any(x.split()[-1] == "validate_matrix" for x in v), v
        assert all(x.split()[-1] != "RISK_CLASSES" for x in v)
        assert all(x.split()[-1] != "ceiling_members" for x in v)

    def test_stdlib_only_folds_clean(self, tmp_path):
        _write(tmp_path, L.PARITY_CLI_REL,
               "import json, sys, argparse, hashlib\n"
               "from pathlib import Path\n")
        assert L.parity_import_violations(tmp_path) == []


# ===========================================================================
# the transitive-closure backstop (cloned from the COG-3 shape)
# ===========================================================================
# the comparator must never REACH the executor doors — a read-only comparator legally
# reaches authority/matrix/graduation (and consequence only transitively via graduation),
# but never the acting/frontdoor planes.
_PARITY_FORBIDDEN_NS = ("framework.acting", "framework.frontdoor")
# the exact COG-3 demonstration namespace — used only to prove the closure detector
# follows transitive edges (consequence.py top-level imports framework.authority).
_DEMO_FORBIDDEN_NS = ("framework.authority", "framework.acting", "framework.frontdoor",
                      "framework.fidelity", "framework.missions", "framework.ovi")


def _closure_after_import(module_name: str, forbidden_ns, extra_path: Path | None = None):
    """Subprocess-import `module_name` (framework importable via cwd=_REPO) and return
    (returncode, stderr, forbidden_modules_loaded)."""
    lines = ["import sys, json"]
    if extra_path is not None:
        lines.append(f"sys.path.insert(0, {str(extra_path)!r})")
    lines += [
        f"import {module_name}",
        f"FZ = {tuple(forbidden_ns)!r}",
        "loaded = sorted(m for m in sys.modules "
        "if any(m == f or m.startswith(f + '.') for f in FZ))",
        "print(json.dumps(loaded))",
    ]
    r = subprocess.run([sys.executable, "-c", "\n".join(lines)],
                       cwd=str(_REPO), capture_output=True, text=True)
    loaded = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else []
    return r.returncode, r.stderr, loaded


class TestParityTransitiveClosure:
    # RETIRED vacuity skip (integrator corpus surgery per §13 + the unit
    # contradictions[] routes, W4 landing 2026-07-24): the guard's RETIREMENT
    # CONDITION — "when cog4-parity.py lands, run it (subprocess / runpy) and
    # assert its module closure excludes framework.acting/framework.frontdoor" —
    # was discharged by W4 v2 (9df66b12). The companion absence assertion tripped
    # RED as designed; the arm below now RUNS the real CLI hermetically via runpy.
    # An empty manifest dir takes the documented exit-3 zero-ops refusal AFTER the
    # full §8.4 import surface is loaded (top-level imports + the registry load),
    # so the run closure is honestly populated, never vacuous; the rc==0
    # full-pipeline closure over fixture manifests lives in
    # test_cog4_parity_cli.py::TestBoundaryLawsLive::
    # test_hermetic_run_closure_excludes_executor_doors (the landed battery this
    # arm's condition names).
    def test_real_cli_run_closure_excludes_executor_doors(self, tmp_path):
        cli = _REPO / L.PARITY_CLI_REL
        assert cli.is_file(), (
            f"{L.PARITY_CLI_REL} vanished — the run-closure arm lost its subject")
        empty = tmp_path / "organs-empty"
        empty.mkdir()
        out = tmp_path / "rec.json"
        driver = (
            "import sys, json, runpy\n"
            f"sys.argv = ['cog4-parity.py', '--manifest-dir', {str(empty)!r}, "
            f"'--out', {str(out)!r}]\n"
            "rc = 0\n"
            "try:\n"
            f"    runpy.run_path({str(cli)!r}, run_name='__main__')\n"
            "except SystemExit as e:\n"
            "    rc = int(e.code or 0)\n"
            f"FZ = {_PARITY_FORBIDDEN_NS!r}\n"
            "doors = sorted(m for m in sys.modules "
            "if any(m == f or m.startswith(f + '.') for f in FZ))\n"
            "fw = sorted(m for m in sys.modules if m.startswith('framework.'))\n"
            "print(json.dumps({'rc': rc, 'doors': doors, 'fw': fw}))\n"
        )
        r = subprocess.run([sys.executable, "-c", driver], cwd=str(_REPO),
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout.strip().splitlines()[-1])
        assert payload["rc"] == 3, payload      # the zero-ops setup refusal — a REAL run
        assert payload["fw"] != [], payload     # the import surface genuinely loaded
        assert payload["doors"] == [], (
            f"the comparator's run closure reached the executor doors: "
            f"{payload['doors']}")

    def test_consequence_mutant_edge_following(self, tmp_path):
        # the exact COG-3 consequence-import mutant: importing framework.fidelity.consequence
        # transitively loads framework.authority (consequence.py top-level import). The closure
        # detector MUST see it — proving the machinery follows transitive edges, not a no-op.
        _write(tmp_path, "_cog4_scratch_conseq/__init__.py",
               "import framework.fidelity.consequence  # MUTANT: transitive edge to authority\n")
        rc, stderr, loaded = _closure_after_import("_cog4_scratch_conseq",
                                                   _DEMO_FORBIDDEN_NS, extra_path=tmp_path)
        assert rc == 0, stderr
        assert "framework.authority" in loaded, loaded

    def test_executor_reach_trips_parity_forbidden_set(self, tmp_path):
        # a comparator that reaches an executor door trips the REAL parity-forbidden set —
        # proving the guard-as-configured bites (not just the demonstration set).
        _write(tmp_path, "_cog4_scratch_exec/__init__.py",
               "import framework.acting  # MUTANT: a comparator must never reach the actor plane\n")
        rc, stderr, loaded = _closure_after_import("_cog4_scratch_exec",
                                                   _PARITY_FORBIDDEN_NS, extra_path=tmp_path)
        assert rc == 0, stderr
        assert "framework.acting" in loaded, loaded

    def test_clean_scratch_closure_is_empty(self, tmp_path):
        # the anti-no-op control: a pkg importing only stdlib has an EMPTY forbidden closure,
        # so the backstop is genuinely discriminating.
        _write(tmp_path, "_cog4_scratch_clean/__init__.py",
               "import json, hashlib  # only stdlib\n")
        rc, stderr, loaded = _closure_after_import("_cog4_scratch_clean",
                                                   _PARITY_FORBIDDEN_NS, extra_path=tmp_path)
        assert rc == 0, stderr
        assert loaded == []
