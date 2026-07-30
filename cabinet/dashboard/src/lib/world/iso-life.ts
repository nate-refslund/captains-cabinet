/**
 * ISO-LIFE — where the world's MOVING things stand, in the composed layout's
 * own space.
 *
 * WHAT WAS MISSING. `drawDynamics` (top-down) carries walkers, life sites,
 * construction crews, apprentices, chimney smoke and window glow.
 * `drawIsoDynamics` carried the lighthouse lamp, the roof cutaway and — since
 * PR #292 — the product archipelago, and nothing else. The world lost MOTION
 * when it gained ownership of its art, and two of the losses are not
 * decoration: an officer could not be clicked anywhere on the island, and a
 * PENDING RUNG WAS INVISIBLE, so the frame said nothing at all where it used
 * to say "this is about to change".
 *
 * THE SPLIT THIS MODULE IS BUILT ON, and the reason it is a port rather than a
 * wiring job. `lifeStep` is ONE reducer for both kernels and it must stay that
 * way — it is the thing that decides WHETHER a walker walks. Its output divides
 * cleanly in two:
 *
 *   MEASURED, projection-independent — a commuter's `progress` (0..1 along a
 *   road, engine-mapped by contract), which district they are walking to, their
 *   verb bubble, a site's element/phase/witness, its CREW SIZE, each wright's
 *   action and swing frame, an apprentice's officer and spawn proof. None of it
 *   names a coordinate system. All of it is carried through untouched.
 *
 *   GEOMETRY, top-down by construction — `roadPoint(t)`'s tile polyline, a
 *   site's `footprint` in TILES, a wright's perimeter tile, a fauna anchor, an
 *   apprentice's tile offset. Every one of those names different ground under
 *   iso, and drawing them here would put a walker in open sea and call it a
 *   feature.
 *
 * So this module re-sites the first half on the SECOND kernel's own measured
 * geometry: the commute walks the `main` lane the layout actually laid, the
 * yard is the great house's own frontage, a site sits on the lot its element
 * would be built on, and the pending mark stands at the sprite whose rung is
 * moving. Nothing invents a place that the layout does not already know.
 *
 * WHICH SPACE. Layout px — compose.py's 2400x1760 screen space, the space every
 * other on-island module here works in (`iso-layout/*`, `iso-quay`,
 * `iso-scene`). It is NOT a strict 2:1 iso projection of a ground plane: the
 * island is composed at an 0.82:1 aspect and lane paint uses its own
 * `LANE_SQUASH` of 0.72. So the ground ellipses below use LANE_SQUASH, the
 * layout's own ground-ellipse aspect, and NOT the projection kernel's 2:1 —
 * which `iso-lanes` correctly uses out on the flat open sea, where the fan is
 * sited by the kernel rather than by the compositor. Importing the wrong one of
 * those two constants is the kind of mistake that looks right in a test and
 * wrong on the frame.
 *
 * PURE: no clocks, no unseeded randomness, no IO, no DOM (determinism ratchet).
 */
import { fnv1a } from './hash'
import { LANE_PAINT_SQUASH } from './iso-scene'
import { polyPoint, LOT_SEPARATION } from './iso-layout/lots'
import type { Layout, Structure } from './iso-layout'
import type { Point } from './iso-layout/space'
import { CHAR_FRAME_H, CHAR_FRAME_W, type CharFacing } from './sprites'
import type { CommuterOut, SiteOut } from './life/life'
import type { ApprenticeFigure } from './life/apprentices'
import type { WrightAction } from './life/sites'

// ── how big a person is on this atlas ───────────────────────────────────────

/**
 * A DRAWN PERSON'S HEIGHT in layout px, and where the number comes from.
 *
 * THE SHIPPED PACK HAS NO HUMANS (all 182 frames enumerated at the port's step
 * 3 — zero character sprites), so a person's scale cannot be read off the atlas
 * directly and has to be derived from things in it whose real height is not in
 * dispute. Two independent objects agree: `signpost` is drawn at dh=31 for a
 * post of about 2 m, and `town_streetlight` at dh=76 for a lamp standard of
 * about 4 m — 15.5 and 19 px per metre. A 1.7 m person therefore lands at
 * 26-32 px, and 30 is inside both readings.
 *
 * IT IS PINNED TO THE PACK RATHER THAN TO THIS COMMENT: iso-life.test.ts
 * asserts a person stands taller than the pack's `barrel_single` and shorter
 * than its `law_post`, both measured from the SHIPPED world-pack.json. If the
 * atlas is ever re-scaled, that arm reds instead of the world quietly filling
 * with giants — which is what a bare literal here would have done.
 *
 * The character sheets are 16x32 native, so the scale works out at almost
 * exactly 1:1. That is a happy accident of two independently-chosen art scales
 * and NOT a licence to drop the constant: the day either one moves, the ratio
 * is what has to change.
 */
