/**
 * killswitch.ts auth-guard coverage — before this guard an unauthenticated
 * POST of toggleKillSwitch could flip the entire fleet's kill switch. Pins:
 * unauthenticated → Unauthorized AND Redis is never touched; authenticated →
 * proceeds to the Redis mutation.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { mockVerify, mockRedisGet, mockRedisSet, mockRedisDel } = vi.hoisted(() => ({
  mockVerify: vi.fn<() => Promise<boolean>>(),
  mockRedisGet: vi.fn(),
  mockRedisSet: vi.fn(),
  mockRedisDel: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ verifySession: mockVerify }))
vi.mock('@/lib/redis', () => ({
  default: { get: mockRedisGet, set: mockRedisSet, del: mockRedisDel },
  // A LIVE store. The arms above are about auth and the read-back; the posture
  // gate has its own describe at the bottom, where this is varied per test.
  // These two are load-bearing, not decorative: vitest 4 THROWS on an
  // undeclared named export ('No "isMockRedis" export is defined on the
  // "@/lib/redis" mock'), so omitting them errors four arms rather than
  // handing back a falsy `undefined` — measured, because the reverse was
  // assumed here first and it is the wrong reason to keep a correct line.
  isMockRedis: false,
  storeReading: { posture: 'live', source: 'the configured store', fabricated: false },
}))

import { toggleKillSwitch } from './killswitch'

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubEnv('MOCK_DATA', '')
  vi.stubEnv('NODE_ENV', 'test')
})

afterEach(() => vi.unstubAllEnvs())

describe('toggleKillSwitch', () => {
  it('unauthenticated → Unauthorized, and the fleet lever is never touched', async () => {
    mockVerify.mockResolvedValue(false)
    expect(await toggleKillSwitch('activate')).toEqual({
      success: false,
      error: 'Unauthorized',
    })
    expect(mockRedisGet).not.toHaveBeenCalled()
    expect(mockRedisSet).not.toHaveBeenCalled()
    expect(mockRedisDel).not.toHaveBeenCalled()
  })

  it('authenticated → proceeds to flip the switch, and reads it back', async () => {
    mockVerify.mockResolvedValue(true)
    // Pre-read: inactive. Post-read: the write landed. Two calls now, because
    // the action proves the write instead of assuming it.
    mockRedisGet.mockResolvedValueOnce(null).mockResolvedValueOnce('active')
    const res = await toggleKillSwitch('activate')
    expect(res).toEqual({ success: true })
    expect(mockRedisSet).toHaveBeenCalledWith('cabinet:killswitch', 'active')
    expect(mockRedisGet).toHaveBeenCalledTimes(2)
  })

  // ── the read-back, 2026-07-31 ───────────────────────────────────────────
  // This action returned `{success:true}` from HAVING ISSUED the command. A
  // store that accepted the SET and did not keep it — a read-only replica, an
  // eviction, a competing DEL loop, a mock store standing in for a fleet that
  // was never contacted — came back as success, and the header pill flipped to
  // "officers halted" over a fleet that was still running. Both arms below FAIL
  // against the pre-change code, which never issued the second GET at all.
  it('activate that does not land → failure naming what the store actually reads', async () => {
    mockVerify.mockResolvedValue(true)
    mockRedisGet.mockResolvedValueOnce(null).mockResolvedValueOnce(null)
    const res = await toggleKillSwitch('activate')
    expect(res.success).toBe(false)
    expect(res.error).toMatch(/did not take/)
    expect(res.error).toMatch(/\(absent\)/)
  })

  it('deactivate that does not land → failure, never a silent success', async () => {
    mockVerify.mockResolvedValue(true)
    mockRedisGet.mockResolvedValueOnce('active').mockResolvedValueOnce('active')
    const res = await toggleKillSwitch('deactivate')
    expect(res.success).toBe(false)
    expect(res.error).toMatch(/did not take/)
    expect(mockRedisDel).toHaveBeenCalledWith('cabinet:killswitch')
  })

  it('an already-correct end state is still a no-op (no write, no read-back)', async () => {
    mockVerify.mockResolvedValue(true)
    mockRedisGet.mockResolvedValueOnce('active')
    expect(await toggleKillSwitch('activate')).toEqual({ success: true })
    expect(mockRedisSet).not.toHaveBeenCalled()
    expect(mockRedisGet).toHaveBeenCalledTimes(1)
  })
})

/**
 * THE POSTURE GATE — the read-back's blind spot, on the highest-stakes surface.
 *
 * `lib/redis.ts` hands out an in-process object when no store is configured, so
 * `set` then `get` returns exactly what was just written: the read-back above
 * PASSES having contacted nothing, and the header pill and the world lever both
 * report a halt over a fleet that is still running. `unconfigured` carries no
 * production exclusion, so this is reachable on a real deploy that forgot
 * REDIS_URL — it is not a dev-only shape.
 *
 * Every arm here FAILS against the pre-gate action, which returned
 * `{ success: true }` in this posture. The last one is the inverse: a live store
 * must still be able to halt the fleet and say so.
 */
