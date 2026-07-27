/**
 * HARBOUR + LIGHTHOUSE tests — properties, not smoke.
 *
 * Every arm names the defect it exists to catch, and every arm was proven able
 * to FAIL by disabling the rule it guards (the mutation table is in the review
 * artifact for this branch). An arm that cannot fail is a disabled sensor
 * wearing a green tick, which is the defect class this whole directory was
 * re-reviewed for.
 *
 * A SEPARATE FILE from iso-layout.test.ts on purpose: this branch had two waves
 * in one worktree, and a shared test file is the one surface where two writers
 * silently drop each other's arms.
 */
import { describe, expect, it } from 'vitest'
import {
  auditLayout,
  buildCoastline,
  composeLayout,
  type Coastline,
  DEFAULT_FOOTPRINTS,
  LAYOUT_SPACE,
  type Layout,
  type LayoutState,
  type Point,
} from './index'
import {
  buildHarbour,
  CRANE_SPACING,
  DOCK_KIT,
  jettyLength,
  lighthouseSite,
  quayDepth,
  shoreAt,
  SHORE_LIFT,
  shoreLine,
  type Cove,
  type Harbour,
  type Rect,
} from './harbour'

/** Coarse coastline: the shore polyline is the subject, not its fidelity. */
const FAST = { coastline: { step: 8 } }

/** A full working port: every count non-zero, so every rule is in play. */
const PORT: LayoutState = {
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
    quay: 'stone_quay_4',
    lighthouse: 'tower_full',
    lighthouse_lamp: 'lit',
    harbormaster_hut: 'hut',
  },
  counts: {
    officer_dwellings: 6,
    field_plots: 4,
    berths: 6,
    cargo_stacks: 2,
    warehouse: 2,
    packs_inherited: 5,
  },
}

const CAMP: LayoutState = {
  era: 'camp',
  road: 'dirt_path',
  // A camp whose quay rung is the TOP of the ladder, deliberately: the era gate
  // and the rung measurement have to be separable, and a state where they agree
  // cannot tell them apart.
  stages: { great_house: 'camp_log_cabin', quay: 'stone_quay_5', lighthouse: 'dark_cairn' },
  counts: { officer_dwellings: 1, berths: 2, cargo_stacks: 1, warehouse: 1, packs_inherited: 5 },
}

const SEEDS = ['acme-corp', 'harbour', 'lantern', 'captains-cabinet', 'zeta']
const WIDE = Array.from({ length: 25 }, (_, i) => `org-${i}`)

function withState(base: LayoutState, patch: Partial<LayoutState>): LayoutState {
  return {
    ...base,
    ...patch,
    stages: { ...base.stages, ...patch.stages },
    counts: { ...base.counts, ...patch.counts },
  }
}

function harbourOf(state: LayoutState, seed = 'acme-corp'): Harbour {
  const h = composeLayout(state, seed, FAST).harbour
  expect(h).not.toBeNull()
  return h as Harbour
}

const inRect = (r: Rect, p: Point) => p.x >= r[0] && p.x <= r[2] && p.y >= r[1] && p.y <= r[3]

/**
 * The pier, ASSERTED to exist rather than non-null-asserted away.
 *
 * `jetty` became nullable when the harbour stopped building a pier out of an
 * unmeasured quay ladder, and every fixture below that reaches for it does have
 * a quay rung — so the honest form of `h.jetty!` is an assertion that fails
 * loudly if the rung ever stops producing one. A bare `!` would turn that
 * regression into a null-dereference inside whichever arm hit it first.
 */
function pierOf(h: Harbour) {
  expect(h.jetty).not.toBeNull()
  return h.jetty as NonNullable<Harbour['jetty']>
}

/**
 * A HAND-BUILT ISLAND — land from `shoreOf(x) - 600` down to `shoreOf(x)`, open
 * water below it, and NO LAND AT ALL in a column where `shoreOf` returns null.
 *
 * It exists for the degenerate arms, which no real seed reaches: `buildHarbour`
 * has already returned null before a cove is ruined enough to strip a column,
 * so the branch that refuses to root a pier there would never be executed by a
 * seeded fixture. A rule with no reachable case is a comment until something
 * asks it.
 *
 * EVERY METHOD buildHarbour IS NOT SUPPOSED TO NEED THROWS. A stub that returns
 * a plausible value for an unasked question is how a fixture starts asserting
 * that the degenerate value is valid — so this one has no raster and no radial
 * geometry, and says so by failing loudly if either is ever consulted.
 */
function fakeCoast(cove: Cove, shoreOf: (x: number) => number | null): Coastline {
  const nope =
    (name: string) =>
    (): never => {
      throw new Error(`fakeCoast has no ${name}: this fixture answers land questions only`)
    }
  const landAt = (x: number, y: number): boolean => {
    const s = shoreOf(x)
    return s !== null && y <= s && y > s - 600
  }
  return {
    space: LAYOUT_SPACE,
    seed: 0,
    cove,
    step: 1,
    mw: 0,
    mh: 0,
    land: new Uint8Array(0),
    beach: new Uint8Array(0),
    landAt,
    beachAt: nope('beach mask'),
    groundAt: nope('groundAt'),
    landEdge: nope('landEdge'),
    edgeAt: nope('edgeAt'),
    shoreY(x, yFrom, yTo) {
      let last: number | null = null
      for (let y = Math.floor(yFrom); y < Math.floor(yTo); y++) if (landAt(x, y)) last = y
      return last
    },
    inShoreBand: nope('inShoreBand'),
    isInner: nope('isInner'),
  }
}

// ── the waterline: nothing floats ──────────────────────────────────────────

describe('the shore polyline', () => {
  /**
   * compose.py:1119-1120 records the defect: "the Captain's note on v12 was
   * that the dock sat out in open sea." Every deck point is on land at its own
   * column, and the water starts immediately below it — which is the definition
   * of a waterline and the one thing a wharf must be pinned to.
   *
   * The margin below is one raster cell (step 8 here): shoreY walks in whole
   * pixels over a mask quantised to `step`, so the first genuinely-wet row can
   * be up to a cell lower. Asserting at y+1 would be asserting the raster's
   * resolution, not the rule.
   */
  it('sits on land, with open water immediately below it', () => {
    for (const seed of SEEDS) {
      const l = composeLayout(PORT, seed, FAST)
      const h = l.harbour as Harbour
      expect(h.shore.length).toBeGreaterThan(3)
      for (const p of h.shore) {
        expect(l.coast.landAt(p.x, p.y)).toBe(true)
        expect(l.coast.landAt(p.x, p.y + 8 + 4)).toBe(false)
      }
    }
  })

  /**
   * A COLUMN WITH NO LAND CONTRIBUTES NOTHING. The alternative — substituting a
   * y so the deck stays rectangular — is precisely how a wharf ends up in open
   * sea, so the polyline is allowed to be short and the callers all cope.
   * Probed past the island's own half-width, where most columns are water.
   */
  it('drops columns that have no land rather than guessing a waterline', () => {
    const coast = buildCoastline('acme-corp', LAYOUT_SPACE, { step: 8 })
    const cove = coast.cove as Cove
    const wide = shoreLine(coast, cove, 1400, 12)
    const columns = Math.floor((2 * 1400) / 12) + 1
    expect(wide.length).toBeLessThan(columns)
    expect(wide.length).toBeGreaterThan(3)
    for (const p of wide) expect(coast.landAt(p.x, p.y)).toBe(true)
  })
})

