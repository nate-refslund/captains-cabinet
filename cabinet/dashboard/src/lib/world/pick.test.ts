/**
 * PICK — the file the hit test never had.
 *
 * The whole clickability of the world was a closure inside a PixiJS effect with
 * ZERO tests, in either kernel. Under iso a click on a tall building returned
 * empty ground, silently, and the full suite stayed green while every inspect
 * card, deep link, the mailbox, the chart table and the Library entrance became
 * unreachable. So the arms below are organised around the one question that
 * failure asks: FOR EACH INTERACTIVE KIND, IN EACH PROJECTION, CAN IT BE
 * REACHED — and when it cannot, is that because the world does not draw it?
 *
 * Every arm here was proven to FAIL by disabling the rule it guards; the
 * mutations and their results are recorded in the commit that landed this file.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import { buildIsoScene, elementForRole, type IsoScene } from './iso-scene'
import { interiorSlots, openFrameOf } from './iso-cutaway'
import { parsePack, type IsoPack } from './iso-pack'
import { officerSlots, pickTarget, STATIONS, type PickKind, type PickWorld } from './pick'
import { LOD_RULES, lodTier } from './lod'
import { projectionFor, worldToScreen } from './projection'
import { buildWorldGeo, CHART_TABLE_LOCAL, roadPoint, toWorld } from './world-geo'
import { buildWorldBuildings } from './world-buildings'
import { fnv1a } from './hash'
import type { LayoutState } from './iso-layout'
import type { ElementResolution, WorldResolution } from './era-engine'
import type { LifeOut } from './life/life'

const PACK: IsoPack = parsePack(
  JSON.parse(
    fs.readFileSync(
      path.resolve(__dirname, '..', '..', '..', 'public', 'world-assets', 'originals', 'iso', 'world-pack.json'),
      'utf8'
    )
  )
)

// ── the world, built from the REAL builders (never a hand-shaped stub) ──────

const GEO = buildWorldGeo({
  orgEventsTotal: 900,
  lanes: {},
  berths: ['polads', 'stephie', null, null, null],
  probeWiredLanes: [],
})

function el(rung: number, rungName: string): ElementResolution {
  return { rung, rungName, vocab: null, pending: null, measured: true, value: null }
}

/** A cabinet with every anchor built, so every building row exists to pick. */
const RESOLUTION: WorldResolution = {
  era: 'hamlet',
  eraIndex: 0.42,
  eraUnmeasured: [],
  transition: null as unknown as WorldResolution['transition'],
  lanes: {},
  elements: {
    great_house: el(2, 'great_house'),
    library: el(2, 'library_hall'),
    workshop: el(2, 'shed'),
    well: el(1, 'well'),
    firepit: el(1, 'stone_ring'),
    law_plot: el(1, 'posted'),
    observatory: el(1, 'hut'),
    outbuildings: el(1, 'small_barn'),
    pens: el(1, 'pen'),
    water_store: el(1, 'store'),
    journal_desk: el(1, 'desk'),
    warehouse: el(2, 'warehouse'),
    harbormaster_hut: el(1, 'hut'),
    lighthouse: el(3, 'tower_full'),
    officer_dwellings: el(3, 'dwellings_3'),
  },
}
const BUILDINGS = buildWorldBuildings(RESOLUTION, GEO)
const GH = BUILDINGS.find((b) => b.element === 'great_house')!
const LIB = BUILDINGS.find((b) => b.id === 'library')!
const OFFICERS = { cos: {}, cpo: {}, cto: {} }
const SLOTS = officerSlots(GH, Object.keys(OFFICERS).sort(), false)

const SITE_FOOTPRINT = { x: GH.x + 10, y: GH.y + 10, w: 4, h: 3 }
const LIFE = {
  commuters: [{ slug: 'cos', walk: { to: 'quay' }, progress: 0.5, glance: false }],
  sites: [{ site: { id: 'site:library:library_hall', footprint: SITE_FOOTPRINT } }],
  districts: {},
  fauna: [],
  apprentices: { figures: [], overflow: {} },
  states: {},
  problems: [],
} as unknown as LifeOut

/** The iso scene the renderer would draw for the same cabinet. */
const ISO_STATE: LayoutState = {
  era: 'hamlet',
  road: 'gravel_road',
  stages: {
    great_house: 'great_house',
    officer_dwellings: 'dwellings_4',
    library: 'library_hall',
    workshop: 'shed',
    outbuildings: 'small_barn',
    well: 'well',
    firepit: 'stone_ring',
    lighthouse: 'tower_full',
    lighthouse_lamp: 'lit',
    quay: 'timber_jetty',
    warehouse: 'warehouse',
    harbormaster_hut: 'hut',
    harbor_boat: 'packet_boat',
    cargo_stacks: 'crates_mid',
    berths: 'berths_2',
    field_plots: 'plots_2',
    road: 'gravel_road',
  },
  counts: { officer_dwellings: 4, field_plots: 2, berths: 2, cargo_stacks: 2, warehouse: 2 },
}
const SCENE: IsoScene = buildIsoScene(PACK, ISO_STATE, 'cabinet-pick')

const VIEWPORT = { w: 1440, h: 900 }

function world(over: Partial<PickWorld> = {}): PickWorld {
  return {
    projection: 'topdown',
    camera: { z: 3, x: GH.x, y: GH.y },
    viewport: VIEWPORT,
    geo: GEO,
    buildings: BUILDINGS,
    officers: OFFICERS,
    life: LIFE,
    chartTable: true,
    cutawayOpenId: null,
    scene: SCENE,
    ...over,
  }
}

