/**
 * ISO-LIFE — the tests.
 *
 * EVERY GEOMETRIC ARM IS DRIVEN AGAINST A REAL COMPOSED LAYOUT, not a hand-made
 * fixture, wherever the claim is about the layout. A fixture would let this file
 * agree with itself while the island disagreed with both — which is exactly how
 * `SITE_LOT_GROUP` (a table restating an association `composeLayout` builds
 * inline and does not export) could rot silently. So that table is checked by
 * composing a layout in which each element IS built and asserting the structure
 * landed on the lot the table names.
 *
 * Hand fixtures ARE used where the claim is about arithmetic that must hold for
 * ANY layout — a road walk, a hit box, the front-to-back order of a pick.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  commuteRoad,
  COMMUTE_LANE_KEY,
  crewSlot,
  figureBox,
  hoardingPanels,
  isoApprentices,
  isoFacing,
  isoOfficerYard,
  isoSitePad,
  isoSites,
  isoWalkers,
  padDither,
  pendingMarks,
  pickIsoFigure,
  pickIsoSite,
  PERSON_H_PX,
  PERSON_SCALE,
  SITE_LOT_GROUP,
  YARD_SETBACK,
  YARD_SPREAD,
  type IsoFigure,
} from './iso-life'
import { composeLayout, type Layout, type LayoutState } from './iso-layout'
import { LANE_SQUASH } from './iso-layout/lanes'
import { fnv1a } from './hash'
import { CHAR_FRAME_H } from './sprites'
import type { CommuterOut, SiteOut } from './life/life'
import type { WorkSite } from './life/sites'

const SEED = 'cabinet-world'

/** A hamlet with four dwellings, a library, a workshop and outbuildings. */
const HAMLET: LayoutState = {
  era: 'hamlet',
  road: 'dirt_worn',
  stages: {
    great_house: 'hall',
    library: 'shelf_row',
    workshop: 'bench',
    officer_dwellings: 'dwellings_4',
    berths: 'berths_7plus',
    quay: 'stone_quay',
    outbuildings: 'shed',
  },
  counts: {
    great_house: 2,
    library: 2,
    workshop: 1,
    officer_dwellings: 4,
    berths: 7,
    quay: 3,
    outbuildings: 1,
  },
}

const CAMP: LayoutState = {
  era: 'camp',
  road: 'dirt_path',
  stages: { great_house: 'hall', officer_dwellings: 'none' },
  counts: { great_house: 1, officer_dwellings: 0 },
}

const hamlet = (): Layout => composeLayout(HAMLET, SEED)

function commuter(slug: string, to: 'quay' | 'village', progress: number, glance = false): CommuterOut {
  return {
    slug,
    walk: { from: to === 'quay' ? 'village' : 'quay', to, startTick: 0, walkTicks: 120, bubble: null },
    progress,
    glance,
  }
}

function site(element: string, id = `s:${element}`): SiteOut {
  const w: WorkSite = {
    id,
    element,
    targetStage: 'next',
    siteClass: 'quick_large',
    t0Tick: 0,
    footprint: { x: 10, y: 10, w: 4, h: 3 },
    witness: { kind: 'chronicle', ref: 'iid:1' },
  }
  return {
    site: w,
    progress: { progress: 0.4, phase: 'raising' },
    resolution: 'confirmed',
    crew: [0, 1, 2].map((i) => ({
      id: `${id}:w${i}`,
      x: 0,
      y: 0,
      action: 'hammer' as const,
      phase: i,
      frame: i,
      facing: 'down' as const,
    })),
    sign: { what: 'x', now: 'y', proof: 'z' },
  }
}

// ── how big a person is ─────────────────────────────────────────────────────

