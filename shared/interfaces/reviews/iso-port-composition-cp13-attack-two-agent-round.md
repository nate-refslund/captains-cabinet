# cp13 — adversarial attack on the two-agent round (districts/feather/state-feed + the overgrown island)

Independent attack, fresh context, own measurements. Nothing below is quoted from either
author's report: every number was produced this session by a probe I wrote, and every
sensor I wrote carries a positive control that is reported alongside its green.

**Trees under attack**

| tree | sha | what it is |
|---|---|---|
| pre-round base | `f655bc5b` | before either agent |
| agent A | `d1cbe7c4` | districts gating + meadow feather + unmeasured-state |
| agent B (part) | `2b665d63` | timber deck + ground paint order (landed 18:01 mid-attack) |
| working tree | `2b665d63` + uncommitted | the clearing/overgrown-island model, **not committed** |

Harness: `node --import cabinet/scripts/world-capture/resolve-ts.mjs`, calling the SAME
`composeLayout` the suite and `emit.ts` call. 4 eras x 5 seeds = 20 composed islands
unless stated. `camp` and `hamlet` are the shipped fixtures verbatim; `town` and
`beyond_bay` were built the way `states/hamlet.json`'s own provenance note documents — a
REAL rung name of each ladder in `cabinet/world/growth-ladders.yml` at that era's end,
never a computed metric.

---

## 1. Did the two agents clash?

**No, and neither reverted the other.** Verified rather than assumed:

- `npx tsc --noEmit` → exit 0 at `2b665d63` + uncommitted.
- Full `npx vitest run` at the tip: see the bottom of this file.
- Agent A's feather survives inside agent B's ground-order rewrite: `PAINT_FEATHER` is
  still imported (`engine-canvas.tsx:60`), still read (`:1347`), still applied through
  ONE feathered alpha mask per region (`:1238` `featheredBlobMask`) with
  `setMask({channel:'alpha'})` (`:1186`), and still shipped in the draw list
  (`blueprint.ts:424,610`) and consumed offline (`raster.py:361-364`).
- Agent B's reorder claim — lanes under the paving — is TRUE against the mirror:
  `raster.py` lays pond `:374-383`, lanes `:385-388`, plaza `:391`, tillage `:402`,
  deck `:413-418`. The engine now matches.

**But agent B's layout work is still UNCOMMITTED** (`iso-layout/index.ts`,
`clearing.ts`, `clearance.ts`, `scatter.ts` + `clearing.test.ts` modified/untracked at
the time of writing) and `iso-layout/zz-probe.test.ts` is an untracked scratch file that
`console.log`s a table inside the suite. Everything below section 3 is measured against
that uncommitted tree.

---

## 2. Land honesty — PASS, with one PRE-EXISTING exception

20 islands. Sensors carry positive controls: `plaza-centre-reads-as-plaza = 1`,
`open-sea-reads-as-not-land = 1` (both fire).

| check | result |
|---|---|
| planting (scatter) in the sea | **0** |
| forest belt in the sea | **0** |
| lane centreline points in open water | **0** of 4,743 sampled run points |
| planting on the painted plaza | **0** |
| planting on the tilled plots (`crop`+`ploughed`) | **0** |
| planting in the pond/stream (excl. `lilypads`/`reeds`) | **0** |
| **structures in the sea** | **2** |

Inverting the planting density did NOT reintroduce any of the classes the brief warned
about. The one structure-in-the-sea is:

```
SEA cabinet-camp/beyond_bay:  structure warehouse role=warehouse @1057,1281
SEA cabinet-hamlet/beyond_bay: structure warehouse role=warehouse @1053,1289
```

**Attributed, not blamed:** byte-identical coordinates at `f655bc5b`, at `d1cbe7c4` and
in the working tree. **Pre-existing; neither agent caused it.**

