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

import { getUpdateStatus, refusalToShow, updateHeadline, type UpdateStatus } from './updates'

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

// ---------------------------------------------------------------------------
// A5.15 — a refusal reaches the screen, and the same bundle never reads as
// "ready" again.
//
// Measured on the installed Cabinet 2026-09-08: an apply refused because one
// constitutional path differed, wrote no state at all, and `status --json`
// answered `phase: idle, last: null`. This card would then have offered
// "Update ready" for that same bundle for ever — a button that cannot work,
// with nothing anywhere saying why.
// ---------------------------------------------------------------------------

const WAITING = {
  sha: 'b'.repeat(40), short: 'bbbbbbbb', built_at: '2026-09-07T00:00:00Z',
  from_sha: null, file_count: 12, changelog: ['x'], owner: 'nate',
  mtime: '2026-09-07T00:00:00Z',
}

const LOCKED_REFUSAL = {
  bundle: 'b'.repeat(40),
  reason: 'bundle changes locked constitutional paths',
  paths: ['cabinet/scripts/start-officer-mac.sh'],
  ts: '2026-09-08T18:58:00Z',
  door: 'terminal',
}

describe('a refused bundle', () => {
  it('says it was refused, names how many files, and never says "ready"', () => {
    const line = updateHeadline({
      ...BASE, phase: 'refused', latest: WAITING, last_refusal: LOCKED_REFUSAL,
    })
    expect(line).toContain('Update refused')
    expect(line).toContain('1 constitutional file')
    expect(line).not.toContain('Update ready')
  })

  it('counts more than one path in the plural', () => {
    const line = updateHeadline({
      ...BASE, phase: 'refused', latest: WAITING,
      last_refusal: { ...LOCKED_REFUSAL, paths: ['a.sh', 'b.sh', 'c.sh'] },
    })
    expect(line).toContain('3 constitutional files differ')
  })

  it('a refusal with no paths says its own reason instead of inventing a count', () => {
    const line = updateHeadline({
      ...BASE, phase: 'refused', latest: WAITING,
      last_refusal: { ...LOCKED_REFUSAL, paths: [], reason: 'failed per-file digest verification' },
    })
    expect(line).toContain('Update refused')
    expect(line).toContain('digest')
    expect(line).not.toContain('constitutional')
  })

  it('stays refused for that bundle even after some other apply moved the phase', () => {
    const line = updateHeadline({
      ...BASE, phase: 'applied', latest: WAITING, last_refusal: LOCKED_REFUSAL,
      last: { phase: 'applied', to_sha: 'c'.repeat(40), changed: 3 },
    })
    expect(line).toContain('Update refused')
  })

  it('a refusal of some OTHER bundle never silences the one that is waiting', () => {
    const line = updateHeadline({
      ...BASE, phase: 'applied', latest: WAITING,
      last_refusal: { ...LOCKED_REFUSAL, bundle: 'e'.repeat(40) },
      last: { phase: 'applied', to_sha: 'c'.repeat(40), changed: 3 },
    })
    expect(line).toBe('Update ready — 12 files changed (bbbbbbbb)')
  })

  it('busy is about timing, not about the bundle, so it does not stick to it', () => {
    const line = updateHeadline({
      ...BASE, phase: 'applied', latest: WAITING,
      last_refusal: { ...LOCKED_REFUSAL, reason: 'busy', paths: [] },
      last: { phase: 'applied', to_sha: 'c'.repeat(40), changed: 3 },
    })
    expect(line).toBe('Update ready — 12 files changed (bbbbbbbb)')
  })

  it('an apply in flight still leads — it is the live state', () => {
    const line = updateHeadline({
      ...BASE, phase: 'applying', latest: WAITING,
      last_refusal: { ...LOCKED_REFUSAL, reason: 'busy', paths: [] },
      last: { phase: 'applying', to_sha: 'b'.repeat(40) },
    })
    expect(line).toContain('Taking an update')
  })
})

describe('refusalToShow', () => {
  it('is null when nothing was refused', () => {
    expect(refusalToShow(BASE)).toBeNull()
    expect(refusalToShow(null)).toBeNull()
  })

  it('is the refusal the headline is speaking about, so the card cannot disagree', () => {
    const status = { ...BASE, phase: 'refused', latest: WAITING, last_refusal: LOCKED_REFUSAL }
    expect(refusalToShow(status)).toEqual(LOCKED_REFUSAL)
    expect(updateHeadline(status)).toContain('Update refused')
  })

  it('is null while an apply is in flight', () => {
    expect(refusalToShow({ ...BASE, phase: 'applying', last_refusal: LOCKED_REFUSAL })).toBeNull()
  })
})
