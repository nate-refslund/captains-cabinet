/**
 * LANES — the road network, as data.
 *
 * PORTED FROM compose.py lines 185-236 and 678-682, then re-founded on the
 * Captain's traffic model (2026-07-27).
 *
 * A PATH IS WORN BY USE. IT IS NOT SWITCHED ON BY AN ERA. Until 2026-07-27
 * every lane carried a `villageOnly` flag: at camp they were skipped and at
 * hamlet all nine appeared in one step, the instant the era index crossed a
 * threshold. That contradicted the world's own construction law
 * (cabinet/world/show-grammar.yml: "NO structure ever pops in: every growth
 * rung earns itself on-screen") and the subtractive-clearing model the island
 * is built on, where ground is WON incrementally. Nine carriageways
 * materialising together is the largest pop-in on the frame.
 *
 * SO A LANE EXISTS WHEN THE PLACE AT ITS FAR END EXISTS. The track to the
 * library is worn when there is a library; the works spur when there is a
 * workshop; the field track when something is farmed; the harbour road from day
 * zero, because the landing is where everyone arrives and it is the one place
 * open on a hatched island. The network therefore grows edge by edge, at the
 * same moment the building it serves is raised, and nothing appears with an
 * era.
 *
 * AND IT WIDENS ON HOW MUCH THAT PLACE IS USED (Captain: "when having a library
 * the path exists, but only a tiny/narrow path to begin with. the more the
 * library is used the wider the path?"). Every destination already has a metric
 * that IS its usage — the same one that grows the building there: the library's
 * `memory_rows_total`, the workshop's `evolved_skills`, the quay's commits, the
 * law plot's `captain_rules`. The state hands the layout that metric already
 * folded onto its ladder as a RUNG INDEX (iso-scene.ts layoutStateFrom:
 * `counts[name] = trunc(el.rung)`, and era-engine computes the rung as
 * `clamp(floor(log2(v/base + 1)))`), so the log scaling this needs is the
 * growth ladders' own and no second curve is invented here. A lane is born at
 * the narrowest rung — a desire path, one person wide — and the first few
 * visits widen it visibly while the ten-thousandth does not.
 *
 * THE ORG-WIDE ROAD RUNG NO LONGER SETS WIDTH. It sets SURFACE: dirt_path,
 * dirt_worn, gravel_road, cobbled_road. That is already what
 * growth-ladders.yml means by "the egg's t0 dirt path, upgraded by real traffic
 * volume" — the rung names are materials, not sizes. The two axes now say two
 * different true things: WIDTH is how much this particular place is used,
 * SURFACE is how mature the org's roads are overall. A heavily-used library
 * gets a broad dirt track in a young org and a broad cobbled one later.
 *
 * THE HONEST CONSEQUENCE IS KEPT, NOT SMOOTHED. A destination with a low
 * measurement keeps a hairline forever, and a district that NOTHING measures
 * (the dojo and the crossroads have no ladder in growth-ladders.yml — see
 * ./dressing's own note on not inventing one) stays at the bottom rung for
 * good. An unmeasured place renders its baseline; it is never interpolated up
 * to look busier than it is.
 *
 * A lane is emitted as its JITTERED CENTRELINE plus a width, not as a raster.
 * The renderer paints it; the layout stages test against it. compose.py paints
 * overlapping ellipses of radius (w/2, w/2*0.72) every ~16px along the line and
 * thresholds the result, so the occupancy test here is the same family of
 * discs — same geometry, no bitmap.
 *
 * THE NETWORK IS CLIPPED TO LAND (compose.py:343, `paths =
 * ImageChops.darker(paths.filter(...), landmask)`). The control points are
 * authored against the fixed compass layout and the island is a function of the
 * org seed, so a lane can and does run off the shore — measured before this
 * clip: 37 of 80 seeds had a lane or drive sample standing in open water. The
 * reference intersects the road raster with the land mask before anything
 * samples it; the equivalent without a bitmap is to cut the centreline into its
 * on-land RUNS, which is why a Lane carries `runs` and not one `path`. A lane
 * that crosses an inlet is two runs with a gap, exactly as the reference paints
 * it. buildLanes therefore cannot be called without saying where the land is.
 *
 * PURE: no clocks, no unseeded randomness (the wobble is a sine of position,
 * exactly as in the reference), no IO, no DOM.
 */
import { hypot, type Point, type RoadRung } from './space'

