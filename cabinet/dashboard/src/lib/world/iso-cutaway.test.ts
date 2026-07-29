/**
 * iso-cutaway.test.ts — every arm here was watched FAIL before it was kept.
 *
 * The pattern each block follows: state the rule, then feed the same input with
 * that one rule neutralised and assert the answer changes. An arm nobody has
 * seen fail is decoration, and this module is full of rules whose absence is
 * invisible — a candidate rule that never fires leaves the whole cutaway machine
 * green and dead.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  ISO_CUTAWAY_MIN_H,
  cutawayMix,
  interiorSlots,
  isoCutawayCandidate,
  openFrameOf,
  openTwinRefusal,
  ROOM_FLOOR,
  roomChildStale,
  type CutawaySprite,
} from './iso-cutaway'
import { CUTAWAY_FADE_MS, ROOF_ALPHA_OPEN, TICK_MS, initialCutaway, roofAlpha } from './lod'
import { groundDiamond } from './projection'
import { buildIsoScene } from './iso-scene'
import type { LayoutState } from './iso-layout'
import type { IsoPack } from './iso-pack'

const PACK: IsoPack = JSON.parse(
  readFileSync(
    join(process.cwd(), 'public', 'world-assets', 'originals', 'iso', 'world-pack.json'),
    'utf8'
  )
)

/** A pack with only the frames a case needs — no fixture inherits the atlas. */
function packOf(frames: Record<string, { dw: number; dh: number }>): IsoPack {
  const f: Record<string, unknown> = {}
  for (const [n, s] of Object.entries(frames)) {
    f[n] = { atlas: 0, x: 0, y: 0, w: s.dw, h: s.dh, dw: s.dw, dh: s.dh, scale: 1, anchor: [s.dw / 2, s.dh] }
  }
  return { ...PACK, frames: f as IsoPack['frames'] }
}

function sprite(over: Partial<CutawaySprite> = {}): CutawaySprite {
  return { id: 'a', frame: 'great_house', x: 1200, y: 800, dw: 196, dh: 174, role: 'great_house', ...over }
}

const VP = { w: 1280, h: 800 }

describe('openFrameOf — the ATLAS answers, not a list', () => {
  it('returns the twin at ITS OWN drawn size, which is not the closed size', () => {
    const p = packOf({ great_house: { dw: 196, dh: 174 }, great_house_open: { dw: 190, dh: 120 } })
    expect(openFrameOf(p, 'great_house')).toEqual({ frame: 'great_house_open', dw: 190, dh: 120 })
  })

  it('is null when the pack has no twin — a building with no art simply does not open', () => {
    const p = packOf({ great_house: { dw: 196, dh: 174 } })
    expect(openFrameOf(p, 'great_house')).toBeNull()
  })

  // THE ABSENT END. A pack with no frames at all must answer null, not throw and
  // not answer for a frame it does not have.
  it('is null against an EMPTY pack', () => {
    expect(openFrameOf(packOf({}), 'great_house')).toBeNull()
    expect(openFrameOf(packOf({}), '')).toBeNull()
  })
})

