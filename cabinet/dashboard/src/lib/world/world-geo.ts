/**
 * WORLD GEOGRAPHY — the authored archipelago canvas (morphology-law
 * constants from archipelago-positions/v1 + the ratified egg tile plan).
 *
 * Everything here is LAW-shaped data, not behavior: the 240×192-tile canvas,
 * the main island composed in at offset (90,8), the quay line, the road
 * spine (village rise → crossroads → quay), and the isle-anchor bearing fan
 * (fixed at birth, never rotated/mirrored/moved — layout_fold).
 *
 * PURE: buildWorldGeo() is a function of the growth counters only; the
 * chunked base field (chunks.ts) samples it, so land growth (R ticking up,
 * isle rings raising) requires ZERO chunk rewrites.
 */
import { fnv1a } from './hash'
import { landRadius } from './growth'
import type { LaneRecord } from './era-engine'
import { laneRung } from './era-engine'

/** Canvas + main-island composition constants (archipelago-positions/v1). */
export const CANVAS = { w: 240, h: 192 } as const
export const MAIN_OFFSET = { x: 90, y: 8 } as const
export const MAIN_CORE = { w: 60, h: 48 } as const
/** Quay center in world tiles — the bearing-fan origin. */
export const QUAY_CENTER = { x: 120, y: 52 } as const
/** Sea owns everything south of the quay line. */
export const SEA_EDGE_Y = 54

/** Isle anchor slots — morphology law, fixed at birth (30° fan, r=126). */
export interface IsleAnchor {
  slot: number
  lane: string | null
  cx: number
  cy: number
  status: 'active' | 'retired' | 'reserved'
  probeWired: boolean
}

export const ISLE_ANCHORS: readonly IsleAnchor[] = [
  { slot: 1, lane: 'polads', cx: 200, cy: 150, status: 'active', probeWired: true },
  { slot: 2, lane: 'stephie', cx: 40, cy: 150, status: 'active', probeWired: false },
  { slot: 3, lane: 'stepnetwork', cx: 120, cy: 168, status: 'retired', probeWired: false },
  { slot: 4, lane: null, cx: 238, cy: 95, status: 'reserved', probeWired: false },
  { slot: 5, lane: null, cx: 2, cy: 95, status: 'reserved', probeWired: false },
] as const

/**
 * The road spine in MAIN-ISLAND local tiles: village rise (north) through
 * the crossroads (mailbox + noticeboard midpoint) down to the quay. The
 * egg's t0 dirt path IS this road (egg-tile-plan: the path never moves).
 */
export const ROAD_SPINE_LOCAL: ReadonlyArray<readonly [number, number]> = [
  [28, 10], // village rise — Great House door yard
  [29, 18],
  [30, 26], // the crossroads (mailbox / noticeboard / post kiosk)
  [30, 36],
  [30, 44], // quay line
] as const

/** Crossroads tile in main-island local coords. */
export const CROSSROADS_LOCAL = { x: 30, y: 26 } as const

/**
 * Path spurs (cozy pass 2026-07-09 — mockup path logic: every lived-in
 * door connects to the street; v1a cottages floated beside the road).
 * Local polylines from the fixed building anchors (world-buildings law
 * constants: dwellings at (16,14)/(11,14)/(16,20)/(11,20), workshop
 * (20,12), barn (42,14)) to the road spine. 1-wide worn lanes.
 */
export const ROAD_SPURS_LOCAL: ReadonlyArray<
  ReadonlyArray<readonly [number, number]>
> = [
  [
    [18, 17],
    [24, 17],
    [29, 17],
  ], // dwelling row 1 → spine
  [
    [18, 23],
    [24, 24],
    [30, 25],
  ], // dwelling row 2 → crossroads approach
  [
    [22, 15],
    [26, 16],
    [29, 16],
  ], // workshop yard → spine
  [
    [45, 19],
    [38, 18],
    [31, 17],
  ], // barn door → spine
] as const

export function toWorld(lx: number, ly: number): { x: number; y: number } {
  return { x: MAIN_OFFSET.x + lx, y: MAIN_OFFSET.y + ly }
}