/**
 * HOW WIDE A LANE IS AT EACH RUNG OF ITS DESTINATION'S OWN LADDER, in layout px.
 *
 * EIGHT RUNGS because that is the range a growth ladder's rung index can take
 * (era-engine clamps `floor(log2(v/base + 1))` to 0..7), so this table can be
 * indexed by a rung directly and never needs a second scale.
 *
 * RUNG 0 IS 13, WHICH IS THE REFERENCE'S OWN PAINT FLOOR (compose.py:209
 * `max(13, ...)`) — the narrowest line the ground painter can actually lay
 * down. That is the "desire path, one person wide" the model starts every lane
 * at, and it is a real visible line rather than a rounding to nothing.
 *
 * THE TOP IS 62, which is the widest road this network has ever drawn (the old
 * `main` nominal at a cobbled rung). Nothing gets wider than the world used to
 * be able to draw; what changed is WHO earns it.
 *
 * Geometric by construction (13 * (62/13)^(k/7), rounded), so each rung is
 * ~25% wider than the one below. On a log-scaled ladder that makes every rung
 * cost the same multiple of traffic and read as the same step on screen.
 */
export const LANE_WIDTH_RUNGS: readonly number[] = [13, 16, 20, 25, 32, 40, 50, 62]

/** compose.py:189-190 — the two fixed civic points every lane hangs off. */
export const SQUARE: Point = { x: 1200, y: 1010 }
export const GREAT: Point = { x: 1200, y: 800 }

/** A lane's role, so the renderer and the clearance rules can both reason about it. */
export type LaneKind = 'main' | 'spur' | 'district' | 'coastal' | 'driveway'

/**
 * THE PLACE AT A LANE'S FAR END — what has to exist for the lane to, and what
 * measures how much it is walked.
 *
 * Four kinds, because the island really does have four kinds of destination and
 * collapsing them would mean inventing a measurement for one of them:
 *
 *   `landing`  the cove. Open on day zero: a cabinet exists because somebody
 *              came ashore, so the track up from the water is as true on the
 *              hatch frame as the treeline. Its TRAFFIC is still measured (the
 *              quay's ladder), so it starts as a footpath and becomes a road.
 *   `built`    a measured place. It exists when any of `objects` has built
 *              something, and `traffic` names the ladder whose rung index is
 *              its usage — the SAME ladder that grows the building there, so
 *              the number is one the org already publishes.
 *   `district` civic ground with furniture but NO ladder anywhere in
 *              growth-ladders.yml (the dojo, the crossroads). It appears with
 *              the village that furnishes it and stays at the bottom rung
 *              forever, because nothing measures it. Gating it on an invented
 *              ladder name would be a switch wired to the empty set — the
 *              defect ./dressing records paying for with the market stall.
 *   `link`     a shore path between two other lanes. It exists when both of
 *              them do and is never more than a desire path: nobody's
 *              destination is halfway along it.
 */
export type LaneEnd =
  | { at: 'landing'; traffic: string }
  | { at: 'built'; objects: readonly string[]; traffic: string }
  | { at: 'district' }
  | { at: 'link'; between: readonly string[] }

export interface LaneSpec {
  key: string
  kind: LaneKind
  /** Control points, before the wobble. */
  points: readonly Point[]
  /** What is at the far end. */
  to: LaneEnd
  /**
   * A ladder that must ALSO have built something at the NEAR end, for the one
   * lane that does not hang off the square. `north` starts at the great house's
   * forecourt, so without a great house it would be a carriageway floating in
   * open grass with a junction at neither end.
   */
  from?: string
}

/**
 * The network: control points verbatim from compose.py:216-235, with each
 * lane's DESTINATION carried alongside it in place of the old era flag.
 *
 * Every `traffic` name below is a real ladder in cabinet/world/growth-ladders.yml
 * and is THAT DESTINATION'S OWN ladder — the metric that grows the thing there
 * is the metric that widens the path to it. Inventing a metric per lane would
 * be a second measurement of the same place, free to disagree with the first.
 */