/**
 * Pick at a WORLD-TILE point, by projecting it to a screen point first.
 *
 * Deliberately NOT by calling the inner geometry: this drives the real
 * screen->world inverse the canvas uses, so a kernel that placed a sprite one
 * way and inverted the pointer another would fail here rather than in nobody's
 * test. Under iso the camera is centred on the target so the point is on
 * screen — the pick has no viewport cull, but pinning the round trip at the
 * viewport centre is what makes these coordinates readable.
 */
function pickAtTile(w: PickWorld, wx: number, wy: number) {
  const s = worldToScreen(projectionFor(w.projection), wx, wy, w.camera, w.viewport)
  return pickTarget(w, s)
}

/** A layout-PIXEL point (iso sprite space) as a world tile. */
function tileOfLayoutPx(x: number, y: number) {
  const t = projectionFor('iso').unproject(x, y)
  return { wx: t.tx, wy: t.ty }
}

/** The pick solid, restated here so the test does not import what it tests. */
function solidHolds(s: { x: number; y: number; dw: number; dh: number }, px: number, py: number) {
  const hw = s.dw * 0.42
  const depth = Math.max(6, Math.min(s.dh * 0.55, s.dw * 0.55))
  if (hw <= 0 || depth <= 0) return false
  const u = Math.abs(px - s.x) / hw
  if (u > 1) return false
  const e = (depth / 2) * (1 - u)
  const cy = s.y - depth / 2
  return py <= cy + e && py >= cy - e - Math.max(0, s.dh - depth)
}

/** The card a scene sprite opens, derived the way the module derives it. */
function targetOf(s: { frame: string; role: string | null }) {
  const station = STATIONS.get(s.frame)
  if (station) return station
  const b = BUILDINGS.find((bb) => bb.element === elementForRole(s.role))
  return b ? { kind: 'building', id: b.id } : { kind: 'ground', id: 'ground' }
}

const isoWorld = (over: Partial<PickWorld> = {}) =>
  world({ projection: 'iso', camera: { z: 3, x: 0, y: 0 }, ...over })

/** Pick on an iso sprite, `up` of the way up its drawn body (0 = its base). */
function pickOnSprite(w: PickWorld, frame: string, up: number) {
  const s = SCENE.sprites.find((sp) => sp.frame === frame)
  expect(s, `scene has a ${frame}`).toBeDefined()
  const { wx, wy } = tileOfLayoutPx(s!.x, s!.y - Math.max(1, s!.dh * up))
  const cam = { z: 3, x: wx, y: wy }
  return pickTarget({ ...w, camera: cam }, { x: VIEWPORT.w / 2, y: VIEWPORT.h / 2 })
}

// ── 1. THE ENUMERATION: every interactive kind, in both projections ─────────