export const PERSON_H_PX = 30
export const PERSON_SCALE = PERSON_H_PX / CHAR_FRAME_H
export const PERSON_W_PX = CHAR_FRAME_W * PERSON_SCALE

// ── the commute road ────────────────────────────────────────────────────────

/**
 * WHICH LANE THE COMMUTE WALKS: `main`, the harbour road.
 *
 * It is not a choice. `commuteStep` moves an officer between exactly two
 * districts — `village` and `quay` (life/commute.ts `District`) — and
 * `iso-layout/lanes.ts` lays exactly one carriageway between the village square
 * and the landing, from day zero, "because the landing is where everyone
 * arrives". Walking any other lane would be walking somewhere the reducer never
 * said anyone went.
 */
export const COMMUTE_LANE_KEY = 'main'

/**
 * The walkable road as ONE polyline, or null when the island has none.
 *
 * `Lane.runs` is the centreline cut into its ON-LAND pieces — a lane that
 * crosses an inlet is two runs with a gap, exactly as the reference paints it.
 * The runs are concatenated in order here, which means a walker on a
 * multi-run road crosses the gap rather than stopping at it. That is a real and
 * stated approximation, and it is the right one: the alternative — walking only
 * the longest run — silently shortens the journey so that `progress` 1.0 no
 * longer means "arrived at the quay", which would make the ANIMATION disagree
 * with the reducer's own state. Measured on the shipped seed at every era: the
 * main lane is a SINGLE run, so no walker crosses a gap on the world as it
 * ships (pinned in iso-life.test.ts).
 *
 * null when the layout laid no main lane at all — an honest absence, and the
 * draw pass renders no walkers rather than inventing a route.
 */
export function commuteRoad(layout: Pick<Layout, 'lanes'>): Point[] | null {
  const lane = layout.lanes.find((l) => l.key === COMMUTE_LANE_KEY)
  if (!lane) return null
  const pts: Point[] = []
  for (const run of lane.runs) pts.push(...run)
  return pts.length >= 2 ? pts : null
}

/**
 * SCREEN FACING from a step along the road.
 *
 * The character sheets are four-directional and were drawn for a top-down
 * world; the pack ships no isometric human art, so a walker's facing can only
 * ever be the best of four. It is chosen in SCREEN space — the space the reader
 * judges it in — rather than by un-squashing back to a ground vector: the
 * sprite is a flat image on the frame, and matching the direction the eye sees
 * it travel is the only claim it can honestly make.
 */
export function isoFacing(dx: number, dy: number): CharFacing {
  if (Math.abs(dx) > Math.abs(dy)) return dx >= 0 ? 'right' : 'left'
  return dy >= 0 ? 'down' : 'up'
}

/** A figure the frame draws and the pick can name. */
export interface IsoFigure {
  /** Pool key — stable within a frame. */
  id: string
  /** The REAL actor this figure is. Walkers resolve to their officer. */
  slug: string
  kind: 'officer' | 'walker' | 'apprentice'
  /** Base centre (feet), in layout px. */
  x: number
  y: number
  facing: CharFacing
  anim: 'walk' | 'work'
  /** Dimmed when the actor is not present. */
  present: boolean
  /** Drawn scale relative to PERSON_SCALE (apprentices stand smaller). */
  scale: number
}

/**
 * The commute walkers, placed on the road the layout laid.
 *
 * `progress` runs 0..1 from the district the officer LEFT to the one they are
 * walking to, so the road parameter is `progress` toward the quay and
 * `1 - progress` toward the village — the same two lines the top-down path
 * uses, because it is the reducer's contract and not a rendering choice. The
 * road's t=0 end is the village square and t=1 is the shore, which is the
 * direction `LANE_SPECS.main` is authored in.
 */
