# iso-port-composition — cp7: the render path (first pixels)

Round 7 of the isometric port. The previous six rounds built and attacked the
LAYOUT stage; this one builds the delivery path that makes those measurements
mean something. Scope: wire the projection kernel through the engine, drive the
scene from `composeLayout` under `?iso=1`, load the shipped pack, compute the
ground, light the lamp.

## Why this round existed

`composeLayout` had survived three adversarial rounds and had **no caller**. The
twelve invariants in `cabinet-meta/checks/` had never seen a composed island,
the calibrated aesthetic judge had nothing to run on, and "does the belt read as
framing" was being answered by a density histogram. Every measurement already
taken was worth nothing until a frame could be looked at.

## What landed

| Area | What |
|---|---|
| kernel | `projection.ts` gains `ISO_BASE`, `worldScale()`, `projectionFromParam()`; every camera/pointer/label/drag transform in the engine now routes through it |
| flag | `?iso=1` / `?iso=0`, read server-side in `page.tsx`, threaded as a `projection` prop to `EngineClient` → `EngineCanvas`. `DEFAULT_PROJECTION` stays `'topdown'` |
| pack | `iso-pack.ts` — strict parser, `frameFor(object, era, rung)`, `isEmptyRung()`, `eraOfFrame()`, pack-backed footprints. Atlas + pack committed under `public/world-assets/originals/iso/`, registered in the asset manifest |
| scene | `iso-scene.ts` — `LayoutState` from `WorldResolution`, `composeLayout` with the pack's own drawn sizes, a depth-sorted sprite list, the lamp, and an `issues[]` that nothing can be dropped past |
| ground | `iso-terrain.ts` — the port of `designs/world-mockup-v2/terrain.py`: seeded fbm, 4×4 Bayer dither onto the brief's ramps, the isometric flagstone lattice, furrows on the ground axis, a seamless open sea |
| renderer | `engine-canvas.tsx` grows an iso branch: island/beach masks from the coastline raster, paint regions, lanes, wharf and jetty baked into one RenderTexture; pack sprites at base-centre anchors on the existing `sortableChildren` layer; the lamp glow composited over the ambience grade |
| ratchet | ratchets arm 10 — no file on the engine path may declare its own tile constant or import the legacy wardroom `TILE` |

## Evidence

- **The top-down path is pixel-identical.** `/world` captured at z=1 and z=3
  against `HEAD` and against this change, 1600×1000: **0 differing pixels, max
  channel delta 0** at both zooms. That is the bake-off, measured — not the
  arithmetic argument.
- **Suites**: `npx vitest run` → 2552 passed, 1 skipped (the skip is a
  pre-existing live-store smoke test, untouched). World subset 695 passed
  (was 616). `npx tsc --noEmit` clean. Re-run green after the concurrent
  session's `b658fe72` landed under this branch.
- **Mutation battery**: 36 mutations, each disabling one rule this round added;
  **all 36 killed**. Script:
  `scratchpad/mutate-render.py`. Ratchet 10 separately mutation-proved twice
  (re-introducing a tile constant, re-introducing the legacy import).
- **First pixels**: `/world?iso=1` renders the composed island — coastline,
  beach ring, computed ground, forest belt, meadow scatter, pond and outflow,
  the lane, the campfire, the cairn — with **zero iso-pack issues** in the
  console. Captures in `cabinet-meta/.playwright-mcp/iso-z1-b.png` and
  `iso-z3-close.png`.

### Two mutants survived the first pass, and both were real holes

1. `?iso=0 no longer forces topdown` survived because the explicit answer and
   the default agree today — the arm would have stayed green right up to the
   day `DEFAULT_PROJECTION` flips, which is the one day it matters.
   `projectionFromParam` now takes an injectable fallback and the arm is
   exercised against `'iso'`.
2. `the sea patch stops tiling` survived because the test rebuilt the field
   from a hand-copied options object instead of the shipped one — a test
   proving the test was periodic. `seaFieldOptions()` is now exported and both
   use it.

## Defects found and fixed in existing code

- **`ISO_TILE`'s docstring cited a calibration test that did not exist**, in the
  same sentence as noting the constant had once cited a test that did not exist.
  There was no `projection.test.ts` at all, so *every* "pinned by the tests
  below" claim in that module was false. The file now exists (15 arms) and the
  docstring states what is actually pinned: 2:1 with whole-pixel halves,
  agreeing with the shipped pack's own `projection` declaration and with
  `iso-layout`'s `ISO_AXIS_SLOPE`. The historical anchor calibration is recorded
  as history, because the shipped iso path no longer places from that table.
