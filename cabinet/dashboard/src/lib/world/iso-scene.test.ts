/**
 * ISO-SCENE — the delivery path, held to the properties that make it worth
 * having.
 *
 * The load-bearing arms, each stated as the failure it catches:
 *   - the ERA LAW: what a state wears is the pack's answer for (object, era,
 *     rung). Without it a camp island grows a stone lighthouse and a town wears
 *     hamlet cottages, and nothing anywhere goes red.
 *   - SPACED IS DRAWN: the footprint composeLayout measured with is the drawn
 *     size of the frame the renderer resolves. A mismatch is every spacing rule
 *     in the layout enforcing the wrong distance and reporting that it did.
 *   - NOTHING IS DROPPED SILENTLY: every emitted thing either resolves or
 *     lands in `issues`.
 *   - TRACEABILITY: a sprite carries the state object that justifies it, or
 *     an honest null.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import {
  buildLaneField,
  composeLayout,
  DEFAULT_FOOTPRINTS,
  type Era,
  type LayoutState,
} from './iso-layout'
import { parsePack, type IsoPack } from './iso-pack'
import {
  buildIsoScene,
  cameraClamp,
  cameraHome,
  LANE_PAINT_SQUASH,
  layoutStateFrom,
  NO_STATE_KINDS,
  packFootprintOf,
  pickIsoSprite,
  resolveFrame,
} from './iso-scene'
import { projectionFor } from './projection'
import type { WorldResolution } from './era-engine'

const PACK_PATH = path.resolve(
  __dirname,
  '..',
  '..',
  '..',
  'public',
  'world-assets',
  'originals',
  'iso',
  'world-pack.json'
)
const PACK: IsoPack = parsePack(JSON.parse(fs.readFileSync(PACK_PATH, 'utf8')))
const ERAS: readonly Era[] = ['camp', 'hamlet', 'town', 'beyond_bay']

/** A built-out state per era, using REAL rung names from growth-ladders.yml. */
function stateFor(era: Era): LayoutState {
  return {
    era,
    road: era === 'camp' ? 'dirt_path' : 'gravel_road',
    stages: {
      great_house: era === 'camp' ? 'cottage' : 'great_house',
      officer_dwellings: 'dwellings_4',
      library: 'library_hall',
      workshop: 'shed',
      outbuildings: 'small_barn',
      well: 'well',
      firepit: 'stone_ring',
      lighthouse: era === 'camp' ? 'dark_cairn' : 'tower_full',
      lighthouse_lamp: 'lit',
      quay: 'timber_jetty',
      warehouse: 'warehouse',
      harbormaster_hut: 'hut',
      harbor_boat: 'packet_boat',
      cargo_stacks: 'crates_mid',
      berths: 'berths_2',
      field_plots: 'plots_2',
      road: era === 'camp' ? 'dirt_path' : 'gravel_road',
    },
    counts: {
      officer_dwellings: 4,
      field_plots: 2,
      berths: 2,
      cargo_stacks: 2,
      warehouse: 2,
    },
  }
}

