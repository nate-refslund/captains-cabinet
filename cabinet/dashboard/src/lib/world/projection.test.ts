/**
 * projection.ts — the ONE world→screen kernel.
 *
 * The load-bearing assertion of iso-port step 1 is NEGATIVE: rewiring the
 * five copies of the transform through this module must reproduce the legacy
 * arithmetic BIT FOR BIT, or "nothing visible changed" is a claim rather than
 * a fact. Every legacy expression below is transcribed verbatim from the site
 * it replaced, with the file:line it came from, and compared with
 * toBe() (Object.is — no epsilon, no rounding slack).
 */
import { describe, expect, it } from 'vitest'
import {
  cameraTranslation,
  DEFAULT_PROJECTION,
  groundBox,
  groundDiamond,
  groundOverlap,
  ISO_TILE,
  pointInGround,
  projectionFor,
  screenDeltaToTiles,
  screenToWorld,
  TOPDOWN_TILE,
  worldToScreen,
} from './projection'
import { TILE } from './layout'

const TD = projectionFor('topdown')
const ISO = projectionFor('iso')

/** A fixture grid that covers negatives, fractions and the island band. */
const GRID: Array<[number, number]> = []
for (const tx of [-24, -0.5, 0, 1, 3.1, 16.5, 117, 120.75, 240]) {
  for (const ty of [-24, -0.5, 0, 1, 2.1, 19.5, 96, 150.25, 192]) {
    GRID.push([tx, ty])
  }
}

describe('projection — the single kernel', () => {
  it('starts in top-down so the port lands invisible', () => {
    expect(DEFAULT_PROJECTION).toBe('topdown')
  })

  it('the top-down tile IS the engine tile (layout.TILE) — one grid, not two', () => {
    expect(TOPDOWN_TILE.w).toBe(TILE)
    expect(TOPDOWN_TILE.h).toBe(TILE)
  })

  // The original assertion here demanded both tile sizes be POWERS OF TWO, which the
  // measured iso tile (48x24) is not, and never needed to be. What actually has to hold
  // is that half a tile is a whole pixel — an iso projection adds tile/2 terms, and a
  // fractional half-tile would put sprites on sub-pixel positions and destroy the very
  // pixel grid the integer display scale exists to protect.
  it('half a tile is a whole pixel in both grids — no sub-pixel placement', () => {
    for (const n of [TOPDOWN_TILE.w, TOPDOWN_TILE.h, ISO_TILE.w, ISO_TILE.h]) {
      expect(n % 2).toBe(0)
    }
  })

  it('the iso grid is 2:1 (the projection world-pack.json declares)', () => {
    expect(ISO_TILE.w).toBe(2 * ISO_TILE.h)
  })
})

