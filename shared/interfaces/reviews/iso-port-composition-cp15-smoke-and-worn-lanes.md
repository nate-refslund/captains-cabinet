# Checkpoint review — iso-port-composition cp15: smoke and worn lanes

**Branch:** `iso-port-composition`
**Scope:** two Captain rulings of 2026-07-27 — smoke comes from the fire, not
the tent; and a path is worn by traffic, not switched on by an era.
**Reviewer:** the builder, before commit (self-review; it removes the findings
that would otherwise waste an independent pass, it does not replace one).
**Verification run this session, in this worktree:**

- `npx tsc --noEmit` → clean.
- `npx vitest run` (whole dashboard) → 136 files passed, 1 skipped;
  2625 tests passed, 1 skipped.
- `python3.12 -m pytest cabinet/scripts/world-capture/tests/` → 13 passed.
- `python3.12 cabinet/scripts/world-capture/sync-checks.py --check` → 4/4
  mirrored files identical.
- `capture.py --state camp` and `--state hamlet` → GREEN, 12/12 invariants,
  re-verified through `checks/verify.py` directly.

1439 changed lines across 21 files.

---

## 1. The smoke was bound to the ROLE, so a tent smoked

`blueprint.ts smokesOf` emitted a plume for every structure whose ROLE was
`officer_dwelling` or `great_house`, at every era. A role is era-agnostic: at
camp `officer_dwelling` draws `camp_tent`, so the hatch frame had a plume rising
out of canvas while the campfire three tiles away was cold. Measured on the
shipped camp fixture before the fix: exactly one smoke, at (839, 763) =
`camp_tent.x + w*0.18, camp_tent.y - h*0.92`.

The gate is now the FRAME, not the role. `SMOKE_FLUES` is a per-frame allowlist
carrying a measured flue offset, and absence is the hard default — the inverse
(a smokeless list) is open at the wrong end, and every new shed the pack ships
would smoke until someone remembered it. Every entry was read off the shipped
atlas by cropping the frame and looking at it; the omissions carry their reason
in place (`camp_log_cabin` has no chimney drawn on it; `cottage_a`'s topmost
feature is a roof ridge; `bay_workshop_hall` already draws its own smoke and a
second plume would be one fire counted twice). The sweep covers
`layout.dressing` as well as `layout.structures`, because the kiln is a fire
with a stack that happens to ride in the dressing list.

Four arms in `blueprint.test.ts`. The load-bearing one is POSITIONAL and never
reads `SMOKE_FLUES`: it names sprites whose art has no flue and asserts that no
plume starts inside their box. Asking "is every smoke's frame in the table?"
would be a tautology against the emitter that reads that table.

## 2. The road network was switched on by an era

`LaneSpec.villageOnly` skipped every district lane at camp and produced all nine
at hamlet in one keyframe. That is the largest pop-in on the frame and it
contradicts the world's own construction law in `cabinet/world/show-grammar.yml`.