describe('isoCutawayCandidate', () => {
  const P = packOf({ great_house: { dw: 196, dh: 174 }, great_house_open: { dw: 190, dh: 120 } })

  it('opens the building the camera is pointed at', () => {
    const s = sprite()
    // centre inside the drawn rect: x within ±dw/2, y within [y-dh, y]
    expect(isoCutawayCandidate([s], P, { x: 1200, y: 720 }, VP, 1)).toBe('a')
  })

  // THE ABSENT SUBJECT: the camera is over open ground. Not an error, not the
  // nearest building — nothing opens.
  it('is null when the centre is off every building', () => {
    const s = sprite()
    expect(isoCutawayCandidate([s], P, { x: 1200, y: 900 }, VP, 1)).toBeNull() // below its base
    expect(isoCutawayCandidate([s], P, { x: 1200, y: 600 }, VP, 1)).toBeNull() // above its roof
    expect(isoCutawayCandidate([s], P, { x: 1400, y: 720 }, VP, 1)).toBeNull() // beside it
    expect(isoCutawayCandidate([], P, { x: 1200, y: 720 }, VP, 1)).toBeNull() // no sprites at all
  })

  it('is null on a degenerate viewport or scale', () => {
    const s = sprite()
    expect(isoCutawayCandidate([s], P, { x: 1200, y: 720 }, { w: 0, h: 0 }, 1)).toBeNull()
    expect(isoCutawayCandidate([s], P, { x: 1200, y: 720 }, VP, 0)).toBeNull()
  })

  // ARM: the on-screen size floor. DISABLED-FORM: the same sprite at a scale
  // where the floor passes must open, so the null below is the FLOOR firing and
  // not the rule silently never matching.
  it('refuses a building that is too small on screen, and opens it when it is not', () => {
    const s = sprite()
    const tooSmall = (ISO_CUTAWAY_MIN_H * VP.h) / s.dh / 2
    expect(isoCutawayCandidate([s], P, { x: 1200, y: 720 }, VP, tooSmall)).toBeNull()
    expect(isoCutawayCandidate([s], P, { x: 1200, y: 720 }, VP, tooSmall * 4)).toBe('a')
  })

  // ARM: decoration never opens. DISABLED-FORM: give the same sprite a role.
  it('never opens a sprite no state entitled', () => {
    const deco = sprite({ role: null })
    expect(isoCutawayCandidate([deco], P, { x: 1200, y: 720 }, VP, 1)).toBeNull()
    expect(isoCutawayCandidate([sprite()], P, { x: 1200, y: 720 }, VP, 1)).toBe('a')
  })

  // ARM: no twin in the atlas, no opening. DISABLED-FORM: add the twin.
  it('never opens a building the pack has no roof-off art for', () => {
    const noTwin = packOf({ great_house: { dw: 196, dh: 174 } })
    expect(isoCutawayCandidate([sprite()], noTwin, { x: 1200, y: 720 }, VP, 1)).toBeNull()
    expect(isoCutawayCandidate([sprite()], P, { x: 1200, y: 720 }, VP, 1)).toBe('a')
  })

  // ARM: front-most wins. DISABLED-FORM: reverse the depth order and watch the
  // answer flip — which is what proves the scan direction is load-bearing rather
  // than incidental.
  it('returns the FRONT-MOST of two buildings under the centre', () => {
    const far = sprite({ id: 'far', y: 780 })
    const near = sprite({ id: 'near', y: 820 })
    expect(isoCutawayCandidate([far, near], P, { x: 1200, y: 740 }, VP, 1)).toBe('near')
    expect(isoCutawayCandidate([near, far], P, { x: 1200, y: 740 }, VP, 1)).toBe('far')
  })

  /**
   * THE ARM THAT EXISTS BECAUSE THE PORT WOULD HAVE SHIPPED GREEN AND DEAD.
   *
   * lod.cutawayCandidate opens the first bound building covering ≥40% of the
   * viewport's central third. Reproduce that measure here against the REAL iso
   * numbers — the great house at its pack size, the iso scale re-based by
   * ISO_BASE — and it never reaches the floor at any zoom the close tier covers.
   * So a verbatim port yields a cutaway that can never fire, with every existing
   * lod test still passing.
   */
  it('the top-down 40%-of-the-central-third rule cannot fire on iso numbers', () => {
    const box = ((2 * VP.w) / 3 - VP.w / 3) * ((2 * VP.h) / 3 - VP.h / 3)
    const cover = (dw: number, dh: number, scale: number) => (dw * scale * dh * scale) / box
    // z = 3 is ZOOM_MAX and ISO_BASE = 1/3, so scale 1.0 is as large as the
    // world ever draws; the close tier's own floor is z = 2.5 -> 0.833.
    expect(cover(196, 174, 1.0)).toBeLessThan(0.4)
    expect(cover(196, 174, 0.833)).toBeLessThan(0.4)
    // ...and the rule this module ships DOES fire on exactly those numbers.
    expect(isoCutawayCandidate([sprite()], P, { x: 1200, y: 720 }, VP, 0.833)).toBe('a')
  })
})

