/**
 * WAKE/SLEEP — the refusals, the order, and the reversal.
 *
 * A Server Action is a POST endpoint with a global action id; middleware never
 * covers action dispatch. So every arm here drives the REAL exported action and
 * asserts that the dangerous thing — a command against launchd on somebody's
 * Mac — did not happen, rather than asserting a returned flag. The distinction
 * matters: `officers.ts` shipped 19 actions that returned `{success: true}` for
 * work that never ran, and the lesson was to check the effect, not the value.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const {
  mockVerify,
  mockOnboardingComplete,
  mockRunCrewOp,
  mockRedisSet,
  mockRedisDel,
  mockReadRoster,
} = vi.hoisted(() => ({
  mockVerify: vi.fn<() => Promise<boolean>>(),
  mockOnboardingComplete: vi.fn<() => Promise<boolean>>(),
  mockRunCrewOp: vi.fn(),
  mockRedisSet: vi.fn(),
  mockRedisDel: vi.fn(),
  mockReadRoster: vi.fn(),
}))

let mockIsMockRedis = false

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ verifySession: mockVerify }))
// The state-file half. `completion.ts` became the PURE predicate while this
// branch was in flight (the arrival screen is a client component, and gating it
// on a module importing node:fs/promises 500'd /onboarding), so the disk read
// this mock stands in for now lives next door. Mocking the module the action
// does NOT import would leave the real disk read live behind a green mock.
vi.mock('@/lib/onboarding/completion-state-file', () => ({ isOnboardingComplete: mockOnboardingComplete }))
vi.mock('@/lib/redis', () => ({
  default: { set: mockRedisSet, del: mockRedisDel },
  get isMockRedis() {
    return mockIsMockRedis
  },
  storeReading: { posture: 'live', source: 'the configured store', fabricated: false },
}))
vi.mock('@/lib/crew-ops', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/crew-ops')>()
  return { ...actual, runCrewOp: mockRunCrewOp }
})
vi.mock('@/lib/crew-roster', () => ({
  readRoster: mockReadRoster,
  officerNameSources: () => ({ titles: { 'first-lane-ceo': 'First Lane CEO' }, laneNames: {} }),
}))

import { sleepCrew, wakeCrew } from './crew'

const ROSTER = [
  { slug: 'cos', title: 'Chair', onDemand: false },
  { slug: 'first-lane-ceo', title: 'First Lane CEO', onDemand: true },
]

beforeEach(() => {
  vi.clearAllMocks()
  mockIsMockRedis = false
  mockVerify.mockResolvedValue(true)
  mockOnboardingComplete.mockResolvedValue(true)
  mockReadRoster.mockReturnValue(ROSTER)
  mockRedisSet.mockResolvedValue('OK')
  mockRedisDel.mockResolvedValue(1)
  mockRunCrewOp.mockImplementation(async (op: string, slug: string) => ({
    op,
    slug,
    ok: true,
    detail: `deployed: com.cabinet.officer.${slug}`,
  }))
})
afterEach(() => vi.unstubAllEnvs())

describe('nothing runs until every precondition holds', () => {
  it('UNAUTHENTICATED — refused, and no command and no store write', async () => {
    mockVerify.mockResolvedValue(false)
    for (const action of [wakeCrew, sleepCrew]) {
      const out = await action()
      expect(out.ok).toBe(false)
      expect(out.message).toBe('Unauthorized')
    }
    expect(mockRunCrewOp).not.toHaveBeenCalled()
    expect(mockRedisSet).not.toHaveBeenCalled()
    expect(mockRedisDel).not.toHaveBeenCalled()
  })

  it('ONBOARDING INCOMPLETE — refused in plain words, nothing started', async () => {
    mockOnboardingComplete.mockResolvedValue(false)
    const out = await wakeCrew()
    expect(out.ok).toBe(false)
    expect(out.message).toContain('still being set up')
    expect(mockRunCrewOp).not.toHaveBeenCalled()
    expect(mockRedisSet).not.toHaveBeenCalled()
  })

  it('ONBOARDING INCOMPLETE blocks SLEEP too — a refusal that only guards one door is not one', async () => {
    mockOnboardingComplete.mockResolvedValue(false)
    const out = await sleepCrew()
    expect(out.ok).toBe(false)
    expect(mockRunCrewOp).not.toHaveBeenCalled()
  })

  it('NO STORE — refused, because a wake nobody can then observe is a dead end', async () => {
    mockIsMockRedis = true
    const out = await wakeCrew()
    expect(out.ok).toBe(false)
    expect(out.message).toContain('not connected to a cabinet')
    expect(mockRunCrewOp).not.toHaveBeenCalled()
  })

  it('EMPTY ROSTER — refused rather than guessing a fleet', async () => {
    mockReadRoster.mockReturnValue([])
    const out = await wakeCrew()
    expect(out.ok).toBe(false)
    expect(out.message).toContain('no crew on its roster')
    expect(mockRunCrewOp).not.toHaveBeenCalled()
  })

  it('a roster of ONLY consultants is an empty wake — the deploy script refuses them', async () => {
    mockReadRoster.mockReturnValue([{ slug: 'first-lane-ceo', title: null, onDemand: true }])
    const out = await wakeCrew()
    expect(out.ok).toBe(false)
    expect(mockRunCrewOp).not.toHaveBeenCalled()
  })
})

describe('wake — what it runs, and on whom', () => {
  it('runs the wake op for every always-on officer and NO ONE else', async () => {
    const out = await wakeCrew()
    expect(out.ok).toBe(true)
    expect(mockRunCrewOp).toHaveBeenCalledTimes(1)
    expect(mockRunCrewOp).toHaveBeenCalledWith('wake', 'cos')
    // The on-demand lane CEO is never keepalive-deployed: promising it would
    // be promising something deploy-mac.sh refuses.
    expect(mockRunCrewOp).not.toHaveBeenCalledWith('wake', 'first-lane-ceo')
  })

  it('marks only the officers that actually started as expected-active', async () => {
    mockReadRoster.mockReturnValue([
      { slug: 'cos', title: null, onDemand: false },
      { slug: 'ops', title: null, onDemand: false },
    ])
    mockRunCrewOp.mockImplementation(async (op: string, slug: string) => ({
      op,
      slug,
      ok: slug === 'cos',
      detail: slug === 'cos' ? 'deployed' : 'Bootstrap failed: 5: Input/output error',
    }))
    const out = await wakeCrew()
    expect(out.ok).toBe(false)
    expect(out.message).toContain('1 of 2')
    expect(mockRedisSet).toHaveBeenCalledTimes(1)
    expect(mockRedisSet).toHaveBeenCalledWith('cabinet:officer:expected:cos', 'active')
    // The last stop's time is cleared with the wake, so the NEXT sleep's
    // leftover-vs-still-running comparison is against that sleep, not an old one.
    expect(mockRedisDel).toHaveBeenCalledWith('cabinet:officer:stop-requested:cos')
    expect(mockRedisDel).not.toHaveBeenCalledWith('cabinet:officer:stop-requested:ops')
    // The failed one must NOT be claimed: an officer marked active that nobody
    // started is exactly the invented alarm this release removes.
    expect(mockRedisSet).not.toHaveBeenCalledWith('cabinet:officer:expected:ops', 'active')
  })

  it('every step carries a plain-word label and the script\'s own detail', async () => {
    const out = await wakeCrew()
    expect(out.steps).toHaveLength(1)
    expect(out.steps[0].label).toBe('Starting First Mate in the background')
    expect(out.steps[0].detail).toContain('com.cabinet.officer.cos')
  })

  it('a total failure says nothing changed, and offers no false success', async () => {
    mockRunCrewOp.mockResolvedValue({ op: 'wake', slug: 'cos', ok: false, detail: 'nope' })
    const out = await wakeCrew()
    expect(out.ok).toBe(false)
    expect(out.message).toContain('Nothing started')
    expect(mockRedisSet).not.toHaveBeenCalled()
  })

  it('a refusal thrown by the allowlist becomes a failed STEP, never an unhandled crash', async () => {
    const { CrewOpRefused } = await import('@/lib/crew-ops')
    mockRunCrewOp.mockRejectedValue(new CrewOpRefused('not an officer id: cos;id'))
    const out = await wakeCrew()
    expect(out.ok).toBe(false)
    expect(out.steps[0].ok).toBe(false)
    expect(out.steps[0].detail).toContain('not an officer id')
  })

  it('IDEMPOTENT — pressing it twice issues the same single command each time', async () => {
    await wakeCrew()
    await wakeCrew()
    expect(mockRunCrewOp).toHaveBeenCalledTimes(2)
    for (const call of mockRunCrewOp.mock.calls) expect(call).toEqual(['wake', 'cos'])
  })
})

describe('sleep — the same crew, reversed', () => {
  it('stops exactly the officers wake starts', async () => {
    const out = await sleepCrew()
    expect(out.ok).toBe(true)
    expect(mockRunCrewOp).toHaveBeenCalledTimes(1)
    expect(mockRunCrewOp).toHaveBeenCalledWith('sleep', 'cos')
  })

  it('writes the deliberate-stop marker BEFORE the bootout', async () => {
    const order: string[] = []
    mockRedisSet.mockImplementation(async (key: string, value: string) => {
      order.push(`set ${key}=${value}`)
      return 'OK'
    })
    mockRunCrewOp.mockImplementation(async (op: string, slug: string) => {
      order.push(`run ${op}:${slug}`)
      return { op, slug, ok: true, detail: 'stopped' }
    })
    await sleepCrew()
    // Marker first: between the bootout and the marker, the card would alarm
    // about an officer the operator deliberately stopped. The stop TIME goes
    // with it — without it the card cannot tell the heartbeat that outlives a
    // successful stop from one proving the stop never took.
    expect(order[0]).toBe('set cabinet:officer:expected:cos=stopped')
    expect(order[1]).toMatch(/^set cabinet:officer:stop-requested:cos=/)
    expect(order[2]).toBe('run sleep:cos')
  })

  it('a partial stop says so rather than claiming the crew is asleep', async () => {
    mockReadRoster.mockReturnValue([
      { slug: 'cos', title: null, onDemand: false },
      { slug: 'ops', title: null, onDemand: false },
    ])
    mockRunCrewOp.mockImplementation(async (op: string, slug: string) => ({
      op,
      slug,
      ok: slug === 'cos',
      detail: '',
    }))
    const out = await sleepCrew()
    expect(out.ok).toBe(false)
    expect(out.message).toContain('1 of 2')
    expect(out.message).toContain('still running')
  })

  it('IDEMPOTENT — an already-asleep crew is a success, not an error', async () => {
    await sleepCrew()
    const out = await sleepCrew()
    expect(out.ok).toBe(true)
  })
})