describe('every interactive kind is reachable, or is honestly not drawn', () => {
  // The list is EXHAUSTIVE by construction: `PickKind` has seven members and
  // the arm below asserts this table covers every one of them. An enumeration
  // is the only defence against "the one nobody tried", and a hand-written
  // list that silently falls behind the type is not an enumeration.
  const TOPDOWN: Array<[string, PickKind, string, () => { wx: number; wy: number }]> = [
    ['officer (great-house yard)', 'officer', 'cos', () => ({ wx: SLOTS[0].x, wy: SLOTS[0].y - 0.3 })],
    ['officer (commute walker)', 'officer', 'cos', () => {
      const p = roadPoint(0.5)
      return { wx: p.x + 0.5, wy: p.y + 0.5 }
    }],
    ['construction site', 'site', 'site:library:library_hall', () => ({
      wx: SITE_FOOTPRINT.x + 1,
      wy: SITE_FOOTPRINT.y + 1,
    })],
    ['mailbox', 'mailbox', 'mailbox', () => ({
      wx: GEO.crossroads.x + 1.2,
      wy: GEO.crossroads.y,
    })],
    ['chart table', 'chart_table', 'chart-table', () => {
      const c = toWorld(CHART_TABLE_LOCAL.x, CHART_TABLE_LOCAL.y)
      return { wx: c.x + 0.5, wy: c.y + 0.5 }
    }],
    ['building', 'building', 'great_house', () => ({
      wx: GH.x + GH.w / 2,
      wy: GH.y + GH.h / 2,
    })],
    ['Library entrance', 'building', 'library', () => ({
      wx: LIB.x + LIB.w / 2,
      wy: LIB.y + LIB.h / 2,
    })],
    ['lane isle / buoy', 'lane', 'lane:1', () => {
      const s = GEO.laneSites[0]
      return { wx: s.cx, wy: s.cy }
    }],
    ['empty ground', 'ground', 'ground', () => ({ wx: 2, wy: 2 })],
  ]

  it.each(TOPDOWN)('top-down: %s -> %s', (_label, kind, id, at) => {
    const { wx, wy } = at()
    // lane sites live far out; pick them at the tier that renders them
    const z = kind === 'lane' ? 0.3 : 3
    const got = pickAtTile(world({ camera: { z, x: wx, y: wy } }), wx, wy)
    expect(got).toEqual({ kind, id })
  })

  it('the top-down table covers every PickKind — no member goes untested', () => {
    const ALL: PickKind[] = [
      'officer',
      'building',
      'lane',
      'mailbox',
      'chart_table',
      'site',
      'ground',
    ]
    // ALL is pinned against the module's own union by the type annotation
    // above: adding a member to PickKind without adding it here is a compile
    // error at the it.each rows, not a silent hole.
    const covered = new Set(TOPDOWN.map(([, k]) => k))
    expect([...ALL].filter((k) => !covered.has(k))).toEqual([])
  })

  // ISO. The world under iso is composeLayout's island, not the tile lattice,
  // so the reachable set is genuinely different — and the difference has to be
  // ASSERTED rather than skipped, because "we did not test it" and "the world
  // does not draw it" look identical from a green board.
  it.each([
    ['great_house', 'great_house'],
    ['library', 'library'],
    ['lighthouse', 'lighthouse'],
    ['workshop', 'workshop'],
    ['warehouse', 'warehouse'],
  ])('iso: a click anywhere up the body of %s opens its card', (frame, id) => {
    for (const up of [0.02, 0.35, 0.65, 0.9]) {
      expect(pickOnSprite(isoWorld(), frame, up), `${frame} at ${up} of its height`).toEqual({
        kind: 'building',
        id,
      })
    }
  })

  it.each([
    ['mailbox', { kind: 'mailbox', id: 'mailbox' }],
    ['chart_table', { kind: 'chart_table', id: 'chart-table' }],
  ])('iso: the %s station answers, though no ladder entitles it', (frame, target) => {
    // THE DEFECT: both are `village_life` dressing, so `role` is null and the
    // pick skipped them with the trees. Measured unreachable on a composed
    // hamlet scene 2026-07-28, with `s.frame === 'mailbox'` sitting in
    // engine-canvas.tsx as dead code and the suite green over it.
    const s = SCENE.sprites.find((sp) => sp.frame === frame)!
    expect(s.role, `${frame} really is role-less — that is the trap`).toBeNull()
    for (const up of [0.02, 0.5, 0.9]) {
      expect(pickOnSprite(isoWorld(), frame, up)).toEqual(target)
    }
  })

  it('iso: the STATIC scene draws no walker, site or lane isle, so nothing answers', () => {
    // Not a gap in the pick — a gap in the world. The five-slot isle fan is
    // top-down `world-geo` geometry with no iso counterpart, and the pick must
    // not invent one from top-down coordinates: that would be a card asserting
    // something false about the org.
    // stated as the BEHAVIOUR, not as a name heuristic: an earlier version of
    // this arm looked for the substring 'officer' in frame names and fired on
    // `officer_house_a`, which is a HOUSE. A living thing is a thing the pick
    // can answer `officer`/`site`/`lane` for, so that is what is measured.
    //
    // SCOPED TO THE STATIC SCENE ON PURPOSE. This arm shipped saying "the pack
    // ships no character sprites, drawIsoDynamics draws only the lamp", and the
    // very next commit made that false: `drawIsoCutaway` draws one owned
    // officer per slug inside any open room (engine-canvas.tsx ~1887). The
    // sweep could not see it, because a scene with no cutaway open has no
    // officer in it — so the justification was rewritten to what is measured
    // here, and the surface it stopped covering is pinned by the arm below.
    //
    // THE SWEEP CARRIES THE NEGATIVE CLAIM ONLY, and that split is the fix for
    // a sensor that was measuring sprite AREA rather than reachability. The
    // positive half used to ride on the same 2500 random tiles, so a chart
    // table drawn 96x105 was hit by luck and the same table drawn 32x35 — the
    // 2026-07-28 scale contract, which holds every prop to the person beside
    // it — was not, and the arm went red for a world where nothing had become
    // unreachable. Expected hits for a 32x35 sprite in a 2400x1760 scene are
    // under one; raising the sample count until it passes again would restore
    // the green and keep the defect. So the two small interactive sprites are
    // now probed WHERE THEY STAND, which is the claim that matters: a prop the
    // contract shrank must still answer when a pointer is actually on it.
    //
    // KNOWN COST, stated so a future red is readable: the sweep's expectation
    // below now encodes "chart_table and mailbox are too small for 2500 random
    // samples to hit". Enlarge either prop and this line goes red with a
    // message about walkers and lane isles — which is NOT what broke. Verified
    // by mutation (2026-07-28 review): restoring chart_table or mailbox to /1
    // reds this line and nothing else. If a class change makes it red, move the
    // frame out of the expectation; do not raise the sample count.
    const seen = new Set<PickKind>()
    for (let i = 0; i < 2500; i++) {
      const h = fnv1a(`iso-living:${i}`)
      const { wx, wy } = tileOfLayoutPx((h >>> 3) % SCENE.space.w, (h >>> 15) % SCENE.space.h)
      seen.add(pickAtTile(isoWorld({ camera: { z: 3, x: wx, y: wy } }), wx, wy).kind)
    }
    expect([...seen].sort()).toEqual(['building', 'ground'])
    for (const frame of ['chart_table', 'mailbox'] as const) {
      const hit = pickOnSprite(isoWorld(), frame, 0.3)
      expect(hit.kind, `${frame} answers when the pointer is on it`).toBe(frame)
      seen.add(hit.kind)
    }
    expect([...seen].sort()).toEqual(['building', 'chart_table', 'ground', 'mailbox'])
    for (const gone of ['officer', 'site', 'lane'] as PickKind[]) {
      expect(seen.has(gone), `iso answers ${gone} for something it never drew`).toBe(false)
    }
  })

  /**
   * A DECLARED GAP, so it is visible from the board instead of from a report.
   *
   * Under iso the cutaway DOES draw officers: `drawIsoCutaway` places one
   * character sprite per slug on `interiorSlots` inside the open room. The iso
   * pick has no officer branch at all — it answers stations, then a building
   * row, then ground — so a click on a drawn officer opens the BUILDING's card.
   * That is wrong but not dishonest: the card names a thing that is really
   * there. Inventing an officer from top-down yard coordinates would be worse.
   *
   * Pinned rather than left implicit BECAUSE IT GOES RED WHEN IT IS FIXED. The
   * two commits that produced this state each held one half of it and the suite
   * was green over the pair; an arm that says out loud what is not reachable is
   * the only thing that survives the next hand-off.
   */
  it('iso: an officer inside an OPEN room is not pickable yet — declared, not discovered', () => {
    const gh = SCENE.sprites.find((s) => s.role === 'great_house')!
    const open = openFrameOf(PACK, gh.frame)
    expect(open, 'the great house really does have roof-off art to open').not.toBeNull()
    const slots = interiorSlots(open!, gh.x, gh.y, 3)
    expect(slots.length, 'the room really does place desks the officers stand at').toBe(3)
    for (const slot of slots) {
      // the officer is drawn at slot.y + 7 (engine-canvas.tsx), inside the room
      const { wx, wy } = tileOfLayoutPx(slot.x, slot.y + 7)
      const got = pickAtTile(isoWorld({ camera: { z: 3, x: wx, y: wy } }), wx, wy)
      expect(got.kind, 'when this becomes `officer`, delete this arm').toBe('building')
      expect(got.id).toBe('great_house')
    }
  })

  /**
   * THE ENUMERATION IS DERIVED, not listed. The five-frame table above proves
   * the five frames somebody thought of; it cannot notice a SIXTH role whose
   * card stops opening, which is exactly what had happened — every officer
   * dwelling on a hamlet island answered `ground` while that table stayed
   * green, because the pick compared the layout's `officer_dwelling` to the
   * ladder's `officer_dwellings` with `===`.
   *
   * So the subject is the composed scene: every card-bearing role it really
   * draws must either open its own building card, or be named here as a role
   * the top-down building table has no row for. A new role joins the second
   * list only by someone writing it down.
   */
  it('iso: EVERY card-bearing role a hamlet island draws opens its own card', () => {
    // Measured, real, and deliberately card-less: the harbour's own kit is
    // entitled by ladders but `world-buildings.ts` has no row for any of it,
    // so `ground` is the honest answer rather than a neighbour's card.
    const NO_BUILDING_ROW = ['berths', 'cargo_stacks', 'harbor_boat']
    const roles = [...new Set(SCENE.sprites.map((s) => s.role).filter((r): r is string => r !== null))]
    expect(roles.length, 'the hamlet scene drew no measured structure at all').toBeGreaterThan(8)
    const unreachable: string[] = []
    for (const role of roles.sort()) {
      const b = BUILDINGS.find((bb) => bb.element === elementForRole(role))
      const s = SCENE.sprites.find((sp) => sp.role === role)!
      const got = pickOnSprite(isoWorld(), s.frame, 0.3)
      if (b) {
        if (got.kind !== 'building') unreachable.push(`${role} -> ${got.kind}`)
      } else if (!NO_BUILDING_ROW.includes(role)) {
        unreachable.push(`${role} has no building row and is not declared card-less`)
      }
    }
    expect(unreachable, 'drawn, measured, and answers nothing').toEqual([])
    // and the declaration is verified rather than trusted: a name that stops
    // being drawn, or grows a row, must not sit here unnoticed
    for (const role of NO_BUILDING_ROW) {
      expect(roles, `${role} is declared card-less but is not drawn`).toContain(role)
      expect(
        BUILDINGS.find((bb) => bb.element === elementForRole(role)),
        `${role} now HAS a building row — it is no longer card-less`
      ).toBeUndefined()
    }
  })

  it('iso: an officer dwelling opens its dwelling card, at every height', () => {
    // The role the LAYOUT spells is singular; the ladder that entitles it is
    // plural. `pick` resolves through iso-scene's one alias table.
    const dwellings = SCENE.sprites.filter((s) => s.role === 'officer_dwelling')
    expect(dwellings.length, 'a hamlet island really does draw dwellings').toBeGreaterThan(2)
    expect(
      BUILDINGS.some((b) => b.element === 'officer_dwellings'),
      'the ladder spells it plural — that is the trap'
    ).toBe(true)
    for (const up of [0.02, 0.4, 0.85]) {
      const got = pickOnSprite(isoWorld(), dwellings[0].frame, up)
      expect(got.kind, `dwelling at ${up} of its height`).toBe('building')
      expect(got.id).toMatch(/^dwelling:/)
    }
  })

  it('iso: open sea answers ground — no phantom target off the island', () => {
    const { wx, wy } = tileOfLayoutPx(40, 40)
    expect(pickAtTile(isoWorld({ camera: { z: 3, x: wx, y: wy } }), wx, wy)).toEqual({
      kind: 'ground',
      id: 'ground',
    })
  })
})

