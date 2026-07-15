# Release-readiness checkpoint 1

- Branch: `codex/release-readiness-audit`
- Scope: staged observe-only dogfood release (~101 files)
- Reviewer: Claude Fable 5
- Initial review: 2026-07-15, Claude CLI, read-only, high effort
- Follow-up: 2026-07-15, Anthropic API, `claude-fable-5`, adaptive thinking, read-only excerpts

## Initial stop-ship finding

**P2 — observe-only removed the only trigger-ACK path.** The hook blocked the
shell `trigger_ack` path and did not admit a Redis-trigger tool. Since the
channel intentionally does not ACK on delivery, processed triggers would stay
pending, be reclaimed and re-delivered, prevent processed-prefix trimming, and
potentially consume the sole Telegram reply budget during the 72-hour soak.

Initial verdict: `CHECKPOINT VERDICT: FAIL` (one P2; no P0/P1).

## Resolution

- Added the germline `cabinet/scripts/hooks/observe-ack.sh` doorway. It derives
  the stream/group exclusively from validated inherited `OFFICER_NAME` and
  `CABINET_ACTIVE_PROJECT`; callers can supply only 1–50 Redis Stream IDs.
- The observe gate and its safe-doorway early exit admit the same exact,
  anchored command shape. Interpreter prefixes, environment overrides,
  redirects, compound commands, invalid IDs, and arbitrary Redis commands
  remain blocked.
- The Redis trigger channel still never ACKs on delivery. In observe-only it
  exposes the exact receipt ID after the trigger content, with an instruction
  to ACK only after processing.
- Redis errors fail visibly; partial multi-ID progress is reported; a repeated
  receipt is an idempotent `already_clear` success. Conservative trimming
  remains in `triggers.sh`, retaining the oldest pending boundary.
- The post-tool recovery message and observe-only runbook now describe and
  verify this receipt path.

## Verification

- Real disposable Redis regression: delivery became pending, the bounded ACK
  reduced `XPENDING` to zero, and replay returned `already_clear=1`.
- Closed-shape adversarial hook cases passed.
- Targeted observe/channel/trigger tests: 24 passed.
- Full Cabinet Python suite: 761 passed, 3 skipped.
- Germline lockstep: 367 passed.
- Golden evals: 26/26 passed.
- Staged-tree Gitleaks scan: no leaks.

## Follow-up Fable verdict

Fable verified no remaining P0–P2. It specifically confirmed inherited
identity/project binding, identical closed regexes, no delivery-time ACK,
honest Redis failure/idempotency behavior, pending-safe trimming, and runbook
agreement.

Non-blocking P3 residuals recorded by the reviewer:

1. A multi-ID ACK is not atomic; partial progress is honest and retry-safe.
2. `redis-cli` stderr is suppressed, so the failure message lacks root-cause
   detail.
3. A future recovery batch above 50 IDs must be split (the current safety net
   reads at most 50).
4. A well-formed but nonexistent ID reports `already_clear`; it cannot ACK a
   different stream/group.
5. Captain-side use outside a gated process can ACK while the Captain marker is
   active; ACK is deliberately classified as receipt state, not business
   authority.

`CHECKPOINT VERDICT: PASS`
