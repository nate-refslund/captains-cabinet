# Checkpoint review — iso-layout cp4: the harbour and the lighthouse

Branch `iso-port-composition`, on top of `6de522e6`. This artifact covers ONE
unit of the composition port: `harbour.ts` (new), `harbour.test.ts` (new), the
`cove` field on `Coastline`, and the wiring in `index.ts` that hangs the
harbour, the lighthouse and the region extents off `composeLayout`.

A second wave was writing in the same worktree at the same time (the ground
paint extraction into `paint.ts` and the forest enclosure ring in `ring.ts`,
with their own `planting.test.ts`). Where this artifact quotes a whole-suite
number it is measuring the merged tree, and it says so; every measurement
attributed to this unit was produced against `harbour.test.ts` alone.

## What was missing, and what is here now

The armature port had no harbour and no lighthouse at all: the two places the
world tells its most important state — how much the org has shipped, and whether
a trust cell has ever graduated — were absent from the layout. Also open from
cp3 were the region extents `checks/world_checks.py` reads.

| deliverable | where | reference |
|---|---|---|
| the wharf, shore-attached, drawn as one surface | `harbour.ts` `shoreLine` / `Wharf` | compose.py:1126-1142, quay.py |
| the finger jetty, length following the quay rung | `harbour.ts` `Jetty` | compose.py:1144-1153 |
| moorings, one per open outcome window | `harbour.ts` `moorings` | compose.py:1149-1152 |
| cargo following completed work items | `harbour.ts` `DOCK_KIT` | compose.py:1178-1191 |
| warehouse + harbourmaster on land above the wharf | `index.ts` quayside `put` | compose.py:1165-1176 |
| crane gated on the pack count | `harbour.ts` `cranes` | compose.py:1180-1182, morphology.yml:178 |
| the lighthouse, sited by walking the coast | `harbour.ts` `lighthouseSite` | compose.py:891-897 |
| the lamp and `LAMP_AT` | `harbour.ts` `LighthouseLamp` | compose.py:1198-1205 |
| plaza / field / quay extents | `index.ts` `Regions` | compose.py:1373-1378 |

## Eight places this port does NOT do what the reference does

Each is a divergence with a reason, not an omission.

