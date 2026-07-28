/**
 * The shipped iso pack, held to its own contract.
 *
 * Every arm here runs against the file the RENDERER fetches
 * (public/world-assets/originals/iso/world-pack.json), not a fixture: a fixture
 * would let the shipped pack rot while the suite stayed green, which is the
 * same defect as pointing a check at a dead twin.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import yaml from 'js-yaml'
import {
  drawSize,
  eraOfFrame,
  frameFor,
  isEmptyRung,
  packFootprints,
  parsePack,
  type IsoPack,
} from './iso-pack'

const DASH = path.resolve(__dirname, '..', '..', '..')
const PACK_PATH = path.join(DASH, 'public', 'world-assets', 'originals', 'iso', 'world-pack.json')
const ATLAS_PATH = path.join(DASH, 'public', 'world-assets', 'originals', 'iso', 'atlas-0.png')
const LADDERS_PATH = path.resolve(DASH, '..', 'world', 'growth-ladders.yml')

const RAW = JSON.parse(fs.readFileSync(PACK_PATH, 'utf8')) as Record<string, unknown>
const PACK: IsoPack = parsePack(RAW)
const ERAS = ['camp', 'hamlet', 'town', 'beyond_bay'] as const

/**
 * The ladders the pack deliberately does not dress, because the renderer draws
 * them procedurally: the road surface, the wharf, the lamp glow, the lit-post
 * count and the per-lane isle rings. Named here so a ladder that QUIETLY stops
 * resolving fails instead of joining the list.
 */
const PROCEDURAL_LADDERS = new Set(['quay', 'road', 'lane_isles', 'lighthouse_lamp', 'posts_lit'])

interface LaddersFile {
  ladders: Record<string, { rungs?: string[] }>
}

