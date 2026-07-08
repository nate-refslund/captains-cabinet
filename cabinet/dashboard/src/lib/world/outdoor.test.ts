/**
 * T3 wider-world tests — street/island layouts, outdoor sprite resolution,
 * scene mapping, and the pure scene dynamics.
 *
 * Doctrine pinned here:
 *  - DETERMINISM: identical inputs → deep-equal layouts, forever (fold law:
 *    positions never move once placed).
 *  - GROWTH HONESTY: the beacon renders dark at cells_graduated=0; plots
 *    track outcomes_total; the HQ stacks one floor per commits tier;
 *    day-0 (no census) renders the honest islet, never fake growth.
 *  - LOUD FAILURE: every sheet either scene may draw resolves against the
 *    REAL committed manifest (a missing row would badge in DOM — this test
 *    fails first).
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import { buildGrowth, type CensusKeyframe } from './growth'
import { buildStreetLayout, hqStack, STREET_W } from './street-layout'
import { buildIslandLayout } from './island-layout'
import {
  bucketOf,
  cropCut,
  motePatrolX,
  requiredOutdoorSheets,
  resolveOutdoorSprites,
} from './sprites-outdoor'
import type { WorldAssetManifest } from './sprites'

/** The live 2026-07-08 census keyframe (§4 fixtures pin today's world). */
const KF: CensusKeyframe = {
  date: '2026-07-08',
  org_events_total: 155_784,
  commits_total: 1_011,
  ev_role_defined: 4,
  outcomes_total: 10,
  ev_work_item_completed: 6_708,
  ev_subagent_completed: 1_260,
  cells_graduated: 0,
  packs_dirs: 5,
  services_rows_total: 38,
  services_rows_disabled: 2,
  golden_evals_delta_vs_seed: -4,
}
const SLUGS = ['comms-officer', 'cos', 'polads-ceo', 'stephie-ceo']
// First census date fixed >30d back so the fixture pins the planters band
// (the live band follows the REAL first keyframe date — honesty over vibes).
const growth = buildGrowth([KF], '2026-06-01')

describe('street layout (Z1)', () => {
  const L = buildStreetLayout(growth, SLUGS)

  it('is deterministic: identical inputs → deep-equal layout', () => {
    expect(buildStreetLayout(growth, SLUGS)).toEqual(L)
  })

  it('stacks one modular floor per commits tier (3 today)', () => {
    expect(L.hqFloors).toBe(3)
    const stack = hqStack(3)
    // ground + 3 middles + roof
    expect(stack).toHaveLength(5)
    // pieces stack upward without gaps
    for (let i = 1; i < stack.length; i++) {
      expect(stack[i].bottomPx).toBe(stack[i - 1].bottomPx - stack[i - 1].hPx)
    }
  })

  it('places integer-tile ground across the full band', () => {
    for (const g of L.ground) {
      expect(Number.isInteger(g.x)).toBe(true)
      expect(Number.isInteger(g.y)).toBe(true)
      expect(g.x).toBeGreaterThanOrEqual(0)
      expect(g.x).toBeLessThan(STREET_W)
    }
  })

  it('gives every officer a facade mote slot + a lit-window slot', () => {
    expect(L.motes.map((m) => m.slug)).toEqual([...SLUGS].sort())
    expect(L.windows).toHaveLength(SLUGS.length)
  })

  it('age band today (>30d) unlocks benches + trees + planters', () => {
    expect(growth.streetBand).toBe('planters')
    expect(L.props.some((p) => p.id === 'street:bench')).toBe(true)
    expect(L.props.some((p) => p.id.startsWith('street:planter:'))).toBe(true)
  })

  it('HQ door navigates to the Wardroom (door-is-a-scene-swap)', () => {
    const door = L.props.find((p) => p.id === 'street:hq:door')
    expect(door?.navigate).toBe(2)
  })
})

