/**
 * Growth read-model tests — PIN the world-alive direction §4 table against
 * the live 2026-07-08 census keyframe values, so the fixtures pin today's
 * world ("young org, first sprouts, dark beacon").
 */
import { describe, expect, it } from 'vitest'
import {
  ageDays,
  buildGrowth,
  landRadius,
  streetAgeBand,
  surfaceGrowth,
  tier,
} from './growth'

/** The live keyframe values on 2026-07-08 (direction §4 table). */
const K_2026_07_08 = {
  date: '2026-07-08',
  org_events_total: 155_784,
  commits_total: 1_011,
  ev_role_defined: 4,
  outcomes_total: 10,
  ev_work_item_completed: 6_708,
  cells_graduated: 0,
  packs_dirs: 5,
  services_rows_total: 38,
  services_rows_disabled: 2,
  golden_evals_delta_vs_seed: -4,
  ev_subagent_completed: 1_260,
  memory_rows_total: 1_170,
  tier2_note_files: 37,
}
const K_PREV = { ...K_2026_07_08, date: '2026-07-07', commits_total: 997 }

describe('tier law', () => {
  it('pins the §4 table (all tier-3 surfaces)', () => {
    expect(tier(1_170, 80)).toBe(3) // memory_rows_total
    expect(tier(9, 1)).toBe(3) // evolved_skills
    expect(tier(569, 70)).toBe(3) // consequence_ledger_lines
    expect(tier(1_011, 120)).toBe(3) // commits_total → 3 modular floors
    expect(tier(38, 5)).toBe(3) // captain_rules
    expect(tier(6_708, 850)).toBe(3) // work_completed → crop stage 3
    expect(tier(1_260, 140)).toBe(3) // subagents_lifetime → flagstone center
    expect(tier(37, 4)).toBe(3) // tier2_note_files
    expect(tier(5, 1)).toBe(2) // packs_dirs → 5 crates, tier 2
  })
  it('honest zero/negative → tier 0, never NaN', () => {
    expect(tier(0, 1)).toBe(0) // cells_graduated — the dark beacon
    expect(tier(-4, 2)).toBe(0) // golden_evals_delta — scarecrow only
    expect(tier(10, 0)).toBe(0) // corrupt base fails closed
    expect(tier(Number.NaN, 5)).toBe(0)
  })
  it('clamps at 7', () => {
    expect(tier(1e12, 1)).toBe(7)
  })
})

describe('island fold radius', () => {
  it('R = 54 tiles at 155,784 events (today)', () => {
    expect(landRadius(155_784)).toBe(54)
  })
  it('day-0 islet is 24 tiles', () => {
    expect(landRadius(0)).toBe(24)
  })
})

describe('hysteresis pair', () => {
  it('same tier across keyframes → no pending', () => {
    const s = surfaceGrowth(K_PREV, K_2026_07_08, 'commits_total', 120)
    expect(s).toEqual({ tier: 3, pendingTier: null, value: 1_011 })
  })
  it('tier change renders OLD tier + pending scaffold', () => {
    const jumped = { ...K_2026_07_08, commits_total: 4_000 } // tier 5
    const s = surfaceGrowth(K_PREV, jumped, 'commits_total', 120)
    expect(s.tier).toBe(3)
    expect(s.pendingTier).toBe(5)
  })
  it('single keyframe renders directly (day one of hysteresis is honest)', () => {
    const s = surfaceGrowth(undefined, K_2026_07_08, 'commits_total', 120)
    expect(s).toEqual({ tier: 3, pendingTier: null, value: 1_011 })
  })
})

describe('street age band (street_liveliness TEXTURE)', () => {
  it('computes days from census dates, never a wall clock', () => {
    expect(ageDays('2026-07-07', '2026-07-08')).toBe(1)
    expect(ageDays(null, '2026-07-08')).toBe(0)
  })
  it('bands: <7d bare, 7–30d benches, >30d planters', () => {
    expect(streetAgeBand(1)).toBe('bare')
    expect(streetAgeBand(7)).toBe('benches')
    expect(streetAgeBand(30)).toBe('benches')
    expect(streetAgeBand(31)).toBe('planters')
  })
})

describe('buildGrowth — the whole young-org model', () => {
  it('pins today: 3-floor HQ, 54-tile island, 4 cottages, 10 stage-3 plots, 5 crates, DARK beacon', () => {
    const g = buildGrowth([K_PREV, K_2026_07_08], '2026-07-07')
    expect(g.available).toBe(true)
    expect(g.radius).toBe(54)
    expect(g.hqFloors.tier).toBe(3)
    expect(g.officerHouses).toBe(4)
    expect(g.fieldPlots).toBe(10)
    expect(g.cropStage.tier).toBe(3) // first sprouts, nothing ripe
    expect(g.beaconLit).toBe(false) // THE dark beacon — honest zero
    expect(g.dockCrates).toBe(5)
    expect(g.millsTotal).toBe(38)
    expect(g.millsDisabled).toBe(2)
    expect(g.goldenEvalsDelta).toBe(-4) // scarecrow only, no grown dummies
    expect(g.streetBand).toBe('bare')
    expect(g.plazaTier.tier).toBe(3) // flagstone center
  })
  it('crop stage caps at 6 (7-stage strips, index 0..6)', () => {
    const ripe = { ...K_2026_07_08, ev_work_item_completed: 10_000_000 }
    const g = buildGrowth([ripe], null)
    expect(g.cropStage.tier).toBe(6)
  })
  it('missing census → available:false, day-0 world (24-tile islet, ground-floor HQ, dark beacon)', () => {
    const g = buildGrowth([], null)
    expect(g.available).toBe(false)
    expect(g.radius).toBe(24)
    expect(g.hqFloors.tier).toBe(0)
    expect(g.officerHouses).toBe(0)
    expect(g.beaconLit).toBe(false)
  })
})
