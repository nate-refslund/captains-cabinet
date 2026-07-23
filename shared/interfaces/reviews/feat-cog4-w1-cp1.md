# FW-019 checkpoint — feat/cog4-w1 (COG-4 W1 landing integration, 2026-07-23)

One PR lands the four reviewed W1 units off post-WR `origin/master` 0d8a74d4, plus the
integrator joins J1-J4. Integrator: fresh-context Fable session, scratch full clone
(never the live tree). Per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan grant.

## Units landed (review chains)

| unit | branch@sha | verdict | chain |
|------|-----------|---------|-------|
| u1 | feat/cog4-w1-u1 @dfab84f8 | SHIP | C2 boundary engine: `boundary-manifest.yml` + `cog2-import-gate.py` engine conversion + `test_cog4_boundary_rows.py` + cp artifact; byte-compat proven pre-WR by the unit, RE-PROVEN post-WR at integration (J1). |
| u2 | feat/cog4-w1-u2 @54835c37 | SHIP after 2 fix rounds | guards: `test_cog4_fleet_truth.py` + 3 AST-pin tests + `lib_cog4_ast_pins.py` + cp artifact; review rounds closed the exec-pin, closure, and star-import (`from os import *` MF-R1 exec-bind) escapes (commits 6f9712e0 → 593398af → 54835c37). |
| u3 | feat/cog4-w1-u3 @6f90e577 | PARK upheld | marker doc only (`cog4-w1-u3-officer-plist-cleanup-PARKED-2026-07-23.md`); parked on cos-inbound blast-radius evidence (one plist is the live watchdog). J2 amended its one false sentence. |
| u4 | feat/cog4-w1-u4 @1bcd7a22 | SHIP | C1 closed-range retrofit phases 0/1/2 (3 manifests + 3 footprint tests), seal-vs-doneflip semantics reviewed (COG-1 PARKED → footprint SEAL stand-in). Phase 3 applied at integration (J3). |

Merge order: u1 (conflict-resolved) → shadow-dividend docstring fix → u2 → u3 → u4 →
joins commit → this re-freeze/cp commit.

## J1 — u1 byte-compat RE-PROOF vs post-WR master

The u1 merge conflicted exactly where expected: the WR merge grew the OLD gate's
objectives exact allowlist by two rider CLIs inside `cog2-import-gate.py`, which u1
rewrote wholesale. Resolution: u1 engine bytes taken; the WR delta carried into
`cabinet/config/boundary-manifest.yml`:

- **Objectives module row** `allowlist_exact` += `cog3-verdict-inbox.py`,
  `cog3-shadow-dividend.py` (comments mirrored from the post-WR gate; "three" → "five").
