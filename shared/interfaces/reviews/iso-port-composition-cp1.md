# Checkpoint review — iso-port-composition cp1

**Branch:** `iso-port-composition`
**Scope:** the offline compositor's LAYOUT stage, ported to TypeScript as pure
seeded functions (`cabinet/dashboard/src/lib/world/iso-layout/`), plus a
byte-identical copy of the parallel wave's `projection.ts`.
**Reviewer:** the builder, before push (self-review; does not replace an
independent pass — it removes the findings that would otherwise waste one).
**Verification run this session, in the worktree:**

- `npx tsc --noEmit` → clean.
- `npx vitest run src/lib/world/iso-layout` → 51 passed.
- `npx vitest run` (whole dashboard) → 121 files passed, 1 skipped;
  2255 tests passed, 1 skipped.
- `bash cabinet/scripts/check-layer-separation.sh` → `new=0`, OK.

---

## What landed

| File | Ported from | What it owns |
|---|---|---|
| `space.ts` (pre-existing, 2 edits) | — | the layout coordinate space; now re-exports the tile from `projection.ts` instead of re-typing it |
| `coastline.ts` | compose.py 48-121 | fbm island field over an ellipse, cove carved, blurred + thresholded; `landAt` / `landEdge` / `edgeAt` / shore + inner bands |
| `lanes.ts` | compose.py 185-236, 678-682 | the network; extent from era, width from the road rung; the lane occupancy field |
| `lots.ts` | compose.py 238-325 | `lotsAlong` / `lotFor` / separation at birth |
| `driveways.ts` | compose.py 291-307 | `isoRoute` — door to lane as an L on the two iso ground axes |
| `clearance.ts` | compose.py 417-506, 547-560 | the ground-diamond rules; road wins; drop rather than stack |
| `scatter.ts` | compose.py 604-682, 1217-1263 | Bridson Poisson-disk with the wildness density field |
| `index.ts` | the whole stage order | `composeLayout(state, seed)` + `auditLayout` |

Stage order enforced in `index.ts`: coastline → lanes → lots → driveways →
ground paint → structures → scatter. Driveways before paint is the load-bearing
one: a drive is paved surface AND part of the occupancy field every later rule
tests against.

---

## Deliberate divergences from the reference (each one, and why)

1. **Noise basis.** compose.py uses OpenSimplex; this uses a hashed value-noise
   lattice with a quintic fade. Porting OpenSimplex byte-for-byte would pin the
   mockup's exact pixels — an artefact of a Python library — where the ruling is
   about the KIND of coastline and the law is about the same seed always giving
   the same island. Both hold.
2. **A camp gets ONE lane, not two.** compose.py gates every lane but two on
   `hamlet_only`, so a camp still draws the main street AND the great-house
   forecourt spur — against its own stated rule (compose.py:205-207) of one worn
   track. The rule wins; the forecourt is a consequence of there being a house
   with a front.
3. **Lot separation is relaxed, not swept once.** The reference's single sweep
   pushes each new lot off every earlier one and never looks again — measured on
   the officer row, six lots, closest pair **95px against a 168px rule**. A
   bounded relaxation (12 rounds, fixed order) now converges to exactly 168.
4. **District keep-outs are era-gated.** A keep-out disc is not drawn but it IS
   visible — it makes a bald patch in the planting. Reserving the works ridge on
   an island with no works would mow a circle around nothing.
5. **The verge pass is village-only.** A verge is a road having sides worth
   dressing; a camp's worn track through grass has none.
6. **Per-region paint streams.** See finding 2 below.

---

## Findings from my own review, and what I did about them

Seven defects found in my own code after it first went green. All fixed in this
commit; each fix has an arm that was proven to fail against the pre-fix code.

1. **The audit carried a SECOND geometry.** `auditLayout` looked scatter sizes
   up in `DEFAULT_FOOTPRINTS`, so any caller passing real pack sizes through
   `footprintOf` would have been audited against different footprints from the
   ones the rules used — the exact defect class that cost this program three
   placement bugs. Fixed: `PlacedItem` carries the size the rules used, and the
   audit reads it.
2. **Org state reshaped morphology.** One shared rng stream for all paint
   regions meant the pond's shape depended on how many draws the FIELDS
   consumed — water moving because an org ploughed a field. Fixed: one seeded
   stream per region.
3. **The pond floated on the sea.** The reference clips the pond mask against
   the land mask; my first version emitted all 14 blobs whenever the centre
   happened to be on land. Fixed: per-blob clip, region dropped when nothing
   survives.
