# Checkpoint review — iso-layout cp3: re-attack of the cp2 fix round

Branch `iso-port-composition`, on top of `691e8631`. Diff ~494 LOC across 4
files under `cabinet/dashboard/src/lib/world/iso-layout/`.

This is an adversarial RE-review of cp2, which claimed three measured defects
fixed. Every number below is mine, produced this session by one probe run
against three trees — `1954df5d` (pre-fix), `691e8631` (cp2, as reviewed) and
this checkout — with the pre-fix and cp2 sources materialised side by side so
the probe is literally identical across all three.

## Verdict on cp2's three claims

Hamlet, 6 dwellings, 4 field plots, 80 seeds (`org-0..79`), coastline step 4.
Lane samples walked at 6px between stations, which is how
`checks/world_checks.py:check_terrain` walks them, with the same cove exemption.

| | 1954df5d | 691e8631 | this commit |
|---|---|---|---|
| seeds with a structure in the sea (base at y-2, the rule's own probe) | 5 | 0 | 0 |
| seeds with a structure in the sea (base at y) | 4 | **1** | 0 |
| seeds with a lot in the sea | 13 | 0 | 0 |
| seeds with a lane/drive sample in open water outside the cove | 37 (1311 samples) | 0 | 0 |
| scatter items inside a keep-out disc | 10197 / 13411 | 0 | 0 |
| items on the paved plaza | 97 | 0 | 0 |
| items in a tilled plot | 630 | **9** | 0 |
| items in the pond | 56 | 0 | 0 |
| seeds with a stacked structure pair | 0 | **1** | 0 |
| seeds under the 168px lot-separation rule | 0 | **40** | 6 |
| closest lot pair anywhere | 168.0px | **59.8px** | 67.2px |

At the production step (step 2, 24 seeds) the same three columns read: lots in
the sea 6 / 0 / 0; lane samples in water 14 seeds / 0 / 0; items in a plot
187 / 2 / 0; stacked pairs 0 / 1 / 0; seeds under the separation rule
0 / 14 / 3; closest pair 168.0 / 69.1 / 81.5px.

So cp2's three headline defects are genuinely gone and stayed gone. Three
things it introduced or missed are what this commit is:

**1. The lot snap undid the separation it runs after.** Every snap heads for
the same island centre, so neighbouring lots converge as they come inland and a
row relaxed to exactly 168px closes behind itself. On `org-13` that put two
officer dwellings on one patch of ground — `auditLayout` reported it and the
only stacking arm composed one seed, so nothing saw it. Fixed in `lots.ts` by a
repair pass that runs after the snap and is monotone (a move must strictly
increase the moving lot's distance to its nearest neighbour, so the closest pair
in the set can only go up) and land-preserving by construction (the destination
must be on land, so the land invariant survives a stage running after the snap
rather than depending on the snap being last). A first version had neither test
and was measurably *worse than doing nothing* — it oscillated between two
neighbours and stopped mid-swing at 8.7px against the 59.8px it started from.

**2. "Nothing is planted on the plaza or in a plot" was never a rule.** It was
carried incidentally by whichever keep-out disc happened to overlap the region,
and leaked wherever none did: 9 shore-band items standing in the east crop plot,
whose outer rim reaches past every disc. The arm named for the property ran five
seeds and passed over all nine. `free()` and the verge predicate now carry a
paving term (`paintField`), and the sweep arm runs 80 seeds.

**3. The residual stack was the road-wins fallback taking the FIRST shared
spot.** `clearOfLane` may fall back to occupied ground when nothing is clear —
"a slight stack beats a blocked lane" — but it took whichever the deterministic
ring met first, so two neighbouring lots took the same one. It now ranks by
shared ground, which is what that sentence already claimed.

## Four rules that were stated and had no sensor

Found by mutating rules the suite did not name and watching all 74 arms stay
green. Each is REACHABLE, measured, not theoretical:

| rule | file | reachability, measured |
|---|---|---|
| the blob clip's interior lattice | `index.ts` `blobOnLand` | deciding probe 13 times in 84,336 (rim, interior) evaluations, on the default island (org-1/org-3 ponds, org-2 ploughed, org-24 plaza) |
| `buildLanes` drops a lane with no on-land run | `lanes.ts` | 448 drops across the island radii this suite already composes; the drive era gate reads the surviving key set, so an empty husk puts a drive on a road that is not there |
| a drive with no on-land run is not emitted | `index.ts` | 293 unemitted drives over the same sweep |
| `auditLayout`'s water arm measures scatter | `index.ts` | quiet today (0 across 120 configurations) — but the negative twin injected a structure and never a scatter item, so half the arm was unsensored |

## Mutations

29 mutations, each applied to the source by script, whole iso-layout suite run,
sources restored from a byte-copy backup afterwards. The ten cp2 claimed all
reproduce exactly as it stated, including the one it reported green.

| mutation | result |
|---|---|
| M1 placeOnGround's land walk removed | RED 2 |
| M2 the lot snap removed | RED 2 |
| M3 district/lotFor anchor snap removed | RED 2 |
| M4 clipToLand neutered | RED 7 |
| M4b segment-level check removed | RED 1 |
| M5 blob clip reverted to centre-only | RED 4 |
| M6 keep-out disc term dropped from free() | RED 2 |
| M7 in_water term dropped from free()/verge() | **GREEN** — as cp2 disclosed; the pond lies inside its own disc |
| M8 drive era gate removed | RED 2 |
| M10 pond keep-out disc shrunk 190→60 | RED 1 |
| MX1 field plots era-gated | RED 1 |
| MX2 clipBlobToLand never drops | RED 6 |
| MX3 snapInland tests the point, not the margin | RED 1 |
| MX4 walkInland reach 0.45→1.0 | RED 1 |
| MX5 audit's structure water arm blinded | RED 1 |
| MX6 audit's scatter water arm blinded | RED 1 *(was GREEN before this commit)* |
| MX7 lane field interpolates across run gaps | RED 1 |
| MX8 blob interior lattice removed | RED 1 *(was GREEN)* |
| MX9 blob rim fixed at 24 angles | RED 1 |
| MX10 scatter drops its onLand check | RED 2 |
| MX11 buildLanes keeps a lane with no run | RED 1 *(was GREEN)* |
| MX12 a drive with no run is still emitted | RED 1 *(was GREEN)* |
| MY1 paving term dropped from free()/verge() | RED 1 |
| MY2 relaxOnLand removed | RED 1 |
| MY3 relaxOnLand's monotone test removed | RED 1 |
| MY4 relaxOnLand's land guard removed | RED 1 |
| MY5 relaxOnLand's second (bare-land) phase removed | RED 1 |
| MY6 clearOfLane fallback takes the first | RED 1 |
| MY7 paintField always false | RED 3 |

Two arms this session added were themselves too weak on first writing, and
saying so is the point:

- the separation arm asserted only a floor on the closest pair. Deleting the
  whole repair pass moves that number 64.2 → 67.2 and leaves the arm GREEN,
  because the defect is a *count*: 42 of 80 seeds under the rule against 5. The
  arm now asserts both, and the comment carries the four-row table showing which
  guard each number can and cannot see.
- the interior-lattice arm was written as a lagoon whose centre was water — so
  `blobOnLand`'s separate centre test refused it and the lattice stayed
  unmeasured. It is a moat now: land in the middle, a ring of water inside the
  blob, land all the way round the rim.

## Measured, reported, not fixed

- **The village core is bald at hamlet.** 67–79% of the island's land, and
  84–88% of the plantable inner band, is inside a keep-out disc, so growing an
  org from camp to hamlet takes its planting from 134–168 items to 38–67.
  Density by distance from the disc rim (5 seeds pooled, items per Mpx of land):
  0 inside, 138 at 1.0–1.2 rim radii, 73 at 1.2–2.0, 49 beyond. That is a hard
  edge with a pile-up on it, not deliberate framing. The exclusion itself is
  faithful — compose.py:899-914 reserves the same discs at the same radii — so
  the hole is the unported content that should fill it (the forest enclosure
  ring, the harbour, the district dressing), which cp2 already lists as open.
- **The main track no longer runs into the cove**: it ended at y=1355 pre-fix
  and now ends 2–16px inside the true land bottom in its own column, i.e. within
  one 16px station. That matches compose.py:343, which clips the road raster
  against the LAND mask (`land.point(v>120)`, no beach) — but the reference's
  blueprint still declares the lane into the cove, and `check_terrain` exempts
  the cove radius precisely so a harbour approach may leave the shore. Whoever
  emits the blueprint has to decide which of the two the `lanes` field is.
- **Three single-station lane runs** across 80 seeds (org-28/org-53 `coastal`,
  org-70 `drive-fields`): a 22–24px disc of road with nothing either side. Kept
  deliberately (`lanes.ts` argues the reference paints a disc at every station),
  noted because it will read as a puddle of dirt.
- **No network damage from the clip** at the reference island: 0 carriageways
  dropped, 0 drives orphaned from their road, 25 of 1520 lane instances cut into
  more than one run, `main` never cut.
- **The residual separation violations** (6 of 80 seeds, worst 67.2px) are a
  genuine conflict between land and separation on a crowded shore, not a bug.
  The pass improves as far as land allows and then stops; the arm pins both the
  floor and the count so neither can drift.

## Gates

`npx tsc --noEmit` exit 0 · `npx vitest run src/lib/world/iso-layout/iso-layout.test.ts`
83 passed (was 74) · `npx vitest run` (the CI job's own command) 121 files,
2287 passed, 1 skipped · `cabinet/scripts/check-layer-separation.sh` new=0.
The live checkout `/Users/nate/captains-cabinet` was never touched.
