/**
 * PLANTING CONTENT tests — the forest enclosure ring, the ground passes, the
 * pond's own dressing, and the officer row's per-lot house.
 *
 * Same standard as iso-layout.test.ts: every arm asserts something that would
 * be FALSE against a naive implementation, and each one either carries its
 * negative twin here or names the source mutation that was run against it and
 * what that mutation did. An arm with neither is a disabled sensor wearing a
 * green tick.
 */
import { describe, expect, it } from 'vitest'
import {
  auditLayout,
  buildLaneField,
  clearOfDistricts,
  composeLayout,
  CAMP_DWELLING,
  DEFAULT_FOOTPRINTS,
  footprintOnLane,
  forestRing,
  maxGroundOverlap,
  grownField,
  HOUSE_KINDS,
  inRingGap,
  LAYOUT_SPACE,
  MOTTLE_TONES,
  OUTFLOW,
  paintField,
  POND,
  RING_DISTRICT_K,
  RING_GAPS,
  RING_LAYERS,
  REED_MARGIN,
  RING_MIN_RADIUS,
  RING_SPACING,
  rectField,
  ringAngleDeg,
  waterField,
  type Lane,
  type Layout,
  type LayoutState,
  type Point,
  type RingContext,
} from './index'

const FAST = { coastline: { step: 8 } }

const HAMLET: LayoutState = {
  era: 'hamlet',
  road: 'dirt_worn',
  stages: {
    great_house: 'cottage',
    well: 'stone_well',
    library: 'shelf',
    workshop: 'forge',
    outbuildings: 'shed',
    market_stall: 'stall',
  },
  counts: { officer_dwellings: 3, field_plots: 2 },
}

const CAMP: LayoutState = {
  era: 'camp',
  road: 'dirt_path',
  stages: { great_house: 'camp_log_cabin', library: 'none', workshop: 'none' },
  counts: { officer_dwellings: 1 },
}

const VILLAGE: LayoutState = {
  era: 'hamlet',
  road: 'gravel_road',
  stages: {
    great_house: 'timber_hall',
    library: 'stone_hall',
    workshop: 'forge',
    outbuildings: 'barn',
    well: 'stone_well',
    market_stall: 'stall',
    firepit: 'firepit',
  },
  counts: { officer_dwellings: 6, field_plots: 4 },
}

const SEEDS = ['acme-corp', 'harbour', 'lantern', 'captains-cabinet', 'zeta']
const WIDE_SEEDS = Array.from({ length: 40 }, (_, i) => `org-${i}`)

const hamlet = composeLayout(HAMLET, 'acme-corp', FAST)
const camp = composeLayout(CAMP, 'acme-corp', FAST)

/**
 * A seed whose west meadow has room for the pond.
 *
 * NOT the file's default island: on `acme-corp` the pond anchor (612,1086) is
 * open sea, so that island honestly has no pond, no outflow and no bank at all.
 * That is the reference's own behaviour ("on some islands there is no room for
 * one"), and it is the reason the pond arms below name their seed instead of
 * riding the fixture — an arm about the pond that runs on the one island
 * without one is a sensor measuring nothing.
 */
const PONDY = 'harbour'
const pondy = composeLayout(HAMLET, PONDY, FAST)

/** The reference's own frame: distance and bearing from the island centre. */
function radial(p: Point): { d: number; deg: number } {
  const d = Math.hypot(p.x - LAYOUT_SPACE.cx, (p.y - LAYOUT_SPACE.cy) / 0.92)
  return { d, deg: ringAngleDeg(p, LAYOUT_SPACE) }
}

/** How far out this point sits, as a fraction of the island's radius there. */
function radialFraction(l: Layout, p: Point): number {
  const { d } = radial(p)
  const ang = Math.atan2((p.y - LAYOUT_SPACE.cy) / 0.92, p.x - LAYOUT_SPACE.cx)
  return d / l.coast.landEdge(ang)
}

/** A RingContext over a composed layout, with every gate wide open but the ring's own. */
function ctxOf(l: Layout, over: Partial<RingContext> = {}): RingContext {
  return {
    space: l.space,
    coast: l.coast,
    lanes: buildLaneField(l.lanes),
    districts: l.districts,
    occupied: [],
    inWater: () => false,
    onPaving: () => false,
    onQuay: () => false,
    sizeOf: (k) => DEFAULT_FOOTPRINTS[k] ?? { w: 96, h: 96 },
    ...over,
  }
}

// ── the forest enclosure ring ──────────────────────────────────────────────