4. **The lane occupancy field had silent holes.** It is a union of discs built
   from `lane.path`; a `Lane` is a plain object anyone can construct, and a path
   sparser than the disc radius leaves gaps that every clearance rule then
   reports as clear road. Found by a test that passed a two-point polyline.
   Fixed: `buildLaneField` resamples to guarantee overlapping discs.
5. **The density field used the exact edge walk.** `wildnessField` called
   `landEdge` (a 6px raster walk) once per scatter candidate, where the
   reference memoises on a 0.02-rad key. Fixed: `coast.edgeAt`.
6. **Degenerate inputs.** `poissonScatter` with an empty kind set emitted points
   with `kind: undefined` (a point that draws nothing but holds occupancy);
   `polyPoint` on an empty polyline read `pts[0]`. Both now refuse.
7. **The tests only ever ran the coarse coastline.** Every arm used
   `step: 8` for speed — a test environment guaranteeing something production
   does not. Added an arm at the production default (`step: 2`) re-asserting the
   load-bearing invariants.

Two of my first-draft test arms were **vacuous** and are recorded here because
that is the failure mode worth naming: the pond-morphology arm compared
`undefined` with `undefined` on an island that had no pond, and a field-plot arm
compared a region emitted *before* the thing that could have perturbed it.
Both were caught by mutation testing, not by reading them.

---

## Mutation testing — every load-bearing arm proven to fail

Each rule was disabled in turn and the suite re-run. Restored and re-verified
green after each.

| Rule disabled | Arm that went red |
|---|---|
| `dropIfBlocked` ignored | decoration that cannot settle is DROPPED |
| lane clearance skipped | nothing in the composed layout stands on a lane (+1) |
| camp era gate off | a camp has exactly ONE lane (+1) |
| `isoRoute` → straight screen line | every leg runs on an iso ground axis (+1) |
| wildness flattened to a constant | density higher at the treeline (+1) |
| sampling-time rejection removed | a candidate whose ground is TAKEN is rejected |
| lot relaxation removed | no two lots are born on the same spot |
| one shared paint stream | the pond ignores the field count |
| audit falls back to the default table | the audit measures the caller's footprints |
| production coastline step forced coarse | invariants hold at the PRODUCTION step |
| `Math.random` added to a new file in the tree | ratchets arm 4 (proves the determinism ratchet reaches this directory) |

---

## Risks I am carrying forward, stated rather than buried

- **`projection.ts` is a byte-identical copy of an UNLANDED parallel wave.** It
  lives staged-but-uncommitted on the sibling `iso-port-projection` branch, and
  the brief requires using its `groundDiamond`/`groundBox`/`groundOverlap`
  rather than re-deriving a fourth notion of where a sprite stands. This branch
  cannot compile or be tested without the file, so it is committed here as an
  exact copy (verified with `diff`, no edits). If both branches land, an
  add/add merge of identical blobs resolves cleanly; if that wave edits the file
  first, the merge conflicts and **the resolution is to take theirs** — this
  branch consumes three stable functions and owns none of it. Whoever merges
  second should check that explicitly rather than assume.
- **Determinism has a boundary and it is now written down** (`space.ts`): within
  one JS engine the layout is bit-identical, which is what the tests pin; across
  engines it is identical to the precision of `sin`/`cos`/`atan2`, which are
  implementation-defined in the last ulp. The world renders in one runtime, so
  this costs nothing today — but an unstated boundary is how a claim becomes a
  lie later.
- **`DEFAULT_FOOTPRINTS` is a default, not the truth.** The sizes are measured
  from `designs/world-mockup-v2/manifest.py` (generated size ÷ `scale_of`). The
  renderer must pass the shipped pack's own sizes through `opts.footprintOf`; a
  layout computed against stale sizes puts the ground diamond in the wrong place.
- **Structures move off their compass anchor when the anchor sits on a lane.**
  The forecourt lane ENDS at the great house's anchor, so the great house is the
  routine case, not the exception (measured: ~110px west). This is the
  reference's behaviour and it is what "the road wins" means, but it is a visible
  consequence and the Captain should see it in a render before it is called
  settled. The alternative — ending the forecourt short of the door — leaves a
  100px gap between lane and doorstep, which is worse.
- **Not ported in this slice:** the quay/harbour deck, fences and hedgerows,
  frontage dressing, the forest enclosure ring, smoke, grading and depth sort.
  This is the LAYOUT stage as briefed; the render-side stages are separate.

---

## Verdict

Ship this checkpoint. The port is faithful where faithfulness is the point,
divergent only where the reference contradicted its own stated rule or where a
Python artefact would have been pinned as doctrine, and every layout invariant
the Captain's ruling names has an arm that has been shown to fail without it.
