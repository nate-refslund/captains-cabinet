# cp14 — repairing what the two-agent attack found

Branch `iso-port-composition`. Repairs every DEFECT and the one pre-existing
hole in `iso-port-composition-cp13-attack-two-agent-round.md`, plus the three
mutations that round reported GREEN. Everything below was measured this session
on this tree; the commands are named where the number came from one.

## What the attack found, and what happened to it

| cp13 finding | verdict | where |
|---|---|---|
| §5 the timber gradient does not exist | FIXED | `clearing.ts` `timberAt`, `CLEARING_EDGE_BAND` |
| §6 furniture outside its cut ground | FIXED | `index.ts` `dressSettle`, `FURNITURE_MAX_TIMBER` |
| §7 the belt is unguarded against structures | FIXED | `ring.ts` `RING_BUILT_OVERLAP` |
| §8 the quay has no pilings | FIXED | `iso-quay.ts` `wharfPostRects` / `jettyPostRects` |
| §2 two structures in the sea (pre-existing) | FIXED | `clearance.ts` `walkInland` / `placeOnGround` |
| §9 `TREE_SPACING_MAX` 250→72 green on 147 arms | ARMED | "the wood THINS toward a clearing" |
| §9 chosen-sprite re-test deleted, green on 222 | ARMED | "an item whose DRAWN sprite fails a rule" |
| §9 unmeasured announcement `if (false && …)` green on 4 | ARMED | `unmeasuredIssues` + a tighter ratchet |
| §4 the clearing edge stops being legible at beyond_bay | NOT FIXED — see below |
| the untracked `zz-probe.test.ts` scratch file | DELETED, never committed |

## 1. The treeline was on the wrong side of the rim

`CLEARING_EDGE_BAND` ran INWARD from a clearing's rim, and the planting
predicate refuses every point inside a clearing (`free()` → `!isCleared`), so
the band was on ground the tree pass can never sample. Measured before the fix,
over the tree pass's own admissible domain on the composed islands:
`timber()` returned **one distinct value, 1.0000**, and the exclusion radius was
flat at `TREE_SPACING_MIN`.

