/**
 * blueprint.test.ts — the bridge's contract, and the arms that prove it is a
 * sensor rather than a restatement.
 *
 * The end-to-end arm (compose -> raster -> all twelve checks, plus six
 * mutations) lives in capture.test.ts, because it needs python and pixels.
 * Everything here is pure TypeScript and runs anywhere.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  composeFrame,
  DOCK_KIT_FRAMES,
  drawSizeOf,
  frameOfKind,
  justifiedFromState,
  packFootprints,
  resolveFrame,
  type WorldPack,
} from './blueprint'
import {
  composeLayout,
  DOCK_KIT,
  ellipseOfRegion,
  maxGroundOverlap,
  type LayoutState,
} from './iso-layout'
import { groundBox } from './projection'

const CAPTURE = join(process.cwd(), '..', 'scripts', 'world-capture')
const PACK: WorldPack = JSON.parse(
  readFileSync(
    join(process.cwd(), 'public', 'world-assets', 'originals', 'iso', 'world-pack.json'),
    'utf8'
  )
)

function fixture(name: string) {
  return JSON.parse(readFileSync(join(CAPTURE, 'states', `${name}.json`), 'utf8')) as {
    name: string
    seed: string
    date: string
    index: number
    state: LayoutState
  }
}

const HAMLET = fixture('hamlet')
const CAMP = fixture('camp')

const frameFor = (f: ReturnType<typeof fixture>) =>
  composeFrame(PACK, f.state, f.seed, { date: f.date, index: f.index })

describe('blueprint — the shape checks/world_checks.py reads', () => {
  it('emits every key the twelve checks index into, at the hamlet state', () => {
    const { blueprint: bp } = frameFor(HAMLET)
    expect(bp.canvas).toEqual([2400, 1760])
    // check_on_road, check_terrain: the exemption zones and the sweep targets
    expect(bp.plaza).toHaveLength(4)
    expect(bp.fields.length).toBeGreaterThan(0)
    for (const f of bp.fields) expect(f).toHaveLength(4)
    expect(bp.quay).toHaveLength(4)
    expect(bp.cove).toHaveLength(3)
    // check_terrain's lane arm walks these polylines
    expect(Object.keys(bp.lanes).length).toBeGreaterThan(4)
    for (const pts of Object.values(bp.lanes)) {
      expect(pts.length).toBeGreaterThan(1)
      for (const p of pts) expect(p).toHaveLength(2)
    }
    // check_stacking / check_on_road / check_paint_fidelity
    expect(bp.sprites.length).toBeGreaterThan(50)
    for (const s of bp.sprites) {
      expect(typeof s.n).toBe('string')
      for (const k of ['x', 'y', 'w', 'h'] as const) {
        expect(Number.isInteger(s[k])).toBe(true)
      }
      expect(s.w).toBeGreaterThan(0)
      expect(s.h).toBeGreaterThan(0)
    }
    // check_era / check_state_traceable / check_light
    expect(bp.state.era).toBe('hamlet')
    expect(bp.state.ladders.lighthouse_lamp).toEqual({ stage: 'lit', n: 0, measured: true })
    expect(Array.isArray(bp.state.justified)).toBe(true)
    expect(Array.isArray(bp.state.gaps)).toBe(true)
  })

  it('leaves `layers` EMPTY — paint order belongs to whatever paints', () => {
    // A guessed layer list would be a sensor wired to the wrong artifact:
    // check_depth_order would then be judging this module's opinion of the
    // paint order instead of the renderer's actual one.
    expect(frameFor(HAMLET).blueprint.layers).toEqual([])
  })

  it('every sprite name exists in the shipped pack', () => {
    for (const f of [HAMLET, CAMP]) {
      const missing = frameFor(f).blueprint.sprites
        .map((s) => s.n)
        .filter((n) => !(n in PACK.frames))
      expect(missing, `${f.name}: frames absent from the pack`).toEqual([])
    }
  })

  it('sprite w/h are the PACK drawn size, so the ground diamond is the real one', () => {
    for (const s of frameFor(HAMLET).blueprint.sprites) {
      expect({ n: s.n, w: s.w, h: s.h }).toEqual({ n: s.n, ...drawSizeOf(PACK, s.n)! })
    }
  })
})

describe('blueprint — justified is a sensor, not a restatement', () => {
  it('is derived from STATE, so an unentitled sprite would show as an orphan', () => {
    // The defect this guards: compose.py adds a name to JUSTIFIED in the same
    // breath as it places the sprite, so `drawn - justified` is empty by
    // construction and check_state_traceable can never fire. Removing the
    // count must remove the entitlement — if it does not, the set is being
    // read off the placements.
    const withOfficers = justifiedFromState(PACK, HAMLET.state)
    const none: LayoutState = { ...HAMLET.state, counts: { ...HAMLET.state.counts, officer_dwellings: 0 } }
    const withoutOfficers = justifiedFromState(PACK, none)
    expect(withOfficers).toContain('officer_house_a')
    expect(withoutOfficers).not.toContain('officer_house_a')

    const noWarehouse: LayoutState = { ...HAMLET.state, counts: { ...HAMLET.state.counts, warehouse: 0 } }
    expect(justifiedFromState(PACK, noWarehouse)).not.toContain('warehouse')
  })

  it('nature is NOT justified — it goes through the ambient list', () => {
    const j = justifiedFromState(PACK, HAMLET.state)
    for (const n of ['tree_oak', 'reeds', 'bush_round', 'flowers_pink']) {
      expect(j, `${n} must not be state-justified`).not.toContain(n)
    }
  })

  it('the ambient list covers every name the planting stages can emit', () => {
    // The list is hand-held on purpose (a generated one could never disagree
    // with the planter). This arm is what tells a human the day it falls behind.
    const allowed = new Set(
      readFileSync(join(CAPTURE, 'ambient-nature.txt'), 'utf8')
        .split('\n')
        .map((l) => l.trim())
        .filter((l) => l && !l.startsWith('#'))
    )
    for (const f of [HAMLET, CAMP]) {
      const { blueprint: bp } = frameFor(f)
      const justified = new Set(bp.state.justified)
      const orphans = [...new Set(bp.sprites.map((s) => s.n))]
        .filter((n) => !justified.has(n) && !allowed.has(n))
      expect(orphans, `${f.name}: drawn, neither justified nor ambient`).toEqual([])
    }
  })

  it('DOCK_KIT_FRAMES tracks the table that actually places the kit', () => {
    // The copy exists so entitlement does not follow placement; this pins the
    // two together so the copy cannot silently fall behind.
    const placed = DOCK_KIT.map((k) => k.kind).filter((k) => k !== 'cargo_stacks')
    expect([...DOCK_KIT_FRAMES].sort()).toEqual([...new Set(placed)].sort())
  })
})

describe('blueprint — the era vocabulary comes from the pack', () => {
  it('camp draws camp art for every built role', () => {
    const names = new Set(frameFor(CAMP).blueprint.sprites.map((s) => s.n))
    expect(names.has('camp_dark_cairn')).toBe(true)   // the unlit cairn, not a tower
    expect(names.has('camp_campfire')).toBe(true)     // not the stone firepit
    expect(names.has('camp_tent')).toBe(true)         // not a cottage
    for (const village of ['lighthouse', 'firepit', 'great_house', 'library', 'well']) {
      expect(names.has(village), `${village} must not appear at camp`).toBe(false)
    }
  })

  it('resolveFrame falls back to the era wildcard, never across eras', () => {
    expect(resolveFrame(PACK, 'library', 'camp', 'library_hall')).toBe('camp_book_crate')
    expect(resolveFrame(PACK, 'library', 'hamlet', 'library_hall')).toBe('library')
    expect(resolveFrame(PACK, 'nonesuch', 'hamlet', 'x')).toBeNull()
  })

  it('the dwelling row keeps its per-lot variety (the one KIND_IS_ERA_AWARE case)', () => {
    for (const k of ['officer_house_b', 'cottage_c']) {
      expect(frameOfKind(PACK, HAMLET.state, k)).toBe(k)
    }
    const houses = new Set(
      frameFor(HAMLET).blueprint.sprites
        .map((s) => s.n)
        .filter((n) => n.startsWith('officer_house') || n.startsWith('cottage'))
    )
    expect(houses.size, 'a row of identical roofs reads as a barracks').toBeGreaterThan(1)
  })

  it('every fixture rung is a real rung of that ladder', () => {
    // A fixture that invented a rung would be turning check_era's rung arm off
    // while appearing to exercise it.
    const yml = readFileSync(
      join(process.cwd(), '..', 'world', 'growth-ladders.yml'), 'utf8')
    for (const f of [HAMLET, CAMP]) {
      for (const [object, rung] of Object.entries(f.state.stages ?? {})) {
        if (!rung) continue
        const block = yml.split(`\n  ${object}:`)[1]
        if (block === undefined) continue           // census metric, not a ladder
        const rungs = block.split(/\n  [a-z_]+:/)[0]
        expect(rungs, `${f.name}: ${object} has no rung ${rung}`).toContain(rung)
      }
    }
  })
})

describe('layout — a building may not stand in the crop', () => {
  it('holds across 40 village seeds, not just the pinned one', { timeout: 120_000 }, () => {
    // FOUND BY DRAWING A FRAME (2026-07-27): the first capture ever rendered
    // put the harbourmaster's hut in a ploughed plot, and check_on_road named
    // it (soil is the same warm brown as a dirt lane). Before the fix this
    // measured 28/40 seeds. A single-seed assertion would have gone green on
    // the fix that only moved the pinned island.
    const bad: string[] = []
    for (let i = 0; i < 40; i++) {
      const L = composeLayout(HAMLET.state, `sweep-${i}`, {
        footprintOf: packFootprints(PACK, HAMLET.state),
      })
      const plots = L.paint
        .filter((r) => r.kind === 'ploughed' || r.kind === 'crop')
        .map((r) => ellipseOfRegion(r))
        .filter((e): e is [number, number, number, number] => e !== null)
        .map(([cx, cy, rx, ry]) => ({
          at: { x: cx, y: cy + ry },
          size: { w: rx / 0.42, h: (2 * ry) / 0.55 },
        }))
      for (const s of L.structures) {
        if (maxGroundOverlap(s.at, s.size, plots) > 0.04) {
          bad.push(`sweep-${i}: ${s.kind}@${Math.round(s.at.x)},${Math.round(s.at.y)}`)
        }
      }
    }
    expect(bad).toEqual([])
  })

  it('the plaza is deliberately NOT a keep-off surface', () => {
    // The firepit stands ON the square by design. If a future tightening
    // sweeps the plaza in with the plots, this is what says so.
    const L = composeLayout(HAMLET.state, HAMLET.seed, {
      footprintOf: packFootprints(PACK, HAMLET.state),
    })
    const plaza = ellipseOfRegion(L.paint.find((r) => r.kind === 'plaza'))!
    const firepit = L.structures.find((s) => s.role === 'firepit')!
    const box = groundBox(firepit.at.x, firepit.at.y, firepit.size.w, firepit.size.h)
    const inside =
      box.x0 > plaza[0] - plaza[2] * 1.6 && box.x1 < plaza[0] + plaza[2] * 1.6 &&
      box.y0 > plaza[1] - plaza[3] * 1.6 && box.y1 < plaza[1] + plaza[3] * 1.6
    expect(inside, 'the hearth belongs on the square').toBe(true)
  })
})