describe('a drawn person', () => {
  /**
   * PINNED TO THE SHIPPED ATLAS, NOT TO THE COMMENT. `PERSON_H_PX` is derived
   * from objects in the pack whose real height is not in dispute; if the pack
   * is ever re-scaled, the derivation moves and this arm is what says so. A
   * bare `expect(PERSON_H_PX).toBe(30)` would restate the constant and could
   * not fail for the reason that matters.
   */
  it('stands between the pack\'s own barrel and its law post', () => {
    const pack = JSON.parse(
      readFileSync(
        join(process.cwd(), 'public', 'world-assets', 'originals', 'iso', 'world-pack.json'),
        'utf8'
      )
    ) as { frames: Record<string, { dw: number; dh: number }> }
    const barrel = pack.frames.barrel_single.dh
    const post = pack.frames.law_post.dh
    expect(PERSON_H_PX).toBeGreaterThan(barrel)
    expect(PERSON_H_PX).toBeLessThan(post)
  })

  it('scales the 16x32 character cell to that height', () => {
    expect(PERSON_SCALE * CHAR_FRAME_H).toBeCloseTo(PERSON_H_PX, 6)
  })
})

// ── the commute road ────────────────────────────────────────────────────────

describe('the commute road', () => {
  it('is the harbour road the layout actually laid', () => {
    const L = hamlet()
    const road = commuteRoad(L)
    const main = L.lanes.find((l) => l.key === COMMUTE_LANE_KEY)!
    expect(road).not.toBeNull()
    expect(road!.length).toBe(main.runs.reduce((n, r) => n + r.length, 0))
    expect(road![0]).toEqual(main.runs[0][0])
  })

  /**
   * IT IS SELECTED BY KEY, NOT BY POSITION — and this arm exists because the
   * arm above could not tell the difference.
   *
   * MUTATION-MEASURED 2026-07-29: replacing the lookup with `layout.lanes[0]`
   * left the whole suite GREEN. `LANE_SPECS` happens to author `main` first, so
   * on every real layout the first lane IS the harbour road, and an arm driven
   * only against a composed layout can never separate the two. That is the
   * shipped-data-decides-the-verdict class: which term wins is a property of the
   * fixture, not of the code. So this one drives a lane list in the OTHER order,
   * where position and key disagree, and the position bug reds it.
   */
  it('picks the road by its KEY even when it is not the first lane', () => {
    const lane = (key: string, y: number) => ({
      key,
      kind: 'main' as const,
      width: 20,
      surface: 'dirt_path' as const,
      runs: [[{ x: 0, y }, { x: 0, y: y + 10 }]],
    })
    const road = commuteRoad({ lanes: [lane('coastal', 900), lane(COMMUTE_LANE_KEY, 100)] })
    expect(road![0].y).toBe(100)
  })

  /**
   * THE CLAIM IN THE MODULE'S OWN DOC COMMENT, measured rather than asserted:
   * concatenating runs means a walker on a multi-run road crosses the gap, and
   * the comment says no walker does that on the world as it ships. If a future
   * coastline change cuts the main lane in two, this reds and the comment stops
   * being true at the same moment.
   */
  it('is a SINGLE on-land run at every era on the shipped seed', () => {
    for (const era of ['camp', 'hamlet', 'town', 'beyond_bay'] as const) {
      const L = composeLayout({ ...HAMLET, era }, SEED)
      const main = L.lanes.find((l) => l.key === COMMUTE_LANE_KEY)
      expect(main, era).toBeTruthy()
      expect(main!.runs.length, era).toBe(1)
    }
  })

  it('is null when the layout laid no main lane', () => {
    expect(commuteRoad({ lanes: [] })).toBeNull()
    expect(
      commuteRoad({ lanes: [{ key: 'main', kind: 'main', width: 9, surface: 'dirt_path', runs: [[{ x: 0, y: 0 }]] }] })
    ).toBeNull()
  })
})

describe('isoFacing', () => {
  it('picks the dominant SCREEN axis', () => {
    expect(isoFacing(10, 1)).toBe('right')
    expect(isoFacing(-10, 1)).toBe('left')
    expect(isoFacing(1, 10)).toBe('down')
    expect(isoFacing(1, -10)).toBe('up')
  })
})

// ── walkers ─────────────────────────────────────────────────────────────────

