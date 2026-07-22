"""COG-3 STEP 0 — the census compiler-wall (contract §6.2 / :110), tests-first.

The foundry law (:110): no existing joint may absorb causal-epistemic derivation
without becoming the forbidden mega-compiler. Mechanically: no file under
framework/objectives/ may match *compiler*.py, and adding one sends the REAL
census RED on named_compiler_modules. This is the "trivial half" of §6.2 (the
binding wall is the zero-headroom module/line budgets, handled by the landing
allowance rows — NOT this suite), labeled as such.

Green-by-vacuity today. The mutant is proven against a SCRATCH COPY of the tree
(never the clean clone — §6.2(3) protocol / the task's stated option), so no
in-clone mutation can race another test.

S0: python3.12, no DB.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
_CENSUS = _REPO / "cabinet" / "scripts" / "cognitive-architecture-census.py"

_IGNORE = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "node_modules")


def _run_census(root: Path) -> dict:
    r = subprocess.run(
        [sys.executable, str(_CENSUS), "--root", str(root), "--json"],
        capture_output=True, text=True)
    assert r.stdout, r.stderr
    return json.loads(r.stdout)


class TestCompilerWall:
    def test_no_compiler_module_under_objectives_on_real_tree(self):
        # the permanent assertion — green by vacuity now, RED the instant a
        # framework/objectives/*compiler*.py appears.
        objdir = _REPO / "framework" / "objectives"
        assert sorted(objdir.rglob("*compiler*.py")) == []

    def test_named_compiler_budget_is_one_on_the_real_tree(self):
        rep = _run_census(_REPO)
        # exactly framework/missions/compiler.py — naming discipline holds the line.
        assert rep["observed"]["named_compiler_modules"] == 1
        assert rep["maximums"]["named_compiler_modules"] == 1

    def test_objectives_compiler_sends_the_real_census_red(self, tmp_path):
        copy = tmp_path / "clone"
        shutil.copytree(_REPO, copy, ignore=_IGNORE, symlinks=True)

        base = _run_census(copy)
        assert base["observed"]["named_compiler_modules"] == 1
        assert "named_compiler_modules" not in {f["budget"] for f in base["failures"]}

        # inject the mutant into the COPY only.
        (copy / "framework" / "objectives").mkdir(parents=True, exist_ok=True)
        (copy / "framework" / "objectives" / "spec_compiler.py").write_text(
            "x = 1\n", encoding="utf-8")

        mut = _run_census(copy)
        assert mut["observed"]["named_compiler_modules"] == 2
        failing = {f["budget"] for f in mut["failures"]}
        assert "named_compiler_modules" in failing, mut["failures"]
        assert mut["ok"] is False

    def test_census_is_green_again_after_removing_the_mutant(self, tmp_path):
        # RED-then-GREEN: the wall is a tripwire, not a permanent state.
        copy = tmp_path / "clone2"
        shutil.copytree(_REPO, copy, ignore=_IGNORE, symlinks=True)
        (copy / "framework" / "objectives").mkdir(parents=True, exist_ok=True)
        mutant = copy / "framework" / "objectives" / "spec_compiler.py"
        mutant.write_text("x = 1\n", encoding="utf-8")
        assert _run_census(copy)["observed"]["named_compiler_modules"] == 2
        mutant.unlink()
        assert _run_census(copy)["observed"]["named_compiler_modules"] == 1