// ── the wharf ──────────────────────────────────────────────────────────────

describe('the wharf', () => {
  it('is the kept span of the real shore, every point of it on land', () => {
    for (const seed of SEEDS) {
      const l = composeLayout(PORT, seed, FAST)
      const h = l.harbour as Harbour
      const w = h.wharf
      expect(w).not.toBeNull()
      if (!w) continue
      expect(w.depth).toBe(50) // stone_quay_4
      for (const p of w.shore) {
        expect(h.shore).toContainEqual(p)
        expect(l.coast.landAt(p.x, p.y)).toBe(true)
        // the rect the checks read must cover the deck it describes
        expect(inRect(w.rect, p)).toBe(true)
      }
      // and it reaches DOWN into the water by at least the deck's depth
      const lowest = Math.max(...w.shore.map((p) => p.y))
      expect(w.rect[3]).toBeGreaterThanOrEqual(lowest + w.depth)
    }
  })

  /**
   * ERA GATES CONTENT. A camp has a few planks over the water, not a wharf —
   * and this state proves the gate is the ERA and not the rung, because the
   * rung is the top of the quay ladder in both cases.
   */
  it('does not exist at camp, whatever the quay rung says', () => {
    expect(quayDepth('camp', 'stone_quay_5')).toBe(0)
    expect(quayDepth('hamlet', 'stone_quay_5')).toBe(54)
    for (const seed of SEEDS) {
      expect(harbourOf(CAMP, seed).wharf).toBeNull()
      expect(harbourOf(withState(CAMP, { era: 'hamlet' }), seed).wharf).not.toBeNull()
    }
  })

  /**
   * AND ERA MAY NOT HIDE THE COUNT. The rung still measures at camp — through
   * the jetty, which is the thing a camp does have. A gate that swallowed both
   * would make a camp that has shipped for a year indistinguishable from one
   * hatched this morning.
   */
  it('leaves the rung visible at camp through the jetty length', () => {
    expect(jettyLength('rowboat_jetty')).toBe(96)
    expect(jettyLength('timber_jetty')).toBe(150)
    expect(jettyLength('stone_quay_5')).toBe(230)
    const fresh = harbourOf(withState(CAMP, { stages: { quay: 'rowboat_jetty' } }))
    const seasoned = harbourOf(CAMP)
    expect(pierOf(fresh).length).toBe(96)
    expect(pierOf(seasoned).length).toBe(230)
    expect(seasoned.wharf).toBeNull()
  })

  it('deepens with the quay rung and treats an unknown rung as a full wharf', () => {
    const depths = (['timber_jetty', 'stone_quay_2', 'stone_quay_3', 'stone_quay_4'] as const).map(
      (rung) => harbourOf(withState(PORT, { stages: { quay: rung } })).wharf?.depth
    )
    expect(depths).toEqual([30, 40, 46, 50])
    expect(harbourOf(withState(PORT, { stages: { quay: 'rowboat_jetty' } })).wharf).toBeNull()
    // a sixth stone rung the ladder grows later: more quay, never none
    expect(harbourOf(withState(PORT, { stages: { quay: 'stone_quay_6' } })).wharf?.depth).toBe(54)
  })

  /**
   * NO RUNG, NO QUAY — the state-traceability arm.
   *
   * compose.py:1134 reads `WS.stage("quay") or "rowboat_jetty"`, so an org whose
   * quay ladder was never measured gets the ladder's FIRST RUNG built out of the
   * absence: a 96px finger pier standing in the water with no rule behind it,
   * which is precisely what check_state_traceable exists to catch. This port
   * diverges, on the same ground it already refused compose.py:1188's
   * `max(1, 1 + cargo*3)` crate.
   *
   * BOTH DIRECTIONS ARE ASSERTED, because a gate that answers "nothing" to
   * everything is not a gate: a rung that IS present still builds its pier, and
   * `rowboat_jetty` — the ladder's real first rung, which a freshly hatched org
   * genuinely sits on — is the case that must keep its 96px.
   *
   * MUTATIONS (both proven RED, 2026-07-27):
   *   - `jettyLength` without its emptyRung guard  -> jettyLength(undefined)
   *     is 96, jettyLength('bare_ground') is 230, and every no-rung harbour
   *     grows a pier again.
   *   - `quayDepth` without its emptyRung guard    -> quayDepth('hamlet',
   *     'bare_ground') is 54, the DEEPEST wharf in the table, because
   *     `bare_ground` is not in QUAY_DEPTH and the unknown-rung rule read an
   *     unbuilt quay as a rung past the top of the ladder.
   */
  it('builds neither deck nor pier from a quay rung that does not exist', () => {
    // the ladder is unmeasured: no key at all, or an explicit null
    for (const rung of [undefined, null]) {
      expect(jettyLength(rung)).toBe(0)
      expect(quayDepth('hamlet', rung)).toBe(0)
      expect(quayDepth('camp', rung)).toBe(0)
    }
    // the ladder exists but has built nothing yet (worldstate.py present())
    for (const rung of ['none', 'bare_ground', 'dark']) {
      expect(jettyLength(rung)).toBe(0)
      expect(quayDepth('hamlet', rung)).toBe(0)
    }
    // ...and a rung that IS a rung still builds, at both ends of the ladder
    expect(jettyLength('rowboat_jetty')).toBe(96)
    expect(quayDepth('hamlet', 'rowboat_jetty')).toBe(0) // planks, not a deck
    expect(jettyLength('stone_quay_6')).toBe(230)
    expect(quayDepth('hamlet', 'stone_quay_6')).toBe(54)

    const noLadder = { ...PORT, stages: { ...PORT.stages, quay: undefined } }
    for (const seed of SEEDS) {
      const h = harbourOf(noLadder, seed)
      expect(h.jetty).toBeNull()
      expect(h.wharf).toBeNull()
      // and the harbour is still a harbour: the things with their OWN ladders
      // survive, because the quay's absence is not their absence
      expect(h.moorings.length).toBe(6)
      expect(h.warehouseSites.length).toBe(2)
      expect(h.harbourmasterSite).not.toBeNull()
      expect(h.shore.length).toBeGreaterThan(3)
      // nothing it emits leaves the envelope just because the pier is gone
      expect(auditLayout(composeLayout(noLadder, seed, FAST)).outsideHarbour).toEqual([])
    }
    // the pier IS there on the same island the moment the rung is
    expect(harbourOf(PORT).jetty).not.toBeNull()
  })

  /**
   * THE ENVELOPE MUST REACH THE DEEPEST THING IN THE HARBOUR, and that is not
   * always the pier.
   *
   * Found 2026-07-27: `reach` was the jetty's alone, while the mooring rows walk
   * 52px further out per PAIR of open outcome windows. Measured over 20 seeds at
   * the top quay rung, `berths: 16` put 6 mooring posts outside the harbour's own
   * declared envelope and `berths: 24` put 150 — auditLayout reporting a defect
   * that belonged to the envelope, not to the moorings. It survived because every
   * fixture in this file stopped at 6 berths; `count()` admits up to 64.
   *
   * MUTATION (proven RED): `const reach = pierReach` — 6 posts out at 16 berths,
   * 150 at 24, and 342 with no quay rung at all.
   */
  it('declares an envelope that reaches its own mooring rows, at any berth count', () => {
    for (const quay of ['stone_quay_4', undefined]) {
      for (const berths of [2, 6, 16, 24, 64]) {
        const st = { ...PORT, stages: { ...PORT.stages, quay }, counts: { ...PORT.counts, berths } }
        for (const seed of SEEDS) {
          const l = composeLayout(st, seed, FAST)
          const h = l.harbour as Harbour
          expect(h.moorings.length).toBe(berths)
          expect(auditLayout(l).outsideHarbour).toEqual([])
        }
      }
    }
  })

  /**
   * compose.py:1138 — a timber jetty decks only the middle 30% of the cove.
   * The rect follows the DECK, not the whole shore: the reference declares the
   * full span there, which exempts bare shore from check_on_road for no reason.
   */
  it('decks only the middle of the cove at the timber rung', () => {
    const full = harbourOf(PORT)
    const timber = harbourOf(withState(PORT, { stages: { quay: 'timber_jetty' } }))
    expect(timber.wharf).not.toBeNull()
    if (!timber.wharf || !full.wharf) return
    const timberSpan = timber.wharf.rect[2] - timber.wharf.rect[0]
    const fullSpan = full.wharf.rect[2] - full.wharf.rect[0]
    expect(timberSpan).toBeLessThan(fullSpan * 0.45)
    expect(timber.wharf.shore.length).toBeLessThan(full.wharf.shore.length * 0.45)
    // and it is still the MIDDLE — centred on the cove, not on one end
    const mid = (timber.wharf.rect[0] + timber.wharf.rect[2]) / 2
    expect(Math.abs(mid - timber.cove.x)).toBeLessThan(40)
  })
})