// ── 2. THE GEOMETRY THIS ROUND FIXED ───────────────────────────────────────

describe('the iso pick reaches the body, not just the footprint', () => {
  it('a click high on a tall building no longer returns empty ground', () => {
    // The shipped pick tested the ground DIAMOND, whose depth is at most
    // 0.55*dh — so everything above that answered `ground`. This is that exact
    // failure, expressed as the pixel it happened at.
    const lh = SCENE.sprites.find((s) => s.role === 'lighthouse')!
    const g = { hw: lh.dw * 0.42, depth: Math.max(6, Math.min(lh.dh * 0.55, lh.dw * 0.55)) }
    const highAbove = lh.y - g.depth - 1 // one px above the old solid's roof
    expect(lh.dh).toBeGreaterThan(g.depth) // the sprite really is taller
    const { wx, wy } = tileOfLayoutPx(lh.x, highAbove)
    expect(pickAtTile(isoWorld({ camera: { z: 3, x: wx, y: wy } }), wx, wy)).toEqual({
      kind: 'building',
      id: 'lighthouse',
    })
  })

  it('the solid stays the diamond WIDE — a tall sprite does not swallow its neighbours', () => {
    const lh = SCENE.sprites.find((s) => s.role === 'lighthouse')!
    const hw = lh.dw * 0.42
    // just outside the footprint's half width, high up the art
    const { wx, wy } = tileOfLayoutPx(lh.x + hw + 2, lh.y - lh.dh * 0.8)
    const got = pickAtTile(isoWorld({ camera: { z: 3, x: wx, y: wy } }), wx, wy)
    expect(got.id).not.toBe('lighthouse')
  })

  it('front to back: where two CARDS overlap, the nearer one answers', () => {
    // MEASURED FIRST, and it is why this arm is constructed rather than taken
    // from the hamlet scene: that scene has exactly 3 contested points and all
    // 3 are `berths < harbor_boat`, neither of which has a building row — so
    // both sides map to `ground` and the arm could not tell the orders apart.
    // A mutation that walked the sprites BACK to front came back GREEN through
    // it (M9, 2026-07-28). Real card-on-card occlusion is rare precisely
    // because the clearance rules space structures apart, so the ordering rule
    // is a LATENT property of the shipped island and has to be driven directly.
    const back = SCENE.sprites.find((sp) => sp.role === 'library')!
    const near = {
      ...SCENE.sprites.find((sp) => sp.role === 'workshop')!,
      id: 'near',
      // stand it just in front of the library, overlapping its solid
      x: back.x,
      y: back.y + 8,
      depth: back.depth + 8,
    }
    const stacked = { sprites: [back, near] } // back-to-front, as the scene is
    const px = back.x
    const py = back.y - back.dh * 0.5
    expect(solidHolds(back, px, py) && solidHolds(near, px, py), 'they really overlap').toBe(true)
    const { wx, wy } = tileOfLayoutPx(px, py)
    expect(
      pickAtTile(isoWorld({ scene: stacked, camera: { z: 3, x: wx, y: wy } }), wx, wy)
    ).toEqual({ kind: 'building', id: 'workshop' })
    // …and with the two swapped, the answer swaps with them
    const swapped = { sprites: [{ ...near, depth: back.depth - 8 }, back] }
    expect(
      pickAtTile(isoWorld({ scene: swapped, camera: { z: 3, x: wx, y: wy } }), wx, wy)
    ).toEqual({ kind: 'building', id: 'library' })
  })

  it('on the shipped island the pick never answers with a sprite behind the front one', () => {
    // The scene is depth-sorted back to front and the renderer paints it in
    // that order, so the pick walking it backwards IS the paint order
    // reversed. Where two card-bearing solids overlap, the nearer one (higher
    // depth) must win.
    const cards = SCENE.sprites.filter((s) => s.role !== null || STATIONS.has(s.frame))
    expect(cards.length).toBeGreaterThan(10)
    let contested = 0
    for (const s of cards) {
      // walk up the body so overlaps are found where tall art really overlaps
      for (const up of [0.05, 0.4, 0.8]) {
        const px = s.x
        const py = s.y - Math.max(1, s.dh * up)
        const holding = cards.filter((c) => solidHolds(c, px, py))
        if (holding.length < 2) continue
        contested++
        // the scene is back-to-front, so the LAST holder is the one painted on
        // top — that is the sprite the eye sees and the one the pick must name
        const front = holding[holding.length - 1]
        const { wx, wy } = tileOfLayoutPx(px, py)
        const got = pickAtTile(isoWorld({ camera: { z: 3, x: wx, y: wy } }), wx, wy)
        expect(got, `${holding.map((c) => c.frame).join(' < ')} at ${up}`).toEqual(
          targetOf(front)
        )
      }
    }
    expect(contested, 'the arm found real overlaps to decide').toBeGreaterThan(0)
  })
})

