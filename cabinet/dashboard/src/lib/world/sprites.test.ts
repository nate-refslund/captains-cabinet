/**
 * The shared sprite vocabulary — per-slug picks, frame math, and the CAST.
 *
 * THE THREE ARMS THAT LEFT THIS FILE (2026-07-29), named so their absence is a
 * decision rather than a gap. This file used to open with the SILENT-BLACK
 * defence (2026-07-08 incident: a renderer failure produced an empty canvas
 * with zero signal) in three arms over `resolveWorldSprites` — the WARDROOM
 * resolver, whose only caller was `world-canvas.tsx` in the legacy three-scene
 * shell. The shell was deleted in the same commit, and with it the resolver.
 *
 * THE LAW DID NOT LEAVE WITH THEM. It is enforced on the live path by
 * `resolveOutdoorSprites`, and pinned in `outdoor.test.ts`: every island sheet
 * resolves against the REAL committed manifest, absent rows are reported LOUDLY
 * in `missing` rather than quietly dropped, urls come only from manifest rows,
 * and a sheet whose real dimensions cannot contain the cuts taken from it is
 * treated as missing. That last arm was MOVED there rather than deleted, so the
 * count of sensors over the silent-black class is unchanged.
 *
 * What stays here is what still has a subject: the pure sprite vocabulary the
 * engine draws with, and the cast the world actually binds.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import {
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
  type WorldAssetManifest,
} from './sprites'
import { requiredOutdoorSheets, resolveOutdoorSprites } from './sprites-outdoor'

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

describe('the shared sprite vocabulary', () => {
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
      // the same dimension rule the resolver applies to the licensed set
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
    const { urls, missing } = resolveOutdoorSprites(manifest, 'island')
    const bound = requiredOutdoorSheets('island').filter((id) =>
      id.startsWith(`${CHARACTER_DIR}/`)
    )
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
    for (const id of requiredOutdoorSheets('island')) {
      expect(id.startsWith('characters/'), id).toBe(false)
    }
  })
})
