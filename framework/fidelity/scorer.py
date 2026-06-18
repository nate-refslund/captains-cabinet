"""Endorsement-aware scorer (docs/fidelity-harness-design-2026-06-18.md §127-141).

Wraps retrodiction's three-channel score_case: STYLE (Voyage cosine vs the
recency-weighted voice centroid - text decisions only), DECISION-MATCH (the
tone-blind judge, run here via OAuth `claude -p` keeping JUDGE_SYSTEM intact),
MECHANICS (deterministic flags). F1 covers the reply cell with endorsement
'unknown' => scored vs the actual reply; F4 wires the endorsed-direction
adjustment. The privacy fence holds: nate_model/voice inform the centroid +
clone draft but are never emitted into a score row."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from framework.fidelity import retro
from framework.fidelity.oauth_llm import oauth_json_llm
from framework.fidelity.types import Case, OfficerDecision

_COMPOSITE = {"match": 1.0, "partial": 0.5, "divergent": 0.0, "error": 0.0,
              "skipped": 0.0}


@dataclass
class CaseScore:
    case_id: str
    style_win: bool
    decision_verdict: str
    mechanics_flags: list[str]
    endorsement_adjusted: bool
    composite: float
    raw: dict[str, Any] = field(default_factory=dict)


def judge_with_oauth(case_dict: dict, clone_draft: str) -> dict:
    """Run retrodiction's decision judge via OAuth `claude -p`, keeping
    JUDGE_SYSTEM (decision-only) intact. Returns the verdict dict."""
    return retro.judge_decision(case_dict, clone_draft, llm=oauth_json_llm)


def score(case: Case, officer_decision: OfficerDecision, baseline_draft: str,
          centroids: dict, embedder=None, judge=None) -> CaseScore:
    """Score one officer decision vs ground truth across the three channels."""
    judge = judge or judge_with_oauth
    clone_draft = officer_decision.decision if isinstance(
        officer_decision.decision, str) else str(officer_decision.decision)
    rc = case.to_retro_case()

    # DECISION via OAuth judge; inject as judge_result so score_case does no
    # ANTHROPIC_API_KEY call.
    verdict = judge(rc, clone_draft)
    row = retro.score_case(rc, clone_draft, baseline_draft, centroids,
                           judge=False, embedder=embedder, judge_result=verdict)

    decision_verdict = row["judge"]["verdict"]
    # F1: endorsement 'unknown' -> score vs actual, no adjustment.
    endorsement_adjusted = case.endorsement in ("regretted", "constrained")
    return CaseScore(
        case_id=case.case_id,
        style_win=bool(row["style_win"]),
        decision_verdict=decision_verdict,
        mechanics_flags=row["mechanics"],
        endorsement_adjusted=endorsement_adjusted,
        composite=_COMPOSITE.get(decision_verdict, 0.0),
        raw=row,
    )