/** Bresenham tiles along a polyline (integer tile coords). */
export function carvePolyline(
  pts: ReadonlyArray<readonly [number, number]>
): Array<[number, number]> {
  const out: Array<[number, number]> = []
  const seen = new Set<string>()
  const push = (x: number, y: number) => {
    const k = `${x},${y}`
    if (!seen.has(k)) {
      seen.add(k)
      out.push([x, y])
    }
  }
  for (let i = 0; i + 1 < pts.length; i++) {
    let [x0, y0] = pts[i]
    const [x1, y1] = pts[i + 1]
    const dx = Math.abs(x1 - x0)
    const dy = -Math.abs(y1 - y0)
    const sx = x0 < x1 ? 1 : -1
    const sy = y0 < y1 ? 1 : -1
    let err = dx + dy
    for (;;) {
      push(x0, y0)
      if (x0 === x1 && y0 === y1) break
      const e2 = 2 * err
      if (e2 >= dy) {
        err += dy
        x0 += sx
      }
      if (e2 <= dx) {
        err += dx
        y0 += sy
      }
    }
  }
  return out
}

/** One landmass the base terrain field samples (main island or a lane isle). */
export interface IslandDisc {
  id: string
  cx: number
  cy: number
  /** Land radius in tiles (0 = no land: reef-buoy-only anchors). */
  r: number
  /** Cleared-heart radius — grass/meadow inside, forest ring outside. */
  clearR: number
}

/** How a lane renders at its anchor (Captain rulings 2026-07-09). */
export type LaneRender = 'isle' | 'reef_buoy' | 'mist_reserved'

export interface LaneSite {
  lane: string | null
  slot: number
  cx: number
  cy: number
  render: LaneRender
  /** Visible ring rung (0 reef / 1 dock r0 / 2 warehouses r1 / …). */
  ringRung: number
  /** Honest inspect line: why this render (retired / instance-test / …). */
  why: string
}

/** Isle land radius from its visible ring rung (ring bands, archipelago.md):
 * r0 dock = band 0–4 → r 5; r1 warehouses = band 4–10 → r 10. */
export function isleRadius(ringRung: number): number {
  if (ringRung <= 0) return 0
  return ringRung === 1 ? 5 : 10
}

export interface WorldGeo {
  canvas: { w: number; h: number }
  islands: IslandDisc[]
  laneSites: LaneSite[]
  /** Road tiles (world coords) — Set of "x,y" keys for O(1) sampling. */
  roadTiles: Set<string>
  quayCenter: { x: number; y: number }
  crossroads: { x: number; y: number }
}

export interface WorldGeoInput {
  /** org_events_total — main-island land radius via the fold law. */
  orgEventsTotal: number
  /** Per-lane outcome records (outcomes.yml derived). */
  lanes: Record<string, LaneRecord>
}