`timber` is no longer `1 - clearedAt`. `clearedAt` still measures depth INTO cut
ground (its one consumer is the record's swallow test); `timber` now ramps from
0 at the rim to 1 one band width OUTSIDE it. Same domain, re-measured: **998 of
1000 sampled values distinct**.

The three arms that guarded this drove `buildClearedGround` on a hand-written
list. They are re-pointed, and a new arm measures the REALISED canopy —
scatter-only canopy per unit of plantable area, inside vs beyond one band width
of the nearest rim, pooled over 8 camp islands:

| | control | `TREE_SPACING_MAX` 250→72 |
|---|---|---|
| near-rim | 40/32741 = 0.00122 | 137/32741 = 0.00418 |
| beyond | 628/136764 = 0.00459 | 640/136764 = 0.00468 |
| ratio | **3.76** | **1.12** |

The bar is 2.0. The first version of this arm folded `l.ring` in and the
mutation stayed GREEN — the belt does not read a density field at all, so it was
a sensor wired to something other than its control. Caught on the arm's first
mutation run and recorded in the arm.

Era canopy coverage after the change (8 seeds, `canopyCoverage`):
camp 0.7468 · hamlet 0.3472 · town 0.2585 · beyond_bay 0.2213 — monotone,
camp/beyond_bay = 3.37x. Canopy sprite counts re-measured and the stale
docstring claim (430-500 / 300-360) corrected to 180-231 / 53-96.

## 2. Village furniture now stands on ground somebody cut

Measured before the rule, 20 hamlet islands: **648** pieces of village furniture
in standing timber, **129** of them under fully closed canopy, worst **188px**
past the nearest rim. Kinds: `fence_run` 540, `bush_flowering` 22,
`market_stall` 19, `water_trough` 19, `bench` 17, `chicken` 16, `veg_garden` 13.

Two changes. The clearing stage moved from step 9 to step **8a** — before the
dressing rather than after it; its inputs are the paint, the harbour, the
structures and the lighthouse, never the dressing. And `dressSettle` refuses a
`village_life` spot whose ground is more wood than clearing.

The bar is `FURNITURE_MAX_TIMBER = 0.5`, the treeline's midpoint, NOT the rim.
The hard rim was tried first and deleted the observatory bench for standing
**0.1px** outside its district, taking the market stall and the law ledger with
it — three authored civic props, and three red arms that were right.

The count-gated outbuildings (windmill, kiln, coop) cannot be dropped — each is
a measured count — so they now cut their own clearing at 8a, from the same
exported offsets the dressing places from. After: **0 items** in more-wood-than-
clearing at every era, no exemptions, and the furniture GREW with the era
(1568 → 1944 → 2095 placed items at hamlet/town/beyond_bay).

## 3. The belt was holding buildings to the tree-vs-tree bar

`forestRing` called `groundTaken(at, size, ctx.occupied)` at the 0.16 default.
At that call site `ctx.occupied` contains nothing but built ground. Measured:
**27 belt-vs-structure pairs over 0.04, worst 0.131**. `RING_BUILT_OVERLAP =
0.04` is the bar the rest of the library already uses against a building. Cost
~1 item per island. New arm reads BOTH populations; 0 over 3 eras × 5 seeds,
7000+ trees checked.

## 4. Two warehouses in the sea

`placeOnGround` closed with `onLand(p.x, p.y - 2)` and returned `p`.
`baseOnLand` — "requiring BOTH removes the band" — already existed and the ring
searches already used it; `walkInland` did not. Both ends now ask the same
question, so the rule RESCUES (walks inland) rather than deletes. Making only
the closing test stricter dropped a warehouse and the whole lighthouse: 2 red
arms, and that is why the walk had to move too.

## 5. The quay's pilings

`raster.py:418` has called `quay.posts` since it was written; the engine drew
only the deck. `wharfPostRects` and `jettyPostRects` port quay.py:68 and :93-97,
emitted separately from the deck so the deck's own arms keep measuring the deck.
`POST_COLOURS` is its own material set: the pilings stand against the water.

## 6. Mutations run this session

| mutation | arm that went red |
|---|---|
| `TREE_SPACING_MAX` 250→72 | the wood THINS toward a clearing |
| chosen-sprite `items.filter` deleted | an item whose DRAWN sprite fails a rule |
| `if (false && unmeasured.length > 0)` | the canvas RAISES it on the issues channel |
| `unmeasuredIssues` always `[]` | the DECISION to announce is a function |
| belt back to `groundTaken` default | NEITHER population of trees shares a building's ground |
| furniture cut-ground gate removed | no village furniture stands in ground that is more wood |
| land rule back to the stem row only | placeOnGround refuses a spot whose OWN row is water |
| `POST_DROP` 8 → −40 | the wharf stands on pilings, and they hang BELOW the deck |
| jetty legs moved to the pier's middle | the finger pier walks out on pairs of pilings |
| engine stops calling the piling functions | the engine draws the pilings the offline still already drew |

Ten mutations, ten red arms. No mutation this round came back green.

## 7. NOT FIXED, and why

**cp13 §4 — the clearing edge stops distinguishing anything at beyond_bay**
(record lift 6.61x at camp falling to 1.02x). `RECORD_BAND` is a fixed 84px
while the clearings multiply, so by beyond_bay 86.5% of all land is within 84px
of some rim and the rim is most of the island. That is a property of a mature
island rather than a broken rule: the record's DENSITY still falls correctly
(rawness falls with the rung, and `RECORD_SWALLOWED_AT` already suppresses arcs
that stopped being boundaries). Narrowing the band with the era would make the
lift number go up without making a frame better. Stated rather than fixed, and
the honest bound belongs with the metric.

**Not built at all, still.** The hit-test, the roof cutaway, characters and the
LIFE layer (the actor who fells the trees and then raises the cabin) are absent
under the flag. The Captain's direction is explicit that the felling sequence is
the LIFE layer and follows the hit-test and characters; this commit is the
static half.

## 8. Evidence

- `npx tsc --noEmit` — clean.
- `npx vitest run` — **2609 passed, 1 skipped, 136 files** (was 2599/1 at
  `102e45bd` plus the attacker's scratch probe).
- `capture.py --state camp` — GREEN 12/12, 0 surfaces unchecked, exit 0.
- `capture.py --state hamlet` — GREEN 12/12, 1 surface unchecked, exit 0.
- `sync-checks.py --check` — 4/4 mirrored files identical.
- Top-down pixel identity: canvas screenshot at 1600x1000, `?iso=0`, same
  camera and same live state, with `engine-canvas.tsx` at HEAD and at this tree
  — sha256 `e2ce9daa…` on both, byte-identical (546205 bytes).
- Captures (1600x1000, real engine, live feed):
  `~/cabinet-meta/.playwright-mcp/iso-camp-overgrown-island-zoom.png`,
  `…-close-zoom.png`, `iso-hamlet-today-island-zoom.png`, `…-close-zoom.png`.
  The camp pair is the era engine driven from a day-zero metrics basket
  (every metric at its floor) so the frame is the real engine at camp, not a
  fixture.
