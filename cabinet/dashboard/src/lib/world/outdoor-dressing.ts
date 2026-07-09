/**
 * OUTDOOR SET-DRESSING — the cozy pass for the ONE continuous world
 * (cozy-density fix 2026-07-09; Captain feedback: live render read less
 * detailed/decorative/alive than the approved 7.5 mockups — now the
 * harness's positive class).
 *
 * The exact template of the Wardroom interior cozy pass (set-dressing.ts):
 * PURE DATA + seeded pickers, no rendering here. Doctrine:
 *  - Every sheet is a content-addressed manifest row, unioned into
 *    requiredOutdoorSheets('island') → the SAME loud missing→badge chain.
 *  - All decor is DECORATIVE: zero information (grammar decorative-honest
 *    class — a bench carries no data; growth-bound props like torch posts
 *    take their COUNT from the resolved ladder rung, position is dressing).
 *  - Composition rulebook (the mockups' own grammar): props arrive in
 *    purposeful CLUSTERS anchored to places (quay cargo by the pier, hay
 *    by the barn, flowers by doors), and runs FRAME places (hedges frame
 *    the yard) — never a uniform sprinkle (CLUSTER_SCATTER is a recorded
 *    failure class).
 *  - Determinism: fnv1a off stable ids only; f(geo, buildings, resolution)
 *    → identical output forever. No clocks, no Math.random.
 */
import { fnv1a } from './hash'
import type { SpriteCut } from './sprites'
import {
  DECOR_PROPS,
  STREET_PROPS,
  TORCH_LIT,
  TORCH_UNLIT,
  V,
  VILLAGE_SHEET,
} from './sprites-outdoor'
import { landAt, baseTile } from './chunks'
import { roadPoint, type WorldGeo } from './world-geo'
import type { WorldResolution } from './era-engine'
import type { WorldBuilding } from './world-buildings'

export interface OutdoorDecor {
  id: string
  sheet: string
  cut?: SpriteCut
  /** Anchor center-x / foot-y in world TILES (floats fine — fixed forever). */
  x: number
  y: number
  /** Drop-shadow footprint width in px (0 = no shadow, e.g. flat decals). */
  shadowW: number
}

export interface OutdoorDressing {
  decor: OutdoorDecor[]
  /** Meadow flower-cluster centers — butterfly anchors (fauna). */
  flowerAnchors: Array<{ x: number; y: number }>
  /** Open-water tiles off the quay — fish-jump anchors (fauna). */
  quayWater: Array<{ x: number; y: number }>
  /** The dog's porch spot by the Great House (null until it exists). */
  dogPerch: { x: number; y: number } | null
  /** Seeded chicken spots inside the pens/barn yard. */
  chickenSpots: Array<{ x: number; y: number }>
}

/** lantern_posts rung → post count (rungs: none/post_1/posts_2/posts_3/
 * posts_row — growth-ladders.yml). */
const POSTS_BY_RUNG: Record<string, number> = {
  none: 0,
  post_1: 1,
  posts_2: 2,
  posts_3: 3,
  posts_row: 6,
}

const ROAD_FRACTIONS = [0.16, 0.3, 0.44, 0.58, 0.72, 0.88] as const