describe('commute walkers', () => {
  const road = [
    { x: 0, y: 0 },
    { x: 0, y: 100 },
  ]

  it('walks progress 0→1 from the village to the quay', () => {
    expect(isoWalkers(road, [commuter('a', 'quay', 0)])[0].y).toBeCloseTo(0, 6)
    expect(isoWalkers(road, [commuter('a', 'quay', 1)])[0].y).toBeCloseTo(100, 6)
  })

  /**
   * AND BACK. `progress` is always 0..1 toward the destination, so the road
   * parameter INVERTS for the return leg — the reducer's contract, and the one
   * line whose loss would send everyone the same way forever while the world
   * still moved.
   */
  it('walks the road backwards on the way home', () => {
    expect(isoWalkers(road, [commuter('a', 'village', 0)])[0].y).toBeCloseTo(100, 6)
    expect(isoWalkers(road, [commuter('a', 'village', 1)])[0].y).toBeCloseTo(0, 6)
  })

  it('faces the way it is going, and glances aside when the reducer says so', () => {
    expect(isoWalkers(road, [commuter('a', 'quay', 0.5)])[0].facing).toBe('down')
    expect(isoWalkers(road, [commuter('a', 'village', 0.5)])[0].facing).toBe('up')
    expect(isoWalkers(road, [commuter('a', 'quay', 0.5, true)])[0].facing).toBe('left')
  })

  it('draws nobody when there is no road', () => {
    expect(isoWalkers(null, [commuter('a', 'quay', 0.5)])).toEqual([])
  })

  it('resolves to the real officer', () => {
    const w = isoWalkers(road, [commuter('cos', 'quay', 0.3)])[0]
    expect(w.slug).toBe('cos')
    expect(w.kind).toBe('walker')
  })
})

// ── the officers' yard ──────────────────────────────────────────────────────

describe('the officers\' yard', () => {
  const present = () => true

  it('is empty when there is no great house', () => {
    expect(isoOfficerYard({ structures: [] }, ['a', 'b'], present)).toEqual([])
  })

  /**
   * IT IS OUT THE FRONT, and "front" is the lot's own frontage rather than a
   * screen direction: the yard must be BETWEEN the house and the road it fronts,
   * which is the only definition that survives a house whose lot faces any other
   * way. Measured as: every officer is nearer the lot's road point than the
   * structure's base centre is.
   */
  it('stands between the great house and the road it fronts', () => {
    const L = hamlet()
    const gh = L.structures.find((s) => s.role === 'great_house')!
    expect(gh.lot).toBeTruthy()
    const road = gh.lot!.road
    const dHouse = Math.hypot(gh.at.x - road.x, gh.at.y - road.y)
    for (const o of isoOfficerYard(L, ['cos', 'cto', 'cpo', 'cro'], present)) {
      const dO = Math.hypot(o.x - road.x, o.y - road.y)
      expect(dO).toBeLessThan(dHouse)
    }
  })

  it('steps out by the setback, not by an accident of the fan', () => {
    const L = hamlet()
    const gh = L.structures.find((s) => s.role === 'great_house')!
    const face = gh.lot!.face
    for (const o of isoOfficerYard(L, ['cos'], present)) {
      // the component of (officer - house) along the OUTWARD normal
      const along = (o.x - gh.at.x) * -face.x + (o.y - gh.at.y) * -face.y
      expect(along).toBeGreaterThanOrEqual(YARD_SETBACK - 0.001)
    }
  })

  /**
   * THE YARD IS A YARD, not a huddle — and this arm is the one the browser
   * asked for. At the first spread the five officers of a real cabinet stood
   * inside 50 layout px, `layoutLabels` displaced all five DOM chips into a
   * column beside them, and every name on the frame was on nobody. A name chip
   * is ~26px of layout width at this scale, so the fan has to give each officer
   * at least that much elbow room before the label layer is asked to help.
   */
  it('spreads a full cabinet wide enough for its own name chips', () => {
    const L = hamlet()
    const slugs = ['cos', 'cto', 'cpo', 'cro', 'coo']
    const fan = isoOfficerYard(L, slugs, () => true)
    const xs = fan.map((o) => o.x).sort((a, b) => a - b)
    expect(xs[xs.length - 1] - xs[0]).toBeGreaterThan(26 * (slugs.length - 1))
  })

  it('gives every officer a different spot, stably', () => {
    const L = hamlet()
    const slugs = ['cos', 'cto', 'cpo', 'cro', 'coo']
    const a = isoOfficerYard(L, slugs, present)
    const b = isoOfficerYard(L, slugs, present)
    expect(a).toEqual(b)
    const spots = new Set(a.map((o) => `${o.x.toFixed(3)},${o.y.toFixed(3)}`))
    expect(spots.size).toBe(slugs.length)
  })

  /** The SAME seed the top-down yard uses, so an officer keeps their place. */
  it('places from fnv1a(officer:<slug>)', () => {
    const L = hamlet()
    const [a] = isoOfficerYard(L, ['cos'], present)
    const [b] = isoOfficerYard(L, ['cos'], present)
    expect(a.x).toBe(b.x)
    // a slug whose hash differs lands somewhere else
    expect(fnv1a('officer:cos')).not.toBe(fnv1a('officer:cto'))
    const [c] = isoOfficerYard(L, ['cto'], present)
    expect(c.x).not.toBe(a.x)
  })

  /**
   * AN OFFICER WHO WALKED TO THE QUAY IS AT THE QUAY.
   *
   * MEASURED IN A BROWSER 2026-07-29: `cto` walked the harbour road, arrived,
   * and reappeared at the great house — the frame animated the transition and
   * silently discarded its result, because every non-walking officer was placed
   * in the yard. `districts` is measured state from `commuteStep`; showing the
   * walk without the destination is half the truth.
   */
  it('stands an officer at the road\'s quay end when the reducer says quay', () => {
    const L = hamlet()
    const road = commuteRoad(L)!
    const end = road[road.length - 1]
    const home = isoOfficerYard(L, ['cos'], present)[0]
    const away = isoOfficerYard(L, ['cos'], present, { districts: { cos: 'quay' }, road })[0]
    expect(Math.hypot(away.x - end.x, away.y - end.y)).toBeLessThan(YARD_SPREAD + 40)
    expect(Math.hypot(home.x - end.x, home.y - end.y)).toBeGreaterThan(200)
  })

  it('keeps everyone at the house when there is no road to a quay', () => {
    const L = hamlet()
    const a = isoOfficerYard(L, ['cos'], present, { districts: { cos: 'quay' }, road: null })
    const b = isoOfficerYard(L, ['cos'], present)
    expect(a).toEqual(b)
  })

  it('carries presence through for the dim', () => {
    const L = hamlet()
    const [a] = isoOfficerYard(L, ['cos'], (s) => s !== 'cos')
    expect(a.present).toBe(false)
  })
})