export function isoWalkers(
  road: Point[] | null,
  commuters: readonly CommuterOut[]
): IsoFigure[] {
  if (!road || road.length < 2) return []
  const out: IsoFigure[] = []
  for (const cm of commuters) {
    const t = cm.walk.to === 'quay' ? cm.progress : 1 - cm.progress
    const { at, tangent } = polyPoint(road, Math.max(0, Math.min(1, t)))
    // The GLANCE is a real seeded event (two commuters passing at the
    // crossroads) and it turns the head, exactly as the top-down path turns it.
    const facing: CharFacing = cm.glance
      ? 'left'
      : isoFacing(
          cm.walk.to === 'quay' ? tangent.x : -tangent.x,
          cm.walk.to === 'quay' ? tangent.y : -tangent.y
        )
    out.push({
      id: `walker:${cm.slug}`,
      slug: cm.slug,
      kind: 'walker',
      x: at.x,
      y: at.y,
      facing,
      anim: 'walk',
      present: true,
      scale: 1,
    })
  }
  return out
}

// ── the officers' yard ──────────────────────────────────────────────────────

/**
 * How far out of the great house's front the yard sits, as a multiple of the
 * lot separation. A lot is `LOT_SEPARATION` across centre-to-centre, so a
 * fraction of it is the layout's own unit for "just outside the door" and no
 * new distance constant enters the world.
 */
export const YARD_SETBACK = LOT_SEPARATION * 0.34
/**
 * Lateral spread of the yard fan, same unit.
 *
 * WIDE ENOUGH THAT THE NAMES DO NOT COLLIDE, which is a browser finding: at
 * 0.30 the five officers of a real cabinet stood in a 50px huddle, and
 * `layoutLabels` then displaced all five DOM chips into a column 100px to one
 * side — every name on the frame, none of them on the person it named. The
 * yard has to be a yard.
 */
export const YARD_SPREAD = LOT_SEPARATION * 0.62
/** Depth between the two ranks of the fan. */
export const YARD_RANK_STEP = 34

/**
 * WHERE THE OFFICERS STAND when no roof is off.
 *
 * The top-down world puts them in the great house YARD — `gh.y + gh.h + 1`,
 * one tile in front of the building. The iso layout knows the same place far
 * better than a tile offset does: the great house stands on a LOT, and a lot
 * carries `road` (the point on the lane it fronts) and `face` (the unit vector
 * from road to plot — which way the frontage looks). So the yard is the
 * structure's own base centre, stepped back out toward its road along `-face`,
 * with the fan running across the frontage.
 *
 * NO GREAT HOUSE MEANS NO OFFICERS ANYWHERE — the same honest answer
 * `pick.officerSlots` gives, for the same reason: the yard IS the great
 * house's, and a cabinet that has not built one has nowhere for them to stand.
 * A structure with no lot (repulsion can strand one) falls back to a straight
 * step down-screen, which is the direction a frontage faces on this compass
 * layout when nothing else says otherwise.
 *
 * THE FAN IS EVEN AND THE HASH IS THE JITTER, not the other way round. The
 * top-down yard places each officer at `fnv1a('officer:<slug>')` alone, and a
 * purely hashed row clumps: measured in a browser on the real five-officer
 * cabinet, they stood inside 50 layout px and the DOM name chips collided into
 * an unreadable column. Spacing by INDEX guarantees separation, and the same
 * `fnv1a('officer:<slug>')` still decides where inside their slot each one
 * stands, so no two cabinets look alike and a reload never moves anyone.
 *
 * The cost, stated: an officer's absolute spot now depends on how many
 * officers there are, so a new officer shifts the row. That is the correct
 * trade — a row nobody can read is worse than a row that widens when the
 * cabinet grows, and the iso layout already computes lot positions from state
 * rather than fixing them at birth.
 */
export interface YardOptions {
  /**
   * Which district each officer is IN, from the reducer — `village` or `quay`.
   *
   * THE DEFECT IT CLOSES, measured in a browser 2026-07-29: `commuteStep`
   * tracks a district per officer and moves them between the two, and the first
   * version of this function stood EVERY non-walking officer in the great house
   * yard. So an officer walked the harbour road, arrived at the quay, and
   * reappeared at the great house — a round trip to nowhere, with the world
   * showing the walk and then silently discarding its result. `districts` is
   * measured state; a frame that animates the transition and not the outcome is
   * telling half the truth.
   */
  districts?: Record<string, string>
  /** The commute road, so an officer at the quay stands where it ends. */
  road?: Point[] | null
}

