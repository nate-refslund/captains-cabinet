/**
 * The projection kernel's pins.
 *
 * WHY THIS FILE EXISTS AT ALL, stated because the gap is the lesson: until it
 * was written, projection.ts's own doc comments claimed "pinned by the
 * bit-for-bit tests below" and cited "projection.test.ts's calibration block" —
 * and no such file existed. The ISO_TILE comment even recorded that the
 * constant had ONCE cited a test that did not exist, while itself citing a test
 * that did not exist. A constant pinned by a docstring is pinned by nothing.
 *
 * What is pinned here, and why each arm can fail:
 *   1. the top-down kernel reproduces the legacy `t * TILE` arithmetic BIT FOR
 *      BIT, which is the whole proof that rewiring ~100 call sites in
 *      engine-canvas changed nothing;
 *   2. both kernels round-trip exactly enough to hit-test with;
 *   3. depth is the projected base y in both — the value the renderer's one
 *      sortableChildren layer already sorts on;
 *   4. groundDiamond IS world-pack.json's own note, parsed out of the SHIPPED
 *      pack rather than restated here (a check that restates the code guards
 *      nothing);
 *   5. ISO_TILE is 2:1 with whole-pixel halves, agreeing with the pack's own
 *      `projection` declaration and with iso-layout's ISO_AXIS_SLOPE.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import {
  cameraTranslation,
  DEFAULT_PROJECTION,
  groundBox,
  groundDiamond,
  groundOverlap,
  ISO_BASE,
  ISO_TILE,
  pointInGround,
  projectionFor,
  projectionFromParam,
  screenDeltaToTiles,
  screenToWorld,
  TOPDOWN_TILE,
  worldScale,
  worldToScreen,
} from './projection'
import { ISO_AXIS_SLOPE } from './iso-layout'
import { TILE } from './layout'

const PACK_PATH = path.resolve(
  __dirname,
  '..',
  '..',
  '..',
  'public',
  'world-assets',
  'originals',
  'iso',
  'world-pack.json'
)

/** Fixture grid: integers, halves, negatives, and the canvas extremes. */
const SAMPLES = [
  0, 1, 2, 3, 7, 15, 16, 17, 31, 63, 64, 119, 120, 191, 192, 239, 240, -1, -7, -24,
  0.5, 1.25, 2.75, 33.4, 96.125, -3.5, 1e-3, 1e6,
]

