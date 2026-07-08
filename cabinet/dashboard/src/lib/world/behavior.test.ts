/**
 * Behavior vocabulary tests (world-alive direction §1) — the T1 LIFE gate:
 *  - determinism: identical tick/clock/killswitch sequences → identical
 *    scene sequences, across ALL new state machines;
 *  - pathing bounds: wander + transitions never leave the walkable room,
 *    never teleport (per-tick displacement bounded);
 *  - chat pairing: co-present idle officers pair, face each other, chip;
 *  - micro-loops: seeded desk variation, typing dominates, no lockstep;
 *  - night: asleep at the bunk with a blinking z chip;
 *  - killswitch: frozen mid-stride, resumes without teleporting;
 *  - group scenes: ≥2 coordinating officers meet at distinct table seats.
 */
import { describe, expect, it } from 'vitest'
import { buildLayout, ROOM_H, ROOM_W, WALL_BAND } from './layout'
import {
  DAY_END_HOUR,
  microRoll,
  PAIR_DIST,
  step,
  TICKS_PER_TILE,
  type DirectorState,
} from './director'
import type { ShowGrammar } from './grammar'
import type { OfficerPresence, OfficerScene } from './types'

const CODEX = { represents: 'x', mechanism_path: 'y', day0: 'z' }

/** Mirror of the live v2 law (cabinet/world/show-grammar.yml). */
const GRAMMAR: ShowGrammar = {
  version: 2,
  verbs: {
    working: { station: 'desk', anim: 'work', salience: 0, codex: CODEX },
    reviewing: { station: 'board', anim: 'work', salience: 1, codex: CODEX },
    coordinating: { station: 'board', anim: 'work', salience: 1, codex: CODEX },
    shipping: { station: 'postbox', anim: 'work', salience: 2, codex: CODEX },
  },
  fallback: { station: 'floor', anim: 'idle' },
  idleProgram: {
    waypoints: ['kettle', 'bookshelf', 'window:1', 'window:2'],
    dwellTicks: 24,
    nightStation: 'bunk',
    chatChip: true,
    codex: CODEX,
  },
  groupScenes: {
    coordinating: { minOfficers: 2, station: 'table', codex: CODEX },
  },
  killswitchScene: { freeze: true, wash: 'red', codex: CODEX },
}

const SLUGS = ['comms-officer', 'cos', 'polads-ceo', 'stephie-ceo']

function present(verb: string): OfficerPresence {
  return { present: true, verb, since: '2026-07-08T10:00:00Z' }
}
const EXPIRED: OfficerPresence = { present: false }

interface Frame {
  scenes: OfficerScene[]
}

function run(
  script: Array<{
    ticks: number
    officers: Record<string, OfficerPresence>
    clockHour?: number | null
    killswitch?: boolean
  }>,
  grammar: ShowGrammar | null = GRAMMAR
): Frame[] {
  const allSlugs = new Set<string>()
  for (const seg of script) for (const s of Object.keys(seg.officers)) allSlugs.add(s)
  const layout = buildLayout([...allSlugs])
  let state: DirectorState = {}
  const frames: Frame[] = []
  let tick = 0
  for (const seg of script) {
    for (let i = 0; i < seg.ticks; i++, tick++) {
      const out = step(state, {
        officers: seg.officers,
        grammar,
        layout,
        tick,
        clockHour: seg.clockHour ?? null,
        killswitch: seg.killswitch ?? false,
      })
      state = out.state
      frames.push({ scenes: out.scenes })
    }
  }
  return frames
}