export function isoOfficerYard(
  layout: Pick<Layout, 'structures'>,
  slugs: readonly string[],
  present: (slug: string) => boolean,
  opts: YardOptions = {}
): IsoFigure[] {
  const gh = layout.structures.find((s) => s.role === 'great_house')
  if (!gh) return []
  const home = yardOrigin(gh)
  // THE QUAY END OF THE ROAD, which is where the walk actually finishes — never
  // a second guess at where the harbour is. With no road there is no quay to
  // stand at, so everyone stays at the house and the world says nothing it
  // cannot support.
  const road = opts.road
  const quay =
    road && road.length >= 2
      ? (() => {
          const end = road[road.length - 1]
          const prev = road[Math.max(0, road.length - 3)]
          const dx = end.x - prev.x
          const dy = end.y - prev.y
          const len = Math.hypot(dx, dy) || 1
          const o = { x: dx / len, y: dy / len }
          return { at: end, out: o, across: { x: -o.y, y: o.x } }
        })()
      : null
  const span = Math.max(1, slugs.length - 1)
  return slugs.map((slug, i) => {
    const out = quay && opts.districts?.[slug] === 'quay' ? quay : home
    const h = fnv1a(`officer:${slug}`)
    // Two rows, alternating, so a wide cabinet does not draw one long line —
    // the same `i % 2` the top-down yard uses for its second rank.
    const rank = i % 2
    const slot = slugs.length === 1 ? 0 : i / span - 0.5
    const jitter = (((h >>> 4) % 1000) / 1000 - 0.5) * (0.34 / span)
    const lateral = slot + jitter
    return {
      id: `officer:${slug}`,
      slug,
      kind: 'officer' as const,
      x: out.at.x + out.across.x * lateral * 2 * YARD_SPREAD + out.out.x * rank * YARD_RANK_STEP,
      y: out.at.y + out.across.y * lateral * 2 * YARD_SPREAD + out.out.y * rank * YARD_RANK_STEP,
      facing: 'down' as CharFacing,
      anim: 'work' as const,
      present: present(slug),
      scale: 1,
    }
  })
}

/** The yard's origin, its outward normal and its across vector — layout px. */
function yardOrigin(st: Structure): { at: Point; out: Point; across: Point } {
  // `face` runs road -> plot, so the way OUT of the front door is its negation.
  const f = st.lot?.face
  const out: Point = f ? { x: -f.x, y: -f.y } : { x: 0, y: 1 }
  // Perpendicular in layout px: the frontage runs across the screen, which is
  // how the compositor's own lot rows run (iso-layout/lots.ts `lotsAlong`
  // offsets by a plain 2D lane normal in this same space).
  const across: Point = { x: -out.y, y: out.x }
  return {
    at: { x: st.at.x + out.x * YARD_SETBACK, y: st.at.y + out.y * YARD_SETBACK },
    out,
    across,
  }
}

// ── construction sites ──────────────────────────────────────────────────────

/**
 * WHICH LOT GROUP AN ELEMENT IS BUILT ON.
 *
 * `composeLayout` builds this association inline (its `built[]` fold pairs
 * `['memory','library']`, `['works','workshop']`, `['fields','outbuildings']`,
 * residential -> officer_dwelling, centre -> great_house) and does not export
 * it, so it is restated here — and, because a restated table is a second place
 * for the answer to be wrong, iso-life.test.ts COMPOSES A REAL LAYOUT at a
 * state where each element is built and asserts the structure landed on the lot
 * this table names. The sensor is wired to the live artifact, not to the table.
 *
 * An element with no entry here has no plot in the layout, and a site for it
 * therefore has no honest place to stand. It is REPORTED rather than guessed —
 * see `isoSites`' `unplaced`.
 */
export const SITE_LOT_GROUP: ReadonlyMap<string, string> = new Map<string, string>([
  ['library', 'memory'],
  ['workshop', 'works'],
  ['outbuildings', 'fields'],
  ['officer_dwellings', 'residential'],
  ['officer_dwelling', 'residential'],
  ['great_house', 'centre'],
])

