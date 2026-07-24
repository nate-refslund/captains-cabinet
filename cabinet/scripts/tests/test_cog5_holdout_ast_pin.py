"""COG-5 §7.3/§8.4 sibling pin — the frozen-holdout league-invisibility IMPORTER
pin at symbol level. Tests-first, gates-before-code (contract
cognitive-core-phase-5-contract-2026-07-24 §7.3: "an AST pin enforces the same
[league-invisibility] at symbol level"; the byte-untouched COG-3/COG-4 pins are
the siblings this clones).

ROW 8 of the boundary manifest already fences framework.evolution.holdout_gen
repo-wide at MODULE granularity (importable by the oracle CLI + holdout tests
ONLY). This pin is the SYMBOL-level twin over the evolution tree: no sibling
module (league/generator/arena/candidate/scorers/bench_factory) may import the
frozen generator, however spelled — dotted, the alias `from framework.evolution
import holdout_gen`, or a symbol import `from framework.evolution.holdout_gen
import X`. The oracle CLI + holdout tests live OUTSIDE framework/evolution/ and
are naturally clean.

VACUITY — retire when framework/evolution/holdout_gen.py lands (§13 law): the
real-tree arm below is green-by-vacuity while holdout_gen is absent and carries
a COMPANION assertion that the module does NOT exist, so the vacuity cannot
silently persist after it lands (the companion goes RED the moment holdout_gen.py
appears, forcing retirement + real-tree activation). The scratch-tree controls
run NOW and prove the scanner bites (a gate without a biting mutant is
decoration — §12).
RETIREMENT CONDITION: when holdout_gen.py lands (W5), the companion trips RED;
delete it and keep test_real_tree_scans_clean as the live symbol-level pin.

S0: python3.12, no DB, no network. Provenance: authored per the 2026-07-07
full-autonomy grant + the 2026-07-20 cognitive-masterplan continuous grant.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
for _p in (str(_HERE), str(_REPO)):        # tests/ is a package: put it on the path
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib_cog5_ast_pins as L  # noqa: E402


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


class TestHoldoutImporterPin:
    def test_target_absent_and_scanner_green_by_vacuity(self):
        target = _REPO / L.HOLDOUT_GEN_REL
        assert not target.exists(), (
            "holdout_gen.py LANDED — retire this vacuity guard per the RETIREMENT "
            "CONDITION: delete the absence companion, keep the real-tree scan.")
        assert L.holdout_importer_violations(_REPO) == []   # green-by-vacuity

    def test_scratch_sibling_dotted_import_is_red(self, tmp_path):
        _write(tmp_path, "framework/evolution/league.py",
               "import framework.evolution.holdout_gen\n")
        v = L.holdout_importer_violations(tmp_path)
        assert any("framework/evolution/league.py" in x for x in v), v

    def test_scratch_sibling_alias_import_is_red(self, tmp_path):
        _write(tmp_path, "framework/evolution/generator.py",
               "from framework.evolution import holdout_gen\n")
        assert L.holdout_importer_violations(tmp_path), "alias spelling must RED"

    def test_scratch_sibling_symbol_import_is_red(self, tmp_path):
        _write(tmp_path, "framework/evolution/arena.py",
               "from framework.evolution.holdout_gen import Oracle\n")
        assert L.holdout_importer_violations(tmp_path), "symbol import must RED"

    def test_holdout_gen_itself_is_not_scanned(self, tmp_path):
        # the module IS the holdout generator; it is not an "importer" of itself.
        _write(tmp_path, "framework/evolution/holdout_gen.py",
               "import framework.evolution.holdout_gen  # pathological self-ref\n")
        assert L.holdout_importer_violations(tmp_path) == []

    def test_scratch_sibling_without_holdout_folds_clean(self, tmp_path):
        # anti-no-op control: a sibling importing OTHER evolution modules + stdlib
        # is clean, so the scanner is genuinely discriminating (not always-RED).
        _write(tmp_path, "framework/evolution/league.py",
               "import json\nfrom framework.evolution import archive, scorers\n")
        assert L.holdout_importer_violations(tmp_path) == []
