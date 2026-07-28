/**
 * Sprite resolution tests — the SILENT-BLACK failure class (2026-07-08).
 *
 * The incident: a renderer failure produced an empty canvas with zero
 * signal. These tests pin the two structural defenses in lib form:
 *  1. every sheet the renderer needs resolves against the REAL committed
 *     manifest (a regression here = a texture silently gone), and
 *  2. when a sheet is absent or dimension-invalid, the resolver reports it
 *     LOUDLY in `missing` (the renderer badges + console.errors from that)
 *     instead of quietly returning less work to do.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import {
  ASSET_BASE,
  BUNK_SHEET,
  CHAR_FRAME_H,
  CHAR_FRAME_W,
  CHAR_SHEET_MIN_H,
  CHAR_SHEET_MIN_W,
  CHARACTER_COUNT,
  CHARACTER_DIR,
  charFrame,
  characterSheetFor,
  DESK_SHEETS,
  deskSheetFor,
  requiredSheets,
  resolveWorldSprites,
  ROOM_SHEET,
  STATION_SPRITES,
  type WorldAssetManifest,
} from './sprites'

const MANIFEST_PATH = path.resolve(
  __dirname,
  '..',
  '..',
  '..',
  'public',
  'world-assets',
  'manifest.json'
)

function realManifest(): WorldAssetManifest {
  return JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf8')) as WorldAssetManifest
}

describe('world sprite resolution', () => {
  it('every required sheet resolves against the committed manifest', () => {
    const { urls, missing } = resolveWorldSprites(realManifest())
    expect(missing).toEqual([])
    for (const id of requiredSheets()) {
      expect(urls[id], id).toBeDefined()
      expect(urls[id], id).toMatch(new RegExp(`^${ASSET_BASE}`))
    }
  })

  it('absent sheets are reported loudly, never silently dropped', () => {
    const { urls, missing } = resolveWorldSprites({ version: 2, assets: [] })
    expect(Object.keys(urls)).toEqual([])
    // Every single required sheet must be named in missing.
    expect([...missing].sort()).toEqual([...requiredSheets()].sort())
  })

  it('dimension-invalid sheets are treated as missing (cuts must fit)', () => {
    const m = realManifest()
    const shrunk: WorldAssetManifest = {
      version: m.version,
      assets: m.assets.map((r) =>
        r.id === characterSheetFor('cos') || r.id === ROOM_SHEET
          ? { ...r, w: 64, h: 32 } // too small for strips / floor+wall cuts
          : r
      ),
    }
    const { missing } = resolveWorldSprites(shrunk)
    expect(missing).toContain(ROOM_SHEET)
    expect(missing).toContain(characterSheetFor('cos'))
  })

  it('per-slug picks are deterministic and inside the known sets', () => {
    for (const slug of ['cos', 'bakery-ceo', 'newsletter-ceo', 'comms-officer']) {
      expect(deskSheetFor(slug)).toBe(deskSheetFor(slug))
      expect(DESK_SHEETS).toContain(deskSheetFor(slug))
      expect(characterSheetFor(slug)).toBe(characterSheetFor(slug))
      expect(characterSheetFor(slug)).toMatch(
        new RegExp(`^${CHARACTER_DIR}/Premade_Character_\\d{2}$`)
      )
    }
  })

  it('frame math is pure and stays inside the validated sheet region', () => {
    const anims = ['idle', 'work', 'walk', 'asleep'] as const
    const facings = ['right', 'up', 'left', 'down'] as const
    for (const anim of anims) {
      for (const facing of facings) {
        for (let tick = 0; tick <= 24; tick++) {
          const a = charFrame(anim, facing, tick, 3)
          const b = charFrame(anim, facing, tick, 3)
          expect(a).toEqual(b) // deterministic
          expect(a.w).toBe(CHAR_FRAME_W)
          expect(a.h).toBe(CHAR_FRAME_H)
          expect(a.x).toBeGreaterThanOrEqual(0)
          expect(a.y).toBeGreaterThanOrEqual(0)
          expect(a.x + a.w, `${anim}/${facing}/${tick}`).toBeLessThanOrEqual(CHAR_SHEET_MIN_W)
          expect(a.y + a.h, `${anim}/${facing}/${tick}`).toBeLessThanOrEqual(CHAR_SHEET_MIN_H)
        }
      }
    }
  })

  it('station fixture map covers every fixed civic station in the layout', () => {
    // Fixed stations from layout.ts — desks/bunks are per-slug and covered
    // by DESK_SHEETS/BUNK_SHEET instead. v2 adds the cozy-pass stations
    // (table/kettle/bookshelf/windows/noticeboard — clockwall is DOM-only,
    // deliberately NOT a station sprite: numbers are text, text is DOM).
    for (const id of [
      'board', 'postbox', 'door', 'dojo', 'floor', 'lever',
      'table', 'kettle', 'bookshelf', 'window:1', 'window:2', 'noticeboard',
    ]) {
      expect(STATION_SPRITES[id], id).toBeDefined()
    }
    expect(BUNK_SHEET).toMatch(/^office\/singles\//)
  })
  /**
   * The owned cast must be complete, correctly shaped, and BOUND — the
   * licensed LimeZu sheets are gitignored do-not-redistribute binaries, so
   * only the owned set can be relied on to be present.
   */
  it('the owned character set is complete and correctly shaped', () => {
    const manifest = realManifest()
    const owned = manifest.assets.filter((r) =>
      r.id.startsWith('originals/characters/Premade_Character_')
    )
    expect(owned).toHaveLength(CHARACTER_COUNT)
    for (let i = 1; i <= CHARACTER_COUNT; i++) {
      const id = `originals/characters/Premade_Character_${String(i).padStart(2, '0')}`
      const row = owned.find((r) => r.id === id)
      expect(row, id).toBeDefined()
      // the same dimension rule resolveWorldSprites applies to the licensed set
      expect(row!.w, id).toBeGreaterThanOrEqual(CHAR_SHEET_MIN_W)
      expect(row!.h, id).toBeGreaterThanOrEqual(CHAR_SHEET_MIN_H)
      expect(row!.grid, id).toBe(16)
      expect(row!.license, id).toBe('owned — org-original')
    }
  })

  /**
   * The world draws art the org OWNS (Captain ruling 2026-07-28).
   *
   * The completeness test above passed both before and after the flip — it
   * proves the owned sheets exist, never that they are the ones bound. This
   * one fails against pre-flip code: it asserts the paths resolveWorldSprites
   * actually hands the renderer are the owned files. Reverting the cast is
   * still one line, but it can no longer happen by accident.
   */
  it('the LIVE cast is the owned set — every bound character path is owned art', () => {
    expect(CHARACTER_DIR).toBe('originals/characters')

    const manifest = realManifest()
    const { urls, missing } = resolveWorldSprites(manifest)
    const bound = requiredSheets().filter((id) => id.startsWith(`${CHARACTER_DIR}/`))
    expect(bound).toHaveLength(CHARACTER_COUNT)

    const byId = new Map(manifest.assets.map((r) => [r.id, r]))
    for (const id of bound) {
      expect(missing, id).not.toContain(id)
      expect(urls[id], id).toBeDefined()
      // the drawn bytes come from the owned directory, under the owned licence
      expect(urls[id], id).toContain('originals/characters/')
      expect(byId.get(id)?.license, id).toBe('owned — org-original')
    }
    // and no licensed LimeZu character sheet is bound anywhere
    for (const id of requiredSheets()) {
      expect(id.startsWith('characters/'), id).toBe(false)
    }
  })
})