describe('the forest enclosure ring — the frame, not a gradient', () => {
  it('the belt is planted, and it is the larger half of the planting', () => {
    // Before the ring the island carried 41-68 items at hamlet and the coast was
    // bare. This is the count arm for that.
    //
    // THE FLOOR IS 60 AND NOT A REFERENCE FIGURE, deliberately. The line here
    // used to read "the reference draws 150-200", which was an inherited claim
    // with no measurement under it — compose.py's belt walks the same 4 layers
    // at the same 4.4-7.2 degree step, so its candidate ceiling is the same ~250
    // and its three rejection terms are the ones this port copied. Measured, the
    // composed belt is 74-119 per hamlet island and the port's own added rules
    // cost 3.5 of that (see forestRing's rejection budget). Asserting against a
    // number nobody measured would be pinning this suite to a rumour.
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      expect({ seed, enough: l.ring.length > 60 }).toEqual({ seed, enough: true })
      expect({ seed, dominant: l.ring.length > l.scatter.length }).toEqual({
        seed,
        dominant: true,
      })
    }
  })

  it('the belt is COASTAL and the sublayers stack inward in order', () => {
    // The property that distinguishes a frame from a gradient: every layer sits
    // at its own depth, and layer 0 is the silhouette against the sea. A field
    // that merely thickened toward the coast would put all four at one mean.
    const byLayer = RING_LAYERS.map((_, i) => hamlet.ring.filter((r) => r.layer === i))
    for (const items of byLayer) expect(items.length).toBeGreaterThan(8)
    const meanFrac = byLayer.map(
      (items) => items.reduce((s, r) => s + radialFraction(hamlet, r.at), 0) / items.length
    )
    // strictly decreasing: 0 outermost
    for (let i = 1; i < meanFrac.length; i++) {
      expect({ i, inward: meanFrac[i] < meanFrac[i - 1] }).toEqual({ i, inward: true })
    }
    // and all of it is out in the coastal band, not in the meadow
    expect(meanFrac[meanFrac.length - 1]).toBeGreaterThan(0.55)
    expect(meanFrac[0]).toBeGreaterThan(0.9)
  })

  it('the belt has GAPS, and the gaps are a choice rather than missing island', () => {
    // A ring with no gaps is a wall: it hides the water, and the water is what
    // says "island". So two halves — nothing inside a gap arc...
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      const inGap = l.ring.filter((r) => inRingGap(radial(r.at).deg))
      expect({ seed, inGap: inGap.map((r) => r.kind) }).toEqual({ seed, inGap: [] })
    }
    // ...and every gap arc HAS island under it, so the emptiness is the rule
    // and not the coastline. Without this half the arm would pass on an island
    // that simply had no land at those bearings.
    for (const [lo, hi] of RING_GAPS) {
      const mid = ((lo + hi) / 2) * (Math.PI / 180)
      const edge = hamlet.coast.edgeAt(mid)
      expect({ lo, hi, plantable: edge - RING_LAYERS[0].inset > RING_MIN_RADIUS }).toEqual({
        lo,
        hi,
        plantable: true,
      })
      const r = edge - RING_LAYERS[0].inset - 10
      const p = {
        x: LAYOUT_SPACE.cx + Math.cos(mid) * r,
        y: LAYOUT_SPACE.cy + Math.sin(mid) * r * 0.92,
      }
      expect({ lo, hi, land: hamlet.coast.landAt(p.x, p.y) }).toEqual({ lo, hi, land: true })
    }
    // ...and the belt IS dense on the bearings either side, so "no items in the
    // gap" is not "no items anywhere"
    const justOutside = hamlet.ring.filter((r) => {
      const d = radial(r.at).deg
      return RING_GAPS.some(([lo, hi]) => (d > lo - 14 && d <= lo) || (d >= hi && d < hi + 14))
    })
    expect(justOutside.length).toBeGreaterThan(3)
  })

  it('inRingGap is the reference arcs, exclusive at both ends', () => {
    // unit twin for the population arm above
    expect(inRingGap(90)).toBe(true) // due south — the harbour
    expect(inRingGap(32)).toBe(true) // the lighthouse point
    expect(inRingGap(210)).toBe(true) // west-north-west
    expect(inRingGap(58)).toBe(false)
    expect(inRingGap(122)).toBe(false)
    expect(inRingGap(0)).toBe(false)
    expect(inRingGap(180)).toBe(false)
    expect(inRingGap(300)).toBe(false)
  })

  it('the belt CROWDS a district but never grows through it', () => {
    // compose.py:916-918 — the shrink to RING_DISTRICT_K is what stops a bald
    // collar appearing around every district. Both halves are needed: without
    // the first the belt could sit on the great house, without the second the
    // constant could be 1.0 and nobody would know.
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      const through = l.ring.filter((r) => !clearOfDistricts(r.at.x, r.at.y, l.districts))
      expect({ seed, through: through.map((r) => r.kind) }).toEqual({ seed, through: [] })
    }
    // ...and the shrink is LIVE: some of the belt stands inside a full-radius
    // disc, which is exactly the ground the 0.62 factor hands back.
    const crowding = hamlet.ring.filter((r) => !clearOfDistricts(r.at.x, r.at.y, hamlet.districts, 1))
    expect(crowding.length).toBeGreaterThan(0)
    expect(RING_DISTRICT_K).toBeLessThan(1)
  })

  it('the belt keeps its own spacing — no two trunks inside RING_SPACING', () => {
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      let worst = Infinity
      for (let i = 0; i < l.ring.length; i++) {
        for (let j = i + 1; j < l.ring.length; j++) {
          const a = l.ring[i].at
          const b = l.ring[j].at
          worst = Math.min(worst, Math.hypot(a.x - b.x, (a.y - b.y) * 1.35))
        }
      }
      expect({ seed, ok: worst >= RING_SPACING }).toEqual({ seed, ok: true })
    }
  })

  it('the spacing rule can actually FAIL — a belt planted without it crowds', () => {
    // negative twin: the same walk with the caller's book pre-seeded so that
    // nothing is admissible proves nothing, so instead prove the rule bites by
    // showing the belt is DENSER than the rule alone would allow if it were
    // absent. Concretely: at least one adjacent pair sits within 1.6x the rule,
    // i.e. the walk really is offering candidates the rule has to judge.
    let near = 0
    for (let i = 0; i < hamlet.ring.length; i++) {
      for (let j = i + 1; j < hamlet.ring.length; j++) {
        const a = hamlet.ring[i].at
        const b = hamlet.ring[j].at
        const d = Math.hypot(a.x - b.x, (a.y - b.y) * 1.35)
        if (d < RING_SPACING * 1.6) near++
      }
    }
    expect(near).toBeGreaterThan(0)
  })

  it('a building keeps its ground: the belt yields to the occupancy book', () => {
    // The one rule the belt does NOT get its own looser version of. Planted
    // against a book holding one enormous occupant, the belt must have a hole
    // in it exactly there.
    const blocker = { at: { x: 1200, y: 1500 }, size: { w: 900, h: 900 } }
    const open = forestRing('acme-corp', ctxOf(hamlet))
    const blocked = forestRing('acme-corp', ctxOf(hamlet, { occupied: [blocker] }))
    expect(blocked.length).toBeLessThan(open.length)
    for (const r of blocked) {
      expect(Math.hypot(r.at.x - blocker.at.x, r.at.y - blocker.at.y)).toBeGreaterThan(60)
    }
  })

  it('the ROAD WINS for the belt too — a lane in the treeline makes a hole', () => {
    // BOTH of the belt's road terms are quiet on the real network: every
    // carriageway is inland of the radii the belt walks, so deleting the
    // near-lane test AND the footprint test together leaves all 164 arms green
    // (mutation run 2026-07-27). That is a MISSING SENSOR rather than a
    // redundant rule — the day a lane reaches the treeline, or the day the belt
    // reaches further in, nothing would have said so. This arm supplies the
    // situation instead of waiting for the world to.
    const deg = 270 // due north: outside every gap arc
    const ang = (deg * Math.PI) / 180
    const r = hamlet.coast.edgeAt(ang) - RING_LAYERS[0].inset
    const pts: Point[] = []
    for (let d = -30; d <= 30; d += 2) {
      const a = ang + (d * Math.PI) / 180
      pts.push({
        x: LAYOUT_SPACE.cx + Math.cos(a) * r,
        y: LAYOUT_SPACE.cy + Math.sin(a) * r * 0.92,
      })
    }
    const road: Lane[] = [{ key: 'treeline', kind: 'coastal', width: 60, runs: [pts] }]
    const withRoad = forestRing('acme-corp', ctxOf(hamlet, { lanes: buildLaneField(road) }))
    const noRoad = forestRing('acme-corp', ctxOf(hamlet, { lanes: buildLaneField([]) }))
    const field = buildLaneField(road)
    expect(withRoad.length).toBeLessThan(noRoad.length)
    for (const item of withRoad) {
      expect(footprintOnLane(item.at, item.size, field)).toBe(false)
      expect(field.nearLane(item.at.x, item.at.y, 40)).toBe(false)
    }
    // ...and the hole is where the lane is: the outermost sublayer, which the
    // lane was laid along, is empty across its bearings and was not before
    const onBearing = (items: typeof withRoad) =>
      items.filter(
        (it) =>
          it.layer === 0 &&
          Math.abs((((ringAngleDeg(it.at, LAYOUT_SPACE) - deg + 540) % 360) - 180)) < 12
      ).length
    expect(onBearing(noRoad)).toBeGreaterThan(3)
    // fewer, not none: the outermost layer jitters up to 26px inward, so a tree
    // that drew a large jitter clears a lane laid on the layer's nominal radius.
    // The rule is the per-item test above; this is the shape of its effect.
    expect(onBearing(withRoad)).toBeLessThan(onBearing(noRoad))
  })

  it('both belt clearance rules are measured on the sprite it DRAWS', () => {
    // PAID 2026-07-27, adversarial re-review. The belt samples every rule
    // against the LARGEST sprite in its layer. That is right for a containment
    // question ("would the biggest thing here fit?") and it is NOT conservative
    // for either of the two rules below, so the belt emitted items the audit —
    // and the renderer, and check_on_road — then measured as defects:
    //   4 of 200 hamlet islands had a belt item standing on the coastal
    //   carriageway, and 40 of 11031 belt items shared ground with a building.
    //
    // PREMISE FIRST, because the consequence is only interesting if the two
    // sizes really can disagree in this direction. footprintOnLane is a sparse
    // 4x5 probe grid whose sample points SCALE with the footprint, so a bigger
    // diamond does not probe a superset of a smaller one's points: a narrow lane
    // passes clean between the big probes and is hit square on by the small
    // ones. iso-layout.test.ts already pins the opposite direction (big hits,
    // small misses); this is the one the belt walks into.
    const deg = 270 // due north — outside every gap arc
    const ang = (deg * Math.PI) / 180
    const r = hamlet.coast.edgeAt(ang) - RING_LAYERS[0].inset
    const pts: Point[] = []
    for (let d = -30; d <= 30; d += 2) {
      const a = ang + (d * Math.PI) / 180
      pts.push({
        x: LAYOUT_SPACE.cx + Math.cos(a) * r,
        y: LAYOUT_SPACE.cy + Math.sin(a) * r * 0.92,
      })
    }
    // 18px is not a contrived width: it is what the coastal lane really is at
    // the `dirt_worn` rung, which is the island the defect was measured on.
    const narrow: Lane[] = [{ key: 'treeline', kind: 'coastal', width: 18, runs: [pts] }]
    const field = buildLaneField(narrow)
    const big = { w: 150, h: 150 }
    const small = DEFAULT_FOOTPRINTS.fern_cluster
    let disagree: Point | null = null
    for (const p of pts) {
      for (let dy = 0; dy <= 40 && !disagree; dy += 1) {
        const q = { x: p.x, y: p.y + dy }
        if (footprintOnLane(q, small, field) && !footprintOnLane(q, big, field)) disagree = q
      }
      if (disagree) break
    }
    expect(disagree).not.toBeNull()

    // ...so the belt re-tests the sprite it chose. Mutation: delete the two
    // itemSize lines in ring.ts and this goes RED with one fern_cluster on the
    // lane, on this exact seed and bearing.
    const items = forestRing('acme-corp', ctxOf(hamlet, { lanes: field }))
    expect(items.filter((i) => footprintOnLane(i.at, i.size, field)).map((i) => i.kind)).toEqual([])
    // and a belt that planted nothing would pass the line above while measuring
    // nothing at all
    expect(items.length).toBeGreaterThan(40)
  })

  /**
   * THE BELT DOES NOT PLANT ON THE WHARF — and this arm exists because the
   * composed layout cannot currently prove it either way.
   *
   * HONEST STATE OF THIS RULE, stated rather than implied by a green tick:
   * measured over 240 composed islands (80 seeds x camp/hamlet/village), ZERO
   * belt items land on the deck with the term and zero without it. The term is
   * therefore green at the composed level, and the reason is a coincidence of
   * two unrelated constants — the wharf spans cove.x +/- 360, the reference's
   * south gap runs 58-122 degrees, and the wharf's east end lands at ~58.5
   * degrees, half a degree inside a gap that exists to show the water at the
   * harbour rather than to keep trees off a deck. Nothing links them.
   *
   * So the rule is driven DIRECTLY here instead: a synthetic deck laid across
   * due north, which no gap covers and the belt's outer layers walk straight
   * through. That makes this a live sensor on the RULE even while the composed
   * layout does not reach it — unreached is not unreachable, and "no arm can
   * fail" is the state this port keeps finding defects in.
   *
   * MUTATION (proven RED 2026-07-27): drop `|| ctx.onQuay(x, y)` from ring.ts
   * and 20 belt items stand on the synthetic deck.
   */
  it('drops a belt candidate that lands on the wharf deck', () => {
    const deg = 270 // due north — outside every gap arc
    const ang = (deg * Math.PI) / 180
    const r = hamlet.coast.edgeAt(ang) - RING_LAYERS[0].inset
    const deck: [number, number, number, number] = [
      LAYOUT_SPACE.cx + Math.cos(ang) * r - 260,
      LAYOUT_SPACE.cy + Math.sin(ang) * r * 0.92 - 120,
      LAYOUT_SPACE.cx + Math.cos(ang) * r + 260,
      LAYOUT_SPACE.cy + Math.sin(ang) * r * 0.92 + 120,
    ]
    const onDeck = rectField(deck)
    const without = forestRing('acme-corp', ctxOf(hamlet))
    const on = without.filter((i) => onDeck(i.at.x, i.at.y))
    // PREMISE: the belt really does walk through this rectangle, so the arm
    // below is measuring a rule and not an empty region.
    expect(on.length).toBeGreaterThan(8)

    const with_ = forestRing('acme-corp', ctxOf(hamlet, { onQuay: onDeck }))
    expect(with_.filter((i) => onDeck(i.at.x, i.at.y))).toEqual([])
    // and it dropped them rather than moving them: the belt never nudges
    expect(with_.length).toBeLessThan(without.length)
    expect(with_.length).toBeGreaterThan(without.length - on.length - 6)
  })

  it('nothing the belt plants stands on a lane or on a building — 80 islands', () => {
    // COVERAGE, not a new rule. The composed on-lane arms in iso-layout.test.ts
    // run on two islands; the size-aliasing above fires on about 2% of them and
    // the stacking on about 0.4% of belt items, so two islands cannot see it. A
    // rule is only as true as the population it was measured over.
    //
    // Mutation (both itemSize lines deleted from ring.ts): lane=3, stacked=59.
    const seeds = Array.from({ length: 80 }, (_, i) => `org-${i}`)
    let lane = 0
    let stacked = 0
    const examples: string[] = []
    for (const seed of seeds) {
      for (const state of [HAMLET, VILLAGE]) {
        const l = composeLayout(state, seed, FAST)
        for (const hit of auditLayout(l).onLane) {
          lane++
          if (examples.length < 4) examples.push(`onLane ${seed} ${hit.kind}`)
        }
        // The audit's own stacked arm compares structures to structures only, so
        // belt-on-building has no sensor there. Same function the rule calls.
        const book = l.structures.map((s) => ({ at: s.at, size: s.size }))
        for (const item of l.ring) {
          if (maxGroundOverlap(item.at, item.size, book) > 0.16) {
            stacked++
            if (examples.length < 4) examples.push(`stacked ${seed} ${item.kind}`)
          }
        }
      }
    }
    expect({ lane, stacked, examples }).toEqual({ lane: 0, stacked: 0, examples: [] })
  })

  it('the belt is on land, off the road, out of the water and off the paving', () => {
    for (const seed of SEEDS) {
      const l = composeLayout(VILLAGE, seed, FAST)
      const water = waterField(l.paint)
      const paving = paintField(l.paint, ['plaza', 'crop', 'ploughed'])
      const bad = l.ring.filter(
        (r) => !l.coast.landAt(r.at.x, r.at.y) || water(r.at.x, r.at.y) || paving(r.at.x, r.at.y)
      )
      expect({ seed, bad: bad.map((r) => r.kind) }).toEqual({ seed, bad: [] })
    }
  })

  it('every belt sprite has a real footprint — no silent 96x96 fallback', () => {
    // A typo in a species pool would otherwise place a 96x96 ghost and space
    // the belt against a size nothing draws.
    for (const layer of RING_LAYERS) {
      for (const kind of layer.kinds) {
        expect({ kind, known: kind in DEFAULT_FOOTPRINTS }).toEqual({ kind, known: true })
      }
    }
    expect(RING_LAYERS.flatMap((l) => l.kinds)).toContain('tree_pine')
  })

  /**
   * A PROVENANCE LOCK on the sizes every spacing rule in this library measures
   * against — and it is a change-detector, which is stated here rather than
   * dressed up as a property.
   *
   * WHY IT EXISTS. DEFAULT_FOOTPRINTS claims to be manifest.py's generated size
   * divided by scale_of(). Audited row by row on 2026-07-27, five of fifty rows
   * contradicted that claim, and REVERTING all five left the whole suite green
   * (164 arms): belt separation, ground overlap and lane clearance were all
   * being enforced at the wrong distance with no sensor anywhere. A green
   * mutation is either a redundant rule or a missing sensor, and this one was
   * squarely the second.
   *
   * WHAT IT CANNOT DO, said plainly: manifest.py lives in another repository and
   * cannot be read from a test here, so this arm cannot notice the SPRITE
   * changing — only the table drifting from what was measured off it. The
   * derivation is written into each line so the next edit has to re-derive
   * rather than guess, and the real fix is the renderer passing the shipped
   * pack's own sizes through `opts.footprintOf`, which is what the table's own
   * docstring already says it is for.
   */
  it('carries the sizes manifest.py actually generates, for the five that drifted', () => {
    // kind -> [generated w, generated h, scale_of() divisor]
    const derivation: Record<string, [number, number, number]> = {
      tree_birch: [125, 165, 1], // NATURE, not in HALF
      tree_willow: [155, 155, 1], // NATURE, not in HALF
      rock_cluster: [105, 95, 2], // in HALF
      fallen_log: [120, 95, 2], // in HALF
      mushrooms: [90, 90, 2], // in HALF
      // three that were already right, so the arm is not only about the drift
      tree_pine: [130, 175, 1],
      tree_oak_small: [110, 110, 2],
      bush_round: [95, 95, 2],
    }
    for (const [kind, [w, h, div]] of Object.entries(derivation)) {
      expect({ kind, size: DEFAULT_FOOTPRINTS[kind] }).toEqual({
        kind,
        size: { w: Math.floor(w / div), h: Math.floor(h / div) },
      })
    }
  })

  it('the belt is MORPHOLOGY: a camp has one too, and a larger one', () => {
    // An island has a treeline whether or not anyone has landed on it — the same
    // argument that keeps the pond at camp. And with the village-only keep-out
    // discs absent, the belt is free to close over ground a hamlet reserves.
    expect(camp.ring.length).toBeGreaterThan(60)
    expect(camp.ring.length).toBeGreaterThan(hamlet.ring.length)
  })

  it('the belt is seeded: same seed same belt, different seed different belt', () => {
    const a = composeLayout(HAMLET, 'acme-corp', FAST).ring
    const b = composeLayout(HAMLET, 'acme-corp', FAST).ring
    const c = composeLayout(HAMLET, 'zeta', FAST).ring
    expect(JSON.stringify(a)).toBe(JSON.stringify(b))
    expect(JSON.stringify(a)).not.toBe(JSON.stringify(c))
  })

  it('the sublayer insets are what put the layers at different depths', () => {
    // negative twin for the "stacks inward" arm: flatten every inset to one
    // value and the depth separation disappears.
    const flat = forestRing(
      'acme-corp',
      ctxOf(hamlet, { layers: RING_LAYERS.map((l) => ({ ...l, inset: 22 })) })
    )
    const meanOf = (items: typeof flat, layer: number) => {
      const xs = items.filter((r) => r.layer === layer)
      return xs.reduce((s, r) => s + radialFraction(hamlet, r.at), 0) / Math.max(1, xs.length)
    }
    const spread = Math.abs(meanOf(flat, 0) - meanOf(flat, 3))
    const real = forestRing('acme-corp', ctxOf(hamlet))
    expect(spread).toBeLessThan(Math.abs(meanOf(real, 0) - meanOf(real, 3)))
  })
})