// ── 3. PRIORITY ORDER AND THE LOD GATE (product law, top-down) ─────────────

describe('the priority order and the LOD gate are law', () => {
  it('an officer standing on a building answers officer', () => {
    // the yard slot is inside the great house bbox padding, which is exactly
    // the overlap the order exists to settle
    const o = SLOTS[0]
    const w = world({ camera: { z: 3, x: o.x, y: o.y } })
    expect(pickAtTile(w, o.x, o.y - 0.3).kind).toBe('officer')
  })

  it('a LIFE site inside a lot answers site, not the building', () => {
    const b = BUILDINGS.find(
      (x) =>
        SITE_FOOTPRINT.x >= x.x - 1 &&
        SITE_FOOTPRINT.x <= x.x + x.w + 1 &&
        SITE_FOOTPRINT.y >= x.y - 1 &&
        SITE_FOOTPRINT.y <= x.y + x.h + 1
    )
    const wx = SITE_FOOTPRINT.x + 1
    const wy = SITE_FOOTPRINT.y + 1
    const got = pickAtTile(world({ camera: { z: 3, x: wx, y: wy } }), wx, wy)
    expect(got.kind).toBe('site')
    if (b) expect(got.id).not.toBe(b.id)
  })

  it('below the officers tier nothing living answers — the frame does not draw them', () => {
    expect(LOD_RULES[lodTier(0.3)].officers).toBe(false)
    const o = SLOTS[0]
    const got = pickAtTile(world({ camera: { z: 0.3, x: o.x, y: o.y } }), o.x, o.y - 0.3)
    expect(got.kind).not.toBe('officer')
    const sx = SITE_FOOTPRINT.x + 1
    const sy = SITE_FOOTPRINT.y + 1
    expect(pickAtTile(world({ camera: { z: 0.3, x: sx, y: sy } }), sx, sy).kind).not.toBe('site')
  })

  it('with no directions the chart table is not a target, in either kernel', () => {
    const c = toWorld(CHART_TABLE_LOCAL.x, CHART_TABLE_LOCAL.y)
    const td = world({ chartTable: false, camera: { z: 3, x: c.x, y: c.y } })
    expect(pickAtTile(td, c.x + 0.5, c.y + 0.5).kind).not.toBe('chart_table')
    expect(pickOnSprite(isoWorld({ chartTable: false }), 'chart_table', 0.5).kind).not.toBe(
      'chart_table'
    )
  })
})

