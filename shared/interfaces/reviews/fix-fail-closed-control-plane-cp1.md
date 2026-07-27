# Checkpoint review — fix/fail-closed-control-plane cp1 (2026-07-26)

Reviewer: the implementing session, against executed evidence only. Every claim
below was produced by a command run this session against real `redis-server`
processes on ephemeral ports (never 6379, never the live plane).

## The defect, reproduced before anything was changed

`cabinet/cron/cost-summary.sh` read the day's spend as
`redis-cli … 2>/dev/null` + `[[ … =~ ^[0-9]+$ ]] || DAILY_MICRO=0`. Driven
against a port with nothing listening, with the outbound sender stubbed to a
file:

| condition | bytes that would reach the Captain's group | rc | stderr |
|---|---|---|---|
| healthy plane, true zero-spend day | `💰 Cabinet cost summary …  Total: $0.00` | 0 | empty |
| control plane DEAD | `💰 Cabinet cost summary …  Total: $0.00` | 0 | empty |

`cmp` reports these **byte-identical**. The outage rendered as a legitimate
business result on the one automated surface that reaches the Captain
personally.

Independently confirmed on the live plane (read-only `GET`):
`cabinet:watchdog:outcome:heartbeat` was **34.5h stale, 27.6× its documented
75-minute floor**, and nothing had fired.

## Shape, not instance

A value read through `2>/dev/null` and coerced to its type's identity element
(`0`, `""`, absent) — **which is also a valid business answer**. `|| echo 0` is
the same bug written shorter. 36 `|| echo 0`-family lines exist across
`cabinet/**/*.sh`; the enumeration and the converted/left split is in the PR
body.

## What was built (all repair, no new machinery)

1. **`cabinet/scripts/lib/plane-read.sh`** — one proven-read helper returning
   **VALUE / ABSENT / INDETERMINATE**, lifting the nonce-sandwich discipline
   verbatim from `cabinet/scripts/hooks/killswitch-read.sh`. Not a second
   dialect: same endpoint precedence, same rc 11 for INDETERMINATE.
2. **`cost-summary.sh`** — proves the plane once, then reads each officer's
   spend. Any INDETERMINATE abandons the digest for one honest line. Never
   emits a number it cannot source.
3. **`cost-report.sh`** — same, and the invented innocent cause
   (*"stop-hook may not have fired yet"*) is gone; the genuine one is now an
   observation about a **verified-reachable** plane.
4. **`triggers.sh`** — the failed-XADD line now carries `trigger_send failed`,
   a token the detector actually scans for, pinned to the registry's tuple by
   an executed test.
5. **EVAL-009** — re-pointed from a regex broader than the detector to the
   detector's own `JOB_ERROR_MARKERS`, read out of `registry.py` at eval time.
6. **`heartbeat-watchdog.sh`, `retro-trigger.sh`, `meta-cognition/lib.sh`** —
   the three non-cost sites where an unreadable plane drove a real decision.

**Built, tested, and NOT landed — handed back:** the `control-plane-reachable`
watchdog row plus `Probe.redis_health()`. Ten tests, all green, including the
forgery arm. It is not in this PR because
`framework_production_noncomment_lines` in
`cabinet/config/cognitive-architecture-contract.yml` is at **observed ==
maximum == 67578** — zero headroom by design — so *any* framework growth fails
the census. The only sanctioned path is a `temporary_allowances` row
(phase / budget / additional / reason / owner / sunset / deletion_gate) in that
contract. That is an architecture-contract amendment, not a repair, and the
census is owned by a concurrent agent. Measured delta had it landed:
`registry.py` +70, `check.py` +35 non-comment lines. The gap is now documented
in `framework/docs/outcome-watchdog.md` rather than worked around.

## Where I attacked my own fix

- **Does each new arm FAIL against pre-change code?** Yes, all four red proofs
  executed (see PR body). The cost-surface proof was initially a *fixture
  error*, not a real red — the sandbox hard-required `plane-read.sh`, so
  "the repo has no fail-closed read" surfaced as an ERROR rather than a
  FAILURE. Fixed the fixture to mirror the repo as-is; the honest re-run gives
  7 genuine assertion failures and 3 passes (the negative controls, which
  should pass on both trees).
- **Degenerate end.** `HGETALL` on a missing key frames as one *blank* payload
  line, not zero lines — the first implementation returned VALUE("") for it.
  Caught by execution, fixed to ABSENT.
- **Is the sensor wired to the live artifact?** The new watchdog row ships
  **armed** in `instance/config/watchdog.yml`, not staged dark. A catalog row
  nobody enables is precisely the "sensor pointed at a dead twin" class this
  sweep was hunting. Arming moved the enabled count 5 → 6; both pins updated
  with the reason recorded.
- **Can the check be forged?** A shimmed `redis-cli` that prints `PONG`
  unconditionally is REJECTED by the new code and ACCEPTED by the old — proven
  by running both trees against the same shim. A shim that prints an empty line
  can no longer forge a `$0.00` digest.
- **Fail-closed ≠ fail-always.** Every surface has a negative control asserting
  the real numbers still render on a healthy plane, and that a genuine
  zero-spend day still shows `Total: $0.00`.
- **`set -u` on the error path.** `retro-trigger.sh` died on
  `PLANE_REASON: unbound variable` because the read ran in a `$( )` subshell.
  Found by execution, not review. Fixed at both ends: the callers no longer use
  command substitution, and the helper pre-declares its result variables — a
  crash on the error path is its own kind of fail-open.

## Stated limits (not papered over)

- **The Chair escalation runs over Redis.** On a FULL outage the new watchdog
  row cannot page — `route_failure` returns "escalation FAILED to enqueue" and
  the finding lands only in the sweep's report. This is recorded in the
  verify's docstring and the docs table. Closing that case needs the
  off-machine dead-man, which already exists. Building a second in-cabinet
  escalation channel would be machinery that dies with the thing it watches,
  and was explicitly out of scope.
- **`cabinet/scripts/hooks/*` sites were not converted** — schg germline, and
  their `|| echo 0` reads feed context display, not a Captain-facing business
  result. Handed back rather than worked around.
- **`plane-read.sh` is not germline.** Reasoned in the file header: an officer
  who wanted to hide spend would edit `cost-summary.sh`, which is not germline
  either, so locking the helper alone buys nothing while making every future
  repair need a Captain ceremony. One-line `FILES[]` addition if that calculus
  changes.

## Verification

Full sweep results are in the PR body. Nothing here was claimed from reading.