// ── the jetty and its moorings ─────────────────────────────────────────────

describe('the finger jetty', () => {
  /**
   * A PIER IS ATTACHED TO A SHORE — the arm the Captain's eye had to supply on
   * 2026-07-27, when the first rendered frame from this module showed a timber
   * jetty standing in open water with a strip of sea between it and the beach.
   *
   * The port carried compose.py:1148's `js + 52`, which roots the pier 52px
   * BELOW its column's waterline. On the offline island a stone wharf covered
   * that gap; here it was measured across 80 seeds at three rungs and both
   * eras — 480 of 480 rooted out on the water with no deck under them, and the
   * deepest wharf in the ladder still left the root 6px clear of its own front
   * edge. Every numeric arm in this file was green throughout.
   *
   * So the rule is now stated as the eye sees it, at BOTH ERAS, because the era
   * that shows it worst is the one that decks nothing:
   *   - the root is on LAND, and so is the square end-cap the renderer draws
   *     back along the pier's own axis (engine-canvas strokes at -> end with
   *     `cap: 'square'`, so the planks reach width/2 past the root);
   *   - the far end is in WATER, which is what makes it a pier and not a path.
   */
  it('roots on land and ends in open water, at every era and every rung', () => {
    for (const seed of [...SEEDS, ...WIDE]) {
      for (const state of [PORT, CAMP, withState(CAMP, { stages: { quay: 'rowboat_jetty' } })]) {
        const l = composeLayout(state, seed, FAST)
        const h = l.harbour as Harbour
        const j = pierOf(h)
        expect(l.coast.landAt(j.at.x, j.at.y)).toBe(true)
        // the drawn cap, half a pier-width back along the axis, is on land too:
        // a root that merely touches the waterline still reads as detached.
        const dx = j.end.x - j.at.x
        const dy = j.end.y - j.at.y
        const run = Math.hypot(dx, dy)
        expect(
          l.coast.landAt(j.at.x - (dx / run) * (j.width / 2), j.at.y - (dy / run) * (j.width / 2))
        ).toBe(true)
        // and it walks out into water, along the iso angle
        expect(l.coast.landAt(j.end.x, j.end.y)).toBe(false)
        expect(j.end.y).toBeGreaterThan(j.at.y)
        expect(j.end.x).toBeGreaterThan(j.at.x)
      }
    }
  })

  /**
   * ITS ROOT FOLLOWS THE WATERLINE, and this is the arm that says so rather
   * than the one above — which stayed GREEN when the root was taken from the
   * cove's centre instead of the jetty's own column (mutation MH4). The
   * difference only shows in how the number RESPONDS to the island.
   *
   * So: the offset from the root's own column is the same on every island — the
   * deck's own SHORE_LIFT, on the land side of the waterline — while the
   * absolute y moves with the shore. A root read from a constant inverts both:
   * same y everywhere, offset all over the place, and no single-island
   * assertion can tell them apart.
   *
   * The SIGN is the load-bearing half of it now. `-4` and `+52` are both fixed
   * offsets from the right column, and the suite that asserted only "fixed"
   * held the floating pier in place for four adversarial rounds.
   */
  it('roots at a fixed offset from ITS column, on the land side of it', () => {
    const offsets: number[] = []
    const absolutes: number[] = []
    for (const seed of [...SEEDS, ...WIDE]) {
      const l = composeLayout(PORT, seed, FAST)
      const h = l.harbour as Harbour
      const j = pierOf(h)
      const sy = shoreAt(l.coast, h.cove, j.at.x) as number
      offsets.push(j.at.y - sy)
      absolutes.push(j.at.y)
    }
    expect(new Set(offsets).size).toBe(1)
    expect(offsets[0]).toBe(-SHORE_LIFT)
    expect(offsets[0]).toBeLessThan(0)
    expect(Math.max(...absolutes) - Math.min(...absolutes)).toBeGreaterThan(40)
  })

  /**
   * NO SHORE, NO PIER — the degenerate end of the rule above.
   *
   * A missing pier is honest and a floating one is not, so a column with no land
   * emits nothing rather than falling back to a guessed y (the reference's
   * `?? CVY-140`, which this module carried until the same date). The things
   * that FLOAT are not deleted with it: a mooring is an open outcome window and
   * a count may not be lost to a geometric accident in one column.
   *
   * It runs on a HAND-BUILT island because no real seed reaches this branch —
   * buildHarbour has already returned null before a cove is that ruined, which
   * is exactly why the branch needs a fixture: a rule with no reachable case is
   * a comment until something asks it. The stub throws on every method
   * buildHarbour is not supposed to need, so it cannot answer a question it was
   * never given an answer for.
   */
  it('refuses to root a pier in a column with no land, and keeps what floats', () => {
    const cove: Cove = { x: 1200, y: 1430, r: 300 }
    const flatY = cove.y - 40
    const inputs = {
      era: 'hamlet' as const,
      quay: 'stone_quay_4',
      berths: 4,
      cargo: 1,
      boat: true,
      sizeOf: (k: string) => DEFAULT_FOOTPRINTS[k] ?? { w: 96, h: 96 },
    }

    // the pier's column (cove.x + 104) is open water; every other column is land
    const notched = buildHarbour(
      fakeCoast(cove, (x) => (x > cove.x + 60 && x < cove.x + 150 ? null : flatY)),
      cove,
      inputs
    ) as Harbour
    expect(notched).not.toBeNull()
    expect(notched.jetty).toBeNull()
    expect(notched.moorings.length).toBe(4)
    // hung off a MEASURED waterline from a neighbouring column, not an invented
    // one: the reference's fallback would have put them 140px ABOVE the cove's
    // centre, which is 100px inland of this shore.
    for (const m of notched.moorings) expect(m.y).toBeGreaterThan(flatY)
    expect(notched.items.some((i) => i.kind === 'harbor_boat')).toBe(true)

    // the same island WITH land in that column does build one — otherwise the
    // arm is measuring the fixture rather than the rule
    const whole = buildHarbour(fakeCoast(cove, () => flatY), cove, inputs) as Harbour
    expect(whole.jetty).not.toBeNull()
    expect(whole.jetty?.at.y).toBe(flatY - SHORE_LIFT)
    expect(whole.jetty?.end.y).toBeGreaterThan(flatY)
  })
})