// ── the ground passes ──────────────────────────────────────────────────────

describe('the ground is broken up, not one flat sheet', () => {
  it('the broken meadow and the value mottle are both painted', () => {
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      const kinds = l.paint.map((r) => r.kind)
      expect({ seed, meadow: kinds.includes('meadow_dark') }).toEqual({ seed, meadow: true })
      expect({ seed, mottle: kinds.includes('mottle') }).toEqual({ seed, mottle: true })
      expect(l.paint.filter((r) => r.kind === 'meadow_dark')[0].blobs.length).toBeGreaterThan(8)
    }
  })

  it('every mottle region names a tone, and the tones are the reference three', () => {
    const regions = hamlet.paint.filter((r) => r.kind === 'mottle')
    expect(regions.length).toBeGreaterThan(1)
    const tones = regions.map((r) => r.tone).sort()
    expect(new Set(tones).size).toBe(tones.length) // one region per tone
    for (const r of regions) {
      expect(r.tone).toBeGreaterThanOrEqual(0)
      expect(r.tone!).toBeLessThan(MOTTLE_TONES.length)
      for (const b of r.blobs) expect(b.w).toBeCloseTo(MOTTLE_TONES[r.tone!][3] / 255, 6)
    }
  })

  it('the meadow patches carry the reference’s own per-patch strength', () => {
    // compose.py:148 fills each patch at 110-210 of 255 — the patches are not a
    // solid second grass, they are a varying wash, and a renderer that got a
    // bare ellipse would paint a hard-edged blotch.
    const region = hamlet.paint.find((r) => r.kind === 'meadow_dark')!
    for (const b of region.blobs) {
      expect(b.w).toBeGreaterThanOrEqual(110 / 255)
      expect(b.w).toBeLessThanOrEqual(210 / 255)
    }
    expect(new Set(region.blobs.map((b) => b.w)).size).toBeGreaterThan(3)
  })

  it('SHADING IS NOT SURFACE — planting grows on the meadow patches', () => {
    // The class distinction in PaintKind, as a property. Adding meadow_dark or
    // mottle to the planting exclusions would carve bald patches at random
    // across the island; measured with 'meadow_dark' added to the onPaving set,
    // planting inside patches drops to 0 and the total falls by a fifth.
    const inMeadow = paintField(hamlet.paint, ['meadow_dark'])
    const growing = [...hamlet.ring, ...hamlet.scatter].filter((s) => inMeadow(s.at.x, s.at.y))
    expect(growing.length).toBeGreaterThan(3)
    // and the exclusion set really does exclude, so the arm above is about the
    // KIND and not about the mechanism being dead
    const paving = paintField(hamlet.paint, ['plaza', 'crop', 'ploughed'])
    const onPaving = [...hamlet.ring, ...hamlet.scatter].filter((s) => paving(s.at.x, s.at.y))
    expect(onPaving).toEqual([])
  })
})

