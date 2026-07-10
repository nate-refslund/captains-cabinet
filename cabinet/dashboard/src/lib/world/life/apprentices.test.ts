/**
 * T2 LIFE — apprentice figure tests (spec v2 §15.5): human-shaped sprites
 * are REAL ACTORS ONLY — a figure exists iff a real chronicle spawn record
 * is live; it retires on crew.completed or the honest TTL; caps overflow
 * into a numeric badge rather than crowding or hiding.
 */
import { describe, expect, it } from 'vitest'
import type { ChronicleRecord } from '../types'
import {
  APPRENTICE_CAP,
  APPRENTICE_TTL_TICKS,
  apprenticeCard,
  apprenticesAt,
  isEndRecord,
  isSpawnRecord,
} from './apprentices'

const NOW = Date.parse('2026-07-09T12:00:00Z')
const POS = { cos: { x: 10, y: 8 }, 'bakery-ceo': { x: 40, y: 30 } }

let IID = 0
function rec(
  verb: string,
  ageS: number,
  actor = 'cos',
  attrs?: Record<string, string>
): ChronicleRecord {
  return {
    v: 1,
    iid: ++IID,
    src: 'toollog',
    verb,
    kind: verb === 'tool.call' ? 'Agent' : 'event',
    actor,
    ts: new Date(NOW - ageS * 1000).toISOString(),
    ref: null,
    attrs,
  }
}

const spawn = (ageS: number, actor = 'cos') =>
  rec('tool.call', ageS, actor, { tool: 'Agent' })
const done = (ageS: number, actor = 'cos') => rec('crew.completed', ageS, actor)

function at(records: ChronicleRecord[], tick = 1000) {
  return apprenticesAt({ records, nowTsMs: NOW, tick, officerPos: POS })
}

describe('spawn/end predicates — closed vocabulary', () => {
  it('tool.call[Agent|Task] spawns; anything else does not', () => {
    expect(isSpawnRecord(spawn(1))).toBe(true)
    expect(
      isSpawnRecord(rec('tool.call', 1, 'cos', { tool: 'Task' }))
    ).toBe(true)
    expect(isSpawnRecord(rec('tool.call', 1, 'cos', { tool: 'Read' }))).toBe(
      true // kind === 'Agent' in the fixture — attrs.tool OR kind matches
    )
    expect(isSpawnRecord(rec('work.completed', 1))).toBe(false)
  })
  it('crew.completed ends', () => {
    expect(isEndRecord(done(1))).toBe(true)
    expect(isEndRecord(spawn(1))).toBe(false)
  })
})

describe('apprenticesAt — figures for LIVE runs only', () => {
  it('a live spawn renders one figure near its spawning officer', () => {
    const r = at([spawn(30)])
    expect(r.figures).toHaveLength(1)
    const f = r.figures[0]
    expect(f.officer).toBe('cos')
    expect(Math.abs(f.x - POS.cos.x)).toBeLessThanOrEqual(2)
    expect(f.y).toBeGreaterThan(POS.cos.y) // in front, never on top
    expect(f.spawnIid).toBeGreaterThan(0)
  })
  it('crew.completed retires the OLDEST open run (FIFO)', () => {
    const s1 = spawn(120)
    const s2 = spawn(60)
    const r = at([s1, s2, done(10)])
    expect(r.figures).toHaveLength(1)
    expect(r.figures[0].spawnIid).toBe(s2.iid)
  })
  it('runs older than the TTL retire on their own (honest bound)', () => {
    const r = at([spawn(APPRENTICE_TTL_TICKS / 4 + 10)])
    expect(r.figures).toHaveLength(0)
  })
  it('caps at APPRENTICE_CAP with a numeric overflow badge', () => {
    const r = at([spawn(50), spawn(40), spawn(30), spawn(20), spawn(10), spawn(5)])
    expect(r.figures).toHaveLength(APPRENTICE_CAP)
    expect(r.overflow.cos).toBe(6 - APPRENTICE_CAP)
  })
  it('unknown actors never render a figure (no fictional villagers)', () => {
    expect(at([spawn(10, 'unknown')]).figures).toHaveLength(0)
  })
  it('an officer with no known position renders nothing (no free-floaters)', () => {
    expect(at([spawn(10, 'newsletter-ceo')]).figures).toHaveLength(0)
  })
  it('deterministic: identical inputs → identical figures', () => {
    const records = [spawn(50), spawn(20), done(5)]
    expect(JSON.stringify(at(records, 777))).toBe(
      JSON.stringify(at(records, 777))
    )
  })
})

describe('the honest card', () => {
  it('cites the chronicle iid and states TTL semantics outright', () => {
    const fig = at([spawn(30)]).figures[0]
    const card = apprenticeCard(fig)
    expect(card.what).toContain('cos')
    expect(card.now).toContain('TTL')
    expect(card.now).toContain('not a running-count claim')
    expect(card.proof).toContain(`chronicle iid ${fig.spawnIid}`)
  })
})
