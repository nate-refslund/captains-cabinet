/**
 * Wardroom layout — one dense room, compiled from the live officer roster.
 *
 * Positions are DETERMINISTIC: desks are assigned in sorted-slug order
 * (stable birth-order stand-in until role_lineage ordering lands in E2's
 * fold), so the room can never drift from the org and never reshuffles
 * between sessions. Integer tile math only (determinism doctrine).
 */
import type { Station } from './types'

/** Logical tile size in world units (16px art grid, chassis baseline). */
export const TILE = 16

/** Room size in tiles (one dense Wardroom; E2 grows the town around it). */
export const ROOM_W = 40
export const ROOM_H = 24

/** Fixed civic stations every deployment shares (comparability). */
export const FIXED_STATIONS: Station[] = [
  { id: 'board', x: 20, y: 3, label: 'work board' },
  { id: 'postbox', x: 35, y: 12, label: 'postbox' },
  { id: 'door', x: 2, y: 12, label: 'door' },
  { id: 'dojo', x: 20, y: 20, label: 'dojo corner' },
  { id: 'floor', x: 18, y: 12, label: 'floor' },
  { id: 'lever', x: 37, y: 3, label: 'killswitch lever' },
]

export interface WardroomLayout {
  widthPx: number
  heightPx: number
  stations: Map<string, Station>
  /** Desk station per officer slug (station id `desk:<slug>`). */
  desks: Map<string, Station>
  /** Bunk (asleep) station per officer slug. */
  bunks: Map<string, Station>
}

/** Deterministic desk slots along the room's mid band. */
export function buildLayout(slugs: string[]): WardroomLayout {
  const ordered = [...slugs].sort()
  const stations = new Map<string, Station>()
  for (const s of FIXED_STATIONS) stations.set(s.id, s)
  const desks = new Map<string, Station>()
  const bunks = new Map<string, Station>()
  const n = Math.max(ordered.length, 1)
  const span = ROOM_W - 12 // leave margins for door/postbox columns
  ordered.forEach((slug, i) => {
    const x = 6 + Math.round(((i + 0.5) * span) / n)
    const desk: Station = { id: `desk:${slug}`, x, y: 8, label: `${slug} desk` }
    const bunk: Station = { id: `bunk:${slug}`, x, y: 17, label: `${slug} bunk` }
    stations.set(desk.id, desk)
    stations.set(bunk.id, bunk)
    desks.set(slug, desk)
    bunks.set(slug, bunk)
  })
  return {
    widthPx: ROOM_W * TILE,
    heightPx: ROOM_H * TILE,
    stations,
    desks,
    bunks,
  }
}
