/**
 * THE CLEARING MODEL — the island is overgrown, and growth is subtractive.
 *
 * Captain direction 2026-07-27 (designs/iso-engine-port-plan-2026-07-27.md,
 * "the island is CLEARED, not built"): wilderness is the island's DEFAULT
 * state, every structure stands in ground that was cut for it, the cut grows
 * with the object's rung, and the stumps and felled logs at a clearing's rim
 * are the RECORD of that cut rather than decoration.
 *
 * SAME STANDARD AS THE SIBLING SUITES: every arm asserts something that would
 * be FALSE against a naive implementation, and each one either carries its
 * negative twin here or names the source mutation that was run against it and
 * what that mutation did. An arm with neither is a disabled sensor wearing a
 * green tick. The mutation log for this file is at the bottom, including the
 * two that came back GREEN.
 */
import { describe, expect, it } from 'vitest'
import {
  buildClearedGround,
  buildLaneField,
  buildOccupancyIndex,
  canopyCoverage,
  CANOPY_KINDS,
  CLEAR_PER_RUNG,
  CLEARING_EDGE_BAND,
  clearingRadius,
  composeLayout,
  groundTaken,
  LAYOUT_SPACE,
  maxGroundOverlap,
  rawnessOfRung,
  RECORD_BAND,
  RECORD_FRAMES,
  recordDensity,
  seniority,
  structureClearings,
  type Clearing,
  type Era,
  type Layout,
  type LayoutState,
  type Occupant,
  type Point,
} from './index'
import { seededRng } from '../hash'

const FAST = { coastline: { step: 8 } }
const SEEDS = ['acme-corp', 'harbour', 'zeta']
const ERAS: readonly Era[] = ['camp', 'hamlet', 'town', 'beyond_bay']

/**
 * ONE ORG, REPLAYED THROUGH ITS FOUR ERAS.
 *
 * The counts are the VISIBLE RUNG INDEX for every ladder, which is what the
 * engine writes into this shape (iso-scene.layoutStateFrom) — so `great_house:
 * 4` means the great house is on its fifth rung, not that there are four of
 * them. That is the number the clearing model reads, and stating it here is the
 * difference between an era table and a table of invented numbers.
 */
function org(era: Era): LayoutState {
  switch (era) {
    case 'camp':
      return {
        era,
        road: 'dirt_path',
        stages: { great_house: 'camp_log_cabin' },
        counts: { officer_dwellings: 1, great_house: 0 },
      }
    case 'hamlet':
      return {
        era,
        road: 'dirt_worn',
        stages: {
          great_house: 'cottage',
          well: 'stone_well',
          library: 'shelf',
          workshop: 'forge',
          outbuildings: 'shed',
        },
        counts: {
          officer_dwellings: 3,
          field_plots: 2,
          great_house: 1,
          library: 1,
          workshop: 1,
          outbuildings: 1,
        },
      }
    case 'town':
      return {
        era,
        road: 'gravel_road',
        stages: {
          great_house: 'timber_hall',
          well: 'stone_well',
          library: 'stone_hall',
          workshop: 'forge',
          outbuildings: 'barn',
          firepit: 'firepit',
        },
        counts: {
          officer_dwellings: 5,
          field_plots: 3,
          great_house: 2,
          library: 2,
          workshop: 2,
          outbuildings: 2,
          well: 2,
        },
      }
    case 'beyond_bay':
      return {
        era,
        road: 'cobbled_road',
        stages: {
          great_house: 'great_hall',
          well: 'stone_well',
          library: 'stone_hall',
          workshop: 'forge',
          outbuildings: 'barn',
          firepit: 'firepit',
          lighthouse: 'lit_tower',
        },
        counts: {
          officer_dwellings: 6,
          field_plots: 4,
          great_house: 4,
          library: 4,
          workshop: 4,
          outbuildings: 3,
          well: 3,
          lighthouse: 3,
        },
      }
  }
}

