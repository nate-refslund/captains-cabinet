/**
 * PROJECTION — the ONE world→screen kernel (iso port, step 1).
 *
 * Before this module the transform existed FIVE times and disagreed with
 * itself: the engine-canvas camera transform, engine-canvas's hand-rolled
 * hit-test inverse, engine-client's pointer-drag pan inverse, engine-client's
 * DOM-label project(), and lod.ts's private TILE_PX + screenRect. A building
 * carried FOUR notions of where it stands (draw anchor, zIndex, padded hit
 * rect, shadow width). Adding an isometric notion on top of that would have
 * birthed a sixth. So the copies collapse HERE first, in TOP-DOWN mode, with
 * the existing suite as the proof of equivalence — and only then does the
 * kernel flip.
 *
 * TWO KERNELS, ONE INTERFACE:
 *   topdown  x = tx·W          y = ty·H            (W = H = 16, today's TILE)
 *   iso      x = (tx − ty)·W/2 y = (tx + ty)·H/2   (2:1, W = 2·H)
 *
 * DEPTH is the projected base y in BOTH kernels — which is exactly what the
 * renderer already sorts on (one sortableChildren container, bottom-centre
 * anchors, zIndex = base y) and exactly what the offline compositor does
 * (placed.sort by base y). The mechanism is not redesigned here; only the
 * value fed to it changes when the kernel flips.
 *
 * THE CAMERA STAYS A PURE SCALE+TRANSLATE. The 2:1 matrix is never applied
 * to the world Container — that would shear every sprite. The pack's sprites
 * are ALREADY drawn in isometric; it is the GRID that projects, per object,
 * at placement. cameraTranslation() below is the only camera math.
 *
 * EXACTNESS (why the topdown rewire is a no-op): the TOP-DOWN tile is 16, a
 * power of two, so multiplying by it is exact in IEEE-754 and every rewired
 * call site reproduces its old arithmetic bit for bit. That is what makes the
 * existing suite a valid proof of "nothing changed" rather than a rough check,
 * and it is pinned by the bit-for-bit tests below.
 *
 * The ISO tile is 48x24 and is NOT a power of two — the distributive identity
 * fl(fl(d·48)·z) == fl(d·fl(48·z)) fails on roughly a third of random inputs.
 * That is harmless here and must not be mistaken for a problem: the iso path is
 * new, so there is no legacy arithmetic for it to reproduce. What it does need
 * is that half a tile is a whole pixel (24 and 12), because the iso kernel adds
 * tile/2 terms; a fractional half-tile would place sprites off the pixel grid.
 *
 * PURE: no clocks, no RNG, no DOM (determinism ratchet #4).
 */

/** Which kernel a render pass uses. */
export type ProjectionKind = 'topdown' | 'iso'

/**
 * The kernel the world renders with when nothing overrides it.
 *
 * Starts 'topdown' so the port lands invisible. ?iso=1 / ?iso=0 select
 * explicitly in both directions from day one, so flipping this constant is
 * one line and the top-down path stays permanently reachable for the
 * bake-off (and for a one-line revert).
 */
export const DEFAULT_PROJECTION: ProjectionKind = 'topdown'

/** Tile size in screen px, per kernel. */
export interface TileSize {
  w: number
  h: number
}

/** Today's grid: the 16px LimeZu art cell, one tile = one cell. */
export const TOPDOWN_TILE: TileSize = { w: 16, h: 16 }

/**
 * The isometric grid. 48×24 is MEASURED, not chosen: projection.test.ts's
 * calibration block projects every frame in the SHIPPED world-pack.json at a
 * range of candidate tile sizes and asserts 48×24 is the smallest at which the
 * largest structures' ground diamonds fit within one tile step. Change this
 * constant and that test fails — which is the point. It previously cited a test
 * file that did not exist, so the constant was pinned by nothing and could be
 * set to the value the calibration had REJECTED with the suite still green.
 */
export const ISO_TILE: TileSize = { w: 48, h: 24 }

/** A world-tile point (fractional tiles allowed — LIFE emits floats). */
export interface TilePoint {
  tx: number
  ty: number
}

/** A point in world PX (pre-camera; the camera adds scale+translate). */
export interface WorldPoint {
  x: number
  y: number
}