describe('the moorings', () => {
  /** ONE PER OPEN OUTCOME WINDOW — a real count, never a decorative row. */
  it('are exactly one per open outcome window', () => {
    for (const berths of [0, 1, 2, 3, 6, 13]) {
      const h = harbourOf(withState(PORT, { counts: { berths } }))
      expect(h.moorings.length).toBe(berths)
    }
    // an absent count is zero, never a default row
    const none = harbourOf(withState(PORT, { counts: { berths: undefined } }))
    expect(none.moorings.length).toBe(0)
  })

  it('are a count and not an era, so a camp with open windows has them', () => {
    expect(harbourOf(CAMP).moorings.length).toBe(2)
    expect(harbourOf(withState(CAMP, { counts: { berths: 0 } })).moorings.length).toBe(0)
  })

  it('stand in the water off the pier, in two ranks', () => {
    for (const seed of SEEDS) {
      const l = composeLayout(PORT, seed, FAST)
      const h = l.harbour as Harbour
      for (const m of h.moorings) {
        expect(l.coast.landAt(m.x, m.y)).toBe(false)
        expect(inRect(h.extent, m)).toBe(true)
      }
      // two columns, and each pair sits lower than the pair before it
      expect(new Set(h.moorings.map((m) => Math.round(m.x))).size).toBe(2)
      for (let i = 2; i < h.moorings.length; i++) {
        expect(h.moorings[i].y).toBeGreaterThan(h.moorings[i - 2].y)
      }
    }
  })
})

// ── cargo: the completed work ──────────────────────────────────────────────

describe('the dock kit', () => {
  /**
   * CARGO FOLLOWS COMPLETED WORK. compose.py:1188 reads `max(1, 1 + n*3)`, so
   * it lays a crate on the wharf of an org that has completed nothing — a
   * sprite with no rule behind it, which is what check_state_traceable exists
   * to catch. Zero work, bare wharf.
   */
  it('is empty when nothing has been completed', () => {
    for (const seed of SEEDS) {
      expect(harbourOf(withState(PORT, { counts: { cargo_stacks: 0 } }), seed).items).toEqual([])
    }
  })

  it('grows three items per completed tier, in the reference order, capped', () => {
    for (const [cargo, want] of [
      [1, 3],
      [2, 6],
      [3, 9],
      [4, 10],
      [40, 10],
    ] as const) {
      const h = harbourOf(withState(PORT, { counts: { cargo_stacks: cargo } }))
      expect(h.items.length).toBe(want)
      expect(h.items.map((i) => i.kind)).toEqual(DOCK_KIT.slice(0, want).map((k) => k.kind))
    }
  })

  /**
   * THE ORG'S OWN VESSEL is the one craft with a ladder behind it, and it is
   * the only one drawn. The reference moors a fishing boat, a rowboat, two
   * buoys and two ducks alongside it, none of which any rule over `state`
   * produces — a sprite that cannot be traced to a rule is the defect
   * check_state_traceable exists for, so they are not here.
   */
  it('moor the org vessel off the pier only once the rung says it exists', () => {
    const has = harbourOf(withState(PORT, { stages: { harbor_boat: 'packet_boat' } }))
    const boat = has.items.find((i) => i.kind === 'harbor_boat')
    expect(boat).toBeDefined()
    expect(boat?.overWater).toBe(true)
    expect(boat?.at.y).toBeCloseTo(pierOf(has).end.y - 6, 6)
    expect(boat?.at.x).toBeCloseTo(pierOf(has).end.x - 132, 6)

    for (const rung of ['none', undefined]) {
      const not = harbourOf(withState(PORT, { stages: { harbor_boat: rung } }))
      expect(not.items.some((i) => i.kind === 'harbor_boat')).toBe(false)
    }
    // and no craft nobody measured comes with it
    const ambient = ['boat_fishing', 'boat_rowing', 'buoy', 'duck']
    for (const kind of ambient) expect(has.items.some((i) => i.kind === kind)).toBe(false)
  })

  /**
   * EVERY ITEM RESOLVES ITS OWN COLUMN'S WATERLINE. Computing the row once and
   * reusing it — from the cove's centre, say — floats half the kit, because the
   * cove shore falls away by up to 250px across the span this measures.
   */
  it('sits on the waterline of its own column, not on a shared one', () => {
    for (const seed of [...SEEDS, ...WIDE]) {
      const l = composeLayout(PORT, seed, FAST)
      const h = l.harbour as Harbour
      expect(h.items.length).toBeGreaterThan(0)
      const spread: number[] = []
      for (const item of h.items) {
        const sy = shoreAt(l.coast, h.cove, item.at.x)
        expect(sy).not.toBeNull()
        const below = item.at.y - (sy as number)
        // DOCK_KIT's dy runs -12..+40 around a +14 base
        expect(below).toBeGreaterThanOrEqual(0)
        expect(below).toBeLessThanOrEqual(60)
        expect(inRect(h.extent, item.at)).toBe(true)
        expect(item.overWater).toBe(!l.coast.landAt(item.at.x, item.at.y))
        spread.push(sy as number)
      }
      // the columns genuinely disagree — otherwise the arm above is vacuous
      expect(Math.max(...spread) - Math.min(...spread)).toBeGreaterThan(20)
    }
  })
})

