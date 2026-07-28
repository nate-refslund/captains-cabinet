# iso-port-composition — checkpoint 6: repairing what the attack found

Branch `iso-port-composition`, on top of `c5b825a5`. The adversarial round that
produced cp4/cp5 fixed two defects itself (`2d53e1d7` the belt measuring the
wrong sprite, `c5b825a5` the barrel never re-exporting `./harbour`) and left
four residuals named but open. This checkpoint closes the ones that are defects,
declines the ones that are not, and — while re-measuring the declines — found
two more that nothing in the suite could see.

## Defects fixed

### 1. The harbour built a quay out of a ladder that was never measured

`compose.py:1134` reads `WS.stage("quay") or "rowboat_jetty"`, so an org whose
`quay` ladder is absent gets the ladder's FIRST RUNG built out of the absence:
a 96px finger pier standing in the water with no rule over `state` behind it.
The attack named this and rated it a faithful port of a reference hole.

It is not one this port may keep. The same module already refuses
`compose.py:1188`'s `max(1, 1 + cargo*3)` — a crate on the wharf of an org that
has completed nothing — on exactly this ground, and applying that standard to
cargo but not to the pier is the inconsistency, not the divergence.

A worse case sat next to it and nothing had looked: `quayDepth` fell through to
`QUAY_DEPTH[key] ?? QUAY_DEPTH_MAX`, and `bare_ground` is not in that table
either, so an UNBUILT quay was handed the deepest stone wharf in the ladder by
the "an unknown rung is more quay, never less" rule. That rule is right for a
rung past the TOP of the ladder and wrong for one below the bottom.

Root cause of both: the empty-rung set lived as a private const inside
`index.ts`, so `harbour.ts` could not ask the question at all. It is now
`space.ts`'s `EMPTY_RUNGS` / `emptyRung()`, imported by both.

- `quayDepth(era, rung)` and `jettyLength(rung)` answer 0 for an absent, null or
  empty rung, before the table is consulted.
- `Harbour.jetty` is `Jetty | null`; a length of 0 emits no pier rather than a
  degenerate one for the renderer to interpret.