/** An axis-aligned box in world-tile space. */
export interface TileBox {
  x: number
  y: number
  w: number
  h: number
}

/** An axis-aligned box in world px. */
export interface PxBox {
  x0: number
  y0: number
  x1: number
  y1: number
}

export interface Projection {
  readonly kind: ProjectionKind
  /**
   * Tile size in px. Use for EXTENTS that are honestly axis-aligned in the
   * art (a baked pattern's fill size, a sprite's own pixel span) — never to
   * hand-roll a coordinate conversion; that is what project() is for.
   */
  readonly tile: TileSize
  /** World tile → world px. The paired conversion: under iso the axes are
   * coupled, so a lone `tx * TILE` is always a bug. */
  project(tx: number, ty: number): WorldPoint
  /** World px → world tile. Exact inverse of project(). */
  unproject(x: number, y: number): TilePoint
  /** Paint order key for a footprint's base point: the projected base y. */
  depthOf(tx: number, ty: number): number
  /** The px AABB of a tile-space box (all four corners under iso). */
  screenAABB(box: TileBox): PxBox
}

function topdownProjection(): Projection {
  const tile = TOPDOWN_TILE
  return {
    kind: 'topdown',
    tile,
    project(tx, ty) {
      return { x: tx * tile.w, y: ty * tile.h }
    },
    unproject(x, y) {
      return { tx: x / tile.w, ty: y / tile.h }
    },
    depthOf(_tx, ty) {
      return ty * tile.h
    },
    screenAABB(box) {
      return {
        x0: box.x * tile.w,
        y0: box.y * tile.h,
        x1: (box.x + box.w) * tile.w,
        y1: (box.y + box.h) * tile.h,
      }
    },
  }
}

function isoProjection(): Projection {
  const tile = ISO_TILE
  const hw = tile.w / 2
  const hh = tile.h / 2
  return {
    kind: 'iso',
    tile,
    project(tx, ty) {
      return { x: (tx - ty) * hw, y: (tx + ty) * hh }
    },
    unproject(x, y) {
      // x/W = (tx−ty)/2, y/H = (tx+ty)/2 → tx = sum, ty = difference.
      const a = x / tile.w
      const b = y / tile.h
      return { tx: b + a, ty: b - a }
    },
    depthOf(tx, ty) {
      return (tx + ty) * hh
    },
    screenAABB(box) {
      const c = [
        { tx: box.x, ty: box.y },
        { tx: box.x + box.w, ty: box.y },
        { tx: box.x, ty: box.y + box.h },
        { tx: box.x + box.w, ty: box.y + box.h },
      ].map((p) => ({ x: (p.tx - p.ty) * hw, y: (p.tx + p.ty) * hh }))
      return {
        x0: Math.min(c[0].x, c[1].x, c[2].x, c[3].x),
        y0: Math.min(c[0].y, c[1].y, c[2].y, c[3].y),
        x1: Math.max(c[0].x, c[1].x, c[2].x, c[3].x),
        y1: Math.max(c[0].y, c[1].y, c[2].y, c[3].y),
      }
    },
  }
}

const TOPDOWN = topdownProjection()
const ISO = isoProjection()

/** The kernel for a projection kind (frozen singletons — no per-call alloc). */
export function projectionFor(kind: ProjectionKind): Projection {
  return kind === 'iso' ? ISO : TOPDOWN
}

// ── the ground footprint — ONE definition, shared with the still renderer ──

/**
 * The ground diamond a sprite stands on, from its DRAWN size.
 *
 * world-pack.json's own note, verbatim:
 *   "Sprites are unscaled in the atlas and drawn at dw/dh, an INTEGER
 *    fraction of native, so the pixel grid survives. Anchor is the base
 *    centre. Ground footprint is a diamond of half-width dw*0.42 and depth
 *    min(dh*0.55, dw*0.55) — the same geometry the placement rules and the
 *    checks use; a fourth definition would produce a fourth bug."
 *
 * checks/world_checks.py ground_box() floors the depth at 6px; that floor is
 * part of the shared geometry and is reproduced here. projection.test.ts pins
 * this function against the note string parsed out of the SHIPPED pack, so the
 * engine and the offline checks cannot drift apart silently — the note is the
 * contract, and a check that merely restates the code would guard nothing.
 */
