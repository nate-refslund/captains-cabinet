# Checkpoint review — fix-spend-meter-uncapped, cp1 (meter core)

Reviewer: fresh-context adversarial subagent (Opus 5), 2026-07-26.
Scope: framework/cost/{__init__,meter,record_turn}.py, session-stop.sh cost
section, pre-tool-use.sh `unlimited` sentinel, instance/config/platform.yml.

VERDICT: changes-requested → all MUST-FIX addressed in this branch.

## MUST-FIX (resolved)
1. `_redis()` read rc only; redis-cli emits error replies on stdout with rc=0,
   so a failed HINCRBY advanced the watermark and lost the spend with a green
   log line. Fixed: error-reply prefix table + MULTI/EXEC positive confirmation.
   Follow-on found while verifying: redis-cli in STDIN mode exits 0 with EMPTY
   stdout when the server is unreachable (errors go to stderr) — so the batch
   writer now requires `OK` + one `QUEUED` per command + clean stderr.
2. Truncated/replaced transcript blacked out the meter permanently. Fixed:
   watermark reset when the file is shorter than the mark, repaired even when
   nothing is billable.
3. test_killswitch_fail_closed regressed (uncap skips the enforcement block the
   test exercised). Fixed by pinning the fail-closed read behind an explicit
   numeric cap + a new arm pinning that uncapped does NOT block.
4. cognitive-architecture census budgets exceeded by the new package. Raised to
   the exact measured totals.
5. Config comments asserted watchdog/briefing controls that did not exist —
   grep disproved them. Controls landed in this branch rather than promised.
6. fw-002 golden eval regressed 8→5: its cache-poisoning mechanism has been
   dead since the hook moved to per-call mktemp recompute, so groups 2-4 were
   silently testing live config. Rewritten against a synthetic CABINET_ROOT.

## SHOULD-FIX (resolved)
7 session_id "unknown" collapsed all watermarks · 8 two more copies of the wrong
rate table (advisor-crew.ts live, stop-hook.sh dormant) · 9 unknown-model max by
sum not per-dimension · 10 malformed usage wedged a session permanently ·
12 ~50s worst-case Stop latency from 10 subprocesses → one MULTI/EXEC ·
13 dangling docs/cost-metering.md → written · 14 observe-only-dogfood.md
precondition contradicted the config → updated · 15 zero Redis coverage →
ephemeral-redis suite added · 18 unsanitized last_model could desync HGETALL
line-pair parsers.

## Accepted residuals (documented, not fixed)
- Cross-Stop dedupe: message ids repeating after a Stop boundary re-bill.
  Measured 1 occurrence at gap>9 across 3,124 repeat events. Direction is
  OVER-count, which is the safe direction for a watch.
- Long-context (>200K) premium tiers and batch discounts are not modelled; the
  transcript does not carry service tier reliably. Documented in
  docs/cost-metering.md as a known under-report rather than guessed at.

## Verified clean by the reviewer
Injection (30 hostile inputs vs safe_principal, all argv-list, no shell=True) ·
cannot block an officer (exit 0 + clean stdout across missing python, missing
module, redis down, 89MB transcript, binary garbage) · pricing arithmetic
hand-checked for two models, 0 microdollars rounding drift over 352 responses ·
1h-TTL premise validated at 99.7% of real cache-creation entries · regression
surface (all nine last_* fields, per-turn not cumulative) · layer separation.
