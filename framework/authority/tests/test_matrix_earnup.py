"""AX-1 — the `postures.earn_up` table + the earn_up-only-narrows validator
(axes spec 2026-07-05 §1).

The frozen static table: EVERY non-ceiling class propose_only at ALL five
confidence states; six ceilings {"*": always_gated}. All autonomy above that
floor comes from the trust-ladder overlay at run time (AX-2), never from the
table. Validator invariants under test:

  * earn_up may only NARROW vs the root/guardian table — machine-checked
    cell-by-cell on VERDICT_PERMISSIVENESS (always_gated < propose_only <
    classifier < auto_with_veto_window < {act_with_undo, notify_after} <
    auto); equality is legal, any widening raises.
  * `standing_grant` is forbidden anywhere in earn_up (unranked on purpose).
  * demote stays posture-invariant vs the root (generic posture pass).
  * FIX-6 (`no_ceiling_or_prod_auto`) sweeps the earn_up table too.
  * The root/guardian and sovereign tables are byte-untouched by the earn_up
    addition, and a floor without an earn_up entry still validates.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority import matrix as M

_NON_CEILING_ROWS = (
    "reversible", "read_only_dispatch", "draft_only", "pm_write",
    "calendar_write", "internal_comms", "deploy_nonprod",
)
_CEILING_ROWS = (
    "external_comms", "deploy_prod", "spend",
    "secrets", "network_write", "credentials_grant",
)
_STATES = ("unmeasured", "propose_only", "eligible", "graduated", "demote")

# The EXACT frozen earn_up table (uniform by design — the comprehension IS
# the spec sentence: every non-ceiling class propose_only at all five states,
# six ceilings always_gated).
_EXPECTED_EARN_UP = {
    rc: {state: "propose_only" for state in _STATES} for rc in _NON_CEILING_ROWS
}
_EXPECTED_EARN_UP.update({rc: {"*": "always_gated"} for rc in _CEILING_ROWS})


@pytest.fixture()
def loaded():
    """The shipped framework floor, loaded + validated."""
    return M.load_matrix()


def _pol(data):
    return M.matrix_policy(data)


def _mutant(loaded):
    return copy.deepcopy(loaded)


def _earn(d):
    return _pol(d)["postures"]["earn_up"]["verdicts"]


# ---------------------------------------------------------------------------
# 1. The shipped floor carries the exact frozen earn_up table
# ---------------------------------------------------------------------------

class TestShippedEarnUpTable:
    def test_earn_up_table_is_exactly_the_frozen_static_table(self, loaded):
        assert _earn(loaded) == _EXPECTED_EARN_UP

    def test_earn_up_is_in_the_postures_vocab(self):
        assert "earn_up" in M.POSTURES
        assert "guardian" not in M.POSTURES

    def test_earn_up_entry_carries_only_verdicts(self, loaded):
        assert set(_pol(loaded)["postures"]["earn_up"]) == {"verdicts"}

    def test_earn_up_never_contains_standing_grant_or_acting_verdicts(self, loaded):
        acting = {"auto", "act_with_undo", "auto_with_veto_window",
                  "notify_after", "classifier", "standing_grant"}
        for rc, states in _earn(loaded).items():
            assert not (set(states.values()) & acting), rc

    def test_permissiveness_ordering_is_the_frozen_ruler(self):
        r = M.VERDICT_PERMISSIVENESS
        assert r["always_gated"] < r["propose_only"] < r["classifier"] \
            < r["auto_with_veto_window"] < r["act_with_undo"] < r["auto"]
        assert r["act_with_undo"] == r["notify_after"]
        assert "standing_grant" not in r  # ceiling-row-only, never orderable
        assert set(r) == set(M.VERDICTS) - {"standing_grant"}


# ---------------------------------------------------------------------------
# 2. The narrows-validator fails closed on every widening
# ---------------------------------------------------------------------------

class TestEarnUpNarrowsRejections:
    @pytest.mark.parametrize("rc,state,verdict", [
        # wider than the root cell's rank in each case
        ("reversible", "graduated", "auto"),             # root act_with_undo(4) < auto(5)
        ("read_only_dispatch", "eligible", "auto"),      # root notify_after(4) < auto(5)
        ("internal_comms", "graduated", "auto"),         # root auto_with_veto_window(3) < auto(5)
        ("internal_comms", "unmeasured", "classifier"),  # root propose_only(1) < classifier(2)
        ("deploy_nonprod", "unmeasured", "classifier"),  # root propose_only(1) < classifier(2)
        ("draft_only", "eligible", "auto"),              # root notify_after(4) < auto(5)
    ])
    def test_widening_a_cell_beyond_root_raises(self, loaded, rc, state, verdict):
        d = _mutant(loaded)
        _earn(d)[rc][state] = verdict
        with pytest.raises(M.MatrixValidationError, match="only narrow"):
            M.validate_matrix(d)

    def test_equal_to_root_cell_is_legal(self, loaded):
        # Narrow-OR-EQUAL: earn_up mirroring a root row verbatim validates
        # (demote invariance also holds by construction).
        d = _mutant(loaded)
        _earn(d)["reversible"] = copy.deepcopy(_pol(d)["verdicts"]["reversible"])
        M.validate_matrix(d)  # must NOT raise

    def test_equal_rank_to_root_cell_is_legal(self, loaded):
        # act_with_undo and notify_after share a rank — swapping the oversight
        # handle is not a widening.
        d = _mutant(loaded)
        _earn(d)["pm_write"] = copy.deepcopy(_pol(d)["verdicts"]["pm_write"])
        _earn(d)["pm_write"]["unmeasured"] = "notify_after"
        M.validate_matrix(d)  # must NOT raise

    def test_narrower_than_shipped_stays_legal(self, loaded):
        d = _mutant(loaded)
        _earn(d)["internal_comms"]["graduated"] = "always_gated"
        M.validate_matrix(d)  # must NOT raise — narrowing is always legal

    def test_standing_grant_on_earn_up_ceiling_row_raises(self, loaded):
        d = _mutant(loaded)
        _earn(d)["external_comms"] = {"*": "standing_grant"}
        with pytest.raises(M.MatrixValidationError, match="forbidden in earn_up"):
            M.validate_matrix(d)

    def test_standing_grant_on_earn_up_non_ceiling_cell_raises(self, loaded):
        # Already illegal via the generic posture-table rule; the earn_up
        # doctrine holds either way.
        d = _mutant(loaded)
        _earn(d)["reversible"]["graduated"] = "standing_grant"
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_auto_in_earn_up_ceiling_row_raises(self, loaded):
        d = _mutant(loaded)
        _earn(d)["spend"] = {"*": "auto"}
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)

    def test_demote_drift_in_earn_up_raises(self, loaded):
        # always_gated@demote would be NARROWER — demote is still pinned by
        # posture-INVARIANCE (evidence beats posture, root demote exactly).
        d = _mutant(loaded)
        _earn(d)["reversible"]["demote"] = "always_gated"
        with pytest.raises(M.MatrixValidationError, match="posture-invariant"):
            M.validate_matrix(d)

    def test_missing_risk_class_row_raises(self, loaded):
        d = _mutant(loaded)
        del _earn(d)["calendar_write"]
        with pytest.raises(M.MatrixValidationError):
            M.validate_matrix(d)


# ---------------------------------------------------------------------------
# 3. CI sweeps + additivity
# ---------------------------------------------------------------------------

class TestEarnUpSweepsAndAdditivity:
    def test_no_ceiling_or_prod_auto_sweeps_earn_up(self, loaded):
        assert M.no_ceiling_or_prod_auto(_pol(loaded)) is True
        d = _mutant(loaded)
        _earn(d)["deploy_prod"] = {"*": "auto"}
        assert M.no_ceiling_or_prod_auto(_pol(d)) is False

    def test_root_and_sovereign_tables_untouched_by_earn_up(self, loaded):
        # The earn_up addition is ADDITIVE: byte-comparing the OTHER tables
        # against a floor with earn_up stripped must be an identity.
        d = _mutant(loaded)
        del _pol(d)["postures"]["earn_up"]
        assert _pol(d)["verdicts"] == _pol(loaded)["verdicts"]
        assert (_pol(d)["postures"]["sovereign"]
                == _pol(loaded)["postures"]["sovereign"])

    def test_floor_without_earn_up_entry_still_validates(self, loaded):
        d = _mutant(loaded)
        del _pol(d)["postures"]["earn_up"]
        M.validate_matrix(d)  # earn_up is optional — sovereign-only floors OK

    def test_floor_with_only_earn_up_entry_validates(self, loaded):
        d = _mutant(loaded)
        del _pol(d)["postures"]["sovereign"]
        M.validate_matrix(d)

    def test_validate_postures_standalone_checks_earn_up(self, loaded):
        # The D8 runtime-gate call path reaches the narrows rule too.
        pol = copy.deepcopy(_pol(loaded))
        pol["postures"]["earn_up"]["verdicts"]["reversible"]["graduated"] = "auto"
        with pytest.raises(M.MatrixValidationError, match="only narrow"):
            M._validate_postures(pol)
