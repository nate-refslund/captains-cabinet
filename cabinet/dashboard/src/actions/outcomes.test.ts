/**
 * THE WEB DOOR of the tap.
 *
 * Two properties, and the second one is the reason this file exists rather
 * than being folded into the cross-module auth sweep:
 *
 *  1. an unauthenticated caller gets `{ok:false}` and NOTHING is executed — a
 *     Server Action is a global POST endpoint and middleware never covers
 *     action dispatch;
 *  2. a NOT-LIVE store does not stop the tap. `dockerExec` throws whenever the
 *     store is unconfigured, and an installed Cabinet with no REDIS_URL is
 *     that deployment's normal state — routing this action through it would
 *     have made the one control the no-terminal law exists for throw before it
 *     ran. So the action must not import that transport at all, and the arm
 *     below drives the real module with the not-live posture pinned.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import nodePath from 'node:path'

const { mockVerify, mockLocalExec, mockDockerExec } = vi.hoisted(() => ({
  mockVerify: vi.fn<() => Promise<boolean>>(),
  mockLocalExec: vi.fn(),
  mockDockerExec: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ verifySession: mockVerify }))
vi.mock('@/lib/local-exec', () => ({
  localExec: mockLocalExec,
  CABINET_PYTHON: 'python3.12',
}))
// Mocked so the arm can PROVE it was never reached, not merely that it did
// not throw.
vi.mock('@/lib/docker', () => ({
  dockerExec: mockDockerExec,
  assertRuntimeWritesAllowed: vi.fn(),
}))

import { ratifyOutcome } from './outcomes'

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubEnv('MOCK_DATA', '')
  vi.stubEnv('NODE_ENV', 'test')
  mockLocalExec.mockResolvedValue({
    stdout: JSON.stringify({ status: 'ratified', outcome_id: 'acme-001' }),
    stderr: '',
  })
})

afterEach(() => vi.unstubAllEnvs())

describe('ratifyOutcome refuses the unauthenticated caller', () => {
  beforeEach(() => mockVerify.mockResolvedValue(false))

  it('returns {ok:false} and executes nothing', async () => {
    expect(await ratifyOutcome('acme-001')).toEqual({ ok: false, error: 'unauthorized' })
    expect(mockLocalExec).not.toHaveBeenCalled()
    expect(mockDockerExec).not.toHaveBeenCalled()
  })
})

describe('ratifyOutcome, authenticated', () => {
  beforeEach(() => mockVerify.mockResolvedValue(true))

  it('calls the one writer through the web door and reports its status', async () => {
    const res = await ratifyOutcome('acme-001')
    expect(res).toEqual({ ok: true, status: 'ratified', outcomeId: 'acme-001' })
    const argv = mockLocalExec.mock.calls[0][0] as string[]
    expect(argv).toContain('framework.outcomes.ratify')
    expect(argv).toContain('--door')
    expect(argv[argv.indexOf('--door') + 1]).toBe('web')
    expect(argv[argv.indexOf('--principal') + 1]).toBeTruthy()
    expect(mockDockerExec).not.toHaveBeenCalled()
  })

  it.each([
    ['../../etc/passwd'],
    ['acme 001'],
    ['acme-001; rm -rf /'],
    [''],
    ['a'.repeat(65)],
  ])('refuses the id %s without executing anything', async (id) => {
    expect(await ratifyOutcome(id)).toEqual({ ok: false, error: 'invalid outcome id' })
    expect(mockLocalExec).not.toHaveBeenCalled()
  })

  it('reports the writer refusal rather than claiming success', async () => {
    mockLocalExec.mockResolvedValue({
      stdout: JSON.stringify({ status: 'not_found', reason: 'no proposed card' }),
      stderr: '',
    })
    const res = await ratifyOutcome('acme-001')
    expect(res.ok).toBe(false)
    expect(res.status).toBe('not_found')
    expect(res.error).toContain('no proposed card')
  })

  it('reports a non-zero exit rather than claiming success', async () => {
    mockLocalExec.mockRejectedValue(new Error('Command failed: exit 4'))
    const res = await ratifyOutcome('acme-001')
    expect(res.ok).toBe(false)
    expect(res.error).toContain('exit 4')
  })
})

describe('A1.5 — a not-live store must not stop the tap', () => {
  it('does not import the store-posture-gated transport at all', () => {
    const source = readFileSync(
      nodePath.join(__dirname, 'outcomes.ts'),
      'utf8'
    )
    // The IMPORT, not the word: the module explains in prose why it avoids
    // that transport, and a grep for the name would grade the explanation.
    expect(source).not.toMatch(/^\s*import[^\n]*['"]@\/lib\/docker['"]/m)
    expect(source).toMatch(/^\s*import[^\n]*['"]@\/lib\/local-exec['"]/m)
  })

  it('succeeds with REDIS_URL unset on a production build', async () => {
    vi.resetModules()
    vi.stubEnv('NODE_ENV', 'production')
    vi.stubEnv('REDIS_URL', '')
    vi.stubEnv('MOCK_DATA', '')
    mockVerify.mockResolvedValue(true)
    mockLocalExec.mockResolvedValue({
      stdout: JSON.stringify({ status: 'ratified', outcome_id: 'acme-001' }),
      stderr: '',
    })
    const { ratifyOutcome: fresh } = await import('./outcomes')
    const res = await fresh('acme-001')
    expect(res.ok).toBe(true)
    expect(mockDockerExec).not.toHaveBeenCalled()
  })
})

describe('the id pattern', () => {
  beforeEach(() => mockVerify.mockResolvedValue(true))
  it.each([['acme-001'], ['a'], ['a.b_c-1'], ['a'.repeat(64)]])(
    'accepts %s',
    async (id) => {
      expect((await ratifyOutcome(id)).ok).toBe(true)
    }
  )
})