export const LANE_SPECS: readonly LaneSpec[] = [
  {
    // The harbour road. Day zero, because the landing is where everyone
    // arrives; its width is the quay's own ladder (commits since genesis),
    // which is what actually crosses it.
    key: 'main',
    kind: 'main',
    points: [SQUARE, { x: 1200, y: 1140 }, { x: 1215, y: 1270 }, { x: 1200, y: 1360 }],
    to: { at: 'landing', traffic: 'quay' },
  },
  {
    // The forecourt. A forecourt is a consequence of there being a house with a
    // front, so it appears with the great house and widens on the sessions
    // that ladder counts.
    key: 'forecourt',
    kind: 'spur',
    points: [SQUARE, GREAT],
    to: { at: 'built', objects: ['great_house'], traffic: 'great_house' },
  },
  {
    key: 'north',
    kind: 'district',
    points: [GREAT, { x: 1190, y: 640 }, { x: 1200, y: 470 }, { x: 1200, y: 380 }],
    to: { at: 'built', objects: ['law_plot'], traffic: 'law_plot' },
    from: 'great_house',
  },
  {
    key: 'ne',
    kind: 'district',
    points: [{ x: 1250, y: 760 }, { x: 1420, y: 640 }, { x: 1580, y: 520 }],
    to: { at: 'built', objects: ['library'], traffic: 'library' },
  },
  {
    key: 'east',
    kind: 'district',
    points: [{ x: 1270, y: 950 }, { x: 1500, y: 900 }, { x: 1720, y: 830 }],
    to: { at: 'built', objects: ['workshop'], traffic: 'workshop' },
  },
  {
    // The field track. Two things stand at that end — the barn and the plots —
    // and either one is a reason to walk down there. Its traffic is the
    // outbuildings' ladder, the one that measures the place itself.
    key: 'se',
    kind: 'district',
    points: [{ x: 1290, y: 1060 }, { x: 1480, y: 1120 }, { x: 1650, y: 1180 }],
    to: { at: 'built', objects: ['outbuildings', 'field_plots'], traffic: 'outbuildings' },
  },
  {
    key: 'west',
    kind: 'district',
    points: [{ x: 1140, y: 980 }, { x: 930, y: 930 }, { x: 720, y: 860 }],
    to: { at: 'built', objects: ['officer_dwellings'], traffic: 'officer_dwellings' },
  },
  {
    // The dojo. growth-ladders.yml measures no `dojo`, so this stays a desire
    // path however much training happens — an honest hairline, not a zero
    // dressed up as a road.
    key: 'nw',
    kind: 'district',
    points: [{ x: 1150, y: 720 }, { x: 960, y: 600 }, { x: 800, y: 500 }],
    to: { at: 'district' },
  },
  {
    // The crossroads mailbox. Same: no ladder, so no widening, ever.
    key: 'sw',
    kind: 'district',
    points: [{ x: 1150, y: 1090 }, { x: 980, y: 1170 }, { x: 840, y: 1220 }],
    to: { at: 'district' },
  },
  {
    key: 'coastal',
    kind: 'coastal',
    points: [{ x: 720, y: 860 }, { x: 620, y: 1030 }, { x: 700, y: 1210 }, { x: 840, y: 1220 }],
    to: { at: 'link', between: ['west', 'sw'] },
  },
]

/**
 * The LOT-BEARING lanes (compose.py:244-251). These are the same roads under
 * slightly different control points: the reference walks lots along a lane
 * whose ends differ from the painted one (`west` starts further out so the
 * officer row has frontage on both sides). Kept as its own table for exactly
 * the reason the reference keeps it: lots front a road's IDEALISED line, and
 * snapping them to the wobbled paint would scatter the row.
 */
export const LOT_LANES: Record<string, readonly Point[]> = {
  west: [{ x: 742, y: 742 }, { x: 656, y: 900 }, { x: 712, y: 1050 }],
  north: [{ x: 1200, y: 800 }, { x: 1190, y: 640 }, { x: 1200, y: 470 }, { x: 1200, y: 380 }],
  east: [{ x: 1270, y: 950 }, { x: 1500, y: 900 }, { x: 1720, y: 830 }],
  ne: [{ x: 1250, y: 760 }, { x: 1420, y: 640 }, { x: 1580, y: 520 }],
  se: [{ x: 1290, y: 1060 }, { x: 1480, y: 1120 }, { x: 1650, y: 1180 }],
  main: [{ x: 1200, y: 1010 }, { x: 1200, y: 1140 }, { x: 1215, y: 1270 }, { x: 1200, y: 1360 }],
}

/**
 * One painted lane: the wobbled centreline, CLIPPED TO LAND, plus the width it
 * is painted at.
 *
 * `runs` is the centreline cut into its on-land pieces — one run for a lane
 * that never leaves the island, several for one that crosses an inlet, none at
 * all for a lane whose whole extent is offshore on this seed. Every sample in
 * every run stands on land; the painted band still has a width, so the renderer
 * intersects the drawn surface with `coast.land` exactly as compose.py does.
 */
