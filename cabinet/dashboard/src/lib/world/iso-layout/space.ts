/**
 * ISO-LAYOUT — the shared coordinate space of the ported composition layer.
 *
 * WHY THIS LIBRARY EXISTS (Captain ruling 2026-07-27): the shipped world must
 * look like the approved stills — real coastline, carved cove, lanes, lots,
 * driveways, density-driven planting — not the engine's flat tile lattice.
 * The stills are produced by an offline Python compositor
 * (designs/world-mockup-v2/compose.py); this directory is the TypeScript port
 * of that compositor's LAYOUT stage, as pure seeded functions with tests.
 *
 * WHICH SPACE THE LAYOUT LIVES IN. compose.py has NO tile grid: it places at
 * absolute pixels on a 2400x1760 canvas, and its island is an ellipse with a
 * 962/784 = 0.82:1 aspect. Projecting the engine's circular tile disc through
 * the 2:1 isometric matrix would instead give a 0.5:1 ellipse — 1.6x flatter,
 * a different coastline model, and a rigid lattice where the reference has
 * repulsed lots. That divergence is exactly what the Captain ruled against, so
 * the layout is computed HERE in the compositor's own screen-pixel space and
 * the renderer consumes those coordinates directly. The camera stays a pure
 * scale+translate, so layout space IS the world container's local space.
 *
 * LAYOUT_FOLD AMENDMENT (Captain, 2026-07-27). The standing law is that a
 * building's position fixes at birth and never moves. Lots here are COMPUTED
 * from the lane network rather than hand-placed, so a lot's centre is a
 * function of (seed, era, road rung, coastline) instead of an authored
 * constant. The Captain accepted that amendment when ruling for the layout
 * port; it is recorded here because it is the one law this directory bends.
 * Determinism is what keeps it honest: same inputs -> byte-identical layout,
 * forever, which is why every function in this directory is pure and seeded.
 *
 * THE EXACT SCOPE OF THAT DETERMINISM, stated rather than assumed. Every
 * decision here is a pure function of (state, seed): no clock, no unseeded
 * randomness, no IO, no DOM, no iteration over an unordered collection. Within
 * one JavaScript engine the output is bit-identical run to run, which is what
 * the tests pin. ACROSS engines it is identical to the precision of the
 * transcendental functions the lane wobble and the ring searches use
 * (Math.sin / cos / atan2 are implementation-defined in the last ulp; sqrt,
 * floor and Math.imul are exact). The world renders in one runtime, so this
 * costs nothing today — but "byte-identical forever" is a claim with a
 * boundary, and an unstated boundary is how a claim becomes a lie later.
 *
 * PURE: the world CI ratchet (lib/world/ratchets.test.ts, arm 4) greps this
 * tree for Math.random and Date.now — seeded variation goes through hash.ts's
 * fnv1a/seededRng.
 */

import { ISO_TILE as PROJECTION_ISO_TILE } from '../projection'

/** A point in layout space (screen pixels on the compositor canvas). */
export interface Point {
  x: number
  y: number
}

/**
 * The layout canvas. `cx`/`cy` are the ISLAND CENTRE, not the canvas centre:
 * compose.py sits the island above the middle so the harbour fits below it
 * (compose.py ICX/ICY = 1200/760 on a 2400x1760 canvas).
 */
export interface LayoutSpace {
  w: number
  h: number
  cx: number
  cy: number
}

/** compose.py:57-58 — W,H = 2400,1760; ICX,ICY = 1200,760. */
export const LAYOUT_SPACE: LayoutSpace = { w: 2400, h: 1760, cx: 1200, cy: 760 }

/**
 * The isometric tile, in layout pixels. 48x24 is the calibrated size: it is
 * the first tile size at which no two authored building anchors share a ground
 * diamond in any of the four eras (iso-engine-port-plan-2026-07-27.md step 2,
 * replicated by the premise-check). It is 2:1, which is what makes the ground
 * axes run at slope +/-0.5.
 *
 * RE-EXPORTED, never re-typed: the renderer's projection kernel owns this
 * number (../projection.ts ISO_TILE). A second literal here would be a second
 * notion of the grid, which is the exact defect class that cost this program
 * three placement bugs — so the constant is imported and passed through.
 */
export const ISO_TILE = PROJECTION_ISO_TILE

/**
 * Slope of the two isometric ground axes in layout space.
 *
 * DERIVED, never typed twice: an axis-aligned tile step of (48,0) or (0,48) in
 * world tiles projects to a screen step of half the tile height per half the
 * tile width, i.e. ISO_TILE.h / ISO_TILE.w. driveways.ts routes along +/- this
 * slope. When the renderer's projection module lands it must agree with this
 * number; iso-layout's tests pin the 2:1 relationship so a divergence is loud.
 */
export const ISO_AXIS_SLOPE = ISO_TILE.h / ISO_TILE.w