describe('determinism across the full behavior vocabulary', () => {
  const script = [
    { ticks: 300, officers: { cos: present('working'), 'polads-ceo': present('coordinating'), 'stephie-ceo': present('coordinating'), 'comms-officer': EXPIRED }, clockHour: 10 },
    { ticks: 100, officers: { cos: present('reviewing'), 'polads-ceo': present('coordinating'), 'stephie-ceo': present('working'), 'comms-officer': EXPIRED }, clockHour: 14 },
    { ticks: 50, officers: { cos: present('reviewing'), 'polads-ceo': present('coordinating'), 'stephie-ceo': present('working'), 'comms-officer': EXPIRED }, clockHour: 14, killswitch: true },
    { ticks: 200, officers: { cos: EXPIRED, 'polads-ceo': EXPIRED, 'stephie-ceo': EXPIRED, 'comms-officer': EXPIRED }, clockHour: 22 },
  ]

  it('same tick/clock/killswitch sequence → identical scene sequences', () => {
    const a = run(script)
    const b = run(script)
    expect(JSON.stringify(a)).toBe(JSON.stringify(b))
  })
})

describe('idle wander (day) — pathing bounds + no teleports + stagger', () => {
  const officers = Object.fromEntries(SLUGS.map((s) => [s, EXPIRED]))
  const frames = run([{ ticks: 2000, officers, clockHour: 10 }])

  it('positions stay inside the walkable room forever', () => {
    for (const f of frames) {
      for (const s of f.scenes) {
        expect(s.x).toBeGreaterThanOrEqual(1)
        expect(s.x).toBeLessThanOrEqual(ROOM_W - 2)
        expect(s.y).toBeGreaterThanOrEqual(WALL_BAND)
        expect(s.y).toBeLessThanOrEqual(ROOM_H - 2)
      }
    }
  })

  it('transitions are walked — per-tick displacement bounded (no teleports)', () => {
    const last = new Map<string, { x: number; y: number }>()
    const maxStep = 1 / TICKS_PER_TILE + 0.15
    for (const f of frames) {
      for (const s of f.scenes) {
        const prev = last.get(s.slug)
        if (prev) {
          const d = Math.hypot(s.x - prev.x, s.y - prev.y)
          expect(d, s.slug).toBeLessThanOrEqual(maxStep)
        }
        last.set(s.slug, { x: s.x, y: s.y })
      }
    }
  })

  it('officers wander (walk scenes exist) and dwell (idle scenes exist)', () => {
    const anims = new Set(frames.flatMap((f) => f.scenes.map((s) => s.anim)))
    expect(anims.has('walk')).toBe(true)
    expect(anims.has('idle')).toBe(true)
  })

  it('phase-staggered: officers are NOT in lockstep', () => {
    // At a mid-run tick the four wanderers must not share one position.
    const f = frames[600]
    const positions = new Set(f.scenes.map((s) => `${s.x.toFixed(2)},${s.y.toFixed(2)}`))
    expect(positions.size).toBeGreaterThan(1)
    // And their ongoing walk/dwell SCHEDULES diverge (the fnv1a wander-phase
    // stagger): after the cold-start settles, no two officers share an
    // identical walk-tick signature, and at some frame one officer walks
    // while another dwells. (First-walk tick is NOT the measure — everyone
    // legitimately starts their first journey on the same cold-start tick.)
    const SETTLE = 200
    const walkTicks = new Map<string, number[]>()
    for (const s of SLUGS) walkTicks.set(s, [])
    frames.forEach((f2, i) => {
      if (i < SETTLE) return
      for (const s of f2.scenes) {
        if (s.anim === 'walk') walkTicks.get(s.slug)!.push(i)
      }
    })
    const signatures = SLUGS.map((s) => walkTicks.get(s)!.join(','))
    expect(new Set(signatures).size).toBe(SLUGS.length)
    const mixedFrame = frames
      .slice(SETTLE)
      .some(
        (f2) =>
          f2.scenes.some((s) => s.anim === 'walk') &&
          f2.scenes.some((s) => s.anim !== 'walk')
      )
    expect(mixedFrame).toBe(true)
  })

  it('day wander never puts anyone at the bunk asleep', () => {
    for (const f of frames.slice(500)) {
      for (const s of f.scenes) {
        expect(s.anim).not.toBe('asleep')
      }
    }
  })
})