// ── 4. TOP-DOWN DID NOT CHANGE — measured, not claimed ─────────────────────

describe('the top-down pick reproduces the pre-extraction behaviour exactly', () => {
  /**
   * The oracle: the hit test as it stood in engine-canvas.tsx at 3545ec48,
   * transcribed term for term. It is a duplicate on purpose — a differential
   * test needs an independent copy of the OLD behaviour, and "the extraction
   * was verbatim" is a claim until something drives both and compares.
   */
  function oracle(w: PickWorld, wx: number, wy: number): { kind: string; id: string } {
    const p = w
    if (LOD_RULES[lodTier(p.camera.z)].officers) {
      const gh = p.buildings.find((b) => b.element === 'great_house')
      if (gh) {
        const slugs = Object.keys(p.officers).sort()
        for (let i = 0; i < slugs.length; i++) {
          const h = fnv1a(`officer:${slugs[i]}`)
          const ox = gh.x + 0.5 + ((h >>> 4) % (gh.w * 2)) / 2
          const oy = gh.y + gh.h + 1 + (i % 2)
          if (Math.abs(wx - ox) < 0.8 && Math.abs(wy - oy + 0.3) < 1) {
            return { kind: 'officer', id: slugs[i] }
          }
        }
      }
      if (p.life) {
        for (const cm of p.life.commuters) {
          const t = cm.walk.to === 'quay' ? cm.progress : 1 - cm.progress
          const pos = roadPoint(t)
          if (Math.abs(wx - (pos.x + 0.5)) < 0.9 && Math.abs(wy - (pos.y + 1) + 0.5) < 1.2) {
            return { kind: 'officer', id: cm.slug }
          }
        }
        for (const st of p.life.sites) {
          const f = st.site.footprint
          if (wx >= f.x - 1 && wx <= f.x + f.w + 1 && wy >= f.y - 1 && wy <= f.y + f.h + 1) {
            return { kind: 'site', id: st.site.id }
          }
        }
      }
    }
    if (
      Math.abs(wx - (p.geo.crossroads.x + 1.2)) < 1.2 &&
      Math.abs(wy - p.geo.crossroads.y) < 1.6
    ) {
      return { kind: 'mailbox', id: 'mailbox' }
    }
    if (p.chartTable) {
      const ctw = toWorld(CHART_TABLE_LOCAL.x, CHART_TABLE_LOCAL.y)
      if (Math.abs(wx - (ctw.x + 0.5)) < 1.1 && Math.abs(wy - (ctw.y + 0.5)) < 1.2) {
        return { kind: 'chart_table', id: 'chart-table' }
      }
    }
    for (const b of p.buildings) {
      if (wx >= b.x - 0.3 && wx <= b.x + b.w + 0.3 && wy >= b.y - 1 && wy <= b.y + b.h + 0.3) {
        return { kind: 'building', id: b.id }
      }
    }
    for (const site of p.geo.laneSites) {
      const r = site.render === 'isle' ? 12 : 4
      if (Math.hypot(wx - site.cx, wy - site.cy) <= r) {
        return { kind: 'lane', id: `lane:${site.slot}` }
      }
    }
    return { kind: 'ground', id: 'ground' }
  }

  it('agrees with the oracle on 4000 seeded points across four zooms', () => {
    const zooms = [0.25, 0.9, 1.6, 3]
    // HALF the sample is aimed AT the known targets and half roams free. A
    // purely uniform sweep saw only ground/building/lane — the officer, site,
    // mailbox and chart-table tolerances are a tile or two wide on a 240x192
    // canvas, so a uniform sample proves the two branches that are easy to hit
    // and silently skips the four that are not.
    const AIMS = [
      { x: SLOTS[0].x, y: SLOTS[0].y - 0.3 },
      { x: roadPoint(0.5).x + 0.5, y: roadPoint(0.5).y + 0.5 },
      { x: SITE_FOOTPRINT.x + 1, y: SITE_FOOTPRINT.y + 1 },
      { x: GEO.crossroads.x + 1.2, y: GEO.crossroads.y },
      {
        x: toWorld(CHART_TABLE_LOCAL.x, CHART_TABLE_LOCAL.y).x + 0.5,
        y: toWorld(CHART_TABLE_LOCAL.x, CHART_TABLE_LOCAL.y).y + 0.5,
      },
      { x: GH.x + GH.w / 2, y: GH.y + GH.h / 2 },
      { x: LIB.x + LIB.w / 2, y: LIB.y + LIB.h / 2 },
      { x: GEO.laneSites[0].cx, y: GEO.laneSites[0].cy },
    ]
    let checked = 0
    const kinds = new Set<string>()
    for (let i = 0; i < 4000; i++) {
      const h = fnv1a(`pick-sweep:${i}`)
      const z = zooms[h % zooms.length]
      const aim = i % 2 === 0 ? AIMS[(h >>> 2) % AIMS.length] : null
      // camera roams the authored canvas; the point roams the viewport
      const cam = aim
        ? { z, x: aim.x + (((h >>> 5) % 9) - 4) / 4, y: aim.y + (((h >>> 9) % 9) - 4) / 4 }
        : {
            z,
            x: ((h >>> 3) % (GEO.canvas.w + 40)) - 20,
            y: ((h >>> 11) % (GEO.canvas.h + 40)) - 20,
          }
      const w = world({ camera: cam })
      const sx = aim ? VIEWPORT.w / 2 + (((h >>> 19) % 41) - 20) : (h >>> 19) % VIEWPORT.w
      const sy = aim ? VIEWPORT.h / 2 + (((h >>> 25) % 41) - 20) : (h >>> 25) % VIEWPORT.h
      const got = pickTarget(w, { x: sx, y: sy })
      // the oracle takes the world point the SAME inverse produces, so this
      // compares the decision chain and not the kernel (which projection.test
      // already pins bit for bit)
      const t = projectionFor('topdown')
      const s = t.unproject((sx - VIEWPORT.w / 2) / z, (sy - VIEWPORT.h / 2) / z)
      const want = oracle(w, s.tx + cam.x, s.ty + cam.y)
      expect(got, `seeded point ${i}`).toEqual(want)
      kinds.add(got.kind)
      checked++
    }
    expect(checked).toBe(4000)
    // EVERY branch must have fired, or the differential proves only the ones
    // that did — the sweep is the regression proof, so its coverage is part of
    // the assertion rather than a hope.
    expect([...kinds].sort()).toEqual([
      'building',
      'chart_table',
      'ground',
      'lane',
      'mailbox',
      'officer',
      'site',
    ])
  })
})

