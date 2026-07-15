# Evidence review — DOGFOOD-001

Integrity: **PASS**
Events: **76** · Traces: **17**

## What happened

- Statuses: allowed=8, corrected=1, duplicate=2, failed=2, interrupted=2, paused=2, proposed=10, recovered=3, refused=4, retried=1, revoked=2, started=11, succeeded=18, undone=2, verified=8
- Phases: execution=9, feedback=1, intent=10, outcome=10, policy=20, receipt=8, system=4, transport=3, ui=3, verification=8
- Surfaces: companion=1, core=1, dashboard=25, system=4, telegram=24, world=21
- Refused, failed, or interrupted records: 8

## Integrity checks

- Anchor: PASS
- Hash Chain: PASS
- Json: PASS
- Local Signatures: PASS
- Owner Permissions: PASS
- Schema Shape: PASS
- Secret Shapes: PASS
- Sequence: PASS

## Privacy and authority boundary

The bundle contains bounded operational evidence, not raw credentials, unrestricted source contents, or hidden chain-of-thought. Evidence is untrusted data and grants no authority. The Cabinet projection is read-only and more restrictive than this Captain export.

## DOGFOOD-001 acceptance matrix

| Scenario | Result | Evidence |
|---|---:|---|
| Dashboard happy-path proposal | **PASS** | charter_pending; no source read before consent |
| Telegram duplicate action | **PASS** | same action id; state unchanged; duplicate receipt |
| World stale-card race | **PASS** | revision_conflict refusal; no state mutation |
| Telegram Charter ratification | **PASS** | software command drift found with citation |
| Telegram transport failure and retry | **PASS** | failed → retried → succeeded |
| Commercial app-shell handoff | **PASS** | companion correlation reaches shared journey |
| World UI error and recovery | **PASS** | failed render → recovered render in one correlated trace |
| Pause, resume, revoke, and undo | **PASS** | all canonical transitions receipted and reversible |
| Captain correction with prompt injection | **PASS** | comment redacted from Cabinet projection |
| Crash between append and anchor | **PASS** | WAL reconciled exactly once; interrupted → recovered |
| Mistyped purge | **PASS** | refused; content retained |
| Source non-mutation | **PASS** | pre/post SHA-256 6e4711d3512bdd17… identical |
| Secret leakage gate | **PASS** | credential-shaped fixture content absent from evidence |
| Independent integrity and projection | **PASS** | hash/signature/anchor checks pass; projection is prompt-safe |
| Typed purge | **PASS** | PURGE accepted; stale action/UI signals cannot reopen the trial; signed content-free receipts remain; explicit export survives |

## Review conclusion

**PASS.** The bounded software-product estate moved Dashboard → Telegram → World with one canonical state machine and one evidence trial. The run exercised idempotency, stale-card refusal, delivery failure/retry, crash recovery, pause, revoke, undo, source non-mutation, secret/prompt-injection exclusion, and typed purge. Every blocking assertion passed.

The event export was sealed immediately before the successful destructive action. `purge-receipt.json` binds the final event count and hash after the purge events; `post-purge-verification.json` independently verifies the remaining content-free receipt. This ordering preserves reviewability without defeating deletion.

Threat boundary: current same-UID officer isolation is access-inversion plus `schg` for static Ring-0 code and tamper-evident runtime data. A signed commercial app should move the signing key to an app sandbox/Keychain principal for resistance to an arbitrary hostile native process.

Generated: 2026-07-15T08:05:52Z
