/**
 * Set-dressing determinism + discipline tests (TRACK T2).
 *
 * Pins: seeded per-desk personalization (same slug → same desk forever, two
 * DISTINCT flair items), pin placement staying inside the cork face, paper
 * hues staying off the reserved salience palette, and the cozy sheet
 * universe resolving against the real committed manifest through the same
 * loud missing→badge chain as every other asset class.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import {
  ALCOVE,
  DECOR,
  deskFlairFor,
  FLAIR_POOL,
  KETTLE_SHEET,
  LAMP_SHEETS,
  lampSheetFor,
  NOTE_PIN_COLORS,
  NOTE_PIN_MAX,
  NOTICEBOARD_SHEET,
  PIN_AREA,
  pinPlacement,
  RUG_RUNNER,
  setDressingSheets,
} from './set-dressing'
import { resolveWorldSprites, type WorldAssetManifest } from './sprites'

const MANIFEST_PATH = path.resolve(
  __dirname, '..', '..', '..', 'public', 'world-assets', 'manifest.json'
)

describe('per-desk personalization', () => {
  const slugs = ['cos', 'bakery-ceo', 'newsletter-ceo', 'comms-officer', 'cto', 'coo']

  it('lamp variant is deterministic and inside the 141–146 set', () => {
    for (const slug of slugs) {
      expect(lampSheetFor(slug)).toBe(lampSheetFor(slug))
      expect(LAMP_SHEETS).toContain(lampSheetFor(slug))
    }
    expect(LAMP_SHEETS).toHaveLength(6)
  })

  it('flair picks two DISTINCT items, deterministically per slug', () => {
    for (const slug of slugs) {
      const [a, b] = deskFlairFor(slug)
      const [a2, b2] = deskFlairFor(slug)
      expect(a).toEqual(a2)
      expect(b).toEqual(b2)
      expect(FLAIR_POOL).toContain(a)
      expect(FLAIR_POOL).toContain(b)
      expect(a.sheet === b.sheet && a.dx === b.dx && a.dy === b.dy).toBe(false)
    }
  })

  it('desks differ: the flair space actually varies across slugs', () => {
    const signatures = new Set(
      slugs.map((s) => deskFlairFor(s).map((f) => f.sheet).join('|') + lampSheetFor(s))
    )
    expect(signatures.size).toBeGreaterThan(1)
  })
})

describe('noticeboard pins', () => {
  it('placement is deterministic and stays inside the cork face', () => {
    for (let iid = 0; iid < 500; iid++) {
      const p = pinPlacement(iid)
      expect(p).toEqual(pinPlacement(iid))
      expect(p.dx).toBeGreaterThanOrEqual(PIN_AREA.x0)
      expect(p.dx).toBeLessThan(PIN_AREA.x0 + PIN_AREA.w)
      expect(p.dy).toBeGreaterThanOrEqual(PIN_AREA.y0)
      expect(p.dy).toBeLessThan(PIN_AREA.y0 + PIN_AREA.h)
      expect(NOTE_PIN_COLORS).toContain(p.color)
    }
  })

  it('pin cap honors the rate-routing law (texture, bounded)', () => {
    expect(NOTE_PIN_MAX).toBe(12)
  })

  it('paper hues avoid the reserved salience palette', () => {
    const reserved = new Set([0x22c55e, 0xf59e0b, 0xcc2222, 0xef4444, 0x9ca3af, 0xa855f7])
    for (const c of NOTE_PIN_COLORS) {
      expect(reserved.has(c), `0x${c.toString(16)}`).toBe(false)
    }
  })
})

describe('decor discipline', () => {
  it('every decor id is unique (stable sprite cache keys)', () => {
    const ids = DECOR.map((d) => d.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('cozy sheet universe is covered by the committed manifest via the loud chain', () => {
    const manifest = JSON.parse(
      fs.readFileSync(MANIFEST_PATH, 'utf8')
    ) as WorldAssetManifest
    const { urls, missing } = resolveWorldSprites(manifest)
    expect(missing).toEqual([])
    for (const id of setDressingSheets()) {
      expect(urls[id], id).toBeDefined()
    }
  })

  it('cozy sheets participate in requiredSheets (missing → badged, never silent)', () => {
    const { missing } = resolveWorldSprites({ version: 2, assets: [] })
    for (const id of setDressingSheets()) {
      expect(missing, id).toContain(id)
    }
    for (const id of [RUG_RUNNER.sheet, ALCOVE.rugSheet, ALCOVE.cabinetSheet, KETTLE_SHEET, NOTICEBOARD_SHEET]) {
      expect(missing, id).toContain(id)
    }
  })
})