describe('top-down kernel reproduces the legacy arithmetic exactly', () => {
  it('project() == the inline `tx * TILE` / `ty * TILE` sites', () => {
    for (const [tx, ty] of GRID) {
      const p = TD.project(tx, ty)
      expect(p.x).toBe(tx * TILE)
      expect(p.y).toBe(ty * TILE)
    }
  })

  it('depthOf() == the inline `zIndex = y * TILE` sites', () => {
    for (const [tx, ty] of GRID) {
      expect(TD.depthOf(tx, ty)).toBe(ty * TILE)
    }
  })

  it('screenAABB() == the inline footprint rect (engine-canvas buildFootprints)', () => {
    const box = { x: 117, y: 17, w: 6, h: 5 }
    const r = TD.screenAABB(box)
    // engine-canvas.tsx:987 — g.rect(b.x*TILE, b.y*TILE, b.w*TILE, b.h*TILE)
    expect(r.x0).toBe(box.x * TILE)
    expect(r.y0).toBe(box.y * TILE)
    expect(r.x1 - r.x0).toBe(box.w * TILE)
    expect(r.y1 - r.y0).toBe(box.h * TILE)
  })

  it('cameraTranslation() == engine-canvas.tsx:1482-1485', () => {
    const vp = { w: 1440, h: 900 }
    for (const cam of [
      { z: 1, x: 120, y: 96 },
      { z: 3, x: 120.75, y: 19.5 },
      { z: 0.25, x: -24, y: 150.25 },
    ]) {
      const t = cameraTranslation(TD, cam, vp)
      expect(t.x).toBe(vp.w / 2 - cam.x * TILE * cam.z)
      expect(t.y).toBe(vp.h / 2 - cam.y * TILE * cam.z)
    }
  })

  it('worldToScreen() == engine-client.tsx project() and lod.ts screenRect', () => {
    const vp = { w: 1440, h: 900 }
    for (const cam of [
      { z: 1, x: 120, y: 96 },
      { z: 3, x: 120.75, y: 19.5 },
      { z: 0.375, x: 40, y: 150 },
    ]) {
      for (const [wx, wy] of GRID) {
        const s = worldToScreen(TD, wx, wy, cam, vp)
        // engine-client.tsx:689-693
        expect(s.x).toBe(vp.w / 2 + (wx - cam.x) * TILE * cam.z)
        expect(s.y).toBe(vp.h / 2 + (wy - cam.y) * TILE * cam.z)
        // lod.ts:140-146 — const s = TILE_PX * cam.z; vp.w/2 + (b.x-cam.x)*s
        const legacyScale = TILE * cam.z
        expect(s.x).toBe(vp.w / 2 + (wx - cam.x) * legacyScale)
        expect(s.y).toBe(vp.h / 2 + (wy - cam.y) * legacyScale)
      }
    }
  })

  it('screenToWorld() == engine-canvas.tsx hitTarget (:1509-1510)', () => {
    const vp = { w: 1440, h: 900 }
    for (const cam of [
      { z: 1, x: 120, y: 96 },
      { z: 2.75, x: 117.5, y: 19.5 },
      { z: 0.25, x: -3.5, y: 191.75 },
    ]) {
      for (const sx of [0, 1, 719, 720.5, 1439]) {
        for (const sy of [0, 13, 450.25, 899]) {
          const w = screenToWorld(TD, sx, sy, cam, vp)
          expect(w.x).toBe((sx - vp.w / 2) / (TILE * cam.z) + cam.x)
          expect(w.y).toBe((sy - vp.h / 2) / (TILE * cam.z) + cam.y)
        }
      }
    }
  })

  it('screenDeltaToTiles() == engine-client.tsx pan (:605-606)', () => {
    for (const z of [0.25, 1, 2.75, 3]) {
      for (const dx of [-311, -5, 0, 7, 640]) {
        for (const dy of [-207, -5, 0, 9, 400]) {
          const t = screenDeltaToTiles(TD, dx, dy, z)
          expect(t.tx).toBe(dx / (TILE * z))
          expect(t.ty).toBe(dy / (TILE * z))
        }
      }
    }
  })
})

describe('round trips', () => {
  it('unproject(project(p)) == p in both kernels', () => {
    for (const proj of [TD, ISO]) {
      for (const [tx, ty] of GRID) {
        const p = proj.project(tx, ty)
        const back = proj.unproject(p.x, p.y)
        expect(back.tx).toBeCloseTo(tx, 10)
        expect(back.ty).toBeCloseTo(ty, 10)
      }
    }
  })

  it('screenToWorld(worldToScreen(p)) == p in both kernels', () => {
    const vp = { w: 1440, h: 900 }
    const cam = { z: 1.75, x: 120, y: 96 }
    for (const proj of [TD, ISO]) {
      for (const [tx, ty] of GRID) {
        const s = worldToScreen(proj, tx, ty, cam, vp)
        const back = screenToWorld(proj, s.x, s.y, cam, vp)
        expect(back.x).toBeCloseTo(tx, 8)
        expect(back.y).toBeCloseTo(ty, 8)
      }
    }
  })
})

describe('depth is monotone along both walk directions', () => {
  it('a step toward the camera never sorts behind where it started', () => {
    for (const proj of [TD, ISO]) {
      for (const [tx, ty] of GRID) {
        // +ty is "south" (toward the viewer) in both kernels
        expect(proj.depthOf(tx, ty + 1)).toBeGreaterThan(proj.depthOf(tx, ty))
      }
    }
  })

  it('iso depth also advances along +tx (top-down deliberately does not)', () => {
    for (const [tx, ty] of GRID) {
      expect(ISO.depthOf(tx + 1, ty)).toBeGreaterThan(ISO.depthOf(tx, ty))
      expect(TD.depthOf(tx + 1, ty)).toBe(TD.depthOf(tx, ty))
    }
  })

  it('depth IS the projected base y — one value, not a parallel notion', () => {
    for (const proj of [TD, ISO]) {
      for (const [tx, ty] of GRID) {
        expect(proj.depthOf(tx, ty)).toBe(proj.project(tx, ty).y)
      }
    }
  })
})