export function buildOutdoorDressing(
  geo: WorldGeo,
  buildings: WorldBuilding[],
  resolution: WorldResolution | null
): OutdoorDressing {
  const decor: OutdoorDecor[] = []
  const main = geo.islands.find((i) => i.id === 'main')
  const gh = buildings.find((b) => b.element === 'great_house')
  const barn = buildings.find((b) => b.element === 'outbuildings')
  const pens = buildings.find((b) => b.element === 'pens')
  const q = geo.quayCenter
  const xr = geo.crossroads

  // ── torch posts along the road (growth-bound count, era lamp art) ────────
  const postsEl = resolution?.elements.lantern_posts
  const nPosts = postsEl ? (POSTS_BY_RUNG[postsEl.rungName] ?? 0) : 0
  const litEl = resolution?.elements.posts_lit
  const nLit = litEl ? (POSTS_BY_RUNG[litEl.rungName] ?? 0) : 0
  for (let i = 0; i < Math.min(nPosts, ROAD_FRACTIONS.length); i++) {
    const p = roadPoint(ROAD_FRACTIONS[i])
    const side = i % 2 === 0 ? -1.1 : 1.6
    decor.push({
      id: `dress:torch:${i}`,
      sheet: i < nLit ? TORCH_LIT : TORCH_UNLIT,
      x: p.x + side,
      y: p.y + 0.4,
      shadowW: 10,
    })
  }

  // ── civic cluster at the crossroads (bench + signpost) ──────────────────
  decor.push({
    id: 'dress:bench:crossroads',
    sheet: STREET_PROPS.bench,
    x: xr.x + 2.1,
    y: xr.y + 0.5,
    shadowW: 14,
  })
  decor.push({
    id: 'dress:signpost:crossroads',
    sheet: VILLAGE_SHEET,
    cut: V.signpost,
    x: xr.x - 1.5,
    y: xr.y + 0.3,
    shadowW: 12,
  })

  // ── working-quay dressing: cargo clusters + barrels + bench ─────────────
  // (decorative-honest dockside clutter — never an economy CLAIM; berth
  // chalk/shipments stay P-ECO ledger rows)
  decor.push(
    { id: 'dress:quay:boxload', sheet: DECOR_PROPS.boxLoad, x: q.x - 6.4, y: q.y - 0.2, shadowW: 15 },
    { id: 'dress:quay:box1', sheet: DECOR_PROPS.boxSingle, x: q.x - 5.3, y: q.y - 0.5, shadowW: 12 },
    { id: 'dress:quay:barrel1', sheet: DECOR_PROPS.barrel1, x: q.x - 7.3, y: q.y - 0.6, shadowW: 11 },
    { id: 'dress:quay:barrel2', sheet: DECOR_PROPS.barrel2, x: q.x + 5.6, y: q.y - 0.4, shadowW: 11 },
    { id: 'dress:quay:box2', sheet: DECOR_PROPS.boxSingle, x: q.x + 6.6, y: q.y - 0.7, shadowW: 12 },
    { id: 'dress:quay:boards', sheet: DECOR_PROPS.boardLoad, x: q.x + 7.8, y: q.y - 0.3, shadowW: 15 },
    { id: 'dress:bench:quay', sheet: STREET_PROPS.bench, x: q.x - 3.9, y: q.y - 1.1, shadowW: 14 },
    { id: 'dress:signpost:quay', sheet: VILLAGE_SHEET, cut: V.signpost, x: q.x + 4.4, y: q.y - 1.3, shadowW: 12 }
  )

  // ── yard framing: hedges flank the Great House yard + flowers at doors ──
  const flowerAnchors: Array<{ x: number; y: number }> = []
  if (gh) {
    for (let i = 0; i < 2; i++) {
      decor.push({
        id: `dress:hedge:w${i}`,
        sheet: VILLAGE_SHEET,
        cut: V.hedge,
        x: gh.x - 1.4,
        y: gh.y + gh.h - 0.4 + i * 1.9,
        shadowW: 0,
      })
      decor.push({
        id: `dress:hedge:e${i}`,
        sheet: VILLAGE_SHEET,
        cut: V.hedge,
        x: gh.x + gh.w + 1.4,
        y: gh.y + gh.h - 0.4 + i * 1.9,
        shadowW: 0,
      })
    }
    // flower clusters by the door + yard corner (butterfly anchors)
    const clusters = [
      { cx: gh.x - 0.6, cy: gh.y + gh.h + 0.4 },
      { cx: gh.x + gh.w + 0.4, cy: gh.y + gh.h + 2.6 },
      { cx: xr.x + 1.2, cy: xr.y - 1.6 },
    ]
    clusters.forEach((c, ci) => {
      flowerAnchors.push({ x: c.cx, y: c.cy })
      for (let k = 0; k < 3; k++) {
        const h = fnv1a(`flowers:${ci}:${k}`)
        decor.push({
          id: `dress:flowers:${ci}:${k}`,
          sheet: VILLAGE_SHEET,
          cut: V.flowerbed,
          x: c.cx + ((h % 5) - 2) * 0.55,
          y: c.cy + (((h >>> 8) % 3) - 1) * 0.5,
          shadowW: 0,
        })
      }
    })
  }

  // ── barn-yard cluster: hay + water trough feel (era-honest work yard) ───
  if (barn) {
    decor.push(
      { id: 'dress:hay:pile', sheet: DECOR_PROPS.hayPile, x: barn.x - 0.8, y: barn.y + barn.h - 0.2, shadowW: 14 },
      { id: 'dress:hay:small', sheet: DECOR_PROPS.haySmall, x: barn.x + 0.6, y: barn.y + barn.h + 0.5, shadowW: 10 }
    )
  }

  // ── construction props at staged-vocab lots (visible-work dressing) ─────
  for (const b of buildings) {
    if (b.element !== 'library' && b.element !== 'observatory') continue
    decor.push(
      {
        id: `dress:site:${b.element}:boards`,
        sheet: DECOR_PROPS.boardLoad,
        x: b.x + b.w + 0.7,
        y: b.y + b.h - 0.2,
        shadowW: 15,
      },
      {
        id: `dress:site:${b.element}:box`,
        sheet: DECOR_PROPS.boxSingle,
        x: b.x - 0.7,
        y: b.y + b.h - 0.5,
        shadowW: 12,
      }
    )
  }

  // ── shoreline rocks (seeded ring walk; skips the quay band) + logs ──────
  if (main) {
    let placed = 0
    for (let k = 0; k < 24 && placed < 9; k++) {
      const h = fnv1a(`shore-rock:${k}`)
      const a = (k / 24) * Math.PI * 2
      const rr = main.r - 1.2 - (h % 3) * 0.4
      const tx = main.cx + Math.cos(a) * rr
      const ty = main.cy + Math.sin(a) * rr * 0.96
      // land check + stay off the quay working band
      if (!landAt(Math.round(tx), Math.round(ty), geo)) continue
      if (Math.abs(ty - q.y) < 2.5 && Math.abs(tx - q.x) < 12) continue
      if (h % 5 === 0) continue // seeded gaps — clusters, not a necklace
      const kind = h % 3
      decor.push({
        id: `dress:rock:${k}`,
        sheet:
          kind === 0
            ? DECOR_PROPS.rockSmall
            : kind === 1
              ? DECOR_PROPS.rockMedium
              : DECOR_PROPS.rockBig,
        x: tx,
        y: ty,
        shadowW: kind === 2 ? 14 : 10,
      })
      placed++
    }
    // felled trunks at the forest edge (the clearing was CUT — worked land)
    const edge = [
      { a: 0.9, sheet: DECOR_PROPS.trunkBig1 },
      { a: 3.6, sheet: DECOR_PROPS.trunkBig2 },
      { a: 5.2, sheet: DECOR_PROPS.trunkSmall },
    ]
    edge.forEach((e, i) => {
      const rr = main.clearR + 0.8
      decor.push({
        id: `dress:trunk:${i}`,
        sheet: e.sheet,
        x: main.cx + Math.cos(e.a) * rr,
        y: main.cy + Math.sin(e.a) * rr * 0.9,
        shadowW: 16,
      })
    })
    // two inland rocks in the meadow (mockup: rocks live inland too)
    for (let i = 0; i < 2; i++) {
      const h = fnv1a(`inland-rock:${i}`)
      const tx = main.cx + ((h % 11) - 5)
      const ty = main.cy + (((h >>> 8) % 7) - 3)
      if (baseTile(Math.round(tx), Math.round(ty), geo) !== 'grass') continue
      decor.push({
        id: `dress:inrock:${i}`,
        sheet: DECOR_PROPS.rockSmall,
        x: tx,
        y: ty,
        shadowW: 8,
      })
    }
  }

  // ── fauna anchors (art landed this commit — grammar staged flipped) ─────
  const dogPerch = gh ? { x: gh.x + gh.w - 0.6, y: gh.y + gh.h + 0.9 } : null
  const chickenSpots: Array<{ x: number; y: number }> = []
  const yard = pens ?? barn
  if (yard) {
    for (let i = 0; i < 3; i++) {
      const h = fnv1a(`chicken:${i}`)
      chickenSpots.push({
        x: yard.x + 0.6 + (h % Math.max(1, yard.w * 2 - 1)) / 2,
        y: yard.y + 0.8 + ((h >>> 8) % Math.max(1, yard.h * 2 - 1)) / 2,
      })
    }
  }
  const quayWater = [
    { x: q.x - 2.6, y: q.y + 2.6 },
    { x: q.x + 1.4, y: q.y + 3.3 },
    { x: q.x + 4.3, y: q.y + 2.9 },
  ]

  return { decor, flowerAnchors, quayWater, dogPerch, chickenSpots }
}
