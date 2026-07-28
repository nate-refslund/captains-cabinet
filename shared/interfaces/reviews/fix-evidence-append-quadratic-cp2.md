# FW-019 checkpoint review — fix/evidence-append-quadratic cp2

**Verdict: SHIP**
**Date:** 2026-07-28 · **Baseline:** origin/master `6ec81460` · **Branch:** `fix/evidence-append-quadratic`

Reviewed-Scope-Digest: 5435fddbdd80ff6df3b7937039ca4fe7c74fe34e049022fc48ab092875210951

cp1 was written by the agent that authored the fix; it died on a session limit
after pushing and before CI came back. This checkpoint is a **second agent,
fresh context**, resuming: everything below was re-derived from the code and
re-measured on this machine, not read out of cp1. Where cp1's numbers and mine
differ they are both recorded.

---

## 1. What the dead agent had already done, and what I kept

| | |
|---|---|
| Fix (`verifier.py`, `recorder.py`) | **kept unchanged** — re-derived and attacked below |
| Sensors (needs latency ×2, recorder structural ×1, verifier memo ×6) | **kept unchanged** — mutation-proved below |
| Contract allowance row + `governance-review.py` docstring + `propose-means-propose` correction | **kept unchanged** |
| COG-4 digest re-bind (two commits) | **kept** — independently re-verified, see §4 |
| RES-007 register cite | **fixed** — this was the CI red |

CI on `41ec96a9`: run `30351043684`, seven jobs green, `framework-tests`
**red** on step *Cabinet script tests*, one assertion:
`test_open_row_cites_still_resolve_to_their_declaration`, RES-007 cite
`cognitive-core-phase-4-review.md:543` no longer carrying its anchor. Cause and
fix in commit `37285bdd`. Nothing in the evidence plane was implicated.

## 2. The property `verify_trial` protects, and why the memo preserves it

`verify_trial` re-derives, **from disk and from nothing else**, that a trial's
ledger is exactly the chain the recorder signed: per row — schema, trial id,
sequence position, `previous_hash` linkage, the recomputed `event_hash` over
the unsigned row, the HMAC signature over `(key, trial_id, sequence, hash)`,
and the absence of secret shapes; and per trial — file permissions, the anchor
agreeing with the tip, and a monotonic anti-rollback watermark. The recorder
calls it *before* every append, which is what stops a truncation from being
laundered by writing over it.

The memo preserves that because **every memoized check is a pure function of
(row bytes, position in the chain, signing key, trial id)** — no clock, no
environment, no filesystem state. The memo therefore stores the sha256 of
*exactly* the bytes it proved plus the sha256 of the key that proved them, and
re-hashes those bytes on every call before trusting them. Identical inputs,
identical verdict. Concretely, checked against the code:

- **Interior edit** (same length) → prefix bytes differ → digest mismatch → full
  re-scan. `test_memoized_prefix_still_catches_mid_ledger_content_tampering`.
- **Truncation** → `len(raw) < memo.length` → memo not even consulted; anchor
  and watermark fail closed anyway. `..._catches_tail_truncation`.
- **Key rotation** → `key_digest` mismatch → full re-scan.
  `..._catches_a_swapped_signing_key`.
- **Foreign ledger dropped into another store** → prefix digest mismatch → rows
  re-checked against the local key → refused.
  `test_a_ledger_lifted_from_another_store_is_rejected_with_a_warm_memo`.
- **A prefix that carried findings is never memoized** — `_memo_put` runs only
  on a zero-finding scan that ended on a `b"\n"` boundary, so a partial tail,
  an unreadable ledger or any finding re-scans from byte zero next time.
  `test_a_failing_verification_is_not_memoized_as_clean`.
- **Not memoized at all:** the permission checks, the anchor check and the
  watermark check. They are properties of the filesystem and of `anchor.json`,
  not of these bytes, and still run on every call — I confirmed `_verify_events`
  returns only ledger findings and the three others are appended by
  `verify_trial` itself, outside the memo.
- **Line numbering** is carried through `first_line = memo.lines + 1`, so a
  suffix scan reports the numbers a whole-file scan would.
  `test_warm_and_cold_agree_on_a_ledger_that_goes_bad_after_the_memo`.
