# Checkpoint review — iso-layout cp10: the pier that was attached to nothing

Branch `iso-port-composition`, on top of `f655bc5b`. One unit:
`iso-layout/harbour.ts` and `iso-layout/harbour.test.ts`. No other file is
touched — three other waves were writing in this worktree while this ran
(`index.ts`, `scatter.ts`, `clearance.ts`, `paint.ts`, `ring.ts`,
`engine-canvas.tsx`, `blueprint.ts`, `dressing.ts`, `raster.py`), and none of
them is in this commit.

## The defect

The Captain's frame (`cabinet-meta/designs/defect-jetty-detached-from-shore-2026-07-27.png`):
a short timber jetty standing in open water with a clear strip of sea between it
and the beach. A pier connected to nothing.

`buildHarbour` carried compose.py:1148 verbatim — `quay.jetty(canvas, jx, js+52, …)`
— which roots the finger pier **52px below its own column's waterline**, i.e.
out on the water. The offline compositor gets away with it on the reference
island because a stone wharf happens to cover the gap. Nothing covers it here.

## Before — measured, not inferred

80 seeds (`org-0`..`org-79`), coastline step 2 (the step the renderer composes
at), three quay rungs × two eras = 480 harbours. `DETACHED` = the root is not on
land **and** no deck bridges it.

| case | harbours | jetties | root on land | deck covers root | drawn cap on land | end in water | DETACHED |
|---|---|---|---|---|---|---|---|
| camp / rowboat_jetty | 80 | 80 | 0 | 0 | 0 | 80 | **80** |
| camp / timber_jetty | 80 | 80 | 0 | 0 | 0 | 80 | **80** |
| camp / stone_quay_4 | 80 | 80 | 0 | 0 | 0 | 80 | **80** |
| hamlet / rowboat_jetty | 80 | 80 | 0 | 0 | 0 | 80 | **80** |
| hamlet / timber_jetty | 80 | 80 | 0 | 0 | 0 | 80 | **80** |
| hamlet / stone_quay_4 | 80 | 80 | 0 | 0 | 0 | 80 | **80** |

Systemic, not a seed: the root offset is a constant `+52` on every island, and
the open water above it measured exactly 52px on all 480. Not even the deepest
rung in the ladder rescues it — at `stone_quay_4` the deck's front edge sits at
`shoreY+46` and the root at `shoreY+52`, so the pier clears its own wharf by 6px.
The renderer strokes `at → end` with `cap: 'square'`, so the *drawn* planks begin
~21px further landward and still start 30px out to sea.

## The cause, in one line

`harbour.ts:406` (pre-fix) — `const jRoot: Point = { x: jx, y: js + 52 }`, where
`js` is that column's waterline: the root is placed 52px **seaward** of the shore
and nothing ever asked whether it was on land.

## After

Same sweep, same seeds, same harness, against the fixed module:

| case | jetties | root on land | deck covers root | drawn cap on land | end in water | DETACHED |
|---|---|---|---|---|---|---|
| camp / rowboat_jetty | 80 | **80** | 0 | 80 | 80 | **0** |
| camp / timber_jetty | 80 | **80** | 0 | 80 | 80 | **0** |
| camp / stone_quay_4 | 80 | **80** | 0 | 80 | 80 | **0** |
| hamlet / rowboat_jetty | 80 | **80** | 0 | 80 | 80 | **0** |
| hamlet / timber_jetty | 80 | **80** | 0 | 80 | 80 | **0** |
| hamlet / stone_quay_4 | 80 | **80** | **80** | 80 | 80 | **0** |

No pier was lost to the fix (80/80 still emitted in every case), the root offset
is now `-4` (SHORE_LIFT, the land side) on every seed, and land runs at least
200px inland above every root — the cap is on real ground, not a one-pixel spit.
At the deepest rung the root is now inside the deck it belongs to, which is what
`deck covers root` flipping to 80 says.

## What changed

1. **The root is the waterline, on the land side.** `jShore - SHORE_LIFT` — the
   same lift the deck's upper edge already uses, so the pier starts exactly where
   the wharf starts. One primitive, two callers, one definition.
2. **No shore, no pier.** A column with no land emits no jetty rather than a
   floating one, and `coast.landAt(root)` is *asked*, not assumed. A missing pier
   is honest; a floating pier is false about the org and about the island.
3. **The last guessed waterlines are gone.** `?? cove.y - 140` (jetty) and
   `?? cove.y - 160` (warehouse, harbourmaster) are replaced by `nearestShoreY()`,
   a MEASURED reading from the nearest sampled column. The module's own docstring
   flagged these as an open hole; it no longer has to.
4. **The floating furniture keeps its counts.** Moorings and the org's vessel
   hang off `waterBase`, which is the jetty column's waterline where it exists and
   the nearest measured one otherwise — a geometric accident in one column may
   not delete a count.
5. **The envelope lost the offset it was hiding.** `pierReach` was
   `52 + len*0.86`; the 52 was the root offset, so it left with it. The dock kit's
   own depth is now a named term (`kitReach`, read off the DOCK_KIT table, never
   off the emitted items) instead of being covered by that constant by accident.