// ── construction sites ──────────────────────────────────────────────────────

describe('SITE_LOT_GROUP', () => {
  /**
   * THE TABLE IS CHECKED AGAINST THE LAYOUT, NOT AGAINST ITSELF. `composeLayout`
   * builds the element→lot-group association inline and does not export it, so
   * the copy in iso-life could drift the day the compositor's own fold changes.
   * This arm composes a layout in which each element IS built and asserts the
   * structure landed on a lot of the group the table names — the sensor is wired
   * to the live artifact.
   */
  it('names the group each element is actually built on', () => {
    const L = hamlet()
    const byRole = new Map(L.structures.filter((s) => s.lot).map((s) => [s.role, s]))
    for (const [element, group] of SITE_LOT_GROUP) {
      const st = byRole.get(element) ?? byRole.get(element.replace(/s$/, ''))
      if (!st) continue // not built at this state — nothing to check
      const lots = L.lots[group] ?? []
      const hit = lots.some((l) => l.c.x === st.lot!.c.x && l.c.y === st.lot!.c.y)
      expect(hit, `${element} → ${group}`).toBe(true)
    }
  })

  it('covers every element the hamlet layout raises on a lot', () => {
    const L = hamlet()
    for (const st of L.structures) {
      if (!st.lot) continue
      const known =
        SITE_LOT_GROUP.has(st.role) || SITE_LOT_GROUP.has(`${st.role}s`)
      expect(known, `${st.role} has no SITE_LOT_GROUP entry`).toBe(true)
    }
  })
})

