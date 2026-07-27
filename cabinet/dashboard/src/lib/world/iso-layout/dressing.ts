/**
 * DRESSING — the authored district furniture, and the reason the island stopped
 * reading as a lawn with eleven buildings on it.
 *
 * PORTED FROM compose.py lines 944-1115 (the six fixed-compass districts and
 * their props) plus the helpers at 695-820 (hedgerow, fence_line, lamp_line,
 * face_ring, frontage, row).
 *
 * WHY IT EXISTS. Before this module composeLayout emitted ELEVEN building roles
 * and nothing else: no stall, no noticeboard, no flagpole, no benches, no lamp
 * posts, no fences, no barrels, no scarecrows, no fowl. The first frame ever
 * drawn from the layout was judged "under-furnished — 13 distinct structure
 * names against ~20 building types plus dense props in the approved still" and
 * "the eight undrawn ladders are visible, not theoretical". Ten ladders that the
 * growth file MEASURES had no placement rule at all, so a real rung change
 * moved nothing on the island. That is not a cosmetic gap: a world whose
 * measured state cannot reach the frame is a dashboard that does not report.
 *
 * THREE CLASSES OF THING LIVE HERE, and the difference decides what may draw:
 *   LADDER — flagpole, noticeboard, veto_plinth, observatory, journal_desk,
 *     law_plot, pens, water_store, composter, lantern_posts. Each is entitled by
 *     ITS OWN rung or count, exactly like the buildings one stage up, and its
 *     `kind` is the LADDER OBJECT so the pack's (object, era, rung) table picks
 *     the art. An unmeasured ladder draws nothing.
 *   VILLAGE LIFE — bench, lamp, signpost, barrel, crate, wheelbarrow, chicken,
 *     market goods, haystack, cart, scarecrow, veg garden, laundry, beehives,
 *     fences, hedges. Entitled by the ERA and nothing finer, which is the
 *     reference's own rule (compose.py:523 "A camp is a camp: no benches, no
 *     flowerbeds, no street lamps, no market goods"). NOTHING in this class may
 *     draw at camp, and blueprint.ts justifies the class only at hamlet and
 *     above — so a bench on a camp frame is an orphan and check_state_traceable
 *     goes red. Proven by mutation (`camp-bench`), not asserted.
 *   LANDING — the boats, the buoys, the log pile and the crate cairn at the
 *     waterline. Entitled at EVERY era, including camp, because the org's own
 *     existence is the rule: a cabinet exists because someone landed here, and
 *     the hatch still is the arrival. compose.py draws these unconditionally and
 *     the earlier port dropped them for want of a rule; the rule is the hatch.
 *
 * EVERYTHING GOES THROUGH THE SAME DOOR AS A BUILDING. Every item is settled by
 * placeOnGround against the lanes, the coastline, the tilled plots and the
 * occupancy book, and DROPPED when it cannot settle (`dropIfBlocked`). A prop
 * is decoration, and decoration is what gets dropped — see the `put` docstring
 * in ./index. Authored offsets are therefore a WISH, never a placement: the
 * reference nudges its props and still draws a fence across a lane, and this
 * port would rather lose a barrel than gain an on-road defect.
 *
 * PURE: no clocks, no unseeded randomness, no IO, no DOM.
 */
import { type Footprint } from './clearance'
import { ISO_AXIS_SLOPE, type Era, type Point } from './space'

/** One placed piece of dressing, in the same shape a Structure reports. */
export interface DressItem {
  /** The pack OBJECT for a ladder item, the frame name for anything else. */
  kind: string
  /**
   * WHY this is drawn — the ladder object, or the class that entitles it.
   * check_state_traceable asks the blueprint the same question from the other
   * side (justifiedFromState), and the two must agree without either reading
   * the other.
   */
  role: string
  at: Point
  flip: boolean
  size: Footprint
  /** Stands on water: no shadow, and the land rule does not apply. */
  overWater: boolean
}

