/**
 * Z1 street layout — the HQ building on its street (world-alive §3.1, T3).
 *
 * PURE and DETERMINISTIC: integer tile positions, every variation seeded via
 * fnv1a(stableId), growth surfaces come IN as data (census keyframes via
 * growth.ts) — no clocks, no randomness, no fetches. Positions never move
 * once placed (fold law: placement keys on stable ids, not on counts that
 * reorder).
 *
 * Composition (§3.1): horizontal street band; buildings rear (HQ centered,
 * condos flanking — decorative), sidewalk, asphalt with seeded variation,
 * sidewalk fore. The HQ stacks ONE modular Middle_Floor per commits tier
 * (morphology: street_hq_floors). Street props unlock by org-age band
 * (street_liveliness — TEXTURE class). Officers render as badge motes at
 * the facade — walking the street would lie; they are inside (§3 table).
 */
import { fnv1a } from './hash'
import type { SpriteCut } from './sprites'
import type { GrowthModel } from './growth'
import {
  ASPHALT_SHEETS,
  GROUND_H,
  HQ_GROUND,
  HQ_MIDDLE_FLOORS,
  HQ_ROOF,
  MIDDLE_H,
  MODULAR_W,
  NEIGHBOR_GROUND,
  NEIGHBOR_ROOF,
  ROOF_H,
  SIDEWALK_SHEETS,
  STREET_PROPS,
} from './sprites-outdoor'

export const STREET_W = 64
export const STREET_H = 32
/** Tile row the building fronts stand on (sprite bottom anchor). */
export const BUILD_BASE = 20
/** Sidewalk rows (rear walk + curb) and asphalt band. */
export const WALK_ROWS = [20, 21]
export const ROAD_ROWS = [22, 23, 24, 25, 26]
export const FORE_WALK_ROWS = [27, 28]

export interface GroundTile {
  x: number
  y: number
  sheet: string
}

export interface OutdoorProp {
  /** Stable inspect id, e.g. 'street:lamp:2' / 'island:beacon'. */
  id: string
  sheet: string
  cut?: SpriteCut
  /** Anchor tile: sprite bottom-center sits at (x*TILE, y*TILE). */
  x: number
  y: number
  label: string
  decorative: boolean
  /** morphology.yml v2 entry id when this prop is a bound growth surface. */
  morphId?: string
  /** Ghost-frame render (outline alpha) — e.g. disabled service rows. */
  ghost?: boolean
  /** Primary click navigates (door-is-a-scene-swap doctrine). */
  navigate?: 2 | 1
}

export interface MoteSlot {
  slug: string
  /** Facade rest slot (tile). */
  x: number
  y: number
  /** Seeded patrol half-span in tiles (walked only while a verb is live). */
  span: number
  /** Seeded phase offset for the patrol walk. */
  phase: number
}

export interface WindowSlot {
  /** px rect (world space) of one HQ window pane. */
  px: number
  py: number
  w: number
  h: number
  /** Officer index (sorted slugs) this pane binds to, or -1 = unbound. */
  officerIdx: number
}

export interface StreetLayout {
  w: number
  h: number
  /** street_hq_floors — modular Middle_Floors above ground (commits tier). */
  hqFloors: number
  ground: GroundTile[]
  props: OutdoorProp[]
  motes: MoteSlot[]
  windows: WindowSlot[]
  /** Camera anchor (HQ door) + clamp box, in tiles. */
  anchor: { x: number; y: number }
  /** Street-lamp tile positions (night light pools render here). */
  lampTiles: Array<{ x: number; y: number }>
}

const HQ_X = 32 // HQ door/center column
const MOD_TILES = MODULAR_W / 16 // 7

