/**
 * Outdoor sprite resolution and the pure scene dynamics.
 *
 * WHAT THIS FILE USED TO BE, and why it shrank (2026-07-29). It opened with
 * `describe('street layout (Z1)')` and `describe('island layout (Z0)')` — 18
 * arms over `buildStreetLayout` and `buildIslandLayout`, the two placement
 * modules of the LEGACY three-scene shell. That shell was deleted in the same
 * commit as this edit, so those arms lost their subject entirely; a test whose
 * import no longer resolves is not a sensor, and one kept alive by re-pointing
 * it at whatever still compiles is worse.
 *
 * The product laws they pinned are NOT dropped with them, because the engine
 * proves them on its own data path rather than on a retired renderer's
 * placement:
 *   - the dark beacon at cells_graduated=0 → growth.test.ts ('THE dark beacon —
 *     honest zero') and era-engine.test.ts (lighthouse lamp dark, no lit posts);
 *   - one structure per real role / plot per ratified outcome → world-buildings
 *     + era-engine's ladder arms, which is where the engine reads them;
 *   - day-0 honesty (no census → nothing invented) → pick.test.ts's day-zero
 *     island and unmeasured-state.test.ts;
 *   - determinism of placement → the iso-layout and blueprint suites.
 *
 * What remains here is what still has a live subject: the loud-failure chain
 * that binds every sheet the ENGINE's island may draw against the REAL
 * committed manifest, and the pure scene-dynamics helpers.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import {
  bucketOf,
  cropCut,
  motePatrolX,
  requiredOutdoorSheets,
  resolveOutdoorSprites,
} from './sprites-outdoor'
import { ROOM_SHEET, type WorldAssetManifest } from './sprites'

describe('outdoor sprite resolution (loud-failure chain)', () => {
  const manifest = JSON.parse(
    fs.readFileSync(
      path.resolve(__dirname, '../../../public/world-assets/manifest.json'),
      'utf8'
    )
  ) as WorldAssetManifest

  it('every island sheet + cut fits against the committed manifest', () => {
    const r = resolveOutdoorSprites(manifest, 'island')
    expect(r.missing).toEqual([])
    expect(Object.keys(r.urls)).toHaveLength(requiredOutdoorSheets('island').length)
  })

  it('absent rows are reported loudly, never silently dropped', () => {
    const r = resolveOutdoorSprites({ version: 1, assets: [] }, 'island')
    expect(r.missing.length).toBe(requiredOutdoorSheets('island').length)
    expect(Object.keys(r.urls)).toHaveLength(0)
  })

  it('urls come ONLY from manifest rows (ASSET_BASE + row path)', () => {
    const r = resolveOutdoorSprites(manifest, 'island')
    expect(Object.keys(r.urls).length).toBeGreaterThan(0)
    for (const url of Object.values(r.urls)) {
      expect(url.startsWith('/world-assets/')).toBe(true)
      expect(url).not.toContain('..')
    }
  })

  /**
   * MOVED here from sprites.test.ts (2026-07-29) when the wardroom resolver it
   * used was deleted with the legacy shell. A sheet whose REAL dimensions
   * cannot contain the cuts taken from it is treated as missing — otherwise the
   * renderer takes a cut off the end of a too-small texture and draws nothing,
   * which is the silent-black class this whole chain exists to prevent.
   */
  it('dimension-invalid sheets are treated as missing (cuts must fit)', () => {
    const shrunk: WorldAssetManifest = {
      version: manifest.version,
      assets: manifest.assets.map((r) =>
        r.id === ROOM_SHEET ? { ...r, w: 64, h: 32 } : r
      ),
    }
    const { missing } = resolveOutdoorSprites(shrunk, 'island')
    expect(missing).toContain(ROOM_SHEET)
  })

  /**
   * The street SCENE went with the shell; two of its singles did not, because
   * the island genuinely draws them — the harbour boat and the quay bench. This
   * arm exists so that fact stays MEASURED rather than assumed: the street kit's
   * footprint in the required set is exactly these two, so the ~28 sheets the
   * retired scene bound cannot creep back in, and the two that are really drawn
   * cannot be pruned by a later sweep that reads "street" as "dead".
   */
  it('the street kit survives ONLY where the island really draws it', () => {
    const street = requiredOutdoorSheets('island')
      .filter((id) => id.startsWith('exteriors/street/'))
      .sort()
    expect(street).toEqual([
      'exteriors/street/ME_Singles_City_Props_16x16_Bench_1',
      'exteriors/street/ME_Singles_Vehicles_16x16_Boat_1_Down_1',
    ])
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
