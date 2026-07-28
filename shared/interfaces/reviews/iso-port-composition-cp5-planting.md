# iso-port-composition — checkpoint 5: the planting content

Branch `iso-port-composition`. Ported from `designs/world-mockup-v2/compose.py`:
the forest enclosure ring (:885-941), the broken meadow and value mottle
(:142-150, :378-386), the pond's outflow and bank (:153-174), and per-officer
house variety (:1067-1072).

The armature and the land-honesty rules were already done. What was missing was
CONTENT: enforcing the keep-out discs had removed the trees standing inside the
village and nothing added the ones that belong on the rim.

## What landed

| file | what |
|---|---|
| `iso-layout/ring.ts` (new) | the forest enclosure belt: four depth sublayers walked by angle, gapped at three arcs, planted after the structures and before the meadow scatter |
| `iso-layout/paint.ts` (new) | the whole ground-paint stage, extracted from `index.ts` and grown by four passes: broken meadow, outflow stream, pond bank, value mottle |
| `iso-layout/index.ts` | ring stage wired in; pond bank + lilypad planting passes; `Structure.role`; per-lot dwelling sprite; audit covers the ring |
| `iso-layout/planting.test.ts` (new) | 32 arms over the new content |
| `iso-layout/iso-layout.test.ts` | 7 existing arms restated where the new content made their old wording measure the wrong population |

`index.ts` and `iso-layout.test.ts` also carry a second unit's harbour and
lighthouse work (`harbour.ts`, `harbour.test.ts`, `coastline.ts`, review
artifact cp4), which was in flight in the same worktree and shares those two
files. It is committed here because the two cannot be separated without leaving
`index.ts` importing a module that is not in the tree. Both bodies of work are
green together, per-suite, below.

## Divergences from the reference, deliberate, each recorded in the code

1. **The belt plants after the structures, not before them.** compose.py runs
   the ring before it places the district buildings, protected only by the discs
   it reserved first — the defect its own comment at :907-909 records paying
   for, one level shallower. Planting after the structures means a tree can
   never take ground a measured building needs. The visible belt is the same:
   the discs already hold it 93px off every lot centre.
2. **A blocked belt tree is dropped, not nudged.** compose.py's `place()`
   shoves a crowded tree up to 30 times and draws it wherever it lands. The
   standing rule here is reject-at-sampling-time, so the belt instead takes the
   reference's OTHER number — its own `reserve(x, y, 30)` — as the admission
   rule. Holding it to the building-grade ground-diamond rule instead was
   measured: 35-75 items where the reference draws 150-200, with the depth
   sublayers largely cancelling each other.
3. **The belt also refuses painted water and paved surface**, which the
   reference's ring predicate omits. Not cosmetic: the innermost sublayer
   reaches the outflow stream on most seeds.
4. **The reference's third gap arc is mislabelled.** Its comment calls
   196-224 degrees "the west coastal lane"; that lane runs 126-167 and punches
   its own hole through the near-lane rule. The arcs are ported verbatim and
   described by what they measure.
5. **Houses are keyed on (world seed, lot key), not on `i % 6`.** Same
   stability, but each island gets its own row instead of every org on earth
   getting the same six in the same order. Era gates it: a camp pitches tents.

## Measurements, all run this session

Planting per island, 5 seeds, coastline step 8 (ring + meadow scatter):

| era | before | after |
|---|---|---|
| camp | 139-168 | 250-288 |
| hamlet | 41-68 | 112-163 |
| village (6 officers, 4 plots) | 36-59 | 112-147 |

The reference draws 173-206 per hamlet; this port is short of that and the gap
is honest — it excludes the harbour envelope, the lighthouse clearing and the
quayside discs, none of which the reference's ring stage knew about, and it
drops where the reference nudges.

Density from a keep-out disc's rim outward, village, 5 seeds, items per Mpx of
land in each band:

| band | before | after |
|---|---|---|
| inside the disc (<1.0 r) | 0 | 26.6 |
| the rim (1.0-1.2 r) | 137.5 | 195.2 |
| near (1.2-2.0 r) | 72.0 | 201.4 |
| beyond (>2.0 r) | 41.4 | 182.1 |

Before, the profile spiked at the rim and decayed to nothing — the previous
round called it "a hard edge with a pile-up on it", and that is what it was. It
now rises from the districts outward and stays dense all the way to the coast,
which is what framing looks like. The 26.6 inside the discs is the belt
crowding them at 62% of their radius, which is the reference's own rule.

## Mutation results — every arm proven to fail, and the three that did not

24 rules mutated one at a time, both suites re-run, source reverted. 21 came
back RED. The three GREEN results are reported rather than buried, because a
green mutation is either a missing sensor or a redundant rule and which one it
is matters.

RED: ring gap arcs · ring district keep-out · ring self-spacing · ring
water/paving · ring occupancy book · ring land test · ring not planted at all ·
broken meadow · value mottle · outflow stream · pond bank · masks not clipped ·
shading treated as surface · bank reeds · lilypads · lilypads not gated on
water · one sprite per lot · era not gating dwellings · houses keyed on index
not org · old rim-angle floor of 24 · both belt road terms (after the fix
below).

**GREEN 1 — the belt's two road terms, dropped together: a MISSING SENSOR.**
Every carriageway is inland of the radii the belt walks, so nothing on the real
network could catch it. Fixed by supplying the situation instead of waiting for
it: `planting.test.ts` now plants a belt against a synthetic lane laid along the
outermost sublayer's own radius and asserts the belt yields. All three road
mutations are RED against it now.

**GREEN 2 — `free()`'s water term in `index.ts`: a REDUNDANT rule, kept.** The
docstring predicted the outflow would make it live, and the mutation says
otherwise: delete it and all 164 arms stay green. The stream does reach outside
the pond's disc (20 blobs do on seed zeta), but it is 24-30px wide against
meadow passes that space at 58-104px, and the bank and lilypad passes have
already written the margin into the occupancy book. The docstring now states the
measurement instead of the prediction. The identical term in `ring.ts` is NOT
quiet — deleting it turns four arms red — because the belt walks at a fixed
angular step and does not care how narrow a river is.

**GREEN 3 — tying the blob probe step to the coastline raster: REDUNDANT,
kept.** With the rim-angle floor raised to 512 the rim is sub-pixel at every
radius any region uses, so following the raster only refines the interior
lattice and no arm distinguishes the two. Kept because the comment's claim has
to be true of the code rather than true today.

## A defect found on the way

`clipBlobToLand` bounded its rim-angle count from below with `max(24, ...)`,
which is the wrong end: a 24px blob got 31 angles, a 4.9px arc gap, against an
8px coastline raster — so a cell the rim clips at a corner fell between two
probes. It was invisible until the pond bank produced small blobs, and the
independent 90-angle probe in the existing extent arm caught it immediately.
The floor is now 512. The old comment also claimed the probe step was "finer
than the finest coastline raster this library will build"; it was not, since
production samples every 2px against a fixed probe of 5. Both are fixed and
both mutations are recorded above.

## Verification

- `npx tsc --noEmit` — clean.
- `npx vitest run` (whole dashboard) — 2362 passed, 1 skipped, 124 files.
- `npx vitest run src/lib/world` — 569 passed, 35 files.
- iso-layout + planting + harbour — 158 passed.
- Determinism ratchet (`ratchets.test.ts` arm 4) greps every file under
  `lib/world`, so `ring.ts` and `paint.ts` are in its scope: no `Math.random`,
  no `Date.now`, no IO, no DOM in either.