describe('the ground diamond — one footprint definition', () => {
  it('matches world-pack.json / world_checks.ground_box exactly', () => {
    // barn: dw 159, dh 149 (world-pack.json frames.barn)
    const g = groundDiamond(159, 149)
    expect(g.hw).toBe(159 * 0.42)
    expect(g.depth).toBe(Math.min(149 * 0.55, 159 * 0.55))
    // a sliver sprite floors at 6px depth, like the python
    expect(groundDiamond(4, 4).depth).toBe(6)
  })

  it('groundBox == (x−hw, y−depth, x+hw, y) — the python tuple, in order', () => {
    const b = groundBox(100, 200, 159, 149)
    const g = groundDiamond(159, 149)
    expect(b.x0).toBe(100 - g.hw)
    expect(b.y0).toBe(200 - g.depth)
    expect(b.x1).toBe(100 + g.hw)
    expect(b.y1).toBe(200)
  })

  it('groundOverlap == overlap_frac (fraction of the SMALLER box)', () => {
    const a = { x0: 0, y0: 0, x1: 10, y1: 10 }
    const b = { x0: 5, y0: 5, x1: 25, y1: 25 }
    expect(groundOverlap(a, b)).toBeCloseTo(25 / 100, 12)
    expect(groundOverlap(a, { x0: 100, y0: 100, x1: 110, y1: 110 })).toBe(0)
    expect(groundOverlap(a, a)).toBe(1)
  })

  it('pointInGround picks a diamond, not a rect — corners are OUTSIDE', () => {
    const [bx, by, dw, dh] = [0, 0, 100, 100]
    const g = groundDiamond(dw, dh)
    expect(pointInGround(bx, by, bx, by, dw, dh)).toBe(true) // front vertex
    expect(pointInGround(bx, by - g.depth, bx, by, dw, dh)).toBe(true) // back
    expect(pointInGround(bx - g.hw, by - g.depth / 2, bx, by, dw, dh)).toBe(true)
    expect(pointInGround(bx + g.hw, by - g.depth / 2, bx, by, dw, dh)).toBe(true)
    // the box corner: inside the AABB, outside the diamond
    const box = groundBox(bx, by, dw, dh)
    expect(pointInGround(box.x0, box.y0, bx, by, dw, dh)).toBe(false)
    expect(pointInGround(box.x1, box.y1, bx, by, dw, dh)).toBe(false)
  })
})

describe('iso kernel', () => {
  it('is 2:1 — a tile step east and a tile step south mirror each other', () => {
    const e = ISO.project(1, 0)
    const s = ISO.project(0, 1)
    expect(e.x).toBe(ISO_TILE.w / 2)
    expect(e.y).toBe(ISO_TILE.h / 2)
    expect(s.x).toBe(-ISO_TILE.w / 2)
    expect(s.y).toBe(ISO_TILE.h / 2)
  })

  it('the origin is the origin (no hidden offset)', () => {
    expect(ISO.project(0, 0)).toEqual({ x: 0, y: 0 })
    expect(TD.project(0, 0)).toEqual({ x: 0, y: 0 })
  })

  it('screenAABB spans all four projected corners, not two', () => {
    const box = { x: 0, y: 0, w: 6, h: 5 }
    const r = ISO.screenAABB(box)
    expect(r.x0).toBe(ISO.project(0, 5).x) // west corner
    expect(r.x1).toBe(ISO.project(6, 0).x) // east corner
    expect(r.y0).toBe(ISO.project(0, 0).y) // north corner
    expect(r.y1).toBe(ISO.project(6, 5).y) // south corner
  })
})