/**
 * The frames VILLAGE LIFE may draw, and the whole of it.
 *
 * A CLOSED SET ON PURPOSE. blueprint.ts justifies exactly this list at hamlet
 * and above, so a dressing pass that grows a new prop shows up as an orphan
 * until the name is added here on purpose — the same hand-held discipline
 * ambient-nature.txt uses for morphology, and for the same reason: a set
 * derived from the code that places would be a sensor wired to its own subject.
 */
export const VILLAGE_LIFE_FRAMES: readonly string[] = [
  'barrel_single',
  'beehives',
  'bench',
  // bush_round is DELIBERATELY ABSENT and this comment is the reason: it is
  // NATURE, on cabinet/scripts/world-capture/ambient-nature.txt, and an island
  // has bushes whether or not anyone lives there. The hedgerows and frontages
  // below still plant them — they just do not need an era entitlement to
  // exist, and claiming one here would put morphology beside the measured
  // things and make the difference invisible. blueprint.test.ts asserts nature
  // is never state-justified, and it caught this the first time.
  'cart',
  'chart_table',
  'chicken',
  'chicken_coop',
  'consequence_ledger',
  'crate_single',
  'dog_sleeping',
  'fence_run',
  'flowerbed',
  'haystack',
  'hedge_run',
  'lamp_dark',
  'lamp_lantern',
  'laundry_line',
  'law_post',
  'mailbox',
  'market_goods',
  'market_stall',
  'potted_plant',
  'scarecrow',
  'signpost',
  'training_dummy',
  'veg_garden',
  'water_trough',
  'wheelbarrow',
  'wood_pile',
]

/**
 * The frames THE LANDING may draw, at every era including camp.
 *
 * compose.py:1158-1161 places the fishing boat, the rowboat and the two buoys
 * unconditionally. They are NOT village life — the approved hatch still has
 * craft at its waterline — and they are NOT morphology, because no island grows
 * a rowing boat. The rule is that the org exists.
 *
 * THE BOATS AND THE BUOYS, AND NOT THE CARGO. A log pile and a crate cairn were
 * in this set for one capture and are not any more: `check_era`'s ERA_MIN table
 * floors both `wood_pile` and `crate_single` at hamlet, and it went red on the
 * camp frame the moment they were added. The table is right and this set was
 * wrong — sawn timber stacked in a pile and a made crate are a settlement's
 * output, not an arrival's — and compose.py agrees from the other side: both
 * names are in its AMBIENT set, which it refuses to draw at camp. The rule kept
 * its floor and the content moved, which is the only order these two may ever
 * be reconciled in.
 */
export const LANDING_FRAMES: readonly string[] = ['boat_fishing', 'boat_rowing', 'buoy']

/** The market stall's own spot: compose.py:966, SQUARE + (186, -52). */
export const STALL_OFFSET: Point = { x: 186, y: -52 }

/**
 * The buildings the reference gates on a COUNT rather than on a rung of their
 * own, with the ladder whose count decides them. compose.py:1030-1035, 1055.
 *
 * They are listed rather than inlined because each one is a claim about what a
 * number means — a windmill says "the fleet runs services", a coop says "more
 * than one outbuilding" — and a claim that is only visible inside an `if` is a
 * claim nobody reviews.
 */
export const COUNT_GATED_BUILDINGS: readonly {
  kind: string
  ladder: string
  atLeast: number
  dx: number
  dy: number
  from: 'works' | 'fields'
}[] = [
  { kind: 'windmill', ladder: 'pens', atLeast: 1, dx: 40, dy: -210, from: 'works' },
  { kind: 'watermill_kiln', ladder: 'pens', atLeast: 2, dx: 178, dy: 150, from: 'works' },
  { kind: 'chicken_coop', ladder: 'outbuildings', atLeast: 2, dx: 258, dy: -30, from: 'fields' },
]

