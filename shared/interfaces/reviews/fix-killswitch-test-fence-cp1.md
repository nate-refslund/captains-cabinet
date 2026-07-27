# Checkpoint review — fix/killswitch-test-fence — cp1

Reviewed-Scope-Digest: 668880bbc626e85c4cb7fb445a2d74b5bb8709cb22142fd60a07d3b8378af20e

## What this changes and why

Three test files could flip the Captain's real emergency stop. Not
hypothetically — reproduced, three times, against disposable servers.

`_ks_endpoint` in `cabinet/scripts/hooks/killswitch-read.sh` PREFERS
`REDIS_HOST`/`REDIS_PORT` and only falls back to `REDIS_URL`.
`_ks_marker_path` resolves the filesystem stop marker from
`CABINET_ESTOP_MARKER` else `CABINET_ROOT`/instance/config/estop, and
`kill-switch.sh deactivate` does `rm -f` on whatever that resolves to. Every
officer plist under `cabinet/launchd/` exports `REDIS_HOST`, `REDIS_PORT` and
`CABINET_ROOT` — the officer runtime's normal environment.

All three test files built their child env with `dict(os.environ)`, so those
ambient variables survived and WON:

| file | redis channel | marker channel | reproduced |
|---|---|---|---|
| `test_killswitch_watchdog.py` | unfenced (REDIS_URL only) | unfenced | armed a foreign plane |
| `test_kill_switch_events.py` | unfenced (REDIS_URL only) | unfenced | armed a foreign plane |
| `test_killswitch_telegram_card.py` | fenced | **unfenced** | deleted an armed marker |

The third is the instructive one: it pinned `REDIS_HOST`/`REDIS_PORT` with a
comment saying "keep every reader on the sandbox", and was still exposed on the
channel it did not think about. A partial fence reads as covered.

Each file failed its own assertions immediately afterwards. That is not
mitigation — the red says nothing about what the test already did, and the write
destroys attribution even when the value is restored.

## Reproduction (never touched 6379)

Two disposable servers: A named by `REDIS_URL`, B named by
`REDIS_HOST`/`REDIS_PORT`. Running the REAL unmodified
`test_killswitch_watchdog.py` with B exported: B's `cabinet:killswitch` went
`[]` -> `[active]` while the test asserted against its own sandbox and failed.
6379 verified byte-identical before and after (DBSIZE 48, `cabinet:killswitch`
absent, `KEYS *` sha256 `2602208975552ca3...` unchanged).

## The fix

`cabinet/scripts/tests/lib_killswitch_fence.py`:

- **Derived, not listed.** `derive_channels()` extracts the routing variables
  from the consumer itself — the whole of `killswitch-read.sh` (single-purpose:
  every variable in it selects a server, key or marker path) plus the watchdog's
  own `redis_endpoint`. It distinguishes INPUTS (read-with-default, or
  referenced-but-never-assigned) from the resolver's OUTPUTS (`KS_VERDICT`,
  `KS_REASON`). A hand-maintained list is the drift that caused this:
  `test_killswitch_fail_closed.py` already fenced all five channels correctly
  and documented why, and the knowledge still did not reach its siblings.
- **Fail-closed on drift.** `sandbox_env()` refuses if the resolver has grown a
  channel it cannot sandbox, rather than silently under-fencing.
- **Proven, not assumed.** `assert_isolated()` does not re-implement the
  resolution rules. It sources the REAL resolver in the exact child env and asks
  where it would go, so any channel that resolver honours — today or later — is
  covered by construction. Anything it cannot prove is a refusal, with a message
  naming the endpoint that would have been reached.

## Non-vacuity

Both guards go RED against the pre-fix tree (worktree at `91faed1b`, caches
purged, both directions):

- structural arm — names the three unfenced files;
- behavioral arm — canary redis came back holding `cabinet:killswitch=active`.
- The marker assertion is masked by the redis one when all three are pre-fix, so
  it was isolated separately (redis-channel files fixed, telegram card left
  pre-fix): fires with "A TEST DELETED AN ARMED E-STOP MARKER outside its
  sandbox".

