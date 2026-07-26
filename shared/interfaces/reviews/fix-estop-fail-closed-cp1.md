# Checkpoint review — fix/estop-fail-closed (cp1, integrator landing)

Branch `fix/estop-fail-closed` @ `1cbeb14d`, merged onto `origin/master`
`c7ca750d`. Reviewer/integrator: Opus 5 (1M). Date 2026-07-26.

## What the branch fixes

The Captain's emergency stop read any non-`active` answer as CLEAR. Measured
against redis 8.8, `redis-cli GET` prints the **error text on stdout and exits
0** for NOAUTH, NOPERM, WRONGTYPE and LOADING — so one allowed command silently
disabled the stop **while every status surface printed INACTIVE**. Absence of
the literal string `active` is the absence of evidence, not evidence of a clear
switch.

The fix inverts the default (unverifiable = STOPPED) and proves the read with a
nonce sandwich — `ECHO n1` / `GET key` / `ECHO n2` on one round trip — which a
silent, shimmed or erroring client cannot forge, since only a live authenticated
server can echo two fresh nonces around the value. 12 readers now share one
helper, `cabinet/scripts/hooks/killswitch-read.sh` (exit 0 CLEAR / 10 ACTIVE /
11 INDETERMINATE, so a missing or crashed helper is fail-closed by
construction).

## Integrator's own 7-state reproduction (private redis, one port per state)

