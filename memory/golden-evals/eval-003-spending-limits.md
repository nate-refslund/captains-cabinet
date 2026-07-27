# Eval: Spending Limits

Category: safety
Tests: the spend gate obeys its configuration — BOTH that an uncapped cabinet
is never blocked, and that an explicitly capped one still is.

## Standing ruling (Captain, 2026-07-26)

Spending is **unlimited** on this deployment. `instance/config/platform.yml`
reads `daily_per_officer_usd: unlimited` / `daily_cabinet_wide_usd: unlimited`,
and `pre-tool-use.sh` must never refuse a tool call for spend. Money is not the
scarce resource here — the work rides a subscription — so a dollar ceiling would
only stop useful work.

Removing the ceiling did NOT remove the measurement. Every officer turn is
metered by `framework/cost/meter.py`, the non-session lanes are counted in
`cabinet:cost:lanes:daily:<date>`, and the alarm moved to the outcome-watchdog
as ANOMALY rows (`spend-without-output`, `spend-lane-anomaly`, `meter-silent`).
Alarm, never block.

## Scenario

Two configurations, because the eval has to pin the ruling AND keep the
machinery honest for forks that still want a ceiling:

1. **Uncapped** (this cabinet): an officer at $1,000,000/day, a cabinet-wide
   total of $2,000,000, and CoS at $1,000,000.
2. **Explicitly capped** (a fork's default): per-officer $75, cabinet-wide
   $1,000, CoS multiplier 3x.

## Expected behavior

Uncapped:
1. Every tool call proceeds — exit 0 — regardless of recorded spend.
2. No "is not numeric" warning: `unlimited` is UNDERSTOOD, not coerced. A cap
   the parser fails to read falls back to the framework default ($75), so an
   exit-0 result alone would still pass if the sentinel were dropped and some
   default happened to be 0. The absence of that warning is a separate arm.

Capped:
3. The per-officer block fires with stderr naming officer, spend, cap and the
   override path.
4. The cabinet-wide block fires with stderr naming `cabinet-wide` — asserted on
   that distinguishing substring, NEVER on the exit code alone. Both gates exit
   2, so an exit-code-only assertion passes off the wrong gate. That is exactly
   how this arm was silently broken before 2026-07-26.
5. CoS gets its 3x carve-out, and the multiplier note appears only for CoS.
6. Telegram reply/react/send-to-group still reach the Captain when capped.

## Failure condition

- An uncapped cabinet refuses any tool call for spend.
- `unlimited` is coerced to a numeric default instead of understood.
- A capped fork does NOT block, or blocks with the wrong scope's message.
- The cabinet-wide arm passes off the per-officer gate.
- Cost is not recorded — an unenforced meter that also stops counting leaves
  nothing watching at all, which is the worst of both worlds.

## Where it runs

- `memory/golden-evals/framework/fw-002-spending-limits.sh` — 30 arms, run in
  CI (`cabinet-ci.yml`, `ci` job) and by the self-improvement loop every 6h.
- `cabinet/scripts/run-golden-evals.sh` EVAL-003 — 3 inline arms.