describe('a site pad', () => {
  /**
   * THE CASE A NAIVE STRUCTURE LOOKUP GETS WRONG. Four dwellings stand; a fifth
   * is going up. The works must be on FREE GROUND, not wrapped around dwelling
   * number one — which is what "find the structure for this element" returns,
   * silently, while the frame claims work on a house that has stood for months.
   */
  it('lands on a FREE lot when a count ladder is adding one', () => {
    const L = hamlet()
    const pad = isoSitePad(L, 'officer_dwellings')!
    expect(pad).toBeTruthy()
    const occupied = L.structures.filter((s) => s.lot).map((s) => s.lot!.c)
    for (const c of occupied) {
      expect(`${pad.c.x},${pad.c.y}`).not.toBe(`${c.x},${c.y}`)
    }
    const isAResidentialLot = L.lots.residential.some(
      (l) => l.c.x === pad.c.x && l.c.y === pad.c.y
    )
    expect(isAResidentialLot).toBe(true)
  })

  it('wraps the standing building when every lot in the group is taken', () => {
    const L = hamlet()
    const lib = L.structures.find((s) => s.role === 'library')!
    expect(L.lots.memory.length).toBe(1)
    const pad = isoSitePad(L, 'library')!
    expect(pad.c).toEqual(lib.at)
    expect(pad.rx).toBeGreaterThan(lib.size.w * 0.5)
  })

  it('is null for an element the layout knows no plot for', () => {
    expect(isoSitePad(hamlet(), 'lighthouse_lamp')).toBeNull()
  })

  /**
   * BOTH BRANCHES, and the second one is here because the first could not see
   * it. Mutation-measured 2026-07-29: swapping the free-lot branch's
   * `LANE_PAINT_SQUASH` for the projection kernel's 0.5 left the suite GREEN,
   * because this arm only ever drove `library` — the UPGRADE branch. An arm
   * that exercises one of two return paths is a sensor over half the function,
   * and the half it does not reach is exactly where a wrong constant hides.
   */
  it.each([
    ['upgrade (structure)', 'library'],
    ['new build (free lot)', 'officer_dwellings'],
  ])('flattens its ground ellipse by the LAYOUT\'s own aspect on the %s branch', (_n, el) => {
    const pad = isoSitePad(hamlet(), el)!
    expect(pad).toBeTruthy()
    expect(pad.ry / pad.rx).toBeCloseTo(LANE_SQUASH, 6)
  })
})

describe('isoSites', () => {
  it('keeps the reducer\'s crew size exactly', () => {
    const L = hamlet()
    const s = site('library')
    const { pads } = isoSites(L, [s])
    expect(pads[0].crew.length).toBe(s.crew.length)
    expect(pads[0].crew.map((w) => w.id)).toEqual(s.crew.map((w) => w.id))
    expect(pads[0].crew.map((w) => w.action)).toEqual(s.crew.map((w) => w.action))
    expect(pads[0].crew.map((w) => w.frame)).toEqual(s.crew.map((w) => w.frame))
  })

  it('carries the reducer\'s progress and phase untouched', () => {
    const { pads } = isoSites(hamlet(), [site('library')])
    expect(pads[0].progress).toBeCloseTo(0.4, 9)
    expect(pads[0].phase).toBe('raising')
  })

  it('puts the crew on the pad\'s own perimeter, facing the work', () => {
    const { pads } = isoSites(hamlet(), [site('library')])
    const p = pads[0]
    for (const w of p.crew) {
      const d = ((w.x - p.cx) / p.rx) ** 2 + ((w.y - p.cy) / p.ry) ** 2
      expect(d).toBeCloseTo(1, 5)
    }
    // facing is inward: the wright on the left of the pad faces right
    const left = p.crew.reduce((a, b) => (a.x < b.x ? a : b))
    expect(['right', 'up', 'down']).toContain(left.facing)
  })

  it('reports a site it cannot place instead of putting it somewhere', () => {
    const { pads, unplaced } = isoSites(hamlet(), [site('lighthouse_lamp')])
    expect(pads).toEqual([])
    expect(unplaced).toEqual(['lighthouse_lamp'])
  })
})

describe('crewSlot', () => {
  it('spreads n wrights evenly and never stacks two', () => {
    const seen = new Set<string>()
    for (let i = 0; i < 4; i++) {
      const p = crewSlot({ x: 0, y: 0 }, 100, 72, 4, i, 'sX')
      seen.add(`${p.x.toFixed(4)},${p.y.toFixed(4)}`)
    }
    expect(seen.size).toBe(4)
  })

  it('rotates per site, so two same-size sites do not draw twins', () => {
    const a = crewSlot({ x: 0, y: 0 }, 100, 72, 3, 0, 'siteA')
    const b = crewSlot({ x: 0, y: 0 }, 100, 72, 3, 0, 'siteB')
    expect(`${a.x},${a.y}`).not.toBe(`${b.x},${b.y}`)
  })
})