A lane now exists when the place at its far end exists, and widens on that
place's own usage — the same ladder that grows the building there, whose rung
index the state already carries (`iso-scene.layoutStateFrom` writes
`trunc(el.rung)` into `counts` for every ladder, and era-engine computed that
rung as `clamp(floor(log2(v/base + 1)))`, so the log scaling a worn path needs
is the growth ladders' own and no second curve is invented at the roadside). The
org-wide road rung stops setting width and becomes the SURFACE instead: dirt /
worn dirt / gravel / cobble, which is what growth-ladders.yml already means by
"the egg's t0 dirt path, upgraded by real traffic volume".

`LaneEnd` has four cases because the island really has four kinds of
destination, and collapsing them would mean inventing a measurement for one:
`landing` (day zero, traffic still measured), `built` (exists on a ladder),
`district` (furniture but NO ladder anywhere in growth-ladders.yml — the dojo
and the crossroads, hairline forever) and `link` (the shore path, exists when
both ends do). Inventing a `dojo` metric to widen the NW lane would be the
market-stall defect one layer up; it stays at rung 0 and the code says why.

One divergence from the Captain's own table, stated because it is a divergence:
he lists the SE lane's metric as `ev_work_item_completed`, which in
growth-ladders.yml belongs to `cargo_stacks` (the harbour), not to anything at
the field terrace. The lane is bound to `outbuildings` — the ladder that
actually grows the place it leads to — which is his own stated principle ("the
SAME metric that grows the building") applied to the ladder file as it stands.

## 3. Four real defects the change exposed, and none relabelled

- **Flush is not clear (`LANE_KERB`).** The settle stopped at the first spot
  where the ground diamond and the lane discs did not intersect — which can be
  one pixel. Survivable only because wide lanes pushed hard. At 13px the great
  house came to rest on its own junction and `check_on_road` named it. The check
  probes a ground BOX at fx ±0.5 against a 3px mask; this library probes a
  DIAMOND at ±0.55 with no quantisation. Neither is wrong; a thing settled
  inside their disagreement is a coin toss, and 5px of kerb is wider than the
  disagreement. The gate was not touched — what moved is where things stand.
- **Flush is not clear on PAINT either (`PAINT_KERB`).** `paintField` tests the
  blob boundary exactly while the rasteriser blurs it, so `fallen_log@1052,1061`
  stood on painted flagstone at 1.02 blob radii.
- **The occupancy step forgot the squash.** A disc reaches `half` across but
  `half*0.72` down, so stepping a vertical run by `half` pinched the band to 72%
  of its width between centres — 1.8px on a 13px path, drawn as beads. NOT a
  hole: the discs always overlapped. The first version of this arm claimed one,
  came back GREEN under mutation, and both the arm and the code comment were
  corrected rather than kept.
- **A yard prop had a fixed direction.** `c + (92, 26)` is the back garden for
  one row of officers and the FRONT garden for the other; on the inner row it
  points at the square, and once the street widened with the officer count the
  timber landed on the paving. It now follows the lot's own `face`.

## 4. Fixtures corrected, and what was deliberately left alone

`states/hamlet.json` gained `counts` for `great_house`, `library`, `workshop`
and `quay` — the INDEX of the rung the same file already names in `stages`. One
fact in two channels, and `counts` is the channel the live path writes a rung
index into. `law_plot` (3) and `pens` (2) were LEFT ALONE: their counts predate
this and are read elsewhere as a number of things (fence runs; the windmill and
kiln gates) rather than as a rung. That ambiguity is older than this change and
resolving it would move what the frame draws for reasons unrelated to roads.

`clearing.test.ts`'s camp org carried `great_house: 'camp_log_cabin'`, which is
not a rung of that ladder at all — an invented rung, and it made an arm named
"a HATCHED island is dominated by wood" measure a camp that had already built a
hall. Corrected to a real hatch. All four era fixtures gained the `quay` rung,
without which the harbour road is a footpath on a town.

## 5. Mutation testing — 13 run, 13 red, one reported green first

Ten against the lane model and the two kerbs, three against the road materials.
Every one turned an arm red.

| Mutation | Arm that went red |
|---|---|
| era gate restored (every measured destination always exists) | a lane exists ONLY when the place at its far end does |
| width from the road rung, usage ignored | WIDTH follows the destination, and only the destination |
| unmeasured districts widen anyway | a district nothing measures keeps a hairline forever |
| surface pinned at rung 0 | the ROAD RUNG sets the surface and nothing else |
| link lane needs nothing | a LINK lane needs both of the lanes it joins |
| the near-end gate ignored | the lane a spur hangs off must exist too |
| the occupancy step forgets the squash | the narrowest lane does not NECK between its samples |
| `LANE_KERB = 0` | hamlet: all twelve invariants pass on a real frame |
| `PAINT_KERB = 0` | hamlet: all twelve invariants pass on a real frame |
| a drive may be wider than its road | a drive is one household of its road, never wider |
| gravel leaves the road classifier | every road material reads as road to check_on_road |
| worn dirt is just dirt | the four materials are tellable apart |
| gravel is just dirt | the four materials are tellable apart |

**M7 came back GREEN on the first attempt** and is recorded here rather than
buried: the arm asserted a HOLE in the occupancy field, there has never been one
at any step this code can produce, and it therefore could not fail. It was
rewritten to measure the band's necking by bisection (old step 1.82px, new
0.87px, bar of one whole pixel at the ladder's narrowest rung) and the mutation
is now caught.

The road materials are pinned two ways. Every tone must be inside
`world_checks.ROAD_RGB`'s tolerance — a gravel outside it would not look wrong,
it would turn `check_on_road` BLIND on every org past the dirt rungs, which is
the sensor-not-wired-to-the-control defect with the roads as its subject. And
the four must be tellable apart, because a rung that renders as its predecessor
cannot reach the frame. `iso-quay.test.ts` then caught the first worn-dirt ramp
at 27.6 units from the wharf's fascia against a 40-unit bar: the ramp moved, the
bar did not.

## 6. Both renderers, not one

`engine-canvas.tsx` painted every lane with the `dirt` ground class. Left there,
the offline still would show the org's road maturity and the live page would
not — the two-renderers-one-world rule broken in the direction nobody notices.
It now groups by surface through `ROAD_GROUND`, the twin of `raster.py`'s
`ROAD_TEXTURE`. Only cobble is tiled on the offline side (it is per-pixel Python
and the network spans the canvas); the three field-based materials are generated
whole, because a tile seam was visible on the first attempt.

## 7. Still open, and NOT caused by this change

The live state (today's real chronicle) is RED on `on_road` with
`market_goods@1390,1056` and `bush_flowering@1284,1113`. Byte-identical before
and after — verified by capturing the same state from `origin/master` in a
scratch tree — and already recorded in `live-state.ts`'s own docstring.
Diagnosis: the blueprint declares the plaza as the ellipse INSCRIBED in the
blobs' bounding box, so `check_on_road`'s exemption is smaller than the paint,
and an item whose CENTRE is off the blobs can still have a ground box that
reaches onto flagstone. Three different shapes for one surface: `onPaving` is a
point test on blobs, the exemption is an inscribed ellipse, the paint is a
blurred blob union. Fixing it means changing what the blueprint declares the
plaza to be, which also moves `check_terrain`'s "square paved" arm — a separate
change with its own review, not a rider on this one.

## Verdict

Ship this checkpoint. Both rulings are implemented as properties rather than as
flags, both shipped fixtures are green on all twelve invariants, every new arm
has been shown to fail against the pre-change code, and the one arm that could
not fail was found by mutation and rewritten rather than counted.