- **The era axis was never rendered.** The layout emits `kind: 'lighthouse'` at
  every era and `dwellingKind` only gates at camp, so without the pack's table a
  camp island grows a full stone tower over a `dark_cairn` rung and a town wears
  hamlet cottages. `resolveFrame` makes the pack's `(object, era, rung)` table
  decide, and lets the layout's `kind` refine only *within* the era family — so
  per-lot dwelling variety survives and the era lie does not.
- **The layout was spaced for sprites it would not draw.** `DEFAULT_FOOTPRINTS`
  is era-blind: `great_house` is 200×200 there and 128×120 at camp. Every
  spacing rule the layout enforces was measuring the wrong sprite.
  `packFootprintOf` hands it the pack's drawn size for the frame that will
  actually be resolved, and the *spaced-is-drawn* arm asserts the two agree for
  every structure at every era.
- **The painted lane was 39% wider in y than the corridor the rules reserved.**
  Adopted from the concurrent session's finding (see below): the occupancy field
  tests an ellipse with y-radius `half·0.72`; a round stroke over it lays road on
  ground nothing reserved. The mask is drawn with y pre-divided and scaled back,
  which reproduces the union of ellipses exactly. `LANE_PAINT_SQUASH`
  re-exports their `LANE_SQUASH` (one definition) *and* is pinned by
  **measuring** `buildLaneField`'s real x and y reaches — an import alone would
  survive the constant changing meaning.

## What is absent or broken under `?iso=1` — stated, not discovered

| Surface | State |
|---|---|
| hit-test / inspect cards | **Deliberately inert.** Every tolerance in `hitTarget` is a tile-space test against top-down geometry; run against an iso pointer it would open a card asserting something false about the org. Under iso it returns the ground fallback only. `pick.ts` is the fix and is the next step. |
| officers, commute walkers, site crews, apprentices, fauna | **Not drawn.** All LIFE positions are top-down tile coordinates. |
| roof cutaway and interiors | **Not drawn.** The pack ships zero roof-off and zero interior frames; `cutawayCandidate` still runs client-side but the iso canvas ignores it. |
| chimney smoke, lane-site buoys, mist pockets, isle marks, window glows | **Not drawn** — same reason. |
| LOD footprint tier | **Not applied.** The iso path draws its ~250 sprites at every zoom. |
| the eight measured-but-never-drawn ladders | Still never drawn: `flagpole`, `noticeboard`, `veto_plinth`, `composter`, `field_plots`, `cargo_stacks` (as sprites), `berths` beyond the mooring posts, `harbor_boat`'s variants. The layout does not emit anchors for them. |
| `pending` / `measured` honesty overlays | Not composited yet. `resolveFrame` is invariant to both, which is the precondition for adding them without losing them. |
| deep links | `?x`/`?y` name a **different place** in the two kernels. The camera home is derived from the layout centre through the kernel; re-basing the deep-link contract is the zoom step's work. |
| meadow shading | Hard-edged ellipses. The reference blurs its mask; this does not. A named fidelity gap, not a fix invented to look better. |
| LimeZu sheets | Still fetched under iso even though nothing uses them this round, so the loud-failure path stays wired for the character step. On a machine without the packs this raises a render-issues badge that is about the top-down path, not the iso one. |

## Concurrent-writer note

**A second session was writing in this same worktree throughout this round**,
and it committed mid-way through my staging (`b658fe72`, the verification
bridge): `blueprint.ts`, `capture.test.ts`, `cabinet/scripts/world-capture/`,
`iso-layout/{clearance,index,lanes}.ts`, a CI workflow edit — and the iso atlas
and pack, which it picked up from the untracked copies this round had placed in
`public/world-assets/originals/iso/`. Its commit did not include any of this
round's files; nothing was lost in either direction, which is luck rather than
process.

Consequences handled here: the asset files are already at HEAD, so this commit
carries only the manifest row that registers the atlas with the asset gate; and
`LANE_SQUASH` is now committed, so `LANE_PAINT_SQUASH` re-exports it instead of
duplicating the literal. Every path in this commit was named explicitly to
`git add` — never `-A`, never `.`.

**Two agents in one checkout is the hazard the doctrine names and it should not
be repeated.** The next round needs its own worktree.

## Verdict

SHIP for what it claims: the delivery path exists, the top-down path is proven
untouched to the pixel, and every rule this round added is proven to fail when
disabled. It does **not** claim a finished isometric world — the absence table
above is the work order.
