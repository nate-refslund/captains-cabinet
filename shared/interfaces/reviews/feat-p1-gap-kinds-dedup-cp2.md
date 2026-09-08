# Checkpoint review — feat/p1-gap-kinds-dedup (cp2, the evidence pass)

Base: origin/master `c479b5f5` (cp1 reviewed against `1d1aec53`; master has since
taken PRs #367, #369, #368 and the branch carries a clean merge of it).
Unit U3a — contract §3 (the `capability_gaps.py` half), amendments A3.1, A3.2, A0.3.
Reviewer: the building session, in a fresh clone, on the pushed bytes.

## What changed since cp1

Nothing in the interface. cp1's first residual — "the loop's own summary does not
yet count `surfaced`" — is CLOSED by `5ec26d61`: `self_improvement_loop.run_loop`
counts `surfaced` in its own report, its exception fallback carries the key, and
`TestStructuralGapsAreCountedNotProposed` pins it. A routing bucket with no
consumer is a bucket a later edit deletes without a test noticing, which is why
it did not stay a residual. `62cf8d98` fixed the second half of the same defect
one layer out: `record-capability-gap.sh` used to announce "the loop will propose
a fix to the Captain" for EVERY non-procedure kind, which the widened vocabulary
turned into a lie an officer would wait on.

## Red→green, re-run this session (not inherited from cp1)

The invariant harness states U3a's invariants and calls `record_gap` with
`dedup_key` only where the tree's signature accepts it, so the red arm on master
fails for the invariant's reason and never for a TypeError:

| arm | tree | result |
|---|---|---|
| invariant harness | `c479b5f5` pristine worktree | **10 of 13 invariants FAIL** — `kind` recorded as `tool`; the gap PROPOSED and `notify_fn` fired; 6 then 16 `capability_gap_merged` with 0 recorded (every subject collapsed into one gap) |
| invariant harness | branch `378f20dd` | 13/13 pass |
| `test_record_capability_gap_script.py` | `c479b5f5` + the test file | 3 failed — master prints `[tool] … will propose a fix to the Captain` for `--kind skill` |
| `npx tsc --noEmit` | branch with `lib/capability-gaps.ts` at master bytes | rc=2, TS2322 ×3 + TS2345 on the structural kinds |

Six mutation arms, each breaking ONE control on the branch, each caught by the
sensor that names it (route branch → surface-only test; both auto vetoes →
autonomy test; classify fallback → ambiguity test; scan sees keyed gaps → merge
-target test; `_gaps_lock` dropped → 9 records instead of 2 under 16 observers;
a runtime `str | None` → the 3.9 union test). The two auto vetoes are redundant
by design: dropping only one leaves the sensor green, so the arm drops both —
recorded here rather than left as a false claim of independence.

## Battery

`framework/` 8281 passed / 31 skipped; `cabinet/scripts/task_adapters/tests` 56;
mcp-server 95; layer-separation, docs-track-code, ledger parity, triggers,
mac dry-run, null-hatch, persistence preflight all rc=0; dashboard vitest
3810 passed and `tsc --noEmit` clean. Two rc=1 commands, both the documented
pre-existing set on this host and unchanged by this branch:
`test_evidence_seam_bypass_replay.py::test_shipped_catalog_harness_still_green[evidence-access.sh]`
(harness PASS=10 FAIL=2) and `run-hook-regression.sh` 11/19 with the failing set
{fw040-hotfix5, fw040-h6-v2, fw056-baseline, fw056-adversary,
fw057-notify-officer-argv, fw076-pool-mode, evidence-access, captain-exceptions}.

Locked set: 0 of the 14 changed paths intersect the 73 FILES + 7 DIRS parsed
from `germline-lock.sh`.

## Residuals (unchanged from cp1 minus the closed one)

- A3.3 (an `authority`/`information` line on the briefing card) and the
  `missions/gaps.py` producer are U3b's; U3a records and renders only.
- A0.3's repo-wide grep sensor over bare `python3` in unlocked exec strings waits
  on U2, which owns the remaining anchor (`work-graph-complete.sh`).
- The 3.9 arm here is grammar + evaluated-union static analysis plus a live run
  through the box's own `python3` (3.9.6, asserted in the script test); the
  standing runtime-3.9 CI leg arrives with the drill.
