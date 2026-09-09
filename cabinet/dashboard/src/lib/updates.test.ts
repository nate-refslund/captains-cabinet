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

import { applyTarget, getUpdateStatus, refusalToShow, updateHeadline, type UpdateStatus } from './updates'

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

  // WHERE THE SCOPING WENT, and why these arms changed shape in round 6.
  //
  // Until A5.17 this card decided for itself whether a refusal was about the
  // bundle it was offering — the sha test and the `busy` filter lived here and
  // in the briefing, twice. Round 5 measured what two copies of a rule cost
  // when the record reaching them is already wrong: the resolver handed BOTH
  // surfaces the newest refusal receipt in the window regardless of which
  // bundle it named, so a `busy` note about no bundle at all blanked a
  // constitutional verdict on the bytes in the inbox and both surfaces agreed
  // on "Update ready".
  //
  // So the scoping is done ONCE, upstream, about the WAITING bundle, and both
  // surfaces consume only its answer (A5.17.6). What these arms pin now is the
  // half that is this card's: given the answer, it says the right thing and
  // does not invent a second opinion. The scoping itself is pinned on 5250
  // states in `the whole state space` below and, on the resolver that produces
  // the answer, in `cabinet/scripts/tests/test_cabinet_update.py`.
  for (const phase of ['applied', 'refused']) {
    it(`a refusal of some OTHER bundle never reaches this card (phase: ${phase})`, () => {
      // The resolver answers about the WAITING bundle: with the record on file
      // naming another sha, `current(W)` is empty and the report carries null.
      // Oracle rows `${phase}/same/legacy-verdict/…` with `waiting: other` are
      // the same statement over the whole product.
      const line = updateHeadline({
        ...BASE, phase, latest: WAITING, last_refusal: null,
        last_refusal_source: '',
        last: { phase, to_sha: 'c'.repeat(40), changed: 3 },
      })
      expect(line).toBe('Update ready — 12 files changed (bbbbbbbb)')
    })

    it(`a timing note is never resolved, so the card never sees one (phase: ${phase})`, () => {
      // A5.17.1: `busy` is about no bundle. It is not a candidate anywhere, it
      // never occupies the verdict store, and `last_busy` — which is where it
      // does land — is never a headline. Oracle rows `*/same/legacy-busy/*`.
      const line = updateHeadline({
        ...BASE, phase, latest: WAITING, last_refusal: null,
        last_busy: { bundle: 'b'.repeat(40), ts: '2026-09-09T10:00:30Z' },
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

  // WHAT THIS FUNCTION NO LONGER DOES, and where each rule went (A5.17.6).
  //
  // Rounds 1-3 wrote three rules here — the sha scope, the `busy` filter and
  // the currency check — and wrote them again in the briefing. Round 5 found
  // the record arriving at both copies already wrong, which no amount of
  // agreement between two readers can catch. All three are now properties of
  // the RESOLUTION: `status --json` reports `current(W)` for the waiting
  // bundle, or the newest verdict nothing has overtaken when nothing waits,
  // and this function consumes that and the phase.
  //
  // The arms below are the same STATES as the ones they replace, fed what the
  // resolver actually produces in each. They are deliberately not the old
  // assertions with a new expected value: the old ones would still pass if the
  // scoping came back here as a second opinion, and a rule enforced twice is
  // how two surfaces got to disagree in the first place.
  it('takes the resolved record as final — it does not re-scope it', () => {
    // The report cannot carry a record about a bundle that is not the one
    // waiting (A5.17.6), so this state is unreachable from any writer. It is
    // pinned because the failure it guards against is this card growing its
    // own opinion again: if it ever disagreed with the resolver, the briefing
    // — which has no such opinion — would say something else.
    const status = {
      ...BASE, phase: 'refused', latest: WAITING,
      last_refusal: { ...LOCKED_REFUSAL, bundle: 'f'.repeat(40) },
      last_refusal_source: 'state',
    } as UpdateStatus
    expect(refusalToShow(status)).toEqual({ ...LOCKED_REFUSAL, bundle: 'f'.repeat(40) })
    expect(updateHeadline(status)).toContain('Update refused')
  })

  // CURRENCY — the round-3 defect, now enforced where the record is chosen.
  // Nothing ever clears the legacy `last_refusal`; the updater carries it onto
  // every later state document on purpose, because a refusal is still TRUE
  // after the next thing happens. What it stops being is the NEWS, and the
  // resolver is what stops reporting it: an apply or rollback fact strictly
  // newer than the verdict supersedes it (A5.17.5), and with nothing waiting a
  // verdict speaks only while it is newer than every apply and rollback on
  // record (6). Oracle rows `applied/none/*` and `rolled_back/none/*`.
  for (const [phase, sentence] of [
    ['applied', 'Updated to cccccccc: 4 changes'],
    ['rolled_back', 'An update was rolled back to cccccccc: the health gate was red'],
  ]) {
    it(`the resolver has already dropped a verdict ${phase} overtook`, () => {
      const status = {
        ...BASE, phase, latest: null, last_refusal: null, last_refusal_source: '',
        last: { phase, to_sha: 'c'.repeat(40), changed: 4,
                reason: 'the health gate was red' },
      } as UpdateStatus
      expect(refusalToShow(status)).toBeNull()
      expect(updateHeadline(status)).toBe(sentence)
    })
  }

  it('the busy race ends in the applied sentence, not in its own refusal', () => {
    // Winner takes bbbb..., loser records `busy` about bbbb..., winner lands.
    // The install IS bbbb..., so nothing is waiting — and the busy note was
    // never a verdict, so there is nothing for the resolver to report either.
    const status: UpdateStatus = {
      ...BASE, phase: 'applied', latest: null, last_refusal: null,
      last_busy: { bundle: 'b'.repeat(40), ts: '2026-09-09T10:00:30Z' },
      last: { phase: 'applied', to_sha: 'b'.repeat(40), changed: 4 },
    }
    expect(refusalToShow(status)).toBeNull()
    expect(updateHeadline(status)).toBe('Updated to bbbbbbbb: 4 changes')
  })

  it('a bundle this box rolled back is neither refused nor untried', () => {
    // A5.17.7, and the per-surface difference round 5 declared and the A5.17
    // gate RETIRED: the briefing said this and the card said "Update ready".
    // Apply stays — retrying a health gate that went red is legitimate — but
    // the sentence is the same on both doors now.
    const status: UpdateStatus = {
      ...BASE, phase: 'idle', latest: WAITING, last_refusal: null,
      waiting_rollback: { bundle: 'b'.repeat(40), reason: 'the health gate was red',
                          ts: '2026-09-09T10:00:20Z' },
    }
    expect(refusalToShow(status)).toBeNull()
    expect(updateHeadline(status)).toBe(
      'Update rolled back — the health gate was red; still waiting (bbbbbbbb)')
    expect(applyTarget(status)).not.toBeNull()
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
  resolved: {
    last_refusal: Record<string, unknown> | null
    source: string
    waiting_rollback: { bundle: string; reason: string; ts: string } | null
  }
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
      line.startsWith('Update rolled back') ||
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
 *  hand-shaped object that agrees with the card by construction.
 *
 *  `last_refusal` comes from the case's declared `resolved` (A5.17): the card
 *  consumes ONE resolved refusal — the verdict standing on the WAITING bundle —
 *  and never scopes a state field itself. The same declaration is asserted
 *  against the briefing's own resolver, over these very bytes, in
 *  `test_card_update_notice.py`, so the two halves are not driven from two
 *  different resolutions. */
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
    last_refusal: (c.resolved.last_refusal as never) ?? null,
    last_refusal_source: c.resolved.source,
    waiting_rollback: c.resolved.waiting_rollback ?? null,
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

  it('keeps Apply for a receipt-sourced verdict a retry can re-test', () => {
    // The other half of "treated exactly like a state-sourced one": a digest
    // verdict names no constitutional path, so it says what happened and
    // LEAVES the button (A5.17.7). The `busy` case is not tested here any
    // more because it cannot arrive: a timing note is not a candidate on any
    // channel (A5.17.1), which is a property of the resolver and is pinned on
    // it — `test_cabinet_update.py` and every `*/…/V-busy/*` oracle row.
    const status: UpdateStatus = {
      ...BASE, available: [waiting], latest: waiting,
      last_refusal: { bundle: refused, reason: 'the bundle does not match its manifest',
                      paths: [], ts: '2026-09-09T10:00:00Z', door: 'web' },
      last_refusal_source: 'receipt',
    }
    expect(refusalToShow(status)).not.toBeNull()
    expect(updateHeadline(status)).toBe(
      'Update refused — the bundle does not match its manifest (bbbbbbbb)')
    expect(applyTarget(status)).not.toBeNull()
  })
})

// ---------------------------------------------------------------------------
// THE WHOLE STATE SPACE — every state, not the ones somebody thought of.
//
// Five review rounds each found one more adjacent state in this reader and its
// twin, and every arm written for each of them was aimed at the state that
// already worked: round 1's two arms pinned `phase: 'applied'`, round 2's
// pinned a state with no waiting bundle, round 3's both pinned
// `phase: 'refused'`, round 4's all ran on an EMPTY ledger, round 5's on a
// ledger exactly ONE record deep — the one depth at which "the newest refusal
// about this bundle" and "the newest refusal anywhere" cannot be told apart.
//
// `update_surface_oracle.json` is the whole product of the six axes these
// readers branch on (5250 rows), carrying the exact SENTENCE for each surface,
// whether the refusal sub-surface speaks, whether Apply is live, and what both
// resolvers must produce. It is derived from the contract (A5.17), not from
// either implementation: a row where the code disagrees is a defect in the
// code. The briefing's half is `test_card_update_notice.py`, and the resolver
// that FEEDS this card is driven against the same file in
// `cabinet/scripts/tests/test_cabinet_update.py` — three readers, one table, so
// a sentence flipped in it reds all three, and a fixture that went missing
// FAILS rather than skips.
// ---------------------------------------------------------------------------

const ORACLE_FIXTURES = path.resolve(
  __dirname, '..', '..', '..', '..',
  'framework', 'frontdoor', 'tests', 'update_surface_oracle.json'
)

type OracleRow = {
  id: string
  axes: Record<string, string | boolean>
  resolved: {
    last_refusal: Record<string, unknown> | null
    source: string
    waiting_rollback: { bundle: string; reason: string; ts: string } | null
  }
  expect: {
    briefing: string
    card: string
    refusal_speaks: boolean
    apply_live: boolean
    last_refusal_source: string
  }
}

/** The row as `cabinet-update.sh status --json` reports it — the same
 *  derivation, field for field.
 *
 *  `last_refusal`, its source and `waiting_rollback` come from the row's
 *  `resolved`, because that is where they come from in production: the updater
 *  resolves the marker store, the ledger and the legacy state record into ONE
 *  answer ABOUT THE WAITING BUNDLE and this card reads only the result. Round 4
 *  measured what the other arrangement costs (the briefing read a channel this
 *  card could not see); round 5 measured what a resolution that is not scoped
 *  per bundle costs (a note about a moment blanked a verdict on the bytes in
 *  the inbox, on BOTH surfaces at once). The resolver that produces `resolved`
 *  is held to this same column, on the same 5250 rows, in the cabinet suite —
 *  so this half is not driven from an answer the card's own code invented. */
function statusOfRow(doc: OracleDoc, row: OracleRow): UpdateStatus {
  const state = { ...(doc.phase_state[row.axes.phase as string] || {}) } as Record<string, unknown>
  if (doc.legacy[row.axes.state as string]) {
    state.last_refusal = doc.legacy[row.axes.state as string]
  }
  if (row.axes.ledger_error) state.ledger_error = doc.ledger_error_text
  const bundle = doc.waiting_bundles[row.axes.waiting as string]
  const latest = bundle
    ? {
        sha: bundle.sha, short: bundle.sha.slice(0, 8), built_at: bundle.built_at,
        from_sha: null, file_count: bundle.file_count, changelog: [],
        owner: 'someone', mtime: bundle.built_at,
      }
    : null
  return {
    installed_sha: doc.shas.installed,
    installed_short: doc.shas.installed.slice(0, 8),
    phase: (state.phase as string) || 'idle',
    last: Object.keys(state).length ? (state as never) : null,
    available: latest ? [latest] : [],
    latest,
    snapshots: [],
    last_refusal: (row.resolved.last_refusal as never) ?? null,
    last_refusal_source: row.resolved.source,
    waiting_rollback: row.resolved.waiting_rollback,
    event_fallback: Boolean(state.event_fallback),
    ledger_error: (state.ledger_error as string) || '',
  } as UpdateStatus
}

type OracleDoc = {
  rows: OracleRow[]
  axes: Record<string, (string | boolean)[]>
  shas: Record<string, string>
  times: Record<string, string>
  ledger_error_text: string
  waiting_bundles: Record<string, { sha: string; file_count: number; built_at: string }>
  phase_state: Record<string, Record<string, unknown>>
  legacy: Record<string, Record<string, unknown>>
  markers: Record<string, Record<string, unknown>>
  ledger_seeds: Record<string, unknown[]>
  other_seeds: Record<string, unknown[]>
}

const ORACLE_AXES = ['phase', 'waiting', 'state', 'ledger', 'other', 'ledger_error'] as const

function oracleId(axes: Record<string, string | boolean>): string {
  return [
    axes.phase, axes.waiting, axes.state, axes.ledger, axes.other,
    axes.ledger_error ? 'fault' : 'noledger',
  ].join('/')
}

describe('the whole state space', () => {
  const doc = JSON.parse(fs.readFileSync(ORACLE_FIXTURES, 'utf-8')) as OracleDoc
  const rows = doc.rows

  it('the oracle covers the whole product of the axes it declares', () => {
    // Derived from the declared axes rather than compared to a number, so it
    // detects a REMOVED row as well as a changed one. Round 4 added the ledger
    // as an axis; round 6 made it an axis of SEQUENCES and split off what the
    // ledger says about ANOTHER bundle, because holding an input's depth
    // constant is the same green hole as leaving the input out.
    const values = ORACLE_AXES.map((name) => doc.axes[name])
    const expected = new Set<string>()
    const walk = (index: number, picked: (string | boolean)[]) => {
      if (index === values.length) {
        expected.add(oracleId(Object.fromEntries(
          ORACLE_AXES.map((name, i) => [name, picked[i]])
        )))
        return
      }
      for (const value of values[index]) walk(index + 1, [...picked, value])
    }
    walk(0, [])
    expect(expected.size).toBe(5250)
    expect(rows.map((r) => r.id).sort()).toEqual([...expected].sort())
    for (const row of rows) expect(row.id).toBe(oracleId(row.axes))
    // A declared axis value with nothing behind it is an axis held constant
    // under a name — exactly what the ledger was, and then its depth.
    expect(Object.keys(doc.ledger_seeds).sort()).toEqual([...doc.axes.ledger].sort())
    expect(Object.keys(doc.other_seeds).sort()).toEqual([...doc.axes.other].sort())
    expect(Math.max(...Object.values(doc.ledger_seeds).map((s) => s.length)))
      .toBeGreaterThanOrEqual(2)
  })

  it('the card answers every state the way the oracle says', () => {
    const wrong: string[] = []
    for (const row of rows) {
      const status = statusOfRow(doc, row)
      const line = updateHeadline(status)
      const spoke = refusalToShow(status) !== null
      const live = applyTarget(status) !== null
      if (line !== (row.expect.card || null) ||
          spoke !== row.expect.refusal_speaks ||
          live !== row.expect.apply_live) {
        wrong.push(
          `${row.id}: line ${JSON.stringify(line)} (want ` +
          `${JSON.stringify(row.expect.card || null)}), refusal spoke ${spoke} ` +
          `(want ${row.expect.refusal_speaks}), apply ${live} ` +
          `(want ${row.expect.apply_live})`
        )
      }
    }
    // The count leads the sample: a sensor that shows twenty rows without
    // saying how many there are reads the same at 20 as at 5250.
    expect([`${wrong.length} of ${rows.length} wrong`, ...wrong.slice(0, 10)])
      .toEqual([`0 of ${rows.length} wrong`])
  })

  it('a held record and a busy note never move the headline', () => {
    // The card's half of two of the four INVARIANCE claims A5.17.8 makes to
    // keep the product at 5250 rows rather than 21,000: `event_fallback` and
    // `last_busy` are a sub-line and a diagnostic, never the sentence. Varied
    // on rows that are already in the table, so a reader that started
    // consulting either would go red here rather than silently.
    const sample = rows.filter((_row, index) => index % 61 === 0)
    expect(sample.length).toBeGreaterThanOrEqual(50)
    const wrong: string[] = []
    sample.forEach((row, index) => {
      const status = statusOfRow(doc, row)
      status.event_fallback = index % 2 === 0
      status.last_busy = { bundle: index % 3 ? doc.shas.other : '', ts: doc.times.not_about_b }
      status.state_error = index % 5 ? 'OSError: [Errno 13] Permission denied' : ''
      const line = updateHeadline(status)
      if (line !== (row.expect.card || null)) wrong.push(`${row.id}: ${line}`)
    })
    expect([`${wrong.length} of ${sample.length} moved`, ...wrong.slice(0, 10)])
      .toEqual([`0 of ${sample.length} moved`])
  })
})