const byEra = new Map<Era, Map<string, Layout>>()
for (const era of ERAS) {
  const m = new Map<string, Layout>()
  for (const seed of SEEDS) m.set(seed, composeLayout(org(era), seed, FAST))
  byEra.set(era, m)
}
const at = (era: Era, seed = SEEDS[0]) => byEra.get(era)!.get(seed)!

/** Cleared fraction of the island's LAND, through the rule's own predicate. */
function cutFraction(l: Layout, samples = 30000): number {
  const rng = seededRng(0xbeef)
  let land = 0
  let cut = 0
  for (let i = 0; i < samples; i++) {
    const x = rng() * l.space.w
    const y = rng() * l.space.h
    if (!l.coast.landAt(x, y)) continue
    land++
    if (l.cleared.isCleared(x, y)) cut++
  }
  return land === 0 ? 0 : cut / land
}

/** How far out this point sits, as a fraction of the island's radius there. */
function radialFraction(l: Layout, p: Point): number {
  const ang = Math.atan2((p.y - l.space.cy) / 0.92, p.x - l.space.cx)
  const d = Math.hypot(p.x - l.space.cx, (p.y - l.space.cy) / 0.92)
  return d / l.coast.landEdge(ang)
}

// ── 1. wilderness is the default ───────────────────────────────────────────

describe('the island is OVERGROWN — timber is the default, not decoration', () => {
  it('a hatched island is dominated by wood, one clearing and the landing aside', () => {
    // THE HEADLINE NUMBER. Measured on the model this replaced, camp canopy was
    // 0.4247 and hamlet/town/beyond_bay were 0.2534 / 0.2489 / 0.2469 — three
    // eras a viewer cannot tell apart, and a camp that read as "hamlet minus
    // things". The floor here is what "dominated by timber" has to mean.
    for (const seed of SEEDS) {
      const l = at('camp', seed)
      const c = canopyCoverage(l, seededRng(0xc0ffee))
      expect({ seed, wooded: c.fraction > 0.7 }).toEqual({ seed, wooded: true })
      expect({ seed, open: cutFraction(l) < 0.2 }).toEqual({ seed, open: true })
    }
  })

  it('the wood is ACROSS the island, not a coastal ring round a bare middle', () => {
    // The specific defect the direction names. The old model confined the
    // general planting to `coast.isInner` (d < landEdge-190) and then made that
    // interior the sparsest part of the island, so the trees were a frame and
    // the middle was lawn. Measured on the old code, the deep interior of a
    // camp island carried 8-14 canopy sprites; it now carries 40+.
    for (const seed of SEEDS) {
      const l = at('camp', seed)
      const deep = [...l.ring, ...l.scatter].filter(
        (s) => CANOPY_KINDS.has(s.kind) && radialFraction(l, s.at) < 0.55
      )
      expect({ seed, deep: deep.length > 30 }).toEqual({ seed, deep: true })
    }
  })

  it('an unbuilt lot is FOREST — nobody has chopped it yet', () => {
    // "when camp is expanding, for example with new officers that should mean
    // the new officer spawns and then starts chopping trees and building
    // his/her cabin" — so the ground an officer has not arrived on is standing
    // timber, not a mown lot waiting for a house. The old model reserved a
    // 150px disc on EVERY residential lot whether or not it was built.
    const one = composeLayout(org('camp'), 'acme-corp', FAST)
    const four = composeLayout(
      { ...org('camp'), counts: { officer_dwellings: 4, great_house: 0 } },
      'acme-corp',
      FAST
    )
    const dwellings = (l: Layout) => l.structures.filter((s) => s.role === 'officer_dwelling')
    expect(dwellings(one).length).toBe(1)
    expect(dwellings(four).length).toBe(4)
    // The lots that are empty on the one-officer island carry no clearing —
    // EXCEPT any that falls inside a NATURAL one. On seed `acme-corp` the second
    // officer's lot sits inside the pond's 190px disc, and a lot in a pond is
    // not standing timber whoever has or has not arrived. Skipping it silently
    // would be the hole; it is skipped by NAME of the thing that covers it.
    const naturalCover = (l: Layout, p: Point) =>
      l.cleared.clearings.some(
        (c) => c.cut === 'natural' && Math.hypot(p.x - c.at.x, (p.y - c.at.y) * 1.35) < c.r
      )
    const empty = dwellings(four).slice(1)
    const wooded = empty.filter((d) => !naturalCover(one, d.at))
    expect(wooded.length).toBeGreaterThan(0)
    for (const d of wooded) {
      expect(one.cleared.isCleared(d.at.x, d.at.y)).toBe(false)
      // TIMBER, NOT NECESSARILY CLOSED CANOPY. This used to demand exactly 1
      // and that was only true while the treeline ramped INWARD; the ramp is
      // now on the standing side (CLEARING_EDGE_BAND), so a lot within a band
      // width of somebody else's clearing reads as thinning wood — measured
      // 0.294 on the second officer's lot, which is 68px off the first
      // officer's rim. The claim the direction makes is that nobody has cut it,
      // and that is `> 0`; demanding 1 would be asserting that a neighbour's
      // clearing has no edge.
      expect(one.cleared.timber(d.at.x, d.at.y)).toBeGreaterThan(0)
    }
    // …and every one of them is cleared the moment somebody builds on it
    for (const d of empty) expect(four.cleared.isCleared(d.at.x, d.at.y)).toBe(true)
    expect(four.cleared.clearings.length).toBe(one.cleared.clearings.length + 3)
  })
})