/**
 * AGAINST THE SHIPPED PACK, not a fixture. Everything above proves the rules;
 * this proves the ART the rules run on is really there, which is the half a
 * mocked pack can never answer for.
 */
describe('the shipped pack’s roof-off art', () => {
  /** The buildings the world's own law says have an interior
   *  (world-buildings.ts ANCHORS `interior: true`, plus the dwellings). */
  const WITH_INTERIORS = ['great_house', 'library', 'workshop', 'officer_dwellings']
  /** Fixtures the renderer names by frame; an absent one draws nothing. */
  const KIT = ['int_desk']

  it('no roof-off frame is an orphan — every _open has its closed twin', () => {
    const opens = Object.keys(PACK.frames).filter((n) => n.endsWith('_open'))
    expect(opens.length).toBeGreaterThan(0)
    for (const n of opens) {
      expect(PACK.frames[n.slice(0, -'_open'.length)], `${n} has no closed twin`).toBeDefined()
    }
  })

  /**
   * ASKED OF A COMPOSED SCENE, not of the resolve table — and the difference is
   * a gap this arm found on its first run. `great_house` at hamlet has FOUR
   * rungs and the layout refines per lot within the era, so a great-house lot
   * can draw `cottage_a`; officer dwellings draw `officer_house_b`/`_c` and the
   * cottages. Reading the table's rows alone would have declared the wave
   * complete with most dwellings on a real island still un-openable.
   *
   * The role name is the SCENE's (`officer_dwelling`, singular), aliased in
   * iso-scene the same way the pack lookup aliases it.
   */
  it('every interior-bearing building a hamlet island DRAWS either opens, or is refused BY NAME', () => {
    const st = JSON.parse(
      readFileSync(join(process.cwd(), '..', 'scripts', 'world-capture', 'states', 'hamlet.json'), 'utf8')
    ) as { seed: string; state: LayoutState }
    const scene = buildIsoScene(PACK, st.state, st.seed)
    const want = new Set([...WITH_INTERIORS, 'officer_dwelling'])
    const drawn = scene.sprites.filter((s) => s.role !== null && want.has(s.role))
    expect(drawn.length, 'the hamlet island drew none of them').toBeGreaterThan(4)
    // Two of the seven now stand refused: `library_open` is a different
    // building and `officer_house_b_open` is wider on the ground than what it
    // replaces (iso-cutaway.openTwinRefusal). They keep the interim roof-fade.
    // `cottage_b` left this list on 2026-07-28 — it was oversized by a baked
    // exterior lawn rather than by its walls, and the lawn peel put it back
    // inside its closed footprint. THE POINT OF SPLITTING THE ANSWER: "has no twin"
    // and "has a twin the world will not use" were one bucket, so the day a
    // building silently stops opening it would have joined a list nobody reads.
    const noArt: string[] = []
    const refused: string[] = []
    for (const f of [...new Set(drawn.map((s) => s.frame))].sort()) {
      if (openFrameOf(PACK, f)) continue
      if (PACK.frames[`${f}${'_open'}`]) refused.push(f)
      else noArt.push(f)
    }
    expect(noArt, 'drawn on a hamlet island with no roof-off twin at all').toEqual([])
    expect(refused, 'the refused set changed — re-read openTwinRefusal before touching this').toEqual(
      ['library', 'officer_house_b']
    )
    for (const f of refused) expect(openTwinRefusal(PACK, f)).not.toBeNull()
    // and the majority still opens, so the feature is alive rather than
    // refused into silence
    const opens = [...new Set(drawn.map((s) => s.frame))].filter((f) => openFrameOf(PACK, f)).sort()
    expect(opens).toEqual(['cottage_a', 'cottage_b', 'great_house', 'officer_house_c', 'workshop'])
  })

  /**
   * AND THE ABSENCE IS DECLARED. A camp library is a crate of books and a camp
   * workshop is a toolbox against a wall — there is no room to open, so those
   * frames have no twin and the interim fade is what they get. Asserted rather
   * than left to be discovered in a screenshot, and it goes red the day someone
   * generates art for them without wiring it.
   */
  it('the camp vocabulary has NO interiors, on purpose', () => {
    for (const frame of ['camp_book_crate', 'camp_toolbox', 'camp_tent']) {
      expect(PACK.frames[frame], `${frame} left the pack`).toBeDefined()
      expect(openFrameOf(PACK, frame)).toBeNull()
    }
  })

  it('the interior kit the renderer names is in the atlas', () => {
    for (const n of KIT) expect(PACK.frames[n], `${n} is missing`).toBeDefined()
  })
})