The behavioral guard deliberately POISONS the environment. On a clean env — every
CI runner — none of these variables exist, the resolver falls through to
`REDIS_URL`, and all three pre-fix files PASS. The hole is invisible exactly
where it is tested and open exactly where it is not, so a guard inheriting the
runner's clean env would be vacuous.

## Scope boundary (stated, not implied)

The structural guard covers the WRITE set: tests passing `activate`/`deactivate`
to the emergency stop. `status` is a pure read and is not fenced.
`test_killswitch_fail_closed.py` and `framework/learning/tests/test_gate.py` are
status-only by measurement, and the former already pins all five channels inline;
both are additionally covered by effect in the behavioral arm's nested run.

No production code changed — this is test isolation only. Census unaffected
(every metric still at its ceiling).

## A defect the review caught in the fix itself

The first draft of `sandbox_env()` exposed a `key=` parameter. That is a
footgun: `KILLSWITCH_KEY` steers only the READ (`killswitch-read.sh:142`), while
`kill-switch.sh` hardcodes `cabinet:killswitch` on BOTH write paths (`:96`
`SET`, `:118` `DEL`). A caller pointing it at a sandbox key would have `activate`
arm the LIVE switch and then read back a different, empty key — printing
"ACTIVATION FAILED" having already done the damage. The parameter is removed and
the value pinned to the writer's literal, with an arm asserting the knob cannot
come back.

## Siblings found and NOT closed here (open work, not covered by this PR)

A separate mechanical sweep of every safety switch in the repo. Reported rather
than fixed — each needs its own change and its own non-vacuity proof, and this
PR is already at the review threshold. Ranked by severity:

1. **`cabinet/scripts/tests/test_tamper_drill.py:323,335`** — the sharpest. It
   calls `ef.freeze(_REPO_ROOT, ...)` and then `finally: _thaw(_REPO_ROOT)`,
   writing an immutable evidence judging-freeze marker into the REAL checkout.
   `freeze()` is first-freeze-wins, so if a genuine Captain freeze is armed the
   test's assertion fails and the `finally` **still deletes the real freeze** —
   bypassing the token-gated unfreeze the marker names as the only way out. A
   killed process leaves the marker armed with `uchg`. `marker_path()` has NO env
   override, so the fix is a tmp root, not a fence.
2. **`cabinet/scripts/test-escalation.sh:74,136`** (`--live` only) — `SET`/`DEL
   cabinet:killswitch` resolved from `REDIS_URL`, while its own reader sources
   `killswitch-read.sh`, which prefers `REDIS_HOST`/`REDIS_PORT`. Writer and
   reader can address different servers: the drill can pass while writing
   nowhere, or write live while asserting against live.
3. **`cabinet/tests/hook-regression/fw042-v37-adversary.sh:28`** — unconditional
   `DEL cabinet:killswitch` hardcoded at `-h redis -p 6379`. A no-op where the
   `redis` hostname does not resolve (the Mac fleet), a live clear anywhere it
   does. The `fw041/043/044/045/051` family has the same shape against the CTO
   review-gate keys (fail-closed direction, lower severity).
4. **`CABINET_EVALS_REDIS_DISPOSABLE=1`** (`evals-redis-sandbox.sh:41-42`)
   disables the golden-eval sandbox and lets `run-golden-evals.sh:154,175`
   `SET`/`DEL` the live key at the resolved endpoint. Correct in CI, but it is an
   env-var escape hatch on a live-switch write path with no assertion that the
   endpoint really is disposable.

Verified clean by the same sweep: `test_observe_only.py`, the `captain-vetoes`
tests, the act-first kind-freeze tests, `test_apoptosis.py`, the dashboard
`*.test.ts` suite, and `cabinet/scripts/lib/tests/test_evals_redis_sandbox.py`.
Also noted: the root `conftest.py` fences 12 durable dirs but NOT `REDIS_*`,
`KILLSWITCH_KEY` or `CABINET_ESTOP_MARKER`, and there is no conftest under
`cabinet/scripts/tests/` — which is why this had to be a per-test fence.