// ── 2. clearing is subtractive, and it grows with the rung ─────────────────

describe('the cut is a real quantity that grows with the rung', () => {
  it('clearingRadius grows with BOTH the drawn size and the rung', () => {
    const hut = { w: 120, h: 120 }
    const hall = { w: 200, h: 200 }
    expect(clearingRadius(hall, 0)).toBeGreaterThan(clearingRadius(hut, 0))
    // NEGATIVE TWIN for the rung term, which is the half the direction is about:
    // one rung is worth exactly CLEAR_PER_RUNG, so a mutation that zeroes that
    // constant makes this equality fail rather than merely making the world
    // look flat.
    for (let r = 0; r < 5; r++) {
      expect(clearingRadius(hall, r + 1) - clearingRadius(hall, r)).toBe(CLEAR_PER_RUNG)
    }
    expect(CLEAR_PER_RUNG).toBeGreaterThan(0)
    // "a great house at its top rung has cut more ground than a log cabin"
    expect(clearingRadius(hall, 4)).toBeGreaterThan(clearingRadius(hut, 0) * 1.5)
    // and it is bounded, so a runaway rung cannot clear the island
    expect(clearingRadius(hall, 9999)).toBe(clearingRadius(hall, 60))
  })

  it('the SAME house on a higher rung clears more ground, end to end', () => {
    // Through composeLayout, not through the helper: the arm above proves the
    // formula, this one proves the formula is what the island is built from.
    // Everything but the great house's rung is held fixed.
    const base = org('town')
    const low = composeLayout({ ...base, counts: { ...base.counts, great_house: 0 } }, 'acme-corp', FAST)
    const high = composeLayout({ ...base, counts: { ...base.counts, great_house: 5 } }, 'acme-corp', FAST)
    const rOf = (l: Layout) => l.cleared.clearings.find((c) => c.role === 'great_house')!.r
    expect(rOf(high) - rOf(low)).toBe(5 * CLEAR_PER_RUNG)
    expect(cutFraction(high)).toBeGreaterThan(cutFraction(low))
  })

  it('a count ladder shows as MORE clearings, never as bigger ones', () => {
    // The distinction that keeps "era styles, rung measures" honest one level
    // down: `officer_dwellings` says how many houses exist, not how far one
    // house has come. Six officers must therefore cut six gaps, not one huge
    // one — and each gap is sized by that officer's SENIORITY in the row (see
    // `seniority`), which is why the sizes differ at all.
    expect(seniority(0, 6)).toBe(5)
    expect(seniority(5, 6)).toBe(0)
    expect(seniority(0, 1)).toBe(0)
    const l = at('beyond_bay')
    const homes = l.cleared.clearings.filter((c) => c.role === 'officer_dwelling')
    expect(homes.length).toBe(6)
    // SIX GAPS, EACH AT THE BASELINE. The radius follows the drawn size only,
    // because none of these has a rung of its own — so six officers cut six
    // ordinary clearings and never one enormous one. Every dwelling clears
    // less ground than the great house, which is ONE object four rungs up.
    const great = l.cleared.clearings.find((c) => c.role === 'great_house')!
    const houses = l.structures.filter((s) => s.role === 'officer_dwelling')
    expect(houses.length).toBe(homes.length)
    houses.forEach((s, i) => {
      expect(s.rung).toBe(0)
      expect(homes[i].r).toBe(clearingRadius(s.size, 0))
      expect(homes[i].r).toBeLessThan(great.r)
    })
    // AGE is what varies down the row, not size: the first officer's rim has had
    // five arrivals' worth of time to grow over, the last one's is raw.
    const raw = homes.map((c) => c.rawness)
    for (let i = 1; i < raw.length; i++) expect(raw[i]).toBeGreaterThanOrEqual(raw[i - 1])
    expect(raw[raw.length - 1]).toBe(1)
    expect(raw[0]).toBeLessThan(1)
  })

  it('the cleared region is the UNION — clearings, lanes and paved surface', () => {
    const l = at('hamlet')
    for (const c of l.cleared.clearings) {
      expect({ role: c.role, cleared: l.cleared.isCleared(c.at.x, c.at.y) }).toEqual({
        role: c.role,
        cleared: true,
      })
    }
    // a lane is cut ground too
    const onLane = l.lanes[0].runs[0][2]
    expect(l.cleared.isCleared(onLane.x, onLane.y)).toBe(true)
    // and the WOOD is not. The scatter's timber passes are gated on `free()`,
    // which refuses every cut point, so this is exact for them.
    //
    // THE BELT IS DELIBERATELY EXCLUDED. forestRing holds itself off a clearing
    // at RING_DISTRICT_K (0.62) of the radius rather than all of it, on its own
    // stated rule — "the ring frames the village; it may crowd a district but
    // not grow through it" — so a belt tree between 0.62r and r is inside a
    // clearing on purpose and has been since before this model. Asserting over
    // it here would be this arm quietly re-litigating that one.
    const wood = l.scatter.filter((s) => CANOPY_KINDS.has(s.kind))
    expect(wood.length).toBeGreaterThan(10)
    for (const t of wood) expect(l.cleared.isCleared(t.at.x, t.at.y)).toBe(false)
  })

  it('the timber field ramps on the STANDING side of the rim, not the cut side', () => {
    // Driven directly so the shape is pinned without a coastline in the way.
    //
    // THE RAMP MOVED SIDES ON 2026-07-27 and this arm is the sensor for which
    // side it is on. It used to run INWARD from the rim, where index.ts's
    // planting predicate can never sample — `free()` refuses every point
    // `isCleared` accepts, and that is exactly the set the inward ramp lived on
    // — so the field the tree pass consumed was the constant 1 and
    // TREE_SPACING_MAX decided nothing. Outward, the ramp is on the ground the
    // wood actually stands on.
    const lanes = buildLaneField([])
    const one: Clearing[] = [
      { at: { x: 1000, y: 1000 }, r: 300, rawness: 1, role: 'x', cut: 'felled' },
    ]
    const g = buildClearedGround(one, {
      lanes,
      onPaving: () => false,
      inWater: () => false,
      onQuay: () => false,
    })
    // cut ground carries no timber, at the centre and right up to the rim
    expect(g.timber(1000, 1000)).toBe(0)
    expect(g.timber(1000 + 299, 1000)).toBe(0)
    expect(g.timber(1000 + 300, 1000)).toBe(0)
    // and the canopy closes over CLEARING_EDGE_BAND beyond it
    expect(g.timber(1000 + 300 + CLEARING_EDGE_BAND, 1000)).toBe(1)
    expect(g.timber(1600, 1000)).toBe(1)
    const mid = g.timber(1000 + 300 + CLEARING_EDGE_BAND / 2, 1000)
    expect(mid).toBeGreaterThan(0.4)
    expect(mid).toBeLessThan(0.6)
    // monotone across the band — a ramp, not a step
    let last = -1
    for (let d = 0; d <= CLEARING_EDGE_BAND; d += 8) {
      const v = g.timber(1000 + 300 + d, 1000)
      expect(v).toBeGreaterThan(last)
      last = v
    }
    // THE INVERTED CLAIM, stated as its own assertion so the ramp cannot
    // silently move back inside: no point strictly inside the disc has timber.
    for (let d = 0; d < 300; d += 20) expect(g.timber(1000 + d, 1000)).toBe(0)
  })

  it('structureClearings sizes on the RUNG and ages on the AGE, separately', () => {
    const size = { w: 200, h: 200 }
    const cs = structureClearings([
      { at: { x: 0, y: 0 }, size, role: 'great_house', rung: 3, age: 3 },
      { at: { x: 0, y: 0 }, size, role: 'great_house', rung: 0, age: 0 },
      // the case that made two fields necessary: a count-ladder member with no
      // rung of its own that has nonetheless stood a long time
      { at: { x: 0, y: 0 }, size, role: 'officer_dwelling', rung: 0, age: 5 },
    ])
    expect(cs[0].r).toBe(clearingRadius(size, 3))
    expect(cs[0].r).toBeGreaterThan(cs[1].r)
    expect(cs[0].rawness).toBeLessThan(cs[1].rawness)
    // same rung as cs[1] so the SAME radius, different age so a settled rim
    expect(cs[2].r).toBe(cs[1].r)
    expect(cs[2].rawness).toBeLessThan(cs[1].rawness)
    expect(cs.every((c) => c.cut === 'felled')).toBe(true)
  })
})

