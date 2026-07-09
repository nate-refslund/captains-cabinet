/**
 * CHUNKED TILEMAP — the unbounded world substrate (spec v2 §3.4).
 *
 * Design (growth-grammar.md §5.2, ADOPTED):
 *   chunk       = 16×16 tiles, keyed (cx, cy) — signed, unbounded
 *   base(cx,cy) = PURE function of world geography (WorldGeo — itself a pure
 *                 function of the growth counters) + fnv1a(tx,ty) variation
 *   override    = ONLY chunks containing authored content (road detail,
 *                 construction diffs) store a layer diff; everything else
 *                 renders from base() on demand and is NEVER stored.
 *
 * Because base() takes the growth counters as parameters, land growth
 * requires zero chunk rewrites — R ticks up, the coastline function moves,
 * new shore chunks simply exist when the camera looks. Endless with
 * O(built) storage; LOD samples the same world coarser.
 *
 * PURE: no clocks, no unseeded randomness, no IO.
 */
import { fnv1a } from './hash'
import { coastWobble, type WorldGeo } from './world-geo'

export const CHUNK_SIZE = 16

export function chunkOf(t: number): number {
  return Math.floor(t / CHUNK_SIZE)
}

export function localOf(t: number): number {
  return ((t % CHUNK_SIZE) + CHUNK_SIZE) % CHUNK_SIZE
}

export function chunkKey(cx: number, cy: number): string {
  return `${cx},${cy}`
}

export type Terrain =
  | 'water'
  | 'shore' // water tile adjacent to land — autotiled foam/edge
  | 'sand'
  | 'grass'
  | 'meadow'
  | 'forest'
  | 'dirt' // road / worn path
  | 'quay' // reclaimed stone along the quay line

/** Land predicate — the ONE coastline truth every layer samples. */
export function landAt(tx: number, ty: number, geo: WorldGeo): boolean {
  for (const isl of geo.islands) {
    if (isl.r <= 0) continue
    const dx = tx - isl.cx
    const dy = ty - isl.cy
    const d = Math.sqrt(dx * dx + dy * dy)
    if (d <= isl.r + coastWobble(tx, ty) * Math.min(1, isl.r / 12)) return true
  }
  return false
}

/** The procedural base terrain field (pure f(geo, tile)). */
export function baseTile(tx: number, ty: number, geo: WorldGeo): Terrain {
  if (!landAt(tx, ty, geo)) {
    // water; shore is resolved by the autotile mask (adjacent-to-land)
    return shoreMask(tx, ty, geo) !== 0 ? 'shore' : 'water'
  }
  if (geo.roadTiles.has(`${tx},${ty}`)) return 'dirt'
  // quay band: main-island land on the quay line renders reclaimed stone
  if (
    ty >= geo.quayCenter.y - 1 &&
    ty <= geo.quayCenter.y + 1 &&
    Math.abs(tx - geo.quayCenter.x) <= 10
  ) {
    return 'quay'
  }
  for (const isl of geo.islands) {
    const dx = tx - isl.cx
    const dy = ty - isl.cy
    const d = Math.sqrt(dx * dx + dy * dy)
    if (d > isl.r + 1.5) continue
    // sand fringe just inside the coastline — 1.8 tiles so the beach reads
    // as a CONTIGUOUS ring through the coast wobble (cozy pass: the ±1
    // per-tile wobble turned a 1-tile fringe into salt-pepper speckle)
    if (d >= isl.r - 1.8) return 'sand'
    // forest ring outside the cleared heart (the egg's tree-wall; the
    // clearing only retreats where earned lots need it — visible work law)
    if (d > isl.clearR) return 'forest'
    // cleared heart: grass with seeded meadow variation (TEXTURE class).
    // 1-in-3 (cozy-density pass 2026-07-09; was 1-in-5 — the approved
    // mockups carry ~110 terrain accents per viewport vs live ~33).
    return fnv1a(`meadow:${tx},${ty}`) % 3 === 0 ? 'meadow' : 'grass'
  }
  return 'grass'
}

// ── shore autotiling (exterior-pack edge tiles) ─────────────────────────────

/** 8-bit neighbor land mask for a WATER tile: bit order N,NE,E,SE,S,SW,W,NW.
 * 0 = open water (no land neighbor). Land tiles always mask 0. */
export function shoreMask(tx: number, ty: number, geo: WorldGeo): number {
  // A land tile is not a shore-water tile.
  if (rawLand(tx, ty, geo)) return 0
  const n = [
    [0, -1],
    [1, -1],
    [1, 0],
    [1, 1],
    [0, 1],
    [-1, 1],
    [-1, 0],
    [-1, -1],
  ] as const
  let mask = 0
  for (let i = 0; i < 8; i++) {
    if (rawLand(tx + n[i][0], ty + n[i][1], geo)) mask |= 1 << i
  }
  return mask
}

