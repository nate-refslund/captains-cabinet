/**
 * ISO LANE SITES — the product archipelago, in the isometric world.
 *
 * WHAT WAS MISSING, and why it is not decoration. The top-down kernel draws a
 * lane isle, a reef buoy or a mist pocket at each of the five berth slots, and
 * a click on one opens a card naming the lane and quoting the why-string
 * `buildWorldGeo` derived from `instance/config/outcomes.yml`. Under iso none
 * of it was drawn and `pickIso` could never return `kind:'lane'`, so five
 * product lanes and their provenance were UNREACHABLE in the world that had
 * just become the default — org state the world exists to show, invisible.
 * The data never went away: `WorldGeo.laneSites` is built client-side from the
 * same engine payload in both kernels. Only the geometry and the hit test were
 * absent, which is exactly what this module supplies.
 *
 * THE PLACEMENT LAW, and what it is derived from rather than invented.
 * `world-geo.ts` fixes the fan at birth: five slots at fixed bearings from the
 * quay, "never rotated/mirrored/moved". A bearing is a direction on the screen
 * the reader is looking at, so the bearings are PRESERVED — slot 1 lower-right,
 * slot 3 straight out to sea, slot 5 far left — and read off ISLE_SLOTS rather
 * than re-typed here. What cannot be preserved is the top-down RANGE: the
 * archipelago canvas is 240x192 tiles with a 60x48 island in it, while the
 * layout canvas is 2400x1760 px almost entirely filled by the island, so a fan
 * at 126 tiles' remove means two different places. The radius is therefore
 * re-based on the home island's own reach — the smallest ring that clears
 * everything the island owns (its coastline AND its harbour envelope) by a
 * stated margin. Same law, this world's units; the same re-basing the camera
 * does with ISO_BASE.
 *
 * IT IS A RING ON THE WATER, not a circle in the air: the fan is squashed by
 * the projection kernel's own 2:1 (`ISO_TILE.h / ISO_TILE.w`), so the five
 * anchors lie on the ground plane the island stands on. One continuous world.
 *
 * SIZES ARE FRACTIONS OF HOME, never px literals: a lane isle's ground is
 * `isleRadius(rung) / MAIN_ISLAND_R_CAP` of the home island's own half-width,
 * so an isle is the same fraction of home in both kernels and grows with its
 * ring exactly as the top-down one does.
 *
 * PURE: no DOM, no clock, no RNG. The renderer draws from these anchors and
 * `pickIsoLane` tests against them, so what the eye sees and what the pointer
 * names are one geometry — the defect this world has paid for four times.
 */
import { ISO_TILE } from './projection'
import {
  ISLE_SLOTS,
  LANE_PICK_TILES,
  MAIN_ISLAND_R_CAP,
  QUAY_CENTER,
  isleRadius,
  type IsleSlot,
  type LaneRender,
  type LaneSite,
} from './world-geo'
import type { Layout, LayoutSpace, Point } from './iso-layout'
import type { VoyageRender } from './course'

/**
 * The vertical squash of the isometric ground plane — the projection kernel's
 * own 2:1, derived and never re-typed. A ring drawn without it reads as a hoop
 * standing in the air above the sea.
 */
export const ISO_GROUND_SQUASH = ISO_TILE.h / ISO_TILE.w

/**
 * Open water between everything the home island owns and the fan, in layout px.
 *
 * It is a MARGIN rather than a radius: the radius itself is measured off the
 * island each frame, so a bigger island pushes its own archipelago out instead
 * of growing into it. 220px is a little over two iso tiles' width — far enough
 * that the ring never touches the harbour's deepest mooring row, near enough
 * that the whole fan is in frame at the island tier on a normal viewport.
 */
export const LANE_FAN_CLEARANCE = 220

/**
 * The reef buoy's mark, SAMPLED FROM THE SHIPPED PACK rather than picked.
 *
 * `public/world-assets/originals/iso/atlas-0.png`, the `buoy` frame at
 * (210,903) 77x92: (198,85,63) is its second-commonest opaque colour and the
 * only warm accent on it. Taking it from the atlas is not fussiness — the
 * palette gate is FITTED ON THAT ATLAS and scores composed frames against it,
 * so a red chosen by eye is foreign mass by construction. The top-down kernel's
 * own buoy red (0xc63228) is exactly such a colour and does not appear here.
 */
export const BUOY_RED = 0xc6553f

/**
 * Angles the island's own reach is measured at when deriving the fan radius.
 * 64 is enough to catch the cove bite at the resolution `landEdge` walks in
 * (6px steps); more would cost a rebuild nothing and buy nothing.
 */
const REACH_SAMPLES = 64

