# Checkpoint review — `unit-sensor` cp1 (FW-019)

**Scope:** make the spend-limit sensor honest, green, CI-run, and still able
to fail. Four files: `memory/golden-evals/framework/fw-002-spending-limits.sh`
(rewrite), `cabinet/scripts/run-golden-evals.sh` (EVAL-003), 
`cabinet/scripts/tests/test_killswitch_fail_closed.py`, 
`.github/workflows/cabinet-ci.yml`.

## The defect being closed

The FW-002 eval controlled caps by planting them in the hook's on-disk config
cache. Commit `77422706` replaced that cache with a per-invocation `mktemp`
regenerated from the yaml on every call, so from that commit on the planted
caps were ignored and test groups 2-4 silently read the LIVE
`instance/config/platform.yml`. They passed only because the real cap happened
to equal the planted one ($75). The eval was green while proving nothing about
what it claimed to test — and nothing in CI ran it at all; its only executor
was `framework/learning/self_improvement_loop.py`, unattended, where it had
been red for weeks with no gate reporting it.

## What changed, and why each choice

| Choice | Reason |
|---|---|
| Synthetic `CABINET_ROOT` per arm | the only config surface the current hook honours |
| Hook runs UNPATCHED (no sed-rewritten copy) | the sensor must be wired to the live artifact; a patched twin can drift silently |
| A **mechanism probe** ($0.000001 cap vs $1 spend) that must BLOCK before any other arm runs | an ignored synthetic root would make every allow-arm pass for the wrong reason; the probe fails CLOSED |
| Structural `grep` assertions on the hook (CABINET_ROOT honoured, both yaml paths, cache is an mktemp) | fail closed on mechanism drift instead of quietly testing something else |
| Cabinet-wide arms assert `BLOCKED — cabinet-wide` **and forbid** `officer=` | the old arm exited 2 off the per-officer gate — right exit code, wrong gate; exit-code-only would have been a false green |
| Telegram arms register the test officer in a synthetic mcp-scope derived from the REAL file | the §9 gate fails closed on an unlisted identity, so the old arm was testing identity registration, not contract (b) — a false red |
| Live-config arm asserts CONSISTENCY, not a fixed cap | a specific-value assertion false-REDs the day the Captain legitimately changes a cap |
| `SAVE_DONE` guard around cleanup | an infra_fail before the save loop must never HDEL a field whose real value was never read |
| Killswitch is READ, never written | clearing a deliberately-armed stop is the incident `evals-redis-sandbox.sh` exists for |
| fw-002 does NOT source `evals-redis-sandbox.sh` | fw-002 is germline-locked, that lib is not; sourcing it would make the isolation property depend on an officer-writable file |

## Adversarial checks run

Both directions, against the final file, hook restored byte-identical after
each:

* remove `_cap_is_unlimited` from the hook → 6 arms RED (the ruling arms),
  literal-`0` arms stay green — the eval discriminates the sentinel from the
  numeric-zero path.
* break only the cabinet-wide comparison → 3 arms RED, everything else green.
* break the per-officer comparison → mechanism probe fails CLOSED, exit 1, no
  arm results reported.
* defeat `_spend_gate_can_fail_closed` → the killswitch test goes RED.
* arm the killswitch on a shared endpoint → infra_fail, killswitch NOT
  cleared, pre-existing cost field NOT destroyed.
* restored → 30/30 green, exit 0.

## Residual / not closed here

* `memory/golden-evals/` is schg-locked germline. This lands as bytes on
  master; materialising them on the live Mac needs one Captain unlock/relock
  window.
* 5 pre-existing failures in `cabinet/scripts/tests` (cognitive-architecture
  census + its egg-export consumer) are untouched — another agent owns that
  surface. They do not exist on `origin/master`.