/** A worksite pad on the ground, in layout px. */
export interface IsoSitePad {
  /** The WorkSite's own id — what the pick returns and the card opens on. */
  id: string
  element: string
  /** Pad centre. */
  cx: number
  cy: number
  /** Ground ellipse radii (ry is already LANE_PAINT_SQUASH-flattened). */
  rx: number
  ry: number
  /** 0..1 — the reducer's own progress, carried through untouched. */
  progress: number
  phase: SitePhaseName
  crew: IsoWright[]
}

export type SitePhaseName = 'clearing' | 'raising' | 'finishing' | 'reveal'

export interface IsoWright {
  id: string
  x: number
  y: number
  action: WrightAction
  frame: number
  facing: CharFacing
}

/**
 * Where a site for `element` stands, and how big its pad is — or null.
 *
 * ONE RULE, and it covers the two genuinely different states of the world
 * without a flag distinguishing them: THE WORKS GO ON THE FIRST LOT OF THE
 * ELEMENT'S GROUP THAT NOTHING STANDS ON YET, and if every lot in the group is
 * taken, they go around the building that is already there.
 *
 *   A NEW BUILD lands on free ground. This is the case a naive "find the
 *   structure for this element" lookup gets WRONG and does so invisibly: a
 *   cabinet with four dwellings and a fifth going up has four
 *   `officer_dwelling` structures, so that lookup would raise the scaffolding
 *   around dwelling number one — the world claiming work on a house that has
 *   stood for months. `officer_dwellings` is a COUNT ladder and this is its
 *   normal case, not an edge one.
 *
 *   AN UPGRADE — `library` going from shelf_row to a wing, `great_house` from
 *   hall to hall — has exactly one lot and it is occupied, so the rule lands on
 *   the structure by itself and the works are around the thing being changed.
 *
 * A LOT IS OCCUPIED WHEN A STRUCTURE CARRIES IT, not when something is near it:
 * `Structure.lot` is the layout's own record of which plot it was raised on, so
 * this is an exact identity rather than a distance guess that a repulsion push
 * could defeat.
 *
 * The two sizes are both the layout's own numbers — the structure's drawn width
 * plus a working margin, or a fraction of `LOT_SEPARATION`, the plot spacing
 * that bounds the largest pad that cannot reach its neighbour. Neither is a
 * tile, and neither is a number chosen by eye.
 */
export function isoSitePad(
  layout: Pick<Layout, 'structures' | 'lots'>,
  element: string
): { c: Point; rx: number; ry: number } | null {
  const singular = element.replace(/s$/, '')
  const group = SITE_LOT_GROUP.get(element) ?? SITE_LOT_GROUP.get(singular)
  const taken = new Set(
    layout.structures
      .filter((s) => s.lot)
      .map((s) => `${s.lot!.c.x},${s.lot!.c.y}`)
  )
  const free = group
    ? layout.lots[group]?.find((l) => !taken.has(`${l.c.x},${l.c.y}`))
    : undefined
  if (free) {
    const rx = LOT_SEPARATION * 0.4
    return { c: free.c, rx, ry: rx * LANE_PAINT_SQUASH }
  }
  const st = layout.structures.find((s) => s.role === element || s.role === singular)
  if (st) {
    const rx = Math.max(28, st.size.w * 0.58)
    return { c: st.at, rx, ry: rx * LANE_PAINT_SQUASH }
  }
  return null
}

/**
 * The LIFE sites, re-sited on the iso ground.
 *
 * EVERYTHING MEASURED IS CARRIED, NOTHING MEASURED IS RECOMPUTED. The crew
 * SIZE is `s.crew.length` — the reducer derived it from the site's tile
 * footprint via `crewSize`, and re-deriving it from the iso pad would be a
 * second answer to "how many wrights", free to disagree with the sign the world
 * prints next to them. Each wright keeps its id, its action and its swing
 * frame; only the perimeter SLOT is re-laid, because a tile perimeter is
 * top-down geometry by construction.
 *
 * `unplaced` names every site the layout has no plot for. A site that cannot be
 * placed is not drawn and is not silently dropped: the canvas raises it on the
 * same issues channel it already badges, which is the difference between an
 * honest gap and a lie.
 */
