"""COG-4 §8.4 sibling pin #2 — the DISPATCH CLI import boundary. Tests-first,
gates-before-code (contract cognitive-core-phase-4-contract-2026-07-23 §8.4/§7.3).

The dispatch recheck (`cabinet/scripts/cog4-dispatch-shadow.py`) is the SEPARATE
dispatcher (charter L116). §8.4 pins that it may import EXACTLY:
  * `risk_of, resolve_verdict, read_cell_state, _act_with_undo_gap` from
    framework.authority.policy_engine  (the read-only shadow authority joint)
  * `evaluate` from framework.fidelity.graduation
  * the framework.scheduler.serve surface  (to serve the schedule through the kernel)
— so the dispatcher can never grow into an executor. Everything else is RED: the
acting/frontdoor doors, the fold/snapshot planner internals, any policy_engine symbol
beyond the four (a module-object import is a dot-into bypass — RED), the classifier/
matrix (that is the parity comparator's surface, not the dispatcher's), or a third-party
dep.

VACUITY — retire when cabinet/scripts/cog4-dispatch-shadow.py lands (§13 law): the
real-target arm SKIPS while the CLI is absent, with a COMPANION assertion that the file
does not exist so the skip cannot silently persist after the CLI lands (the companion
goes RED the instant the CLI appears). The scratch-file positive/negative controls run
NOW and prove the scanner bites.
RETIRED (integrator corpus surgery per §13 + the unit contradictions[] routes, W5
landing 2026-07-24): cabinet/scripts/cog4-dispatch-shadow.py landed (W5 x1, 7272db13)
— the real-target vacuity guard is converted per its own RETIREMENT CONDITION: the
live dispatch_import_violations scan now runs over the REAL file. The scratch-file
controls stay, proving the scanner keeps biting.

S0: python3.12, no DB, no network. Provenance: authored per the 2026-07-07 full-autonomy
grant + the 2026-07-20 cognitive-masterplan continuous grant.
"""
from __future__ import annotations

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


class TestDispatchImportPin:
    # RETIRED vacuity skip (integrator corpus surgery per §13 + the unit
    # contradictions[] routes, W5 landing 2026-07-24): the guard's RETIREMENT
    # CONDITION — "when cog4-dispatch-shadow.py lands, delete the skip and keep the
    # green-by-vacuity assertion as the real pin" — was discharged by W5 x1
    # (7272db13, the dispatch-shadow CLI). The companion absence assertion tripped
    # RED as designed; the assertion below is now the REAL-FILE §8.4 symbol-level
    # import pin over the landed dispatcher (the scratch-file controls below keep
    # proving it bites).
    def test_real_cli_scans_clean(self):
        cli = _REPO / L.DISPATCH_CLI_REL
        assert cli.is_file(), (
            f"{L.DISPATCH_CLI_REL} vanished — the real-file pin lost its subject")
        assert L.dispatch_import_violations(_REPO) == []

    def test_sanctioned_surface_folds_clean(self, tmp_path):
        _write(tmp_path, L.DISPATCH_CLI_REL,
               "from __future__ import annotations\n"
               "import json, argparse\n"
               "from pathlib import Path\n"
               "from framework.authority.policy_engine import (\n"
               "    risk_of, resolve_verdict, read_cell_state, _act_with_undo_gap)\n"
               "from framework.fidelity.graduation import evaluate\n"
               "from framework.scheduler.serve import serve_schedule\n"
               "import framework.scheduler.serve\n")
        assert L.dispatch_import_violations(tmp_path) == []

    @pytest.mark.parametrize("stmt", [
        # a fifth policy_engine symbol beyond the sanctioned four
        "from framework.authority.policy_engine import act_with_undo_gap\n",
        "from framework.authority.policy_engine import _write_cell_state\n",
        # the policy_engine MODULE object — a dot-into bypass
        "import framework.authority.policy_engine\n",
        "from framework.authority import policy_engine\n",
        # graduation beyond `evaluate`
        "from framework.fidelity.graduation import _promote\n",
        # the executor doors — the exact thing the dispatcher must never grow into
        "from framework.acting import run_action_lane\n",
        "from framework.acting.runner import execute\n",
        "from framework.frontdoor.door import post\n",
        # the planner internals — the dispatcher serves via .serve only, never the fold
        "from framework.scheduler.fold import build_schedule\n",
        "from framework.scheduler.snapshot import build_snapshot\n",
        "import framework.scheduler\n",
        # the parity comparator's surface is NOT the dispatcher's
        "from framework.authority.classifier import classify_action\n",
        "from framework.authority.matrix import RISK_CLASSES\n",
        "from framework.organs.registry import load_organ_registry\n",
        # the consequence/evidence store — never
        "from framework.fidelity.consequence import append_event\n",
        # third-party dep
        "import requests\n",
    ])
    def test_forbidden_imports_are_red(self, tmp_path, stmt):
        _write(tmp_path, L.DISPATCH_CLI_REL, stmt)
        assert L.dispatch_import_violations(tmp_path), stmt

    def test_the_four_symbols_fold_but_a_fifth_reds(self, tmp_path):
        _write(tmp_path, L.DISPATCH_CLI_REL,
               "from framework.authority.policy_engine import "
               "risk_of, resolve_verdict, read_cell_state, _act_with_undo_gap, _apply\n")
        v = L.dispatch_import_violations(tmp_path)
        assert any(x.split()[-1] == "_apply" for x in v), v
        assert all(x.split()[-1] != "risk_of" for x in v)
        assert all(x.split()[-1] != "_act_with_undo_gap" for x in v)

    def test_stdlib_only_folds_clean(self, tmp_path):
        _write(tmp_path, L.DISPATCH_CLI_REL,
               "import json, sys, argparse, hashlib\n"
               "from pathlib import Path\n"
               "from dataclasses import dataclass\n")
        assert L.dispatch_import_violations(tmp_path) == []
