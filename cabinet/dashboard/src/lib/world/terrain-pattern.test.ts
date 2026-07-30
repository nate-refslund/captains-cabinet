import { describe, expect, it } from 'vitest'
import {
  DIRT_FLECK_DARK,
  DIRT_FLECK_LITE,
  dirtTileFlecks,
  FOAM_WHITE,
  GRASS_FLECK_DARK,
  GRASS_FLECK_LITE,
  GRASS_FLECK_MID,
  GRASS_TONE_DARK,
  GRASS_TONE_MID,
  grassFlecks,
  grassTones,
  MIST_GREY,
  mistBandDashes,
  mistDots,
  PATTERN_PX,
  PATTERN_TILES,
  shadowDots,
  smokePuffs,
  WATER_DARK,
  WATER_DEEP,
  WATER_LITE,
  WATER_MID,
  waterDashes,
  waterTones,
  waveRingDashes,
} from './terrain-pattern'

describe('terrain patterns (compositor-grade ground — v1a aesthetic fix)', () => {
  it('water dashes are dense enough to kill flat 8px voids (≥9/tile)', () => {
    const dashes = waterDashes()
    expect(dashes.length).toBeGreaterThanOrEqual(PATTERN_TILES * PATTERN_TILES * 9)
  })

  it('tonal bands break the single-dominant ocean (≥35% of tiles toned)', () => {
    const tones = waterTones()
    expect(tones.length).toBeGreaterThanOrEqual(
      Math.floor(PATTERN_TILES * PATTERN_TILES * 0.35)
    )
    for (const t of tones) expect([WATER_MID, WATER_DARK]).toContain(t.color)
  })

  it('every primitive stays inside the pattern square', () => {
    for (const d of [...waterTones(), ...waterDashes(), ...grassFlecks()]) {
      expect(d.x).toBeGreaterThanOrEqual(0)
      expect(d.y).toBeGreaterThanOrEqual(0)
      expect(d.x + d.len).toBeLessThanOrEqual(PATTERN_PX)
      expect(d.y + d.h).toBeLessThanOrEqual(PATTERN_PX)
    }
  })

  it('uses ONLY sheet-sampled hues (palette-native by construction)', () => {
    const waterHues = new Set([WATER_DARK, WATER_LITE, WATER_DEEP, FOAM_WHITE])
    for (const d of waterDashes()) expect(waterHues.has(d.color)).toBe(true)
    const grassHues = new Set([GRASS_FLECK_DARK, GRASS_FLECK_MID, GRASS_FLECK_LITE])
    for (const d of grassFlecks()) expect(grassHues.has(d.color)).toBe(true)
  })

  it('is deterministic — two runs are byte-identical (replay ratchet)', () => {
    expect(waterDashes()).toEqual(waterDashes())
    expect(grassFlecks()).toEqual(grassFlecks())
    expect(mistDots(4)).toEqual(mistDots(4))
  })

  it('salted patterns differ (seeding is real, not constant)', () => {
    expect(waterDashes('other-salt')).not.toEqual(waterDashes())
  })
})

describe('cozy-density primitives (2026-07-09 — the mockups are the bar)', () => {
  it('grassTones: in-bin two-tone bands, ≥25% of tiles toned', () => {
    const tones = grassTones()
    expect(tones.length).toBeGreaterThanOrEqual(
      Math.floor(PATTERN_TILES * PATTERN_TILES * 0.25)
    )
    for (const t of tones) {
      expect([GRASS_TONE_MID, GRASS_TONE_DARK]).toContain(t.color)
      expect(t.len).toBe(16)
    }
  })

  it('dirtTileFlecks: worn-path speckle stays inside its tile, worn hues only', () => {
    for (const d of dirtTileFlecks(120, 33)) {
      expect(d.x).toBeGreaterThanOrEqual(0)
      expect(d.y).toBeGreaterThanOrEqual(0)
      expect(d.x + d.len).toBeLessThanOrEqual(17) // paired tick may touch edge
      expect([DIRT_FLECK_DARK, DIRT_FLECK_LITE]).toContain(d.color)
    }
  })

  it('shadowDots: dither inside the half-ellipse, never a solid blob', () => {
    const dots = shadowDots('tree:1,2', 40)
    expect(dots.length).toBeGreaterThan(8)
    for (const d of dots) {
      expect(Math.abs(d.x)).toBeLessThanOrEqual(20)
      expect(Math.abs(d.y)).toBeLessThanOrEqual(7)
    }
    // dither, not fill: strictly fewer dots than the ellipse pixel area
    expect(dots.length).toBeLessThan(20 * 7 * 2)
  })

  it('mistBandDashes: density ramps toward the horizon (growth-fog law)', () => {
    const band = mistBandDashes(180, 191, 0, 39)
    const firstRow = band.filter((d) => d.y < 181 * 16).length
    const lastRow = band.filter((d) => d.y >= 191 * 16).length
    expect(lastRow).toBeGreaterThan(firstRow)
    for (const d of band) expect([MIST_GREY, FOAM_WHITE]).toContain(d.color)
  })

  it('waveRings + smoke: deterministic, seeded, bounded', () => {
    expect(waveRingDashes('pier:0')).toEqual(waveRingDashes('pier:0'))
    expect(waveRingDashes('pier:0')).not.toEqual(waveRingDashes('boat'))
    for (const d of waveRingDashes('boat')) {
      expect(Math.abs(d.x)).toBeLessThanOrEqual(14)
      expect(Math.abs(d.y)).toBeLessThanOrEqual(8)
    }
    expect(smokePuffs('gh', 400)).toEqual(smokePuffs('gh', 400))
    expect(
      smokePuffs('gh', 401).every((p) => p.y <= 0 && p.r >= 1 && p.r <= 3)
    ).toBe(true)
  })

  it('cozy primitives replay byte-identical (determinism ratchet)', () => {
    expect(grassTones()).toEqual(grassTones())
    expect(dirtTileFlecks(5, 9)).toEqual(dirtTileFlecks(5, 9))
    expect(shadowDots('x', 24)).toEqual(shadowDots('x', 24))
    expect(mistBandDashes(180, 191, 0, 10)).toEqual(mistBandDashes(180, 191, 0, 10))
  })
})