/** Growth eras, in order. Mirrors the engine's era vocabulary. */
export type Era = 'camp' | 'hamlet' | 'town' | 'beyond_bay'

const ERA_ORDER: readonly Era[] = ['camp', 'hamlet', 'town', 'beyond_bay']

/** True when `era` is at or beyond `floor` (compose.py's WS.era_at_least). */
export function eraAtLeast(era: Era, floor: Era): boolean {
  return ERA_ORDER.indexOf(era) >= ERA_ORDER.indexOf(floor)
}

/** Road ladder rungs — the road IS a rung, and its width follows it. */
export type RoadRung = 'dirt_path' | 'dirt_worn' | 'gravel_road' | 'cobbled_road'

/**
 * worldstate.py present() — the rung values that mean NOTHING IS BUILT HERE YET.
 *
 * ONE COPY, because two modules ask the question. index.ts asks it of every
 * object's stage (`presentRung`), and harbour.ts asks it of the `quay` rung
 * before it lays a plank. It lived only in index.ts until 2026-07-27, so the
 * harbour could not ask at all: it read an absent quay rung as `rowboat_jetty`
 * and drew a 96px pier for a quay that had never been measured, and it read a
 * rung of `bare_ground` as an UNKNOWN rung and gave it the deepest wharf in the
 * table. Both are the same defect — a drawn thing with no state behind it — and
 * both came of the answer living in a module the harbour could not import.
 *
 * `empty_plinth` is in THIS set and is deliberately absent from
 * checks/world_checks.py's EMPTY_RUNG. The two sets answer different questions
 * and the difference is not drift: the offline check asks "may this SPRITE be
 * drawn", and an empty plinth is a real object a viewer can see; this set asks
 * "has this object BUILT anything", and an empty plinth has not. The objects
 * whose empty rung IS the drawing carry that exception by name, one level up
 * (index.ts ALWAYS_DRAWN).
 */
export const EMPTY_RUNGS: ReadonlySet<string> = new Set([
  'none',
  'bare_ground',
  'bare_pole',
  'bare_wall',
  'empty_plinth',
  'dark',
  'dark_cairn',
])

/**
 * True when a stage value means the object has built nothing yet.
 *
 * ABSENT AND EMPTY ARE THE SAME ANSWER HERE and that is deliberate: an object
 * whose ladder the state never mentions has not been measured, and drawing the
 * first rung of an unmeasured ladder is inventing a measurement. It is the
 * distinction between "no data" and "zero", collapsed in the only direction
 * that cannot fabricate.
 */
export function emptyRung(stage: string | null | undefined): boolean {
  return stage === null || stage === undefined || EMPTY_RUNGS.has(stage)
}

/** Clamp to [lo,hi]; NaN clamps to `lo` so a bad input can never size a buffer. */
export function clamp(v: number, lo: number, hi: number): number {
  if (!Number.isFinite(v)) return lo
  return v < lo ? lo : v > hi ? hi : v
}

/** clamp() into 0..1 — the shape every density/weight field returns. */
export function clamp01(v: number): number {
  return clamp(v, 0, 1)
}

/**
 * Hard ceiling on any raster this library allocates.
 *
 * The coastline and lane fields are Uint8Array rasters whose size comes from
 * caller-supplied numbers (space dimensions / sampling step). Unvalidated they
 * are an allocation lever, so every raster goes through rasterDims(), which
 * clamps the step, rejects a non-finite space, and refuses anything past this
 * cell count. 2400x1760 at step 1 is 4.22M cells, so the default canvas at its
 * finest useful sampling fits with room to spare.
 */
export const MAX_RASTER_CELLS = 8_000_000

export interface RasterDims {
  step: number
  mw: number
  mh: number
  cells: number
}

/**
 * Validated raster dimensions for a space sampled every `step` pixels.
 * Throws rather than allocating when the request is out of range — a silent
 * clamp would render a different world than the caller asked for.
 */
export function rasterDims(space: LayoutSpace, step: number): RasterDims {
  if (
    !Number.isFinite(space.w) ||
    !Number.isFinite(space.h) ||
    space.w <= 0 ||
    space.h <= 0
  ) {
    throw new Error(`iso-layout: invalid layout space ${space.w}x${space.h}`)
  }
  const s = clamp(Math.floor(step), 1, 64)
  const mw = Math.ceil(space.w / s)
  const mh = Math.ceil(space.h / s)
  const cells = mw * mh
  if (cells > MAX_RASTER_CELLS) {
    throw new Error(
      `iso-layout: raster ${mw}x${mh} = ${cells} cells exceeds MAX_RASTER_CELLS ${MAX_RASTER_CELLS}`
    )
  }
  return { step: s, mw, mh, cells }
}

/** Euclidean distance — named so the ported formulas read like the reference. */
export function hypot(dx: number, dy: number): number {
  return Math.sqrt(dx * dx + dy * dy)
}