// ── the cranes: one per inherited pack ─────────────────────────────────────

describe('the dockside cranes', () => {
  it('are one per inherited extension pack, and never silently truncated', () => {
    for (const packs of [0, 1, 2, 4]) {
      const h = harbourOf(withState(PORT, { counts: { packs_inherited: packs } }))
      expect(h.cranesRequested).toBe(packs)
      expect(h.cranes.length).toBe(packs)
    }
    // the default port asks for more than the deck holds: the count is REPORTED
    const h = harbourOf(PORT)
    expect(h.cranesRequested).toBe(5)
    expect(h.cranes.length).toBe(4)
    expect(h.cranes.length).toBeLessThan(h.cranesRequested)
  })

  it('need a deck to stand on, and a camp has none', () => {
    expect(harbourOf(withState(PORT, { stages: { quay: 'rowboat_jetty' } })).cranes).toEqual([])
    const camp = harbourOf(CAMP)
    expect(camp.cranesRequested).toBe(5)
    expect(camp.cranes).toEqual([])
  })

  it('are spread along the deck rather than heaped on one spot', () => {
    for (const seed of SEEDS) {
      const h = harbourOf(PORT, seed)
      const rect = h.wharf?.rect as Rect
      for (const c of h.cranes) expect(inRect(rect, c)).toBe(true)
      const xs = h.cranes.map((c) => c.x).sort((a, b) => a - b)
      for (let i = 1; i < xs.length; i++) {
        expect(xs[i] - xs[i - 1]).toBeGreaterThanOrEqual(CRANE_SPACING)
      }
    }
  })

  /** Each one on ITS OWN column's waterline — the cove shore is not level. */
  it('stand on the deck of the column each is in, not on one shared row', () => {
    for (const seed of SEEDS) {
      const l = composeLayout(PORT, seed, FAST)
      const h = l.harbour as Harbour
      const ys = new Set<number>()
      for (const c of h.cranes) {
        const sy = shoreAt(l.coast, h.cove, c.x) as number
        expect(c.y - sy).toBe(42)
        ys.add(Math.round(c.y))
      }
      // the columns disagree, so "42 below its own" is not "42 below one row"
      expect(ys.size).toBeGreaterThan(1)
    }
  })
})

// ── quayside buildings: on LAND above the wharf ────────────────────────────

describe('the quayside buildings', () => {
  it('are one warehouse per achieved outcome, and none at zero', () => {
    for (const n of [0, 1, 2, 3]) {
      const l = composeLayout(withState(PORT, { counts: { warehouse: n } }), 'acme-corp', FAST)
      expect(l.structures.filter((s) => s.role === 'warehouse').length).toBe(n)
    }
  })

  it('put the harbourmaster there only once the rung says the hut exists', () => {
    const has = composeLayout(PORT, 'acme-corp', FAST)
    expect(has.structures.some((s) => s.role === 'harbormaster_hut')).toBe(true)
    const not = composeLayout(
      withState(PORT, { stages: { harbormaster_hut: 'none' } }),
      'acme-corp',
      FAST
    )
    expect(not.structures.some((s) => s.role === 'harbormaster_hut')).toBe(false)
  })

  /**
   * ON LAND ABOVE THE WHARF. They go through the same structure door as every
   * other building, so this is really a claim about that door still holding for
   * anchors that are BORN a few px off the waterline — the hardest case it has.
   * The +8 is one raster cell: shoreY walks whole pixels over a mask quantised
   * to the sampling step, so "at the waterline" is only defined to a cell.
   */
  it('stand on land, at or above the waterline of their own column', () => {
    for (const seed of [...SEEDS, ...WIDE]) {
      const l = composeLayout(PORT, seed, FAST)
      const h = l.harbour as Harbour
      const quayside = l.structures.filter(
        (s) => s.role === 'warehouse' || s.role === 'harbormaster_hut'
      )
      expect(quayside.length).toBeGreaterThan(0)
      for (const s of quayside) {
        expect(l.coast.landAt(s.at.x, s.at.y - 2)).toBe(true)
        const sy = shoreAt(l.coast, h.cove, s.at.x)
        if (sy !== null) expect(s.at.y).toBeLessThanOrEqual(sy + 8)
      }
    }
  })
})

// ── the lighthouse ─────────────────────────────────────────────────────────