Root cause: `clearance.ts:557` and `:562` — `placeOnGround`'s final land guard tests
`onLand(p.x, p.y - 2)`, a point 2px UP the screen, while the structure is recorded at
`p`. A quayside warehouse settled exactly on the waterline satisfies the guard at `y-2`
and stands in water at `y`. Neither shipped fixture reaches it (`camp` has no warehouse,
`hamlet`'s lands inland), so **the gate cannot see it** — the second concrete instance of
"the two shipped fixtures cannot express today", which agent A already logged as open.

---

## 3. Does the era separate visually? — PASS, 4.35x

My own canopy measurement (union of drawn canopy rects over land, 60,000 seeded samples
per island, `ring` + `scatter`, closed canopy-kind set):

| era | canopy fraction of land (5 seeds) | mean |
|---|---|---|
| camp | 0.8168 0.7766 0.8726 0.8344 0.8257 | **0.8252** |
| hamlet | 0.2728 0.2982 0.3006 0.2482 0.2591 | **0.2758** |
| town | 0.2260 0.2254 0.2441 0.2063 0.1954 | **0.2194** |
| beyond_bay | 0.1994 0.2151 0.2044 0.1804 0.1490 | **0.1896** |

**camp / beyond_bay = 4.35x**, monotone across all four eras, on every seed. Well past
the 2x bar. The model is not decorative. For contrast, `clearing.ts:16-18` records the
old model at 0.42 / 0.25 / 0.25 / 0.25 — three eras a viewer could not tell apart.

Cleared fraction of land moves the same way: camp 0.10, hamlet 0.61, town 0.78,
beyond_bay 0.88.

---

## 4. Is the clearing edge legible? — PARTIAL. Legible at camp, NOT at town/beyond_bay

Fraction of items standing within `RECORD_BAND` (84px) of a felled rim, pooled over
5 seeds, against two baselines:

| era | record items | within 84px | other scatter within | random land within | lift vs other scatter |
|---|---|---|---|---|---|
| camp | 66 | **100.0%** | 15.1% | 16.0% | **6.61x** |
| hamlet | 90 | **100.0%** | 60.4% | 74.6% | **1.66x** |
| town | 77 | **100.0%** | 82.6% | 81.8% | **1.21x** |
| beyond_bay | 43 | **100.0%** | 97.9% | 86.5% | **1.02x** |

Stumps and logs really do sit on the boundary — 100%, by construction, since the pass is
gated on `recordAt > 0`. What decays is the boundary's meaning: as the org matures the
clearings merge until 86.5% of ALL land is within 84px of some rim, so at `beyond_bay`
"on the rim" no longer distinguishes anything (1.02x). The Captain's picture — a raw
young camp, a settled old town — reads correctly at camp and hamlet and stops carrying
information above that. Not a defect in the placement; a limit of the readout, and the
per-kilo-rim statistic in `clearing.ts:484` is the right instrument for it.

---

## 5. DEFECT — the timber density gradient is DEAD. Every clearing is a stamped circle.

The strongest finding of this attack, and it contradicts three docstrings.

`index.ts:1540-1543` claims: *"the exclusion radius sits at TREE_SPACING_MIN there and
opens out to TREE_SPACING_MAX across each clearing's edge band — which is what makes a
clearing read as a thinning treeline rather than as a stamped circle."*
`clearing.ts:72-76` claims the density *"falls linearly to zero over this distance, so a
clearing has a thinning edge rather than a mown circle."*

**Neither can happen.** `clearedAt` (`clearing.ts:293-308`) returns a non-zero value only
strictly INSIDE a disc; `isCleared` (`:310-320`) returns true for exactly the same set;
and `free()` (`index.ts:1395-1400`) rejects every point where `isCleared` is true. The
set {density varies} and the set {a tree may be sampled} are **disjoint**.

Measured, 240,000 seeded samples of the tree pass's own admissible domain across 12
islands:

| seed | era | admissible pts | timber min | timber max | distinct values | effective radius |
|---|---|---|---|---|---|---|
| all 3 seeds | all 4 eras | 20,000 each | **1.0000** | **1.0000** | **1** | **72.0 .. 72.0** |

Behavioural proof, which is stronger than sampling. A SHA-256 fingerprint of every
`scatter` + `ring` item's kind and position across all 20 islands:

| mutation | fingerprint | verdict |
|---|---|---|
| baseline | `84a540e42b3aacf7b5106ba3` | — |
| `TREE_SPACING_MAX` 250 → 72 | `84a540e42b3aacf7b5106ba3` | **byte-identical** |
| shrub max 170 → 62 and the flower range collapsed to its single realised value | `84a540e42b3aacf7b5106ba3` | **byte-identical** |

`TREE_SPACING_MAX` (`index.ts:595`), the shrub range (`:1563`), the flower range
(`:1569`) and the ground range (`:1573`) have **zero effect on any composed island**.
The flower pass's inversion (`1 - timber*0.65`) evaluates to the constant 0.35
everywhere it is allowed to sample, so "light reaches the ground where the canopy has
been opened" is not implemented either.

`CLEARING_EDGE_BAND` is NOT wholly dead — it still moves the felling record through
`RECORD_SWALLOWED_AT` — but it does not do the job its own docstring names.

**GREEN MUTATION (reported, not buried):** `TREE_SPACING_MAX = 250 → 72` leaves
`iso-layout.test.ts`, `planting.test.ts`, `clearing.test.ts` and `dressing.test.ts` at
**147 passed, 0 failed**. Nothing guards the gradient.

The arm that looks like it does — `iso-layout.test.ts:710` *"and it THINS across the edge
band rather than stopping dead"* — is wired to `buildClearedGround` called directly on a
hand-written two-clearing list, and samples `timber(1000, 800)`, a point 200px inside a
250px clearing. In a composed island no pass can ever sample there. **The sensor is
wired to the helper, not to the live artifact.**

Fix direction (deliberately not applied here — see section 9): either make the timber
passes admissible on the outer part of a clearing so the ramp is reachable, or delete
the four dead ranges and the three docstrings that promise a treeline the code cannot
draw. The first is what the Captain's direction actually asks for.

---

## 6. DEFECT — objects still drawn outside the ground that was cut for them

Question 5 of the brief. The Captain found this class by eye as a lectern in open grass;
under the inverted model it has a sharper form: **a fixed-offset item standing in timber
nobody felled.** Dressing items whose base is on land and NOT on cleared ground, pooled
over 5 seeds:

| era | dressing on land | in uncut timber | % | kinds |
|---|---|---|---|---|
| camp | 0 | 0 | — | — |
| hamlet | 634 | **142** | **22.4%** | `fence_run`:110 `bush_flowering`:6 `windmill`:5 `water_trough`:5 `pens`:5 `bench`:5 `veg_garden`:3 `crate_single`:1 `market_stall`:1 `watermill_kiln`:1 |
| town | 656 | **83** | 12.7% | `fence_run`:82 `veg_garden`:1 |
| beyond_bay | 661 | **24** | 3.6% | `fence_run`:24 |

Root cause, and it is the same shape as the lectern: the furniture is authored at a fixed
offset from a compass anchor while the ground under it is now era-scaled.
`dressing.ts:549` and `:558` run the field fences from `FLD.x - 320` to `FLD.x + 352`,
while the `field_terrace` civic clearing is `r = 300 * CIVIC_ERA_SCALE[era]`
(`index.ts` CIVIC_CLEARINGS x `clearing.ts:129-134`) = **174px at hamlet**. The fence
runs ~150px past the cut and into standing wood. `windmill`, `water_trough`, `pens`,
`bench`, `veg_garden`, `market_stall` and `watermill_kiln` fail the same way at their own
offsets.

This is the era-scaling that section 3's separation depends on, so the answer is not to
drop it: it is that a district's clearing must cover the furniture the district draws, or
the furniture must be measured off the clearing the way agent A already fixed the law
ledger (`dressing.ts:478`).

---

## 7. DEFECT — "no tree at a wall" is asserted by a sensor that cannot see the belt

`index.ts:611-613` claims: *"The unit arm measures tree-against-structure overlap across
the composed islands and holds it at zero, which is the sensor for that claim rather than
the argument for it."*

Measured across 20 islands, worst ground-diamond overlap between a structure and any
planted item:

| tree | hits > 0.04 | worst overlap |
|---|---|---|
| `d1cbe7c4` (before the clearing model) | 16 | 0.1312 |
| working tree (after) | **27** | 0.1310 |

**All 27 are `ring` items**, e.g. `tree_oak` sharing **13.1%** of `officer_house_c`'s
ground diamond at `cabinet-hamlet/town` @457,906; `tree_pine` at 12.7% of `cottage_a`;
`tree_oak` at 13.0% of `officer_house_a`.

The arm named — `iso-layout.test.ts:1394` *"the great house keeps its ground"* — filters
`l.scatter` and never reads `l.ring`. The strict book (`strictOccupied: ctx.builtGround`)
is passed only inside `plant()`; `forestRing()` never receives it. So the claim is
checked against the one population that cannot violate it.

The class is pre-existing, but the count rose 16 → 27 (+69%) in this round, consistent
with `CIVIC_CLEARINGS` dropping the great-house disc, the memory lot and the six authored
dwelling discs: those were what previously held the belt off the houses.

**Mutation evidence:** removing `strictOccupied` from the timber passes DOES turn
`iso-layout.test.ts:1394` red, so the scatter half is genuinely guarded. It is the belt
half that has no sensor.

---

## 8. Mutation results — three GREEN, reported not buried

Run against a sandbox copy of the working tree (`/tmp/atk-work`, node_modules symlinked),
over `src/lib/world/iso-layout/`, `iso-scene.test.ts`, `iso-quay.test.ts`,
`unmeasured-state.test.ts`.

| # | mutation | arms red | verdict |
|---|---|---|---|
| A | `CLEARING_EDGE_BAND` 96 → 1 | 4 | fires |
| B | `TREE_SPACING_MAX` 250 → 72 | **0 of 147** | **GREEN — section 5** |
| C | shrub/flower ranges collapsed | fingerprint identical | **GREEN — section 5** |
| E | `CLEAR_PER_RUNG` 34 → 0 | 4 | fires |
| F | timber passes lose `strictOccupied` | 1 | fires (but see section 7) |
| G | `CIVIC_ERA_SCALE` flattened to 1 | 4 | fires |
| H | the chosen-sprite re-test (`scatter.ts:244` `sizeOf` filter) removed | **0 of 222** | **GREEN** |
| A1 | `consequence_ledger` back to a fixed `LAW.x + 104` | 1 | fires — agent A's fix is real |
| A2 | the unmeasured-state announcement wrapped in `if (false && …)` | **0 of 4** | **GREEN** |

**H.** `scatter.ts:98-116` justifies the chosen-sprite re-test with a measured incident
("sampled as a 60x47 log and drawn as a 47x45 stump, an item settled inside the great
house's ground diamond"). Deleting the filter today breaks nothing: the strict book now
covers that case, so the rule has no arm of its own and nothing would notice it going.

**A2.** `unmeasured-state.test.ts:79` is a source-text ratchet: it slices 800 chars after
`if (!p.resolution)` in `engine-canvas.tsx` and asserts the substring
`onIssues?.([UNMEASURED_STATE_ISSUE])` is present. Changing the inner guard to
`if (false && !isoUnmeasuredIssued)` — so the badge is never raised on any frame — leaves
all 4 arms green. The file names the limitation honestly ("the wiring lives inside a
PixiJS closure that no unit test can enter"), so this is a known-shape hole rather than a
false claim; the specific gap worth writing down is that a **disabled conditional still
passes**.

---

## 9. Divergence agent B's own commit did not close: the quay has no pilings

`2b665d63` states iso-quay.ts exists to give "the engine the SAME deck the mirror draws".
It ports `quay.deck_strip` and `quay.jetty`. It does not port `quay.posts`, and it does
not port the jetty's own side pilings (`quay.py:92-97`).

`raster.py:418` calls `quay.posts(pts, depth, step=64)` on every wharf. Measured on the
fresh hamlet capture: the still renderer draws **3 wharf pilings** (shore x 1092..1296)
and **6 jetty side pilings** (length 129, step 46, both sides) that `/world?iso=1` does
not. `grep -n "post" cabinet/dashboard/src/lib/world/iso-quay.ts` → no matches.

---

## 10. What I deliberately did NOT do

Agent B's layout work was uncommitted and that agent was still writing during this attack
(it landed `2b665d63` at 18:01, mid-run, and its message forward-references a "cp12"
review artifact — hence this file is cp13). I made no edit to `index.ts`, `clearing.ts`,
`scatter.ts`, `clearance.ts`, `dressing.ts` or any test file: a second writer in a
checkout another agent is mid-edit in is how work gets destroyed, and the fixes in
sections 5, 6, 7 and 9 all belong to files that agent still holds. This artifact is the
whole of my write.

## Verdict

**STILL_BLOCKED.** The direction is correctly implemented in the large — the island is
overgrown, growth is subtractive, the eras separate 4.35x, and the land rules survived
the inversion. Four things are open: the timber gradient does not exist (5), district
furniture stands in uncut wood (6), the belt is unguarded against structures (7), and the
quay has no pilings (9). Two green mutations (B/C and H) and one on agent A's committed
tree (A2).

## Batteries, this session, against the tip + uncommitted tree

- `npx tsc --noEmit` → **exit 0**
- `npx vitest run` (whole dashboard, at `2b665d63` + uncommitted) → **137 passed | 1
  skipped (138) files; 2600 passed | 1 skipped (2601) tests**. The skip is the
  pre-existing live memory-search smoke that needs a real store. Same totals as the run
  at `d1cbe7c4`, so agent B's commit landed without moving the suite.
- `python3.12 cabinet/scripts/world-capture/sync-checks.py --check` → **4/4 mirrored files identical**
- `capture.py --state camp` → **GREEN 12/12, 0 surfaces unchecked**
- `capture.py --state hamlet` → **GREEN 12/12, 1 surface unchecked** (era vocabulary; no
  floor exists above hamlet)
- `python3.12 ~/cabinet-meta/checks/verify.py` run directly on both fresh captures →
  **GREEN 12/12** camp, **GREEN 12/12** hamlet, exit 0 both