describe('cutawayMix — ONE timing law, two alphas', () => {
  const open = { ...initialCutaway(), openId: 'a', openedAt: 0 }

  it('without roof-off art it is TODAY, bit for bit, and draws no interior', () => {
    for (const tick of [0, 1, 2, 5, 40]) {
      const m = cutawayMix(open, 'a', tick, false)
      expect(m.closed).toBe(roofAlpha(open, 'a', tick))
      expect(m.open).toBe(0)
    }
  })

  it('with roof-off art the roof goes ALL the way off, and the two sum to one', () => {
    const full = Math.ceil(CUTAWAY_FADE_MS / TICK_MS)
    for (const tick of [0, 1, full, full + 20]) {
      const m = cutawayMix(open, 'a', tick, true)
      expect(m.closed + m.open).toBeCloseTo(1, 12)
    }
    expect(cutawayMix(open, 'a', 0, true)).toEqual({ closed: 1, open: 0 })
    const done = cutawayMix(open, 'a', full, true)
    expect(done.closed).toBeCloseTo(0, 12)
    expect(done.open).toBeCloseTo(1, 12)
    // and the ghost the interim leaves behind is exactly what this removes
    expect(roofAlpha(open, 'a', full)).toBeCloseTo(ROOF_ALPHA_OPEN, 12)
  })

  it('a building that is neither open nor closing keeps its roof, both ways', () => {
    expect(cutawayMix(initialCutaway(), 'a', 9, true)).toEqual({ closed: 1, open: 0 })
    expect(cutawayMix(initialCutaway(), 'a', 9, false)).toEqual({ closed: 1, open: 0 })
  })

  it('the closing ramp runs backwards, and still sums to one', () => {
    const closing = { ...initialCutaway(), closingId: 'a', closedAt: 4 }
    const m0 = cutawayMix(closing, 'a', 4, true)
    const m1 = cutawayMix(closing, 'a', 4 + Math.ceil(CUTAWAY_FADE_MS / TICK_MS), true)
    expect(m0.open).toBeCloseTo(1, 12)
    expect(m1.open).toBeCloseTo(0, 12)
    expect(m0.closed + m0.open).toBeCloseTo(1, 12)
  })
})