export function buildWorldGeo(input: WorldGeoInput): WorldGeo {
  const R = Math.min(landRadius(input.orgEventsTotal), 28) // core is 60×48 — cap the disc
  const main: IslandDisc = {
    id: 'main',
    cx: MAIN_OFFSET.x + Math.floor(MAIN_CORE.w / 2),
    cy: MAIN_OFFSET.y + Math.floor(MAIN_CORE.h / 2) - 2,
    r: R,
    clearR: Math.max(10, Math.floor(R * 0.62)),
  }
  const islands: IslandDisc[] = [main]
  const laneSites: LaneSite[] = []

  for (const a of ISLE_ANCHORS) {
    if (a.status === 'reserved') {
      laneSites.push({
        lane: a.lane,
        slot: a.slot,
        cx: a.cx,
        cy: a.cy,
        render: 'mist_reserved',
        ringRung: 0,
        why: 'reserved fan slot — no lane assigned; mist pocket + grey buoy',
      })
      continue
    }
    const rec = a.lane ? input.lanes[a.lane] : undefined
    const rung = laneRung(rec)
    const isInstance = rec?.instanceTest === true
    const isRetired = a.status === 'retired' || (rec ? rec.active === 0 && rec.retired > 0 : false)
    if (rung === 0) {
      laneSites.push({
        lane: a.lane,
        slot: a.slot,
        cx: a.cx,
        cy: a.cy,
        render: 'reef_buoy',
        ringRung: 0,
        why: isInstance
          ? `${a.lane} — instance-only test lane, never foundation (Captain ruling 2026-07-09)`
          : isRetired
            ? `${a.lane} — retired lane (outcomes.yml); reef-buoy is the honest marker`
            : `${a.lane} — no ratified outcome yet`,
      })
      continue
    }
    const r = isleRadius(rung)
    islands.push({
      id: `isle:${a.lane}`,
      cx: a.cx,
      cy: a.cy,
      r,
      clearR: Math.max(2, r - 2),
    })
    laneSites.push({
      lane: a.lane,
      slot: a.slot,
      cx: a.cx,
      cy: a.cy,
      render: 'isle',
      ringRung: rung,
      why: `${a.lane} — ring r${rung - 1} earned (outcomes.yml${a.probeWired ? ', probe-verified lane' : '; unverified by probe — probes.yml has no row'})`,
    })
  }

  const roadTiles = new Set<string>()
  const worldSpine = ROAD_SPINE_LOCAL.map(
    ([lx, ly]) => [MAIN_OFFSET.x + lx, MAIN_OFFSET.y + ly] as const
  )
  for (const [x, y] of carvePolyline(worldSpine)) {
    roadTiles.add(`${x},${y}`)
    // cozy-density pass (2026-07-09): the mockups' street is an organic
    // 2–3-tile dirt band, not a 1-tile carve. Widen with a seeded flank
    // (side alternates per tile) + an occasional second flank bulge.
    // The walkable spine (roadPoint) is unchanged — width is visual.
    const side = fnv1a(`roadw:${x},${y}`) % 2 === 0 ? 1 : -1
    roadTiles.add(`${x + side},${y}`)
    if (fnv1a(`roadw2:${x},${y}`) % 5 === 0) roadTiles.add(`${x - side},${y}`)
  }
  // door-to-street spurs (1-wide worn lanes — mockup path logic)
  for (const spur of ROAD_SPURS_LOCAL) {
    const w = spur.map(([lx, ly]) => [MAIN_OFFSET.x + lx, MAIN_OFFSET.y + ly] as const)
    for (const [x, y] of carvePolyline(w)) roadTiles.add(`${x},${y}`)
  }

  return {
    canvas: { w: CANVAS.w, h: CANVAS.h },
    islands,
    laneSites,
    roadTiles,
    quayCenter: { ...QUAY_CENTER },
    crossroads: toWorld(CROSSROADS_LOCAL.x, CROSSROADS_LOCAL.y),
  }
}

/**
 * Point along the road spine (world tiles) at parameter t ∈ [0,1]:
 * t=0 the village rise (Great House yard), t=1 the quay line. Commute
 * walks interpolate along this (T2 LIFE — walks ride the road, never
 * teleport). Pure + deterministic.
 */
export function roadPoint(t: number): { x: number; y: number } {
  const pts = ROAD_SPINE_LOCAL.map(([lx, ly]) => toWorld(lx, ly))
  const clamped = Math.max(0, Math.min(1, t))
  const segLens: number[] = []
  let total = 0
  for (let i = 0; i + 1 < pts.length; i++) {
    const l = Math.hypot(pts[i + 1].x - pts[i].x, pts[i + 1].y - pts[i].y)
    segLens.push(l)
    total += l
  }
  if (total === 0) return { ...pts[0] }
  let d = clamped * total
  for (let i = 0; i < segLens.length; i++) {
    if (d <= segLens[i] || i === segLens.length - 1) {
      const f = segLens[i] === 0 ? 0 : d / segLens[i]
      return {
        x: pts[i].x + (pts[i + 1].x - pts[i].x) * f,
        y: pts[i].y + (pts[i + 1].y - pts[i].y) * f,
      }
    }
    d -= segLens[i]
  }
  return { ...pts[pts.length - 1] }
}

/** Deterministic coastline wobble (±1 tile) — seeded per tile, stable. */
export function coastWobble(tx: number, ty: number): number {
  return (fnv1a(`coast:${tx},${ty}`) % 3) - 1
}