/** The HQ modular stack for a floors tier: ground + N middles + roof. */
export function hqStack(floors: number): Array<{ sheet: string; bottomPx: number; hPx: number }> {
  const n = Math.max(0, Math.min(7, floors))
  const out: Array<{ sheet: string; bottomPx: number; hPx: number }> = []
  let bottom = BUILD_BASE * 16
  out.push({ sheet: HQ_GROUND, bottomPx: bottom, hPx: GROUND_H })
  bottom -= GROUND_H
  for (let i = 0; i < n; i++) {
    out.push({
      sheet: HQ_MIDDLE_FLOORS[fnv1a(`street:hq:floor:${i}`) % HQ_MIDDLE_FLOORS.length],
      bottomPx: bottom,
      hPx: MIDDLE_H,
    })
    bottom -= MIDDLE_H
  }
  out.push({ sheet: HQ_ROOF, bottomPx: bottom, hPx: ROOF_H })
  return out
}

export function buildStreetLayout(growth: GrowthModel, slugs: string[]): StreetLayout {
  const ground: GroundTile[] = []
  for (const y of WALK_ROWS) {
    for (let x = 0; x < STREET_W; x++) {
      ground.push({ x, y, sheet: SIDEWALK_SHEETS[fnv1a(`street:walk:${x}:${y}`) % SIDEWALK_SHEETS.length] })
    }
  }
  for (const y of ROAD_ROWS) {
    for (let x = 0; x < STREET_W; x++) {
      ground.push({ x, y, sheet: ASPHALT_SHEETS[fnv1a(`street:road:${x}:${y}`) % ASPHALT_SHEETS.length] })
    }
  }
  for (const y of FORE_WALK_ROWS) {
    for (let x = 0; x < STREET_W; x++) {
      ground.push({ x, y, sheet: SIDEWALK_SHEETS[fnv1a(`street:fore:${x}:${y}`) % SIDEWALK_SHEETS.length] })
    }
  }

  const props: OutdoorProp[] = []

  // ── buildings (rear band) ────────────────────────────────────────────────
  // The HQ stack itself renders from hqStack() in the canvas (it needs px
  // stacking, not a single prop). Here: its door hitbox + neighbors + sign.
  props.push({
    id: 'street:hq:door',
    sheet: STREET_PROPS.mailbox, // hitbox only; mailbox prop stands beside
    x: HQ_X,
    y: BUILD_BASE,
    label: 'HQ door — enter the Wardroom',
    decorative: false,
    navigate: 2,
  })
  props.push({
    id: 'street:hq:sign',
    sheet: STREET_PROPS.sign,
    x: HQ_X,
    y: BUILD_BASE - 3,
    label: 'HQ building sign',
    decorative: true,
  })
  props.push({
    id: 'street:mailbox',
    sheet: STREET_PROPS.mailbox,
    x: HQ_X + 4,
    y: BUILD_BASE,
    label: 'blue mailbox — street face of the postbox',
    decorative: true,
  })
  // Neighbor condos: set dressing, decorative, codex says so (§3.1).
  const nLeftX = HQ_X - MOD_TILES - 6
  const nRightX = HQ_X + MOD_TILES + 6
  props.push({
    id: 'street:neighbor:0',
    sheet: NEIGHBOR_GROUND[0],
    x: nLeftX,
    y: BUILD_BASE,
    label: 'neighbor condo',
    decorative: true,
  })
  props.push({
    id: 'street:neighbor:0:roof',
    sheet: NEIGHBOR_ROOF[0],
    x: nLeftX,
    y: BUILD_BASE - GROUND_H / 16,
    label: 'neighbor condo roof',
    decorative: true,
  })
  props.push({
    id: 'street:neighbor:1',
    sheet: NEIGHBOR_GROUND[1],
    x: nRightX,
    y: BUILD_BASE,
    label: 'neighbor bakery',
    decorative: true,
  })
  props.push({
    id: 'street:neighbor:1:roof',
    sheet: NEIGHBOR_ROOF[1],
    x: nRightX,
    y: BUILD_BASE - 80 / 16, // Bakery_1 ground is 80px tall
    label: 'neighbor bakery roof',
    decorative: true,
  })

  // ── street life (age-banded TEXTURE — street_liveliness) ────────────────
  const lampTiles: Array<{ x: number; y: number }> = []
  for (let i = 0; i < 10; i++) {
    const x = 4 + i * 6
    if (x >= STREET_W - 2) break
    lampTiles.push({ x, y: WALK_ROWS[1] })
    props.push({
      id: `street:lamp:${i}`,
      sheet: fnv1a(`street:lamp:${i}`) % 2 === 0 ? STREET_PROPS.lamp1 : STREET_PROPS.lamp2,
      x,
      y: WALK_ROWS[1],
      label: 'street lamp',
      decorative: true,
      morphId: 'street_liveliness',
    })
  }
  if (growth.streetBand !== 'bare') {
    // 7–30d band: benches + trees between the lamps.
    for (let i = 0; i < 9; i++) {
      const x = 7 + i * 6
      if (x >= STREET_W - 2) break
      props.push({
        id: `street:tree:${i}`,
        sheet: fnv1a(`street:tree:${i}`) % 2 === 0 ? STREET_PROPS.tree1 : STREET_PROPS.tree2,
        x,
        y: WALK_ROWS[1],
        label: 'street tree',
        decorative: true,
        morphId: 'street_liveliness',
      })
    }
    props.push({
      id: 'street:bench',
      sheet: STREET_PROPS.bench,
      x: HQ_X - 6,
      y: WALK_ROWS[1],
      label: 'bench',
      decorative: true,
      morphId: 'street_liveliness',
    })
    props.push({
      id: 'street:hydrant',
      sheet: STREET_PROPS.hydrant,
      x: HQ_X + 7,
      y: WALK_ROWS[1],
      label: 'hydrant',
      decorative: true,
      morphId: 'street_liveliness',
    })
    props.push({
      id: 'street:trash',
      sheet: STREET_PROPS.trash,
      x: HQ_X + 9,
      y: WALK_ROWS[1],
      label: 'trash can',
      decorative: true,
      morphId: 'street_liveliness',
    })
  }
  if (growth.streetBand === 'planters') {
    // >30d band: planter row on the fore walk (flower beds come from the
    // village sheet on the island; here reuse trees as planters).
    for (let i = 0; i < 6; i++) {
      props.push({
        id: `street:planter:${i}`,
        sheet: STREET_PROPS.tree2,
        x: 6 + i * 10,
        y: FORE_WALK_ROWS[1],
        label: 'planter',
        decorative: true,
        morphId: 'street_liveliness',
      })
    }
  }
  // Parked cars: 2, seeded slot + facing (§3.1).
  for (let k = 0; k < 2; k++) {
    const h = fnv1a(`street:car:${k}`)
    const left = h % 2 === 0
    const x = 8 + (h % 5) * 9 + k * 22
    props.push({
      id: `street:car:${k}`,
      sheet: left ? STREET_PROPS.carLeft : STREET_PROPS.carRight,
      x: Math.min(STREET_W - 4, x),
      y: left ? ROAD_ROWS[1] + 1 : ROAD_ROWS[3] + 1,
      label: 'parked car',
      decorative: true,
    })
  }

  // ── officer badge motes at the facade (same Redis predicate as Z2) ──────
  const ordered = [...slugs].sort()
  const motes: MoteSlot[] = ordered.map((slug, i) => ({
    slug,
    x: HQ_X - 3 + i * 2,
    y: WALK_ROWS[0],
    span: 2 + (fnv1a(`${slug}:street:span`) % 3),
    phase: fnv1a(`${slug}:street:phase`) % 64,
  }))

  // ── lit windows: one per officer with a live verb (§3.1 — presence-driven,
  //    never volume-driven). Slots on the ground-floor face, px space.
  const groundLeftPx = (HQ_X - MOD_TILES / 2) * 16
  const windows: WindowSlot[] = ordered.map((_, i) => ({
    px: groundLeftPx + 10 + i * 24,
    py: BUILD_BASE * 16 - GROUND_H + 14,
    w: 12,
    h: 14,
    officerIdx: i,
  }))

  return {
    w: STREET_W,
    h: STREET_H,
    hqFloors: growth.hqFloors.tier,
    ground,
    props,
    motes,
    windows,
    anchor: { x: HQ_X, y: BUILD_BASE + 2 },
    lampTiles,
  }
}