describe('projection — the ONE world→screen kernel', () => {
  it('DEFAULT_PROJECTION starts top-down so the port lands invisible', () => {
    expect(DEFAULT_PROJECTION).toBe('topdown')
  })

  it('?iso selects in BOTH directions, absent falls to the default', () => {
    expect(projectionFromParam('1')).toBe('iso')
    expect(projectionFromParam('true')).toBe('iso')
    expect(projectionFromParam('0')).toBe('topdown')
    expect(projectionFromParam('false')).toBe('topdown')
    expect(projectionFromParam(undefined)).toBe(DEFAULT_PROJECTION)
    expect(projectionFromParam(null)).toBe(DEFAULT_PROJECTION)
    expect(projectionFromParam('yes')).toBe(DEFAULT_PROJECTION)
    // Next hands repeated params as arrays; the first one wins.
    expect(projectionFromParam(['1', '0'])).toBe('iso')
    // …and the EXPLICIT arms are exercised against the OTHER default, because
    // with the default at 'topdown' a broken ?iso=0 branch answers correctly by
    // accident — right up to the day the default flips.
    expect(projectionFromParam('0', 'iso')).toBe('topdown')
    expect(projectionFromParam('false', 'iso')).toBe('topdown')
    expect(projectionFromParam('1', 'iso')).toBe('iso')
    expect(projectionFromParam(undefined, 'iso')).toBe('iso')
    expect(projectionFromParam('yes', 'iso')).toBe('iso')
  })

  it('1. topdown reproduces the legacy `t * TILE` arithmetic BIT FOR BIT', () => {
    const p = projectionFor('topdown')
    expect(TOPDOWN_TILE.w).toBe(TILE)
    expect(TOPDOWN_TILE.h).toBe(TILE)
    for (const tx of SAMPLES) {
      for (const ty of SAMPLES) {
        const got = p.project(tx, ty)
        // Object.is, not toBe-with-tolerance: this is an exactness claim.
        expect(Object.is(got.x, tx * TILE)).toBe(true)
        expect(Object.is(got.y, ty * TILE)).toBe(true)
        expect(Object.is(p.depthOf(tx, ty), ty * TILE)).toBe(true)
      }
    }
  })

  it('1b. topdown screenAABB reproduces the legacy rect arithmetic exactly', () => {
    const p = projectionFor('topdown')
    for (const x of SAMPLES.slice(0, 12)) {
      for (const w of [1, 2, 4, 6, 0.5]) {
        const box = p.screenAABB({ x, y: x + 3, w, h: w + 1 })
        expect(Object.is(box.x0, x * TILE)).toBe(true)
        expect(Object.is(box.x1, (x + w) * TILE)).toBe(true)
        expect(Object.is(box.y0, (x + 3) * TILE)).toBe(true)
        expect(Object.is(box.y1, (x + 3 + w + 1) * TILE)).toBe(true)
      }
    }
  })

  it('1c. the topdown camera math is the legacy camera math, unscaled', () => {
    const p = projectionFor('topdown')
    const vp = { w: 1024, h: 640 }
    for (const cam of [
      { z: 1, x: 120, y: 32 },
      { z: 0.25, x: 0, y: 0 },
      { z: 3, x: 87.5, y: 191 },
    ]) {
      // ISO_BASE must NEVER reach the top-down path.
      expect(Object.is(worldScale(p, cam.z), cam.z)).toBe(true)
      const t = cameraTranslation(p, cam, vp)
      expect(Object.is(t.x, vp.w / 2 - cam.x * TILE * cam.z)).toBe(true)
      expect(Object.is(t.y, vp.h / 2 - cam.y * TILE * cam.z)).toBe(true)
      // …and the hit-test inverse is the one engine-canvas hand-rolled.
      for (const [sx, sy] of [[0, 0], [512, 320], [1023, 639]] as const) {
        const w = screenToWorld(p, sx, sy, cam, vp)
        expect(Object.is(w.x, (sx - vp.w / 2) / (TILE * cam.z) + cam.x)).toBe(true)
        expect(Object.is(w.y, (sy - vp.h / 2) / (TILE * cam.z) + cam.y)).toBe(true)
      }
      // …and the drag inverse is the one engine-client hand-rolled.
      const d = screenDeltaToTiles(p, 37, -19, cam.z)
      expect(Object.is(d.tx, 37 / (TILE * cam.z))).toBe(true)
      expect(Object.is(d.ty, -19 / (TILE * cam.z))).toBe(true)
    }
  })

  it('2. both kernels round-trip project/unproject', () => {
    for (const kind of ['topdown', 'iso'] as const) {
      const p = projectionFor(kind)
      for (const tx of SAMPLES) {
        for (const ty of SAMPLES) {
          const back = p.unproject(p.project(tx, ty).x, p.project(tx, ty).y)
          expect(back.tx).toBeCloseTo(tx, 9)
          expect(back.ty).toBeCloseTo(ty, 9)
        }
      }
    }
  })

  it('2b. worldToScreen and screenToWorld invert each other under both kernels', () => {
    const vp = { w: 1280, h: 720 }
    for (const kind of ['topdown', 'iso'] as const) {
      const p = projectionFor(kind)
      for (const cam of [
        { z: 1, x: 30, y: 12 },
        { z: 0.4, x: -5, y: 60 },
        { z: 2.5, x: 56.67, y: 6.67 },
      ]) {
        for (const [wx, wy] of [[0, 0], [30, 12], [61.5, -8.25]] as const) {
          const s = worldToScreen(p, wx, wy, cam, vp)
          const back = screenToWorld(p, s.x, s.y, cam, vp)
          expect(back.x).toBeCloseTo(wx, 6)
          expect(back.y).toBeCloseTo(wy, 6)
        }
      }
    }
  })

  it('3. depth is the projected base y in both kernels', () => {
    for (const kind of ['topdown', 'iso'] as const) {
      const p = projectionFor(kind)
      for (const tx of SAMPLES) {
        for (const ty of SAMPLES) {
          expect(p.depthOf(tx, ty)).toBeCloseTo(p.project(tx, ty).y, 9)
        }
      }
    }
    // …and under iso a step along EITHER ground axis moves depth forward,
    // which is what makes a base-y sort an occlusion order.
    const iso = projectionFor('iso')
    expect(iso.depthOf(5, 5)).toBeGreaterThan(iso.depthOf(4, 5))
    expect(iso.depthOf(5, 5)).toBeGreaterThan(iso.depthOf(5, 4))
  })

  it('3b. iso screenAABB spans all FOUR projected corners, not two', () => {
    const p = projectionFor('iso')
    const box = { x: 2, y: 5, w: 3, h: 7 }
    const corners = [
      p.project(box.x, box.y),
      p.project(box.x + box.w, box.y),
      p.project(box.x, box.y + box.h),
      p.project(box.x + box.w, box.y + box.h),
    ]
    const aabb = p.screenAABB(box)
    expect(aabb.x0).toBeCloseTo(Math.min(...corners.map((c) => c.x)), 9)
    expect(aabb.x1).toBeCloseTo(Math.max(...corners.map((c) => c.x)), 9)
    expect(aabb.y0).toBeCloseTo(Math.min(...corners.map((c) => c.y)), 9)
    expect(aabb.y1).toBeCloseTo(Math.max(...corners.map((c) => c.y)), 9)
    // the degenerate end: a zero-extent box is a point, not an inverted rect
    const dot = p.screenAABB({ x: 4, y: 4, w: 0, h: 0 })
    expect(dot.x0).toBe(dot.x1)
    expect(dot.y0).toBe(dot.y1)
  })

  it('4. groundDiamond IS the SHIPPED pack note, parsed — not restated here', () => {
    const pack = JSON.parse(fs.readFileSync(PACK_PATH, 'utf8')) as { note: string }
    const note = pack.note
    // half-width dw*0.42
    const hw = note.match(/half-width\s+dw\*([0-9.]+)/)
    // depth min(dh*0.55, dw*0.55)
    const depth = note.match(/depth\s+min\(dh\*([0-9.]+),\s*dw\*([0-9.]+)\)/)
    expect(hw, `pack note no longer states a half-width: ${note}`).not.toBeNull()
    expect(depth, `pack note no longer states a depth: ${note}`).not.toBeNull()
    const kHw = Number(hw![1])
    const kDh = Number(depth![1])
    const kDw = Number(depth![2])
    for (const [dw, dh] of [
      [196, 174],
      [159, 149],
      [43, 48],
      [15, 15],
      [107, 125],
      [30, 37],
    ] as const) {
      const g = groundDiamond(dw, dh)
      expect(g.hw).toBeCloseTo(dw * kHw, 9)
      // the 6px floor is checks/world_checks.py ground_box()'s and is part of
      // the shared geometry — stated here because the note does not carry it
      expect(g.depth).toBeCloseTo(Math.max(6, Math.min(dh * kDh, dw * kDw)), 9)
    }
    // the floor is REACHED by real pack geometry, so it is not dead code
    expect(groundDiamond(10, 10).depth).toBe(6)
  })

  it('4b. groundBox is checks/world_checks.py ground_box, and overlap is of the SMALLER', () => {
    const b = groundBox(100, 200, 50, 40)
    const g = groundDiamond(50, 40)
    expect(b).toEqual({ x0: 100 - g.hw, y0: 200 - g.depth, x1: 100 + g.hw, y1: 200 })
    // a box entirely inside another overlaps the SMALLER one fully (1.0),
    // which is the measure the offline checks use
    const big = { x0: 0, y0: 0, x1: 100, y1: 100 }
    const small = { x0: 10, y0: 10, x1: 20, y1: 20 }
    expect(groundOverlap(big, small)).toBeCloseTo(1, 9)
    expect(groundOverlap(small, big)).toBeCloseTo(1, 9)
    // …and disjoint boxes overlap zero, including edge-touching ones
    expect(groundOverlap(small, { x0: 20, y0: 10, x1: 30, y1: 20 })).toBe(0)
  })

  it('4c. pointInGround picks the DIAMOND, not its box', () => {
    const dw = 100
    const dh = 100
    const g = groundDiamond(dw, dh)
    // base centre is the front vertex — on the diamond's boundary
    expect(pointInGround(0, 0, 0, 0, dw, dh)).toBe(true)
    // the box corner is OUTSIDE the diamond (this is the whole point)
    expect(pointInGround(g.hw - 0.5, -g.depth + 0.5, 0, 0, dw, dh)).toBe(false)
    // the centre of the diamond is inside
    expect(pointInGround(0, -g.depth / 2, 0, 0, dw, dh)).toBe(true)
    // …and a point below the base is outside
    expect(pointInGround(0, 2, 0, 0, dw, dh)).toBe(false)
  })

  it('5. ISO_TILE is 2:1 with whole-pixel halves, and everything agrees', () => {
    expect(ISO_TILE.w).toBe(2 * ISO_TILE.h)
    expect(ISO_TILE.w % 2).toBe(0)
    expect(ISO_TILE.h % 2).toBe(0)
    // iso-layout routes driveways along this slope; a second notion of the
    // grid is the defect class that cost three placement bugs
    expect(ISO_AXIS_SLOPE).toBe(ISO_TILE.h / ISO_TILE.w)
    expect(ISO_AXIS_SLOPE).toBe(0.5)
    // the SHIPPED pack declares the geometry its art was drawn in; the grid
    // must be the geometry the art is drawn in or every sprite sits askew
    const pack = JSON.parse(fs.readFileSync(PACK_PATH, 'utf8')) as { projection: string }
    expect(pack.projection).toMatch(/2:1/)
    expect(pack.projection).toMatch(/isometric/i)
  })

  it('5b. ISO_BASE re-bases scale so z keeps its meaning across kernels', () => {
    const iso = projectionFor('iso')
    // z=3 lands on the pack's native pixels at the close tier
    expect(worldScale(iso, 3)).toBeCloseTo(1, 9)
    // an iso tile at z=1 covers the same screen width as a top-down tile does
    expect(ISO_TILE.w * ISO_BASE).toBeCloseTo(TOPDOWN_TILE.w, 9)
  })

  it('5c. the iso camera translation and its inverse use the SAME scale', () => {
    const iso = projectionFor('iso')
    const vp = { w: 1000, h: 800 }
    const cam = { z: 1.7, x: 56.67, y: 6.67 }
    // the camera's own centre must land at the centre of the viewport
    const s = worldToScreen(iso, cam.x, cam.y, cam, vp)
    expect(s.x).toBeCloseTo(vp.w / 2, 9)
    expect(s.y).toBeCloseTo(vp.h / 2, 9)
    // …and the world container translation puts it there too
    const t = cameraTranslation(iso, cam, vp)
    const o = iso.project(cam.x, cam.y)
    const sc = worldScale(iso, cam.z)
    expect(t.x + o.x * sc).toBeCloseTo(vp.w / 2, 9)
    expect(t.y + o.y * sc).toBeCloseTo(vp.h / 2, 9)
    // a drag of one viewport-width must move the camera by the tiles that
    // width covers — the arm that catches a pan inverse missing ISO_BASE
    const d = screenDeltaToTiles(iso, vp.w, 0, cam.z)
    const moved = iso.project(d.tx, d.ty)
    expect(moved.x).toBeCloseTo(vp.w / sc, 6)
    expect(moved.y).toBeCloseTo(0, 6)
  })
})