describe('iso-pack — the shipped pack', () => {
  it('the atlas the pack names is on disk, is a PNG, and is on the 16px grid', () => {
    expect(PACK.atlases).toEqual(['atlas-0.png'])
    const bytes = fs.readFileSync(ATLAS_PATH)
    expect(bytes.subarray(0, 8)).toEqual(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))
    const w = bytes.readUInt32BE(16)
    const h = bytes.readUInt32BE(20)
    expect(w).toBe(PACK.atlasSize)
    expect(h).toBe(PACK.atlasSize)
    expect(w % 16).toBe(0)
  })

  it('every frame anchors at its BASE CENTRE — the renderer sets (0.5, 1) and stops', () => {
    const names = Object.keys(PACK.frames)
    expect(names.length).toBeGreaterThan(100)
    for (const n of names) {
      const f = PACK.frames[n]
      expect(f.anchor[0], `${n} anchor x`).toBeCloseTo(f.dw / 2, 9)
      expect(f.anchor[1], `${n} anchor y`).toBe(f.dh)
    }
  })

  it('drawn size is CARRIED, never derived from scale (28 frames disagree)', () => {
    const odd = Object.entries(PACK.frames).filter(([, f]) => f.dw !== f.w / f.scale)
    // If this ever hits zero the rule is still right, but the REASON stated in
    // iso-pack.ts would have stopped being true — so it is asserted, not assumed.
    expect(odd.length).toBeGreaterThan(0)
    for (const [n, f] of odd) {
      expect(drawSize(PACK, n)).toEqual({ w: f.dw, h: f.dh })
      expect(f.dw).toBe(Math.floor(f.w / f.scale))
    }
  })

  it('EVERY ladder × era × rung either resolves, is an empty rung, or is procedural', () => {
    // js-yaml load() is safe-by-default since v4 (no custom types) — the same
    // call ladders-loader.ts makes on this same file.
    const cfg = yaml.load(fs.readFileSync(LADDERS_PATH, 'utf8')) as LaddersFile
    const ladders = Object.entries(cfg.ladders)
    expect(ladders.length).toBeGreaterThan(20)
    const uncovered: string[] = []
    const holes: string[] = []
    for (const [name, lad] of ladders) {
      const rungs = lad.rungs ?? []
      expect(rungs.length, `${name} has no rungs`).toBeGreaterThan(0)
      if (!PACK.resolve[name]) {
        uncovered.push(name)
        continue
      }
      for (const era of ERAS) {
        for (const rung of rungs) {
          if (isEmptyRung(PACK, rung)) continue
          if (!frameFor(PACK, name, era, rung)) holes.push(`${name}/${era}/${rung}`)
        }
      }
    }
    expect(holes).toEqual([])
    expect(new Set(uncovered)).toEqual(PROCEDURAL_LADDERS)
  })

  it('eraOfFrame parses the generator prefix convention', () => {
    expect(eraOfFrame('great_house')).toBe('hamlet')
    expect(eraOfFrame('camp_tent')).toBe('camp')
    expect(eraOfFrame('town_cottage')).toBe('town')
    expect(eraOfFrame('bay_townhouse')).toBe('beyond_bay')
    // A BARE frame is era-NEUTRAL kit, not "hamlet-only": the pack reuses
    // mooring_post, flagpole and boat_rowing at camp on purpose. Measured
    // against the shipped table rather than assumed, because iso-scene's
    // refinement guard compares two frames' families and a wrong reading there
    // would let a hamlet cottage stand in a town.
    const bareAtCamp = Object.entries(PACK.resolve).flatMap(([obj, byEra]) =>
      Object.entries(byEra.camp ?? {})
        .filter(([, hit]) => eraOfFrame(hit.frame) !== 'camp')
        .map(([rung, hit]) => `${obj}/${rung}->${hit.frame}`)
    )
    expect(new Set(bareAtCamp)).toEqual(
      new Set([
        'berths/*->mooring_post',
        'flagpole/pennant->flagpole',
        'harbor_boat/*->boat_rowing',
        'noticeboard/board->noticeboard',
      ])
    )
  })

  it('a CAMP island never wears town or bay art — the era law with teeth', () => {
    const ahead: string[] = []
    for (const [obj, byEra] of Object.entries(PACK.resolve)) {
      for (const [rung, hit] of Object.entries(byEra.camp ?? {})) {
        const fe = eraOfFrame(hit.frame)
        if (fe === 'town' || fe === 'beyond_bay') ahead.push(`${obj}/${rung}->${hit.frame}`)
      }
    }
    expect(ahead).toEqual([])
  })

  it('honest zero: the pack table answers, and ABSENT answers the same as empty', () => {
    for (const r of ['none', 'bare_ground', 'bare_pole', 'bare_wall', 'dark', 'first_post']) {
      expect(isEmptyRung(PACK, r), r).toBe(true)
    }
    expect(isEmptyRung(PACK, null)).toBe(true)
    expect(isEmptyRung(PACK, undefined)).toBe(true)
    expect(isEmptyRung(PACK, '')).toBe(true)
    expect(isEmptyRung(PACK, 'tower_full')).toBe(false)
    expect(isEmptyRung(PACK, 'great_house')).toBe(false)
  })

  it("frameFor honours the era's '*' row and returns null rather than guessing", () => {
    // an exact rung wins over '*'
    expect(frameFor(PACK, 'great_house', 'hamlet', 'cottage')?.frame).toBe('cottage_a')
    expect(frameFor(PACK, 'great_house', 'hamlet', 'great_house')?.frame).toBe('great_house')
    // '*' catches the rest
    expect(frameFor(PACK, 'great_house', 'town', 'anything')?.frame).toBe('town_manor')
    // an unknown object, era or rung with no '*' is NULL, not a fallback
    expect(frameFor(PACK, 'no_such_object', 'hamlet', 'x')).toBeNull()
    expect(frameFor(PACK, 'great_house', 'no_such_era', 'cottage')).toBeNull()
    expect(frameFor(PACK, 'harbor_boat', 'hamlet', 'no_such_rung')).toBeNull()
  })

  it('the pack ships zero placeholders — REPORTED, not assumed', () => {
    const fake: string[] = []
    for (const [obj, byEra] of Object.entries(PACK.resolve)) {
      for (const [era, byRung] of Object.entries(byEra)) {
        for (const [rung, hit] of Object.entries(byRung)) {
          if (!hit.trueArt) fake.push(`${obj}/${era}/${rung}`)
        }
      }
    }
    expect(fake).toEqual([])
  })

  it('packFootprints hands the layout the DRAWN size, and undefined for a stranger', () => {
    const fp = packFootprints(PACK)
    expect(fp('great_house')).toEqual({ w: PACK.frames.great_house.dw, h: PACK.frames.great_house.dh })
    expect(fp('not_a_frame')).toBeUndefined()
  })

  describe('parsePack refuses rather than draws a nearly-right world', () => {
    const clone = () => JSON.parse(JSON.stringify(RAW)) as Record<string, unknown>

    it('a wrong schema is fatal', () => {
      const bad = clone()
      bad.schema = 'cabinet.world.iso-pack/v2'
      expect(() => parsePack(bad)).toThrow(/schema/)
    })

    it('a resolve row naming an absent frame is fatal', () => {
      const bad = clone()
      ;(bad.resolve as Record<string, Record<string, Record<string, { frame: string }>>>).great_house.town[
        '*'
      ].frame = 'ghost_frame'
      expect(() => parsePack(bad)).toThrow(/absent frame ghost_frame/)
    })

    it('a frame outside the atlas is fatal', () => {
      const bad = clone()
      ;(bad.frames as Record<string, { x: number }>).great_house.x = 4000
      expect(() => parsePack(bad)).toThrow(/outside the .* atlas/)
    })

    it('a zero-size frame is fatal', () => {
      const bad = clone()
      ;(bad.frames as Record<string, { dw: number }>).great_house.dw = 0
      expect(() => parsePack(bad)).toThrow(/non-positive size/)
    })

    it('an empty pack is fatal — a pack that draws nothing must not parse', () => {
      const bad = clone()
      bad.frames = {}
      bad.resolve = {}
      expect(() => parsePack(bad)).toThrow(/ships no frames/)
    })

    it('a non-object, a missing note and a missing atlas list are each fatal', () => {
      expect(() => parsePack(null)).toThrow(/not an object/)
      expect(() => parsePack('{}')).toThrow(/not an object/)
      const noNote = clone()
      delete noNote.note
      expect(() => parsePack(noNote)).toThrow(/note is missing/)
      const noAtlas = clone()
      noAtlas.atlases = []
      expect(() => parsePack(noAtlas)).toThrow(/atlases is empty/)
    })
  })
})
