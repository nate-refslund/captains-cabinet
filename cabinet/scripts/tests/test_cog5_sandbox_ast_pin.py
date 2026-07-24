"""COG-5 §8.4/§10 sibling pin — the SANDBOX (unprivileged verify harness / arena
execution substrate) forbidden-import pin. Tests-first, gates-before-code
(contract cognitive-core-phase-5-contract-2026-07-24 §10: "the harness may import
git/subprocess machinery; it may NOT import credential stores or the archive
writer"; §8.4: "no credential-store import reachable from any candidate-visible
surface").

sandbox.py prepares candidate worktrees + execs verify stages UNPRIVILEGED; it
is the one sanctioned subprocess site (unlike the pure league fold). So this pin
is a DENY-list of exactly the two classes §10 names, NOT an allow-list:
  - the ARCHIVE WRITER (framework.evolution.archive) — the harness executes
    candidates; it must never hold a write path to the immutable archive.
  - a credential store (framework.fidelity.oauth_llm) — the §4.4
    harness-holds-credentials holder must not be reachable from the
    candidate-visible exec surface (the candidate never sees the key).
Everything else — subprocess, os, shutil, tempfile, pathlib, evolution-internal
helpers — is allowed. The action lanes framework.{frontdoor,acting} are fenced
from sandbox.py by ROW 10 (the reverse row, sandbox.py lives under
framework/evolution/), not re-added here; the broader runtime env-scrub is the
BEHAVIORAL sim-7 escape battery (a later wave), not a static import pin.

VACUITY — retire when framework/evolution/sandbox.py lands (W3, §13 law): the
real-tree arm is green-by-vacuity while sandbox.py is absent and carries a
COMPANION absence assertion, so the vacuity cannot silently persist after it
lands. The scratch-tree controls run NOW and prove the scanner bites (§12).
RETIREMENT CONDITION: when sandbox.py lands (W3), the companion trips RED; delete
it and keep test_real_tree_scans_clean as the live pin.

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


class TestSandboxForbiddenImportPin:
    def test_target_absent_and_scanner_green_by_vacuity(self):
        assert not (_REPO / L.SANDBOX_FILE_REL).exists(), (
            "sandbox.py LANDED — retire this vacuity guard per the RETIREMENT "
            "CONDITION: delete the absence companion, keep the real-tree scan.")
        assert L.sandbox_forbidden_import_violations(_REPO) == []   # green-by-vacuity

    def test_git_subprocess_machinery_folds_clean(self, tmp_path):
        # the harness IS the sanctioned subprocess site: git-via-subprocess +
        # tempfile/shutil worktree prep are all legitimate (§4.2/§10).
        _write(tmp_path, "framework/evolution/sandbox.py",
               "from __future__ import annotations\n"
               "import subprocess, os, shutil, tempfile\n"
               "from pathlib import Path\n"
               "def prepare(base):\n"
               "    return subprocess.run(['git', 'worktree', 'add', base],\n"
               "                          capture_output=True)\n")
        assert L.sandbox_forbidden_import_violations(tmp_path) == []

    @pytest.mark.parametrize("stmt", [
        "import framework.evolution.archive\n",                     # the archive writer
        "from framework.evolution.archive import append_row\n",
        "from framework.evolution import archive\n",                # alias spelling
        "from framework.fidelity.oauth_llm import get_token\n",     # credential holder
        "import framework.fidelity.oauth_llm\n",
    ])
    def test_forbidden_imports_are_red(self, tmp_path, stmt):
        _write(tmp_path, "framework/evolution/sandbox.py", stmt)
        v = L.sandbox_forbidden_import_violations(tmp_path)
        assert v, stmt
        assert all(L.RULE_SANDBOX_IMPORT in x for x in v), v

    def test_evolution_internal_non_archive_folds_clean(self, tmp_path):
        # the harness may use OTHER evolution-internal helpers — only the archive
        # WRITER is denied (candidates must never write the archive).
        _write(tmp_path, "framework/evolution/sandbox.py",
               "from framework.evolution import candidate\n"
               "from framework.evolution.contracts import ValidationContext\n")
        assert L.sandbox_forbidden_import_violations(tmp_path) == []

    def test_archive_word_as_data_folds_clean(self, tmp_path):
        # anti-over-fencing: the WORD 'archive' as data/comment is not an import.
        _write(tmp_path, "framework/evolution/sandbox.py",
               "# the harness never imports the archive writer\n"
               "MODE = {'archive': False}\n"
               "def run():\n    return MODE\n")
        assert L.sandbox_forbidden_import_violations(tmp_path) == []