export interface Lane {
  key: string
  kind: LaneKind
  /** How much its destination is used — LANE_WIDTH_RUNGS at its traffic rung. */
  width: number
  /**
   * What it is PAVED with: the org-wide road ladder's rung.
   *
   * A SEPARATE AXIS FROM THE WIDTH ON PURPOSE (Captain, 2026-07-27). The road
   * ladder's rungs are materials — dirt_path, dirt_worn, gravel_road,
   * cobbled_road — and reading them as sizes made a busy library and a
   * forgotten dojo the same width whenever the org's overall traffic moved.
   * The renderer must PAINT this, or the org's road maturity stops reaching
   * the frame at all and a real rung change moves nothing.
   */
  surface: RoadRung
  /** On-land runs of dense centreline samples, ~16 layout px apart. */
  runs: Point[][]
}

/**
 * compose.py lane(): walk the polyline at ~16px, wobbling with a sine of the
 * parameter and the segment origin. Deterministic by construction — there is
 * no RNG in the reference here either, and that is why the same org always
 * gets the same street.
 */
export function laneCentreline(points: readonly Point[], jitter = 9): Point[] {
  const out: Point[] = []
  let prev = points[0]
  for (let i = 1; i < points.length; i++) {
    const p = points[i]
    const steps = Math.max(2, Math.floor(hypot(p.x - prev.x, p.y - prev.y) / 16))
    for (let s = 0; s <= steps; s++) {
      const t = s / steps
      const x = prev.x + (p.x - prev.x) * t + Math.sin(t * 3.1 + prev.x) * jitter
      const y = prev.y + (p.y - prev.y) * t + Math.cos(t * 2.7 + prev.y) * jitter * 0.6
      out.push({ x, y })
    }
    prev = p
  }
  return out
}

/**
 * The step at which a lane SEGMENT is checked for land between its endpoints.
 * 2px is the finest coastline raster this library builds (compose.py's STEP),
 * and finer than the 6px at which checks/world_checks.py walks a lane — so a
 * channel that the check can see is a channel this clip has already cut.
 */
const SEGMENT_PROBE_STEP = 2

/**
 * Cut a centreline into its on-land runs (compose.py:343's landmask clip).
 *
 * THE SEGMENTS ARE CHECKED, NOT JUST THE STATIONS. Testing only the ~16px
 * stations leaves the line free to cross anything narrower than the gap between
 * two of them, and both the renderer (which draws the polyline) and the
 * occupancy field (which interpolates along it) then carry the road over that
 * water. Measured with station-only clipping across 80 seeds: 79 clean, one
 * seed still bridging an inlet. So a run continues only while the whole segment
 * to the next station stays on land.
 *
 * A single-station run is KEPT rather than discarded: the reference paints a
 * disc at every station, so one station on a spit of land does paint there, and
 * dropping it would make the layout claim less road than the frame shows.
 */
export function clipToLand(
  path: readonly Point[],
  onLand: (x: number, y: number) => boolean
): Point[][] {
  const segmentOnLand = (a: Point, b: Point): boolean => {
    const n = Math.ceil(hypot(b.x - a.x, b.y - a.y) / SEGMENT_PROBE_STEP)
    for (let i = 1; i < n; i++) {
      const t = i / n
      if (!onLand(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t)) return false
    }
    return true
  }
  const runs: Point[][] = []
  let cur: Point[] = []
  const cut = () => {
    if (cur.length > 0) runs.push(cur)
    cur = []
  }
  for (const p of path) {
    if (!onLand(p.x, p.y)) {
      cut()
      continue
    }
    const prev = cur[cur.length - 1]
    if (prev && !segmentOnLand(prev, p)) cut()
    cur.push(p)
  }
  cut()
  return runs
}

/**
 * The painted width for a destination's usage rung.
 *
 * CLAMPED AT BOTH ENDS, and the low end is the one that matters: a ladder that
 * has never been measured hands this a 0 and an absent one hands it whatever
 * `countOf` returns for a missing key, which is also 0. Both mean "nothing has
 * walked here yet", and both must land on the hairline rather than on an
 * exception or a NaN width that the paint stage would silently drop.
 */
export function laneWidthAt(usageRung: number): number {
  const n = Number.isFinite(usageRung) ? Math.trunc(usageRung) : 0
  return LANE_WIDTH_RUNGS[Math.max(0, Math.min(LANE_WIDTH_RUNGS.length - 1, n))]
}