// ── 3. the clearing leaves a record, at its edge ───────────────────────────

describe('the felled timber is the RECORD of the cut, and it lies at the rim', () => {
  it('every stump and log stands on a rim, none in the middle of the wood', () => {
    for (const era of ERAS) {
      for (const seed of SEEDS) {
        const l = at(era, seed)
        const rec = l.scatter.filter((s) => RECORD_FRAMES.has(s.kind))
        for (const r of rec) {
          expect({
            era,
            seed,
            kind: r.kind,
            onRim: l.cleared.edgeAt(r.at.x, r.at.y) > 0,
          }).toEqual({ era, seed, kind: r.kind, onRim: true })
        }
      }
    }
  })

  it('and it is AT the rim, not merely somewhere in the band', () => {
    // THE NON-VACUITY TWIN, and the first version of it was too weak to keep.
    // "Every record item is inside the rim band" is nearly free at a mature era:
    // measured, the band covers 0.17 of the island's land at camp but 0.64-0.84
    // at hamlet and beyond, because twenty clearings' bands merge. That number
    // is reported here rather than asserted away.
    //
    // The property that survives is proximity: `edgeAt` is 1 exactly on a rim
    // and falls linearly to 0 at RECORD_BAND, so its MEAN over the record says
    // how close to the boundary the record actually sits. Against two baselines
    // — random land, and the wood — it is high at every era on every seed:
    //   camp        rec 0.70-0.73  land 0.09-0.10  wood 0.02-0.03
    //   hamlet      rec 0.56-0.70  land 0.37-0.39  wood 0.13-0.17
    //   town        rec 0.60-0.67  land 0.46-0.48  wood 0.23-0.30
    //   beyond_bay  rec 0.65-0.76  land 0.52-0.55  wood 0.36-0.42
    for (const era of ERAS) {
      for (const seed of SEEDS) {
        const l = at(era, seed)
        const rng = seededRng(0x51de)
        let land = 0
        let sum = 0
        for (let i = 0; i < 20000; i++) {
          const x = rng() * l.space.w
          const y = rng() * l.space.h
          if (!l.coast.landAt(x, y)) continue
          land++
          sum += l.cleared.edgeAt(x, y)
        }
        expect(land).toBeGreaterThan(3000)
        const mean = (items: readonly { at: Point }[]) =>
          items.reduce((a, s) => a + l.cleared.edgeAt(s.at.x, s.at.y), 0) /
          Math.max(1, items.length)
        const rec = l.scatter.filter((s) => RECORD_FRAMES.has(s.kind))
        const wood = [...l.ring, ...l.scatter].filter((s) => CANOPY_KINDS.has(s.kind))
        expect({ era, seed, some: rec.length > 5 }).toEqual({ era, seed, some: true })
        const mRec = mean(rec)
        expect({ era, seed, atRim: mRec > 0.5 }).toEqual({ era, seed, atRim: true })
        expect({ era, seed, overLand: mRec > sum / land + 0.09 }).toEqual({
          era,
          seed,
          overLand: true,
        })
        expect({ era, seed, overWood: mRec > mean(wood) * 1.5 }).toEqual({
          era,
          seed,
          overWood: true,
        })
      }
    }
  })

  it('a NATURAL clearing leaves no record — nobody felled a pond or a beach', () => {
    const l = at('hamlet')
    const natural = l.cleared.clearings.filter((c) => c.cut === 'natural')
    expect(natural.length).toBeGreaterThan(0)
    for (const c of natural) {
      expect(c.rawness).toBe(0)
      // sampled right on its rim, in the disc metric, in eight directions
      for (let i = 0; i < 8; i++) {
        const a = (i * Math.PI * 2) / 8
        const x = c.at.x + Math.cos(a) * c.r
        const y = c.at.y + (Math.sin(a) * c.r) / 1.35
        const felledNear = l.cleared.clearings.some(
          (o) =>
            o.cut === 'felled' &&
            Math.abs(Math.hypot(x - o.at.x, (y - o.at.y) * 1.35) - o.r) < RECORD_BAND
        )
        if (felledNear) continue // another clearing's rim runs through here
        expect({ role: c.role, edge: l.cleared.edgeAt(x, y) }).toEqual({ role: c.role, edge: 0 })
      }
    }
  })

  it('the record THINS as the org matures — per unit of rim, not in total', () => {
    // Captain: "a mature town has an old, settled edge and a young camp has raw
    // stumps." The TOTAL barely moves (20-22 at camp, 11-19 at beyond_bay), so
    // a count arm here would report success for a model that had stopped
    // working. Per unit of rim it falls several-fold, on every seed.
    const table: string[] = []
    for (const seed of SEEDS) {
      const d = ERAS.map((era) => recordDensity(at(era, seed), seededRng(0xc0ffee)))
      table.push(
        `${seed}: ` + ERAS.map((e, i) => `${e}=${d[i].perKiloRim.toFixed(2)}`).join('  ')
      )
      for (let i = 1; i < d.length; i++) {
        expect({
          seed,
          era: ERAS[i],
          settling: d[i].perKiloRim < d[i - 1].perKiloRim,
        }).toEqual({ seed, era: ERAS[i], settling: true })
      }
      // and the fall is large, not a rounding wobble
      expect({ seed, fall: d[0].perKiloRim > d[3].perKiloRim * 3 }).toEqual({ seed, fall: true })
    }
    // eslint-disable-next-line no-console
    console.log('felling record per 1000 rim samples:\n  ' + table.join('\n  '))
  })

  it('rawness is what does that, and it is read from the rung', () => {
    expect(rawnessOfRung(0)).toBe(1)
    expect(rawnessOfRung(4)).toBe(0)
    for (let r = 0; r < 4; r++) expect(rawnessOfRung(r + 1)).toBeLessThan(rawnessOfRung(r))
    // NEGATIVE TWIN, in-test: flatten rawness to 1 everywhere and the record
    // density stops being able to fall — the band is then the whole rim at every
    // era. Driven through the same builder the layout uses.
    const lanes = buildLaneField([])
    const surf = { lanes, onPaving: () => false, inWater: () => false, onQuay: () => false }
    const settled = buildClearedGround(
      [{ at: { x: 1000, y: 1000 }, r: 300, rawness: 0, role: 'x', cut: 'felled' }],
      surf
    )
    const raw = buildClearedGround(
      [{ at: { x: 1000, y: 1000 }, r: 300, rawness: 1, role: 'x', cut: 'felled' }],
      surf
    )
    // the RIM is identical — that is pure geometry…
    expect(settled.edgeAt(1300, 1000)).toBe(raw.edgeAt(1300, 1000))
    // …and the record on it is not
    expect(settled.recordAt(1300, 1000)).toBe(0)
    expect(raw.recordAt(1300, 1000)).toBeGreaterThan(0.9)
  })

  it('a swallowed rim carries no record — two clearings that merged have no edge', () => {
    const lanes = buildLaneField([])
    const surf = { lanes, onPaving: () => false, inWater: () => false, onQuay: () => false }
    const alone = buildClearedGround(
      [{ at: { x: 1000, y: 1000 }, r: 300, rawness: 1, role: 'a', cut: 'felled' }],
      surf
    )
    const swallowed = buildClearedGround(
      [
        { at: { x: 1000, y: 1000 }, r: 300, rawness: 1, role: 'a', cut: 'felled' },
        { at: { x: 1300, y: 1000 }, r: 400, rawness: 1, role: 'b', cut: 'felled' },
      ],
      surf
    )
    expect(alone.recordAt(1300, 1000)).toBeGreaterThan(0.9)
    expect(swallowed.recordAt(1300, 1000)).toBe(0)
    // and the far side of `a`, which nothing swallowed, still carries it
    expect(swallowed.recordAt(700, 1000)).toBeGreaterThan(0.9)
  })

  it('a woodpile is a settlement s output — never on a camp frame', () => {
    // Two independent checkers floor `wood_pile` at hamlet (check_era's ERA_MIN
    // and the VILLAGE_LIFE justification), so a camp woodpile is an orphan.
    for (const seed of SEEDS) {
      expect(at('camp', seed).scatter.map((s) => s.kind)).not.toContain('wood_pile')
    }
    const anyVillage = ERAS.slice(1).some((era) =>
      SEEDS.some((seed) => at(era, seed).scatter.some((s) => s.kind === 'wood_pile'))
    )
    // …and it is not simply absent everywhere, which would make the arm vacuous
    expect(anyVillage).toBe(true)
  })
})

