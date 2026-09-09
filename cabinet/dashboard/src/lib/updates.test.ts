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

  // BOTH PHASES, and `refused` is the half that matters. `state.json.phase`
  // is written only by the updater and nothing moves it out of `refused`
  // except a later apply — so `refused` is the phase this screen sits in for
  // every bundle that arrives after a constitutional refusal. Written with
  // `applied` alone (round 1) these two arms were VACUOUS: they passed over a
  // card that showed the OLD refusal over EVERY future bundle and withdrew
  // Apply with it, bricking the only no-terminal door until someone ran the
  // CLI. A refusal is scoped to the sha it is about, whatever the phase says.
  for (const phase of ['applied', 'refused']) {
    it(`a refusal of some OTHER bundle never silences the one that is waiting (phase: ${phase})`, () => {
      const line = updateHeadline({
        ...BASE, phase, latest: WAITING,
        last_refusal: { ...LOCKED_REFUSAL, bundle: 'e'.repeat(40) },
        last: { phase, to_sha: 'c'.repeat(40), changed: 3 },
      })
      expect(line).toBe('Update ready — 12 files changed (bbbbbbbb)')
    })

    it(`busy is about timing, not about the bundle, so it does not stick to it (phase: ${phase})`, () => {
      const line = updateHeadline({
        ...BASE, phase, latest: WAITING,
        last_refusal: { ...LOCKED_REFUSAL, reason: 'busy', paths: [] },
        last: { phase, to_sha: 'c'.repeat(40), changed: 3 },
      })
      expect(line).toBe('Update ready — 12 files changed (bbbbbbbb)')
    })
  }

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

  // The degenerate end of the sha scope. Nothing is waiting, so there is no
  // other sentence to be wrong about: the last thing that happened is still
  // the last thing that happened, and silence there would lose the only
  // record the Captain has of a refusal that named files.
  it('still speaks when nothing at all is waiting', () => {
    expect(refusalToShow({ ...BASE, phase: 'refused', latest: null,
                           last_refusal: LOCKED_REFUSAL })).toEqual(LOCKED_REFUSAL)
  })

  // The blocking defect of round 1, stated as the property rather than as the
  // sentence: a stale refusal must not follow bytes it has never seen.
  it('is null for a bundle it is not about, even while the phase still says refused', () => {
    expect(refusalToShow({
      ...BASE, phase: 'refused', latest: WAITING,
      last_refusal: { ...LOCKED_REFUSAL, bundle: 'f'.repeat(40) },
    })).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// SURFACE PARITY — the same state file, both readers, one fixture set on disk.
//
// `framework/frontdoor/tests/update_surface_parity.json` is the contract: the
// states this card and the briefing line must agree about. The briefing's half
// of it is `test_card_update_notice.py::test_the_briefing_says_what_the_card_
// says_on_every_shared_state`, reading the SAME file.
//
// WHY A SHARED FILE. Both sides carried the comment "two surfaces reading one
// state file must not be able to disagree" while the third of the three rules
// was written here only: `refusalToShow` opens with `applying -> null` and
// `_update_refusal_line` had no applying guard, so through every retry of a
// digest-mismatch refusal — the retry this card is deliberately designed for,
// because it keeps Apply for exactly those — this card said "Taking an update"
// and the briefing said "Update refused". Two independently-authored fixture
// sets cannot catch that: each side proves only itself.
//
// The wording differs on purpose, so what is asserted is the KIND each
// sentence classifies to, that no sentence names a bundle other than the one
// the case is about, and any wording the two genuinely share. The classifier
// is total: an unrecognised sentence is `unclassified` and fails naming
// itself, never a silent pass. A missing fixture file FAILS — parity that
// cannot be verified is drift, not a skip.
// ---------------------------------------------------------------------------
import fs from 'node:fs'
import path from 'node:path'

// <root>/cabinet/dashboard/src/lib → four levels up = <root>
const PARITY_FIXTURES = path.resolve(
  __dirname, '..', '..', '..', '..',
  'framework', 'frontdoor', 'tests', 'update_surface_parity.json'
)
const SHA_TOKEN = /\b[0-9a-f]{8}\b/g

type ParityCase = {
  name: string
  installed: string
  waiting: { sha: string; file_count: number; built_at: string } | null
  state: Record<string, unknown> | null
  agree: { kind: string; bundle: string; shared_wording: string[] }
}

function classify(line: string | null): string {
  if (!line) return 'silent'
  if (line.startsWith('Taking an update')) return 'apply-in-flight'
  if (line.startsWith('Update refused')) return 'refusal'
  if (line.startsWith('Update ready')) return 'ready'
  if (line.startsWith('Updated to ')) return 'applied'
  if (line.startsWith('An update was rolled back')) return 'rolled-back'
  return 'unclassified'
}

/** The fixture as `cabinet-update.sh status --json` would report it — the
 *  same derivation, field for field, so this is the state file and not a
 *  hand-shaped object that agrees with the card by construction. */
function statusOf(c: ParityCase): UpdateStatus {
  const state = (c.state || {}) as Record<string, never>
  const latest = c.waiting
    ? {
        sha: c.waiting.sha, short: c.waiting.sha.slice(0, 8),
        built_at: c.waiting.built_at, from_sha: null,
        file_count: c.waiting.file_count, changelog: [],
        owner: 'someone', mtime: c.waiting.built_at,
      }
    : null
  return {
    installed_sha: c.installed,
    installed_short: c.installed.slice(0, 8),
    phase: (state.phase as string) || 'idle',
    last: c.state ? (c.state as never) : null,
    available: latest ? [latest] : [],
    latest,
    snapshots: [],
    last_refusal: (state.last_refusal as never) ?? null,
    event_fallback: Boolean(state.event_fallback),
    ledger_error: (state.ledger_error as string) || '',
  } as UpdateStatus
}

describe('surface parity with the briefing line', () => {
  const doc = JSON.parse(fs.readFileSync(PARITY_FIXTURES, 'utf-8'))
  const cases = doc.cases as ParityCase[]

  it('the fixture set carries every state the two surfaces argue about', () => {
    const kinds = cases.map((c) => c.agree.kind)
    expect(kinds.length).toBe(6)
    expect(kinds.filter((k) => k === 'apply-in-flight').length).toBe(1)
    expect(kinds.filter((k) => k === 'refusal').length).toBe(1)
    expect(kinds.filter((k) => k === 'ready').length).toBe(3)
    expect(kinds.filter((k) => k === 'applied').length).toBe(1)
  })

  for (const c of cases) {
    it(`says what the briefing says: ${c.name}`, () => {
      const status = statusOf(c)
      const line = updateHeadline(status)
      expect([c.name, classify(line), line]).toEqual([c.name, c.agree.kind, line])
      for (const token of line?.match(SHA_TOKEN) ?? []) {
        expect([c.name, token]).toEqual([c.name, c.agree.bundle])
      }
      for (const wording of c.agree.shared_wording) {
        expect(line).toContain(wording)
      }
      // The half of the card that is not the headline: `refusalToShow` is what
      // withdraws Apply and names the files, and its twin on the briefing side
      // is the helper `_update_notice` asks first. Same states, same verdict.
      expect([c.name, refusalToShow(status) !== null])
        .toEqual([c.name, c.agree.kind === 'refusal'])
    })
  }
})
