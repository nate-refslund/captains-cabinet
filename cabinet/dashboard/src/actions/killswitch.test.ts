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