/** How the caller settles one item; null means it could not stand anywhere. */
export type Settle = (
  kind: string,
  role: string,
  at: Point,
  flip: boolean,
  opts?: {
    /**
     * False = do not nudge off a lane; DROP the section instead, and the gap
     * it leaves IS the gate (compose.py fence_axis's `_footprint_on_path`
     * continue). Nudging a fence off a road bends the run.
     */
    avoidLane?: boolean
    /** False = keep the authored spacing; see PlaceOptions.nudge. */
    nudge?: boolean
  }
) => DressItem | null

export interface DressCtx {
  era: Era
  /** era >= hamlet — the reference's `at_least("hamlet")`. */
  village: boolean
  /** A ladder's rung, or null/undefined when it has never been measured. */
  stageOf: (object: string) => string | null | undefined
  /** A ladder's count, 0 when unmeasured. */
  countOf: (object: string) => number
  /** Has this ladder built anything? (presentRung, not isBuilt.) */
  built: (object: string) => boolean
  sizeOf: (kind: string) => Footprint
  settle: Settle
  /** compose.py snap(): pull an authored anchor inland when it is offshore. */
  anchor: (p: Point) => Point
  /** The great house's placed centre and drawn size, when it was built. */
  great: { at: Point; size: Footprint } | null
  /** The library's and workshop's placed centres, when they were built. */
  lib: Point | null
  works: Point | null
  fields: Point | null
  /** The village square (compose.py SQUARE). */
  square: Point
  /** Officer lot centres that really got a dwelling, in row order. */
  dwellings: Point[]
  /** The cove's waterline sampler, and the cove centre — for the landing. */
  shoreAt: ((x: number) => number | null) | null
  cove: Point | null
}

const TAU = Math.PI * 2

/**
 * The authored district furniture for a state.
 *
 * ORDER IS LOAD-BEARING. Items are settled against an occupancy book the caller
 * grows as it accepts them, so an earlier item wins the ground: the civic core
 * is emitted before the outlying dressing, and the ladder items before the
 * decoration, because a measured thing must never be pushed off its spot by a
 * flowerpot.
 */