export function isoSites(
  layout: Pick<Layout, 'structures' | 'lots'>,
  sites: readonly SiteOut[]
): { pads: IsoSitePad[]; unplaced: string[] } {
  const pads: IsoSitePad[] = []
  const unplaced: string[] = []
  for (const s of sites) {
    const spot = isoSitePad(layout, s.site.element)
    if (!spot) {
      unplaced.push(s.site.element)
      continue
    }
    pads.push({
      id: s.site.id,
      element: s.site.element,
      cx: spot.c.x,
      cy: spot.c.y,
      rx: spot.rx,
      ry: spot.ry,
      progress: s.progress.progress,
      phase: s.progress.phase,
      crew: s.crew.map((w, i) => {
        const at = crewSlot(spot.c, spot.rx, spot.ry, s.crew.length, i, s.site.id)
        return {
          id: w.id,
          x: at.x,
          y: at.y,
          action: w.action,
          frame: w.frame,
          // Wrights face the work: inward, toward the pad centre.
          facing: isoFacing(spot.c.x - at.x, spot.c.y - at.y),
        }
      }),
    })
  }
  return { pads, unplaced }
}

/**
 * The cleared-earth dither for a pad — seeded points inside the unit disc.
 *
 * OPAQUE DOTS, NEVER AN ALPHA FILL. Every alpha blend in this world has left
 * the palette on capture (the same finding that made the mist pockets and the
 * glow pools dithers), so ground is painted as discrete pixels in a ramp the
 * atlas already contains. Returned in unit coordinates so the caller scales
 * them by the pad's own radii and no second notion of the pad's size exists.
 *
 * THE COUNT IS DRIVEN BY THE PAD'S AREA, and BOTH the rule and its constant are
 * browser findings rather than preferences. A fixed 90 dots over the library's
 * 110px pad covered 1.3% of it, and the first capture showed a library ringed
 * by loose fence pieces standing on untouched grass — debris, not a worksite.
 * Area-scaling at one dot per 16px² measured 1694 dirt pixels on the frame
 * (6.2% of the pad), which was still invisible against speckled meadow. One dot
 * per 9px², at 2-3px, lands near 40% — churned earth showing through trampled
 * grass, which is what the thing IS.
 *
 * `PAD_DOT_AREA` is therefore a calibrated number and iso-life.test.ts pins the
 * coverage it produces, so a later edit that halves the density fails instead
 * of quietly returning the pad to invisible.
 *
 * AND IT FEATHERS. `keep` falls off toward the rim so the cleared patch fades
 * into the meadow instead of ending at a hard ellipse: a hard edge would draw
 * the eye to the exact shape of a hit box, which is a rendering artefact and
 * not a fact about the org.
 */
export const PAD_DOT_AREA = 9

export function padDither(
  id: string,
  rx = 100,
  ry = 72
): Array<{ x: number; y: number; r: number; tone: number }> {
  const n = Math.max(160, Math.min(3000, Math.round((Math.PI * rx * ry) / PAD_DOT_AREA)))
  const out: Array<{ x: number; y: number; r: number; tone: number }> = []
  for (let i = 0; i < n; i++) {
    const h = fnv1a(`pad:${id}:${i}`)
    const a = ((h % 3600) / 3600) * Math.PI * 2
    // sqrt keeps the scatter uniform over the disc instead of clumping at the
    // centre, which is what a raw uniform radius does.
    const rr = Math.sqrt(((h >>> 12) % 1000) / 1000)
    if (((h >>> 2) % 100) / 100 < rr * rr * 0.9) continue // rim feather
    out.push({
      x: Math.cos(a) * rr,
      y: Math.sin(a) * rr,
      r: 2 + ((h >>> 22) % 2),
      tone: (h >>> 5) % 5,
    })
  }
  return out
}

/**
 * How many fence panels a pad's hoarding takes — its PERIMETER, not a literal.
 *
 * Eight panels round a small pad is a fence; eight round a great house's pad is
 * eight sticks in a field with the gaps between them wider than the panels. The
 * panel's own drawn width is what sets the spacing, so the hoarding is
 * continuous at every size the layout can produce.
 */
