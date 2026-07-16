# Checkpoint review — exact enabled-fleet deployment

- Branch: `codex/exact-enabled-fleet`
- Reviewed base: `0baad32047ea8707bbee2c2d0a7f1d46a1bfd4fc`
- Reviewer: Claude Fable 5, independent adversarial review
- Scope: deployment reconciliation, plist generation, Cabinet Doctor fleet checks, tests, and deployment documentation

## First review

Verdict: request changes.

Confirmed findings:

1. The kiosk behavior and Cabinet Doctor documentation contradicted one another.
2. The active runbook still depended on the legacy `verify-launchagents.sh` gate.
3. Generated-plist pruning could reach beyond the canonical generated-output directory when a custom output path was supplied.

## Fixes applied

- Aligned the kiosk and Doctor contract in code, tests, and the active runbook.
- Replaced the stale runbook gates with the exact enabled-fleet deployment and Doctor checks.
- Restricted pruning to the canonical generated-plist directory and refused `~/Library/LaunchAgents` as generator output.
- Added bounded unload polling, shared roster semantics on all paths, safe label validation, explicit dry-run output, and tests for both pruning-scope cases.

## Re-review

Verdict: **APPROVE**.

The reviewer confirmed that all three blockers were resolved and found no remaining P0-P2 defect. Non-blocking P3 notes were retained for later follow-up: the four-second unload bound may need tuning from live evidence; the retired verification script still has a stale slash-command reference outside the active runbook; and one Doctor exact-set test is source-pinned rather than behavioral.

## Verification at approval

- 46 targeted tests passed.
- Mac deployment dry-run passed.
- Bash syntax, Python compilation, and diff checks passed.
- An earlier full scripts run passed 850 tests with 3 skips; its only failures were the three independently fixed egress test-isolation defects in PR #147.

The live repository and runtime were not modified by this patch or its review.