/** One lane site as the isometric world draws and picks it. */
export interface IsoLaneSite {
  slot: number
  lane: string | null
  render: LaneRender
  ringRung: number
  /** The honest inspect line, carried verbatim from `buildWorldGeo`. */
  why: string
  /** Ground anchor — the ellipse centre, in LAYOUT px. */
  x: number
  y: number
  /**
   * Drawn ground half-width in layout px. The ground it covers is the ellipse
   * (hw, hw * ISO_GROUND_SQUASH) about (x, y) — 0 is not possible: a buoy and
   * a mist pocket have no LAND, but they still have a mark on the water.
   */
  hw: number
  /**
   * Hit half-width in layout px, from `LANE_PICK_TILES` — the shipped
   * top-down tolerance expressed in this world's units, so a lane is no
   * harder to click in one kernel than the other.
   */
  pickHw: number
}

/** The layout-px box everything the home island owns sits inside. */
export interface HomeExtent {
  x0: number
  y0: number
  x1: number
  y1: number
}

/**
 * How far the home island reaches, measured rather than declared.
 *
 * THE COASTLINE IS ASKED, NOT THE CONSTANT IT WAS BUILT FROM. `ISLAND_RADII` is
 * only the DEFAULT ellipse — `composeLayout` takes a `coastline.radii` option,
 * and a module that read the constant would keep siting the archipelago against
 * an island the caller had already changed. `landEdge` is the coastline's own
 * answer to "where is the waterline along this bearing", so this measures the
 * island that was actually carved, cove and all.
 *
 * THE HARBOUR IS UNIONED IN because it reaches PAST the shore: the mooring rows
 * walk 52px further out per pair of open outcome windows, so a well-used
 * harbour out-reaches its own island. A fan sited on the coastline alone would
 * put a reef buoy among the moorings on exactly the deployments that have the
 * most to show.
 */
export function homeExtentOf(layout: Pick<Layout, 'coast' | 'harbour' | 'space'>): HomeExtent {
  const { cx, cy } = layout.space
  let x0 = cx
  let x1 = cx
  let y0 = cy
  let y1 = cy
  for (let i = 0; i < REACH_SAMPLES; i++) {
    const a = (i / REACH_SAMPLES) * Math.PI * 2
    const r = layout.coast.landEdge(a)
    const px = cx + Math.cos(a) * r
    // landEdge walks the reference's 0.92 vertical squash, which is already
    // baked into the radius it returns along a bearing — so the point is taken
    // on the same circle it was measured on, never re-squashed here.
    const py = cy + Math.sin(a) * r
    x0 = Math.min(x0, px)
    x1 = Math.max(x1, px)
    y0 = Math.min(y0, py)
    y1 = Math.max(y1, py)
  }
  const e = layout.harbour?.extent
  if (e) {
    x0 = Math.min(x0, e[0])
    y0 = Math.min(y0, e[1])
    x1 = Math.max(x1, e[2])
    y1 = Math.max(y1, e[3])
  }
  return { x0, y0, x1, y1 }
}

/** The home island's own half-width in layout px — the unit every isle is
 * sized in, and the horizontal term of the fan radius. */
export function homeHalfWidth(space: LayoutSpace, home: HomeExtent): number {
  return Math.max(space.cx - home.x0, home.x1 - space.cx)
}

/**
 * The fan radius: the smallest ring that clears the home island by
 * LANE_FAN_CLEARANCE in BOTH axes, remembering that the ring is squashed.
 *
 * The vertical term divides by the squash because a ring of radius R reaches
 * only R * SQUASH down-screen — sizing it on the horizontal alone would drop
 * the seaward slot (bearing 90 degrees, the one pointing straight out of the
 * harbour) into the wharf.
 */
export function isoLaneFanRadius(space: LayoutSpace, home: HomeExtent): number {
  const hw = homeHalfWidth(space, home)
  const isleHw = laneGroundHw('isle', 2, hw)
  const across = hw + isleHw + LANE_FAN_CLEARANCE
  const down = (home.y1 - space.cy + isleHw * ISO_GROUND_SQUASH + LANE_FAN_CLEARANCE) /
    ISO_GROUND_SQUASH
  return Math.max(across, down)
}

/**
 * A slot's bearing, in radians, on the screen the reader is looking at —
 * `atan2` of its offset from the quay in the authored fan.
 *
 * READ OFF ISLE_SLOTS. The five bearings are morphology law fixed at birth, and
 * the one thing that must not differ between the kernels is WHICH WAY a lane
 * lies from home: a reader who learns that their second product is off to the
 * lower left may not have it move because the projection changed.
 */
export function laneBearing(slot: IsleSlot): number {
  return Math.atan2(slot.cy - QUAY_CENTER.y, slot.cx - QUAY_CENTER.x)
}

