# Checkpoint review — feat/p1-tap (phase-1 unit 1, the tap)

Reviewed-Scope-Digest: e2db080fd28988f786300ac55d404b2a722fd4f6faf38ce2b68361bcd3ad3ecb

What that digest binds: the 34-path scope of the branch as REVIEWED —
`c479b5f5fccde28a2629c228b5b386d3218c4ac9..3c62e04ccbef3a1b3109b072cf9f6edadf7c4739`,
computed with the FW-019 grammar (`git diff --raw --abbrev=40 --no-renames -z`,
`shared/interfaces/reviews/` excluded, LC_ALL=C sorted, sha256). The commit this
artifact rides is the merge with master, which the gate exempts by name
(`cabinet/scripts/git-hooks/pre-commit:157-160`) precisely because a merge
carries the other side's bytes rather than new work; the digest above therefore
binds the reviewed side, which is the thing a reader wants bound.

## The two records

**1. Independent review — APPROVE.** Fresh context, Opus 5, its own clone,
nothing reused from the builder, at `head_sha_verified = 3c62e04c`. Posted in
full on PR #371 (comment of 2026-09-07T19:01:03Z) and not reproduced here.
It re-derived every §1 interface item, invariant and sensor; reproduced every
INVARIANT-level sensor RED on master bytes **for the reason the invariant
names** (not an ImportError) and GREEN after; proved the `cabinet/scripts/tests`
and `run-hook-regression.sh` failing sets identical to pristine master's by
per-test and per-harness verdict lines rather than counts; and confirmed the
locked-set intersection empty. Three non-blocking findings were recorded there:
`edited_since_proposed` reporting `false` where it is unknowable, the web door's
constant `'dashboard-session'` principal, and a stale `--ratified-by captain`
line in `.claude/skills/mission-compile/SKILL.md`. None is a merge blocker and
all three are named residuals, not silent omissions.

