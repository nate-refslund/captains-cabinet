/**
 * Walkable-grid pathing tests — bounds, obstacle avoidance, adjacency,
 * determinism (the T1 "pathing bounds" gate).
 */
import { describe, expect, it } from 'vitest'
import { buildLayout, ROOM_H, ROOM_W, WALL_BAND } from './layout'
import {
  blockedTiles,
  findPath,
  isWalkable,
  pathLength,
  pointAlong,
} from './path'

const SLUGS = ['comms-officer', 'cos', 'bakery-ceo', 'newsletter-ceo']

describe('walkable grid', () => {
  const layout = buildLayout(SLUGS)
  const blocked = blockedTiles(layout)

  it('room border + wall band are unwalkable', () => {
    expect(isWalkable({ x: 0, y: 10 }, blocked)).toBe(false)
    expect(isWalkable({ x: ROOM_W - 1, y: 10 }, blocked)).toBe(false)
    expect(isWalkable({ x: 10, y: WALL_BAND - 1 }, blocked)).toBe(false)
    expect(isWalkable({ x: 10, y: ROOM_H - 1 }, blocked)).toBe(false)
    expect(isWalkable({ x: 10, y: 10 }, blocked)).toBe(true)
  })

  it('desk props and the table core are obstacles; stand tiles stay free', () => {
    for (const desk of layout.desks.values()) {
      expect(isWalkable({ x: desk.x, y: desk.y }, blocked)).toBe(true) // stand
      expect(isWalkable({ x: desk.x, y: desk.y + 1 }, blocked)).toBe(false) // prop
    }
    const table = layout.stations.get('table')!
    for (const dx of [-1, 0, 1]) {
      expect(isWalkable({ x: table.x + dx, y: table.y }, blocked)).toBe(false)
    }
    // Seats around the table remain walkable.
    expect(isWalkable({ x: table.x - 2, y: table.y }, blocked)).toBe(true)
    expect(isWalkable({ x: table.x + 1, y: table.y - 1 }, blocked)).toBe(true)
  })

  it('every fixed station + desk + bunk tile is walkable (reachable law)', () => {
    for (const st of layout.stations.values()) {
      if (st.id === 'table') continue // core is an obstacle; seats are targets
      expect(isWalkable({ x: st.x, y: st.y }, blocked), st.id).toBe(true)
    }
  })
})

describe('findPath', () => {
  const layout = buildLayout(SLUGS)
  const blocked = blockedTiles(layout)

  it('desk → board: connected, 4-adjacent corners, endpoints exact, in bounds', () => {
    const desk = layout.desks.get('cos')!
    const board = layout.stations.get('board')!
    const path = findPath(layout, { x: desk.x, y: desk.y }, { x: board.x, y: board.y })
    expect(path).not.toBeNull()
    expect(path![0]).toEqual({ x: desk.x, y: desk.y })
    expect(path![path!.length - 1]).toEqual({ x: board.x, y: board.y })
    for (const p of path!) {
      expect(isWalkable(p, blocked)).toBe(true)
    }
    // Corner waypoints connect along axis-aligned segments.
    for (let i = 1; i < path!.length; i++) {
      const dx = path![i].x - path![i - 1].x
      const dy = path![i].y - path![i - 1].y
      expect(dx === 0 || dy === 0).toBe(true)
    }
  })

  it('routes around the table core (never through obstacles)', () => {
    const table = layout.stations.get('table')!
    // Cross the table row from left of the table to right of it.
    const path = findPath(
      layout,
      { x: table.x - 4, y: table.y },
      { x: table.x + 4, y: table.y }
    )
    expect(path).not.toBeNull()
    // Expand corners into full tile runs and assert none is blocked.
    for (let i = 1; i < path!.length; i++) {
      const a = path![i - 1]
      const b = path![i]
      const steps = Math.abs(b.x - a.x) + Math.abs(b.y - a.y)
      for (let s = 0; s <= steps; s++) {
        const x = a.x + Math.sign(b.x - a.x) * Math.min(s, Math.abs(b.x - a.x))
        const y = a.y + Math.sign(b.y - a.y) * Math.min(s, Math.abs(b.y - a.y))
        expect(isWalkable({ x, y }, blocked), `${x},${y}`).toBe(true)
      }
    }
  })

  it('unwalkable endpoints → null (caller falls back, never throws)', () => {
    expect(findPath(layout, { x: 0, y: 0 }, { x: 10, y: 10 })).toBeNull()
    const table = layout.stations.get('table')!
    expect(
      findPath(layout, { x: 10, y: 10 }, { x: table.x, y: table.y })
    ).toBeNull()
  })

  it('deterministic: identical args → identical path', () => {
    const a = findPath(layout, { x: 5, y: 5 }, { x: 35, y: 20 })
    const b = findPath(layout, { x: 5, y: 5 }, { x: 35, y: 20 })
    expect(a).toEqual(b)
  })
})

describe('polyline interpolation', () => {
  it('pathLength + pointAlong walk the polyline monotonically', () => {
    const pts = [
      { x: 0, y: 0 },
      { x: 4, y: 0 },
      { x: 4, y: 3 },
    ]
    expect(pathLength(pts)).toBe(7)
    expect(pointAlong(pts, 0)).toMatchObject({ x: 0, y: 0 })
    expect(pointAlong(pts, 4)).toMatchObject({ x: 4, y: 0 })
    expect(pointAlong(pts, 5.5)).toMatchObject({ x: 4, y: 1.5 })
    // Past the end clamps to the final point.
    expect(pointAlong(pts, 99)).toMatchObject({ x: 4, y: 3 })
    // Facing hints follow the active segment.
    expect(pointAlong(pts, 2).dx).toBeGreaterThan(0)
    expect(pointAlong(pts, 6).dy).toBeGreaterThan(0)
  })
})
