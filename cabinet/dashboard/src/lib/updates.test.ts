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

describe('a ledger fault', () => {
  // A5.16. The card has room for both, so the fault is a sub-line beside the
  // headline (update-card.tsx) and does NOT outrank the news. The one thing it
  // must not be is invisible: the page renders this card only when the
  // headline is non-null, so a fault with nothing else going on reached no web
  // surface at all until 2026-09-09.
  it('never takes the headline from something that is happening', () => {
    for (const status of [
      { ...BASE, latest: WAITING, ledger_error: 'OSError: [Errno 28] No space left' },
      { ...BASE, phase: 'applying', last: { phase: 'applying', to_sha: 'b'.repeat(40) },
        ledger_error: 'OSError: [Errno 28] No space left' },
      { ...BASE, phase: 'applied', last: { phase: 'applied', to_sha: 'c'.repeat(40), changed: 2 },
        ledger_error: 'OSError: [Errno 28] No space left' },
    ]) {
      expect(updateHeadline(status as UpdateStatus))
        .not.toContain('Update records are not reaching the ledger')
    }
  })

  it('becomes the headline when nothing else has one, so it reaches a surface', () => {
    expect(updateHeadline({ ...BASE, ledger_error: 'OSError: [Errno 28] No space left' }))
      .toBe('Update records are not reaching the ledger')
    // and the inverse, so this is not a card that appears for no reason
    expect(updateHeadline(BASE)).toBeNull()
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

  // CURRENCY — the round-3 defect, on the branch round 1 left alone. Nothing
  // ever clears `last_refusal`; the updater carries it onto every later state
  // document on purpose (CARRIED_STATE_FIELDS), because a refusal is still
  // true after the next thing happens. What it stops being is the NEWS. Both
  // "nothing is waiting" arms above pin `phase: 'refused'`, so neither could
  // see a refusal that an apply or a rollback had already overtaken — and
  // once an install has refused anything, that is every applied and
  // rolled-back state it will ever be in.
  for (const [phase, what] of [
    ['applied', 'an apply'],
    ['rolled_back', 'a rollback'],
  ]) {
    it(`is null once ${what} has overtaken it and nothing is waiting`, () => {
      expect(refusalToShow({
        ...BASE, phase, latest: null, last_refusal: LOCKED_REFUSAL,
        last: { phase, to_sha: 'c'.repeat(40), changed: 4 },
      })).toBeNull()
    })
  }

  it('the busy race ends in the applied sentence, not in its own refusal', () => {
    // Winner takes bbbb..., loser records `busy` about bbbb..., winner lands.
    // The install IS bbbb..., so `status --json` excludes it and nothing is
    // waiting. Master said "Updated to bbbbbbbb: 4 changes" here.
    const status: UpdateStatus = {
      ...BASE, phase: 'applied', latest: null,
      last_refusal: { ...LOCKED_REFUSAL, reason: 'busy', paths: [] },
      last: { phase: 'applied', to_sha: 'b'.repeat(40), changed: 4,
              last_refusal: { ...LOCKED_REFUSAL, reason: 'busy', paths: [] } },
    }
    expect(refusalToShow(status)).toBeNull()
    expect(updateHeadline(status)).toBe('Updated to bbbbbbbb: 4 changes')
  })

  it('a constitutional refusal overtaken by a later apply stops withdrawing Apply', () => {
    // The ceremony flow: locked refusal on bbbb..., the Captain unlocks and
    // relocks, a NEW bundle applies. "Nothing was applied" over an install
    // that HAS been updated, with Apply withdrawn, for ever.
    const status: UpdateStatus = {
      ...BASE, phase: 'applied', latest: null, last_refusal: LOCKED_REFUSAL,
      last: { phase: 'applied', to_sha: 'c'.repeat(40), changed: 9 },
    }
    expect(refusalToShow(status)).toBeNull()
    expect(updateHeadline(status)).toBe('Updated to cccccccc: 9 changes')
  })

  it('a rollback since the refusal gives the rollback sentence back', () => {
    const status: UpdateStatus = {
      ...BASE, phase: 'rolled_back', latest: null, last_refusal: LOCKED_REFUSAL,
      last: { phase: 'rolled_back', to_sha: 'c'.repeat(40),
              reason: 'the health gate was red' },
    }
    expect(refusalToShow(status)).toBeNull()
    expect(updateHeadline(status)).toBe(
      'An update was rolled back to cccccccc: the health gate was red')
  })

  // The half the currency check must NOT narrow: a later apply of some OTHER
  // bundle does not make the refused one safe to offer. It is still in the
  // inbox and still refused, and the sha scope decides there, not the phase.
  it('still speaks for a refused bundle that is STILL waiting after another apply', () => {
    const status: UpdateStatus = {
      ...BASE, phase: 'applied', latest: WAITING, last_refusal: LOCKED_REFUSAL,
      last: { phase: 'applied', to_sha: 'c'.repeat(40), changed: 9 },
    }
    expect(refusalToShow(status)).toEqual(LOCKED_REFUSAL)
    expect(updateHeadline(status)).toContain('Update refused')
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

/** The one classifier, in the oracle's vocabulary. TOTAL: a sentence it does
 *  not recognise is `unclassified` and fails naming itself. */
function classifyKind(line: string | null): string {
  if (!line) return 'quiet'
  if (line.startsWith('Taking an update')) return 'applying'
  if (line.startsWith('Update records are not reaching the ledger')) return 'fault'
  if (line.startsWith('Update refused')) return 'refused'
  if (line.startsWith('Update ready')) return 'ready'
  if (line.startsWith('Updated to ')) return 'applied'
  // Two rollback sentences share this vocabulary: the state file's ("An update
  // was rolled back: …") and the briefing's receipt-channel one ("An update to
  // <sha> was rolled back … and is still in the inbox"). The card produces only
  // the first; the classifier stays the twin of the briefing's so the two
  // suites cannot describe the same table in different words.
  if (line.startsWith('An update was rolled back') ||
      (line.startsWith('An update to ') && line.includes('was rolled back'))) {
    return 'rolled_back'
  }
  return 'unclassified'
}

/** The parity fixture predates the oracle and names its kinds its own way. */
const PARITY_KIND: Record<string, string> = {
  refused: 'refusal', applying: 'apply-in-flight',
  rolled_back: 'rolled-back', quiet: 'silent',
}

function classify(line: string | null): string {
  const kind = classifyKind(line)
  return PARITY_KIND[kind] ?? kind
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
    expect(kinds.length).toBe(7)
    expect(kinds.filter((k) => k === 'apply-in-flight').length).toBe(1)
    expect(kinds.filter((k) => k === 'refusal').length).toBe(1)
    expect(kinds.filter((k) => k === 'ready').length).toBe(3)
    // TWO applied cases: one with no refusal on record and one carrying the
    // refusal it overtook. The first cannot see the round-3 defect, because
    // `last_refusal` is the one field the carry rule guarantees will be there
    // on any install that has ever refused anything.
    expect(kinds.filter((k) => k === 'applied').length).toBe(2)
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

// ---------------------------------------------------------------------------
// A REFUSAL THE STATE FILE NEVER CARRIED — the round-4 must-fix, this side.
//
// A refusal is written down twice by one call, and either half can be the only
// one that survives. Round 4 measured a locked-path refusal that had reached
// only the LEDGER: the briefing said "REFUSED: it changes locked constitutional
// paths" and this card rendered Apply on the same bundle — the button that
// fails identically every tap, which is A5.15's own rationale.
//
// THIS CARD'S CODE IS NOT WHAT CHANGED, and saying so is the point. It reads
// `status.last_refusal` and always did; what it could not see was a refusal
// that never reached that field. The fix is in its INPUT — `cabinet-update.sh
// status --json` now resolves both channels into that one field and tags it —
// so these two arms are declared guards, green in both directions: they pin
// that a receipt-sourced record is treated exactly like a state-sourced one,
// which is what makes the resolution safe to do upstream. The arms that are
// RED without the fix are on the resolver itself
// (`test_cabinet_update.py::test_a_refusal_that_reached_only_the_ledger_...`)
// and on the briefing.
// ---------------------------------------------------------------------------

describe('a refusal resolved from the ledger receipt', () => {
  const refused = 'b'.repeat(40)
  const waiting = {
    sha: refused, short: refused.slice(0, 8), built_at: '2026-09-07T00:00:00Z',
    from_sha: null, file_count: 7, changelog: [], owner: 'someone',
    mtime: '2026-09-07T00:00:00Z',
  }

  it('withdraws Apply exactly as one the state file carried would', () => {
    const status: UpdateStatus = {
      ...BASE, available: [waiting], latest: waiting,
      last_refusal: {
        bundle: refused, reason: 'bundle changes locked constitutional paths',
        paths: ['cabinet/scripts/start-officer-mac.sh'], ts: '', door: 'web',
      },
      last_refusal_source: 'receipt',
    }
    expect(refusalToShow(status)).not.toBeNull()
    expect(updateHeadline(status)).toBe(
      'Update refused — 1 constitutional file differs; needs the Captain (bbbbbbbb)'
    )
  })

  it('is still filtered by rule 4 when the reason is only timing', () => {
    // The other half, and the round-1 defect arriving on the second channel:
    // `busy` says another updater held the lock, never anything about these
    // bytes. Resolving a refusal from the ledger must not smuggle that back in.
    const status: UpdateStatus = {
      ...BASE, available: [waiting], latest: waiting,
      last_refusal: { bundle: refused, reason: 'busy', paths: [], ts: '', door: 'web' },
      last_refusal_source: 'receipt',
    }
    expect(refusalToShow(status)).toBeNull()
    expect(updateHeadline(status)).toBe('Update ready — 7 files changed (bbbbbbbb)')
  })
})

// ---------------------------------------------------------------------------
// THE WHOLE STATE SPACE — every state, not the ones somebody thought of.
//
// Three review rounds each found one more adjacent state in this reader and
// its twin, and every arm written for each of them was aimed at the state that
// already worked: round 1's two arms pinned `phase: 'applied'`, round 2's
// pinned a state with no waiting bundle, round 3's both pinned
// `phase: 'refused'`. That is not three unlucky arms, it is the shape of
// hand-written arms — the defect is always in the state nobody thought to
// write one for.
//
// `update_surface_oracle.json` is the whole product of the six axes these two
// readers branch on (1440 rows — the ledger became the sixth in round 4, which
// found the previous table complete over five and blind to the one a whole
// refusal channel lived on), with the expected headline kind for EACH
// surface and whether the refusal sub-surface speaks. It is derived from the
// contract (A5.13/A5.15/A5.16), not from either implementation: a row where
// the code disagrees is a defect in the code. The briefing's half of the same
// table is `test_card_update_notice.py::test_the_briefing_answers_every_state_
// the_way_the_oracle_says`, reading the SAME file — so a kind flipped in it
// reds both suites, and a fixture file that went missing FAILS rather than
// skips.
// ---------------------------------------------------------------------------

const ORACLE_FIXTURES = path.resolve(
  __dirname, '..', '..', '..', '..',
  'framework', 'frontdoor', 'tests', 'update_surface_oracle.json'
)

type OracleRow = {
  id: string
  axes: Record<string, string | boolean>
  installed: string
  waiting: { sha: string; file_count: number; built_at: string } | null
  state: Record<string, unknown> | null
  resolved: { last_refusal: Record<string, unknown> | null; source: string }
  expect: { briefing: string; card: string; refusal_speaks: boolean }
}

/** The row as `cabinet-update.sh status --json` reports it — the same
 *  derivation, field for field, so this is the state file and not an object
 *  shaped to agree with the card by construction.
 *
 *  `last_refusal` comes from the row's `resolved`, because that is where it
 *  comes from in production: the updater resolves the state file and the
 *  ledger receipt into ONE record and this card reads only the result. Round 4
 *  measured what the other arrangement costs — the briefing read a second
 *  channel this card could not see, so the two surfaces disagreed on every
 *  state where the state file had lost the record and the ledger had not. The
 *  briefing's own resolver is held to the same `resolved` by
 *  `test_the_briefing_resolves_the_refusal_the_table_says_it_must`, so the two
 *  halves are not driven from two different resolutions. */
function statusOfRow(row: OracleRow): UpdateStatus {
  const state = (row.state || {}) as Record<string, never>
  const latest = row.waiting
    ? {
        sha: row.waiting.sha, short: row.waiting.sha.slice(0, 8),
        built_at: row.waiting.built_at, from_sha: null,
        file_count: row.waiting.file_count, changelog: [],
        owner: 'someone', mtime: row.waiting.built_at,
      }
    : null
  return {
    installed_sha: row.installed,
    installed_short: row.installed.slice(0, 8),
    phase: (state.phase as string) || 'idle',
    last: row.state && Object.keys(row.state).length ? (row.state as never) : null,
    available: latest ? [latest] : [],
    latest,
    snapshots: [],
    last_refusal: (row.resolved.last_refusal as never) ?? null,
    last_refusal_source: row.resolved.source,
    event_fallback: Boolean(state.event_fallback),
    ledger_error: (state.ledger_error as string) || '',
  } as UpdateStatus
}

describe('the whole state space', () => {
  const doc = JSON.parse(fs.readFileSync(ORACLE_FIXTURES, 'utf-8'))
  const rows = doc.rows as OracleRow[]

  it('the oracle covers the whole product of the axes it declares', () => {
    // Derived from the declared axes rather than compared to a number, so it
    // detects a REMOVED row as well as a changed one. The sixth axis is the
    // LEDGER: round 4 found the table complete over the five it declared and
    // blind to the one it did not, which is a green hole rather than a
    // covered one.
    const axes = doc.axes as Record<string, (string | boolean)[]>
    const expected = new Set<string>()
    for (const phase of axes.phase)
      for (const waiting of axes.waiting)
        for (const refusal of axes.refusal)
          for (const ledger of axes.ledger_error)
            for (const fallback of axes.event_fallback)
              for (const receipt of axes.receipt)
                expected.add(
                  `${phase}/${waiting}/${refusal}/` +
                  `${ledger ? 'fault' : 'noledger'}/${fallback ? 'held' : 'nohold'}/` +
                  `${receipt}`
                )
    expect(expected.size).toBe(1440)
    expect(rows.map((r) => r.id).sort()).toEqual([...expected].sort())
    // A declared axis with no seeds behind it is an axis held constant under a
    // name — exactly what the ledger was until this round.
    expect(Object.keys(doc.receipt_seeds).sort()).toEqual([...axes.receipt].sort())
  })

  it('the card answers every state the way the oracle says', () => {
    const wrong: string[] = []
    for (const row of rows) {
      const status = statusOfRow(row)
      const line = updateHeadline(status)
      const kind = classifyKind(line)
      const spoke = refusalToShow(status) !== null
      if (kind !== row.expect.card || spoke !== row.expect.refusal_speaks) {
        wrong.push(
          `${row.id}: kind ${kind} (want ${row.expect.card}), ` +
          `refusal spoke ${spoke} (want ${row.expect.refusal_speaks}) -- ${line}`
        )
      }
    }
    // The count leads the sample: a sensor that shows twenty rows without
    // saying how many there are reads the same at 20 as at 1440.
    expect([`${wrong.length} of ${rows.length} wrong`, ...wrong.slice(0, 20)])
      .toEqual([`0 of ${rows.length} wrong`])
  })
})
