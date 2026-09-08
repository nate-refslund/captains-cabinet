/**
 * Guard coverage for the update actions — the one surface on this dashboard
 * that can replace the bytes of the running Cabinet.
 *
 * Three properties, each with a way it could quietly fail:
 *
 *  1. UNAUTHENTICATED ⇒ NOTHING SPAWNS. A server action is a global action-ID
 *     POST endpoint; middleware gates page navigation and never covers it.
 *  2. THE NO-AUTH POSTURE DOES NOT OPEN THIS (A5.9). Every other mutating
 *     action guards with `requireDashboardAuth()`, which returns TRUE under
 *     `DASHBOARD_NO_AUTH=true`. Reading a page that way is a trade; replacing
 *     the tree that way is not. These arms would pass against the ordinary
 *     guard, so they are pinned on `verifySession` being called directly.
 *  3. A BAD ID NEVER REACHES A PROCESS. The seam takes an argv array, so a
 *     shell string is never composed — the regex is the second line of defence
 *     and this is what proves it fires first.
 *
 * The store-posture arm at the bottom is A5.12: these actions must NOT route
 * through the store-gated exec helper, because an installed single-worker
 * Cabinet — the deployment this whole leg exists for — normally has no store,
 * and that helper REJECTS there.
 */
import { readFileSync } from 'fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { mockVerify, mockSpawn, mockRequireDashboardAuth } = vi.hoisted(() => ({
  mockVerify: vi.fn<() => Promise<boolean>>(),
  mockSpawn: vi.fn<(args: string[]) => void>(),
  mockRequireDashboardAuth: vi.fn<() => Promise<boolean>>(),
}))

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ verifySession: mockVerify }))
vi.mock('@/lib/provisioning/guard', () => ({
  requireDashboardAuth: mockRequireDashboardAuth,
}))
vi.mock('@/lib/updates', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/updates')>()
  return { ...actual, spawnUpdater: mockSpawn }
})

import { applyUpdate, rollbackUpdate } from './updates'

const GOOD_SHA = 'a'.repeat(40)

beforeEach(() => {
  vi.clearAllMocks()
  mockRequireDashboardAuth.mockResolvedValue(true)
  vi.stubEnv('NODE_ENV', 'test')
})

afterEach(() => vi.unstubAllEnvs())

describe('applyUpdate', () => {
  it('unauthenticated → refused, and no updater is ever launched', async () => {
    mockVerify.mockResolvedValue(false)
    expect(await applyUpdate(GOOD_SHA)).toEqual({ ok: false, error: 'unauthorized' })
    expect(mockSpawn).not.toHaveBeenCalled()
  })

  it('authenticated → launches the updater with a fixed argv and the web door', async () => {
    mockVerify.mockResolvedValue(true)
    expect(await applyUpdate(GOOD_SHA)).toEqual({ ok: true })
    expect(mockSpawn).toHaveBeenCalledWith(['apply', '--bundle', GOOD_SHA, '--from', 'web'])
  })

  it.each([
    ['a shell fragment', `${GOOD_SHA}; rm -rf /`],
    ['a path traversal', '../../etc/passwd'],
    ['too short', 'abc'],
    ['not hex', 'z'.repeat(40)],
    ['empty', ''],
  ])('a bad bundle id (%s) → refused before anything runs', async (_name, sha) => {
    mockVerify.mockResolvedValue(true)
    expect(await applyUpdate(sha)).toEqual({ ok: false, error: 'invalid bundle id' })
    expect(mockSpawn).not.toHaveBeenCalled()
  })

  it('the no-auth posture does NOT open apply (A5.9)', async () => {
    // The posture that waives the ordinary guard everywhere else.
    vi.stubEnv('DASHBOARD_NO_AUTH', 'true')
    mockRequireDashboardAuth.mockResolvedValue(true)
    mockVerify.mockResolvedValue(false)
    expect(await applyUpdate(GOOD_SHA)).toEqual({ ok: false, error: 'unauthorized' })
    expect(mockSpawn).not.toHaveBeenCalled()
    // And the waiver was never even consulted: this action does not use it.
    expect(mockRequireDashboardAuth).not.toHaveBeenCalled()
  })
})

describe('rollbackUpdate', () => {
  it('unauthenticated → refused, nothing launched', async () => {
    mockVerify.mockResolvedValue(false)
    expect(await rollbackUpdate()).toEqual({ ok: false, error: 'unauthorized' })
    expect(mockSpawn).not.toHaveBeenCalled()
  })

  it('authenticated with no stamp → rolls back the newest snapshot', async () => {
    mockVerify.mockResolvedValue(true)
    expect(await rollbackUpdate()).toEqual({ ok: true })
    expect(mockSpawn).toHaveBeenCalledWith(['rollback', '--from', 'web'])
  })

  it('a bad snapshot stamp → refused before anything runs', async () => {
    mockVerify.mockResolvedValue(true)
    expect(await rollbackUpdate('../../..')).toEqual({
      ok: false,
      error: 'invalid snapshot stamp',
    })
    expect(mockSpawn).not.toHaveBeenCalled()
  })

  it('the no-auth posture does NOT open rollback (A5.9)', async () => {
    vi.stubEnv('DASHBOARD_NO_AUTH', 'true')
    mockVerify.mockResolvedValue(false)
    expect(await rollbackUpdate()).toEqual({ ok: false, error: 'unauthorized' })
    expect(mockSpawn).not.toHaveBeenCalled()
  })
})

describe('the exec seam (A5.12)', () => {
  it('a store that is not live does not close the update door', async () => {
    // The installed single-worker Cabinet's normal state: no store configured.
    vi.stubEnv('REDIS_URL', '')
    vi.stubEnv('MOCK_DATA', '')
    vi.stubEnv('NODE_ENV', 'production')
    mockVerify.mockResolvedValue(true)
    expect(await applyUpdate(GOOD_SHA)).toEqual({ ok: true })
    expect(mockSpawn).toHaveBeenCalledTimes(1)
  })

  it('neither module reaches for the store-gated exec helper', () => {
    // Structural, and deliberately so: the arm above passes for as long as the
    // import is absent, and the moment someone adds it the behaviour changes
    // only in a posture the unit tests do not run in. This is the line that
    // fails the second the import appears.
    for (const rel of ['src/lib/updates.ts', 'src/actions/updates.ts']) {
      const source = readFileSync(new URL(`../../${rel}`, import.meta.url), 'utf-8')
      // A CALL, not the word: lib/updates.ts names the helper in the comment
      // that explains why it does not use it, and that sentence is the reason
      // a later reader will not re-add the import.
      expect(source).not.toMatch(/dockerExec\s*\(/)
      expect(source).not.toMatch(/from '@\/lib\/docker'/)
    }
  })
})
