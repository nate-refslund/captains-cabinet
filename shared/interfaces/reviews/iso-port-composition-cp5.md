# iso-port-composition · checkpoint 5 — the verification bridge

*FW-019 review artifact. ~2,500 changed lines across the capture harness, the
blueprint emitter and two layout fixes.*

## What this checkpoint does

Closes the gap the previous four checkpoints left: the layout stage was measured
to death and **never looked at**. `composeLayout` had no caller outside its own
tests, "does the belt read as framing" was answered by a density histogram, and
the twelve invariants in `checks/world_checks.py` had never seen a composed
island because nothing emitted a blueprint.

This adds the delivery path: `composeLayout` → blueprint + draw list → a
deterministic rasteriser → `frame.png`, `frame.ground.png`, `frame.ids.png`,
`frame.idsrev.png`, `frame.blueprint.json` → all twelve checks. No browser: the
layout is a pure function and the drawing is done over the same atlas the
approved stills use.

## Result on first contact

`camp` **12/12 green, 0 surfaces unchecked**. `hamlet` **12/12 green**, with
`era` reported unchecked — structurally, because every floor in `ERA_MIN` is
`hamlet`, so above camp that arm cannot fire and the check refuses to claim the
surface rather than print a zero that reads like evidence.

Two real defects were caught, both by pixels, neither visible to any layout-only
arm:

1. **A building standing in the crop.** The harbourmaster's hut, whose harbour
   offset is the tilled plots' own column, stood with its ground diamond in a
   ploughed plot — and ploughed soil is the same warm brown as a dirt lane, so
   `check_on_road` named it. Measured across 40 village seeds: **28/40** stood a
   structure on a plot. Structures knew about lanes, water and each other;
   nothing told them about the plough, while the *planting* passes have excluded
   `crop`/`ploughed` all along.
2. **The painted road was not the reserved road.** `buildLaneField` reserves a
   squashed ellipse (`LANE_SQUASH = 0.72`, a circle on the ground projects
   flattened); a renderer drawing a round stroke paints tarmac 39% taller in y
   than anything ever reserved, so a sprite legitimately cleared by the rules
   ends up on painted road. `LANE_SQUASH` is now exported and shipped in the draw
   list, so there is one definition of the road surface.

## The fixes

| file | change |
|---|---|
| `iso-layout/index.ts` | tilled plots enter the structure stage's occupancy as ONE occupant per plot extent; `put()` finishes with `clearOfRegions`. Plaza deliberately excluded — the hearth belongs on the square. |
| `iso-layout/clearance.ts` | new `clearOfRegions`: the ring search `clearOfLane` runs, for keep-off surfaces, considering only points ON LAND. |
| `iso-layout/lanes.ts` | `LANE_SQUASH` exported. |

`clearOfRegions` exists because neither existing primitive could do it:
`clearOfLane` returns immediately when the spot is off the road (which is the
case that must keep searching), and `settleAgainstOccupants` has no land test, so
it shoves a shoreline anchor into the sea and `placeOnGround`'s land walk brings
it back onto the plot it was pushed off. Per-blob occupants alone took 28/40 to
17/40 — a half-fix that would have gone green over the remainder, which is worse
than none. With the ring search: **0/40**, pinned by a 40-seed sweep in
`blueprint.test.ts`.

## Why the bridge is a sensor and not a restatement

- **`justified` is derived from STATE, never from what was drawn.** The offline
  compositor adds a name to its justified set in the same breath as it places the
  sprite, which makes `check_state_traceable` a tautology — `drawn - justified`
  empty by construction. Here removing a count removes the entitlement, pinned by
  a test that flips `officer_dwellings` to 0 and asserts the houses lose it.
- **Nature is not justified.** An island has a treeline whether or not anyone has
  landed on it, so morphology goes through `--allow-ambient`, a static
  hand-held list that fires the day a planting pass grows a new species.
- **`layers` is filled by whatever paints.** Paint order includes shadows; only
  the rasteriser knows it. A guess would wire `check_depth_order` to the wrong
  artifact.
- **A check never imports what it tests.** `raster.py`/`ground.py` are on the
  tested side; a test asserts `world_checks.py` imports neither.

## Every arm proven to fail

Six mutations in `raster.py --mutate`, each breaking one rule, each asserted to
turn **exactly one** check red and nothing else. All six were run:

| mutation | arm | observed |
|---|---|---|
| `orphan-sprite` | `state_traceable` | `1 sprites with no state justification: ['bench']` |
| `sprite-on-lane` | `on_road` | `1 sprites stand on a lane: ['great_house@1201,1142']` |
| `no-shadows` | `shadows` | `25/56 large sprites darken the ground (45%)` |
| `reverse-depth` | `depth_order` | `10839 of 10936 contested pixels won by the FARTHER layer` |
| `unpaved-square` | `terrain` | `square paving 30% no denser than its surroundings 17%` |
| `ghost-sprite` | `paint_fidelity` | `1 left no mark ['great_house@1096,829 0%']` |

## Findings recorded, not fixed here

- **`--scale` changes what the checks measure.** `world_checks.py` carries
  absolute-pixel constants (`road_mask` steps 3px; `check_shadows` samples
  3/7/12px below a base and takes its bare reference at `max(70, w*1.5)`). At
  `--scale 0.45` a frame that is green at 1.0 invents an on-road sprite and drops
  `shadows` to 46–54% against its 55% floor. The CI arm captures at 1.0; the flag
  is documented as eyeball-only.
- **`composeLayout` gates the market stall on a `market_stall` ladder that does
  not exist** in `cabinet/world/growth-ladders.yml`. In the reference it is
  era-gated village *ambient*. With an honest state the stall can never appear,
  so the hamlet fixture does not declare it. Not fixed here — it is a content
  decision, not a rendering one.
- **`ground.py` is a port, not the reference.** `terrain.py` needs
  `opensimplex`+`numpy`, which neither this machine nor CI has. Ramps, Bayer
  dither, furrow/ripple and flagstone are copied exactly; only the noise source
  differs. `tests/test_ground.py` asserts the ramps are the palette's byte for
  byte, that every surface emits **only** its own ramp, and that each surface
  lands in the colour class `world_checks.py` will read it as.

## Not in scope, stated so it is not assumed

`?iso=1` in the engine. This round builds the bridge and judges the layout; the
engine still renders the top-down path and `DEFAULT_PROJECTION` is unchanged.
The blueprint emitter is what will hold the engine and the still renderer to one
description when steps 3–4 of the port plan land.

## Verification run this session

- `npm test` — 2544 passed, 1 skipped, 134 files.
- `python3.12 -m pytest cabinet/scripts/world-capture/tests -q` — 6 passed.
- `capture.py --state camp` — GREEN 12/12, 0 unchecked.
- `capture.py --state hamlet` — GREEN 12/12, 1 unchecked (`era`, structural).
- `sync-checks.py --check` — 4/4 mirrored files identical.
- `npx tsc --noEmit` — clean for every file in this checkpoint. **Pre-existing
  red in `src/components/world/engine-client.tsx`** (`proj`, `clamp` undefined,
  9 errors) belongs to another writer's uncommitted work in this same worktree;
  untouched here and not committed.