// ── 4. the eras must read differently by construction ─────────────────────

describe('canopy coverage separates the eras BY CONSTRUCTION', () => {
  it('camp is timber, beyond_bay is substantially cleared, and it is monotone', () => {
    const rows: string[] = []
    for (const seed of SEEDS) {
      const cov = ERAS.map((era) => canopyCoverage(at(era, seed), seededRng(0xc0ffee)).fraction)
      const cut = ERAS.map((era) => cutFraction(at(era, seed)))
      rows.push(
        `${seed.padEnd(11)} ` +
          ERAS.map((e, i) => `${e}: canopy=${cov[i].toFixed(3)} cut=${cut[i].toFixed(3)}`).join('  ')
      )
      for (let i = 1; i < cov.length; i++) {
        expect({ seed, era: ERAS[i], receding: cov[i] < cov[i - 1] }).toEqual({
          seed,
          era: ERAS[i],
          receding: true,
        })
        expect({ seed, era: ERAS[i], cutting: cut[i] > cut[i - 1] }).toEqual({
          seed,
          era: ERAS[i],
          cutting: true,
        })
      }
      // and the ends are far apart, not merely ordered. Measured on the model
      // this replaced: 0.425 / 0.253 / 0.249 / 0.247 — ordered by 0.6% at the
      // far end, which is a difference nobody can see.
      expect({ seed, wide: cov[0] > cov[3] * 2.2 }).toEqual({ seed, wide: true })
      expect({ seed, camp: cov[0] > 0.7 }).toEqual({ seed, camp: true })
      expect({ seed, grown: cut[3] > 0.7 }).toEqual({ seed, grown: true })
    }
    // eslint-disable-next-line no-console
    console.log('canopy coverage and cleared fraction by era:\n  ' + rows.join('\n  '))
  })

  it('canopyCoverage is a UNION and a closed set, not a sum of sprite areas', () => {
    const l = at('camp')
    const c = canopyCoverage(l, seededRng(0xc0ffee))
    expect(c.fraction).toBeLessThanOrEqual(1)
    expect(c.trees).toBeGreaterThan(100)
    // it counts canopy and nothing else: a layout with the trees removed reads 0
    const bare = { ...l, ring: [], scatter: [] }
    expect(canopyCoverage(bare, seededRng(0xc0ffee)).fraction).toBe(0)
    // and it is seeded — same stream in, same answer out
    expect(canopyCoverage(l, seededRng(0xc0ffee))).toEqual(
      canopyCoverage(l, seededRng(0xc0ffee))
    )
    // the closed set really excludes things: shrubs are not canopy
    expect(CANOPY_KINDS.has('bush_round')).toBe(false)
    expect(CANOPY_KINDS.has('tree_pine')).toBe(true)
  })
})