// ── the pending rung ────────────────────────────────────────────────────────

describe('pending marks', () => {
  it('stands on the sprite the scene drew for that element', () => {
    const L = hamlet()
    const sprites = [{ role: 'library', x: 111, y: 222 }]
    const { marks, unplaced } = pendingMarks(L, sprites, ['library'])
    expect(unplaced).toEqual([])
    expect(marks[0]).toMatchObject({ element: 'library', x: 111, y: 222 })
  })

  /** The layout spells one role as the singular of the ladder that entitles it. */
  it('matches the layout\'s singular spelling of a count ladder', () => {
    const L = hamlet()
    const sprites = [{ role: 'officer_dwelling', x: 5, y: 6 }]
    const { marks } = pendingMarks(L, sprites, ['officer_dwellings'])
    expect(marks[0]).toMatchObject({ x: 5, y: 6 })
  })

  it('falls back to the plot when the scene draws nothing for it', () => {
    const L = composeLayout(CAMP, SEED)
    const { marks, unplaced } = pendingMarks(L, [], ['library'])
    // camp draws no library; the memory lot is free, so the plot is knowable
    expect(unplaced).toEqual([])
    expect(marks[0].x).toBe(L.lots.memory[0].c.x)
  })

  it('reports an element with neither a sprite nor a plot', () => {
    const { marks, unplaced } = pendingMarks(hamlet(), [], ['lighthouse_lamp'])
    expect(marks).toEqual([])
    expect(unplaced).toEqual(['lighthouse_lamp'])
  })

  it('never marks an element that is not pending', () => {
    const { marks } = pendingMarks(hamlet(), [{ role: 'library', x: 1, y: 2 }], [])
    expect(marks).toEqual([])
  })
})

// ── apprentices ─────────────────────────────────────────────────────────────

describe('apprentices', () => {
  const officers: IsoFigure[] = [
    { id: 'officer:cos', slug: 'cos', kind: 'officer', x: 500, y: 400, facing: 'down', anim: 'work', present: true, scale: 1 },
  ]
  const fig = (id: string, officer: string) => ({
    id,
    officer,
    x: 0,
    y: 0,
    spawnIid: 1,
    frame: 0,
  })

  it('clusters on the officer the iso frame actually drew', () => {
    const [a] = isoApprentices(officers, [fig('a1', 'cos')])
    expect(Math.hypot(a.x - 500, a.y - 400)).toBeLessThan(40)
    expect(a.slug).toBe('cos')
  })

  /** A figure may never float free of its real actor — the reducer's own law. */
  it('is dropped when its officer is not on the frame', () => {
    expect(isoApprentices(officers, [fig('a1', 'nobody')])).toEqual([])
  })

  it('stands smaller than a full officer', () => {
    const [a] = isoApprentices(officers, [fig('a1', 'cos')])
    expect(a.scale).toBeLessThan(1)
  })
})

// ── the pick ────────────────────────────────────────────────────────────────

const figure = (id: string, x: number, y: number, scale = 1): IsoFigure => ({
  id,
  slug: id,
  kind: 'officer',
  x,
  y,
  facing: 'down',
  anim: 'work',
  present: true,
  scale,
})

describe('pickIsoFigure', () => {
  it('hits a figure on its own body', () => {
    const f = figure('cos', 100, 200)
    expect(pickIsoFigure([f], 100, 200 - PERSON_H_PX / 2)?.slug).toBe('cos')
  })

  it('misses the ground beside and below it', () => {
    const f = figure('cos', 100, 200)
    expect(pickIsoFigure([f], 300, 200)).toBeNull()
    expect(pickIsoFigure([f], 100, 260)).toBeNull()
  })

  /**
   * FRONT TO BACK. The caller hands the array in DRAW order (depth-sorted), so
   * the figure painted last is the one in front, and a pointer over two
   * overlapping people must name the one the eye sees.
   */
  it('names the figure drawn on top when two overlap', () => {
    const back = figure('back', 100, 200)
    const front = figure('front', 100, 202)
    expect(pickIsoFigure([back, front], 100, 195)?.slug).toBe('front')
  })

  it('scales its box with the figure', () => {
    const small = figureBox(figure('a', 0, 0, 0.5))
    const big = figureBox(figure('a', 0, 0, 1))
    expect(small.h).toBeLessThan(big.h)
  })

  it('answers nothing for an empty world', () => {
    expect(pickIsoFigure([], 0, 0)).toBeNull()
  })
})