describe('the lighthouse', () => {
  /**
   * SITED BY WALKING THE COAST, not by a hardcoded angle. Re-derived here
   * independently of harbour.ts's own loop: the coastline is a function of the
   * seed, so the compass bearing of "the point" moves island to island and an
   * authored angle would put the tower inland on half of them.
   */
  it('stands on the most seaward south-east point of this island', () => {
    for (const seed of [...SEEDS, ...WIDE]) {
      const coast = buildCoastline(seed, LAYOUT_SPACE, { step: 8 })
      const cove = coast.cove as Cove
      let best: { score: number; x: number; y: number } | null = null
      for (let x = cove.x + 380; x < LAYOUT_SPACE.w - 60; x += 6) {
        const sy = coast.shoreY(x, cove.y - cove.r * 1.5, LAYOUT_SPACE.h - 40)
        if (sy === null) continue
        if (!best || x + sy > best.score) best = { score: x + sy, x, y: sy }
      }
      expect(best).not.toBeNull()
      const site = lighthouseSite(coast, LAYOUT_SPACE, cove)
      expect(site).toEqual({ x: (best as { x: number }).x, y: (best as { y: number }).y - 18 })
    }
  })

  it('is east of the harbour and south of the island centre, and on land', () => {
    for (const seed of [...SEEDS, ...WIDE]) {
      const l = composeLayout(PORT, seed, FAST)
      const lh = l.lighthouse
      expect(lh).not.toBeNull()
      if (!lh) continue
      expect(lh.at.x).toBeGreaterThan((l.harbour as Harbour).cove.x)
      expect(lh.at.y).toBeGreaterThan(l.space.cy)
      expect(l.coast.landAt(lh.at.x, lh.at.y - 2)).toBe(true)
    }
  })

  /** ALWAYS DRAWN: the empty rung IS the drawing (compose.py:26). */
  it('is drawn at every era, because an unearned lighthouse is still a fact', () => {
    for (const era of ['camp', 'hamlet', 'town', 'beyond_bay'] as const) {
      const l = composeLayout(withState(PORT, { era }), 'acme-corp', FAST)
      expect(l.lighthouse).not.toBeNull()
      expect(l.structures.some((s) => s.role === 'lighthouse')).toBe(true)
    }
    const bare = composeLayout(
      { era: 'hamlet', road: 'dirt_path' },
      'acme-corp',
      FAST
    )
    expect(bare.lighthouse).not.toBeNull()
    expect(bare.lighthouse?.tower).toBe(false)
  })

  /**
   * A CLEARING, so the forest ring frames the point instead of swallowing it
   * (compose.py:905). Centred on where the tower ENDED, not where it was sited.
   *
   * THE ONE THING THAT MAY STAND INSIDE IT IS THE FELLING RECORD, and that
   * exception arrived with the inverted planting model (Captain 2026-07-27,
   * iso-layout/clearing.ts). This arm used to say "nothing at all", which was
   * the right assertion while a clearing was an exclusion; now it is ground that
   * was CUT, and a stump is what the cutting left. Measured across these five
   * seeds, everything inside is `tree_stump`, `fallen_log` or `wood_pile` — no
   * tree, no bush, no flower, which is the property the arm actually defends.
   * Weakening it to "nothing green" rather than "nothing" is a real loss of
   * strength, so the kind of every intruder is named rather than skipped.
   */
  it('keeps a clearing round itself that only the felling record stands in', () => {
    const RECORD = new Set(['tree_stump', 'fallen_log', 'wood_pile'])
    for (const seed of SEEDS) {
      const l = composeLayout(PORT, seed, FAST)
      const lh = l.lighthouse
      expect(lh).not.toBeNull()
      if (!lh) continue
      expect(lh.clearing).toBe(200)
      expect(l.districts).toContainEqual({ at: lh.at, r: lh.clearing })
      for (const s of l.scatter) {
        const inside =
          (s.at.x - lh.at.x) ** 2 + ((s.at.y - lh.at.y) * 1.35) ** 2 < lh.clearing ** 2
        if (!inside) continue
        expect({ seed, kind: s.kind, record: RECORD.has(s.kind) }).toEqual({
          seed,
          kind: s.kind,
          record: true,
        })
      }
    }
  })

  it('mows a smaller circle for a cairn than for a tower', () => {
    const tower = composeLayout(PORT, 'acme-corp', FAST).lighthouse
    const cairn = composeLayout(
      withState(PORT, { stages: { lighthouse: 'dark_cairn' } }),
      'acme-corp',
      FAST
    ).lighthouse
    expect(tower?.clearing).toBe(200)
    expect(cairn?.clearing).toBe(90)
    expect(cairn?.tower).toBe(false)
  })
})

describe('the lamp', () => {
  /**
   * THE BIGGEST VISUAL EVENT IN THE WORLD'S LIFE (morphology.yml:189). Lit if
   * and only if the lighthouse_lamp rung says lit — and there is a tower for it
   * to sit in.
   */
  it('is lit exactly when the rung says lit', () => {
    const lit = composeLayout(PORT, 'acme-corp', FAST).lighthouse
    expect(lit?.lamp.rungLit).toBe(true)
    expect(lit?.lamp.lit).toBe(true)
    expect(lit?.lamp.at).not.toBeNull()

    const dark = composeLayout(
      withState(PORT, { stages: { lighthouse_lamp: 'dark' } }),
      'acme-corp',
      FAST
    ).lighthouse
    expect(dark?.lamp.rungLit).toBe(false)
    expect(dark?.lamp.lit).toBe(false)
    expect(dark?.lamp.at).toBeNull()

    const unmeasured = composeLayout(
      withState(PORT, { stages: { lighthouse_lamp: undefined } }),
      'acme-corp',
      FAST
    ).lighthouse
    expect(unmeasured?.lamp.lit).toBe(false)
  })

  /**
   * A LAMP NEEDS A TOWER. The reference gates only on the sprite existing, and
   * the cairn is a sprite — so a graduated cell arriving before the tower is
   * built draws a lamp floating over a pile of stones. Suppressing it is only
   * honest if the measurement survives, which is what rungLit is for.
   */
  it('is not drawn over a cairn, and says so rather than losing the count', () => {
    const l = composeLayout(
      withState(PORT, { stages: { lighthouse: 'dark_cairn', lighthouse_lamp: 'lit' } }),
      'acme-corp',
      FAST
    )
    expect(l.lighthouse?.tower).toBe(false)
    expect(l.lighthouse?.lamp.rungLit).toBe(true)
    expect(l.lighthouse?.lamp.lit).toBe(false)
    expect(l.lighthouse?.lamp.at).toBeNull()
  })

  it('sits at the top of the tower, on its own column', () => {
    for (const seed of SEEDS) {
      const l = composeLayout(PORT, seed, FAST)
      const lh = l.lighthouse
      expect(lh?.lamp.at).not.toBeNull()
      if (!lh?.lamp.at) continue
      expect(lh.lamp.at.x).toBe(lh.at.x)
      expect(lh.lamp.at.y).toBeCloseTo(lh.at.y - lh.size.h * 0.86, 6)
      // above the base by most of the sprite: a glow at the base is a bonfire
      expect(lh.at.y - lh.lamp.at.y).toBeGreaterThan(lh.size.h * 0.8)
    }
  })

  it('is dark at camp, where no cell has graduated and there is no tower', () => {
    const l = composeLayout(CAMP, 'acme-corp', FAST)
    expect(l.lighthouse?.tower).toBe(false)
    expect(l.lighthouse?.lamp.lit).toBe(false)
  })
})

// ── region extents ─────────────────────────────────────────────────────────