describe('island layout (Z0)', () => {
  const L = buildIslandLayout(growth, SLUGS)

  it('is deterministic: identical inputs → deep-equal layout', () => {
    expect(buildIslandLayout(growth, SLUGS)).toEqual(L)
  })

  it('land radius follows the fold law: R=54 at 155,784 events', () => {
    expect(L.radius).toBe(54)
  })

  it('one cottage per defined role, seeded roof, uniform size', () => {
    const houses = L.props.filter((p) => p.id.startsWith('island:house:'))
    expect(houses).toHaveLength(4)
    for (const h of houses) {
      expect(h.cut?.w).toBe(56) // uniform — per-officer tiers are dark
      expect(h.cut?.h).toBe(59)
    }
  })

  it('one field plot per ratified outcome, crop stage 3 (first sprouts)', () => {
    expect(L.fields).toHaveLength(10)
    for (const f of L.fields) {
      expect(f.stage).toBe(3)
      expect(f.pendingStage).toBeNull()
    }
  })

  it('THE dark beacon: present, prominent, unlit at cells_graduated=0', () => {
    const beacon = L.props.find((p) => p.id === 'island:beacon')
    expect(beacon).toBeDefined()
    expect(beacon?.morphId).toBe('island_harbor_beacon')
    expect(beacon?.label).toContain('dark beacon')
    expect(growth.beaconLit).toBe(false)
  })

  it('5 dock crates (one per extension pack)', () => {
    const crates = L.props.filter((p) => p.id.startsWith('island:crate:'))
    // 5 crates render as 2 stacked pairs + 1 single = 3 sprites
    const singles = crates.filter((c) => c.cut?.h === 17).length
    const pairs = crates.filter((c) => c.cut?.h === 32).length
    expect(singles + 2 * pairs).toBe(5)
  })

  it('golden-eval delta ≤ 0 → exactly one weathered scarecrow', () => {
    const sc = L.props.filter((p) => p.id === 'island:scarecrow')
    expect(sc).toHaveLength(1)
    expect(sc[0].ghost).toBe(true)
  })

  it('every anchor surface is marked even when its building is future', () => {
    for (const id of ['island:law', 'island:stall', 'island:post:0', 'island:hq']) {
      expect(L.props.some((p) => p.id === id), id).toBe(true)
    }
  })

  it('all props stand on integer tiles inside the world box', () => {
    for (const p of L.props) {
      expect(Number.isInteger(p.x), p.id).toBe(true)
      expect(Number.isInteger(p.y), p.id).toBe(true)
      expect(p.x).toBeGreaterThanOrEqual(0)
      expect(p.x).toBeLessThanOrEqual(L.w)
      expect(p.y).toBeGreaterThanOrEqual(0)
      expect(p.y).toBeLessThanOrEqual(L.h)
    }
  })

  it('day-0 honesty: no census → 24-tile islet, dark beacon, no houses', () => {
    const g0 = buildGrowth([], null)
    expect(g0.available).toBe(false)
    const L0 = buildIslandLayout(g0, [])
    expect(L0.radius).toBe(24)
    expect(L0.fields).toHaveLength(0)
    expect(L0.props.find((p) => p.id === 'island:beacon')).toBeDefined()
    expect(L0.props.filter((p) => p.id.startsWith('island:house:'))).toHaveLength(0)
  })
})

describe('outdoor sprite resolution (loud-failure chain)', () => {
  const manifest = JSON.parse(
    fs.readFileSync(
      path.resolve(__dirname, '../../../public/world-assets/manifest.json'),
      'utf8'
    )
  ) as WorldAssetManifest

  it('every street sheet resolves against the committed manifest', () => {
    const r = resolveOutdoorSprites(manifest, 'street')
    expect(r.missing).toEqual([])
    expect(Object.keys(r.urls)).toHaveLength(requiredOutdoorSheets('street').length)
  })

  it('every island sheet + cut fits against the committed manifest', () => {
    const r = resolveOutdoorSprites(manifest, 'island')
    expect(r.missing).toEqual([])
  })

  it('absent rows are reported loudly, never silently dropped', () => {
    const r = resolveOutdoorSprites({ version: 1, assets: [] }, 'island')
    expect(r.missing.length).toBe(requiredOutdoorSheets('island').length)
    expect(Object.keys(r.urls)).toHaveLength(0)
  })

  it('urls come ONLY from manifest rows (ASSET_BASE + row path)', () => {
    const r = resolveOutdoorSprites(manifest, 'street')
    for (const url of Object.values(r.urls)) {
      expect(url.startsWith('/world-assets/')).toBe(true)
      expect(url).not.toContain('..')
    }
  })
})

describe('pure scene dynamics', () => {
  it('crop stage cuts stay inside the 7-stage strip', () => {
    expect(cropCut(32, 3)).toEqual({ x: 48, y: 0, w: 16, h: 18 })
    expect(cropCut(64, 6)).toEqual({ x: 96, y: 0, w: 16, h: 33 })
    expect(cropCut(32, 99).x).toBe(96) // clamped to stage 6
    expect(cropCut(32, -1).x).toBe(0)
  })

  it('mote patrol is a pure triangle wave — same tick, same x, forever', () => {
    const a = motePatrolX(30, 3, 7, 123)
    expect(motePatrolX(30, 3, 7, 123)).toBe(a)
    // stays within the span
    for (let t = 0; t < 200; t++) {
      const x = motePatrolX(30, 3, 7, t)
      expect(x).toBeGreaterThanOrEqual(27)
      expect(x).toBeLessThanOrEqual(33)
    }
  })

  it('day buckets follow the night law; missing clock renders day', () => {
    expect(bucketOf(null)).toBe('day')
    expect(bucketOf(7)).toBe('dawn')
    expect(bucketOf(12)).toBe('day')
    expect(bucketOf(19)).toBe('dusk')
    expect(bucketOf(23)).toBe('night')
    expect(bucketOf(2)).toBe('night')
  })
})
