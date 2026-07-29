# Checkpoint review — iso/step14-flip-and-attack-fixes (cp1)

Reviewed-Scope-Digest: cb65b979d68e10d8422d00dd32da6b60cb32b10e6db4e2667dd9555f158f5bde

Reviewer: orchestrating session (Opus 5), self-review against the attack
report's five findings plus an independent re-derivation. Every number below
was produced by a command run in this session against a fresh clone of
origin/master `c2125186`, with the world dirs verified byte-identical to
`8fa4a2f1` (the SHA the attack measured at) — `git diff --stat 8fa4a2f1..c2125186`
over the three world paths prints nothing, so the report's measurements hold.

## What this branch does

Port-plan **step 14**: `DEFAULT_PROJECTION` flips `'topdown'` → `'iso'`, so
`/world` serves the isometric world. Blocked on five findings from the attack
pass; all five are fixed here, plus one the attack did not find and one this
work introduced and closed.

## The findings, and what each fix actually asserts

**F1 — orphaned growth read-model (HIGH).** Re-derived by IMPORT ANALYSIS
rather than identifier grep: only `CensusKeyframe` (grammar route) and
`landRadius` (world-geo) have a production consumer. The attack named five
orphans; there are **nine** (`tier`, `surfaceGrowth`, `GrowthSurface`,
`ageDays`, `streetAgeBand`, `StreetAgeBand`, `GrowthModel`, `GROWTH_BASES`,
`buildGrowth`) — `ageDays` looked live because `engine/route.ts` defines a
LOCAL function of the same name. Dead code and its 10 tests deleted together.

The durable half is **ratchet 11** in `ratchets.test.ts`: dead exports at
SYMBOL granularity, tests explicitly NOT counted as consumers (the only
setting under which it would have caught this — `growth.test.ts` imported
`buildGrowth` to the end). First run found 38, nearly all pre-existing, so it
lands as a measured SHRINK-ONLY baseline (same shape as the layer-separation
gate), not a zero and not a 38-line mute. Comments are stripped before
counting: the first draft passed a re-added `buildGrowth` because this
module's own header names it.

**F2 — the Legend claimed 100% coverage of law it cannot draw (HIGH).**
New `law-render.ts` classifies every ratified `morphology.yml` id as rendered
(with surfaces, per kernel) or unrendered (with a reason). The Legend now shows
a second, honest gauge and NAMES the rows it cannot paint. Nine are unrendered
under iso; the attack said seven, and the two it missed
(`subagents_lifetime`, `golden_evals_delta`) have no ladder and no surface in
either kernel.

The teeth are against LIVE artifacts, not against the file's own opinion:
set-equality with `morphology.yml` on disk (both directions), every claimed
layout surface checked against what the REAL `composeLayout` places across
five seeds, every code surface resolved by import.

**F3 — five officers drawn in the iso room, none clickable (MEDIUM).**
`roomFixtures` is now the ONE placement, used by the draw pass AND the pick;
the officer boxes are handed to `pickTarget` rather than recomputed, so the hit
test is testing what was drawn by construction. `drawIsoCutaway` clears the box
list first, on every pass and before every early return — a closed room must
never name an officer.

**F4 — the P0-2 sensor was walkable (MEDIUM).** Confirmed: mutation M6 (keep
the builder call, discard its return, hand-roll the query) passed the old arm.
The decision moved into `nextWorldHref`, exercised directly; the component's
untested surface is now one call whose result IS the argument.

**F5 — a `done` row's gate verified half what it named (LOW).** Fixed in both
twins. A general "every gate_cmd path exists" check was measured first and
rejected: 33 hits, almost all legitimate (gitignored runtime artifacts, glob
fragments). The gate that landed is scoped to explicit `npx vitest run` file
arguments — the one shape that fails SILENTLY, because pytest exits non-zero.

**NEW (not in either report) — the iso page fetched the entire top-down LimeZu
sheet universe and drew none of it.** The iso pack's load is gated on `isIso`;
`resolveOutdoorSprites(manifest, 'island')` never was. Measured in a browser:
**56 requests** under the iso default. It also made `credit.ts` wrong in the
direction that matters — that module computes the licence notice from the claim
that iso binds the owned atlas and the cast alone. The canvas now resolves
`canvasAssetIds(projection)`, so the notice and the network requests come from
one list. Re-measured after the fix: **0**.

**INTRODUCED AND CLOSED.** F3's fix made five invisible dead affordances into
five VISIBLE ones; that is why the pick change ships in the same commit as the
room it makes clickable, not after it.

## Every arm proven to fail

Ten mutations, each reverted and re-verified green:

| # | Mutation | Result |
|---|---|---|
| M1 | drop a law row from `LAW_RENDER` | red |
| M2 | delete the real `mailbox` renderer from the dressing | red |
| M3 | reclassify `harbor_boat_voyage` as rendered | red |
| M4 | add a new dead export | red |
| M5 | re-add `buildGrowth` as dead code | red *(passed before comment-stripping)* |
| M6 | keep the URL builder call, discard it, hand-roll the query | red *(passed the OLD arm)* |
| M7 | give a baselined export a consumer, leave it listed | red |
| M8 | delete the `nextWorldHref` call | red |
| M9 | write `iso` only when iso, in the builder | red |
| M10 | revert the ungated sheet load | red |

M1's first revert silently no-opped (`git checkout --` does nothing to an
untracked file) and the next two runs were measured against a still-mutated
file. Caught because "restored" did not return to green. Recorded because the
same shape would have produced a false all-green.

## Gates run this session

- dashboard vitest **2733 passed / 0 failed / 1 skipped** (baseline 2707)
- `tsc --noEmit` clean · `next build` exit 0, `/world` in the route table
- layer separation `new=0` · A13 parity OK · ledger status-parity GREEN
  (353 ids) · docs-track-code GREEN (64 files)
- world-aesthetic 91 passed/5 skipped · world-capture 34 passed
- ledger-purge 16 passed · new ledger gate 4 passed
- palette_coherence on the delivered frame: **ok, 1.23% foreign** (limit 5%)

## Tests that stopped executing — all 15, with the reason

13 over `buildGrowth`/`surfaceGrowth`/`tier`/`ageDays`/`streetAgeBand`: the code
they covered is deleted. 1 renamed (`DEFAULT_PROJECTION` now asserts `'iso'`).
1 replaced (the walkable rewrite arm, superseded by the `nextWorldHref` suite).
37 added.

## Declined, stated plainly

**Rendering the nine unrendered law rows.** Two need state that is not on the
`/api/world/engine` payload at all (`tier2_note_files`, `events_today`); two
were legacy-shell-only surfaces; three need an iso dynamics layer that does not
exist (`drawIsoDynamics` paints the lamp and the cutaway, nothing else); two
have no ladder in either kernel. That is a phase of work, not a finding fix.
What changed is that it is now VISIBLE in the Legend with a reason per row
instead of hidden behind a green 100%.

**The pairwise vision judge.** Its corpus images are gitignored and absent from
a fresh clone. Mechanical palette gate green is reported; the judge is not
claimed.

## Known-red, pre-existing, NOT introduced here

`palette_coherence` fails on FOG frames — 11.15% foreign, dominated by two
fog-lightened sea teals that are drawn by code and were never in the
atlas-fitted palette. Sun frames pass at 1.23-1.61%. This morning's pre-flip
capture fails the same gate at **34.9%**, so it predates the flip. Diagnosed,
recorded in BACKLOG, thresholds untouched.
