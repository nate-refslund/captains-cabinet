"""Fidelity consequence-event builders + dual-emit (F0 consumer).

Builds the two F1 consequence-event records — blind case evaluation and
anti-leakage hard-fail — and emits them through BOTH ledgers so graduation
math (consequence ledger) and org-runtime drill-down (org-event ledger) stay
in sync. This is NOT the F0 emitter: it is a thin fidelity-specific BUILDER on
top of it.

- Consequence ledger: framework.fidelity.consequence.emit_consequence
  (validates hand-rolled — NO jsonschema dep — then appends to
  consequence-events-*.jsonl). The graduation read path.
- Org-event ledger: framework.events.emitter.emit with the snake_case event
  type (fidelity_case_evaluated / fidelity_case_leak_detected) and the
  consequence dict as payload. The org-runtime audit trail.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from framework.events.emitter import emit as _emit_org_event
from framework.fidelity.consequence import (
    emit_consequence,
    validate_consequence,
)
from framework.fidelity.types import OfficerDecision


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_event(event: dict[str, Any]) -> None:
    """Validate a fidelity consequence-event dict via F0's hand-rolled
    validator. Raises ConsequenceValidationError on drift (unknown field, bad
    enum, broken invariant)."""
    validate_consequence(event)


def build_case_evaluated(case_id: str, officer: str, lane: str,
                         decision: OfficerDecision, evidence: str) -> dict[str, Any]:
    """Consequence-event for a blind officer decision captured on a held-out
    case. proposal.required=False (eval is below the approval bar);
    outcome.status='ok' with evidence (the decision-chain hash); review
    pending. action is kebab-case on the consequence ledger."""
    return {
        "ts": _now(),
        "actor": {"kind": "officer", "id": officer},
        "lane": lane,
        "action": "fidelity-case-evaluated",
        "subject": case_id,
        "refs": [case_id],
        "proposal": {"required": False},
        "outcome": {"status": "ok", "evidence": evidence},
        "review": {"verdict": "unknown"},
    }


def build_case_leaked(case_id: str, officer: str, lane: str,
                      signals: list[str]) -> dict[str, Any]:
    """Consequence-event for an anti-leakage hard-fail. outcome.status='failed'
    with the leaked signals as evidence; the case is never scored."""
    return {
        "ts": _now(),
        "actor": {"kind": "officer", "id": officer},
        "lane": lane,
        "action": "fidelity-case-leak-detected",
        "subject": case_id,
        "refs": [case_id],
        "proposal": {"required": False},
        "outcome": {"status": "failed", "evidence": "leaked: " + ", ".join(signals)},
        "review": {"verdict": "unknown"},
    }


def _emit_both(consequence_event: dict[str, Any], officer: str,
               org_event_type: str) -> dict[str, Any]:
    """Append to the consequence ledger (validates) + mirror to the org-event
    ledger for drill-down. Returns the consequence dict."""
    emit_consequence(
        ts=consequence_event["ts"],
        actor=consequence_event["actor"],
        lane=consequence_event["lane"],
        action=consequence_event["action"],
        subject=consequence_event["subject"],
        refs=consequence_event["refs"],
        proposal=consequence_event["proposal"],
        outcome=consequence_event["outcome"],
        review=consequence_event["review"],
    )
    _emit_org_event(org_event_type, actor=officer, payload=consequence_event)
    return consequence_event


def emit_case_evaluated(case_id: str, officer: str, lane: str,
                        decision: OfficerDecision, evidence: str) -> dict[str, Any]:
    """Build + dual-emit a fidelity-case-evaluated event."""
    ev = build_case_evaluated(case_id, officer, lane, decision, evidence)
    return _emit_both(ev, officer, "fidelity_case_evaluated")


def emit_case_leaked(case_id: str, officer: str, lane: str,
                     signals: list[str]) -> dict[str, Any]:
    """Build + dual-emit a fidelity-case-leak-detected event."""
    ev = build_case_leaked(case_id, officer, lane, signals)
    return _emit_both(ev, officer, "fidelity_case_leak_detected")