export function groundDiamond(dw: number, dh: number): { hw: number; depth: number } {
  return { hw: dw * 0.42, depth: Math.max(6, Math.min(dh * 0.55, dw * 0.55)) }
}

/**
 * The ground diamond's px AABB around a base-centre point — EXACTLY
 * checks/world_checks.py ground_box(x, y, w, h) = (x−hw, y−depth, x+hw, y).
 * The base centre is the diamond's FRONT (bottom) vertex; the footprint
 * extends up-screen (behind the anchor) by `depth`.
 */
export function groundBox(baseX: number, baseY: number, dw: number, dh: number): PxBox {
  const g = groundDiamond(dw, dh)
  return { x0: baseX - g.hw, y0: baseY - g.depth, x1: baseX + g.hw, y1: baseY }
}

/**
 * Overlap of two ground boxes as a fraction of the SMALLER box — the same
 * measure checks/world_checks.py overlap_frac() uses, so the live world and
 * the still renderer are held to one standard and one number.
 */
export function groundOverlap(a: PxBox, b: PxBox): number {
  const ix = Math.min(a.x1, b.x1) - Math.max(a.x0, b.x0)
  const iy = Math.min(a.y1, b.y1) - Math.max(a.y0, b.y0)
  if (ix <= 0 || iy <= 0) return 0
  const aa = Math.max(1, (a.x1 - a.x0) * (a.y1 - a.y0))
  const ab = Math.max(1, (b.x1 - b.x0) * (b.y1 - b.y0))
  return (ix * iy) / Math.min(aa, ab)
}

/**
 * Is a px point inside a sprite's ground DIAMOND (not its box)? The pick
 * geometry — a diamond, because that is what the sprite actually stands on.
 * The diamond's bottom vertex is the base centre; its top vertex sits
 * `depth` up-screen; its side vertices sit at ±hw, half a depth up.
 */
export function pointInGround(
  px: number,
  py: number,
  baseX: number,
  baseY: number,
  dw: number,
  dh: number
): boolean {
  const g = groundDiamond(dw, dh)
  const cy = baseY - g.depth / 2
  const dx = Math.abs(px - baseX) / g.hw
  const dy = Math.abs(py - cy) / (g.depth / 2)
  return dx + dy <= 1
}

// ── camera: pure scale + translate, one definition ─────────────────────────

/** The continuous camera (world-tile centre + zoom) — mirrors lod.EngineCamera. */
export interface CameraLike {
  z: number
  x: number
  y: number
}

/** Viewport size in SCREEN px (renderer px — convert once at the DOM edge). */
export interface ViewportPx {
  w: number
  h: number
}

/**
 * The world Container's position for a camera: the camera is a pure
 * scale+translate over the ONE world container, forever. (This is also what
 * keeps the glow layer's copy-the-world-transform trick working.)
 */
export function cameraTranslation(
  proj: Projection,
  cam: CameraLike,
  vp: ViewportPx
): WorldPoint {
  const o = proj.project(cam.x, cam.y)
  return { x: vp.w / 2 - o.x * cam.z, y: vp.h / 2 - o.y * cam.z }
}

/** World tile → screen px under a centered camera. */
export function worldToScreen(
  proj: Projection,
  wx: number,
  wy: number,
  cam: CameraLike,
  vp: ViewportPx
): WorldPoint {
  const d = proj.project(wx - cam.x, wy - cam.y)
  return { x: vp.w / 2 + d.x * cam.z, y: vp.h / 2 + d.y * cam.z }
}

/** Screen px → world tile under a centered camera (the ONE hit-test inverse). */
export function screenToWorld(
  proj: Projection,
  sx: number,
  sy: number,
  cam: CameraLike,
  vp: ViewportPx
): { x: number; y: number } {
  const d = proj.unproject((sx - vp.w / 2) / cam.z, (sy - vp.h / 2) / cam.z)
  return { x: d.tx + cam.x, y: d.ty + cam.y }
}

/**
 * A screen-px DRAG delta as a world-tile delta. Under iso a screen drag must
 * walk the inverse iso basis or the camera slides diagonally under the
 * cursor; under top-down it is the same division it always was.
 */
export function screenDeltaToTiles(
  proj: Projection,
  dx: number,
  dy: number,
  z: number
): TilePoint {
  return proj.unproject(dx / z, dy / z)
}