- The boat and the moorings do NOT vanish with it. They have their own ladders,
  and a vessel with no pier lies at anchor: the seaward point is computed
  separately (`jEnd`, the pier's end or its root at length 0) so the pier's
  absence is not theirs.

### 2. The harbour's envelope did not reach its own mooring rows

Found while measuring fix 1. `extent`'s reach was `52 + jettyLength * 0.86` —
the pier's alone — while the mooring rows walk 52px further out per PAIR of open
outcome windows. Over 20 seeds at the top quay rung:

| berths | mooring posts outside the harbour's own envelope |
|---|---|
| 2, 6, 10 | 0 |
| 16 | 6 |
| 24 | 150 |

`auditLayout`'s `outsideHarbour` arm was reporting a defect that belonged to the
envelope. It survived because every fixture in the suite stopped at 6 berths,
which is the value the state happens to carry today; `count()` admits 64.

Both terms are now computed from INPUTS (the rung, the berth count), never from
the emitted positions — the distinction that keeps the envelope a live sensor
rather than a box fitted around what it checks.

### 3. Five of fifty `DEFAULT_FOOTPRINTS` rows contradicted their own provenance

The table claims to be `manifest.py`'s generated size divided by `scale_of()`.
Audited row by row against `manifest.py`:

| kind | was | manifest.py | in HALF | correct |
|---|---|---|---|---|
| `tree_birch` | 150x150 | 125x165 | no | 125x165 |
| `tree_willow` | 150x150 | 155x155 | no | 155x155 |
| `rock_cluster` | 47x45 | 105x95 | yes | 52x47 |
| `fallen_log` | 47x45 | 120x95 | yes | 60x47 |
| `mushrooms` | 47x45 | 90x90 | yes | 45x45 |

The other 45 rows check out. Every spacing number this library enforces — belt
separation, ground overlap, lane clearance — is measured against these, so a
wrong row is a rule enforcing the wrong distance and reporting that it did.

### 4. The belt had no wharf term (a rule added with a GREEN mutation — read on)

`plant()` carries `onQuay`; `forestRing` did not, and the belt is the pass that
walks the coastal band where the deck is. Added, and reported honestly below:
its mutation is green at the composed level.

## Claim-surface corrections — no behaviour change

- **`RING_SPACING` was not the reference's belt rule.** `compose.py:941` does
  `reserve(x, y, 30)` after each belt tree, but `_DISTRICTS` — the list
  `clear_of_districts` reads — is snapshotted at `:915`, BEFORE the ring loop.
  The belt's own reservations are invisible to the belt; they are picked up by
  `AV = list(KEEPOUT)` at `:1211`, which gates the later meadow scatter. Using
  the number as the belt's admission rule is this port's repurposing, and the
  docstring called it the reference's spacing.
- **`RING_SPACING` barely does anything.** Composed hamlet belt, 20 seeds: 96.5
  items/island at 30px, 97.2 at 1px. It rejects 0.8 candidates an island. Anyone
  reaching for it to thicken the belt should know it has no room in it.
- **`Wharf.rect` is not the deck exactly.** It is the deck's x span with a 20px
  apron above and 60px below, which is what makes the exemption usable — and
  what it holds is measured: 223 quayside buildings across 80 village islands.
- **`ellipseOfRegion` is a superset of the paint** — 9.0% of the declared plaza
  and 3.5% of the average field is grass (worst island 15.1% / 17.7%). Stated,
  with the reasoning for not fixing it (see the declines).
- **"the reference draws 150-200"** deleted from the belt's count arm. It was an
  inherited figure with no measurement under it.

## The rejection budget — where the belt's size actually comes from

Measured over 20 composed hamlet islands, per island. This replaces "the belt is
thinner than the reference's, structurally" with a number per rule.

```
249.9 candidates    (4 layers x 360 degrees at a 4.4-7.2 degree step)
 -82.1  in a gap arc            } the REFERENCE'S OWN three terms,
 -47.4  inside a district       } with the reference's own constants
 -20.6  within 40px of a lane   }
  -3.5  everything THIS PORT added, in total:
           1.3 pool footprint on a lane      0.8 belt spacing
           0.7 pool ground taken             0.4 painted water/paving/quay
           0.3 chosen sprite's ground taken  0.0 chosen sprite on a lane
= 96.5 planted
```

The port's divergences — reject-instead-of-nudge, the extra surface terms,
planting after the structures rather than before — cost three and a half items
an island. The belt's density is set by numbers this port copied.

## The 80-seed acceptance sweep — committed tree, `sweep-0..79` x 3 states

Each metric measured with the predicate the RULE uses, not a re-derived one.
`village-no-quay-rung` is the same village state with the `quay` ladder removed.

| | camp | hamlet | village | village, no quay rung |
|---|---|---|---|---|
| structures / props in the sea | 0 | 0 | 0 | 0 |
| lots in the sea | 0 | 0 | 0 | 0 |
| lane points in open water | 0 | 0 | 0 | 0 |
| planting inside a keep-out disc | 0 | 0 | 0 | 0 |
| ring through a disc (k=0.62) | 0 | 0 | 0 | 0 |
| items on a lane | 0 | 0 | 0 | 0 |
| structures stacked | 0 | 0 | 0 | 0 |
| on the plaza or in a field | 0 | 0 | 0 | 0 |
| in the pond or the stream | 0 | 0 | 0 | 0 |
| planting on the wharf | 0 | 0 | 0 | 0 |
| outside the harbour envelope | 0 | 0 | 0 | 0 |
| scatter per island | 92-156 | 18-58 | 18-44 | 18-44 |
| ring per island | 117-157 | 71-124 | 65-124 | 65-124 |
| total planting per island | 221-304 | 96-182 | 88-167 | 88-167 |
| harbours / jetties / wharves | 80/80/0 | 80/80/80 | 80/80/80 | 80/**0**/**0** |
| lighthouses / lamps lit | 80/0 | 80/0 | 80/80 | 80/80 |

Camp has no wharf at the top quay rung (era gates the surface) and keeps its
96px pier (rung measures through it). With no quay ladder at all: no pier, no
deck, and the moorings, warehouses, harbourmaster and lighthouse all survive.

## Mutations — every new arm proven able to fail

| # | mutation | result |
|---|---|---|
| M1 | `jettyLength` without its `emptyRung` guard | RED — the no-rung arm |
| M2 | `quayDepth` without its `emptyRung` guard | RED — same arm (`bare_ground` -> 54) |
| M3 | `reach = pierReach` only | RED — 2 arms, the berth-count one and the envelope-independence one |
| M4 | ring drops `\|\| ctx.onQuay(x, y)` | RED — 20 belt items on the synthetic deck |
| M5 | both `itemSize` re-checks deleted (prior round's fix) | RED — 2 arms, still guarded |
| M6 | the five footprint rows reverted | RED — the provenance lock |
| M7 | ring drops `onQuay`, measured over the 240-island sweep | **GREEN** — reported, see below |

**M7 is green and stays.** Zero belt items land on the deck with the term or
without it, across 80 seeds x 3 states. The reason is a coincidence of two
unrelated constants: the wharf spans `cove.x +/- 360`, the reference's south gap
runs 58-122 degrees, and the wharf's east end lands at ~58.5 degrees — half a
degree inside a gap that exists to show the water at the harbour, not to keep
trees off a deck. Nothing links them. So the RULE is sensed directly instead: a
unit arm lays a synthetic deck across due north, which no gap covers, and the
belt drops 20 candidates onto it without the term. Unreached is not unreachable.

**M6 was green before this checkpoint.** Reverting all five footprint rows left
the entire suite passing — a missing sensor, not a redundant rule. The provenance
lock now added is a change-detector and says so; it cannot notice `manifest.py`
CHANGING, because that file is in another repository.

## Declined, with reasons

1. **No render, no consumer, no aesthetic judge.** `composeLayout` still has no
   caller outside its own tests, so "does it read as framing" is answered by a
   density profile and not by looking, and the >=7 judge has nothing to run on.
   NOT closed here: a renderer is a new surface of its own that would need its
   own review, and building more substrate for a stage with no delivery path is
   the failure this program has already paid for. It is the one open item that
   could still invalidate the southern-arc emptiness below.
2. **The belt is thinner than the reference's.** Quantified above instead of
   closed: the port's own rules cost 3.5 items an island out of ~250 candidates.
   The levers that remain — the gap arcs, the district radii, the angular step —
   are all the reference's own composition numbers, and changing them is a look
   decision that wants a render and the Captain's eye.
3. **~150 degrees of the southern arc carries little or no belt** (18-122 empty
   by the two declared gaps plus a 12-degree sliver, thin to ~168 where the
   coastal lane punches its own hole). Every arc of that is the reference's
   number. Worth the Captain seeing in a render before it is called correct.
4. **The region extents over-exempt by 9.0% / 3.5%.** Not fixed: the direction is
   safe for `check_terrain` (more grass in the denominator can only make it
   harder to pass), nothing this layout produces can hide in the difference (the
   plaza and every plot sit inside keep-out discs, and the structures near them
   go through `placeOnGround`, which refuses a lane outright), and the honest
   alternative is a per-island lattice search on the compose path. Recorded in
   the code with the condition that would make it worth doing.
5. **The jetty root's guessed-y fallback** (`?? cove.y - 140`) is still emitted as
   geometry rather than dropped. Unreached over 300 seeds because `buildHarbour`
   returns null below four land columns; stated in the docstring rather than
   denied by it. Left as-is: dropping the jetty on a fallback would delete the
   harbour's spine on a seed where the fallback is the only thing wrong.
6. **An org with no `quay` rung was getting a jetty** — this one is FIXED, see
   defect 1. It was listed as a decline-worthy faithful port; it is not.

## Suites

| | |
|---|---|
| `src/lib/world/iso-layout` | 164 passed (3 files) |
| `src/lib/world` (whole world suite) | 575 passed (35 files) |
| `tsc --noEmit` | clean |
