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

  it('authenticated → proceeds to flip the switch', async () => {
    mockVerify.mockResolvedValue(true)
    mockRedisGet.mockResolvedValue(null) // currently inactive
    const res = await toggleKillSwitch('activate')
    expect(res).toEqual({ success: true })
    expect(mockRedisSet).toHaveBeenCalledWith('cabinet:killswitch', 'active')
  })
})
