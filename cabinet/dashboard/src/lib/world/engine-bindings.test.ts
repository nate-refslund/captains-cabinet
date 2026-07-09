/**
 * v1a review-fix bindings: the RECOMPOSED lighthouse (Captain ruling
 * 2026-07-09 — NEVER the water-tank/silo body), staged-vocab honesty,
 * the officer-character universe at island tier, and the verb-icon table.
 */
import { describe, expect, it } from 'vitest'
import {
  BUCKET_LOAD,
  ENGINE_CHARACTER_SHEETS,
  FARM_TREES,
  LIGHTHOUSE_BASE,
  LIGHTHOUSE_FULL,
  LIGHTHOUSE_LIT_SHEET,
  LIGHTHOUSE_PART,
  LIGHTHOUSE_SHEET,
  lighthouseCutFor,
  requiredOutdoorSheets,
  STAGED_VOCAB_ELEMENTS,
  UI_SHEET,
  VERB_ICONS,
  verbIconCut,
  WORKSITE_KIT,
} from './sprites-outdoor'
import { ROOM_SHEET } from './sprites'

describe('lighthouse recomposition (ruling: lamp must fit the tower)', () => {
  it('binds the ratified derived 21_Beach tower variants, never the farm silo', () => {
    // forge-derived from the pack's REAL lighthouse tiles (t4 ratified art:
    // unlit honest-zero + lit lamp-room variant) — the silo body is retired
    expect(LIGHTHOUSE_SHEET).toBe('derived/lighthouse/lighthouse_unlit')
    expect(LIGHTHOUSE_LIT_SHEET).toBe('derived/lighthouse/lighthouse_lit')
    expect(LIGHTHOUSE_SHEET).not.toContain('farm')
  })

  it('stages per the growth ladder: cairn → base → part → full', () => {
    expect(lighthouseCutFor('dark_cairn')).toBeNull() // rock cairn composition
    expect(lighthouseCutFor('stone_base')).toEqual(LIGHTHOUSE_BASE)
    expect(lighthouseCutFor('tower_part')).toEqual(LIGHTHOUSE_PART)
    expect(lighthouseCutFor('tower_full')).toEqual(LIGHTHOUSE_FULL)
    expect(lighthouseCutFor('bogus')).toBeNull() // unknown → honest cairn
  })

  it('staged cuts are bottom-anchored slices of the SAME 112x256 sheet', () => {
    for (const cut of [LIGHTHOUSE_BASE, LIGHTHOUSE_PART, LIGHTHOUSE_FULL]) {
      expect(cut.w).toBe(112)
      expect(cut.y + cut.h).toBe(256) // grows upward from the same base
    }
    expect(LIGHTHOUSE_BASE.h).toBeLessThan(LIGHTHOUSE_PART.h)
    expect(LIGHTHOUSE_PART.h).toBeLessThan(LIGHTHOUSE_FULL.h)
  })
})

describe('era-vocab honesty (staged markers, not wrong objects)', () => {
  it('library + observatory are declared staged (worksite marker render)', () => {
    expect(STAGED_VOCAB_ELEMENTS.has('library')).toBe(true)
    expect(STAGED_VOCAB_ELEMENTS.has('observatory')).toBe(true)
  })

  it('the island sheet universe carries the worksite kit + water store', () => {
    const island = requiredOutdoorSheets('island')
    for (const id of Object.values(WORKSITE_KIT)) expect(island).toContain(id)
    expect(island).toContain(BUCKET_LOAD)
  })
})

describe('officer presence at island tier (E1 acceptance headline)', () => {
  it('all 20 character sheets + the interior kit ride the island universe', () => {
    const island = requiredOutdoorSheets('island')
    expect(ENGINE_CHARACTER_SHEETS).toHaveLength(20)
    for (const id of ENGINE_CHARACTER_SHEETS) expect(island).toContain(id)
    expect(island).toContain(ROOM_SHEET)
    expect(island).toContain(LIGHTHOUSE_SHEET)
    expect(island).toContain(LIGHTHOUSE_LIT_SHEET)
    expect(island).toContain(FARM_TREES) // corpus tree canon
    expect(island).toContain(UI_SHEET)
  })
})

describe('commute bubble verb icons (closed table, pixel icons only)', () => {
  it('maps the closed verb set onto verified pack cuts', () => {
    expect(verbIconCut('replying')).toEqual(VERB_ICONS.mail)
    expect(verbIconCut('coordinating')).toEqual(VERB_ICONS.people)
    expect(verbIconCut('deploying')).toEqual(VERB_ICONS.up)
    expect(verbIconCut('shipping')).toEqual(VERB_ICONS.up)
    expect(verbIconCut('working')).toEqual(VERB_ICONS.gear)
    expect(verbIconCut('anything-else')).toEqual(VERB_ICONS.gear) // total fn
  })
})