describe('interiorSlots — the room is a DIAMOND, and the fixtures sit on its lattice', () => {
  const open = { frame: 'great_house_open', dw: 190, dh: 120 }
  const BX = 1200
  const BY = 800

  it('every slot lies inside the open frame’s OWN inset ground diamond', () => {
    const g = groundDiamond(open.dw, open.dh)
    const slots = interiorSlots(open, BX, BY, 8)
    expect(slots.length).toBeGreaterThan(0)
    const cy = BY - g.depth / 2
    for (const s of slots) {
      // the shared footprint, re-derived from projection — never restated here
      const u = Math.abs(s.x - BX) / g.hw + Math.abs(s.y - cy) / (g.depth / 2)
      expect(u, `slot ${s.x},${s.y} escaped the room`).toBeLessThanOrEqual(1)
    }
  })

  // THE ABSENT END, four ways. A room with no officers, no floor, or no size at
  // all must return nothing rather than one slot at the origin.
  it('is empty for zero fixtures and for a degenerate frame', () => {
    expect(interiorSlots(open, BX, BY, 0)).toEqual([])
    expect(interiorSlots(open, BX, BY, -3)).toEqual([])
    expect(interiorSlots({ frame: 'x', dw: 0, dh: 0 }, BX, BY, 4)).toEqual([])
    expect(interiorSlots(open, BX, BY, 4, { margin: 1 })).toEqual([])
  })

  it('never returns more slots than were asked for', () => {
    for (const n of [1, 2, 3, 5, 400]) {
      expect(interiorSlots(open, BX, BY, n).length).toBeLessThanOrEqual(n)
    }
  })

  /**
   * ARM: the room fills from its CENTRE, not from its back wall.
   *
   * The first version of this took the first `count` slots in depth order, and
   * the eye check showed five desks jammed into the top 17px of a 58px-deep
   * floor with the whole front of the room bare. One officer must stand in the
   * middle of the room; a back-to-front slice puts them against the far wall.
   */
  it('one fixture stands at the room’s centre, and three stay on its centre row', () => {
    const g = groundDiamond(open.dw, open.dh)
    const cy = BY - g.depth / 2
    // decisive: back-to-front slicing answers the BACK-MOST slot here
    expect(interiorSlots(open, BX, BY, 1)).toEqual([{ x: BX, y: cy }])
    // ...and fills sideways before it fills backwards. A depth slice puts the
    // first three at y = cy − 17, cy − 8.5, cy − 8.5 on this room.
    const three = interiorSlots(open, BX, BY, 3)
    expect(three).toHaveLength(3)
    expect(Math.max(...three.map((s) => Math.abs(s.y - cy)))).toBeLessThan(8.5)
  })

  it('comes back BACK TO FRONT, so the caller needs no second sort', () => {
    const ys = interiorSlots(open, BX, BY, 6).map((s) => s.y)
    expect([...ys].sort((a, b) => a - b)).toEqual(ys)
  })

  /**
   * ARM: the lattice is ISOMETRIC, and the assertion is the one that TELLS THE
   * TWO APART.
   *
   * The first version of this arm asserted "every x gap is a whole step or a
   * half step" and stayed GREEN when the lattice was mutated to a rectangular
   * grid — a rect grid's gaps are all whole steps, so the property was one both
   * shapes have. Found by running that mutation; kept here as the reason the
   * assertion looks the way it does.
   *
   * What separates them: rows of the 2:1 lattice are offset by HALF a step, so
   * the smallest gap between distinct x values is step/2 and it really occurs.
   * A rectangular grid (the defect this replaces — `col * (w-2)/2.5, row * 1.6`
   * in tile space, drawn inside an isometric building) can only ever produce
   * whole-step gaps.
   */
  it('slots sit on the 2:1 lattice, not on a rectangle', () => {
    const STEP = 34
    const slots = interiorSlots(open, BX, BY, 12, { step: STEP })
    const xs = [...new Set(slots.map((s) => Math.round(s.x * 1e6) / 1e6))].sort((a, b) => a - b)
    expect(xs.length).toBeGreaterThan(2)
    const gaps = xs.slice(1).map((v, i) => v - xs[i])
    // the half-step offset EXISTS — this is the arm a rect grid fails
    expect(Math.min(...gaps)).toBeCloseTo(STEP / 2, 9)
    // ...and nothing lands off the lattice
    for (const d of gaps) {
      expect(Math.abs(d / (STEP / 2) - Math.round(d / (STEP / 2)))).toBeLessThan(1e-9)
    }
    // and a lattice ROW is a whole step across: two slots at one y, x apart by
    // exactly `step` (u−v moves by 2 when u+v is held)
    const byY = new Map<number, number[]>()
    for (const s of slots) {
      const k = Math.round(s.y * 1e6) / 1e6
      byY.set(k, [...(byY.get(k) ?? []), s.x])
    }
    const rows = [...byY.values()].filter((r) => r.length > 1)
    expect(rows.length).toBeGreaterThan(0)
    for (const r of rows) {
      const sorted = [...r].sort((a, b) => a - b)
      expect(sorted[1] - sorted[0]).toBeCloseTo(STEP, 9)
    }
  })
})