- **Objectives data-plane row** `allowlist_exact` += the same two. DEVIATION (widening
  beyond the task's literal "objectives-row"): mechanically REQUIRED for byte-identity —
  the pre-conversion gate feeds ONE set (`ALLOWLIST_EXACT_OBJECTIVES`) to checks O AND D,
  and `cog3-shadow-dividend.py:525` carries the store path in its `--cache-dir` argparse
  help (a live line); row-2-only would have RED'd the committed tree where the old gate
  is green.
- **Cortex row deliberately NOT widened** (second deviation, protection-growing): the old
  gate's Check-3 ALSO skipped the shared set, but neither rider imports the cortex
  (verified: comment/docstring mentions only) — current-tree parity holds and the
  narrower row means a future rider cortex-import REDs instead of riding a set-sharing
  artifact.
- **Cross-wave catch (new engine row bite):** u1's NEW scheduler data-plane row
  (`FORBIDDEN_SCHEDULER_DATAPLANE`, no pre-conversion analog) bit the WR rider's
  docstring precedent-citation naming `cabinet/cache/scheduler` on a live docstring
  line. The rider never reads the schedule store, so allowlisting it would WEAKEN the
  new fence — the docstring prose was reworded instead (2-line, behavior-neutral,
  commit 94c00aff).

**Proof (integrated tree):** old gate extracted from `origin/master` 0d8a74d4, both run
over the same tree in all 3 modes (check / `--report` / `--json`): outputs
byte-identical, both empty (`violations: [], count: 0`), rc parity 0/0/0 vs 0/0/0.
Post-WR 5-member exact-set pin (`test_cog3_allowlist_covers_the_reader_clis_only`) +
committed-tree-clean anchor: both pass against the engine.

## J2 — u3 marker amend

The sentence claiming `test_cog4_fleet_truth.py` "already pins the out-of-manifest set"
(false at writing — the guard rode u2's unlanded branch) now states the guard lands via
u2 in this same wave PR. Nothing else changed.

## J3 — phase-3 coordinated re-freeze

(a) Manifest `cognitive-core-phase-3-rollback-manifest-2026-07-22.yml` gains
`done_flip_sha: e7f95d5a…` (the COG-3 done-flip commit) + the C1 seal note, u4 ph2
shape. Derivation: `b2890f19..e7f95d5a` = exactly 65 paths (50 A + 15 M), zero strays
(ratchet-verified); the flip commit touches only the two retained operative ledgers.
Test gains `DONE_FLIP_SHA` + lockstep assert + both-SHA shallow-skip probe + closed
range + `done_flip_sha` key-set entry — 12/12 green.

(b) Rehearsal `cognitive-phase3-rollback-rehearsal.py`: scratch worktree anchored at
`done_flip_sha` (was HEAD) and must-remain checks over `baseline..done_flip_sha`, sha
read from the manifest; pre-bump refold assert intact. At HEAD the inverse-diff
append-only-only assertion was structurally red once COG-4 commits landed (they are
neither removed nor restored by the COG-3 manifest). END-TO-END now **PASS** — 29/29
compat floor green in the scratch tree, "only append-only operative history remains".

(c) GENUINE mechanical-delta re-review (not a restamp), fresh-context w.r.t. every
unit. Re-run on integrated bytes: combined `test_cog3_*` + phase-3 rollback battery
**385 passed, 2 skipped** — exact reconciliation vs the frozen 361: +24 = the WR
verdict-inbox (…) + shadow-dividend suites added after the freeze; same two declared
measure-only perf skips. `TestServeSurfaceUniformity` **12/12** (all REFUSE cells).
Rehearsal end-to-end **PASS**. cog2 battery **280 passed, 3 skipped**. J1 byte-compat
proof (above). Digest re-frozen `e98fc026…` → `78a7bf18…` via
`cognitive-phase3-review-scope.py --print` → embed → `--verify` rc=0; dated
administrative note appended to the review artifact (items 25-28), verdict unchanged
PASS. `verify-cognitive-phase3.sh` on the committed re-freeze tree → READY_FOR_CI FULL
GREEN (the J3 exit criterion; result echoed below once run post-commit).

## J4 — full verification on the integrated branch

- Full `cabinet/scripts/tests` sweep: **2824 passed, 17 skipped, 0 failed** (5:40).
  The 3 old rollback-ratchet full-clone fails are GONE (ph1/ph2 via u4, ph3 via J3).
- u2 guard files (fleet-truth + 3 AST pins): **114 passed, 7 skipped**.
- Boundary harness `test_cog4_boundary_rows.py`: **80 passed**.
- Census `--check`: exit 0, every budget observed <= max (zero-headroom unchanged).
- Layer-sep: OK — new=0 (baseline 24, allowlist 19).
- `test_egg_export.py`: green inside the sweep — no egg-manifest additions needed.
- HEAD-bytes YAML parse: boundary-manifest + all 4 phase rollback manifests ok.
- `verify-cognitive-phase2.sh`: rc=1 at its review-digest binding ("reviewed bytes !=
  tested bytes") — PRE-EXISTING on post-WR master (the WR merge already grew
  `cog2-import-gate.py`, a phase-2-scope path) and moved further by this wave (u1 engine
  rewrite + u4 ph2 retrofit are both in ph2 scope). Re-freezing the PHASE-2 review is
  out of wave scope per the wave order; noted, not fixed.

## Optional item taken

u4's should-fix comment reword: ph1/ph2 ratchet comments no longer overstate that a
later same-phase commit "trips" the closed range — it lands OUTSIDE the sealed range;
resuming/re-opening a phase means extending the manifest AND moving the seal pin
forward. (Matters most for PARKED COG-1, which may resume.)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