/**
 * Drawn ground half-width for a render, as a fraction of the home island.
 *
 * An isle scales with its ring exactly as `isleRadius` says. A reef buoy and a
 * mist pocket have NO LAND — `isleRadius(0)` is 0 and that is the honest
 * answer — so their mark is sized by the hit tolerance instead, which is the
 * only other number the shipped world states about them.
 */
export function laneGroundHw(render: LaneRender, ringRung: number, homeHw: number): number {
  const tiles = render === 'isle' ? isleRadius(ringRung) : LANE_PICK_TILES.mark
  return (homeHw * tiles) / MAIN_ISLAND_R_CAP
}

/**
 * Every lane site placed on the isometric ground.
 *
 * Slots are matched to `LaneSite`s BY SLOT NUMBER, never by array index: the
 * fold that builds them walks ISLE_SLOTS in order today, and an index join
 * would silently rotate the whole archipelago the day it stops.
 */
export function isoLaneSites(
  sites: readonly LaneSite[],
  space: LayoutSpace,
  home: HomeExtent
): IsoLaneSite[] {
  const R = isoLaneFanRadius(space, home)
  const hw = homeHalfWidth(space, home)
  const out: IsoLaneSite[] = []
  for (const slot of ISLE_SLOTS) {
    const site = sites.find((s) => s.slot === slot.slot)
    if (!site) continue
    const a = laneBearing(slot)
    const pickTiles = site.render === 'isle' ? LANE_PICK_TILES.isle : LANE_PICK_TILES.mark
    out.push({
      slot: site.slot,
      lane: site.lane,
      render: site.render,
      ringRung: site.ringRung,
      why: site.why,
      x: space.cx + Math.cos(a) * R,
      y: space.cy + Math.sin(a) * R * ISO_GROUND_SQUASH,
      hw: laneGroundHw(site.render, site.ringRung, hw),
      pickHw: (hw * pickTiles) / MAIN_ISLAND_R_CAP,
    })
  }
  return out
}

/** Is a layout-px point on this site's hit ellipse? */
export function pointInLaneSite(site: IsoLaneSite, px: number, py: number): boolean {
  const rx = site.pickHw
  const ry = site.pickHw * ISO_GROUND_SQUASH
  if (rx <= 0 || ry <= 0) return false
  const dx = (px - site.x) / rx
  const dy = (py - site.y) / ry
  return dx * dx + dy * dy <= 1
}

/**
 * The lane under a layout-px point, or null.
 *
 * NEAREST WINS, not first: the hit ellipses of two adjacent slots can overlap
 * on a small island with a wide clearance, and "whichever came first in
 * ISLE_SLOTS" would make one lane permanently unclickable in the overlap. The
 * distance is measured in the ellipse's own normalised space so a big isle does
 * not beat a small buoy the pointer is sitting directly on.
 */
export function pickIsoLane(
  sites: readonly IsoLaneSite[],
  px: number,
  py: number
): IsoLaneSite | null {
  let best: IsoLaneSite | null = null
  let bestD = Infinity
  for (const s of sites) {
    if (!pointInLaneSite(s, px, py)) continue
    const dx = (px - s.x) / s.pickHw
    const dy = (py - s.y) / (s.pickHw * ISO_GROUND_SQUASH)
    const d = dx * dx + dy * dy
    if (d < bestD) {
      bestD = d
      best = s
    }
  }
  return best
}

/**
 * Where a lane's course line leaves home: the harbour mouth, or the island's
 * own seaward point when the org has carved no cove.
 *
 * The course lines are the second half of what the lanes mean — the top-down
 * kernel draws one per lane with a course, dashed from the quay to the berth,
 * sagging when the course is adrift. They need ONE origin, and it has to be the
 * harbour rather than the island centre or every line crosses the town.
 */
export function isoQuayMouth(
  layout: Pick<Layout, 'harbour' | 'space'>,
  home: HomeExtent
): Point {
  const h = layout.harbour
  if (h?.jetty) return { x: h.jetty.end.x, y: h.jetty.end.y }
  if (h?.cove) return { x: h.cove.x, y: h.cove.y }
  return { x: layout.space.cx, y: home.y1 }
}

// ── the voyage boat (show-grammar v4 / morphology harbor_boat_voyage) ───────

/**
 * The most of the run out to a berth a voyage ever covers.
 *
 * The top-down kernel's own cap, kept as a ceiling: a voyage should read as a
 * crossing even when the berth is close enough that the standoff below would
 * let the boat sit on top of it.
 */
export const VOYAGE_REACH = 0.9