- **The whole claim in one assertion:**
  `test_memo_hit_and_cold_scan_return_identical_verdicts` compares the warm and
  cold verdict dicts over a growing ledger.

The memo is process-local, bounded at 128 entries, guarded by a lock, and holds
immutable tuples; eviction costs a re-scan and never a verdict. A fresh process
re-derives everything from disk. **It can make verification cheaper. It cannot
make it weaker.**

The recorder change is the same argument: when `verified["ok"]` is true, the
recomputed `last_event_hash` *is* the stored `event_hash` of the last row,
because any divergence is an `:event_hash` finding and would have made `ok`
false. Taking length and tip from the verdict rather than a second `_rows()`
pass also closes the TOCTOU window between the bytes verified and the bytes
read back.

## 3. Measurements — re-run on this machine, this session

`file_need` on the production path (mirror pointed at a scratch store through
its own sanctioned seam), best of 15 samples at each depth. Pre-change tree =
this branch's tests over master's `verifier.py` + `recorder.py`, `__pycache__`
purged, `PYTHONDONTWRITEBYTECODE=1`.

| trial depth | before | after |
|---:|---:|---:|
| 40 | 3.24 ms | 1.49 ms |
| 240 | 22.66 ms | 2.09 ms |
| 500 (R-8 envelope) | 47.97 ms | 3.07 ms |
| 2000 (caps lifted, past the envelope) | 144.23 ms | 8.08 ms |

Depth-dependence **71.9 µs → 3.4 µs per prior event**, a 21x reduction —
matching cp1's 71.4 → 3.4 independently.

**One correction to cp1, and it makes the defect worse, not better.** cp1 read
36.6 ms at depth 499 and concluded the 50 ms budget "breaks past about 500
events". On this run the *best* of 15 samples at depth 500 was 47.97 ms and the
**median was 50.16 ms — already over the 50 ms hook budget at the live
ceiling**, with no extrapolation. The envelope did not protect the budget; it
was breached inside it.

## 4. The frozen-scope collision — checked, not assumed

`cabinet/scripts/cognitive-phase4-rollback-rehearsal.py` and
`verify-cognitive-phase4.sh` pin test bytes as well as code bytes, so a landing
that touches the frozen battery BLOCKs the phase gate, and re-freezing the
digest to get past that would assert a review that never happened.

Re-derived here rather than taken from cp1: `resolve_scope()` returns 85 paths;
intersected with every path this landing changes (branch diff **plus** working
tree), the result is **exactly one file** —
`cabinet/config/cognitive-architecture-contract.yml`, and only its
`temporary_allowances` block. Zero COG-4 implementation bytes, zero battery
bytes, zero test bytes. That file sits in `restore_from_baseline` and is
therefore digest-bound, which is the mechanical-delta re-bind this artifact's
own procedure prescribes and which has nine documented precedents — not a
restamp. `--verify` over HEAD after my merge and commit:

```
COG-4 review binding: OK — tested bytes match the reviewed scope digest
(5435fddbdd80ff6df3b7937039ca4fe7c74fe34e049022fc48ab092875210951)
```

My own change adds `docs/plans/declared-residuals-register.md`, which is not in
scope, so no further re-bind is owed.

## 5. Mutation proofs — the new arms against pre-change code

| arm | against pre-change code | against the fix |
|---|---|---|
| `test_append_reverifies_only_the_new_tail` | **RED** — 40 events scanned, 1 expected | green |
| `test_filing_latency_does_not_grow_with_trial_depth` | **RED** — 33.8 ms growth vs the 10 ms allowance (3.4x over) | green — 1.6 ms |
| `test_filing_latency_smoke` (50 ms absolute) | **green at 35.4 ms** | green |

The third row is the honest one and cp1 says so in the docstring: the absolute
budget arm is fsync-dominated and does *not* go red on fast hardware, which is
precisely why the depth arm exists beside it. The structural arm is the one that
is deterministic and machine-independent.

## 6. The four questions, asked of the new sensors

**Does it fail against pre-change code, both directions, cache purged?** Yes —
§5, `__pycache__` removed and `PYTHONDONTWRITEBYTECODE=1` set (which only stops
*writing*, hence the removal).