export function hoardingPanels(rx: number, ry: number, panelW = 29): number {
  const perim = Math.PI * (3 * (rx + ry) - Math.sqrt((3 * rx + ry) * (rx + 3 * ry)))
  return Math.max(6, Math.min(40, Math.round(perim / (panelW * 0.92))))
}

/** Wright i of n, on the pad's perimeter — seeded, evenly spread, stable. */
export function crewSlot(
  c: Point,
  rx: number,
  ry: number,
  n: number,
  i: number,
  seed: string
): Point {
  // An even fan plus a seeded per-site rotation, so two sites of the same size
  // do not draw identical crews and one wright never sits on another.
  const jitter = ((fnv1a(`crew:${seed}`) % 360) * Math.PI) / 180
  const a = jitter + (i / Math.max(1, n)) * Math.PI * 2
  return { x: c.x + Math.cos(a) * rx, y: c.y + Math.sin(a) * ry }
}

// ── the pending rung ────────────────────────────────────────────────────────

/**
 * A PENDING RUNG, marked on the ground where the change will land.
 *
 * THE DEFECT THIS CLOSES. The top-down path draws a worksite cone on any
 * building whose element has a pending rung — the "visible-work seam". Under
 * iso there was no counterpart at all, so the world showed NOTHING where it
 * used to show "this is about to change". A silent frame about a state
 * transition is the one thing this world is not allowed to be.
 *
 * WHERE THE CHANGE WILL LAND IS `isoSitePad`'S QUESTION, NOT A SECOND ANSWER,
 * and this file learnt that the expensive way. Until 2026-07-30 this function
 * looked the element up among the DRAWN SPRITES first and only fell back to the
 * lot rule — which is precisely the "naive find the structure for this element"
 * lookup `isoSitePad`'s own docstring names as the invisible error. MEASURED on
 * a composed hamlet (four dwellings, six residential lots): a pending
 * `officer_dwellings` rung pegged its plot at (833, 818) — dwelling number ONE,
 * a house that has stood for months — while the free lot the fifth dwelling
 * will actually be raised on sits at (593, 762) showing nothing. The world said
 * "this is about to change" about a building that is not changing, which is
 * fabricated state, and fabricated state is worse than absent state. Its own
 * test pinned the defect: an arm asserted the sprite's coordinates, so putting
 * the order right turned an arm red. THE ARM WAS THE DEFECT.
 *
 * So the order is: the LOT RULE first (free lot of the element's group for a
 * count ladder, the structure itself for a single-lot upgrade — one rule, shared
 * with the construction sites so a pending mark and the works that follow it can
 * never disagree), and only then the drawn sprite. An element with neither is
 * reported rather than placed — the same three-way honesty as the site pads.
 *
 * THE SPRITE FALLBACK IS NOT DEAD CODE, and it is what makes the mark reach the
 * water: the harbour's kit (`berths`, `quay`, `harbor_boat`) and the lighthouse
 * lamp are not structures raised on lots, so `SITE_LOT_GROUP` knows no group for
 * them and `isoSitePad` returns null — measured, `isoSitePad(hamlet, 'berths')`
 * is null while the scene draws seven mooring posts. For those the sprite the
 * scene drew IS the only honest ground for the mark.
 */
export interface PendingMark {
  element: string
  x: number
  y: number
  /** Half-width of the pegged-out plot, layout px. */
  hw: number
}

export interface PendingSource {
  /** `role` as the SCENE spells it, and where it stands. */
  role: string | null
  x: number
  y: number
}

/**
 * Plot half-width for a mark on HARBOUR KIT — the only things that reach the
 * sprite fallback. It is not a lot fraction because there is no lot: a mooring
 * post's own drawn width is ~24px and the pegged plot has to read as ground
 * around it rather than as a box on it.
 */
const KIT_MARK_HW = 46