// ── 5. ABSENT SUBJECTS — what the pick does when there is nothing there ────

describe('an absent subject answers ground, and never invents one', () => {
  it('iso with no scene at all (the pack failed to load) answers ground', () => {
    // The canvas draws ground and no sprites in that state. A pick that fell
    // through to the top-down tolerances would open cards for buildings the
    // frame never drew.
    const got = pickAtTile(isoWorld({ scene: null }), GH.x, GH.y)
    expect(got).toEqual({ kind: 'ground', id: 'ground' })
  })

  it('iso with an empty sprite list answers ground', () => {
    expect(pickAtTile(isoWorld({ scene: { sprites: [] } }), 0, 0)).toEqual({
      kind: 'ground',
      id: 'ground',
    })
  })

  it('a camp cabinet — almost nothing built — answers ground almost everywhere', () => {
    const camp = buildIsoScene(PACK, { era: 'camp', road: 'dirt_path', stages: {}, counts: {} }, 'c')
    const cards = camp.sprites.filter((s) => s.role !== null || STATIONS.has(s.frame))
    // honest zero: a day-zero island really does have nothing measured on it
    expect(cards.length).toBeLessThan(5)
    const w = isoWorld({ scene: camp, buildings: [] })
    const { wx, wy } = tileOfLayoutPx(camp.space.w / 2, camp.space.h / 2)
    expect(pickAtTile({ ...w, camera: { z: 3, x: wx, y: wy } }, wx, wy).kind).toBe('ground')
  })

  /**
   * THE CUTAWAY MOVES THE OFFICERS, so it moves the pick.
   *
   * `officerSlots(gh, slugs, open)` is ONE definition with TWO answers, and the
   * canvas calls it with `p.cutaway.openId === gh.id` while the extraction
   * called it with a hardcoded `false`. Measured 2026-07-28 before this arm
   * existed: with the great house open, a click on the drawn officer at
   * (117.00, 16.60) returned `building:great_house`, and a click on the empty
   * yard at (121.50, 21.00) returned `officer:cos` — a phantom. The whole suite
   * stayed green, including a 4,000-point differential sweep, because its oracle
   * had the closed formula inlined and neither side modelled the open case.
   *
   * Both directions are asserted. An arm that only checked the drawn slot would
   * pass on a pick that answered `officer` for BOTH sets of squares.
   */
  it('with the roof off, the pick follows the officers INSIDE — and leaves the yard', () => {
    const slugs = Object.keys(OFFICERS).sort()
    const inside = officerSlots(GH, slugs, true)
    const yard = officerSlots(GH, slugs, false)
    expect(inside.every((s) => s.inside)).toBe(true)
    expect(inside.map((s) => `${s.x},${s.y}`)).not.toEqual(yard.map((s) => `${s.x},${s.y}`))
    const open = world({ cutawayOpenId: GH.id })
    for (const o of inside) {
      const got = pickAtTile({ ...open, camera: { z: 3, x: o.x, y: o.y } }, o.x, o.y - 0.3)
      expect(got, `drawn officer ${o.slug} inside the open great house`).toEqual({
        kind: 'officer',
        id: o.slug,
      })
    }
    for (const o of yard) {
      const got = pickAtTile({ ...open, camera: { z: 3, x: o.x, y: o.y } }, o.x, o.y - 0.3)
      expect(got.kind, `the yard slot ${o.slug} is empty while the roof is off`).not.toBe('officer')
    }
    // …and shut again, the yard answers and the desks do not.
    const shut = world({ cutawayOpenId: null })
    for (const o of yard) {
      expect(pickAtTile({ ...shut, camera: { z: 3, x: o.x, y: o.y } }, o.x, o.y - 0.3)).toEqual({
        kind: 'officer',
        id: o.slug,
      })
    }
    for (const o of inside) {
      expect(
        pickAtTile({ ...shut, camera: { z: 3, x: o.x, y: o.y } }, o.x, o.y - 0.3).kind,
        `the desk slot ${o.slug} is empty while the roof is on`
      ).not.toBe('officer')
    }
  })

  it('a cutaway open on some OTHER building leaves the officers in the yard', () => {
    // The gate is `openId === greatHouse.id`, not "anything is open" — the
    // officers live in the great house's yard and nowhere else.
    const other = world({ cutawayOpenId: LIB.id })
    const o = SLOTS[0]
    expect(pickAtTile({ ...other, camera: { z: 3, x: o.x, y: o.y } }, o.x, o.y - 0.3)).toEqual({
      kind: 'officer',
      id: o.slug,
    })
  })

  it('no great house means no officer anywhere — not an officer at (0,0)', () => {
    expect(officerSlots(null, ['cos', 'cpo'], false)).toEqual([])
    const noGh = BUILDINGS.filter((b) => b.element !== 'great_house')
    const o = SLOTS[0]
    const got = pickAtTile(world({ buildings: noGh, camera: { z: 3, x: o.x, y: o.y } }), o.x, o.y - 0.3)
    expect(got.kind).not.toBe('officer')
  })

  it('no life layer means no walker and no site, but the world still answers', () => {
    const w = world({ life: null, camera: { z: 3, x: GH.x + GH.w / 2, y: GH.y + GH.h / 2 } })
    expect(pickAtTile(w, GH.x + GH.w / 2, GH.y + GH.h / 2)).toEqual({
      kind: 'building',
      id: 'great_house',
    })
    const sx = SITE_FOOTPRINT.x + 1
    const sy = SITE_FOOTPRINT.y + 1
    expect(pickAtTile(world({ life: null, camera: { z: 3, x: sx, y: sy } }), sx, sy).kind).not.toBe(
      'site'
    )
  })

  it('an empty cabinet never returns null — a dead click is worse than a bare one', () => {
    const empty = world({
      buildings: [],
      officers: {},
      life: null,
      chartTable: false,
      camera: { z: 1, x: 0, y: 0 },
    })
    for (let i = 0; i < 200; i++) {
      const h = fnv1a(`empty:${i}`)
      const got = pickTarget(empty, { x: h % VIEWPORT.w, y: (h >>> 12) % VIEWPORT.h })
      expect(got).toBeTruthy()
      expect(typeof got.id).toBe('string')
    }
  })
})