describe('chat pairing', () => {
  const pairGrammar: ShowGrammar = {
    ...GRAMMAR,
    idleProgram: { ...GRAMMAR.idleProgram!, waypoints: ['kettle'] },
  }
  const officers = { cos: EXPIRED, 'polads-ceo': EXPIRED }

  it('two idle officers on one waypoint pair up: ellipsis chips, facing each other', () => {
    const frames = run([{ ticks: 800, officers, clockHour: 10 }], pairGrammar)
    const paired = frames.filter((f) => {
      const [a, b] = f.scenes
      return a?.chip === 'ellipsis' && b?.chip === 'ellipsis'
    })
    expect(paired.length).toBeGreaterThan(0)
    for (const f of paired) {
      const [a, b] = f.scenes
      expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeLessThanOrEqual(PAIR_DIST)
      // Face each other by relative x.
      if (a.x <= b.x) {
        expect(a.facing).toBe('right')
        expect(b.facing).toBe('left')
      } else {
        expect(a.facing).toBe('left')
        expect(b.facing).toBe('right')
      }
    }
  })

  it('chat_chip=false → no ellipsis chips ever', () => {
    const noChip: ShowGrammar = {
      ...pairGrammar,
      idleProgram: { ...pairGrammar.idleProgram!, chatChip: false },
    }
    const frames = run([{ ticks: 800, officers, clockHour: 10 }], noChip)
    for (const f of frames) {
      for (const s of f.scenes) expect(s.chip).not.toBe('ellipsis')
    }
  })
})

describe('night — asleep at the bunk per the snapshot clock', () => {
  const officers = { cos: EXPIRED, 'polads-ceo': EXPIRED }

  it('night hours (and unknown clock) → bunk + asleep', () => {
    for (const clockHour of [22, 3, null]) {
      const frames = run([{ ticks: 300, officers, clockHour }])
      const tail = frames[frames.length - 1]
      for (const s of tail.scenes) {
        expect(s.stationId).toBe(`bunk:${s.slug}`)
        expect(s.anim).toBe('asleep')
      }
    }
  })

  it('z chip blinks while asleep (on some ticks, off on others)', () => {
    const frames = run([{ ticks: 300, officers, clockHour: 23 }])
    const settled = frames.slice(200)
    const on = settled.filter((f) => f.scenes[0].chip === 'zzz').length
    expect(on).toBeGreaterThan(0)
    expect(on).toBeLessThan(settled.length)
  })

  it('day → night transition is WALKED to the bunk', () => {
    const frames = run([
      { ticks: 400, officers, clockHour: 10 },
      { ticks: 300, officers, clockHour: DAY_END_HOUR },
    ])
    const after = frames.slice(400)
    expect(after.some((f) => f.scenes.some((s) => s.anim === 'walk'))).toBe(true)
    const tail = after[after.length - 1]
    for (const s of tail.scenes) expect(s.anim).toBe('asleep')
  })
})

