"""COG-5 §10 sibling pin — the LEAGUE (pure ranking fold) symbol-level import
ALLOW-LIST + the no-subprocess/no-socket pin. Tests-first, gates-before-code
(contract cognitive-core-phase-5-contract-2026-07-24 §10: "league tree imports =
stdlib | evolution-internal | the fidelity scorer/leakguard/officer_runner
PUBLIC surfaces | nothing else — no subprocess in the pure ranking fold; the
arena/sandbox layer is the sanctioned subprocess site").

The league consumes arena + scorers + archive and RANKS; it is not the execution
site. So its imports are allow-listed to stdlib | framework.evolution.* |
framework.fidelity.{scorer,leakguard,officer_runner}; anything else is RED — the
action/authority planes, framework.fidelity.oauth_llm (the credential holder),
any OTHER fidelity module (graduation/consequence/judge_calibration go through
the scorers adapter, not the league), a third-party dep. Separately, the pure
fold takes NO subprocess/socket import and makes no os.<exec> call. (League
blindness to holdout_gen is NOT this pin's job — evolution-internal is allowed
here; ROW 8 + test_cog5_holdout_ast_pin enforce holdout invisibility.)

VACUITY — retire when framework/evolution/league.py lands (W6, §13 law): the
real-tree arms are green-by-vacuity while league.py is absent and each carries a
COMPANION absence assertion, so the vacuity cannot silently persist after it
lands. The scratch-tree controls run NOW and prove the scanners bite (§12).
RETIREMENT CONDITION: when league.py lands (W6), the companions trip RED; delete
them and keep the real-tree scans as the live pins.

S0: python3.12, no DB, no network. Provenance: authored per the 2026-07-07
full-autonomy grant + the 2026-07-20 cognitive-masterplan continuous grant.
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

import lib_cog5_ast_pins as L  # noqa: E402


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


class TestLeagueImportPin:
    def test_target_absent_and_scanner_green_by_vacuity(self):
        assert not (_REPO / L.LEAGUE_FILE_REL).exists(), (
            "league.py LANDED — retire this vacuity guard per the RETIREMENT "
            "CONDITION: delete the absence companion, keep the real-tree scan.")
        assert L.league_import_violations(_REPO) == []   # green-by-vacuity

    def test_sanctioned_surface_folds_clean(self, tmp_path):
        _write(tmp_path, "framework/evolution/league.py",
               "from __future__ import annotations\n"
               "import json, hashlib\n"
               "from pathlib import Path\n"
               "from framework.evolution import archive, scorers, arena\n"
               "from framework.fidelity.scorer import score_case\n"
               "from framework.fidelity.leakguard import filter_mcp_result\n"
               "from framework.fidelity.officer_runner import run_case\n"
               "from . import candidate\n")
        assert L.league_import_violations(tmp_path) == []

    @pytest.mark.parametrize("stmt", [
        "from framework.fidelity.oauth_llm import get_token\n",     # credential holder
        "from framework.fidelity.graduation import evaluate\n",     # non-sanctioned fidelity
        "from framework.fidelity.consequence import _REVIEW_SOURCES\n",
        "from framework.fidelity.judge_calibration import JUDGE_HARD_BAR\n",
        "from framework.authority.matrix import RISK_CLASSES\n",    # action/authority plane
        "from framework.frontdoor import door\n",
        "from framework.acting import runner\n",
        "import framework.learning.gate\n",                         # NO learning in the fold
        "from framework.fidelity import scorer\n",                  # fidelity module OBJECT
        "import yaml\n",                                            # third-party dep
    ])
    def test_forbidden_imports_are_red(self, tmp_path, stmt):
        _write(tmp_path, "framework/evolution/league.py", stmt)
        assert L.league_import_violations(tmp_path), stmt

    def test_stdlib_and_evolution_internal_fold_clean(self, tmp_path):
        _write(tmp_path, "framework/evolution/league.py",
               "import json, hashlib, os\n"
               "from dataclasses import dataclass\n"
               "from framework.evolution.archive import append_row\n")
        assert L.league_import_violations(tmp_path) == []


class TestLeagueNoSubprocessNoSocket:
    def test_target_absent_and_scanner_green_by_vacuity(self):
        assert not (_REPO / L.LEAGUE_FILE_REL).exists(), (
            "league.py LANDED — retire this vacuity guard per the RETIREMENT "
            "CONDITION: delete the absence companion, keep the real-tree scan.")
        assert L.league_subprocess_socket_violations(_REPO) == []

    def test_pure_fold_folds_clean(self, tmp_path):
        _write(tmp_path, "framework/evolution/league.py",
               "import json, os\n"
               "from pathlib import Path\n"
               "def rank():\n    return os.path.join('a', 'b')\n")   # NOT an exec sink
        assert L.league_subprocess_socket_violations(tmp_path) == []

    @pytest.mark.parametrize("body", [
        "import subprocess\n",
        "import socket\n",
        "from subprocess import run\n",
        "from socket import socket\n",
        "import os\ndef f():\n    return os.system('echo hi')\n",
        "import os as o\ndef f():\n    return o.popen('ls').read()\n",  # aliased os
        "from os import system\ndef f():\n    return system('x')\n",    # bare-name exec
    ])
    def test_exec_and_socket_uses_are_red(self, tmp_path, body):
        _write(tmp_path, "framework/evolution/league.py", body)
        v = L.league_subprocess_socket_violations(tmp_path)
        assert v, body
        assert all(L.RULE_LEAGUE_EXEC in x for x in v), v

    def test_from_os_innocuous_symbol_stays_green(self, tmp_path):
        # anti-over-fencing: os.path/getcwd/environ are not exec sinks.
        _write(tmp_path, "framework/evolution/league.py",
               "from os import path, getcwd, environ\n"
               "def f():\n    return path.join(getcwd(), 'x')\n")
        assert L.league_subprocess_socket_violations(tmp_path) == []
