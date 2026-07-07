"""T5 CI guard — the two non-negotiable safety invariants, asserted against
the SHIPPED framework floor (no fixtures, no mutation): exactly the checks the
task names.

  CI #1 [FIX-7]: set(ceiling_frozenset_map.values()) == HARD_CEILING_TOUCHES
                 (all six members, not a self-fulfilling "mappable subset").
  CI #2 [FIX-6]: no row maps a prod/ceiling class to `auto`.

Kept separate from test_matrix.py so a regression here is unambiguously a
safety-floor breach, not a fixture/shape nit. Also proves the legacy policy
loader (framework/authority/policy_engine.py load_policies) ingests the new
authority-matrix.yml without choking — A0 is additive + shadow-only, so the
legacy floor must keep loading.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from framework.authority import matrix as M
from framework.learning.capability_gaps import HARD_CEILING_TOUCHES


def _floor_policy():
    return M.matrix_policy(M.load_matrix())


def test_ci_invariant_1_full_ceiling_coverage():
    """All six HARD_CEILING_TOUCHES members are covered — exactly."""
    pol = _floor_policy()
    assert set(pol["ceiling_frozenset_map"].values()) == set(HARD_CEILING_TOUCHES)
    assert len(set(pol["ceiling_frozenset_map"].values())) == 6


def test_ci_invariant_2_no_prod_or_ceiling_auto():
    """No prod/ceiling row resolves to auto — fail-closed hard ceiling."""
    pol = _floor_policy()
    assert M.no_ceiling_or_prod_auto(pol) is True
    for rc in pol["hard_ceiling"]:
        assert "auto" not in set(pol["verdicts"][rc].values())
    # prod is explicitly in the ceiling and never auto
    assert "deploy_prod" in pol["hard_ceiling"]
    assert "auto" not in set(pol["verdicts"]["deploy_prod"].values())


def test_shipped_floor_self_validates():
    """The shipped floor passes its own validator (load_matrix validates)."""
    data = M.load_matrix()  # raises MatrixValidationError if the floor is bad
    assert M.matrix_policy(data)["type"] == "authority_matrix"


def test_legacy_loader_ingests_authority_matrix_without_breaking():
    """A0 is additive: the legacy policy loader must still load the policy dir
    (now containing authority-matrix.yml) without raising, and surface the
    authority-matrix entry by name."""

    # Force the real yaml if a conftest stub leaked in.
    if "yaml" in sys.modules and not hasattr(sys.modules["yaml"], "safe_load"):
        del sys.modules["yaml"]
        import yaml  # noqa: F401

    from framework.authority import policy_engine

    policies = policy_engine.load_policies(str(_REPO_ROOT))
    names = {p.get("name") for p in policies}
    assert "authority-matrix" in names
    am = next(p for p in policies if p.get("name") == "authority-matrix")
    assert am["type"] == "authority_matrix"