// ── the pond, its outflow and its bank ─────────────────────────────────────

describe('the pond has an outflow, a bank and its own plants', () => {
  it('an island with no room for a pond gets no pond, no stream and no bank', () => {
    // the honest absence case, asserted rather than assumed: (612,1086) is open
    // sea on acme-corp, and morphology the island does not have is not drawn
    expect(hamlet.coast.landAt(POND.x, POND.y)).toBe(false)
    for (const kind of ['pond', 'stream', 'pond_bank']) {
      expect({ kind, drawn: hamlet.paint.some((r) => r.kind === kind) }).toEqual({
        kind,
        drawn: false,
      })
    }
    expect(hamlet.scatter.filter((s) => s.kind === 'lilypads')).toEqual([])
  })

  it('the stream runs from the pond to the west coast', () => {
    const stream = pondy.paint.find((r) => r.kind === 'stream')
    expect(stream).toBeDefined()
    const west = Math.min(...stream!.blobs.map((b) => b.c.x))
    // the outflow's last waypoint is 282px west of the pond; the clip may stop
    // it short of the shore but it must leave the pond's own footprint
    expect(west).toBeLessThan(POND.x - 120)
    expect(OUTFLOW[OUTFLOW.length - 1].x).toBeLessThan(POND.x)
  })

  it('the water reaches OUTSIDE the pond’s keep-out disc', () => {
    // NAMED FOR WHAT IT MEASURES. It was first written as "the stream is why the
    // water term is not redundant" and that title was false: deleting the water
    // term from free() leaves all 164 arms green (mutation run 2026-07-27), so
    // the term in index.ts is still quiet and the docstring there now says so.
    // What IS true, and what this arm holds, is the geometric half — the water
    // is no longer contained by the disc that used to cover it, which is why the
    // ring's own water term is live even though free()'s is not.
    //
    // Measured over the five seeds: acme-corp has no pond at all, lantern's
    // outflow is clipped after 9 blobs and stays inside, and harbour /
    // captains-cabinet / zeta reach outside with 19 / 116 / 324 rim points and
    // 0 / 7 / 20 whole blobs. So the claim is stated as a count of ISLANDS,
    // which is what the seed space actually supports.
    const outsideOn = SEEDS.filter((seed) => {
      const l = composeLayout(HAMLET, seed, FAST)
      const water = l.paint
        .filter((r) => r.kind === 'pond' || r.kind === 'stream')
        .flatMap((r) => r.blobs)
      const free = (x: number, y: number) =>
        !l.districts.some((d) => (x - d.at.x) ** 2 + ((y - d.at.y) * 1.35) ** 2 < d.r * d.r)
      return water.some((b) => {
        if (free(b.c.x, b.c.y)) return true
        for (let i = 0; i < 16; i++) {
          const a = (i * Math.PI * 2) / 16
          if (free(b.c.x + Math.cos(a) * b.rx, b.c.y + Math.sin(a) * b.ry)) return true
        }
        return false
      })
    })
    expect(outsideOn.length).toBeGreaterThanOrEqual(2)
    // ...and nothing but a lilypad is standing in any of it
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      const water = waterField(l.paint)
      const wet = [...l.ring, ...l.scatter].filter(
        (s) => s.kind !== 'lilypads' && water(s.at.x, s.at.y)
      )
      expect({ seed, wet: wet.map((s) => s.kind) }).toEqual({ seed, wet: [] })
    }
  })

  it('the masks are clipped at the PRODUCTION sampling step too', () => {
    // The blob-extent arm in iso-layout.test.ts runs at step 8. The coastline
    // that ships samples every 2px, where a fixed 5px probe is COARSER than the
    // mask it is reading — the exact shape of "the test environment guarantees
    // something production does not". Measured: with the probe pinned at 5
    // instead of following the raster, this arm is the only one that turns red.
    const l = composeLayout(HAMLET, PONDY, { coastline: { step: 2 } })
    expect(l.paint.map((r) => r.kind)).toContain('stream')
    for (const region of l.paint) {
      for (const b of region.blobs) {
        for (let i = 0; i < 720; i++) {
          const a = (i * Math.PI * 2) / 720
          const x = b.c.x + Math.cos(a) * b.rx
          const y = b.c.y + Math.sin(a) * b.ry
          expect({ kind: region.kind, land: l.coast.landAt(x, y) }).toEqual({
            kind: region.kind,
            land: true,
          })
        }
      }
    }
  }, 120_000)

  it('the bank rings the water and is clipped to land like everything else', () => {
    const bank = pondy.paint.find((r) => r.kind === 'pond_bank')
    expect(bank).toBeDefined()
    for (const b of bank!.blobs) {
      expect(pondy.coast.landAt(b.c.x, b.c.y)).toBe(true)
    }
    // the bank is where the water is: every bank blob centre is a water blob
    // centre, because the ring is the water grown outward
    const water = pondy.paint
      .filter((r) => r.kind === 'pond' || r.kind === 'stream')
      .flatMap((r) => r.blobs)
    for (const b of bank!.blobs) {
      expect(water.some((w) => w.c.x === b.c.x && w.c.y === b.c.y)).toBe(true)
    }
  })

  it('reeds stand at a waterline — the sea’s or the pond’s, never in open meadow', () => {
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      // the rule's own function, per the audit doctrine in index.ts: a second
      // notion of where the bank is would be a second place to be wrong
      const onBank = grownField(l.paint, ['pond', 'stream'], REED_MARGIN)
      const stray = l.scatter.filter(
        (s) => s.kind === 'reeds' && !l.coast.inShoreBand(s.at.x, s.at.y) && !onBank(s.at.x, s.at.y)
      )
      expect({ seed, stray: stray.map((s) => `${s.at.x | 0},${s.at.y | 0}`) }).toEqual({
        seed,
        stray: [],
      })
    }
  })

  it('the bank pass really plants — some reed is on the bank, not just the shore', () => {
    // liveness twin for the arm above, which a bank pass that emitted nothing
    // would also pass
    const found = SEEDS.some((seed) => {
      const l = composeLayout(HAMLET, seed, FAST)
      const onBank = grownField(l.paint, ['pond', 'stream'], REED_MARGIN)
      return l.scatter.some((s) => s.kind === 'reeds' && onBank(s.at.x, s.at.y))
    })
    expect(found).toBe(true)
  })

  it('lilypads float, and only on water that was actually painted', () => {
    let total = 0
    for (const seed of SEEDS) {
      const l = composeLayout(HAMLET, seed, FAST)
      const water = waterField(l.paint)
      const pads = l.scatter.filter((s) => s.kind === 'lilypads')
      total += pads.length
      for (const p of pads) {
        expect({ seed, floating: water(p.at.x, p.at.y) }).toEqual({ seed, floating: true })
      }
    }
    expect(total).toBeGreaterThan(0)
    // and the pads are on the pond ISLANDS only — the no-pond case is asserted
    // by its own arm above, on the island that really has no pond
  })
})