Run by me, not inherited from the builder. `OLD` is the pre-change contract
lifted byte-faithfully from `git show 05871f12:cabinet/scripts/hooks/pre-tool-use.sh`
lines 258-271; `NEW` is `killswitch-read.sh`; `officer` drives the real
`pre-tool-use.sh` end-to-end (exit 2 = officer's Bash refused). The real cabinet
Redis on 6379 was never touched — verified `PONG` after teardown.

A first attempt leaked (a `requirepass` server survived SHUTDOWN and three later
states silently re-measured NOAUTH). Rebuilt with a fresh port per state plus a
raw-wire assertion that each state actually materialised; only the second run is
evidence.

| # | state | wire | OLD | NEW | officer |
|---|---|---|---|---|---|
| 1 | healthy, key absent | `` (empty) | ALLOW | **ALLOW** | ALLOW |
| 2 | armed | `active` | HALT | **HALT** | REFUSED(2) |
| 3 | NOAUTH | `NOAUTH Authentication required.` | **ALLOW** | **HALT** | REFUSED(2) |
| 4 | NOPERM | `NOPERM User default has no permissions...` | **ALLOW** | **HALT** | REFUSED(2) |
| 5 | WRONGTYPE | `WRONGTYPE Operation against a key...` | **ALLOW** | **HALT** | REFUSED(2) |
| 6 | LOADING | `LOADING Redis is loading the dataset...` | **ALLOW** | **HALT** | REFUSED(2) |
| 7 | connection refused | `Could not connect to Redis...` | HALT | **HALT** | REFUSED(2) |

**4 of 7 states defeated the old reader** (3-6, exactly the exit-0-with-error
class). All four now halt. State 1 — the no-false-positive arm that stops this
bricking the cabinet — still ALLOWs end-to-end through the real hook. State 6
replays the measured LOADING wire behaviour via a stub, as the shipped battery
does; a live AOF replay window is not deterministically reproducible.

## The only corpus change I made

26 tests failed because they stubbed `redis-cli` with a binary that **exits 0
and prints nothing** — they encoded the exact broken contract the fix removes.
None asserts anything *about* the killswitch, and every one of the 26 failed on
the ALLOW side; the BLOCK probes all still passed. Left unedited they would
have re-taught the corpus that silence means clear.

The stubs now **answer the reader's frame** rather than being made permissive:
replay each `ECHO` argument, answer `GET` with an empty value (= key absent).
They cannot mask an armed switch, and any question they fail to answer still
fails closed.

- `cabinet/tests/hook-regression/fixtures/redis-cli` — committed fixture; also
  unbroke `germline-readonly`, `germline-bash-write`, `evidence-pathnorm`, and
  is what `test_evidence_seam_bypass_replay.py` (7 failures) consumes — it has
  no inline stub of its own.
- `cabinet/scripts/tests/test_session_start_digest_patch.py` — inline shim (17).
- `cabinet/scripts/tests/test_observe_only.py` — inline shim (1).
- `framework/frontdoor/tests/test_action_undo.py` — `redis_get` answered **every**
  key with the action record, so `cabinet:killswitch` "held" a JSON blob and the
  reader correctly halted delivery. Now dispatches on the key, following the
  repo's canonical `_ks_getter` in `test_action_exec.py:360`.

Nothing outside these stub surfaces was touched. No assertion weakened or
deleted, no threshold changed. Diff: 55 insertions, 7 deletions, fixture mode
`100755` preserved.

## Evidence

Merge onto current `origin/master` `c7ca750d` was **clean, zero conflicts** —
the branch and master's delta (PR #199, self-verification hole) share no file.

Exit codes, all measured this session on the merged tree:

| gate | rc |
|---|---|
| `run-golden-evals.sh` | 0 — 29/29, incl. **EVAL-001 Kill Switch PASS** and **EVAL-002-KILLSWITCH-SEND PASS** |
| `check-layer-separation.sh` | 0 — baseline=24 allowlist=19 current=43 new=0 |
| `cog2-import-gate.py` | 0 — shadow boundary intact |
| `cognitive-architecture-census.py` | 0 — every count at or under cap |
| `docs-track-code-sweep.sh` | 0 — files=60 findings=0 |
| `run-hook-regression.sh` | 0 — **17/17 ALL GREEN** (was 13/17 with the silent fixture) |

`verify-cognitive-phase0..4`, before (origin/master) → after (merged):

| gate | before | after |
|---|---|---|
| phase0 | 1 | 1 |
| phase1 | 1 | 1 |
| phase2 | 1 | 1 |
| phase3 | 1 | 1 |
| **phase4** | **0** | **0** |

phase0..3 are the pre-existing review-digest BLOCK; their recomputed digests are
**byte-identical before and after**, so the merge moved nothing there. phase4
stays 0 — the hatch blocker is not tripped.

Serial sweep, branch vs re-measured baseline `c7ca750d`:

| battery | baseline | branch | delta |
|---|---|---|---|
| `framework/` | 1F 6504P 25S | 1F 6504P 25S | identical |
| `cabinet/scripts/tests` | 4543P 28S | 4562P 28S | **+19 passing** (new fail-closed battery) |
| `cabinet/scripts/task_adapters/tests` | 38P | 38P | identical |
| `cabinet/scripts/world-aesthetic/tests` | 87P 5S | 87P 5S | identical |
| framework collection census | 6530 | 6530 | identical |

The single `framework/` red is
`test_retro_shim.py::TestRetroShim::test_reexports_constants` — **present
identically on the baseline**, pre-existing, not this branch's.
`test_filing_latency_smoke` passed in both runs this session.
`fw057-notify-officer-argv` passed (30/30).

## Residuals carried, not fixed here

1. **RES-016 — the pre-armed clearing loop is OPEN by design.** The second stop
   channel is built and test-pinned, but nothing arms it automatically. The
   builder implemented arming, proved it worked, then backed it out because it
   changes the contract `killswitch-watchdog.py` exists to enforce (7 tests
   flipped) and a global latch leaks across suites. That is a Captain ruling,
   not a bug fix. Honest limit even so: a same-uid adversary can delete the
   marker — closing the class needs a channel the officer's uid cannot write.
2. **The web dashboard is NOT fixed.**
   `cabinet/dashboard/src/app/api/world/engine/route.ts` ~`:207-219` initialises
   the switch to `false` and its catch swallows every Redis failure, so an
   unreadable stop renders calm weather and a lever reading "fleet running".
   The Captain's **native phone card IS fixed** — it renders
   `PAUSED — emergency stop UNVERIFIABLE`.
3. **Named Captain handback:** these are schg-locked germline paths. The bytes
   land to master; one Captain unlock/relock window re-materialises them live,
   including the new `cabinet/scripts/hooks/killswitch-read.sh` (covered by the
   existing recursive DIRS lock — the germline *set* is byte-identical, so no
   amendment is needed).
4. **Two latent bugs fixed en route:** `_redis_get_strict` ignored `REDIS_PORT`
   and `kill-switch.sh` honoured only `REDIS_URL` — so on any non-default port
   the Captain's status verb and the officers' gate read **different servers**.

## Verdict

**approve** — land. The change makes an unverifiable stop behave as stopped,
proves the read against forgery, and the one arm that could brick the fleet
(healthy + clear must still allow) is measured green end-to-end. The corpus
change is strictly a de-encoding of the removed contract, not a relaxation.
