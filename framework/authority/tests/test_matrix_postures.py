"""SOV-2 — the posture axis on the authority matrix: the §2.1
`postures.sovereign` table (sovereign build spec 2026-07-04) + the
posture-aware fail-closed validator.

Guardian IS the root `verdicts` table (pinned literally below — the posture
axis must leave it byte-untouched). `postures.*` adds FULL per-posture verdict
tables (sovereign only in v1). Validator invariants under test:

  * `postures.guardian` is rejected — guardian is never redefined [D1].
  * `standing_grant` is forbidden in the root/guardian table and on any
    non-ceiling posture row; posture ceiling rows are single-'*' wildcard in
    {always_gated, standing_grant} — `auto` structurally impossible [D2].
  * demote is posture-invariant vs the root table for every non-ceiling
    risk class [§2.1].
  * FIX-6 (`no_ceiling_or_prod_auto`) sweeps EVERY posture table; FIX-7
    ceiling coverage is untouched by the posture axis.
  * A postures-less matrix still validates and the legacy policy loader still
    ingests the floor (back-compat — guardian stays bit-identical with no
    posture config).
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

# Repo root on sys.path so the framework package imports cleanly (same
# convention as the sibling authority tests).
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority import matrix as M
from framework.learning.capability_gaps import HARD_CEILING_TOUCHES

_HARD_CEILING_ROWS = {
    "external_comms",
    "deploy_prod",
    "spend",
    "secrets",
    "network_write",
    "credentials_grant",
}

# The root/guardian table as ratified BEFORE the posture axis landed — the
# posture change must leave it semantically identical (byte-parity of the file
# region is SOV-9's golden suite; this pin catches any verdict-level drift).
_EXPECTED_GUARDIAN = {
    "reversible": {
        "graduated": "auto", "eligible": "propose_only",
        "propose_only": "propose_only", "unmeasured": "propose_only",
        "demote": "propose_only",
    },
    "pm_write": {
        "graduated": "act_with_undo", "eligible": "act_with_undo",
        "propose_only": "act_with_undo", "unmeasured": "act_with_undo",
        "demote": "propose_only",
    },
    "calendar_write": {
        "graduated": "act_with_undo", "eligible": "act_with_undo",
        "propose_only": "act_with_undo", "unmeasured": "act_with_undo",
        "demote": "propose_only",
    },
    "internal_comms": {
        "graduated": "auto_with_veto_window", "eligible": "propose_only",
        "propose_only": "propose_only", "unmeasured": "propose_only",
        "demote": "propose_only",
    },
    "deploy_nonprod": {
        "graduated": "classifier", "eligible": "classifier",
        "propose_only": "propose_only", "unmeasured": "propose_only",
        "demote": "propose_only",
    },
    "external_comms": {"*": "always_gated"},
    "deploy_prod": {"*": "always_gated"},
    "spend": {"*": "always_gated"},
    "secrets": {"*": "always_gated"},
    "network_write": {"*": "always_gated"},
    "credentials_grant": {"*": "always_gated"},
}

# The EXACT §2.1 sovereign table the floor must ship.
_EXPECTED_SOVEREIGN = {
    "reversible": {
        "graduated": "auto", "eligible": "auto", "propose_only": "auto",
        "unmeasured": "auto", "demote": "propose_only",
    },
    "pm_write": {
        "graduated": "act_with_undo", "eligible": "act_with_undo",
        "propose_only": "act_with_undo", "unmeasured": "act_with_undo",
        "demote": "propose_only",
    },
    "calendar_write": {
        "graduated": "act_with_undo", "eligible": "act_with_undo",
        "propose_only": "act_with_undo", "unmeasured": "act_with_undo",
        "demote": "propose_only",
    },
    "internal_comms": {
        "graduated": "notify_after", "eligible": "notify_after",
        "propose_only": "notify_after", "unmeasured": "notify_after",
        "demote": "propose_only",
    },
    "deploy_nonprod": {
        "graduated": "notify_after", "eligible": "notify_after",
        "propose_only": "notify_after", "unmeasured": "notify_after",
        "demote": "propose_only",
    },
    "external_comms": {"*": "standing_grant"},
    "deploy_prod": {"*": "standing_grant"},
    "spend": {"*": "standing_grant"},
    "secrets": {"*": "standing_grant"},
    "network_write": {"*": "standing_grant"},
    "credentials_grant": {"*": "standing_grant"},
}


@pytest.fixture()
def loaded():
    """The shipped framework floor matrix, loaded + validated."""
    return M.load_matrix()


def _pol(data):
    return M.matrix_policy(data)


def _mutant(loaded):
    return copy.deepcopy(loaded)


# ---------------------------------------------------------------------------
# 1. The shipped floor self-validates and carries the exact §2.1 tables
# ---------------------------------------------------------------------------

class TestShippedFloorPostures:
    def test_floor_self_validates_with_postures(self, loaded):
        # load_matrix() validates — reaching here means the posture-bearing
        # floor passed the full fail-closed validator.
        assert "postures" in _pol(loaded)

    def test_postures_key_is_sovereign_only(self, loaded):
        assert set(_pol(loaded)["postures"]) == {"sovereign"}
        assert set(_pol(loaded)["postures"]) <= M.POSTURES

    def test_sovereign_table_is_exactly_spec_2_1(self, loaded):
        assert _pol(loaded)["postures"]["sovereign"]["verdicts"] == _EXPECTED_SOVEREIGN

    def test_root_guardian_table_untouched(self, loaded):
        # The posture axis is ADDITIVE: the root verdicts table must equal the
        # pre-change guardian table exactly.
        assert _pol(loaded)["verdicts"] == _EXPECTED_GUARDIAN

    def test_root_table_never_contains_standing_grant(self, loaded):
        for rc, states in _pol(loaded)["verdicts"].items():
            assert "standing_grant" not in set(states.values()), rc

    def test_posture_entry_carries_only_verdicts(self, loaded):
        assert set(_pol(loaded)["postures"]["sovereign"]) == {"verdicts"}

    def test_standing_grant_is_in_the_verdict_enum(self):
        assert "standing_grant" in M.VERDICTS

    def test_postures_vocab_is_sovereign_only(self):
        assert M.POSTURES == frozenset({"sovereign"})
        assert "guardian" not in M.POSTURES


# ---------------------------------------------------------------------------
# 2. Rejection cases — the validator fails closed on every widening/drift
# ---------------------------------------------------------------------------

class TestPostureRejections:
    def test_postures_guardian_key_raises(self, loaded):
        d = _mutant(loaded)
        _pol(d)["postures"]["guardian"] = {
            "verdicts": copy.deepcopy(_EXPECTED_GUARDIAN)
        }
        with pytest.raises(M.MatrixValidationError, match="guardian"):
            M.validate_matrix(d)

    def test_unknown_posture_key_raises(self, loaded):
        d = _mutant(loaded)
        _pol(d)["postures"]["yolo"] = {
            "verdicts": copy.deepcopy(_EXPECTED_SOVEREIGN)
        }
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_standing_grant_in_root_ceiling_row_raises(self, loaded):
        d = _mutant(loaded)
        _pol(d)["verdicts"]["spend"] = {"*": "standing_grant"}
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_standing_grant_in_root_non_ceiling_cell_raises(self, loaded):
        d = _mutant(loaded)
        _pol(d)["verdicts"]["reversible"]["graduated"] = "standing_grant"
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_standing_grant_on_non_ceiling_posture_row_raises(self, loaded):
        d = _mutant(loaded)
        sov = _pol(d)["postures"]["sovereign"]["verdicts"]
        sov["internal_comms"]["graduated"] = "standing_grant"
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_auto_in_posture_ceiling_row_raises(self, loaded):
        d = _mutant(loaded)
        _pol(d)["postures"]["sovereign"]["verdicts"]["spend"] = {"*": "auto"}
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_auto_in_posture_prod_row_raises(self, loaded):
        d = _mutant(loaded)
        sov = _pol(d)["postures"]["sovereign"]["verdicts"]
        sov["deploy_prod"] = {"*": "auto"}
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_act_with_undo_in_posture_ceiling_row_raises(self, loaded):
        d = _mutant(loaded)
        sov = _pol(d)["postures"]["sovereign"]["verdicts"]
        sov["external_comms"] = {"*": "act_with_undo"}
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_posture_ceiling_row_non_wildcard_raises(self, loaded):
        d = _mutant(loaded)
        sov = _pol(d)["postures"]["sovereign"]["verdicts"]
        sov["spend"] = {
            "graduated": "standing_grant", "eligible": "standing_grant",
            "propose_only": "standing_grant", "unmeasured": "standing_grant",
            "demote": "standing_grant",
        }
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_demote_drift_raises(self, loaded):
        # A posture may never soften the demote floor [§2.1].
        d = _mutant(loaded)
        sov = _pol(d)["postures"]["sovereign"]["verdicts"]
        sov["reversible"]["demote"] = "auto"
        with pytest.raises(M.MatrixValidationError, match="posture-invariant"):
            M.validate_matrix(d)

    def test_demote_drift_even_to_a_valid_verdict_raises(self, loaded):
        d = _mutant(loaded)
        sov = _pol(d)["postures"]["sovereign"]["verdicts"]
        sov["internal_comms"]["demote"] = "notify_after"
        with pytest.raises(M.MatrixValidationError, match="posture-invariant"):
            M.validate_matrix(d)

    def test_missing_confidence_state_raises(self, loaded):
        d = _mutant(loaded)
        del _pol(d)["postures"]["sovereign"]["verdicts"]["reversible"]["demote"]
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_unknown_confidence_state_raises(self, loaded):
        d = _mutant(loaded)
        sov = _pol(d)["postures"]["sovereign"]["verdicts"]
        sov["reversible"]["sometimes"] = "auto"
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_missing_risk_class_row_raises(self, loaded):
        # Posture tables are FULL tables — no partial overlays [D1].
        d = _mutant(loaded)
        del _pol(d)["postures"]["sovereign"]["verdicts"]["pm_write"]
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_unknown_verdict_in_posture_table_raises(self, loaded):
        d = _mutant(loaded)
        sov = _pol(d)["postures"]["sovereign"]["verdicts"]
        sov["reversible"]["graduated"] = "yolo"
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_extra_posture_entry_key_raises(self, loaded):
        d = _mutant(loaded)
        _pol(d)["postures"]["sovereign"]["surprise"] = 1
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_posture_entry_missing_verdicts_raises(self, loaded):
        d = _mutant(loaded)
        _pol(d)["postures"]["sovereign"] = {}
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_posture_entry_not_mapping_raises(self, loaded):
        d = _mutant(loaded)
        _pol(d)["postures"]["sovereign"] = ["not", "a", "mapping"]
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_postures_not_mapping_raises(self, loaded):
        d = _mutant(loaded)
        _pol(d)["postures"] = ["sovereign"]
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_postures_empty_mapping_raises(self, loaded):
        d = _mutant(loaded)
        _pol(d)["postures"] = {}
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)


# ---------------------------------------------------------------------------
# 3. Narrowing stays legal — a posture ceiling row may keep always_gated
# ---------------------------------------------------------------------------

class TestPostureNarrowingAllowed:
    def test_posture_ceiling_always_gated_allowed(self, loaded):
        d = _mutant(loaded)
        sov = _pol(d)["postures"]["sovereign"]["verdicts"]
        sov["external_comms"] = {"*": "always_gated"}
        M.validate_matrix(d)  # must NOT raise — narrowing is always legal

    def test_posture_non_ceiling_may_narrow_to_propose_only(self, loaded):
        d = _mutant(loaded)
        sov = _pol(d)["postures"]["sovereign"]["verdicts"]
        sov["internal_comms"] = {
            "graduated": "propose_only", "eligible": "propose_only",
            "propose_only": "propose_only", "unmeasured": "propose_only",
            "demote": "propose_only",
        }
        M.validate_matrix(d)  # must NOT raise


# ---------------------------------------------------------------------------
# 4. FIX-6 / FIX-7 swept per posture
# ---------------------------------------------------------------------------

class TestCiInvariantsPerPosture:
    def test_no_ceiling_or_prod_auto_true_on_shipped_floor(self, loaded):
        assert M.no_ceiling_or_prod_auto(_pol(loaded)) is True

    def test_no_ceiling_or_prod_auto_sweeps_posture_tables(self, loaded):
        # FIX-6 must catch an auto smuggled into a POSTURE ceiling row, not
        # just the root table.
        d = _mutant(loaded)
        _pol(d)["postures"]["sovereign"]["verdicts"]["spend"] = {"*": "auto"}
        assert M.no_ceiling_or_prod_auto(_pol(d)) is False

    def test_no_ceiling_or_prod_auto_sweeps_posture_prod_row(self, loaded):
        d = _mutant(loaded)
        sov = _pol(d)["postures"]["sovereign"]["verdicts"]
        sov["deploy_prod"] = {"*": "auto"}
        assert M.no_ceiling_or_prod_auto(_pol(d)) is False

    def test_every_posture_ceiling_row_is_gated_or_grant(self, loaded):
        # Behavioral FIX-6 sweep of the SHIPPED floor: ceilings never resolve
        # unconditional auto in ANY posture.
        pol = _pol(loaded)
        for name, entry in pol["postures"].items():
            for rc in pol["hard_ceiling"]:
                states = entry["verdicts"][rc]
                assert set(states) == {"*"}, (name, rc)
                assert states["*"] in {"always_gated", "standing_grant"}, (name, rc)
                assert states["*"] != "auto", (name, rc)

    def test_fix7_ceiling_coverage_untouched_by_posture_axis(self, loaded):
        # FIX-7 is posture-independent: the ONE ceiling map still covers all
        # six HARD_CEILING_TOUCHES members exactly.
        pol = _pol(loaded)
        assert set(pol["ceiling_frozenset_map"].values()) == set(HARD_CEILING_TOUCHES)
        assert set(pol["hard_ceiling"]) == _HARD_CEILING_ROWS


# ---------------------------------------------------------------------------
# 5. _validate_postures standalone (the D8 runtime-gate call path)
# ---------------------------------------------------------------------------

class TestValidatePosturesStandalone:
    def test_standalone_pass_on_shipped_policy(self, loaded):
        assert M._validate_postures(_pol(loaded)) is None

    def test_absent_postures_is_a_noop(self):
        # No postures key ⇒ nothing to validate ⇒ legacy shape untouched.
        assert M._validate_postures({"verdicts": {}}) is None
        assert M._validate_postures({}) is None

    def test_standalone_rejects_malformed_root_shapes(self, loaded):
        # Fail-closed when called on a merged policy whose root shapes are
        # broken while postures is present.
        sov = copy.deepcopy(_pol(loaded)["postures"])
        with pytest.raises(M.MatrixValidationError):
            M._validate_postures({"postures": sov})

    def test_standalone_rejects_guardian_key(self, loaded):
        pol = copy.deepcopy(_pol(loaded))
        pol["postures"]["guardian"] = {"verdicts": copy.deepcopy(_EXPECTED_GUARDIAN)}
        with pytest.raises(M.MatrixValidationError, match="guardian"):
            M._validate_postures(pol)


# ---------------------------------------------------------------------------
# 6. Back-compat — postures-less floors and the legacy loader
# ---------------------------------------------------------------------------

class TestBackCompat:
    def test_matrix_without_postures_still_validates(self, loaded):
        # Legacy guardian-only shape (the pre-posture floor) must stay valid.
        d = _mutant(loaded)
        del _pol(d)["postures"]
        M.validate_matrix(d)  # must NOT raise

    def test_legacy_loader_ingests_floor_with_postures(self):
        """The legacy policy loader (cabinet/scripts/lib/policy_engine.py)
        must keep loading the posture-bearing floor and surface the postures
        key intact — the posture axis is additive."""
        lib_dir = _REPO_ROOT / "cabinet" / "scripts" / "lib"
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        # Force the real yaml if a conftest stub leaked in.
        if "yaml" in sys.modules and not hasattr(sys.modules["yaml"], "safe_load"):
            del sys.modules["yaml"]
            import yaml  # noqa: F401

        import policy_engine

        policies = policy_engine.load_policies(str(_REPO_ROOT))
        am = next(p for p in policies if p.get("name") == "authority-matrix")
        assert am["type"] == "authority_matrix"
        assert set(am["postures"]) == {"sovereign"}
        assert am["postures"]["sovereign"]["verdicts"] == _EXPECTED_SOVEREIGN