describe('iso-scene — the layout, dressed in the shipped pack', () => {
  it('composes and dresses a world at every era with ZERO unresolved things', () => {
    for (const era of ERAS) {
      const scene = buildIsoScene(PACK, stateFor(era), 'cabinet')
      expect(scene.issues, `${era} issues`).toEqual([])
      expect(scene.sprites.length, `${era} sprite count`).toBeGreaterThan(50)
      for (const s of scene.sprites) {
        expect(PACK.frames[s.frame], `${era}: ${s.frame}`).toBeDefined()
        expect(s.dw).toBeGreaterThan(0)
        expect(s.dh).toBeGreaterThan(0)
        expect(Number.isFinite(s.x) && Number.isFinite(s.y)).toBe(true)
      }
    }
  })

  it('THE ERA LAW: a camp island never wears later-era art', () => {
    const camp = buildIsoScene(PACK, stateFor('camp'), 'cabinet')
    const late = camp.sprites.filter((s) => s.frame.startsWith('town_') || s.frame.startsWith('bay_'))
    expect(late.map((s) => `${s.role}/${s.frame}`)).toEqual([])
    // the specific lie this rule exists for: the layout emits kind
    // 'lighthouse' at every era, and at camp the rung is a dark cairn
    const lh = camp.sprites.find((s) => s.role === 'lighthouse')
    expect(lh?.frame).toBe('camp_dark_cairn')
    // …and the great house is a log cabin, not a stone hall
    expect(camp.sprites.find((s) => s.role === 'great_house')?.frame).toBe('camp_log_cabin')
  })

  it('THE ERA LAW: a town dresses its dwellings in town art, not hamlet art', () => {
    // The layout's dwellingKind only gates at camp — at town it hands back the
    // hamlet house set. The pack's table is what corrects that, and this is the
    // arm that would go red if the table stopped deciding.
    for (const era of ERAS) {
      const scene = buildIsoScene(PACK, stateFor(era), 'cabinet')
      const dwellings = scene.sprites.filter((s) => s.role === 'officer_dwelling')
      expect(dwellings.length, `${era} dwellings`).toBeGreaterThan(0)
      const expected: Record<Era, RegExp> = {
        camp: /^camp_tent$/,
        hamlet: /^(officer_house_[abc]|cottage_[abc])$/,
        town: /^town_cottage$/,
        beyond_bay: /^bay_townhouse$/,
      }
      for (const d of dwellings) expect(d.frame, `${era} dwelling`).toMatch(expected[era])
    }
  })

  it('per-lot dwelling VARIETY survives the era law at hamlet', () => {
    // The refinement is the whole reason the guard is a family check and not a
    // flat "the table always wins": one house six times is what the layout
    // deliberately stopped doing.
    const scene = buildIsoScene(PACK, { ...stateFor('hamlet'), counts: { officer_dwellings: 5 } }, 'cabinet')
    const frames = new Set(
      scene.sprites.filter((s) => s.role === 'officer_dwelling').map((s) => s.frame)
    )
    expect(frames.size).toBeGreaterThan(1)
  })

  it('SPACED IS DRAWN: the footprint the layout measured is the frame drawn', () => {
    for (const era of ERAS) {
      const state = stateFor(era)
      const fp = packFootprintOf(PACK, state)
      const scene = buildIsoScene(PACK, state, 'cabinet')
      for (const st of scene.layout.structures) {
        const drawn = scene.sprites.find((s) => s.role === st.role && s.x === st.at.x && s.y === st.at.y)
        expect(drawn, `${era}: no sprite for ${st.role} at ${st.at.x},${st.at.y}`).toBeDefined()
        expect({ w: drawn!.dw, h: drawn!.dh }, `${era}: ${st.role} spaced-vs-drawn`).toEqual(st.size)
        // …and the size the layout used came from the pack, not the fallback
        expect(fp(st.kind), `${era}: ${st.kind} footprint`).toEqual(st.size)
      }
    }
  })

  it('the pack footprint really OVERRIDES the era-blind default table', () => {
    // If packFootprintOf silently returned undefined the layout would fall back
    // to DEFAULT_FOOTPRINTS and this whole arm would pass vacuously — so the
    // difference is asserted, at the era where it is largest.
    const state = stateFor('camp')
    const fp = packFootprintOf(PACK, state)
    expect(DEFAULT_FOOTPRINTS.great_house).toEqual({ w: 200, h: 200 })
    expect(fp('great_house')).toEqual({ w: 128, h: 120 })
    expect(fp('lighthouse')).toEqual({ w: 88, h: 126 })
    // …and at town the same kind is a different size again
    const town = packFootprintOf(PACK, stateFor('town'))
    expect(town('great_house')).toEqual({ w: 192, h: 196 })
  })

  it('every kind a composed world emits either has state behind it or is listed', () => {
    const seen = new Set<string>()
    for (const era of ERAS) {
      const scene = buildIsoScene(PACK, stateFor(era), 'cabinet')
      for (const s of scene.sprites) if (s.role === null) seen.add(s.frame)
    }
    // Nature is nature: it has no ladder and says so. Everything else with a
    // null role must be on the documented no-state list, so a role that
    // QUIETLY stops resolving cannot join it by accident.
    //
    // THE AUTHORITY IS cabinet/scripts/world-capture/ambient-nature.txt and this
    // pattern was missing two of its names — `mushrooms` and `lilypads`. It went
    // unnoticed because neither had ever landed on the four fixture islands; the
    // inverted planting model (iso-layout/clearing.ts) reaches ground the old
    // sparse interior never did, and mushrooms turned up on the first camp
    // frame. A filter that only fires on the cases it has seen is a sensor with
    // a hole in it, so the pattern is now the whole ambient set.
    const notNature = [...seen].filter(
      (f) => !/^(tree_|bush_|fern_|flowers_|rock_|reeds|fallen_log|tree_stump|mushrooms|lilypads)/.test(f)
    )
    for (const f of notNature) expect(NO_STATE_KINDS.has(f), `${f} has no state and is not listed`).toBe(true)
  })

  it('NOTHING IS DROPPED SILENTLY: an unresolvable thing lands in issues', () => {
    // Strip the great_house object out of the table and the sprite must be
    // REPORTED, not quietly absent. (kind 'great_house' is itself a frame, so
    // this is engineered against a kind the pack cannot draw either.)
    const crippled: IsoPack = {
      ...PACK,
      resolve: { ...PACK.resolve },
      frames: { ...PACK.frames },
    }
    delete (crippled.resolve as Record<string, unknown>).great_house
    delete (crippled.frames as Record<string, unknown>).great_house
    delete (crippled.frames as Record<string, unknown>).camp_log_cabin
    const scene = buildIsoScene(crippled, stateFor('camp'), 'cabinet')
    expect(scene.issues.some((i) => i.includes('great_house'))).toBe(true)
    expect(scene.sprites.some((s) => s.role === 'great_house')).toBe(false)
  })

  it('the lamp is emitted ONLY when a tower holds it', () => {
    const lit = buildIsoScene(PACK, stateFor('hamlet'), 'cabinet')
    expect(lit.lamp).not.toBeNull()
    expect(lit.lamp!.y).toBeLessThan(lit.layout.lighthouse!.at.y)
    // rung says lit, but a camp cairn is not a tower — LAMP_AT stays null
    const cairn = buildIsoScene(PACK, stateFor('camp'), 'cabinet')
    expect(cairn.layout.lighthouse!.lamp.rungLit).toBe(true)
    expect(cairn.layout.lighthouse!.lamp.lit).toBe(false)
    expect(cairn.lamp).toBeNull()
    // and an unlit lamp on a real tower is null too
    const dark = buildIsoScene(
      PACK,
      { ...stateFor('hamlet'), stages: { ...stateFor('hamlet').stages, lighthouse_lamp: 'dark' } },
      'cabinet'
    )
    expect(dark.lamp).toBeNull()
  })

  it('sprites come back depth-sorted by base y, with a stable tie-break', () => {
    const scene = buildIsoScene(PACK, stateFor('hamlet'), 'cabinet')
    for (let i = 1; i < scene.sprites.length; i++) {
      expect(scene.sprites[i].depth).toBeGreaterThanOrEqual(scene.sprites[i - 1].depth)
    }
    // depth IS the base y — the value the renderer's sortableChildren layer
    // already consumes, not a second notion of front-to-back
    for (const s of scene.sprites) expect(s.depth).toBe(s.y)
    const again = buildIsoScene(PACK, stateFor('hamlet'), 'cabinet')
    expect(again.sprites.map((s) => s.id)).toEqual(scene.sprites.map((s) => s.id))
  })

  it('layoutStateFrom reads rung NAMES for stages and rung INDEX for counts', () => {
    const res = {
      era: 'town',
      eraIndex: 2,
      eraUnmeasured: [],
      transition: null,
      elements: {
        officer_dwellings: { rung: 4, rungName: 'dwellings_4', vocab: null, pending: null, measured: true, value: 4 },
        road: { rung: 2, rungName: 'gravel_road', vocab: null, pending: null, measured: true, value: 2 },
      },
      lanes: {},
    } as unknown as WorldResolution
    const st = layoutStateFrom(res)
    expect(st.era).toBe('town')
    expect(st.road).toBe('gravel_road')
    expect(st.stages?.officer_dwellings).toBe('dwellings_4')
    expect(st.counts?.officer_dwellings).toBe(4)
    // an absent or nonsense resolution falls to the honest floor, never throws
    expect(layoutStateFrom(null)).toEqual({ era: 'camp', road: 'dirt_path', stages: {}, counts: {} })
    const junk = { era: 'atlantis', elements: { road: { rung: 0, rungName: 'hyperloop' } } } as unknown as WorldResolution
    expect(layoutStateFrom(junk).era).toBe('camp')
    expect(layoutStateFrom(junk).road).toBe('dirt_path')
  })

  it('resolveFrame: the table decides, the kind may only refine within the family', () => {
    // table wins outright when the kind is a different era
    expect(resolveFrame(PACK, 'officer_dwellings', 'cottage_a', 'town', 'dwellings_4')).toEqual({
      frame: 'town_cottage',
      trueArt: true,
      refined: false,
    })
    // …and refines within it
    expect(resolveFrame(PACK, 'officer_dwellings', 'cottage_a', 'hamlet', 'dwellings_4')).toEqual({
      frame: 'cottage_a',
      trueArt: true,
      refined: true,
    })
    // an object with no table entry draws its kind — nothing measured it
    expect(resolveFrame(PACK, null, 'tree_oak', 'town', undefined)?.frame).toBe('tree_oak')
    // a kind the pack cannot draw, with no table entry, is NULL (loud)
    expect(resolveFrame(PACK, null, 'unicorn', 'town', undefined)).toBeNull()
    // a rung the object's era row does not carry and has no '*' is NULL too
    expect(resolveFrame(PACK, 'harbor_boat', 'harbor_boat', 'hamlet', 'galleon')).toBeNull()
  })

  it('the camera home and clamp are derived from the layout, through the kernel', () => {
    const home = cameraHome('iso')
    const px = projectionFor('iso').project(home.x, home.y)
    expect(px.x).toBeCloseTo(1200, 6)
    expect(px.y).toBeCloseTo(760, 6)
    // top-down keeps its own home untouched
    expect(cameraHome('topdown')).toEqual({ x: 120, y: 32 })
    // the clamp box spans all four PROJECTED corners; a top-down-shaped box
    // would cut two of them off and the world could not pan to its harbour
    const b = cameraClamp('iso', { w: 240, h: 192 }, 6)
    for (const [x, y] of [[0, 0], [2400, 0], [0, 1760], [2400, 1760]] as const) {
      const t = projectionFor('iso').unproject(x, y)
      expect(t.tx).toBeGreaterThanOrEqual(b.x0)
      expect(t.tx).toBeLessThanOrEqual(b.x1)
      expect(t.ty).toBeGreaterThanOrEqual(b.y0)
      expect(t.ty).toBeLessThanOrEqual(b.y1)
    }
    // …and the TOP-DOWN clamp is still the archipelago canvas plus its margin,
    // untouched: the iso derivation must never reach the other kernel.
    expect(cameraClamp('topdown', { w: 240, h: 192 })).toEqual({
      x0: -24,
      y0: -24,
      x1: 264,
      y1: 216,
    })
  })

  it('an empty state draws the world that has been earned, and no more', () => {
    // The degenerate end: nothing measured. The objects whose empty rung IS the
    // drawing still appear (a cairn is a lighthouse nobody has earned); nothing
    // else does, and nothing is reported as broken.
    const scene = buildIsoScene(PACK, { era: 'camp', road: 'dirt_path' }, 'cabinet')
    expect(scene.issues).toEqual([])
    const roles = new Set(scene.sprites.map((s) => s.role).filter((r): r is string => r !== null))
    expect(roles.has('lighthouse')).toBe(true)
    expect(roles.has('firepit')).toBe(true)
    expect(roles.has('library')).toBe(false)
    expect(roles.has('warehouse')).toBe(false)
    expect(roles.has('officer_dwelling')).toBe(false)
    expect(scene.lamp).toBeNull()
  })

  it('reusing a prepared layout gives the same scene as composing it', () => {
    const state = stateFor('hamlet')
    const layout = composeLayout(state, 'cabinet', { footprintOf: packFootprintOf(PACK, state) })
    const a = buildIsoScene(PACK, state, 'cabinet', { layout })
    const b = buildIsoScene(PACK, state, 'cabinet')
    expect(a.sprites).toEqual(b.sprites)
  })
})

