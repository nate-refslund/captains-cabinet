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
    for (const slug of ['cos', 'polads-ceo', 'stephie-ceo', 'comms-officer']) {
      expect(deskSheetFor(slug)).toBe(deskSheetFor(slug))
      expect(DESK_SHEETS).toContain(deskSheetFor(slug))
      expect(characterSheetFor(slug)).toBe(characterSheetFor(slug))
      expect(characterSheetFor(slug)).toMatch(/^characters\/Premade_Character_\d{2}$/)
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
    // by DESK_SHEETS/BUNK_SHEET instead.
    for (const id of ['board', 'postbox', 'door', 'dojo', 'floor', 'lever']) {
      expect(STATION_SPRITES[id], id).toBeDefined()
    }
    expect(BUNK_SHEET).toMatch(/^office\/singles\//)
  })
})