export function pendingMarks(
  layout: Pick<Layout, 'structures' | 'lots'>,
  sprites: readonly PendingSource[],
  pendingElements: readonly string[]
): { marks: PendingMark[]; unplaced: string[] } {
  const marks: PendingMark[] = []
  const unplaced: string[] = []
  for (const el of pendingElements) {
    // THE ONE RULE FOR "WHERE DOES WORK ON THIS ELEMENT LAND", first.
    const spot = isoSitePad(layout, el)
    if (spot) {
      marks.push({ element: el, x: spot.c.x, y: spot.c.y, hw: spot.rx * 0.8 })
      continue
    }
    // Only harbour kit and the lamp reach here — nothing the layout raises on a
    // lot. The scene's own spelling can be the singular of the ladder's name
    // (`officer_dwelling` vs `officer_dwellings`) — the same alias iso-scene
    // has carried since it was written. Matched on both, never fuzzily.
    const singular = el.replace(/s$/, '')
    const s = sprites.find((sp) => sp.role === el || sp.role === singular)
    if (s) {
      marks.push({ element: el, x: s.x, y: s.y, hw: KIT_MARK_HW })
      continue
    }
    unplaced.push(el)
  }
  return { marks, unplaced }
}

// ── apprentices ─────────────────────────────────────────────────────────────

/**
 * Apprentice figures, clustered on their officer's ISO position.
 *
 * The reducer places them near `officerPos`, which the shell feeds from the
 * TOP-DOWN great-house yard — a tile coordinate that names different ground
 * here. What is MEASURED about an apprentice is that it exists at all: a spawn
 * record opened a run for a real actor and it has not closed (`spawnIid` is the
 * chronicle proof). So the figure is kept, its officer is kept, and only the
 * offset is re-laid against the officer the iso yard actually drew.
 *
 * An apprentice whose officer is not on the frame is DROPPED rather than
 * floated free — the reducer's own law ("a figure may never float free of its
 * real actor"), enforced again at the point of drawing.
 */
export function isoApprentices(
  officers: readonly IsoFigure[],
  figures: readonly ApprenticeFigure[]
): IsoFigure[] {
  const by = new Map(officers.map((o) => [o.slug, o]))
  const out: IsoFigure[] = []
  for (const fig of figures) {
    const o = by.get(fig.officer)
    if (!o) continue
    const h = fnv1a(`apprentice:${fig.id}`)
    const a = ((h % 360) * Math.PI) / 180
    const r = 22 + (h >>> 9) % 14
    out.push({
      id: `apprentice:${fig.id}`,
      slug: fig.officer,
      kind: 'apprentice',
      x: o.x + Math.cos(a) * r,
      y: o.y + Math.sin(a) * r * LANE_PAINT_SQUASH,
      facing: 'down',
      anim: 'walk',
      present: true,
      scale: 0.78,
    })
  }
  return out
}

// ── the pick ────────────────────────────────────────────────────────────────

/**
 * A figure's hit box, in layout px, relative to its base centre (feet).
 *
 * Generous on purpose and no more: a person is ~15 px wide on this atlas, and a
 * box that tight is unclickable at the island tier. It is the SAME box the draw
 * pass places the sprite in, widened once, here — the pick tests what the eye
 * is looking at because both read this function.
 */
export function figureBox(f: IsoFigure): { x: number; y: number; w: number; h: number } {
  const w = Math.max(18, PERSON_W_PX * f.scale * 1.6)
  const h = PERSON_H_PX * f.scale
  return { x: f.x - w / 2, y: f.y - h, w, h }
}

/**
 * The topmost figure under a point, or null.
 *
 * BACK TO FRONT, so the figure drawn ON TOP wins — the same reason
 * `pickRoomOfficer` walks its boxes in reverse. The caller passes the array in
 * the order it drew, which is depth-sorted, so "last" is "nearest".
 */
export function pickIsoFigure(
  figures: readonly IsoFigure[],
  px: number,
  py: number
): IsoFigure | null {
  for (let i = figures.length - 1; i >= 0; i--) {
    const b = figureBox(figures[i])
    if (px >= b.x && px <= b.x + b.w && py >= b.y && py <= b.y + b.h) return figures[i]
  }
  return null
}

/** The nearest site pad whose ground ellipse contains the point, or null. */
export function pickIsoSite(
  pads: readonly IsoSitePad[],
  px: number,
  py: number
): IsoSitePad | null {
  let best: IsoSitePad | null = null
  let bestD = Infinity
  for (const p of pads) {
    const dx = (px - p.cx) / p.rx
    const dy = (py - p.cy) / p.ry
    const d = dx * dx + dy * dy
    if (d <= 1 && d < bestD) {
      bestD = d
      best = p
    }
  }
  return best
}