/**
 * The lane occupancy field: "is this point on a carriageway?"
 *
 * compose.py samples a painted, blurred, thresholded raster. The equivalent
 * without a bitmap is the union of the discs that raster was painted from —
 * radius w/2 across, w/2*0.72 down, because a circle on the ground projects
 * squashed. Bucketed on a uniform grid because the scatter stage asks this
 * question tens of thousands of times.
 */
export interface LaneField {
  readonly lanes: readonly Lane[]
  /** compose.py on_path(). `grow` widens the disc, for a "near" query. */
  onLane(x: number, y: number, grow?: number): boolean
  /** compose.py near_path(x,y,r): the same 3x3 probe the reference uses. */
  nearLane(x: number, y: number, r?: number): boolean
}

/**
 * The vertical squash of a lane's occupancy disc — a circle on the ground
 * projects flattened on a 2:1 screen.
 *
 * EXPORTED because the thing that PAINTS the road has to paint this exact
 * shape. It was private until 2026-07-27, and the first frame ever rendered
 * from this layout put the harbourmaster's hut on a lane: the rules had cleared
 * it against a squashed ellipse while the renderer drew a round stroke 39%
 * taller in y, so the painted road reached ground the rules had never reserved.
 * check_on_road caught it on first contact. One constant, emitted to the
 * renderer through the draw list, is what stops that class returning.
 */
export const LANE_SQUASH = 0.72
const SQUASH = LANE_SQUASH
const BUCKET = 64

export function buildLaneField(lanes: readonly Lane[]): LaneField {
  // grid of (x, y, halfWidth) discs
  const grid = new Map<number, number[]>()
  // Offset before packing so a negative bucket (a query near the canvas edge)
  // can never alias a positive one — a collision here would report clear road
  // as occupied, silently, in one corner of the map only.
  const key = (gx: number, gy: number) => (gx + 1024) * 8192 + (gy + 1024)
  let maxHalf = 1
  const add = (x: number, y: number, half: number) => {
    const k = key(Math.floor(x / BUCKET), Math.floor(y / BUCKET))
    const cell = grid.get(k)
    if (cell) cell.push(x, y, half)
    else grid.set(k, [x, y, half])
  }
  for (const lane of lanes) {
    const half = lane.width / 2
    if (half > maxHalf) maxHalf = half
    // RESAMPLE rather than trust the caller's spacing. The field is a union of
    // discs, so any gap wider than a disc is a hole in the road that every
    // clearance rule then reports as clear ground. laneCentreline already
    // emits ~16px apart, but a Lane is a plain object anyone can construct,
    // and a hole here fails SILENTLY and only in one place on the map.
    //
    // RUN BY RUN, never across the gap between two runs: the gap is where the
    // land clip cut the road out, and interpolating over it would put the
    // occupancy field back on the water the clip just removed.
    // BOUNDED BY THE SQUASHED RADIUS, NOT THE HALF-WIDTH, so the band does not
    // NECK between samples. A disc reaches `half` across but only `half*SQUASH`
    // down, so stepping down a vertical run by `half` puts consecutive centres
    // 1/0.72 of a y-radius apart and the union pinches to 0.72 of its width
    // halfway between them. NOT A HOLE — measured, the discs still overlap at
    // every step this function can produce — but a visible scallop: 1.8px of
    // necking on the 13px path the traffic model starts every lane at, drawn as
    // a chain of beads rather than a track. Stepping by the SQUASHED radius
    // instead holds the pinch under a pixel. The renderer's own mask
    // (world-capture/raster.py _lane_mask) carries the same bound, because the
    // painted road and the reserved road must be one surface.
    const spacing = Math.max(2, Math.min(half * SQUASH, 16))
    for (const run of lane.runs) {
      for (let i = 0; i < run.length; i++) {
        const a = run[i]
        add(a.x, a.y, half)
        const b = run[i + 1]
        if (!b) continue
        const len = hypot(b.x - a.x, b.y - a.y)
        const n = Math.floor(len / spacing)
        for (let s = 1; s < n; s++) {
          const t = s / n
          add(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, half)
        }
      }
    }
  }

  const onLane = (x: number, y: number, grow = 0): boolean => {
    const reach = maxHalf + grow
    const gx0 = Math.floor((x - reach) / BUCKET)
    const gx1 = Math.floor((x + reach) / BUCKET)
    const gy0 = Math.floor((y - reach / SQUASH) / BUCKET)
    const gy1 = Math.floor((y + reach / SQUASH) / BUCKET)
    for (let gx = gx0; gx <= gx1; gx++) {
      for (let gy = gy0; gy <= gy1; gy++) {
        const cell = grid.get(key(gx, gy))
        if (!cell) continue
        for (let i = 0; i < cell.length; i += 3) {
          const hw = cell[i + 2] + grow
          const dx = (x - cell[i]) / hw
          const dy = (y - cell[i + 1]) / (hw * SQUASH)
          if (dx * dx + dy * dy <= 1) return true
        }
      }
    }
    return false
  }

  return {
    lanes,
    onLane,
    nearLane(x, y, r = 46) {
      for (const dx of [-r, 0, r]) for (const dy of [-r, 0, r]) if (onLane(x + dx, y + dy)) return true
      return false
    },
  }
}