1. **A camp has no wharf** — `quayDepth()` returns 0 at camp whatever the quay
   rung says. The reference has no era gate here; it gets the right answer only
   because a real camp's rung happens to be `rowboat_jetty`. A deck is a built
   surface, and the era is the axis that says whether the org builds surfaces.
   The rung is NOT hidden: it goes on driving the jetty's length at every era,
   so a camp that has shipped for a year shows it as a longer pier over the
   water. Both halves are pinned (mutation MH1, and the arm "leaves the rung
   visible at camp through the jetty length").

2. **No cargo when nothing has been completed.** compose.py:1188 computes
   `max(1, 1 + n*3)`, so it lays a crate on the wharf of an org that has
   completed nothing — a sprite with no rule behind it, which is the whole
   subject of `check_state_traceable`. Dropped to `n*3`.

3. **One crane per inherited pack, not one crane.** compose.py's comment says
   "one dockside crane per inherited extension pack" and its code places exactly
   one. `packs_inherited` is a census count (morphology.yml:178, "Harbor cranes
   — extension packs present", day-0 five). A count that renders as 1 whatever
   it says is era-hiding-a-count by another route. The number that does not fit
   the deck is REPORTED as `cranesRequested`, never silently lost — at the
   reference island the port asks for 5 and the deck holds 4.

4. **The quay rect covers the deck, not the whole cove shore.** compose.py:1376
   builds it from the full shore polyline even at the timber rung, where it
   decked only the middle 30% — so its exemption zone covers bare shore and
   every sprite standing there stops being judged by `check_on_road`. An
   exemption wider than the surface it exempts is a check turned down.

5. **A lamp needs a tower.** compose.py:1203 gates the lamp on the lighthouse
   SPRITE existing, and the unlit cairn is a sprite — so a graduated cell
   arriving before the tower is built draws a lamp floating over a pile of
   stones. Suppressed here, and the measurement survives: `lamp.rungLit` carries
   what state said even on the frame that cannot draw it.

6. **The clearing shrinks for a cairn.** The reference reserves 200px round the
   lighthouse flat. A 200px bald ring round a knee-high cairn is a mown circle
   around nothing — the same argument that era-gates the district discs.

7. **Only the org's own vessel is moored.** The reference draws a fishing boat,
   a rowboat, two buoys and two ducks alongside it. `harbor_boat` has a ladder;
   none of the others does. They belong to the renderer's ambient set if
   anywhere, not to a stage that claims everything it emits is measured.

8. **The region extents are the paint that was emitted**, not the authored
   constants. This port shrinks and drops blobs that would spill into the sea,
   so the reference's declared 300x190 square is not the square on any island —
   measured, the emitted plaza half-width is 176-191px across 30 seeds, never
   above 220. A hardcoded extent would tell `check_terrain` to sweep water for
   paving.

## The harbour's own invariant, and why the water arm could not be it

`auditLayout` re-measures "nothing stands on open water" for structures and
scatter. It cannot be the harbour's sensor: a mooring post is in the water by
construction and a crate stands on a deck that is over water. Growing an
exemption for them would be the standard way a real defect later gets waved
through, so the harbour carries a different question — is this in the HARBOUR? —
against an envelope built from the COVE AND THE SHORE ONLY.

That last clause is the whole of it. A box fitted around the items it checks
cannot fail, which is the defect class this directory has now been re-reviewed
for three times. The arm that proves the envelope is independent is not the one
that checks containment (mutation MH19 leaves that green); it is the one that
holds the seed and the quay rung fixed, moves every count, and requires the
envelope not to move by a pixel.

## Two arms that were too weak on first writing

Reported because the point of the battery is that it finds these.

- **The jetty arm.** "Leaves the shore and ends in open water" stayed GREEN when
  the root's y was taken from the cove's centre instead of the jetty's own
  column (MH4) — the cove centre is deep, so both versions put the root below
  the shore and the end in water. The discriminator is how the number RESPONDS
  to the island: the offset from its own column is 52px on every seed while the
  absolute y moves 40px+. Both are asserted now, and the cranes gained the same
  arm (each on its own column, 42px down, and the columns must disagree).
- **The field-extent arm.** Containment of the blob centres passes over the
  authored `(w+60, h+40)` box, exactly as it did for the plaza. Both now assert
  the extent EQUALS the emitted blobs' bounds to six decimal places.

## Mutations — 27, every one proven able to fail

Each applied by script to an isolated copy of the tree, the harbour suite run,
the sources restored from a byte copy. Baseline 43 arms, 0 failures.

| mutation | result |
|---|---|
| MH1 camp gate removed from `quayDepth` | RED 3 |
| MH2 `QUAY_SPAN` ignored (always the full cove) | RED 1 |
| MH3 wharf rect from the FULL shore (the reference's loose zone) | RED 1 |
| MH4 jetty root y from the cove centre, not its own column | RED 1 *(GREEN before the arm above was rewritten)* |
| MH5 dock kit y from ONE shared waterline | RED 1 |
| MH6 the reference's `max(1, 1 + cargo*3)` restored | RED 3 |
| MH7 moorings hardcoded to 2 | RED 3 |
| MH8 crane count forced to 1 (the reference's own code) | RED 1 |
| MH9 crane deck gate removed | RED 1 |
| MH10 cranes heaped on one spot | RED 1 |
| MH11 lighthouse sited by a hardcoded bearing | RED 1 |
| MH12 lighthouse clearing dropped from the districts | RED 1 |
| MH13 the lamp's tower term dropped | RED 1 |
| MH14 the lamp glows at the foot of the tower | RED 1 |
| MH15 plaza extent emitted as the authored constant | RED 1 |
| MH16 field extents emitted as the authored plot constants | RED 1 *(GREEN before that arm was rewritten)* |
| MH17 `onQuay` dropped from `free()` | RED 1 |
| MH18 `onQuay` dropped from `verge()` | RED 1 |
| MH19 harbour extent fitted around its own items | RED 1 *(GREEN before the independence arm existed)* |
| MH20 harbourmaster placed whatever the rung says | RED 2 |
| MH21 `shoreLine` substitutes a y for a landless column | RED 1 |
| MH22 `presentRung` treats every rung as built | RED 4 |
| MH23 warehouse count ignored (always one) | RED 2 |
| MH24 quayside buildings skip the structure door | RED 2 |
| MH25 `SHORE_LIFT` dropped (the deck edge straddles the waterline) | RED 3 |
| MH26 the org vessel drawn whatever the rung says | RED 5 |
| MH27 the ambient craft the reference draws, restored | RED 1 |

Three came back GREEN on the first pass — MH4, MH16, MH19 — and all three were
missing sensors rather than redundant rules. Each is described above and each is
RED against the arm that replaced it.

## Measurements

Hamlet, full working port (6 dwellings, 4 plots, 6 berths, cargo tier 2, 2
warehouses, 5 packs, `stone_quay_4`), 30 seeds, coastline step 8.

| | measured |
|---|---|
| seeds with no cove shore to build on | 0 |
| structures or scatter standing in the sea (`auditLayout.inWater`) | 0 |
| harbour items outside the harbour envelope | 0 |
| jetty ends on land | 0 |
| moorings on land | 0 |
| dock-kit items off their own column's waterline | 0 |
| warehouses below their column's waterline | 0 of 60 (max +2px, one raster cell) |
| lighthouses missing, or west of the cove | 0 |
| scatter standing on the wharf | 0 (was 8 with the term on `free()` only) |
| plaza extent wider than the authored 300px half-width | 0 of 30 |
| cranes emitted / requested at the reference island | 4 / 5 |

The wharf's `onQuay` planting term was found by measurement, not by reasoning:
adding it to `free()` alone left 8 verge items (5 shore rocks, 2 flowers, a
bush) standing on the deck, because the main street ends at the harbour head and
the verge band is 62-96px off a carriageway. Adding a term to one predicate and
calling the rule enforced is exactly how the paving leak survived its own arm at
cp3.

## Still open, stated rather than implied

- **The reference's harbour dressing is not ported**: the fishing boat, rowboat,
  buoys and ducks (deliberate — see divergence 7), and quay.py's plank/post
  drawing, which is the renderer's job and needs the geometry this unit now
  emits.
- **`lighthouseSite` walks columns east of the cove only.** On an island whose
  most seaward point is south-WEST it will pick a lesser point. That is the
  reference's own model (the compass layout puts the light on the south-east
  point) and every seed measured has land there, but it is a model, not a proof.
- **The `stacked` audit still reports one pair across 30 seeds**, unchanged from
  cp3 and unrelated to this unit: it is the crowded-shore lot separation
  residual that cp3 measured and documented.

## Gates

`npx tsc --noEmit` exit 0 · `npx vitest run src/lib/world/iso-layout/harbour.test.ts`
43 passed · `npx vitest run src/lib/world` 35 files, 568 passed · `npx vitest run`
(the CI job's own command) 123 files, 2361 passed, 1 skipped ·
`cabinet/scripts/check-layer-separation.sh` new=0 · purity grep over `harbour.ts`
and `harbour.test.ts` for `Math.random` / `Date.now` / `new Date(` / `require(` /
`process.` / `fetch(`: none. The whole-suite numbers are the MERGED tree —
this unit plus the ground-paint and forest-ring wave landing beside it. The live
checkout `/Users/nate/captains-cabinet` was never touched.
