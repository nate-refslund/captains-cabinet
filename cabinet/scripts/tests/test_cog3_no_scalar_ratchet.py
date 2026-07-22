"""COG-3 STEP 0 — the P12 no-scalar ratchet (contract §6.6 P12 / N3 / SIM-6),
tests-first, gates-before-code + PERMANENT CI.

The standing law the whole phase turns on: the value surface is a vector that can
NEVER collapse to a scalar. This ratchet is the permanent tripwire over
framework/objectives/ (+ its schemas when present), green-by-vacuity today, proven
to bite via scratch mutants — each the exact SIM-6 negative control:

  * a total_value() / score() / __float__ accessor (bare single-number valuation
    or scorecard aggregation-to-one) ⇒ RED
  * an ovi_view emitting composite_score / weights (attack C-M4) ⇒ RED
  * a numeric edge weight (code identifier or a schema property typed number) ⇒ RED

HONEST LIMITATION (attack G-m4, mirrored from EVAL-025 C2 / test_cog2_contradiction):
dynamic construction evades an AST scan — evasion IS the violation; the scan is the
tripwire, not the definition. Pinned in the lib docstring; the later reader-wiring
phase inherits the ratchet and amends it consciously.

S0: python3.12, no DB — pure AST/JSON scans over scratch trees.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
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

import lib_cog3_no_scalar as R  # noqa: E402


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


class TestGreenByVacuity:
    def test_real_tree_has_no_scalar_leakage(self):
        # framework/objectives/ + its schemas do not exist yet — the ratchet folds.
        assert R.ratchet_violations(_REPO) == []


# ===========================================================================
# SCALAR_ACCESSOR — bare single-number valuation / aggregation-to-one
# ===========================================================================

class TestScalarAccessor:
    def test_total_value_accessor_is_red(self, tmp_path):
        # THE SIM-6 mutant.
        _write(tmp_path, "framework/objectives/scorecard.py",
               "class Scorecard:\n"
               "    def total_value(self):\n"
               "        return sum(d.value for d in self.dimensions)\n")
        v = R.ratchet_violations(tmp_path)
        assert any(x.endswith(":total_value") for x in v), v

    @pytest.mark.parametrize("name", [
        "total", "score", "__float__", "composite_score", "aggregate",
        "fitness", "overall", "weighted_sum", "sort_by_fitness",
    ])
    def test_each_forbidden_accessor_name_bites(self, tmp_path, name):
        _write(tmp_path, "framework/objectives/graph.py",
               f"class Graph:\n    def {name}(self):\n        return 1.0\n")
        assert any(x.endswith(f":{name}") for x in
                   R.scalar_accessor_violations(tmp_path)), name

    def test_ordinary_vector_methods_fold_clean(self, tmp_path):
        # anti-over-fencing: the legitimate vector surface (per-dimension access,
        # full-vector return) carries no scalar accessor.
        _write(tmp_path, "framework/objectives/query.py",
               "class View:\n"
               "    def dimensions(self):\n"
               "        return dict(self._dims)\n"
               "    def per_dimension(self, name):\n"
               "        return self._dims.get(name)\n")
        assert R.ratchet_violations(tmp_path) == []


# ===========================================================================
# OVI_COMPOSITE — the per-instrument view refuses composite/weights (C-M4)
# ===========================================================================

class TestOviComposite:
    def test_ovi_view_emitting_composite_score_is_red(self, tmp_path):
        # THE C-M4 mutant: an ovi_view variant emitting composite_score.
        _write(tmp_path, "framework/objectives/ovi_view.py",
               "def project(instruments):\n"
               "    return {'composite_score': sum(instruments.values())}\n")
        v = R.ratchet_violations(tmp_path)
        assert any(x.endswith(":composite_score") and R.RULE_OVI in x for x in v), v

    @pytest.mark.parametrize("ident,body", [
        ("weights", "def project(i):\n    weights = {'a': 0.5}\n    return weights\n"),
        ("composite", "def composite(i):\n    return 1.0\n"),
        ("weight", "def project(i, weight=1.0):\n    return i\n"),
    ])
    def test_ovi_weight_and_composite_idents_bite(self, tmp_path, ident, body):
        _write(tmp_path, "framework/objectives/ovi_view.py", body)
        assert any(x.endswith(f":{ident}") and R.RULE_OVI in x
                   for x in R.ovi_composite_violations(tmp_path)), ident

    def test_ovi_per_instrument_projection_folds_clean(self, tmp_path):
        # the SANCTIONED shape: a per-instrument mapping, no composite, no weights.
        _write(tmp_path, "framework/objectives/ovi_view.py",
               "def project(instruments):\n"
               "    return {name: {'value': v} for name, v in instruments.items()}\n")
        assert R.ovi_composite_violations(tmp_path) == []

    def test_composite_word_in_a_non_ovi_module_is_not_ovi_flagged(self, tmp_path):
        # the OVI rule is scoped to ovi_view.py; the same ident elsewhere is not an
        # OVI violation (it may still trip SCALAR_ACCESSOR if it is a def name).
        _write(tmp_path, "framework/objectives/model.py",
               "COMPOSITE_NOTE = 'the view emits no composite_score'\n")
        assert R.ovi_composite_violations(tmp_path) == []


# ===========================================================================
# NUMERIC_EDGE_WEIGHT — code + schema (contract §4.2 "no numeric weight")
# ===========================================================================

class TestNumericEdgeWeight:
    def test_edge_weight_identifier_in_code_is_red(self, tmp_path):
        _write(tmp_path, "framework/objectives/model.py",
               "def make_edge():\n"
               "    edge_weight = 0.7\n"
               "    return edge_weight\n")
        assert any(x.endswith(":edge_weight") for x in
                   R.numeric_weight_violations(tmp_path))

    def test_numeric_weight_dict_literal_is_red(self, tmp_path):
        _write(tmp_path, "framework/objectives/model.py",
               "EDGE = {'dimension': 'budget', 'weight': 0.5}\n")
        assert any(":weight=" in x for x in R.numeric_weight_violations(tmp_path))

    def test_numeric_weight_schema_property_is_red(self, tmp_path):
        # the §4.2 locus: a schema edge property typed number.
        _write(tmp_path, "framework/schemas/domains/objectives/edge.v1.json",
               '{"type": "object", "properties": {'
               '"dimension": {"type": "string"}, '
               '"weight": {"type": "number"}}}\n')
        v = R.numeric_weight_violations(tmp_path)
        assert any(x.endswith(":schema:weight") for x in v), v

    def test_typed_enum_fields_fold_clean(self, tmp_path):
        # reversibility / captain_attention_cost are TYPED enums (:105), never
        # weights — the sanctioned edge schema carries NO numeric weight.
        _write(tmp_path, "framework/schemas/domains/objectives/edge.v1.json",
               '{"type": "object", "properties": {'
               '"expected_effect": {"enum": ["increase", "decrease", "maintain"]}, '
               '"reversibility": {"enum": ["reversible", "irreversible"]}}}\n')
        assert R.numeric_weight_violations(tmp_path) == []

    def test_string_weight_value_is_not_a_numeric_weight(self, tmp_path):
        # narrowness: a non-numeric "weight" value is not a numeric edge weight.
        _write(tmp_path, "framework/objectives/model.py",
               "E = {'weight': 'increase'}\n")
        assert R.numeric_weight_violations(tmp_path) == []


# ===========================================================================
# combined — a clean objectives tree stays green; the full ratchet aggregates
# ===========================================================================

class TestCombined:
    def test_clean_objectives_tree_is_fully_green(self, tmp_path):
        _write(tmp_path, "framework/objectives/scorecard.py",
               "class Scorecard:\n"
               "    def dimensions(self):\n        return dict(self._d)\n")
        _write(tmp_path, "framework/objectives/ovi_view.py",
               "def project(instruments):\n"
               "    return {n: {'value': v} for n, v in instruments.items()}\n")
        _write(tmp_path, "framework/schemas/domains/objectives/scorecard.v1.json",
               '{"type": "object", "properties": {"state": {"type": "string"}}}\n')
        assert R.ratchet_violations(tmp_path) == []

    def test_full_ratchet_aggregates_every_rule(self, tmp_path):
        _write(tmp_path, "framework/objectives/scorecard.py",
               "class S:\n    def total(self):\n        return 1\n")
        _write(tmp_path, "framework/objectives/ovi_view.py",
               "def f():\n    return {'composite_score': 1}\n")
        _write(tmp_path, "framework/objectives/model.py",
               "W = {'weight': 3}\n")
        rules = {x.split(":")[1] for x in R.ratchet_violations(tmp_path)}
        assert rules == {R.RULE_SCALAR, R.RULE_OVI, R.RULE_WEIGHT}, rules
