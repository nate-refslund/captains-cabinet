#!/usr/bin/env python3
"""measure_intent.py — clone vs generic intent-fidelity over scoreable held-out
reply cases. SHARDABLE so the run can be parallelised across processes.

Reuses the leak-safe harness end to end — it does NOT reimplement any fence:
  * build_cases(n) applies the scoreable fairness filter (benchmark.is_scoreable).
  * officer_runner.run_case(...) is the CLONE arm (clone identity + as-of-cutoff
    gather); it RAISES leakguard.LeakageDetectedError if the officer's output
    carries post-cutoff content -> counted as a leak, never scored.
  * oauth_raw_llm(format_situation(c), BASELINE_SYSTEM) is the GENERIC arm.
  * scorer.score(...) runs the OAuth intent judge -> intent_verdict + the
    surface decision_verdict.

Determinism: build_cases(n) is deterministic for a fixed corpus, so every shard
builds the SAME n cases and runs the slice cases[shard::num_shards]; the author
centroid excludes ALL n situation_refs in every shard (consistent, leak-safe).

Identity (D17/INT-3): --identity clone|agent selects which identity the
officer-under-test drafts under (officer_runner.run_case identity_mode).
DEFAULT IS 'clone' until the first AGB baseline is cut — flipping the default
would silently change shard outputs and breach the A/A invariant. The mode is
stamped into EVERY rec so shards are segmentable per identity downstream
(framework.fidelity.intent_report).

Usage:
  python measure_intent.py --n 48 --list-ids                  # determinism check
  python measure_intent.py --n 48 --shard 0 --num-shards 6 --out shard0.jsonl
Emits one JSON line per case:
  {case_id, channel, identity_mode, decision_verdict, intent_verdict,
   outcome_verdict, leaked, error}
where outcome_verdict is the D17 AGB axis (clone vs the held-out real reply,
anonymized A/B, judged only against the reconstructed intent).
"""
import os
import sys
import json
import argparse
from pathlib import Path

# Repo root from THIS file (parents[2] = the tree with framework/), NEVER a
# hardcoded absolute. WHY [lane-supply 2026-07-05, adversarial-review fix]:
# framework/ is a namespace package, so a literal "/Users/nate/captains-cabinet"
# front-loads the MAIN checkout onto framework's namespace __path__ and a run
# from a git worktree then imports main's STALE framework/* instead of the
# worktree's (the same import-order shadowing that failed lane-supply's registry
# tests under a full sweep). parents[2] resolves identically in production (run
# from main), so it is byte-for-byte equivalent there. Matches run_action_lane.py:49.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, os.path.expanduser("~/.screenpipe/pipes/_shared"))
sys.path.insert(0, os.path.expanduser("~/.screenpipe/pipes"))

from framework.fidelity.benchmark import build_cases
from framework.fidelity import officer_runner, scorer, leakguard
from framework.fidelity.officer_runner import gather_cutoff_context
from framework.fidelity.retro import author_centroid, BASELINE_SYSTEM
from framework.fidelity.oauth_llm import oauth_raw_llm
from framework.fidelity.officer_prompt import format_situation


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=48)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--out", default="")
    ap.add_argument("--list-ids", action="store_true",
                    help="print the case_ids build_cases yields (determinism check)")
    ap.add_argument("--dump-dir", default="",
                    help="write rich per-case artifacts (clone/real reply, context, "
                         "verdicts, grounded_fact) here for diagnosis")
    ap.add_argument("--identity", default="clone",
                    choices=list(officer_runner.IDENTITY_MODES),
                    help="identity the officer drafts under (D17): 'clone' "
                         "(default until the first AGB baseline) or 'agent'")
    args = ap.parse_args()

    cases = build_cases(n=args.n)  # scoreable_only=True is the default
    if args.list_ids:
        print(json.dumps([c.case_id for c in cases]))
        return

    cents = author_centroid(exclude_keys={c.situation_ref for c in cases})
    shard = cases[args.shard::args.num_shards]
    out = open(args.out, "w") if args.out else sys.stdout

    for c in shard:
        # identity_mode is stamped on EVERY rec (leak/error rows included) so
        # a shard file is segmentable per identity without ambiguity (D17).
        rec = {"case_id": c.case_id, "channel": getattr(c, "channel", ""),
               "identity_mode": args.identity,
               "leaked": False, "error": None,
               "decision_verdict": None, "intent_verdict": None,
               "outcome_verdict": None, "grounded_fact": None}
        try:
            decision = officer_runner.run_case(
                c, "cos", gather=gather_cutoff_context, emit_events=False,
                identity_mode=args.identity)
        except leakguard.LeakageDetectedError:
            rec["leaked"] = True
            out.write(json.dumps(rec) + "\n"); out.flush(); continue
        except Exception as e:  # noqa: BLE001 — record + continue, never abort the shard
            rec["error"] = repr(e)[:300]
            out.write(json.dumps(rec) + "\n"); out.flush(); continue
        try:
            base = oauth_raw_llm(format_situation(c), BASELINE_SYSTEM) or ""
            ctx = gather_cutoff_context(c)
            cs = scorer.score(
                c, decision, base, cents,
                intent_ctx={"reconstructed_intent": getattr(c, "intent", "") or "",
                            "full_cutoff_context": ctx})
            rec["decision_verdict"] = cs.decision_verdict or ""
            rec["intent_verdict"] = cs.intent_verdict or ""
            rec["outcome_verdict"] = getattr(cs, "outcome_verdict", "") or ""
            rec["grounded_fact"] = getattr(cs, "intent_grounded_fact", "") or ""
            if args.dump_dir:
                os.makedirs(args.dump_dir, exist_ok=True)
                clone_reply = decision.decision if isinstance(
                    decision.decision, str) else str(decision.decision)
                real_reply = (getattr(c, "ground_truth", None) or {}).get("real_reply", "")
                dump = {**rec,
                        "reconstructed_intent": (getattr(c, "intent", "") or "")[:1500],
                        "clone_reply": (clone_reply or "")[:2500],
                        "generic_reply": (base or "")[:1500],
                        "real_reply": (real_reply or "")[:2500],
                        "outcome_grounded_fact":
                            getattr(cs, "outcome_grounded_fact", "") or "",
                        "context_preview": str(ctx)[:3000]}
                with open(os.path.join(args.dump_dir, f"{c.case_id}.json"), "w") as df:
                    json.dump(dump, df, indent=2, default=str)
        except Exception as e:  # noqa: BLE001
            rec["error"] = repr(e)[:300]
        out.write(json.dumps(rec) + "\n"); out.flush()

    if args.out:
        out.close()


if __name__ == "__main__":
    main()