// ── 6. THE STATION DECLARATION IS VERIFIED, NOT ASSERTED ──────────────────

describe('the stations the pick names really exist', () => {
  it('every STATIONS frame is in the shipped pack AND in a composed scene', () => {
    // A pick that names a frame nothing draws is the dead-twin failure this
    // whole round exists for: the branch reads fine and can never fire.
    expect(STATIONS.size).toBeGreaterThan(0)
    for (const frame of STATIONS.keys()) {
      expect(PACK.frames[frame], `pack ships ${frame}`).toBeDefined()
      expect(
        SCENE.sprites.some((s) => s.frame === frame),
        `a composed hamlet scene contains ${frame}`
      ).toBe(true)
    }
  })

  it('a station is NOT justified by a ladder — which is why role could not gate it', () => {
    for (const frame of STATIONS.keys()) {
      const s = SCENE.sprites.find((sp) => sp.frame === frame)!
      expect(s.role, `${frame} is entitled by an era, not a rung`).toBeNull()
    }
  })
})

// ── 7. THE LEVER GUARD — the world's one actuator has no path through here ─

describe('the killswitch lever cannot be reached through the pick', () => {
  it('no sweep of either kernel produces anything but the seven read-only kinds', () => {
    const READ_ONLY: PickKind[] = [
      'officer',
      'building',
      'lane',
      'mailbox',
      'chart_table',
      'site',
      'ground',
    ]
    for (const projection of ['topdown', 'iso'] as const) {
      for (let i = 0; i < 1500; i++) {
        const h = fnv1a(`lever-sweep:${projection}:${i}`)
        const w = world({
          projection,
          camera: {
            z: [0.25, 1, 3][h % 3],
            x: ((h >>> 3) % 300) - 60,
            y: ((h >>> 11) % 260) - 60,
          },
        })
        const got = pickTarget(w, { x: (h >>> 17) % VIEWPORT.w, y: (h >>> 23) % VIEWPORT.h })
        expect(READ_ONLY, `${projection} point ${i} -> ${got.kind}`).toContain(got.kind)
      }
    }
  })

  it('the pick module imports nothing that can write', () => {
    // Ratchet #1b says exactly one file imports exactly one server action, and
    // that file is killswitch-lever.tsx. This is the same guard read from the
    // other end: the module every click now flows through must be inert.
    const src = fs.readFileSync(path.resolve(__dirname, 'pick.ts'), 'utf8')
    // COMMENTS STRIPPED FIRST: the module's own docstring says the word
    // "killswitch" while explaining why it must never reach one, and an
    // earlier version of this arm fired on that sentence. A guard that a
    // truthful comment can trip teaches the next author to delete the comment.
    const code = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
    expect(code).not.toMatch(/['"]use server['"]/)
    expect(code).not.toMatch(/from '@\/app\//)
    expect(code).not.toMatch(/action/i)
    expect(code.toLowerCase()).not.toMatch(/lever|killswitch/)
  })
})
