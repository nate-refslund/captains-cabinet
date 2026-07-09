import { describe, expect, it } from 'vitest'
import {
  FOAM_WHITE,
  GRASS_FLECK_DARK,
  GRASS_FLECK_LITE,
  GRASS_FLECK_MID,
  grassFlecks,
  mistDots,
  PATTERN_PX,
  PATTERN_TILES,
  WATER_DARK,
  WATER_DEEP,
  WATER_LITE,
  WATER_MID,
  waterDashes,
  waterTones,
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