describe('the region extents', () => {
  /**
   * THE LAYOUT EMITS ITS OWN CONTRACT. check_on_road exempts anything standing
   * on the paved square, a tilled plot or the wharf; check_terrain sweeps the
   * square for paving and each plot for cultivation. Deriving those in a bridge
   * would put the exemption zone in a module that does not know what was
   * painted — and this port SHRINKS and DROPS blobs that would spill into the
   * sea, so the authored 300x190 square is not the square on any island.
   */
  it('describe the paint that was actually emitted, not the authored constant', () => {
    let tighter = 0
    for (const seed of [...SEEDS, ...WIDE]) {
      const l = composeLayout(PORT, seed, FAST)
      const pz = l.regions.plaza
      expect(pz).not.toBeNull()
      if (!pz) continue
      const blobs = l.paint.filter((r) => r.kind === 'plaza').flatMap((r) => r.blobs)
      expect(blobs.length).toBeGreaterThan(0)
      for (const b of blobs) {
        expect(((b.c.x - pz[0]) / pz[2]) ** 2 + ((b.c.y - pz[1]) / pz[3]) ** 2).toBeLessThanOrEqual(
          1.000001
        )
      }
      // the bounding extent IS the blobs' extent, to the pixel
      const x0 = Math.min(...blobs.map((b) => b.c.x - b.rx))
      const x1 = Math.max(...blobs.map((b) => b.c.x + b.rx))
      expect(pz[0]).toBeCloseTo((x0 + x1) / 2, 6)
      expect(pz[2]).toBeCloseTo((x1 - x0) / 2, 6)
      if (pz[2] < 300 || pz[3] < 190) tighter++
    }
    // and it is never the authored 300x190 — a constant would be caught here
    expect(tighter).toBe(SEEDS.length + WIDE.length)
  })

  /**
   * ONE PER EMITTED PLOT, and the extent is the plot that was PAINTED.
   *
   * Containment of the blob centres is not enough here and was not enough for
   * the plaza either: the authored (w+60, h+40) box contains every centre it
   * ever draws, so an arm that only checks containment passes over a hardcoded
   * constant. The extent has to EQUAL the emitted blobs' own bounds, which is
   * what fails the moment a blob is shrunk or dropped at the waterline.
   */
  it('carry one field extent per emitted plot, and none when nothing is tilled', () => {
    for (const plots of [0, 1, 2, 4]) {
      const l = composeLayout(withState(PORT, { counts: { field_plots: plots } }), 'acme-corp', FAST)
      const painted = l.paint.filter((r) => r.kind === 'crop' || r.kind === 'ploughed')
      expect(l.regions.fields.length).toBe(painted.length)
      expect(l.regions.fields.length).toBeLessThanOrEqual(plots)
      l.regions.fields.forEach((f, i) => {
        const blobs = painted[i].blobs
        const x0 = Math.min(...blobs.map((b) => b.c.x - b.rx))
        const x1 = Math.max(...blobs.map((b) => b.c.x + b.rx))
        const y0 = Math.min(...blobs.map((b) => b.c.y - b.ry))
        const y1 = Math.max(...blobs.map((b) => b.c.y + b.ry))
        expect(f[0]).toBeCloseTo((x0 + x1) / 2, 6)
        expect(f[1]).toBeCloseTo((y0 + y1) / 2, 6)
        expect(f[2]).toBeCloseTo((x1 - x0) / 2, 6)
        expect(f[3]).toBeCloseTo((y1 - y0) / 2, 6)
        // CONTAINMENT IN THE EXTENT, WHICH IS A BOX — not in the ellipse
        // INSCRIBED in it. This arm used to require every blob CENTRE inside
        // the inscribed ellipse, which was only ever true because the plots
        // were themselves ellipse-shaped: the blobs clustered near the middle.
        // A plot is now a rhombus on the iso axes (paint.ts), so its corner
        // blobs sit at the corners of the extent — outside the inscribed
        // ellipse and correctly so. The property `regions.fields` actually
        // promises is that it IS the extent of these blobs, which the four
        // assertions above state exactly; asserting a shape on top of that was
        // pinning the old silhouette, not the contract.
        for (const b of blobs) {
          expect(b.c.x - b.rx).toBeGreaterThanOrEqual(x0 - 1e-6)
          expect(b.c.x + b.rx).toBeLessThanOrEqual(x1 + 1e-6)
          expect(b.c.y - b.ry).toBeGreaterThanOrEqual(y0 - 1e-6)
          expect(b.c.y + b.ry).toBeLessThanOrEqual(y1 + 1e-6)
        }
      })
    }
  })

  it('carry the quay rect the wharf actually built, and nothing at camp', () => {
    for (const seed of SEEDS) {
      const l = composeLayout(PORT, seed, FAST)
      expect(l.regions.quay).toEqual((l.harbour as Harbour).wharf?.rect)
    }
    const camp = composeLayout(CAMP, 'acme-corp', FAST)
    expect(camp.regions.quay).toBeNull()
    expect(camp.regions.plaza).toBeNull()
    expect(camp.regions.fields).toEqual([])
  })

  /**
   * NOTHING IS PLANTED ON THE WHARF. The port's own term, on the same argument
   * the paving term needed: no keep-out disc reaches the deck, and the verge
   * band and the shore band both run exactly along the waterline. Measured with
   * the term dropped from the verge predicate alone: 8 items on the deck across
   * these 30 seeds.
   */
  it('keep the planting off the deck', () => {
    for (const seed of [...SEEDS, ...WIDE]) {
      const l = composeLayout(PORT, seed, FAST)
      const q = l.regions.quay
      expect(q).not.toBeNull()
      if (!q) continue
      for (const s of l.scatter) expect(inRect(q, s.at)).toBe(false)
    }
  })
})

// ── the audit ──────────────────────────────────────────────────────────────