/** landAt without the shore recursion (private twin). */
function rawLand(tx: number, ty: number, geo: WorldGeo): boolean {
  for (const isl of geo.islands) {
    if (isl.r <= 0) continue
    const dx = tx - isl.cx
    const dy = ty - isl.cy
    const d = Math.sqrt(dx * dx + dy * dy)
    if (d <= isl.r + coastWobble(tx, ty) * Math.min(1, isl.r / 12)) return true
  }
  return false
}

/**
 * Autotile variant for a shore mask — the 4-bit cardinal blob + corner
 * refinement used by the LimeZu exterior water-edge sheets. Returns a
 * stable variant id the renderer maps to a sprite cut:
 *   'edge_n'|'edge_e'|'edge_s'|'edge_w'          — one land side
 *   'corner_ne'|'corner_se'|'corner_sw'|'corner_nw' — two adjacent sides
 *   'inner_ne'|'inner_se'|'inner_sw'|'inner_nw'  — diagonal-only land
 *   'channel_ns'|'channel_ew'                    — opposite sides
 *   'cove'                                       — 3+ sides
 *   'open'                                       — no land (not shore)
 */
export type ShoreVariant =
  | 'open'
  | 'edge_n'
  | 'edge_e'
  | 'edge_s'
  | 'edge_w'
  | 'corner_ne'
  | 'corner_se'
  | 'corner_sw'
  | 'corner_nw'
  | 'inner_ne'
  | 'inner_se'
  | 'inner_sw'
  | 'inner_nw'
  | 'channel_ns'
  | 'channel_ew'
  | 'cove'

const N = 1 << 0
const NE = 1 << 1
const E = 1 << 2
const SE = 1 << 3
const S = 1 << 4
const SW = 1 << 5
const W = 1 << 6
const NW = 1 << 7

export function shoreVariant(mask: number): ShoreVariant {
  if (mask === 0) return 'open'
  const card =
    (mask & N ? 1 : 0) + (mask & E ? 1 : 0) + (mask & S ? 1 : 0) + (mask & W ? 1 : 0)
  if (card >= 3) return 'cove'
  if ((mask & N && mask & S) && !(mask & E) && !(mask & W)) return 'channel_ns'
  if ((mask & E && mask & W) && !(mask & N) && !(mask & S)) return 'channel_ew'
  if (mask & N && mask & E) return 'corner_ne'
  if (mask & S && mask & E) return 'corner_se'
  if (mask & S && mask & W) return 'corner_sw'
  if (mask & N && mask & W) return 'corner_nw'
  if (mask & N) return 'edge_n'
  if (mask & E) return 'edge_e'
  if (mask & S) return 'edge_s'
  if (mask & W) return 'edge_w'
  // diagonal-only land: inner corners
  if (mask & NE) return 'inner_ne'
  if (mask & SE) return 'inner_se'
  if (mask & SW) return 'inner_sw'
  return 'inner_nw'
}

// ── sparse override store (O(built) — the ONLY stored state) ────────────────

export interface TileOverride {
  terrain: Terrain
  /** Provenance: which authored element / site wrote this diff. */
  by: string
}

export class ChunkStore {
  private overrides = new Map<string, Map<number, TileOverride>>()

  setOverride(tx: number, ty: number, o: TileOverride): void {
    const key = chunkKey(chunkOf(tx), chunkOf(ty))
    let m = this.overrides.get(key)
    if (!m) {
      m = new Map()
      this.overrides.set(key, m)
    }
    m.set(localOf(ty) * CHUNK_SIZE + localOf(tx), o)
  }

  getOverride(tx: number, ty: number): TileOverride | null {
    const m = this.overrides.get(chunkKey(chunkOf(tx), chunkOf(ty)))
    if (!m) return null
    return m.get(localOf(ty) * CHUNK_SIZE + localOf(tx)) ?? null
  }

  /** The composed tile: override wins, else the procedural base. NEVER
   * allocates storage for un-authored chunks (O(built) invariant). */
  tileAt(tx: number, ty: number, geo: WorldGeo): Terrain {
    return this.getOverride(tx, ty)?.terrain ?? baseTile(tx, ty, geo)
  }

  /** Stored chunk count — the O(built) storage gauge (tests pin it). */
  storedChunkCount(): number {
    return this.overrides.size
  }
}

/** Chunks intersecting a world-tile rect (render iteration order stable). */
export function chunksInRect(
  x0: number,
  y0: number,
  x1: number,
  y1: number
): Array<{ cx: number; cy: number }> {
  const out: Array<{ cx: number; cy: number }> = []
  for (let cy = chunkOf(y0); cy <= chunkOf(y1); cy++) {
    for (let cx = chunkOf(x0); cx <= chunkOf(x1); cx++) {
      out.push({ cx, cy })
    }
  }
  return out
}
