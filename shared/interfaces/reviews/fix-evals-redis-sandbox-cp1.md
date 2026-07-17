# Review artifact — fix/evals-redis-sandbox cp1 (2026-07-17)

Batch: golden-eval redis sandbox (Wave-1 item e, killswitch-clobber fix) —
new `cabinet/scripts/lib/evals-redis-sandbox.sh` + suite gate in
`run-golden-evals.sh` + CI disposable declaration + 6 tests + pre-push
comment corrections. ~340 lines → FW-019 artifact.

## Incident
`run-golden-evals.sh` resolves REDIS_HOST/PORT with a 127.0.0.1:6379
default — the LIVE production Redis on the Mac. EVAL-001 `SET
cabinet:killswitch active`; the cleanup EXIT trap `DEL cabinet:killswitch`
UNCONDITIONALLY. FW-025 (pre-push) runs the suite on every master push, so
each push momentarily armed the fleet emergency stop and then silently
cleared it — including a killswitch the Captain deliberately armed (the
2026-07-15 lockdown read INACTIVE on 07-16 "presumably cleared" with four
eval-running pushes in between; the clobber mechanism stands regardless of
which actor cleared it). Tests must never touch the emergency stop.

## Fix
- Sourceable lib: `evals_redis_sandbox_start` spawns an ephemeral
  localhost redis-server (random high port ≤10 attempts, no persistence,
  private tmp dir, PING-wait, foreign-server identity check via
  `CONFIG GET dir` against the physical tmp path) and exports the full
  endpoint triple (REDIS_HOST/REDIS_PORT preferred by every hook +
  REDIS_URL defensively). `CABINET_EVALS_REDIS_DISPOSABLE=1` (CI's
  throwaway redis:7 service container) skips the spawn. Failure returns
  non-zero WITHOUT exporting.
- Suite: sources the lib immediately after endpoint resolution and REFUSES
  to run (exit 1, actionable message incl. brew/apt hints) if the sandbox
  cannot start; cleanup trap tears the sandbox down last. EVAL-014's two
  hardcoded `-h redis` Docker-DNS DELs redirected to the resolved endpoint
  (silent no-op on Mac/CI, but live layer-1 gate-ACK deletion in any
  Docker-DNS deployment — same tests-touch-live class).
- Binary discovery mirrors fw-002-spending-limits.sh (brew-prefix fallback
  + PATH-prepend; upfront redis-cli check avoids a 50s misleading burn).
- pre-push: `--no-verify` justification + flock rationale updated
  (docs-track-code); CI job comment on hook endpoint resolution corrected
  (hooks PREFER HOST/PORT; URL is fallback).

## Review
Independent adversarial review (fresh-context Fable subagent):
**SHIP-WITH-FIXES** — all findings applied in this commit:
- P1 #1: the stop-kills test asserted nothing (`kill -0 0` always true —
  the B4 tested-nothing class) → PID_SAVED captured, "DEAD" asserted.
- P2 #2: foreign-PONG adoption (spawn dies on bind, PONG from a foreign
  server, triple exported at it) → liveness-before-PONG + CONFIG GET dir
  identity check + empty-physical-path guard.
- P2 #3: EV14 hardcoded DELs → resolved endpoint (above).
- P2 #4: binary discovery (above).
- P2 #5: refusal hint now names brew AND apt. (Adding redis-server to the
  three officer/watchdog Dockerfiles = follow-up, filed.)
- P2 #6a-d: pre-push --no-verify + flock comments, lib/CI mechanism
  wording, lib-tests count comment (191).
- P3 #7: refusal pin re-anchored on a LINE-anchored `fi` (word-containing
  "fi" can no longer truncate the scanned block).
- P3 #8 accepted-risk notes verified by the reviewer (kill -9 orphan is
  localhost-bound/empty/non-persisting and -9-only — EXIT trap cleanup
  proven on both real timeout carriers incl. this Mac's perl/ALRM one).
  Sibling surface test-escalation.sh SETs the killswitch on its resolved
  endpoint → filed as hardening follow-up, out of scope here.

Reviewer-verified clean: gate ordering (refusal fires before ANY redis-cli;
cleanup trap installs after the gate), no eval needs pre-existing live
state (CI's empty container is proven-green input), FW-025 300s budget
holds (spawn ~0.2s), flock story intact, bash 3.2 verified live, zizmor
static-literal only, EVAL-001c closed-port simulation unaffected, item (e)
second half (kill_switch_* events from flip surfaces — kill-switch.sh is
schg germline) honestly untouched and filed.

## Verification (post-fixes)
- shellcheck --severity=error + bash -n: lib, suite, pre-push — PASS.
- cabinet/scripts/lib/tests: 191 passed (incl. the 6 new; 3 of 6 run on
  CI's redis-server-less runner, the canary teeth run where the risk
  lives — Macs).
- FULL suite 26/26 against its self-spawned sandbox, with an armed canary
  killswitch on the stand-in resolved endpoint SURVIVING the entire run
  (pre-fix: cleanup deleted it); real live Redis untouched throughout.
- The FW-025 pre-push hook exercises the new sandbox path live on this
  very push (fail-closed if it can't).