describe('auditLayout, on the harbour', () => {
  /**
   * The water arm cannot be the harbour's sensor — a mooring post is in the
   * water by construction — so the harbour carries its own: everything it emits
   * is inside an envelope built from the COVE AND THE SHORE ONLY. A box fitted
   * around the items would be a sensor that cannot fail, which is the defect
   * class this suite was rewritten for.
   */
  it('reports nothing outside the harbour, and nothing standing in the sea', () => {
    for (const seed of [...SEEDS, ...WIDE]) {
      const l = composeLayout(PORT, seed, FAST)
      const a = auditLayout(l)
      expect(a.outsideHarbour).toEqual([])
      expect(a.inWater).toEqual([])
      expect(a.onLane).toEqual([])
    }
  })

  /**
   * THE ENVELOPE IS INDEPENDENT OF WHAT IS INSIDE IT — and this is the arm that
   * proves it, because the one above cannot: fitting the box around the items
   * makes every item inside it and leaves the whole suite green (mutation
   * MH19). A box defined by what it checks is a sensor that cannot fail, which
   * is the single defect class this directory keeps paying for.
   *
   * The discriminator is how the box RESPONDS. It is a function of the cove,
   * the shore, the quay rung and the berth COUNT — and of nothing else — so:
   *
   *   - moving cargo, warehouses and packs must not shift it by a pixel, even
   *     though each one adds emitted things inside it. An items-fitted box
   *     tracks all three.
   *   - berths DOES move it, because the mooring rows walk 52px further out per
   *     pair and the envelope has to reach its own deepest row (that term was
   *     missing until 2026-07-27; see the berth-count arm above). So the arm
   *     pins the RESPONSE instead of forbidding it: the sides and the top edge
   *     never move, and the bottom edge moves by exactly the row stride. An
   *     items-fitted box reproduces neither — its bottom edge would sit at the
   *     last post rather than a margin below it, and its sides would follow the
   *     dock kit.
   *
   * The distinction that makes this a live sensor: the envelope is derived from
   * the INPUTS (rung, count), never from the emitted positions, so a mooring row
   * indexed off the wrong base or a kit computed from the wrong origin still
   * lands outside it — which is what the negative twin below measures.
   */
  it('measures the harbour against an envelope the harbour does not define', () => {
    for (const seed of SEEDS) {
      const empty = harbourOf(
        withState(PORT, {
          counts: { berths: 0, cargo_stacks: 0, warehouse: 0, packs_inherited: 0 },
        }),
        seed
      )
      // everything EXCEPT berths moved: the box may not notice
      const busy = harbourOf(
        withState(PORT, {
          counts: { berths: 0, cargo_stacks: 9, warehouse: 3, packs_inherited: 9 },
        }),
        seed
      )
      expect(busy.items.length).toBeGreaterThan(empty.items.length)
      expect(busy.extent).toEqual(empty.extent)

      // BOTH REGIMES. Up to 6 berths the pier still reaches deeper than the last
      // row, so the box must not move at all — that is the same
      // count-invariance the old arm asserted, kept where it is still true.
      const few = harbourOf(withState(PORT, { counts: { berths: 6 } }), seed)
      expect(few.moorings.length).toBe(6)
      expect(few.extent).toEqual(empty.extent)

      // Past that the rows are the deepest thing in the harbour, and the box
      // follows the ROW STRIDE — one 52px step per pair — while its sides and
      // its top edge hold. 13 -> rows 0..6, 21 -> rows 0..10: four strides.
      const many = harbourOf(withState(PORT, { counts: { berths: 13 } }), seed)
      const more = harbourOf(withState(PORT, { counts: { berths: 21 } }), seed)
      expect(more.extent.slice(0, 3)).toEqual(many.extent.slice(0, 3))
      expect(more.extent[3] - many.extent[3]).toBe(52 * 4)
      // and the deepest post is inside it, with the margin still to spare
      for (const h of [few, many, more]) {
        expect(h.extent[3]).toBeGreaterThan(Math.max(...h.moorings.map((m) => m.y)))
      }
    }
  })

  /** The negative twin: the arm above is only worth its green if this is red. */
  it('DOES report a dock item computed from the wrong origin', () => {
    const l = composeLayout(PORT, 'acme-corp', FAST)
    const h = l.harbour as Harbour
    const strayItem: Layout = {
      ...l,
      harbour: { ...h, items: [{ ...h.items[0], at: { x: h.items[0].at.x - 900, y: 300 } }] },
    }
    expect(auditLayout(strayItem).outsideHarbour.length).toBe(1)

    const strayMooring: Layout = { ...l, harbour: { ...h, moorings: [{ x: 60, y: 60 }] } }
    expect(auditLayout(strayMooring).outsideHarbour.length).toBe(1)

    const strayCrane: Layout = { ...l, harbour: { ...h, cranes: [{ x: 2300, y: 100 }] } }
    expect(auditLayout(strayCrane).outsideHarbour.length).toBe(1)

    const strayJetty: Layout = {
      ...l,
      harbour: { ...h, jetty: { ...pierOf(h), end: { x: 40, y: 1700 } } },
    }
    expect(auditLayout(strayJetty).outsideHarbour.length).toBe(1)
  })
})

// ── purity ─────────────────────────────────────────────────────────────────

describe('determinism', () => {
  it('gives the same harbour, lighthouse and regions for the same inputs', () => {
    for (const seed of SEEDS) {
      const a = composeLayout(PORT, seed, FAST)
      const b = composeLayout(PORT, seed, FAST)
      expect(JSON.stringify(b.harbour)).toBe(JSON.stringify(a.harbour))
      expect(JSON.stringify(b.lighthouse)).toBe(JSON.stringify(a.lighthouse))
      expect(JSON.stringify(b.regions)).toBe(JSON.stringify(a.regions))
    }
  })

  it('gives a DIFFERENT harbour for a different island', () => {
    const shapes = SEEDS.map((s) =>
      JSON.stringify((composeLayout(PORT, s, FAST).harbour as Harbour).shore)
    )
    expect(new Set(shapes).size).toBe(SEEDS.length)
  })

  /** No cove bite, no harbour — but the keystone is still drawn. */
  it('emits no harbour on an island carved without a cove', () => {
    const l = composeLayout(PORT, 'acme-corp', { coastline: { step: 8, cove: null } })
    expect(l.harbour).toBeNull()
    expect(l.regions.quay).toBeNull()
    expect(l.lighthouse).not.toBeNull()
    expect(auditLayout(l).outsideHarbour).toEqual([])
  })

  /** buildHarbour is callable on its own — it takes state, not a Layout. */
  it('is a pure function of (coastline, cove, counts)', () => {
    const coast = buildCoastline('acme-corp', LAYOUT_SPACE, { step: 8 })
    const cove = coast.cove as Cove
    const sizeOf = (k: string) => DEFAULT_FOOTPRINTS[k] ?? { w: 96, h: 96 }
    const one = buildHarbour(coast, cove, { era: 'hamlet', quay: 'stone_quay_4', sizeOf })
    const two = buildHarbour(coast, cove, { era: 'hamlet', quay: 'stone_quay_4', sizeOf })
    expect(JSON.stringify(two)).toBe(JSON.stringify(one))
    // every count absent = an empty working port, never a default one
    expect(one?.moorings).toEqual([])
    expect(one?.items).toEqual([])
    expect(one?.cranes).toEqual([])
    expect(one?.warehouseSites).toEqual([])
    expect(one?.harbourmasterSite).toBeNull()
    expect(one?.wharf).not.toBeNull()
  })
})