describe('roomChildStale — a pool may only switch off what it PLACED', () => {
  /**
   * THE ARM THAT WOULD HAVE CAUGHT THE ROOM GOING INVISIBLE.
   *
   * Watched fail against the pre-change rule (`!!label && !want.has(label)`),
   * which answers `true` here and is what hid the floor. It reads the label off
   * a REAL PixiJS Sprite rather than the string this repo assumed one carries —
   * the whole defect was an assumption about somebody else's constructor, so a
   * fixture repeating the assumption would re-encode the bug as a test.
   */
  it('never hides a child it did not place — whatever PixiJS names it', async () => {
    const PIXI = await import('pixi.js')
    const untouched = new PIXI.Sprite().label
    // the premise, stated out loud: PixiJS does NOT leave it empty
    expect(untouched).toBeTruthy()
    expect(roomChildStale(untouched, new Set(['desk:0', 'off:cto']))).toBe(false)
    // and the pre-change rule, shown failing on the same input
    const preChange = (l: string | null, w: ReadonlySet<string>) => Boolean(l) && !w.has(l ?? '')
    expect(preChange(untouched, new Set(['desk:0', 'off:cto']))).toBe(true)
  })

  it('never hides the floor, even when the caller forgets to want it', () => {
    expect(roomChildStale(ROOM_FLOOR, new Set())).toBe(false)
  })

  it('still does its job: a slot this pass did not place is stale', () => {
    // five officers became three — desks 3 and 4 must stop being drawn, which
    // is the ONLY reason this sweep exists
    const want = new Set(['desk:0', 'desk:1', 'desk:2', 'off:coo', 'off:cos', 'off:cpo'])
    expect(roomChildStale('desk:3', want)).toBe(true)
    expect(roomChildStale('off:cro', want)).toBe(true)
    expect(roomChildStale('desk:1', want)).toBe(false)
    expect(roomChildStale('off:cos', want)).toBe(false)
  })

  it('an unlabelled child is not ours either', () => {
    expect(roomChildStale('', new Set())).toBe(false)
    expect(roomChildStale(null, new Set())).toBe(false)
    expect(roomChildStale(undefined, new Set())).toBe(false)
  })

  /**
   * The renderer must actually seed `want` with the floor and route every
   * hide through this predicate. A pure function nobody calls is the class-11
   * defect this repo keeps paying for, so the wiring is pinned by grep — the
   * same device ratchets.test.ts uses for the contracts the canvas must honour.
   */
  it('the canvas labels its floor and sweeps through this predicate', () => {
    const src = readFileSync(
      join(process.cwd(), 'src', 'components', 'world', 'engine-canvas.tsx'),
      'utf8'
    )
    expect(src).toMatch(/floor\.label\s*=\s*ROOM_FLOOR/)
    expect(src).toMatch(/new Set<string>\(\[ROOM_FLOOR\]\)/)
    expect(src).toMatch(/roomChildStale\(/)
    // and nothing left behind that hides a child on truthiness alone
    expect(src).not.toMatch(/if \(n && !want\.has\(n\)\)/)
  })
})