describe('toggleKillSwitch — a dashboard with no cabinet may not report a halt', () => {
  const withPosture = async (isMock: boolean, posture: string) => {
    // mockReset, not clearAllMocks: `mockResolvedValueOnce` queues survive a
    // clear, so an arm that refuses BEFORE consuming its queued value leaves it
    // in front of the next arm. That is how the inverse arm below first read
    // 'active' from an earlier test and "passed" the wrong branch.
    mockRedisGet.mockReset()
    mockRedisSet.mockReset()
    mockRedisDel.mockReset()
    vi.resetModules()
    vi.doMock('next/cache', () => ({ revalidatePath: vi.fn() }))
    vi.doMock('@/lib/auth', () => ({ verifySession: async () => true }))
    vi.doMock('@/lib/redis', () => ({
      default: { get: mockRedisGet, set: mockRedisSet, del: mockRedisDel },
      isMockRedis: isMock,
      storeReading: {
        posture,
        source: isMock
          ? 'no store is configured (REDIS_URL unset)'
          : 'the configured store',
        fabricated: posture === 'demo',
      },
    }))
    return import('./killswitch')
  }

  it('unconfigured → refuses, and the fleet key is never touched', async () => {
    const { toggleKillSwitch: toggle } = await withPosture(true, 'unconfigured')
    const res = await toggle('activate')
    expect(res.success).toBe(false)
    expect(res.error).toMatch(/not connected to a cabinet/)
    expect(res.error).toMatch(/fleet was not halted/)
    // Before the pre-read, not after: an empty store answers `null`, which the
    // action would otherwise read as "not engaged" and act on.
    expect(mockRedisGet).not.toHaveBeenCalled()
    expect(mockRedisSet).not.toHaveBeenCalled()
    expect(mockRedisDel).not.toHaveBeenCalled()
  })

  it('demo → refuses too; a seeded store is not a fleet either', async () => {
    const { toggleKillSwitch: toggle } = await withPosture(true, 'demo')
    const res = await toggle('deactivate')
    expect(res.success).toBe(false)
    expect(mockRedisSet).not.toHaveBeenCalled()
    expect(mockRedisDel).not.toHaveBeenCalled()
  })

  it('the intent-pinned no-op cannot slip past the gate either', async () => {
    // `intent === 'activate'` with the key already 'active' returns early with
    // `{ success: true }` BEFORE any write. Gating only the write path would
    // have left this one shape reporting a halt from an empty store.
    const { toggleKillSwitch: toggle } = await withPosture(true, 'unconfigured')
    mockRedisGet.mockResolvedValueOnce('active')
    expect((await toggle('activate')).success).toBe(false)
  })

  it('the inverse: a live store still halts the fleet and reports success', async () => {
    const { toggleKillSwitch: toggle } = await withPosture(false, 'live')
    mockRedisGet.mockResolvedValueOnce(null).mockResolvedValueOnce('active')
    expect(await toggle('activate')).toEqual({ success: true })
    expect(mockRedisSet).toHaveBeenCalledWith('cabinet:killswitch', 'active')
  })
})