export function dressDistricts(ctx: DressCtx): DressItem[] {
  const out: DressItem[] = []
  const keep = (it: DressItem | null) => {
    if (it) out.push(it)
  }
  const { village, square: SQ } = ctx

  /** VILLAGE LIFE: silent at camp, always. One gate, one place to read it. */
  const life: Settle = (kind, role, at, flip, opts) =>
    village ? ctx.settle(kind, role, at, flip, opts) : null

  /** A ladder item: drawn only when its own rung has built something. */
  const ladder = (object: string, at: Point, flip = false) => {
    if (!ctx.built(object)) return null
    return ctx.settle(object, object, at, flip)
  }

  /** compose.py row(): n copies along a straight step. */
  const row = (
    place: Settle,
    kind: string,
    role: string,
    x0: number,
    y0: number,
    n: number,
    dx: number,
    dy = 0,
    flipAlt = true
  ) => {
    for (let i = 0; i < n; i++) {
      keep(place(kind, role, { x: x0 + i * dx, y: y0 + i * dy }, flipAlt && i % 2 === 1))
    }
  }

  /** compose.py face_ring(): items evenly round a focal point. */
  const faceRing = (
    place: Settle,
    centre: Point,
    r: number,
    kinds: readonly string[],
    role: string,
    n: number,
    start = 0,
    squash = 0.62
  ) => {
    for (let i = 0; i < n; i++) {
      const a = start + (i * TAU) / n
      keep(
        place(
          kinds[i % kinds.length],
          role,
          { x: centre.x + Math.cos(a) * r, y: centre.y + Math.sin(a) * r * squash },
          Math.cos(a) > 0
        )
      )
    }
  }

  /** compose.py frontage(): garden props across a building's door. */
  const frontage = (bx: number, by: number, kinds: readonly string[], dx = 52, yOff = 26) => {
    const n = kinds.length
    for (let i = 0; i < n; i++) {
      keep(life(kinds[i], 'village_life', { x: bx + (i - (n - 1) / 2) * dx, y: by + yOff }, i % 2 === 1))
    }
  }

  /**
   * compose.py fence_line(): a continuous run along ONE isometric axis.
   *
   * The reference measures the fence sprite's baked ground slope out of its
   * pixels. A layout module has no pixels, and inventing a second slope is how
   * runs come out staggered — so the axis is the projection's own
   * ISO_AXIS_SLOPE, which is the slope the art was drawn to by construction.
   *
   * `avoidLane: false` is the reference's rule and not an oversight: a fence
   * MEANS to stop at a lane, and the gap it leaves IS the gate. The section
   * that would stand on the road is dropped instead (the caller's lane test
   * still runs — it just drops rather than nudges, so the run stays straight).
   */
  const fenceLine = (pts: readonly Point[], kind = 'fence_run') => {
    if (!village) return
    const w = ctx.sizeOf(kind).w
    const step = Math.max(6, w - 2)
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i]
      const b = pts[i + 1]
      const dx = b.x - a.x
      if (Math.abs(dx) < step) continue
      const n = Math.max(1, Math.floor(Math.abs(dx) / step))
      const want = dx === 0 ? 0 : (b.y - a.y) / dx
      const axis =
        Math.abs(want - ISO_AXIS_SLOPE) <= Math.abs(want + ISO_AXIS_SLOPE) ? 1 : -1
      const sgn = dx > 0 ? 1 : -1
      const from = sgn > 0 ? a : b
      for (let k = 0; k < n; k++) {
        const x = from.x + k * step
        const y = from.y + k * step * ISO_AXIS_SLOPE * axis
        keep(life(kind, 'village_life', { x, y }, axis < 0, { avoidLane: false, nudge: false }))
      }
    }
  }

  /** compose.py lamp_line(): street lamps set back from a lane. */
  const lampLine = (pts: readonly Point[], kind: string, spacing = 190, offset = 34) => {
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i]
      const b = pts[i + 1]
      const d = Math.hypot(b.x - a.x, b.y - a.y)
      const n = Math.max(1, Math.floor(d / spacing))
      for (let j = 0; j < n; j++) {
        const t = (j + 0.5) / n
        const nx = -(b.y - a.y) / Math.max(1e-3, d)
        const ny = (b.x - a.x) / Math.max(1e-3, d)
        keep(
          life(
            kind,
            'lantern_posts',
            { x: a.x + (b.x - a.x) * t + nx * offset, y: a.y + (b.y - a.y) * t + ny * offset },
            false
          )
        )
      }
    }
  }

  // ---- CENTRE: the great house's curtilage (compose.py:950-957) ------------
  if (ctx.great) {
    const g = ctx.great.at
    const gw = ctx.great.size.w
    frontage(g.x, g.y, ['flowerbed', 'bush_round', 'potted_plant', 'bush_round', 'flowerbed'], 54, 18)
    // exactly one dog, forever (compose.py:953) — and it is village life, so a
    // camp has no dog, which is what `ambient=False` in the reference hides.
    keep(life('dog_sleeping', 'village_life', { x: g.x - gw * 0.42, y: g.y + 4 }, false))
    keep(life('chart_table', 'village_life', { x: g.x + gw * 0.78, y: g.y + 58 }, false))
    keep(life('bench', 'village_life', { x: g.x + gw * 0.62, y: g.y + 8 }, true))
    keep(life('lamp_dark', 'village_life', { x: g.x - gw * 0.52, y: g.y + 118 }, false))
  }

  // ---- THE SQUARE: daily life (compose.py:959-996) -------------------------
  // benches face the hearth
  faceRing(life, SQ, 138, ['bench'], 'village_life', village ? 4 : 0, Math.PI / 4)

  // THE MARKET STALL IS GATED ON THE ERA AND NOTHING ELSE, which is what
  // compose.py:966 does. It used to be gated on `isBuilt(state,'market_stall')`
  // — and there is no `market_stall` ladder in cabinet/world/growth-ladders.yml
  // (29 ladders, checked), so the predicate was false on every state that has
  // ever existed and the stall could not draw at all. A gate on a name nothing
  // measures is a switch wired to nothing: it reads as a rule and enforces the
  // empty set. The stall is village life, exactly like the goods beside it.
  keep(life('market_stall', 'village_life', { x: SQ.x + STALL_OFFSET.x, y: SQ.y + STALL_OFFSET.y }, false))
  row(life, 'market_goods', 'village_life', SQ.x + 132, SQ.y + 26, village ? 2 : 0, 58, 20)

  keep(ladder('noticeboard', { x: SQ.x - 34, y: SQ.y - 116 }))
  keep(ladder('journal_desk', { x: SQ.x - 178, y: SQ.y + 96 }))
  keep(ladder('flagpole', { x: SQ.x + 248, y: SQ.y - 124 }))

  keep(life('signpost', 'village_life', { x: SQ.x - 208, y: SQ.y - 96 }, false))
  keep(life('wheelbarrow', 'village_life', { x: SQ.x - 96, y: SQ.y + 124 }, true))
  keep(life('barrel_single', 'village_life', { x: SQ.x + 124, y: SQ.y + 106 }, false))
  keep(life('crate_single', 'village_life', { x: SQ.x + 156, y: SQ.y + 122 }, true))
  keep(life('chicken', 'village_life', { x: SQ.x + 56, y: SQ.y + 118 }, false))

  // Street lighting is the trust story (compose.py:983-989): a post exists per
  // graduation transition, and a post only LIGHTS for a graduated cell. An
  // honest zero is dark posts, never no posts — so the sequence is lit ones
  // first and the remainder on the ladder's own dark art.
  const posts = Math.max(0, ctx.countOf('lantern_posts'))
  const lit = Math.max(0, Math.min(posts, ctx.countOf('posts_lit')))
  const darkArt = ctx.built('lantern_posts') ? 'lantern_posts' : 'lamp_dark'
  const lampSeq: string[] = [
    ...Array<string>(lit).fill('lamp_lantern'),
    ...Array<string>(Math.max(0, posts - lit)).fill(darkArt),
  ]
  if (lampSeq.length > 0) {
    faceRing(
      life,
      SQ,
      292,
      lampSeq,
      'lantern_posts',
      Math.min(2, lampSeq.length),
      Math.PI / 4,
      0.6
    )
  }

  // planting only OUTSIDE the paving (compose.py:990-993)
  for (let a = 0; a < 10; a++) {
    const ang = (a * TAU) / 10 + 0.31
    keep(
      life(
        ['bush_round', 'bush_flowering', 'flowerbed'][a % 3],
        'village_life',
        { x: SQ.x + Math.cos(ang) * 262, y: SQ.y + Math.sin(ang) * 162 },
        Math.cos(ang) > 0
      )
    )
  }

  // ---- LAW (N): one fenced plot, posts inside it (compose.py:998-1007) -----
  const LAW = ctx.anchor({ x: 1010, y: 392 })
  if (ctx.built('law_plot')) {
    const n = Math.max(1, ctx.countOf('law_plot'))
    row(ctx.settle, 'law_plot', 'law_plot', LAW.x - 60, LAW.y + 40, n, 62, -8, false)
  }
  row(life, 'law_post', 'village_life', LAW.x - 84, LAW.y + 22, village ? 3 : 0, 74, -12, false)
  keep(ladder('veto_plinth', { x: LAW.x + 6, y: LAW.y + 66 }))
  keep(life('consequence_ledger', 'village_life', { x: LAW.x + 104, y: LAW.y + 70 }, false))

  // ---- MEMORY (NE): the library's curtilage (compose.py:1010-1018) --------
  if (ctx.lib) {
    const L = ctx.lib
    const lw = ctx.sizeOf('library').w
    frontage(L.x, L.y, ['bush_round', 'flowerbed', 'bush_round'], 58, 22)
    keep(life('bench', 'village_life', { x: L.x + lw * 0.62, y: L.y + 18 }, true))
    keep(life('lamp_dark', 'village_life', { x: L.x - lw * 0.62, y: L.y + 34 }, false))
  }

  // ---- WORKS (E): the machine room (compose.py:1021-1045) -----------------
  const WRK = ctx.works ?? ctx.anchor({ x: 1830, y: 800 })
  for (const b of COUNT_GATED_BUILDINGS) {
    if (b.from !== 'works') continue
    if (!village || ctx.countOf(b.ladder) < b.atLeast) continue
    keep(ctx.settle(b.kind, `${b.ladder}_count`, ctx.anchor({ x: WRK.x + b.dx, y: WRK.y + b.dy }), false))
  }
  keep(ladder('water_store', { x: WRK.x - 216, y: WRK.y + 176 }))
  row(life, 'wood_pile', 'village_life', WRK.x - 186, WRK.y + 58, village ? 2 : 0, 54, 12)
  row(life, 'crate_single', 'village_life', WRK.x - 72, WRK.y + 74, village ? 3 : 0, 40, 10)
  row(life, 'barrel_single', 'village_life', WRK.x + 58, WRK.y + 92, village ? 2 : 0, 42, 10)
  if (ctx.built('composter')) {
    const n = Math.max(0, Math.min(4, ctx.countOf('composter')))
    row(ctx.settle, 'composter', 'composter', WRK.x - 140, WRK.y + 188, n, 60, 14)
  }
  keep(life('wheelbarrow', 'village_life', { x: WRK.x - 236, y: WRK.y + 96 }, true))
  keep(life('water_trough', 'village_life', { x: WRK.x + 236, y: WRK.y + 58 }, false))
  // the service pens themselves — the ladder the windmill only counts
  keep(ladder('pens', { x: WRK.x - 120, y: WRK.y - 96 }))

  // ---- FIELDS (SE): shipped work (compose.py:1048-1065) -------------------
  const FLD = ctx.fields ?? ctx.anchor({ x: 1620, y: 1180 })
  for (const b of COUNT_GATED_BUILDINGS) {
    if (b.from !== 'fields') continue
    if (!village || ctx.countOf(b.ladder) < b.atLeast) continue
    keep(ctx.settle(b.kind, `${b.ladder}_count`, ctx.anchor({ x: FLD.x + b.dx, y: FLD.y + b.dy }), false))
  }
  keep(life('chicken', 'village_life', { x: FLD.x + 206, y: FLD.y + 16 }, false))
  keep(life('chicken', 'village_life', { x: FLD.x + 282, y: FLD.y + 30 }, true))
  keep(life('cart', 'village_life', { x: FLD.x - 136, y: FLD.y - 96 }, true))
  keep(life('scarecrow', 'village_life', { x: FLD.x - 46, y: FLD.y + 40 }, false))
  row(
    life,
    'haystack',
    'village_life',
    FLD.x - 150,
    FLD.y + 54,
    village ? Math.max(0, Math.min(4, ctx.countOf('outbuildings'))) : 0,
    60,
    16
  )
  keep(life('veg_garden', 'village_life', { x: FLD.x - 268, y: FLD.y + 140 }, false))
  fenceLine([
    { x: FLD.x - 320, y: FLD.y + 94 },
    { x: FLD.x + 108, y: FLD.y + 142 },
  ])
  fenceLine([
    { x: FLD.x + 150, y: FLD.y + 150 },
    { x: FLD.x + 352, y: FLD.y + 96 },
  ])
  fenceLine([
    { x: FLD.x - 190, y: FLD.y - 64 },
    { x: FLD.x + 70, y: FLD.y - 38 },
  ])

  // ---- RESIDENTIAL (W): one yard prop per officer (compose.py:1068-1081) --
  ctx.dwellings.forEach((c, i) => {
    keep(
      life(
        ['wood_pile', 'barrel_single', 'water_trough'][i % 3],
        'village_life',
        { x: c.x + 92, y: c.y + 26 },
        true
      )
    )
  })
  fenceLine([
    { x: 742, y: 742 },
    { x: 656, y: 900 },
    { x: 712, y: 1050 },
  ])
  if (lampSeq.length > 4) {
    lampLine(
      [
        { x: 742, y: 742 },
        { x: 656, y: 900 },
        { x: 712, y: 1050 },
      ],
      lampSeq[4],
      300,
      -46
    )
  }
  keep(life('laundry_line', 'village_life', { x: 760, y: 1120 }, false))
  keep(life('beehives', 'village_life', { x: 556, y: 966 }, false))

  // ---- TRAINING (NW): the dojo (compose.py:1084-1095) ---------------------
  // The law is explicit that a delta of zero or less renders exactly ONE
  // weathered scarecrow and no dummies. This port has no chronicle reader, so
  // it renders the honest arm and never the dummies — an invented delta would
  // be three false claims of authored evals, which is the defect the
  // reference's own comment records paying for.
  const TRN = ctx.anchor({ x: 760, y: 470 })
  keep(life('scarecrow', 'village_life', { x: TRN.x - 10, y: TRN.y + 30 }, false))
  fenceLine([
    { x: TRN.x - 140, y: TRN.y + 86 },
    { x: TRN.x + 180, y: TRN.y + 104 },
  ])

  // ---- OBSERVATORY (N rise): foresight (compose.py:1098-1104) -------------
  const OBS = ctx.anchor({ x: 960, y: 372 })
  keep(ladder('observatory', OBS))
  keep(life('bench', 'village_life', { x: OBS.x + 64, y: OBS.y + 56 }, true))

  // ---- SIGNALS (SW): the crossroads mailbox (compose.py:1107-1112) --------
  const SIG = ctx.anchor({ x: 840, y: 1226 })
  keep(life('mailbox', 'village_life', SIG, false))
  keep(life('signpost', 'village_life', { x: SIG.x + 82, y: SIG.y + 14 }, false))
  keep(life('lamp_dark', 'village_life', { x: SIG.x - 74, y: SIG.y + 22 }, false))
  keep(life('bench', 'village_life', { x: SIG.x + 26, y: SIG.y + 74 }, false))

  // lamps along the main street (compose.py:1115)
  if (lampSeq.length > 2) {
    lampLine([SQ, { x: 1200, y: 1140 }, { x: 1210, y: 1290 }], lampSeq[2], 260, 58)
  }

  return out
}

