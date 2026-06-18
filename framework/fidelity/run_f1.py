"""F1 end-to-end batch over the reply cell
(docs/fidelity-harness-design-2026-06-18.md §266-268).

Build held-out reply cases -> blind-drive the officer (leak-guarded, no side
effects) -> draft a generic-assistant baseline -> score (OAuth judge, Voyage
STYLE) -> aggregate the decision-match rate -> assert the clone beats the 0.083
generic-assistant baseline. Leaked cases are counted and EXCLUDED (never
silently scored). One fidelity-case-evaluated consequence event is emitted per
scored case (inside run_case via fidelity_events)."""

from __future__ import annotations

from framework.fidelity import leakguard
from framework.fidelity.benchmark import build_cases
from framework.fidelity.officer_prompt import format_situation
from framework.fidelity.officer_runner import run_case
from framework.fidelity.oauth_llm import oauth_raw_llm
from framework.fidelity.retro import BASELINE_SYSTEM, author_centroid
from framework.fidelity.scorer import score

BASELINE_MATCH_RATE = 0.083  # retrodiction generic-assistant baseline


def _rate(rows: list, verdict: str) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.decision_verdict == verdict) / len(rows)


def _baseline_payload(case) -> str:
    """The generic-assistant baseline sees the same situation text (no voice /
    no intel) - that contrast is what makes the scores meaningful."""
    return format_situation(case)


def run_batch(officer_role: str = "cos", n_cases: int = 24, people_dir=None,
              runner=run_case, scorer_fn=score, baseline_llm=oauth_raw_llm,
              emit_events: bool = True) -> dict:
    """Drive -> score -> aggregate over the reply cell."""
    cases = build_cases(n=n_cases, people_dir=people_dir)
    centroids = author_centroid(exclude_keys={c.situation_ref for c in cases})

    scores, n_leaked = [], 0
    for case in cases:
        try:
            decision = runner(case, officer_role, emit_events=emit_events)
        except leakguard.LeakageDetectedError:
            n_leaked += 1  # hard-failed + leak event already emitted in run_case
            continue
        baseline_draft = baseline_llm(_baseline_payload(case), BASELINE_SYSTEM) or ""
        cs = scorer_fn(case, decision, baseline_draft, centroids)
        scores.append(cs)

    mechanics_fail = (sum(1 for s in scores if s.mechanics_flags) / len(scores)
                      if scores else 0.0)
    style_win = (sum(1 for s in scores if s.style_win) / len(scores)
                 if scores else 0.0)
    match_rate = _rate(scores, "match")
    return {
        "n_scored": len(scores),
        "n_leaked": n_leaked,
        "decision_match_rate": round(match_rate, 4),
        "partial_rate": round(_rate(scores, "partial"), 4),
        "divergent_rate": round(_rate(scores, "divergent"), 4),
        "style_win_rate": round(style_win, 4),
        "mechanics_fail_rate": round(mechanics_fail, 4),
        "beats_baseline": match_rate > BASELINE_MATCH_RATE,
        "baseline": BASELINE_MATCH_RATE,
        "scores": [s.__dict__ for s in scores],
    }


def assert_beats_baseline(result: dict) -> None:
    """Bootstrap-validation gate: fail if the clone does not beat the
    generic-assistant baseline."""
    rate = result["decision_match_rate"]
    assert rate > BASELINE_MATCH_RATE, (
        f"clone decision_match_rate {rate} <= baseline {BASELINE_MATCH_RATE}")


if __name__ == "__main__":
    import json
    import sys

    role = sys.argv[1] if len(sys.argv) > 1 else "cos"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    result = run_batch(officer_role=role, n_cases=n)
    print(json.dumps({k: v for k, v in result.items() if k != "scores"}, indent=2))
    assert_beats_baseline(result)
    print(f"OK - clone beats baseline: "
          f"{result['decision_match_rate']} > {result['baseline']} "
          f"(n_scored={result['n_scored']}, n_leaked={result['n_leaked']})")