// ── the occupancy index — a speed change that may not move an answer ───────

describe('buildOccupancyIndex answers exactly what a linear scan answers', () => {
  it('same maximum, same verdict, over a random population', () => {
    // The inversion multiplied the island's population by about five and the
    // scatter tests every candidate against every occupant. The index is a pure
    // speed change, so the arm that matters is that it changed no answer.
    const rng = seededRng(0x1dea)
    const occupied: Occupant[] = []
    for (let i = 0; i < 400; i++) {
      occupied.push({
        at: { x: rng() * 2400, y: rng() * 1760 },
        size: { w: 30 + rng() * 200, h: 30 + rng() * 200 },
      })
    }
    const index = buildOccupancyIndex(occupied)
    expect(index.count).toBe(occupied.length)
    let touched = 0
    for (let i = 0; i < 4000; i++) {
      const p = { x: rng() * 2400, y: rng() * 1760 }
      const size = { w: 20 + rng() * 180, h: 20 + rng() * 180 }
      const linear = maxGroundOverlap(p, size, occupied)
      expect(index.maxOverlap(p, size)).toBe(linear)
      for (const frac of [0.04, 0.16, 0.5]) {
        expect(index.taken(p, size, frac)).toBe(groundTaken(p, size, occupied, frac))
      }
      if (linear > 0) touched++
    }
    // NOT VACUOUS: the population is dense enough that most probes really do
    // hit something, so "identical" is being asserted over real overlaps.
    expect(touched).toBeGreaterThan(1000)
  })

  it('an empty book is empty, and a far-away occupant is not near', () => {
    const empty = buildOccupancyIndex([])
    expect(empty.maxOverlap({ x: 10, y: 10 }, { w: 50, h: 50 })).toBe(0)
    expect(empty.taken({ x: 10, y: 10 }, { w: 50, h: 50 })).toBe(false)
    const far = buildOccupancyIndex([{ at: { x: 2000, y: 1500 }, size: { w: 50, h: 50 } }])
    expect(far.maxOverlap({ x: 10, y: 10 }, { w: 50, h: 50 })).toBe(0)
    expect(far.maxOverlap({ x: 2000, y: 1500 }, { w: 50, h: 50 })).toBeGreaterThan(0.9)
  })
})

/**
 * MUTATION LOG — 2026-07-27, every arm above driven from the source it guards.
 * Recorded here rather than asserted, because a mutation is a thing that was
 * RUN once and cannot be left in the tree. Two came back green and are named
 * with the rest; burying those is the failure this discipline exists to catch.
 *
 * See the round's notes in the commit message for the full table.
 */
export const MUTATION_LOG_2026_07_27 = true