/**
 * How far short of a berth the boat stops, as a multiple of THAT BERTH'S own
 * drawn ground half-width.
 *
 * IT IS NOT THE TOP-DOWN 0.9, AND THE BROWSER IS WHY. `drawDynamics` stops at
 * 0.9 of the run and that works there because its fan sits 126 tiles out from a
 * 5-tile isle: a tenth of that run clears the island many times over. Here the
 * fan radius and the isle are the SAME ORDER — measured 2026-07-29 on the live
 * cabinet, the polads run is 1871px and the isle's own ground is ~250px, so a
 * tenth of the run (187px) left the hull INSIDE the berth's ellipse, painted
 * over by the isle's jetty and warehouse block. The voyage was correct in the
 * data and invisible on the screen.
 *
 * So the stand-off is measured against the thing it has to clear rather than
 * copied as a fraction of something else: a quarter of the berth's own mark
 * beyond its edge, which scales with the ring the way the berth does. A reef
 * buoy is small and gets a small berth; an r2 isle is large and pushes the
 * anchorage out with it.
 */
export const BERTH_STANDOFF = 1.25

/** The org's vessel, placed for this payload. */
export interface IsoBoat {
  /** Ground anchor in layout px. */
  x: number
  y: number
  /** True = on the course line; false = at the berth the layout measured. */
  underway: boolean
  /** The lane being sailed to, or null when moored. */
  lane: string | null
  /** Mirror the hull when the course runs left, so the bow leads. */
  flip: boolean
}

/**
 * Where the org's vessel is for this payload — at its berth, or out on a course.
 *
 * IT IS THE HARBOUR'S OWN BOAT, MOVED, and that is the whole design. The iso
 * layout already berths `harbor_boat` — the one craft with a ladder behind it —
 * by SEARCHING for open water beside the pier, and the pack ships its art at
 * every rung (rowboat → boat_rowing, packet_boat → boat_packet, steam_packet →
 * bay_steam_packet). Drawing a second hull for the voyage would put two vessels
 * in one harbour and would invent pixels for a thing the pack already draws;
 * the top-down kernel moves its one boat too, and the grammar says the boat's
 * "SIZE/vocab stay the harbor_boat ladder's". So this function returns a
 * DISPLACEMENT for a sprite that already exists, never a boat of its own.
 *
 * NO BERTH MEANS NO BOAT, and the caller gets null. That is the layout's own
 * rule, not a guard bolted on here: a seed whose pier has no open water beside
 * it gets no vessel, "because a missing boat says the harbour could not berth
 * one, a beached boat says something false about the island". A voyage cannot
 * be shown by a boat that does not exist, and inventing one to show it would be
 * exactly that false claim.
 *
 * PROGRESS IS SERVER DATA, folded by `voyageRender` from the newest port call;
 * nothing here reads a clock, exactly as the top-down path does not. The fold
 * is the same triangle: out at progress ≤ 0.5, back at > 0.5, so a voyage
 * returns home instead of teleporting.
 *
 * A TACKING LANE WITH NO BERTH ON THE FAN LEAVES THE BOAT AT ITS MOORING. Not a
 * bug guard — a lane can be tacking and hold no slot (the fan is five wide and
 * `outcomes.yml` is not), and inventing a destination for it would draw a
 * voyage the org has not made. The top-down kernel makes the same choice with
 * the same `if (site)`.
 */
export function isoVoyageBoat(
  voyage: VoyageRender | null | undefined,
  berth: Point | null | undefined,
  sites: readonly IsoLaneSite[]
): IsoBoat | null {
  if (!berth) return null
  const site =
    voyage?.underway && voyage.lane
      ? (sites.find((s) => s.lane === voyage.lane) ?? null)
      : null
  if (!site) {
    return { x: berth.x, y: berth.y, underway: false, lane: null, flip: false }
  }
  const p = voyage as VoyageRender
  const fold = p.progress <= 0.5 ? p.progress * 2 : (1 - p.progress) * 2
  // THE RUN IS MEASURED ON THE GROUND PLANE, because the stand-off it is
  // compared against (`site.hw`) is a ground half-width. Taking the screen
  // distance instead would under-state a run that goes mostly north-south by
  // the projection's own 2:1 and moor the boat short by half an isle.
  const run = Math.hypot(site.x - berth.x, (site.y - berth.y) / ISO_GROUND_SQUASH)
  const clear = run > 0 ? Math.max(0, (run - site.hw * BERTH_STANDOFF) / run) : 0
  const t = Math.min(VOYAGE_REACH, clear) * fold
  return {
    x: berth.x + (site.x - berth.x) * t,
    y: berth.y + (site.y - berth.y) * t,
    underway: true,
    lane: site.lane,
    flip: site.x < berth.x,
  }
}

/** The berth the layout measured for the org's vessel, or null if it seated none. */
export function isoBoatBerth(layout: Pick<Layout, 'harbour'>): Point | null {
  const it = layout.harbour?.items.find((i) => i.kind === 'harbor_boat')
  return it ? { x: it.at.x, y: it.at.y } : null
}
