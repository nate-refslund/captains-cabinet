/**
 * lib/updates.ts — the read side.
 *
 * The one property worth a test here is what the card says when it could NOT
 * ask. A status reader that returned an empty "nothing waiting" object on a
 * box with no updater would render "you are up to date" over a Cabinet that
 * has no idea whether it is — the degenerate answer, dressed as a measurement.
 * So: `null` on every failure, and `updateHeadline(null) === null`, which the
 * page turns into an absent card rather than a reassuring one.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { mockExecFile } = vi.hoisted(() => ({ mockExecFile: vi.fn() }))

vi.mock('child_process', () => ({
  execFile: mockExecFile,
  spawn: vi.fn(() => ({ unref: vi.fn() })),
}))

import { getUpdateStatus, updateHeadline, type UpdateStatus } from './updates'

/** promisify(execFile) calls the callback form: (cmd, args, opts, cb). */
function answer(stdout: string) {
  mockExecFile.mockImplementation((_cmd: string, _args: string[], _opts: unknown, cb: Function) =>
    cb(null, { stdout, stderr: '' })
  )
}

function fail(err: Error) {
  mockExecFile.mockImplementation((_cmd: string, _args: string[], _opts: unknown, cb: Function) =>
    cb(err)
  )
}

const BASE: UpdateStatus = {
  installed_sha: 'a'.repeat(40),
  installed_short: 'aaaaaaaa',
  phase: 'idle',
  last: null,
  available: [],
  latest: null,
  snapshots: [],
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.unstubAllEnvs())

describe('getUpdateStatus', () => {
  it('reads the updater CLI as JSON', async () => {
    answer(JSON.stringify(BASE))
    const status = await getUpdateStatus()
    expect(status?.installed_sha).toBe('a'.repeat(40))
    expect(mockExecFile).toHaveBeenCalledWith(
      'bash',
      ['cabinet/scripts/cabinet-update.sh', 'status', '--json'],
      expect.anything(),
      expect.anything()
    )
  })

  it('no updater on this box → null, never an empty "nothing waiting"', async () => {
    fail(Object.assign(new Error('No such file or directory'), { code: 'ENOENT' }))
    expect(await getUpdateStatus()).toBeNull()
  })

  it('unparseable output → null', async () => {
    answer('not json at all')
    expect(await getUpdateStatus()).toBeNull()
  })

  it('a JSON payload of the wrong shape → null', async () => {
    answer('[1,2,3]')
    expect(await getUpdateStatus()).toBeNull()
  })
})

describe('updateHeadline', () => {
  it('null status → no line at all', () => {
    expect(updateHeadline(null)).toBeNull()
  })

  it('nothing waiting and nothing applied → no line', () => {
    expect(updateHeadline(BASE)).toBeNull()
  })

  it('a waiting bundle leads, because it is the only one he can act on', () => {
    const line = updateHeadline({
      ...BASE,
      latest: {
        sha: 'b'.repeat(40), short: 'bbbbbbbb', built_at: '2026-09-07T00:00:00Z',
        from_sha: null, file_count: 12, changelog: ['x'], owner: 'nate',
        mtime: '2026-09-07T00:00:00Z',
      },
    })
    expect(line).toBe('Update ready — 12 files changed (bbbbbbbb)')
  })

  it('after an apply → "Updated to <sha>: N changes" (A5.13)', () => {
    expect(
      updateHeadline({
        ...BASE, phase: 'applied',
        last: { phase: 'applied', to_sha: 'c'.repeat(40), changed: 1 },
      })
    ).toBe('Updated to cccccccc: 1 change')
  })

  it('a rollback says so, with the reason', () => {
    expect(
      updateHeadline({
        ...BASE, phase: 'rolled_back',
        last: { phase: 'rolled_back', to_sha: 'a'.repeat(40), reason: 'the health gate was red' },
      })
    ).toBe('An update was rolled back to aaaaaaaa: the health gate was red')
  })
})