**2. This landing.** What the lander did that the review could not: master moved
by four merges (U2 claim #373, U3a gaps #370, U4r drill #374 and their merges)
between approval and landing, so the branch was merged with master and the whole
battery re-run on the merged bytes. The reviewer's evidence is cited, never
re-typed as if measured here.

## Merge resolution — three conflicts, all in the architecture-budget plane

Resolved under contract AMENDMENTS round 2, **A0.9**: where two units raise the
same maximum off a common base the merged value is the **SUM of the raises**,
never the max of the two, and every expansion row from both sides is kept.

| Conflict | Base | Landed side | This branch | Merged |
|---|---|---|---|---|
| `framework_production_modules` maximum | 208 | +1 (claims.py) | +3 (outcomes/__init__.py, outcomes/ratify.py, missions/receipts.py) | **212** |
| `framework_production_noncomment_lines` maximum | 64741 | +129 (U3a) +787 (claim) | +623 (tap) | **66280** |
| `expansions:` rows | — | claims.py, work_item_claim_renewed, work_item_claim_released | ratify.py, outcomes/__init__.py, receipts.py | all six kept |

Both comment blocks survive on each numeric row — a budget row whose reason was
dropped at a merge is a budget row nobody can audit later.

Not summed on paper: `cognitive-architecture-census.py --check` re-measured the
merged tree and returned PASS with `framework_production_modules: 252 <= 252`
and `framework_production_noncomment_lines: 80930 <= 80930` — observed ==
maximum on both, zero headroom, which is what the SUM rule is supposed to
produce and is the arm that would have caught it if it had not.

Fourth conflict, `cabinet/scripts/tests/test_baseline_set_ratchet.py`: master's
side taken **whole**, not merged. This branch had appended its three new members
to a typed literal; master's side reads the adjudicated member list back from
the live expansion registry (`_live_expansion_members`) while keeping EXACT
set equality, so it asserts the same thing this branch was asserting by hand and
covers the tap's three members without another author re-typing the list. Taking
the literal instead would have re-armed the breakage master had just removed.

**A0.10 checked, not assumed:** `framework/tests/test_interpreter_pin.py` passes
on the merged tree. Its `work-graph-complete.sh` PENDING row was already retired
by the U2 lander (2026-09-08) and the surviving `cabinet/cron/mission-supervisor.sh`
row names a script this unit does not pin — so the sanctioned PENDING-row
deletion does not apply here and none was made.

## Battery on the merged tree — this clone, foreground, per-job commands

| Command | rc | Result |
|---|---|---|
| `python3.12 -m pytest framework/ -q -rs -p no:cacheprovider` | 0 | 8442 passed, 31 skipped, 2 subtests passed |
| `python3.12 -m pytest cabinet/scripts/tests -q -p no:cacheprovider` | 1 | 1 failed, 5389 passed, 34 skipped |
| `python3.12 -m pytest cabinet/scripts/task_adapters/tests -q` | 0 | 56 passed |
| `python3.12 cabinet/mcp-server/test_server.py` | 0 | 95 passed |
| `bash cabinet/scripts/check-layer-separation.sh` | 0 | baseline=24 allowlist=19 current=43 **new=0** |
| `bash cabinet/scripts/docs-track-code-sweep.sh` | 0 | files=65 findings=0 |
| `bash cabinet/scripts/ledger-status-parity.sh` | 0 | ids=353 md_rows=353 findings=0 |
| `bash cabinet/scripts/run-hook-regression.sh` | 1 | 11/19 harnesses |
| `bash cabinet/scripts/test-triggers.sh` | 0 | PASS 55 / FAIL 0 |
| `bash cabinet/scripts/test-mac-dry-run.sh` | 0 | Mac dry-run eval PASS |
| `bash cabinet/scripts/null-hatch.sh` | 0 | PROOF 1 — NULL HATCH: PASS |
| `python3.12 cabinet/scripts/state-persistence-preflight.py --repo .` | 0 | 97 candidates, 0 UNACCOUNTED |
| `python3.12 cabinet/scripts/cognitive-architecture-census.py --check` | 0 | PASS, every class at or under its maximum |
| `npm ci --no-audit --no-fund` (cabinet/dashboard) | 0 | 297 packages |
| `npx vitest run` | 0 | 183 files, 3849 passed, 1 skipped |
| `npx tsc --noEmit` | 0 | clean |

**The failing set is identical to the declared pre-existing set, proved by
verdict lines rather than counts.**

- `cabinet/scripts/tests`: the one failure is
  `test_evidence_seam_bypass_replay.py::test_shipped_catalog_harness_still_green[evidence-access.sh]`
  — the declared pre-existing row, and the same single row the independent
  reviewer measured on an idle machine at PR head.
- `run-hook-regression.sh`: failing harnesses are `fw040-hotfix5 · fw040-h6-v2 ·
  fw056-baseline · fw056-adversary · fw057-notify-officer-argv · fw076-pool-mode
  · evidence-access · captain-exceptions` — exactly the eight declared for this
  host, no more and no fewer.

CI checks on the PR are ignored under the standing CI-outage protocol: GitHub
Actions is billing-locked and every job fails instantly with 0 steps, so local
proof in a fresh clone of the landing bytes is the gate (A0.6).

## The unit's own sensors, re-run on the merged bytes

`framework/outcomes/tests/test_ratify.py`, `framework/missions/tests/test_receipts.py`,
`framework/onboarding/tests/test_no_manual_ratify_text.py`,
`framework/frontdoor/tests/test_binder_ratify.py`,
`framework/attention/tests/test_advisor.py`,
`cabinet/scripts/tests/test_ratify_doors.py`,
`cabinet/scripts/tests/test_ratify_text_sweep.py`,
`cabinet/scripts/tests/test_baseline_set_ratchet.py` — **103 passed, rc 0**.
Dashboard arms `src/actions/outcomes.test.ts` + `src/lib/outcomes.test.ts` —
**34 passed, rc 0**. Red-before-green for all of these is the reviewer's record
at PR head; the merge changed no source file of this unit, only the two budget
files above, so what is re-proved here is that the merge did not break them.

## Laws checked at landing, not inherited

- **Locked set.** `git diff --name-only origin/master` = 33 paths; intersected
  against the parsed `FILES` (73) and `DIRS` (7) of
  `cabinet/scripts/germline-lock.sh` → **empty**. Run again immediately before
  the merge commit, not once at the start.
- **A0.3, Python 3.9 for the pull path.** `/usr/bin/python3` is 3.9.6 on this
  host. All 17 changed `.py` files byte-compile under it, and
  `framework.outcomes.ratify`, `framework.missions.receipts`,
  `framework.missions.claims`, `framework.missions.session_bridge`,
  `framework.missions.compiler`, `framework.learning.capability_gaps` and
  `framework.events.emitter` all import under it.
- **Agnostic.** `check-layer-separation.sh` new=0; door kinds stay
  `terminal | web | chat`; the merge introduced no new name.
- **Docs track code.** `docs-track-code-sweep.sh` green over 65 files.

## What this landing does NOT prove

The drill has not run on the installed Cabinet, and per **A0.8** the phase-1
ledger status stays `in-flight`: nobody writes `done` on a fixture pass. The tap
is landed and sensed; the Captain has not yet tapped a real card on his own box,
which is the acceptance A0.7 names and which no test in this battery can stand
in for.