describe('the painted lane band is the corridor the rules reserved', () => {
  it('LANE_PAINT_SQUASH reproduces buildLaneField measured, not copied', () => {
    // iso-layout keeps its squash private, so this MEASURES the field instead
    // of grepping for a literal: walk out in x and in y from a lane sample
    // until onLane flips, and take the ratio of the two reaches. A copied
    // number can rot; a measurement cannot.
    const half = 40
    const lane = {
      key: 'probe',
      kind: 'main' as const,
      width: half * 2,
      runs: [[{ x: 1000, y: 1000 }]],
    }
    const field = buildLaneField([lane])
    const reach = (dx: number, dy: number): number => {
      let lo = 0
      let hi = 400
      for (let i = 0; i < 40; i++) {
        const mid = (lo + hi) / 2
        if (field.onLane(1000 + dx * mid, 1000 + dy * mid)) lo = mid
        else hi = mid
      }
      return lo
    }
    const rx = reach(1, 0)
    const ry = reach(0, 1)
    expect(rx).toBeCloseTo(half, 3)
    expect(ry / rx).toBeCloseTo(LANE_PAINT_SQUASH, 4)
  })
})

describe('the iso pick — the world answers when you click it', () => {
  // THE ARM THIS REPLACES was `if (isIso) return { kind: 'ground' }` in
  // engine-canvas: the whole iso world was inert, and its docstring said the
  // world "carries no data" — true only because nothing had been written to
  // answer. Every assertion below FAILS against that constant.
  const state = stateFor('hamlet')
  const scene = buildIsoScene(PACK, state, 'cabinet-pick')

  it('picks the sprite whose ground diamond holds the point, not the one behind it', () => {
    const measured = scene.sprites.filter((s) => s.role !== null)
    expect(measured.length).toBeGreaterThan(10)
    // A sprite's own base centre is the front vertex of its own diamond, so a
    // pick there must return that sprite or one drawn IN FRONT of it (which is
    // a real occlusion, not a miss) — never nothing, and never one behind.
    let exact = 0
    for (const s of measured) {
      const hit = pickIsoSprite(scene, s.x, s.y - 1)
      expect(hit).not.toBeNull()
      if (hit!.id === s.id) exact++
      else expect(hit!.depth).toBeGreaterThanOrEqual(s.depth)
    }
    // the overwhelming majority are unoccluded at their own base
    expect(exact / measured.length).toBeGreaterThan(0.8)
  })

  it('skips decoration so a bush cannot answer for the building behind it', () => {
    const decor = scene.sprites.filter((s) => s.role === null)
    expect(decor.length).toBeGreaterThan(50)
    for (const d of decor.slice(0, 40)) {
      const hit = pickIsoSprite(scene, d.x, d.y - 1)
      // whatever answers, it is never the decoration itself
      if (hit) expect(hit.role).not.toBeNull()
    }
    // …and asking for decoration explicitly does return it
    const withDecor = pickIsoSprite(scene, decor[0].x, decor[0].y - 1, {
      includeDecorative: true,
    })
    expect(withDecor).not.toBeNull()
  })

  it('answers null on open sea — no phantom target off the island', () => {
    expect(pickIsoSprite(scene, 40, 40)).toBeNull()
    expect(pickIsoSprite(scene, 2360, 1720)).toBeNull()
  })

  it('the pointer conversion is the projection kernel run forward', () => {
    // engine-canvas converts a TILE-space pointer to the LAYOUT PIXEL the
    // sprites live in with proj.project(); this pins that the round trip is
    // exact, because a pick one tile out is a card about the wrong building.
    const proj = projectionFor('iso')
    for (const s of scene.sprites.slice(0, 25)) {
      const t = proj.unproject(s.x, s.y)
      const back = proj.project(t.tx, t.ty)
      expect(back.x).toBeCloseTo(s.x, 6)
      expect(back.y).toBeCloseTo(s.y, 6)
    }
  })
})