describe('micro-loops at the desk', () => {
  const officers = { cos: present('working'), 'stephie-ceo': present('working') }

  it('typing dominates; micro states are the only variation; deterministic', () => {
    const frames = run([{ ticks: 4096, officers, clockHour: 10 }])
    const frames2 = run([{ ticks: 4096, officers, clockHour: 10 }])
    expect(JSON.stringify(frames)).toBe(JSON.stringify(frames2))
    const micros = new Set<string>()
    let workTicks = 0
    for (const f of frames) {
      const s = f.scenes.find((sc) => sc.slug === 'cos')!
      if (s.micro) micros.add(s.micro)
      if (s.anim === 'work') workTicks++
    }
    for (const m of micros) {
      expect(['stretch', 'sip', 'glance']).toContain(m)
    }
    expect(workTicks / frames.length).toBeGreaterThan(0.6)
  })

  it('micro windows fire per the seeded roll (cross-check vs microRoll)', () => {
    const frames = run([{ ticks: 4096, officers, clockHour: 10 }])
    // Some window in 32 windows should roll a special (10..13) for at least
    // one of the two officers — and the scenes must reflect only rolls.
    let sawSpecial = false
    for (const f of frames) {
      for (const s of f.scenes) {
        if (s.micro) sawSpecial = true
      }
    }
    const rolls: number[] = []
    for (let w = 0; w < 40; w++) rolls.push(microRoll('cos', w), microRoll('stephie-ceo', w))
    const expectSpecial = rolls.some((r) => r >= 10 && r <= 13)
    expect(sawSpecial).toBe(expectSpecial)
  })

  it('sip walks to the kettle and back — never a teleport', () => {
    const frames = run([{ ticks: 8192, officers, clockHour: 10 }])
    const last = new Map<string, { x: number; y: number }>()
    const maxStep = 1 / TICKS_PER_TILE + 0.15
    for (const f of frames) {
      for (const s of f.scenes) {
        const prev = last.get(s.slug)
        if (prev) {
          expect(Math.hypot(s.x - prev.x, s.y - prev.y)).toBeLessThanOrEqual(maxStep)
        }
        last.set(s.slug, { x: s.x, y: s.y })
      }
    }
  })
})

describe('group scenes — coordinating meets at the table', () => {
  it('≥2 coordinating officers take DISTINCT seeded seats; dissolves when the condition does', () => {
    const meeting = {
      cos: present('coordinating'),
      'polads-ceo': present('coordinating'),
      'stephie-ceo': present('working'),
    }
    const dissolved = {
      cos: present('coordinating'),
      'polads-ceo': present('working'),
      'stephie-ceo': present('working'),
    }
    const frames = run([
      { ticks: 300, officers: meeting, clockHour: 10 },
      { ticks: 300, officers: dissolved, clockHour: 10 },
    ])
    const settled = frames[299]
    const seats = settled.scenes
      .filter((s) => s.stationId.startsWith('seat:table:'))
      .map((s) => s.stationId)
    expect(seats.length).toBe(2)
    expect(new Set(seats).size).toBe(2)
    for (const s of settled.scenes) {
      if (s.stationId.startsWith('seat:table:')) expect(s.anim).toBe('idle')
      if (s.slug === 'stephie-ceo') expect(s.stationId).toBe('desk:stephie-ceo')
    }
    // After polads-ceo drops the verb, cos coordinates SOLO → board mapping.
    const after = frames[599]
    const cos = after.scenes.find((s) => s.slug === 'cos')!
    expect(cos.stationId).toBe('board')
  })
})

describe('killswitch — freeze mid-stride, resume without teleport', () => {
  it('frozen frames are identical; unfreeze resumes the journey exactly', () => {
    const walking = { cos: present('shipping') } // desk → postbox journey
    const frames = run([
      { ticks: 4, officers: walking, clockHour: 10 }, // start walking
      { ticks: 30, officers: walking, clockHour: 10, killswitch: true },
      { ticks: 120, officers: walking, clockHour: 10 },
    ])
    // Frozen window: positions identical, mid-stride (walk anim held).
    const frozen = frames.slice(4, 34)
    const first = JSON.stringify(frozen[0].scenes)
    for (const f of frozen) {
      expect(JSON.stringify(f.scenes)).toBe(first)
    }
    expect(frozen[0].scenes[0].anim).toBe('walk')
    // Resume: no teleport at the freeze boundary, journey completes.
    const before = frozen[frozen.length - 1].scenes[0]
    const after = frames[34].scenes[0]
    expect(Math.hypot(after.x - before.x, after.y - before.y)).toBeLessThanOrEqual(
      1 / TICKS_PER_TILE + 0.15
    )
    const tail = frames[frames.length - 1].scenes[0]
    expect(tail.stationId).toBe('postbox')
    expect(tail.anim).toBe('work')
  })
})