**Degenerate end?** Empty ledger: `_read_ledger_bytes` returns `b""` with no
findings, the memo stores `length=0` and the next call reproduces the cold path
exactly. Absent ledger: `recorder.append` skips `verify_trial` entirely and
starts from `ZERO_HASH`. Symlinked ledger: refused by `_private_path_error`, its
bytes never read, nothing memoized. Zero events: the depth arm subtracts
shallow from deep, so a zero-depth run yields ~0 growth and passes — which is
why the fixture **asserts** an observed depth ≥ 480 and fails loudly if the
mirror ever goes quiet again.

**What does the test environment guarantee that production does not?** This is
the question that was never asked here, and the answer *was* the defect. Under
`PYTEST_CURRENT_TEST` the evidence mirror is off unless a scratch store is
supplied, so the old budget arm measured a filing that never reached the
recorder — ~0.2 ms of a path whose other half held all the risk. The new fixture
supplies the store and asserts the depth. Residual difference that remains: the
scratch store is a fresh `tmp_path` on the runner's disk, so fsync cost and page
cache differ from the live store; that is why the sensitive arm measures a
*difference* between two depths on the same store rather than an absolute.

**Is the sensor wired to the live artifact?** Yes — the arms drive
`framework.authority.needs.file_need` and `framework.evidence.EvidenceRecorder`,
the same entry points production uses; the structural arm counts calls into
`framework.evidence.verifier._shape_errors`, the live function.

## 7. `PYTEST_CURRENT_TEST` siblings — enumerated, deliberately NOT fixed

`_store_root()` returning `None` under `PYTEST_CURRENT_TEST` is a general
mechanism. Every other site, and whether it leaves a claim unmeasured:

| site | what changes under pytest | leaves a claim unmeasured? |
|---|---|---|
| `framework/events/emitter.py:636` | the org-runtime **Store mirror write is skipped** unless `CABINET_FRAMEWORK_STORE_MIRROR=1` | **YES, the closest sibling.** Forced on in exactly two arms (`framework/events/tests/test_emitter.py:379,414`); sixteen other test files force it *off*. Every end-to-end emit claim outside those two measures the mirror-less path — its failure modes, its latency, its transactional behaviour |
| `framework/evidence_recompute.py:276` | store root `None` unless `CABINET_ACTION_EVIDENCE_STORE` set | **PARTLY.** Covered by `framework/tests/test_evidence_recompute.py`, which supplies the override; anything reaching `_store_root` without it silently no-ops |
| `framework/frontdoor/action_reconcile.py:196` | same shape | **PARTLY**, same reasoning — `framework/acting/tests/test_action_lane_evidence.py` supplies it, `framework/frontdoor/tests/test_action_reconcile.py` does not |
| `framework/frontdoor/action_exec.py:1617` | same shape | **PARTLY** — covered where `test_action_lane_evidence.py` drives it |
| `framework/evidence_recompute.py:1117` | `attest_process_identity` is **skipped in `main()`** | **YES, narrow.** The function is unit-tested (`framework/evidence/tests/test_identity.py`), but the *wiring* — that the recompute CLI attests at start — cannot be exercised in-process by any test. Sensor not wired to the live call site |
| `framework/frontdoor/action_exec.py:1872` | the re-card presentability pre-flight takes the "no channel" branch | **NO** — hermetic tests inject `telegram_send`, which bypasses the fence, so the real branch is exercised |
| `framework/events/emitter.py:347` | the event JSONL is redirected to a temp dir | **NO** — a destination redirect, not a disable; the emitter still does all its work. Only production *path resolution* is unmeasured |
| `conftest.py:107` | the documented root fence, twin of the above | **NO** — it is the fence itself |

Rows marked YES want their own ledger rows. They are not fixed here: this branch
is one defect, and widening it would put unreviewed surface under a digest that
has already been re-bound twice.

## 8. Verification run this session

- `pytest framework/evidence/tests/ framework/authority/tests/test_needs.py` — 222 passed
- `pytest cabinet/scripts/tests/test_declared_residuals_register.py` — red before the fix, 9 passed after
- `pytest framework/` and `pytest cabinet/scripts/tests` — see the PR's CI run, read per job
- `cognitive-phase4-review-scope.py --verify` over HEAD — OK

**No must-fix. SHIP.**