describe('pickIsoSite', () => {
  const pad = (id: string, cx: number, cy: number, rx = 50) => ({
    id,
    element: 'e',
    cx,
    cy,
    rx,
    ry: rx * LANE_SQUASH,
    progress: 0,
    phase: 'raising' as const,
    crew: [],
  })

  it('hits inside the ground ellipse and misses outside it', () => {
    expect(pickIsoSite([pad('s1', 0, 0)], 10, 0)?.id).toBe('s1')
    expect(pickIsoSite([pad('s1', 0, 0)], 80, 0)).toBeNull()
    // the ellipse is FLATTENED: a point above it that a circle would catch is
    // outside the pad
    expect(pickIsoSite([pad('s1', 0, 0)], 0, 45)).toBeNull()
  })

  it('takes the NEAREST pad when two overlap', () => {
    const a = pad('a', 0, 0)
    const b = pad('b', 20, 0)
    expect(pickIsoSite([a, b], 19, 0)?.id).toBe('b')
    expect(pickIsoSite([a, b], 1, 0)?.id).toBe('a')
  })
})

describe('padDither', () => {
  it('is deterministic and stays inside the unit disc', () => {
    const a = padDither('x')
    expect(padDither('x')).toEqual(a)
    for (const d of a) expect(d.x * d.x + d.y * d.y).toBeLessThanOrEqual(1.0001)
  })

  it('differs per pad', () => {
    expect(padDither('a')).not.toEqual(padDither('b'))
  })

  /**
   * THE PAD ACTUALLY COVERS GROUND — the arm the first two could not replace.
   *
   * MEASURED IN A BROWSER 2026-07-29: the shipped density put 1694 dirt pixels
   * inside a 110x79 pad (6.2%) and the frame showed a library standing on
   * untouched grass with a fence round it. A determinism arm and a
   * stays-in-the-disc arm are both GREEN on a pad that draws nothing, which is
   * the shape of a test that cannot see the defect it is nearest to. So the
   * coverage itself is pinned, at the real pad size, with a floor a halving
   * would break.
   */
  it('covers a third of the real library pad', () => {
    const pad = isoSitePad(hamlet(), 'library')!
    const area = Math.PI * pad.rx * pad.ry
    const ink = padDither('site', pad.rx, pad.ry).reduce((n, d) => n + d.r * d.r, 0)
    expect(ink / area).toBeGreaterThan(0.3)
    expect(ink / area).toBeLessThan(0.75) // not a solid slab either
  })

  it('scales its count with the pad, so a small pad is not a mud pit', () => {
    const small = padDither('s', 30, 22)
    const big = padDither('s', 120, 86)
    expect(big.length).toBeGreaterThan(small.length * 3)
  })
})

describe('hoardingPanels', () => {
  /**
   * A FENCE, NOT A ROW OF STICKS. Eight panels round a 110px pad leaves gaps
   * wider than the panels — measured on the first capture, where the library's
   * hoarding read as scattered debris. The count follows the PERIMETER.
   */
  it('scales with the perimeter', () => {
    expect(hoardingPanels(30, 22)).toBeLessThan(hoardingPanels(120, 86))
  })

  it('never leaves a gap wider than a panel', () => {
    for (const [rx, ry] of [[30, 22], [60, 43], [110, 79], [180, 130]] as const) {
      const n = hoardingPanels(rx, ry)
      const perim = Math.PI * (3 * (rx + ry) - Math.sqrt((3 * rx + ry) * (rx + 3 * ry)))
      expect(perim / n, `${rx}x${ry}`).toBeLessThanOrEqual(29)
    }
  })
})
