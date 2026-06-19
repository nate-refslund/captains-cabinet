# T5 — Live end-to-end smoke result (fidelity harness)

Real reversible run of `framework/fidelity/run_e2e_smoke.py` on **n=1** held-out
reply case, with the **live** seams: OAuth `claude -p` officer + judge, real
`gather`, real Voyage STYLE scoring. Reversible: reads + scores + LOCAL JSONL
ledger writes only — NO queue_draft, NO send, NO board write, NO deploy, NO
pay-as-you-go spend (ANTHROPIC_API_KEY stripped; Max OAuth pool).

## How it was run

```
CABINET_EVENT_LOG_DIR=<isolated tmp dir> \
PYTHONPATH="$HOME/.screenpipe/pipes/_shared:$HOME/.screenpipe/pipes:$PWD" \
python3 -m framework.fidelity.run_e2e_smoke cos 1
```

Run from the repo root via `-m` (NOT as a bare file path from inside
`framework/fidelity/`, which would let the cwd shadow stdlib `types`). The
isolated ledger dir was removed afterward — nothing durable was written.

## Result (2026-06-19, live)

```json
{
  "n_scored": 1,
  "n_leaked": 0,
  "decision_match_rate": 0.0,
  "beats_baseline": false,
  "baseline": 0.083,
  "graduation_states": {
    "officer:cos|send-1to1-reply|internal_message": "unmeasured"
  },
  "ts": "2026-06-19T20:11:09.980058+00:00"
}
```

## What this proves (the FLOW, live — scores expected low)

- **Pipeline completes** — one real held-out case driven blind through the
  OAuth officer, judged, Voyage-scored. `n_scored=1`.
- **CaseScore per case** — `decision_verdict="divergent"`. A low score is fine;
  the point is the live wiring, not the number (single uncached blind case).
- **Consequence events emitted** — both rows landed in the local ledger:
  - `fidelity-case-evaluated` (from `run_case`, blind-decision capture)
  - `fidelity-case-scored` (the T3 path, carrying the scorer axis):
    ```json
    {"action":"fidelity-case-scored","subject":"c68343a785",
     "action_type":"internal_message","decision_verdict":"divergent",
     "intent_verdict":"","intent_composite":0.0,"endorsement":"unknown",
     "outcome":{"status":"ok","evidence":"intent=n/a composite=0.0"},
     "review":{"verdict":"unknown"}}
    ```
  - Both also mirrored to the org-event ledger (`fidelity_case_evaluated`,
    `fidelity_case_scored`) for drill-down.
- **Graduation reads them** — `state="unmeasured"`, the fail-safe verdict on one
  thin sample. Never silently `eligible`/`graduated`.
- **NO leak** — `n_leaked=0`; leaked cases (none here) would have been counted
  and EXCLUDED, never silently scored.

## Known seam (not a T5 bug — surfaced for the morning)

`run_batch` (the F1 batch the smoke reuses) calls `scorer.score()` WITHOUT
`intent_ctx`, so the live scored row carries `intent_verdict=""`
(decision-only / F1 path). Consequence: the scored cell's
`review_confirmed_rate` stays `unknown` → graduation stays `unmeasured`. To make
intent (and therefore `review_confirmed_rate`) measurable on the live batch,
`run_batch` would need to thread `intent_ctx` (the reconstructed intent +
fenced cutoff context) into `score()` the way the stubbed T4 seam test does.
That is an F4-wiring change to `run_f1.run_batch` (a sibling module), NOT a
germline file — proposed diff appended to
`docs/overnight-integration-drafts.md` for morning authorization. The T5 smoke
itself is complete and correct: it proves the chain runs live and reversibly.