// ── the officer row ────────────────────────────────────────────────────────

describe('per-officer house variety', () => {
  it('a full row draws several different houses, not one sprite six times', () => {
    let distinct = 0
    for (const seed of WIDE_SEEDS) {
      const l = composeLayout(VILLAGE, seed, FAST)
      const kinds = l.structures.filter((s) => s.role === 'officer_dwelling').map((s) => s.kind)
      expect(kinds.length).toBe(6)
      distinct += new Set(kinds).size
    }
    const mean = distinct / WIDE_SEEDS.length
    // six independent draws from six kinds average 3.99 distinct; ONE sprite
    // for every lot — which is what this port did before — averages exactly 1.
    expect(mean).toBeGreaterThan(3)
  })

  it('every house is a real dwelling sprite, and its ROLE is still traceable', () => {
    const row = hamlet.structures.filter((s) => s.role === 'officer_dwelling')
    expect(row.length).toBe(3)
    for (const s of row) {
      expect({ kind: s.kind, known: HOUSE_KINDS.includes(s.kind) }).toEqual({
        kind: s.kind,
        known: true,
      })
      expect(s.kind in DEFAULT_FOOTPRINTS).toBe(true)
    }
  })

  it('a lot keeps its house when the row GROWS — the choice is the lot’s', () => {
    // `HOUSES[i % 6]` would also pass this; `fnv1a(centre)` would not, because
    // the centres shift as the separation relaxation runs against more lots.
    for (const seed of ['acme-corp', 'zeta']) {
      const three = composeLayout({ ...VILLAGE, counts: { officer_dwellings: 3 } }, seed, FAST)
      const six = composeLayout(VILLAGE, seed, FAST)
      const kindsOf = (l: Layout) =>
        l.structures.filter((s) => s.role === 'officer_dwelling').map((s) => s.kind)
      expect(kindsOf(six).slice(0, 3)).toEqual(kindsOf(three))
    }
  })

  it('the row is the ORG’s, not a fixed table — two seeds differ', () => {
    const a = composeLayout(VILLAGE, 'acme-corp', FAST)
    const b = composeLayout(VILLAGE, 'zeta', FAST)
    const kindsOf = (l: Layout) =>
      l.structures.filter((s) => s.role === 'officer_dwelling').map((s) => s.kind)
    expect(kindsOf(a)).not.toEqual(kindsOf(b))
  })

  it('ERA GATES IT: a camp pitches tents, a hamlet builds houses', () => {
    const campRow = camp.structures.filter((s) => s.role === 'officer_dwelling')
    expect(campRow.length).toBe(1)
    for (const s of campRow) expect(s.kind).toBe(CAMP_DWELLING)
    for (const s of hamlet.structures.filter((s) => s.role === 'officer_dwelling')) {
      expect(s.kind).not.toBe(CAMP_DWELLING)
    }
  })

  it('nothing is drawn that no rule justifies — every kind has a footprint', () => {
    // the port's own check_state_traceable edge: a sprite name nothing knows
    // the size of is a sprite the clearance rules measured wrong
    for (const seed of SEEDS) {
      const l = composeLayout(VILLAGE, seed, FAST)
      for (const s of [...l.structures, ...l.ring, ...l.scatter]) {
        expect({ seed, kind: s.kind, known: s.kind in DEFAULT_FOOTPRINTS }).toEqual({
          seed,
          kind: s.kind,
          known: true,
        })
      }
    }
  })
})