/**
 * THE LANDING — the shore story, at every era.
 *
 * compose.py:1158-1161 places a fishing boat, a rowboat and two buoys with no
 * gate at all, and the approved hatch still adds a log pile and a crate cairn
 * on the sand. The earlier port dropped all of it for want of a state rule and
 * said so; the rule is that the org exists. A cabinet is hatched by somebody
 * arriving, so the craft that brought them is as true on day zero as the
 * treeline — and on the hatch frame it is the ONLY thing that says a person has
 * ever been here. Without it the camp reads as an empty island with a tent.
 *
 * Offsets are the reference's, measured from the cove centre; the y of each
 * shore item comes from the SAME waterline sampler the wharf uses, so nothing
 * here floats and nothing is beached.
 */
export function dressLanding(ctx: DressCtx): DressItem[] {
  const cove = ctx.cove
  const shore = ctx.shoreAt
  if (!cove || !shore) return []
  const out: DressItem[] = []
  const water = (kind: string, x: number, dy: number, flip = false) => {
    const s = shore(x)
    if (s === null) return
    out.push({
      kind,
      role: 'landing',
      at: { x, y: s + dy },
      flip,
      size: ctx.sizeOf(kind),
      overWater: true,
    })
  }
  // compose.py:1159-1161 — the rowboat off the west horn, the buoys either side
  water('boat_rowing', cove.x - 286, 126)
  water('buoy', cove.x + 352, 92)
  water('buoy', cove.x - 372, 38)
  // compose.py:1158 — the fishing boat lies east of the pier head
  water('boat_fishing', cove.x + 122, 96, true)
  return out
}