/**
 * WHAT THE STATE HAS TO ANSWER for a lane to be worn, and how wide.
 *
 * Two questions and a flag, deliberately narrow: the lane stage runs BEFORE the
 * structures are placed (index.ts stage 2 — everything downstream samples the
 * road, so it has to exist first), which means it cannot ask "did that building
 * land?". It asks the same predicates the structure stage itself is gated on,
 * so the two cannot disagree about whether a place exists.
 */
export interface LaneDemand {
  /** Has this ladder built anything? (presentRung, or a positive count.) */
  present(object: string): boolean
  /**
   * Its VISIBLE RUNG INDEX — the destination's usage, already folded onto its
   * own log ladder by era-engine and carried in the state's counts.
   */
  usage(object: string): number
  /**
   * Hamlet and above: the districts with furniture and no ladder exist because
   * somebody is using them, and the era is the only thing that says so.
   */
  village: boolean
}

/**
 * The ladder that measures a lane's traffic, or null when nothing does.
 *
 * READ OFF THE SPEC TABLE rather than re-typed at the call site: a drive joins
 * a carriageway, so it must widen on the SAME number, and two tables would be
 * one edit away from a drive and its road disagreeing about how busy the place
 * they both serve is.
 */
export function laneTrafficLadder(key: string, specs: readonly LaneSpec[] = LANE_SPECS): string | null {
  const to = specs.find((s) => s.key === key)?.to
  return to && (to.at === 'built' || to.at === 'landing') ? to.traffic : null
}

/** Does this lane's far end exist, and how much is it used? */
function laneTraffic(spec: LaneSpec, demand: LaneDemand, built: ReadonlySet<string>): number | null {
  const to = spec.to
  if (spec.from !== undefined && !demand.present(spec.from)) return null
  switch (to.at) {
    case 'landing':
      // The beach is there on day zero; only its traffic is measured.
      return demand.usage(to.traffic)
    case 'built':
      return to.objects.some((o) => demand.present(o)) ? demand.usage(to.traffic) : null
    case 'district':
      return demand.village ? 0 : null
    case 'link':
      return to.between.every((k) => built.has(k)) ? 0 : null
  }
}

/**
 * The network this state has actually worn, at the widths its use has earned.
 *
 * `onLand` is REQUIRED, not optional with a permissive default: a default of
 * "everywhere is land" is how the land clip would go missing again on the one
 * call site that forgot it, silently, and only on the seeds where it matters.
 * A lane with no on-land run at all is dropped — a road wholly offshore is not
 * a road.
 *
 * THE ORDER OF `specs` IS LOAD-BEARING for a `link` lane: it can only ask
 * whether the lanes it joins were built, so those must come first. The one
 * link in the table (`coastal`) sits last, and the arm that proves it is a
 * behavioural one — a link whose partners are absent is absent.
 */
export function buildLanes(
  road: RoadRung,
  onLand: (x: number, y: number) => boolean,
  demand: LaneDemand,
  specs: readonly LaneSpec[] = LANE_SPECS
): Lane[] {
  const out: Lane[] = []
  const built = new Set<string>()
  for (const spec of specs) {
    const usage = laneTraffic(spec, demand, built)
    if (usage === null) continue
    const width = laneWidthAt(usage)
    // A YOUNG PATH WANDERS AND AN OLD ONE DOES NOT. The wobble used to be
    // keyed off the era ("a camp's ONE track is a worn track, so it wobbles
    // more"); under the traffic model the same truth is keyed off the lane
    // itself, so a hairline through the trees still wanders on a mature island
    // and a trunk road does not straighten just because the org is young.
    const runs = clipToLand(laneCentreline(spec.points, usage >= 3 ? 9 : 12), onLand)
    if (runs.length === 0) continue
    built.add(spec.key)
    out.push({ key: spec.key, kind: spec.kind, width, surface: road, runs })
  }
  return out
}
