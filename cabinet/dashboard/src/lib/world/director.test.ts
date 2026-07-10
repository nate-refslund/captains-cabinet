/**
 * Director determinism tests — the E0/E1 gate in miniature: identical input
 * sequences MUST yield identical scene sequences (frame-identical render).
 */
import { describe, expect, it } from 'vitest'
import { buildLayout } from './layout'
import { step, targetStation, type DirectorState } from './director'
import type { ShowGrammar } from './grammar'
import type { OfficerPresence } from './types'
import { fnv1a, jitter, seededRng } from './hash'

const GRAMMAR: ShowGrammar = {
  version: 1,
  verbs: {
    working: {
      station: 'desk',
      anim: 'work',
      salience: 0,
      codex: { represents: 'x', mechanism_path: 'y', day0: 'z' },
    },
    reviewing: {
      station: 'board',
      anim: 'work',
      salience: 1,
      codex: { represents: 'x', mechanism_path: 'y', day0: 'z' },
    },
  },
  fallback: { station: 'floor', anim: 'idle' },
  scenes: {},
}

const OFFICERS: Record<string, OfficerPresence> = {
  cos: { present: true, verb: 'working', since: '2026-07-07T10:00:00Z' },
  'bakery-ceo': { present: true, verb: 'reviewing', since: '2026-07-07T10:00:00Z' },
  'newsletter-ceo': { present: false },
}

function runSequence(ticks: number[]) {
  const layout = buildLayout(Object.keys(OFFICERS))
  let state: DirectorState = {}
  const frames: string[] = []
  for (const tick of ticks) {
    const out = step(state, { officers: OFFICERS, grammar: GRAMMAR, layout, tick })
    state = out.state
    frames.push(JSON.stringify(out.scenes))
  }
  return frames
}

describe('determinism', () => {
  it('identical input sequences produce identical scene sequences', () => {
    const ticks = Array.from({ length: 40 }, (_, i) => i)
    expect(runSequence(ticks)).toEqual(runSequence(ticks))
  })

  it('hash + rng are stable across calls', () => {
    expect(fnv1a('cos')).toBe(fnv1a('cos'))
    expect(jitter('cos', 'walk-phase')).toBe(jitter('cos', 'walk-phase'))
    const a = seededRng(42)
    const b = seededRng(42)
    expect([a(), a(), a()]).toEqual([b(), b(), b()])
  })
})

describe('grammar law', () => {
  it('verb maps through grammar to station', () => {
    expect(targetStation('cos', OFFICERS.cos, GRAMMAR)).toEqual({
      stationId: 'desk:cos',
      anim: 'work',
    })
    expect(targetStation('bakery-ceo', OFFICERS['bakery-ceo'], GRAMMAR)).toEqual(
      { stationId: 'board', anim: 'work' }
    )
  })

  it('unknown verb under loaded grammar uses the grammar OWN fallback', () => {
    const p: OfficerPresence = { present: true, verb: 'juggling' }
    expect(targetStation('cos', p, GRAMMAR)).toEqual({
      stationId: 'floor',
      anim: 'idle',
    })
  })

  it('expired presence is honestly asleep', () => {
    expect(targetStation('newsletter-ceo', { present: false }, GRAMMAR)).toEqual({
      stationId: 'bunk:newsletter-ceo',
      anim: 'asleep',
    })
  })

  it('grammar pending → static desk marker, never a walk scene', () => {
    const layout = buildLayout(['cos'])
    let state: DirectorState = {}
    const anims = new Set<string>()
    for (let tick = 0; tick < 30; tick++) {
      const out = step(state, {
        officers: { cos: { present: true, verb: 'working' } },
        grammar: null,
        layout,
        tick,
      })
      state = out.state
      for (const s of out.scenes) anims.add(s.anim)
    }
    expect(anims.has('walk')).toBe(false)
    expect(anims.has('idle')).toBe(true)
  })
})

describe('motion', () => {
  it('officers walk to a retargeted station and arrive', () => {
    const layout = buildLayout(['cos'])
    let state: DirectorState = {}
    // Tick 0: at desk, working.
    let out = step(state, {
      officers: { cos: { present: true, verb: 'working' } },
      grammar: GRAMMAR,
      layout,
      tick: 0,
    })
    state = out.state
    const deskPos = { x: out.scenes[0].x, y: out.scenes[0].y }
    // Retarget to the board.
    out = step(state, {
      officers: { cos: { present: true, verb: 'reviewing' } },
      grammar: GRAMMAR,
      layout,
      tick: 1,
    })
    state = out.state
    expect(out.scenes[0].anim).toBe('walk')
    // Walk long enough to arrive.
    for (let t = 2; t < 200; t++) {
      out = step(state, {
        officers: { cos: { present: true, verb: 'reviewing' } },
        grammar: GRAMMAR,
        layout,
        tick: t,
      })
      state = out.state
    }
    const board = layout.stations.get('board')!
    expect(out.scenes[0].x).toBe(board.x)
    expect(out.scenes[0].y).toBe(board.y)
    expect(out.scenes[0].anim).toBe('work')
    expect({ x: deskPos.x, y: deskPos.y }).not.toEqual({
      x: out.scenes[0].x,
      y: out.scenes[0].y,
    })
  })

  it('layout is stable: sorted slugs, fixed slots', () => {
    const a = buildLayout(['newsletter-ceo', 'cos', 'bakery-ceo'])
    const b = buildLayout(['cos', 'bakery-ceo', 'newsletter-ceo'])
    expect(a.desks.get('cos')).toEqual(b.desks.get('cos'))
    expect(a.desks.get('newsletter-ceo')).toEqual(b.desks.get('newsletter-ceo'))
  })
})
