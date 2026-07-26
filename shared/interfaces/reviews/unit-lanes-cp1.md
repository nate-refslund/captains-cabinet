# Checkpoint review — branch `unit-lanes` cp1 (2026-07-26)

Scope: make every paid API call that bypasses the Claude Code Stop hook land in
`cabinet:cost:lanes:daily:<UTC-date>`; fix the 5x rate table still live in
`advisor-crew.ts`; kill the dead rate table in `stop-hook.sh`.

786 changed lines across 14 files + 2 new files.

## What was built

| Piece | Why it is shaped this way |
|---|---|
| `framework/cost/record_lane.py` (new) | ONE parser for the Anthropic usage block / Voyage usage / `claude -p` cost envelope, consumed by python callers as an import and by shell + TypeScript as a CLI. Six callers each growing their own `jq` expression is exactly how the 5x cache error got duplicated into two hooks and a TS file. Exits 0 on every path, prints nothing on stdout. |
| `cabinet/scripts/lib/cost-lane.sh` (new) | One line of metering per shell call site. `cost_lane_record` always returns 0 and swallows stdout+stderr, so it is safe inside a command substitution whose stdout is the caller's return value. |
| 12 instrumented call sites | Recorded AFTER the paid call returns and BEFORE any early return, so a call that errors still shows as a call. |
| `advisor-crew.ts` rate table | Cache prices DERIVED from the input rate by multiplier; unknown model → most expensive known rate. |
| `advisor-crew.ts` executor persistence | `executorCostMicro` was computed and thrown away on every call. |
| `stop-hook.sh` rate table | Deleted, not corrected — see below. |
| `run-golden-evals.sh` EVAL-008 | Re-pointed from the dead twin to the live Stop path. |

## Findings raised during the build

1. **`library.sh:539` must NOT be instrumented.** It calls
   `memory_get_embedding`, which is where the Voyage request is actually made
   and where the `embeddings` lane is now recorded. A second `record_lane` on
   that line would have doubled the lane for every library search. Instrumented
   once, at the money; a comment on the call site says so.

2. **EVAL-008 was a sensor pointed at a dead artifact.** It drove
   `stop-hook.sh` — wired to no hook event — and asserted that file's
   arithmetic, while the live path (`session-stop.sh` →
   `framework.cost.record_turn`) was unguarded. Both the 5x cache mispricing
   and the one-response-per-turn bug shipped past a green suite because of it.
   Re-pointed at the live hook with the fixture and every expected value
   unchanged. Verified live: reintroducing the exact shipped bug
   (`MULT_CACHE_WRITE_5M = 0.25`) turns EVAL-008 red (38500 vs 40500); it was
   green against that same bug before.

3. **The re-point needed a watermark delete.** The live meter bills a session
   once. Without `DEL cabinet:cost:wm:eval-session` the eval passes on a clean
   box and bills NOTHING on every rerun — a green eval measuring an empty
   write. Added to the pre-clean, the inline cleanup and the EXIT trap; proven
   by running the suite twice (30/30 both times).

4. **Six `test_oauth_llm.py` fakes were under-specified.** They patch
   `subprocess.run` on the shared module, so they captured whichever subprocess
   ran LAST — which became the meter's `redis-cli`. Guarded with
   `_is_claude(argv)` so each assertion points at the CLI invocation it names.
   Guard liveness checked: breaking cwd isolation and HOME still turns three of
   them red.

5. **The advisor lane shells out rather than writing Redis inline.** The field
   shape stays defined once, in `meter.record_lane`, which also carries the
   positive-confirmation check for the trap where `redis-cli` in stdin mode
   exits 0 with empty stdout on a connection failure. `execFileSync` (no shell)
   because that argv carries an interpreter name and a path from the
   environment. `safePrincipal()` added because the officer name reaches a
   Redis field name and a command line and arrives from argv/env.

6. **`stop-hook.sh` rates deleted, not corrected.** Correcting them would put a
   second, live-looking rate table next to a "do not copy" marker — the exact
   duplication being undone. `COST_MICRO=0` is left in the unreachable block
   because a visibly wrong zero beats a plausible number, which is how a 16x
   error hides for months.

## Known-open (carried, not hidden)

- **`test_retrieval_eval_gate.py::test_fingerprint_matches_live_ranking_block`
  is RED.** The `rerank` lane meter sits inside `memory.sh`'s RANKING-BLOCK
  fingerprint scope, and there is no placement outside it that can observe
  whether a paid rerank happened. Needs a store-local
  `retrieval-eval-nightly.sh --stamp` (both arms passing) — not runnable
  without a live Neon store and a Voyage key. The fixture hex was NOT
  hand-edited.
- **Two touched files are germline (schg):**
  `framework/acting/run_action_lane.py`, `framework/frontdoor/actfirst_canary.py`.
  Built in a clone per the landed-then-ceremonied rule; landing them needs one
  Captain unlock/relock window on the live box.
- **Silent metering failure has no watchdog.** If Redis is down for a week
  every lane records nothing and nothing says so. `record_lane` returns the
  boolean; no consumer watches it.

## Verification run

`bash -n` + `shellcheck -S error` on 9 shell files · `py_compile` on 3.12 and on
system 3.9 (the interpreter the shell wrapper actually invokes) · end-to-end
lane writes for `embeddings`/`rerank`/`stt`/`tts`/`api_direct`/`subscription`/`advisor`
against a scratch Redis on port 6401 · redis-DOWN diff of stdout+exit codes
against the pre-change tree (identical) · `framework/` 6551 passed /
1 pre-existing failure · `cabinet/scripts/tests` 4663 passed / 7 failed, 6 of
them pre-existing at the base commit · golden evals 30/30 · hook regression
17/17 · captain-rules evals 5/5 and 29/29 · layer separation clean · docs sweep
green.
