/**
 * Walkable-grid pathing for the Wardroom (behavior vocabulary wave).
 *
 * PURE + DETERMINISTIC: integer tile math, fixed neighbor order, no clocks,
 * no randomness — the same (layout, from, to) always yields the same path
 * (CI ratchet greps this tree for Math.random / Date.now). The director
 * calls this only on retarget; the per-tick position is interpolation along
 * the returned polyline.
 *
 * Grid model (one dense room):
 *  - walkable = room interior below the wall band, inside a 1-tile border
 *    margin on the other three sides;
 *  - obstacles = desk furniture tiles (the desk prop sits one tile below the
 *    officer's stand tile) + the conference-table core (seats around it stay
 *    free — TABLE_SEAT_OFFSETS in layout.ts).
 * Station tiles themselves stay walkable (officers stand AT stations).
 */
import type { WardroomLayout } from './layout'
import { ROOM_H, ROOM_W, WALL_BAND } from './layout'

export interface TilePoint {
  x: number
  y: number
}

/** Set of blocked "x,y" keys derived from a layout (pure). */
export function blockedTiles(layout: WardroomLayout): Set<string> {
  const blocked = new Set<string>()
  // Desk props: one tile below each officer's stand tile.
  for (const desk of layout.desks.values()) {
    blocked.add(`${desk.x},${desk.y + 1}`)
  }
  // Conference table core: 3 tiles wide at the table station row.
  const table = layout.stations.get('table')
  if (table) {
    for (let dx = -1; dx <= 1; dx++) {
      blocked.add(`${table.x + dx},${table.y}`)
    }
  }
  return blocked
}

/** Whether an integer tile is walkable under the layout's grid. */
export function isWalkable(
  tile: TilePoint,
  blocked: Set<string>
): boolean {
  if (!Number.isInteger(tile.x) || !Number.isInteger(tile.y)) return false
  if (tile.x < 1 || tile.x > ROOM_W - 2) return false
  if (tile.y < WALL_BAND || tile.y > ROOM_H - 2) return false
  return !blocked.has(`${tile.x},${tile.y}`)
}

/** Fixed neighbor order — determinism (up, right, down, left). */
const NEIGHBORS: ReadonlyArray<TilePoint> = [
  { x: 0, y: -1 },
  { x: 1, y: 0 },
  { x: 0, y: 1 },
  { x: -1, y: 0 },
]

/**
 * BFS shortest path on the walkable grid, endpoints inclusive.
 * Returns integer tile waypoints (collinear runs compressed), or null when
 * either endpoint is unwalkable or no route exists — the caller falls back
 * to a straight line (never invisible, never stuck).
 */
export function findPath(
  layout: WardroomLayout,
  from: TilePoint,
  to: TilePoint
): TilePoint[] | null {
  const blocked = blockedTiles(layout)
  const start = { x: Math.round(from.x), y: Math.round(from.y) }
  const goal = { x: Math.round(to.x), y: Math.round(to.y) }
  if (!isWalkable(start, blocked) || !isWalkable(goal, blocked)) return null
  if (start.x === goal.x && start.y === goal.y) return [start]

  const key = (p: TilePoint) => `${p.x},${p.y}`
  const parent = new Map<string, string>()
  const visited = new Set<string>([key(start)])
  const queue: TilePoint[] = [start]
  let head = 0
  let found = false
  while (head < queue.length) {
    const cur = queue[head++]
    if (cur.x === goal.x && cur.y === goal.y) {
      found = true
      break
    }
    for (const d of NEIGHBORS) {
      const nxt = { x: cur.x + d.x, y: cur.y + d.y }
      const nk = key(nxt)
      if (visited.has(nk) || !isWalkable(nxt, blocked)) continue
      visited.add(nk)
      parent.set(nk, key(cur))
      queue.push(nxt)
    }
  }
  if (!found) return null

  // Reconstruct goal → start, then reverse.
  const rev: TilePoint[] = []
  let curKey: string | undefined = key(goal)
  while (curKey) {
    const [x, y] = curKey.split(',').map(Number)
    rev.push({ x, y })
    curKey = parent.get(curKey)
  }
  rev.reverse()

  // Compress collinear runs into corner waypoints (endpoints kept).
  const out: TilePoint[] = [rev[0]]
  for (let i = 1; i < rev.length - 1; i++) {
    const a = out[out.length - 1]
    const b = rev[i]
    const c = rev[i + 1]
    const abx = b.x - a.x
    const aby = b.y - a.y
    const bcx = c.x - b.x
    const bcy = c.y - b.y
    if (abx * bcy !== aby * bcx) out.push(b)
  }
  out.push(rev[rev.length - 1])
  return out
}

/** Total polyline length in tiles (Euclidean per segment). */
export function pathLength(points: ReadonlyArray<TilePoint>): number {
  let len = 0
  for (let i = 1; i < points.length; i++) {
    const dx = points[i].x - points[i - 1].x
    const dy = points[i].y - points[i - 1].y
    len += Math.sqrt(dx * dx + dy * dy)
  }
  return len
}

/**
 * Position + facing at `dist` tiles along the polyline (pure interpolation).
 */
export function pointAlong(
  points: ReadonlyArray<TilePoint>,
  dist: number
): { x: number; y: number; dx: number; dy: number } {
  if (points.length === 0) return { x: 0, y: 0, dx: 0, dy: 0 }
  let remaining = Math.max(0, dist)
  for (let i = 1; i < points.length; i++) {
    const ax = points[i - 1].x
    const ay = points[i - 1].y
    const dx = points[i].x - ax
    const dy = points[i].y - ay
    const seg = Math.sqrt(dx * dx + dy * dy)
    if (seg <= 0) continue
    if (remaining <= seg) {
      const f = remaining / seg
      return { x: ax + dx * f, y: ay + dy * f, dx, dy }
    }
    remaining -= seg
  }
  const last = points[points.length - 1]
  const prev = points.length > 1 ? points[points.length - 2] : last
  return { x: last.x, y: last.y, dx: last.x - prev.x, dy: last.y - prev.y }
}
