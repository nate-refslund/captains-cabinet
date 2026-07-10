/**
 * Outdoor set-dressing tests (cozy-density pass 2026-07-09).
 *
 * Doctrine pinned:
 *  - DETERMINISM: identical inputs → deep-equal dressing forever.
 *  - DENSITY BAR: with today's buildings the world carries ≥25 placed props
 *    (the approved mockups run ~35/viewport; v1a live had ~6 — the gap the
 *    Captain named).
 *  - COMPOSITION RULEBOOK: props CLUSTER at anchors (quay cargo hugs the
 *    quay, hay hugs the barn) and every sheet is in the island scene's
 *    loud-failure universe (a missing sheet badges, never silently skips).
 *  - GROWTH HONESTY: torch-post count follows the lantern_posts ladder rung.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import { buildOutdoorDressing } from './outdoor-dressing'
import { buildWorldGeo } from './world-geo'
import { buildWorldBuildings } from './world-buildings'
import { requiredOutdoorSheets } from './sprites-outdoor'
import type { WorldResolution } from './era-engine'

const geo = buildWorldGeo({ orgEventsTotal: 155_784, lanes: {} })

/** Minimal element helper. */
function el(rung: number, rungName: string) {
  return { rung, rungName, vocab: null, pending: null, measured: true, value: 1 }
}

const resolution: WorldResolution = {
  era: 'hamlet',
  eraIndex: 0.36,
  eraUnmeasured: [],
  transition: null,
  lanes: {},
  elements: {
    great_house: el(1, 'cottage'),
    library: el(0, 'crate'),
    workshop: el(1, 'rack'),
    well: el(1, 'well'),
    firepit: el(1, 'ring'),
    law_plot: el(1, 'staked'),
    observatory: el(0, 'none'),
    outbuildings: el(2, 'barn'),
    pens: el(1, 'pen_1'),
    water_store: el(1, 'bucket'),
    journal_desk: el(1, 'desk'),
    warehouse: el(0, 'none'),
    harbormaster_hut: el(0, 'none'),
    lighthouse: el(0, 'dark_cairn'),
    lighthouse_lamp: el(0, 'dark'),
    lantern_posts: el(3, 'posts_3'),
    posts_lit: el(0, 'none'),
    flagpole: el(1, 'raised'),
    noticeboard: el(0, 'none'),
    officer_dwellings: el(2, 'huts_2'),
    road: el(1, 'worn'),
    quay: el(1, 'timber'),
    berths: el(0, 'none'),
    cargo_stacks: el(0, 'none'),
    harbor_boat: el(0, 'rowboat'),
    field_plots: el(0, 'none'),
  },
} as unknown as WorldResolution

const buildings = buildWorldBuildings(resolution, geo)
const D = buildOutdoorDressing(geo, buildings, resolution)

describe('outdoor dressing (cozy pass)', () => {
  it('is deterministic: identical inputs → deep-equal dressing', () => {
    expect(buildOutdoorDressing(geo, buildings, resolution)).toEqual(D)
  })

  it('meets the mockup density bar: ≥25 placed props', () => {
    expect(D.decor.length).toBeGreaterThanOrEqual(25)
  })

  it('every prop id is unique (stable cache keys / seeds)', () => {
    const ids = D.decor.map((d) => d.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('clusters, not scatter: quay cargo hugs the quay line', () => {
    const cargo = D.decor.filter((d) => d.id.startsWith('dress:quay:'))
    expect(cargo.length).toBeGreaterThanOrEqual(5)
    for (const c of cargo) {
      expect(Math.abs(c.x - geo.quayCenter.x)).toBeLessThanOrEqual(9)
      expect(Math.abs(c.y - geo.quayCenter.y)).toBeLessThanOrEqual(2)
    }
  })

  it('torch posts follow the lantern_posts ladder rung (growth honesty)', () => {
    expect(D.decor.filter((d) => d.id.startsWith('dress:torch:')).length).toBe(3)
    const none = buildOutdoorDressing(geo, buildings, {
      ...resolution,
      elements: { ...resolution.elements, lantern_posts: el(0, 'none') },
    } as WorldResolution)
    expect(none.decor.filter((d) => d.id.startsWith('dress:torch:')).length).toBe(0)
  })

  it('every dressed sheet is in the island loud-failure universe', () => {
    const universe = new Set(requiredOutdoorSheets('island'))
    for (const d of D.decor) expect(universe.has(d.sheet)).toBe(true)
  })

  it('every dressed sheet resolves against the REAL committed manifest', () => {
    const manifest = JSON.parse(
      fs.readFileSync(
        path.join(__dirname, '../../../public/world-assets/manifest.json'),
        'utf8'
      )
    ) as { assets: Array<{ id: string }> }
    const ids = new Set(manifest.assets.map((a) => a.id))
    for (const d of D.decor) expect(ids.has(d.sheet)).toBe(true)
  })

  it('fauna anchors: fish water is open sea south of the quay; the dog has a porch; chickens stay in the yard', () => {
    expect(D.quayWater.length).toBeGreaterThanOrEqual(3)
    for (const w of D.quayWater) expect(w.y).toBeGreaterThan(geo.quayCenter.y + 1)
    expect(D.dogPerch).not.toBeNull()
    const pens = buildings.find((b) => b.element === 'pens')
    expect(pens).toBeDefined()
    expect(D.chickenSpots.length).toBeGreaterThan(0)
    for (const c of D.chickenSpots) {
      expect(c.x).toBeGreaterThanOrEqual(pens!.x)
      expect(c.x).toBeLessThanOrEqual(pens!.x + pens!.w + 1)
    }
  })
})
