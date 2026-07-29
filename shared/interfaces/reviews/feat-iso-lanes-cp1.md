# Checkpoint review — feat/iso-lanes cp1 (2026-07-29)

Reviewed-Scope-Digest: 34f99f9197552308b3b807f3de55c9330bd0ea86addee5ee3f646a60f5a6c8fa

## What this lands

The product archipelago, in the isometric kernel. Before this commit `/world`
under iso drew no lane isle, no reef buoy and no mist pocket, and `pickIso`
could never return `kind:'lane'` — five product lanes and the why-strings that
cite `instance/config/outcomes.yml` were unreachable in the kernel that had just
become the default. The data was never missing: `WorldGeo.laneSites` is built
client-side from the same engine payload in both kernels. Only the geometry and
the hit test were absent.

- `lib/world/iso-lanes.ts` (new, pure) — sites the fan in open water measured
  off the island's own reach (coastline + harbour envelope), preserving the
  authored `ISLE_SLOTS` bearings and squashing the ring by the projection
  kernel's own 2:1. Sizes are fractions of the home island via
  `isleRadius(rung) / MAIN_ISLAND_R_CAP`, so an isle is the same fraction of
  home in both kernels. Carries the hit test the renderer draws from.
- `engine-canvas.tsx` — `drawIsoLanes` paints isle / reef buoy / mist pocket and
  the course drift lines, and `hitTarget` hands the pick THE SAME ARRAY it drew.
- `pick.ts` — the iso arm tests lanes, and a measured role with no building row
  now answers with the new read-only `element` kind instead of falling through
  to `ground` (the seven mooring posts' `berths` count).
- `engine-client.tsx` — one `elementCard` builder serving both the building and
  the element kind; the far-zoom NAVIGATE branch is gated to top-down, because
  every coordinate it flies to is a top-down tile.
- `law-render.ts` — `lane_reef_buoys` moves to rendered; `harbor_boat_voyage`
  stays unrendered with a corrected reason (the drift lines are drawn now, the
  boat is not, and half a law painted is not the law).

## Verification

- `npx tsc --noEmit` clean; `npx vitest run` 2773 passed / 1 skipped, 139 files.
- `cabinet/scripts/check-layer-separation.sh` — new=0.
- 8 mutations on `iso-lanes.ts` and 3 on `pick.ts`, each proven to red the arm
  that guards it (listed in the commit message).
- ONE MUTATION CAME BACK GREEN and was fixed rather than reported away: the
  first "the clearance enters the radius" arm asserted a lower bound that the
  OTHER term of the max already satisfied, so dropping the clearance from the
  horizontal term passed. The arm now drives a wide island and a deep one and
  checks both terms.
- Browser, real dev server against the live cabinet (`CABINET_ROOT` = the live
  checkout), clicked and read every card: slot 1 `polads — isle ring r1`,
  slot 2 `stephie — isle ring r1`, slot 3 `stepnetwork — reef buoy`, slots 4/5
  `reserved fan slot N`, and a mooring post `berths: berths_7plus (jetty_berth)
  — metric 7` where it used to answer ground.

## Known and stated

- The reef buoy and the mist pockets are small at the archipelago tier — honest
  (no land earned) but hard to find by eye. Legibility is a composition call for
  the Captain, not a threshold to move.
- The voyage boat is still top-down only.
- `palette_coherence` on fog frames is pre-existing and untouched; every hue
  added here is either an `iso-terrain` RAMP, an `iso-quay` plank colour, a
  corpus neutral, or `BUOY_RED` sampled from the shipped pack's own `buoy`
  frame.
