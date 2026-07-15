"""Fail-closed self-diagnosis and repair policy for evidence consumers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RepairRequest:
    """Facts proved about a proposed Cabinet repair.

    Evidence can motivate a proposal; it can never supply authority.  These
    fields must be established outside untrusted log content by the authority
    gate and an independent verifier.
    """

    internal_change: bool
    reversible: bool
    explicit_grant: bool
    regression_tests: bool
    rollback_plan: bool
    independent_verification: bool
    external_effect: bool = False
    irreversible: bool = False
    security_sensitive: bool = False
    authority_changing: bool = False
    audit_changing: bool = False
    governance_changing: bool = False


def repair_verdict(request: RepairRequest) -> dict[str, object]:
    """Return ``auto_repair`` only when every narrow safety predicate holds."""
    hard_gates = {
        "external_effect": request.external_effect,
        "irreversible": request.irreversible,
        "security_sensitive": request.security_sensitive,
        "authority_changing": request.authority_changing,
        "audit_changing": request.audit_changing,
        "governance_changing": request.governance_changing,
    }
    triggered = sorted(key for key, active in hard_gates.items() if active)
    if triggered:
        return {
            "verdict": "captain_gated",
            "reason": "hard_ceiling",
            "gates": triggered,
        }
    requirements = {
        "internal_change": request.internal_change,
        "reversible": request.reversible,
        "explicit_grant": request.explicit_grant,
        "regression_tests": request.regression_tests,
        "rollback_plan": request.rollback_plan,
        "independent_verification": request.independent_verification,
    }
    missing = sorted(key for key, present in requirements.items() if not present)
    if missing:
        return {
            "verdict": "captain_gated",
            "reason": "missing_precondition",
            "missing": missing,
        }
    return {
        "verdict": "auto_repair",
        "reason": "narrow_reversible_internal_grant",
        "required_receipts": ["regression", "rollback", "independent_verification"],
    }