/**
 * THE GUARDS THE DOCSTRINGS CLAIMED BUT DID NOT HAVE.
 *
 * A review mutated ISO_TILE to {16,8} — the value the calibration REJECTED — and to
 * {64,32}, and all 23 tests stayed green. The constant's docstring cited a calibration
 * test that did not exist, and groundDiamond's cited a pack test that did not exist. A
 * claimed guard that is absent is worse than no guard: it reads as evidence.
 *
 * These read the SHIPPED pack rather than restating the code, so a check cannot pass by
 * agreeing with the thing it is checking.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const PACK_DIR = '/Users/nate/cabinet-meta/designs/world-pack'
const pack = JSON.parse(readFileSync(join(PACK_DIR, 'world-pack.json'), 'utf8')) as {
  note: string
  frames: Record<string, { dw: number; dh: number; anchor: [number, number]; scale: number }>
}

describe('ISO_TILE is pinned by the shipped pack, not by assertion', () => {
  const frames = Object.values(pack.frames)

  it('the pack is real and non-trivial', () => {
    expect(frames.length).toBeGreaterThan(100)
  })

  it('48x24 fits the structures; the rejected 16x8 does not', () => {
    // A structure must not need more than ~4 tile steps of ground, or the lattice
    // spacing the anchors were authored for cannot hold them apart. The largest frames
    // are the manors and warehouses at ~200px.
    const widest = Math.max(...frames.map((f) => f.dw))
    expect(widest).toBeGreaterThan(150)

    const stepsAt = (tileW: number) => {
      const hw = widest * 0.42
      return (hw * 2) / tileW
    }
    expect(stepsAt(ISO_TILE.w)).toBeLessThanOrEqual(4)
    expect(stepsAt(16)).toBeGreaterThan(4) // the size the calibration rejected
  })

  it('half an iso tile is a whole pixel — the kernel adds tile/2 terms', () => {
    expect(ISO_TILE.w % 2).toBe(0)
    expect(ISO_TILE.h % 2).toBe(0)
  })

  it('the iso grid is 2:1, which the pack declares as its projection', () => {
    expect(ISO_TILE.w).toBe(2 * ISO_TILE.h)
  })
})

describe('groundDiamond is pinned against the shipped pack NOTE, not against itself', () => {
  it('the note still states the formula this module implements', () => {
    // If the pack's contract ever changes wording or numbers, this fails and someone
    // has to reconcile the two — which is the entire point of quoting it.
    expect(pack.note).toContain('half-width dw*0.42')
    expect(pack.note).toContain('min(dh*0.55, dw*0.55)')
    expect(pack.note).toContain('base')
  })

  it('every frame in the pack anchors at its BASE CENTRE', () => {
    for (const [name, f] of Object.entries(pack.frames)) {
      expect(`${name}:${f.anchor[0]}`).toBe(`${name}:${f.dw / 2}`)
      expect(`${name}:${f.anchor[1]}`).toBe(`${name}:${f.dh}`)
    }
  })

  it('the implementation reproduces the note for real pack frames', () => {
    for (const f of Object.values(pack.frames).slice(0, 40)) {
      const g = groundDiamond(f.dw, f.dh)
      expect(g.hw).toBeCloseTo(f.dw * 0.42, 10)
      expect(g.depth).toBeCloseTo(Math.max(6, Math.min(f.dh * 0.55, f.dw * 0.55)), 10)
    }
  })

  it('display size is an INTEGER fraction of native — the pixel-grid promise', () => {
    for (const [name, f] of Object.entries(pack.frames)) {
      expect(`${name}:${Number.isInteger(f.scale)}`).toBe(`${name}:true`)
      expect(f.scale).toBeGreaterThanOrEqual(1)
    }
  })
})

describe('the camera stays a pure scale+translate', () => {
  it('worldToScreen == cameraTranslation + projected*z, in both kernels', () => {
    // This is the property that makes "iso is applied per object, never to the
    // container" safe. It was asserted in prose and by nothing else.
    const vp = { w: 1280, h: 720 }
    for (const kind of ['topdown', 'iso'] as const) {
      const p = projectionFor(kind)
      for (const cam of [{ x: 0, y: 0, z: 1 }, { x: 13.5, y: -7.25, z: 2.5 }]) {
        const t = cameraTranslation(p, cam, vp)
        for (const tile of [{ x: 0, y: 0 }, { x: 40.5, y: -12.25 }, { x: -3, y: 88 }]) {
          const direct = worldToScreen(p, tile.x, tile.y, cam, vp)
          const abs = p.project(tile.x, tile.y)
          expect(direct.x).toBeCloseTo(t.x + abs.x * cam.z, 6)
          expect(direct.y).toBeCloseTo(t.y + abs.y * cam.z, 6)
        }
      }
    }
  })
})