## The arms, and the mutations that prove them

Baseline: 46 arms, 0 failures. Each mutation applied by script to an isolated
copy of the tree, the harbour suite run, the source restored from a byte copy
and re-run green.

| mutation | result |
|---|---|
| MH28 the reference's `+52` root restored (attachment disabled) | **RED 7** |
| MH29 `+52` root AND the on-land refusal removed = the exact pre-fix geometry | **RED 3** |
| MH30 guessed `?? cove.y-140` root restored AND the on-land refusal removed | **RED 1** |
| MH30a guessed root restored, on-land refusal KEPT | GREEN — reported below |

MH29 is the honest one for the new arm: it restores the defect exactly and the
arm fails on the assertion that names it — `expected false to be true` on
`landAt(root)`, `expected 52 to be -4` on the offset's sign, and `expected 1442
to be 1386` on the hand-built island. MH28 goes red more widely only because the
on-land guard then refuses to emit the pier at all.

**MH30a is stated because it came back GREEN.** Restoring the guessed root while
leaving the on-land refusal in place changes nothing observable: the guard
catches the guessed y too. So the sensor is the `landAt` check, not the null —
and the arm that would catch a *removed guard* is the one that matters. It is
MH30, and it is red.

Three arms carry it:

- **`roots on land and ends in open water, at every era and every rung`** — root
  on land, the renderer's square end-cap on land, far end in water, across 30
  seeds × 3 states (hamlet full port, camp at the top rung, camp at the first
  rung). Both eras on purpose: the era that shows the defect worst is the one
  that decks nothing.
- **`roots at a fixed offset from ITS column, on the land side of it`** — the
  offset is identical on every island while the absolute y moves >40px, and the
  SIGN is asserted. The old arm asserted only "fixed", and `+52` is just as fixed
  as `-4`: that is how the floating pier survived four adversarial rounds.
- **`refuses to root a pier in a column with no land, and keeps what floats`** —
  on a hand-built island, because no seeded fixture reaches this branch
  (`buildHarbour` returns null before a cove is that ruined). The stub throws on
  every method `buildHarbour` should not need, so it cannot answer a question it
  was never given an answer for.

## Two arms that were pinning the defect in place

Both are in the deleted half of the diff, and both are the reason twelve green
checks and four adversarial rounds missed this:

- `leaves the shore and ends in open water` asserted
  `expect(j.at.y).toBeGreaterThan(rootShore)` — *the root is BELOW its column's
  waterline: on the water, at the deck*. The suite was asserting the defect.
- `roots at a fixed offset from ITS column` asserted `expect(offsets[0]).toBe(52)`
  — a fixture encoding the broken contract as the expected value.

## Rendered evidence

`cabinet/scripts/world-capture/capture.py --state hamlet` (quay rung
`timber_jetty`, the rung in the Captain's frame), run against both trees:

- before: `jetty at [1304, 1321] → [1328, 1448]`, a plank stack in open water
  with a band of sea between it and the deck.
- after: `jetty at [1304, 1265] → [1328, 1392]`, its landward end on the deck and
  the shore behind it.
- **both render GREEN on all twelve `world_checks.py` invariants**, and camp does
  too. The harness cannot see this defect: `on_road`, `terrain`, `depth_order`
  and `state_traceable` are all satisfied by a pier in open sea. Only an eye or
  the arm above catches it.

A side-by-side crop of the two ground layers is at
`cabinet-meta/designs/fix-jetty-attached-2026-07-27.png`.

## Gates

Run on a scratch clone of HEAD `f655bc5b` plus this unit only — the live worktree
could not be used, because another wave's in-flight `index.ts` has
`ctx.districts` undefined and `composeLayout` throws for everyone.

| gate | result |
|---|---|
| `npx vitest run src/lib/world/iso-layout/harbour.test.ts` | 46 passed |
| `npx vitest run` (whole dashboard suite) | 132 files, **2559 passed**, 1 skipped, 0 failed |
| `npx tsc --noEmit` | exit 0 |
| `capture.py --state camp` / `--state hamlet` | GREEN 12/12 both |

## Still open, stated rather than implied

- **Nothing in `auditLayout` senses this.** The harbour's layout-level audit asks
  "is it inside the envelope", which a floating pier passes. The right home for
  an "every pier roots on land" arm is `index.ts`'s audit, and `index.ts` is
  being rewritten by another wave right now — so the invariant lives in
  `harbour.ts` (the code refuses to emit) and in this suite, and the audit arm is
  left for whoever lands next in that file.
- **The renderer needed no change.** `engine-canvas.tsx` strokes `at → end` with
  a square cap and `raster.py` calls `quay.jetty(at)`; both were drawing the
  geometry they were given. Neither is touched.
- **The pier's seaward end moved 56px landward** with the root, because `length`
  still means what the quay rung says. Measured: still over water on 480/480, and
  the org's vessel still floats on all of them.
- **`nearestShoreY` is exercised only by the hand-built fixture.** On real seeds
  every fallback branch is unreached (0 of 300 measured at cp4, unchanged), which
  is why the fixture exists at all.
