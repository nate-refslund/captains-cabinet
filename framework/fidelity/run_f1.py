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
              emit_events: bool = True, gather=None, with_intent: bool = False,
              emit_scored: bool = False) -> dict:
    """Drive -> score -> aggregate over the reply cell.

    Three knobs, all default OFF -> the F1 (surface-only) path is byte-for-byte
    unchanged. Captain-authorized 2026-06-20 (D1, docs/overnight-integration-
    drafts.md):
    - ``gather`` (None): pass ``officer_runner.gather_cutoff_context`` for the
      F4 leak-guarded gather arm; threaded into the runner so the officer
      decides WITH as-of-cutoff context.
    - ``with_intent`` (False): thread the reconstructed intent + the fenced
      cutoff context into ``score()`` so the intent axis is measured (a
      decision-only run leaves intent_verdict='').
    - ``emit_scored`` (False): persist a fidelity-case-scored consequence event
      per case (carries the intent fields + maps review.verdict from intent), so
      the graduation bar is actually FED. A pure-scorer/dry run leaves it False;
      a measurement run sets it True."""
    from framework.fidelity.officer_runner import gather_cutoff_context
    from framework.fidelity.fidelity_events import emit_case_scored
    cases = build_cases(n=n_cases, people_dir=people_dir)
    centroids = author_centroid(exclude_keys={c.situation_ref for c in cases})

    scores, n_leaked = [], 0
    for case in cases:
        try:
            decision = runner(case, officer_role, emit_events=emit_events,
                              gather=gather)
        except leakguard.LeakageDetectedError:
            n_leaked += 1  # hard-failed + leak event already emitted in run_case
            continue
        baseline_draft = baseline_llm(_baseline_payload(case), BASELINE_SYSTEM) or ""
        intent_ctx = None
        if with_intent:
            ctx = (gather or gather_cutoff_context)(case)
            intent_ctx = {"reconstructed_intent": getattr(case, "intent", "") or "",
                          "full_cutoff_context": ctx}
        cs = scorer_fn(case, decision, baseline_draft, centroids,
                       intent_ctx=intent_ctx)
        scores.append(cs)
        if emit_scored:
            # action_type stays None for an eval reply case: the reply cell is
            # identified by lane="send-1to1-reply"; decision_type ("reply") is a
            # benchmark label, NOT a classifier.ACTION_TYPES value (the schema
            # enum). Absent action_type = the unmeasured default the cell key
            # tolerates.
            emit_case_scored(cs, officer_role, getattr(case, "lane", None),
                             action_type=None,
                             endorsement=getattr(case, "endorsement", None))

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


def _env_flag(name: str) -> bool:
    """Truthy env knob (W3 label-mine wiring 2026-07-09): '1'/'true'/'yes'/'on'."""
    import os
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    import json
    import sys

    role = sys.argv[1] if len(sys.argv) > 1 else "cos"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    # D1 knobs (Captain-authorized 2026-06-20, run_batch docstring) reachable
    # from the scheduled entry (W3 2026-07-09 — before this they were
    # function-params only, so the cron batch could never feed the bar):
    #   F1_WITH_INTENT=1  -> measure the intent axis (threads fenced cutoff
    #                        context into score()).
    #   F1_EMIT_SCORED=1  -> persist fidelity-case-scored consequence events
    #                        (labels for calibration input; graduation bar FED).
    #   F1_GATHER=1       -> F4 leak-guarded gather arm for the officer drive.
    # All default OFF -> bare invocation stays byte-for-byte the old F1 path.
    with_intent = _env_flag("F1_WITH_INTENT")
    emit_scored = _env_flag("F1_EMIT_SCORED")
    gather = None
    if _env_flag("F1_GATHER"):
        from framework.fidelity.officer_runner import gather_cutoff_context
        gather = gather_cutoff_context
    result = run_batch(officer_role=role, n_cases=n, gather=gather,
                       with_intent=with_intent, emit_scored=emit_scored)
    print(json.dumps({k: v for k, v in result.items() if k != "scores"}, indent=2))
    assert_beats_baseline(result)
    print(f"OK - clone beats baseline: "
          f"{result['decision_match_rate']} > {result['baseline']} "
          f"(n_scored={result['n_scored']}, n_leaked={result['n_leaked']})")
