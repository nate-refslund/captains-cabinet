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


# [T3] Map the F4 scorer's INTENT verdict to a consequence review.verdict so an
# intent-based review_confirmed_rate (the channel the graduation bar reads)
# becomes available. intent-aligned -> confirmed (the action served the
# reconstructed mission × core), intent-divergent -> wrong (lesson material),
# everything else (intent-partial / error / "" / unknown) -> unknown (excluded
# from the bar's denominator, never silently scored). This is the seam that
# unblocks audit finding #1: scored cases were emitting review.verdict='unknown'
# forever, so the cell could never leave the `unmeasured` state.
_INTENT_TO_REVIEW = {
    "intent-aligned": "confirmed",
    "intent-divergent": "wrong",
    "intent-partial": "unknown",
    "error": "unknown",
    "": "unknown",
}


def _review_verdict_for_intent(intent_verdict: str) -> str:
    return _INTENT_TO_REVIEW.get(intent_verdict or "", "unknown")


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


def build_case_scored(case_score: Any, officer: str, lane: str,
                      action_type: str | None = None,
                      endorsement: str | None = None) -> dict[str, Any]:
    """[T3] Consequence-event for a SCORED F4 case — the emit the scoring path
    produces AFTER scorer.score() returns a CaseScore.

    Unblocks audit finding #1: the F1 evaluated-event (build_case_evaluated)
    fired BEFORE scoring, so it could only ever carry review.verdict='unknown'
    and no intent axis — graduation (which reads ONLY the consequence ledger)
    was structurally blind to intent and the cell stayed `unmeasured` forever.
    This builder carries the CaseScore's intent fields onto the event AND maps
    review.verdict from the intent verdict, so an intent-based
    review_confirmed_rate (the bar's channel) becomes measurable.

    Same (actor, action, subject) identity is NOT used to supersede the
    evaluated event — this is a DISTINCT action ('fidelity-case-scored' vs
    'fidelity-case-evaluated'), so both rows coexist: the evaluated row records
    the blind decision, the scored row records the reviewed consequence.

    `endorsement` falls back to the CaseScore's adjustment state when the caller
    does not pass an explicit label, so the event always carries a present,
    non-empty endorsement string (never an empty value the validator rejects).
    """
    intent_verdict = getattr(case_score, "intent_verdict", "") or ""
    decision_verdict = getattr(case_score, "decision_verdict", "") or ""
    intent_composite = getattr(case_score, "intent_composite", 0.0)
    grounded_fact = getattr(case_score, "intent_grounded_fact", "") or ""
    if endorsement is None:
        # Derive a present label from the scorer's adjustment flag — the exact
        # endorsement vocabulary is still being wired (design F4); 'unknown' is
        # the default F1 label and 'constrained' marks an adjusted case.
        endorsement = ("constrained"
                       if getattr(case_score, "endorsement_adjusted", False)
                       else "unknown")
    review_verdict = _review_verdict_for_intent(intent_verdict)
    evidence = (f"intent={intent_verdict or 'n/a'} "
                f"composite={intent_composite}"
                + (f" ground={grounded_fact}" if grounded_fact else ""))
    event: dict[str, Any] = {
        "ts": _now(),
        "actor": {"kind": "officer", "id": officer},
        "lane": lane,
        "action": "fidelity-case-scored",
        "subject": case_score.case_id,
        "refs": [case_score.case_id],
        "proposal": {"required": False},
        "outcome": {"status": "ok", "evidence": evidence},
        # source=verdict_judge (flavor-A split 2026-07-03): a harness-scored
        # case is a MACHINE judgment against historical ground truth — it makes
        # fidelity measurable and its `wrong` can hold/demote, but it can never
        # fuel promotion. Promotion fuel is verdict_human only (live Captain
        # replies via loop.outcome_event). This supersedes the Jun-18 intent of
        # feeding the bar's confirmed channel from scored cases.
        "review": {"verdict": review_verdict, "source": "verdict_judge"},
        "decision_verdict": decision_verdict,
        "intent_verdict": intent_verdict,
        "intent_composite": intent_composite,
        "endorsement": endorsement,
    }
    if action_type is not None:
        event["action_type"] = action_type
    return event


def _emit_both(consequence_event: dict[str, Any], officer: str,
               org_event_type: str) -> dict[str, Any]:
    """Append to the consequence ledger (validates) + mirror to the org-event
    ledger for drill-down. Returns the consequence dict.

    [T3] The optional F4 scorer-axis fields (action_type / decision_verdict /
    intent_verdict / intent_composite / endorsement) are forwarded only when
    the consequence dict carries them, using the _UNSET-vs-omit semantics of
    emit_consequence (a real falsy value is written; an absent key is dropped)."""
    extra: dict[str, Any] = {}
    for k in ("action_type", "decision_verdict", "intent_verdict",
              "intent_composite", "endorsement"):
        if k in consequence_event:
            extra[k] = consequence_event[k]
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
        **extra,
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


def emit_case_scored(case_score: Any, officer: str, lane: str,
                     action_type: str | None = None,
                     endorsement: str | None = None) -> dict[str, Any]:
    """[T3] Build + dual-emit a fidelity-case-scored event carrying the F4
    intent axis and an intent-mapped review.verdict — the seam that makes
    review_confirmed_rate measurable for scored cells."""
    ev = build_case_scored(case_score, officer, lane,
                           action_type=action_type, endorsement=endorsement)
    return _emit_both(ev, officer, "fidelity_case_scored")
