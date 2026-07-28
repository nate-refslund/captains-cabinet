/**
 * ART CREDIT — the predicate, in BOTH directions, against the REAL manifest.
 *
 * The failure this pins is a two-sided one. An unconditional "Art: LimeZu"
 * line under a frame drawn entirely from owned art is false attribution of our
 * own work; a credit dropped while LimeZu pixels are on screen breaks the
 * licence. So every arm below asserts a POSITIVE and its NEGATIVE, and each
 * negative is reachable from the same code path as its positive — a suite that
 * only ever exercises "credit shown" would pass against a hardcoded `true`.
 *
 * The 2026-07-28 finding this file exists to keep fixed: the portrait rail is
 * chrome, so it is mounted under BOTH projections, and its portraits are
 * `LimeZu commercial — derived pixels`. A credit rule that keyed on projection
 * alone would have gone dark over a screen full of LimeZu-derived faces.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import {
  canvasAssetIds,
  creditOwed,
  creditReason,
  ISO_ATLAS_ROW,
  isLimeZuRow,
  limezuSurfaces,
} from './credit'
import { CHARACTER_DIR, characterSheetFor, type WorldAssetManifest } from './sprites'
import { ENGINE_CHARACTER_SHEETS } from './sprites-outdoor'

const MANIFEST_PATH = path.resolve(
  __dirname, '..', '..', '..', 'public', 'world-assets', 'manifest.json'
)
function realManifest(): WorldAssetManifest {
  return JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf8')) as WorldAssetManifest
}
const rowFor = (m: WorldAssetManifest, id: string) =>
  m.assets.find((r) => r.id === id) ?? null

describe('isLimeZuRow — the one authority on whose pixels these are', () => {
  it('raw pack rows and derived compositions both count', () => {
    const m = realManifest()
    // raw: a licensed character sheet (kept in the manifest for the revert)
    expect(isLimeZuRow(rowFor(m, 'characters/Premade_Character_01'))).toBe(true)
    // derived: a composed portrait — "LimeZu commercial — derived pixels"
    expect(isLimeZuRow(rowFor(m, 'portraits/portrait_cos'))).toBe(true)
  })

  it('owned, CC0 and unlabelled rows do not', () => {
    const m = realManifest()
    expect(isLimeZuRow(rowFor(m, 'originals/characters/Premade_Character_01'))).toBe(false)
    expect(isLimeZuRow(rowFor(m, ISO_ATLAS_ROW))).toBe(false)
    expect(isLimeZuRow(rowFor(m, 'ui/frame_interim_slate'))).toBe(false) // CC0
    expect(isLimeZuRow(null)).toBe(false)
    expect(isLimeZuRow(undefined)).toBe(false)
    // a row with no licence recorded at all is NOT LimeZu by default
    expect(isLimeZuRow({ id: 'x', path: 'x.png', w: 1, h: 1, grid: 16, sha256: '' })).toBe(false)
    // and "LimeZu" must be the licence's own word, not a substring anywhere
    expect(isLimeZuRow({
      id: 'x', path: 'x.png', w: 1, h: 1, grid: 16, sha256: '',
      license: 'owned — org-original', pack: 'LimeZu-shaped, drawn by us',
    })).toBe(false)
  })
})

describe('canvasAssetIds — what each kernel actually paints', () => {
  it('iso paints the owned atlas and the cast, and nothing else from the packs', () => {
    expect(canvasAssetIds('iso')).toEqual([ISO_ATLAS_ROW, ...ENGINE_CHARACTER_SHEETS])
  })
  it('top-down paints the LimeZu outdoor universe (and the cast within it)', () => {
    const ids = canvasAssetIds('topdown')
    expect(ids).toContain('village/Serene_Village_16x16')
    expect(ids).toContain(characterSheetFor('cos'))
    expect(ids.length).toBeGreaterThan(canvasAssetIds('iso').length)
  })
})

describe('the credit follows the art, in both directions', () => {
  const m = realManifest()

  it('top-down owes it: the tile/prop packs are LimeZu whatever the cast is', () => {
    expect(limezuSurfaces({ projection: 'topdown', manifest: m, limezuPortraits: 0 }))
      .toEqual(['world canvas'])
  })

  it('iso with the OWNED cast and no rail portraits owes nothing', () => {
    // The flip's whole point. If this arm ever goes green-by-accident, the
    // one below (which forces the licensed cast) is what catches it.
    expect(limezuSurfaces({ projection: 'iso', manifest: m, limezuPortraits: 0 }))
      .toEqual([])
    expect(creditOwed({ projection: 'iso', manifest: m, limezuPortraits: 0 })).toBe(false)
  })

  it('iso with the LICENSED cast owes it again — the revert is one line', () => {
    // CHARACTER_DIR flipped back means ENGINE_CHARACTER_SHEETS resolve to the
    // licensed rows. Simulated by relabelling the OWNED rows as licensed,
    // which is the same input the constant would produce, without a second
    // module registry to keep in sync.
    const relicensed: WorldAssetManifest = {
      ...m,
      assets: m.assets.map((r) =>
        ENGINE_CHARACTER_SHEETS.includes(r.id)
          ? { ...r, license: 'LimeZu commercial — do not redistribute' }
          : r
      ),
    }
    expect(limezuSurfaces({ projection: 'iso', manifest: relicensed, limezuPortraits: 0 }))
      .toEqual(['world canvas'])
  })

  it('iso with the rail painting portraits owes it — chrome is on screen too', () => {
    // THE 2026-07-28 FINDING. The rail is not the canvas and does not care
    // which kernel is rendering; its faces are LimeZu-derived pixels.
    expect(limezuSurfaces({ projection: 'iso', manifest: m, limezuPortraits: 4 }))
      .toEqual(['portrait rail'])
    expect(creditOwed({ projection: 'iso', manifest: m, limezuPortraits: 4 })).toBe(true)
  })

  it('top-down with the rail open names both surfaces', () => {
    expect(limezuSurfaces({ projection: 'topdown', manifest: m, limezuPortraits: 2 }))
      .toEqual(['world canvas', 'portrait rail'])
  })

  it('degenerate ends: no manifest, empty manifest, all-owned manifest', () => {
    // Nothing is KNOWN to be bound yet → nothing is credited yet.
    expect(limezuSurfaces({ projection: 'topdown', manifest: null, limezuPortraits: 0 })).toEqual([])
    expect(limezuSurfaces({
      projection: 'topdown', manifest: { version: 2, assets: [] }, limezuPortraits: 0,
    })).toEqual([])
    // A hatched cabinet whose manifest carries only owned rows: no credit, in
    // either projection. This is the arm that fails against a hardcoded
    // `projection === 'topdown'`.
    const ownedOnly: WorldAssetManifest = {
      ...m,
      assets: m.assets.filter((r) => String(r.license ?? '').startsWith('owned')),
    }
    expect(limezuSurfaces({ projection: 'topdown', manifest: ownedOnly, limezuPortraits: 0 })).toEqual([])
    expect(limezuSurfaces({ projection: 'iso', manifest: ownedOnly, limezuPortraits: 0 })).toEqual([])
  })

  it('the reason string says which surfaces, so the line is never mystery chrome', () => {
    expect(creditReason([])).toMatch(/no LimeZu art/)
    expect(creditReason(['world canvas', 'portrait rail']))
      .toBe('LimeZu art drawn by: world canvas, portrait rail')
  })
})

describe('the flip is IN EFFECT (not merely available)', () => {
  /**
   * sprites.test.ts asserts the cast id matches `^${CHARACTER_DIR}/…`, which
   * follows the constant and so stays green whichever way it points. This arm
   * is the one that reads the licence of the row the world actually binds, so
   * a revert turns it red instead of silently passing.
   */
  it('every officer binds an owned sheet', () => {
    const m = realManifest()
    expect(CHARACTER_DIR).toBe('originals/characters')
    for (const slug of ['cos', 'bakery-ceo', 'newsletter-ceo', 'comms-officer']) {
      const row = rowFor(m, characterSheetFor(slug))
      expect(row, slug).not.toBeNull()
      expect(row!.license, slug).toBe('owned — org-original')
      expect(isLimeZuRow(row), slug).toBe(false)
    }
    for (const id of ENGINE_CHARACTER_SHEETS) {
      expect(isLimeZuRow(rowFor(m, id)), id).toBe(false)
    }
  })
})
