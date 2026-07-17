/**
 * Unit tests for the /evidence read model.
 *
 * Pure functions (filter validation, event parsing, basis derivation,
 * matching, shaping) are tested without I/O; the filesystem snapshot and
 * the orchestrator run against tmpdir fixtures with the Python verifier
 * replaced by an injected fake (the production spawn is pinned separately
 * by verifierInvocation/parseVerifyStdout tests and the static contract).
 *
 * Synthetic 'Testburg' vocabulary only. The hostile-input cases replay the
 * PR#140/#149 bypass shapes against the filter surface: traversal-shaped,
 * flag-shaped, newline-smuggled, overlong, array-typed and __proto__ values
 * must all be refused BEFORE any I/O happens.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { promises as fs } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import {
  EVIDENCE_SHOW_CAP,
  EVIDENCE_STATUSES,
  deriveBasis,
  evidenceDir,
  evidenceUtcLabel,
  eventMatches,
  hasActiveFilters,
  parseEventLine,
  parseVerifyStdout,
  readEvidence,
  summarizeVerifiedTrial,
  trialMatches,
  validateFilters,
  verifierInvocation,
  type EvidenceEventLite,
  type StoreVerifyResult,
  type VerifyOutcome,
} from './read'

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/** Lite event factory (pure-function tests). */
function lite(over: Partial<EvidenceEventLite> = {}): EvidenceEventLite {
  return {
    phase: 'execution',
    status: 'succeeded',
    ts: '2026-07-14T09:00:00.000000Z',
    actorKind: 'system',
    actorId: 'testburg-core',
    component: 'testburg-lane',
    source: null,
    resultCode: null,
    ...over,
  }
}

/** Full ledger line factory (fs tests) — extra fields prove the lite
 * parser extracts only what it needs. */
function ledgerLine(over: Record<string, unknown> = {}): string {
  return JSON.stringify({
    schema: 'cabinet.evidence-event/v1',
    event_id: 'ev-0001',
    sequence: 1,
    phase: 'execution',
    status: 'succeeded',
    ts: '2026-07-14T09:00:00.123456Z',
    actor: { kind: 'system', id: 'testburg-core' },
    component: { name: 'testburg-lane', version: '1', commit: 'abc' },
    detail: { action: 'testburg_act' },
    trust: 'untrusted_observation',
    previous_hash: '0'.repeat(64),
    event_hash: 'f'.repeat(64),
    signature: 'f'.repeat(64),
    ...over,
  })
}

const cleanups: Array<() => Promise<void>> = []

async function makeStoreRoot(): Promise<{ root: string; store: string; trials: string }> {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'testburg-evidence-'))
  cleanups.push(async () => fs.rm(root, { recursive: true, force: true }))
  const store = path.join(root, 'instance', 'evidence', 'v1')
  const trials = path.join(store, 'trials')
  await fs.mkdir(trials, { recursive: true })
  vi.stubEnv('CABINET_ROOT', root)
  return { root, store, trials }
}

async function writeTrial(trials: string, trialId: string, lines: string[]): Promise<void> {
  const dir = path.join(trials, trialId)
  await fs.mkdir(dir, { recursive: true })
  await fs.writeFile(path.join(dir, 'events.jsonl'), lines.map((l) => l + '\n').join(''), 'utf8')
}

function okStore(trialRows: Array<{ id: string; ok?: boolean; count?: number; errors?: string[] }>): StoreVerifyResult {
  return {
    ok: trialRows.every((row) => row.ok !== false),
    trials: trialRows.map((row) => ({
      ok: row.ok !== false,
      trialId: row.id,
      eventCount: row.count ?? 1,
      errors: row.errors ?? [],
    })),
    errors: [],
  }
}

function fakeVerify(outcome: VerifyOutcome): { fn: (dir: string) => Promise<VerifyOutcome>; calls: string[] } {
  const calls: string[] = []
  return {
    calls,
    fn: async (dir: string) => {
      calls.push(dir)
      return outcome
    },
  }
}

afterEach(async () => {
  vi.unstubAllEnvs()
  while (cleanups.length) await cleanups.pop()!()
})

// ---------------------------------------------------------------------------
// validateFilters — strict allowlists, refusal BEFORE any I/O
// ---------------------------------------------------------------------------

describe('validateFilters', () => {
  it('accepts absent/empty filters', () => {
    expect(validateFilters()).toEqual({ ok: true, filters: {} })
    expect(validateFilters(null)).toEqual({ ok: true, filters: {} })
    expect(validateFilters({})).toEqual({ ok: true, filters: {} })
    expect(validateFilters({ actor: '', status: undefined })).toEqual({ ok: true, filters: {} })
  })

  it('accepts each valid dimension', () => {
    expect(validateFilters({ actor: 'testburg-core' })).toEqual({
      ok: true,
      filters: { actor: 'testburg-core' },
    })
    expect(validateFilters({ actor: 'officer:cos' })).toEqual({
      ok: true,
      filters: { actor: 'officer:cos' },
    })
    expect(validateFilters({ component: 'action-lane' })).toEqual({
      ok: true,
      filters: { component: 'action-lane' },
    })
    expect(validateFilters({ status: 'failed' })).toEqual({
      ok: true,
      filters: { status: 'failed' },
    })
    expect(validateFilters({ time: '20260714' })).toEqual({
      ok: true,
      filters: { time: '20260714' },
    })
    expect(validateFilters({ time: '20260701-20260715' })).toEqual({
      ok: true,
      filters: { time: '20260701-20260715' },
    })
  })

  it('accepts the 128-char token boundary and refuses 129', () => {
    const okToken = 'a'.repeat(128)
    expect(validateFilters({ component: okToken }).ok).toBe(true)
    expect(validateFilters({ component: okToken + 'a' }).ok).toBe(false)
  })

  it('a prefix that is not a known actor kind stays a plain id token', () => {
    expect(validateFilters({ actor: 'unknownkind:cos' })).toEqual({
      ok: true,
      filters: { actor: 'unknownkind:cos' },
    })
  })

  it('refuses kind: with an empty or invalid id', () => {
    expect(validateFilters({ actor: 'officer:' }).ok).toBe(false)
    expect(validateFilters({ actor: 'officer::' }).ok).toBe(false)
  })

  it('refuses traversal-shaped, flag-shaped, smuggled and malformed values (PR#140/#149 replay)', () => {
    for (const hostile of [
      '../../etc/passwd', // traversal (slash not in charset)
      '..%2f..%2fetc', // encoded traversal (% not in charset)
      '--store', // flag-shaped (leading dash)
      '-rf', // flag-shaped
      'cos\ncat /etc/passwd', // newline smuggle
      'cos; cat /etc/passwd', // compound command
      'cos && rm -rf', // compound command
      'cos cat', // second token
      '$HOME', // expansion-shaped
      '`id`', // subshell-shaped
      ':leadingcolon', // first char must be alnum
      '.hidden', // first char must be alnum
    ]) {
      const verdict = validateFilters({ actor: hostile })
      expect(verdict.ok, `actor ${JSON.stringify(hostile)}`).toBe(false)
      const verdict2 = validateFilters({ component: hostile })
      expect(verdict2.ok, `component ${JSON.stringify(hostile)}`).toBe(false)
    }
  })

  it('refuses non-string and array values (query-param arrays refuse loudly)', () => {
    expect(validateFilters({ actor: ['cos', 'cto'] as unknown }).ok).toBe(false)
    expect(validateFilters({ status: 5 as unknown }).ok).toBe(false)
    expect(validateFilters({ time: { from: 1 } as unknown }).ok).toBe(false)
  })

  it('refuses unknown filter names, including __proto__', () => {
    expect(validateFilters({ evil: 'x' } as never).ok).toBe(false)
    expect(validateFilters(JSON.parse('{"__proto__": "x"}') as never).ok).toBe(false)
  })

  it('refuses out-of-vocabulary statuses (closed enum, case-sensitive)', () => {
    expect(validateFilters({ status: 'bogus' }).ok).toBe(false)
    expect(validateFilters({ status: 'FAILED' }).ok).toBe(false)
    // the v1.1 absence vocabulary is in
    expect(EVIDENCE_STATUSES.has('missed')).toBe(true)
    expect(validateFilters({ status: 'missed' }).ok).toBe(true)
  })

  it('refuses malformed time values', () => {
    for (const bad of ['2026071', '202607140', '20261301', '20260732', '20260715-20260701', '20260714-20260714-20260714', '2026-07-14']) {
      expect(validateFilters({ time: bad }).ok, `time ${bad}`).toBe(false)
    }
    expect(validateFilters({ time: '20260714-20260714' }).ok).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// parseEventLine — defensive extraction only
// ---------------------------------------------------------------------------

describe('parseEventLine', () => {
  it('extracts exactly the lite fields', () => {
    const parsed = parseEventLine(
      ledgerLine({ detail: { action: 'x', source: 'verdict_judge', result_code: 'ttl_ok' } })
    )
    expect(parsed).toEqual({
      phase: 'execution',
      status: 'succeeded',
      ts: '2026-07-14T09:00:00.123456Z',
      actorKind: 'system',
      actorId: 'testburg-core',
      component: 'testburg-lane',
      source: 'verdict_judge',
      resultCode: 'ttl_ok',
    })
  })

  it('never throws on garbage and never invents fields', () => {
    expect(parseEventLine('not json')).toBeNull()
    expect(parseEventLine('[1,2]')).toBeNull()
    expect(parseEventLine('"str"')).toBeNull()
    const sparse = parseEventLine('{}')
    expect(sparse).toEqual({
      phase: '',
      status: '',
      ts: '',
      actorKind: '',
      actorId: '',
      component: '',
      source: null,
      resultCode: null,
    })
    const badShapes = parseEventLine(
      ledgerLine({ actor: 'not-a-dict', component: [1], detail: 7 })
    )
    expect(badShapes?.actorKind).toBe('')
    expect(badShapes?.component).toBe('')
    expect(badShapes?.source).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// deriveBasis — the four classes, strongest-first
// ---------------------------------------------------------------------------

describe('deriveBasis', () => {
  it('captain-attributed judgment events are human-verified (verification/outcome/feedback)', () => {
    for (const phase of ['verification', 'outcome', 'feedback']) {
      const { basis } = deriveBasis([lite(), lite({ phase, actorKind: 'captain', actorId: 'captain' })])
      expect(basis, phase).toBe('human-verified')
    }
  })

  it('a captain actor on a NON-judgment phase does not count', () => {
    const { basis } = deriveBasis([lite({ phase: 'intent', actorKind: 'captain' })])
    expect(basis).toBe('persistence-only')
  })

  it('a recorded human verdict (source verdict_human) is human-verified', () => {
    const { basis } = deriveBasis([
      lite(),
      lite({ phase: 'verification', status: 'verified', source: 'verdict_human' }),
    ])
    expect(basis).toBe('human-verified')
  })

  it('a judge verdict (source verdict_judge) is independently-recomputed', () => {
    const { basis } = deriveBasis([
      lite(),
      lite({ phase: 'outcome', status: 'succeeded', source: 'verdict_judge' }),
    ])
    expect(basis).toBe('independently-recomputed')
  })

  it('producer/system verification without a source is self-asserted', () => {
    const { basis } = deriveBasis([
      lite(),
      lite({ phase: 'verification', status: 'verified' }),
    ])
    expect(basis).toBe('self-asserted')
  })

  it('only reconciler ttl_ok persistence confirmations stay persistence-only', () => {
    const { basis, reason } = deriveBasis([
      lite(),
      lite({ phase: 'verification', status: 'verified', resultCode: 'ttl_ok' }),
    ])
    expect(basis).toBe('persistence-only')
    expect(reason).toContain('ttl_ok')
  })

  it('execution-only trials (even succeeded) are persistence-only', () => {
    expect(deriveBasis([lite()]).basis).toBe('persistence-only')
    expect(deriveBasis([]).basis).toBe('persistence-only')
  })

  it('precedence: human beats judge beats self-assertion', () => {
    const judge = lite({ phase: 'outcome', source: 'verdict_judge' })
    const human = lite({ phase: 'verification', actorKind: 'captain' })
    const self = lite({ phase: 'verification' })
    expect(deriveBasis([self, judge, human]).basis).toBe('human-verified')
    expect(deriveBasis([self, judge]).basis).toBe('independently-recomputed')
  })
})

// ---------------------------------------------------------------------------
// matching + labels + shaping
// ---------------------------------------------------------------------------

describe('eventMatches / trialMatches', () => {
  it('actor: bare value matches actor id; kind:id pins both', () => {
    const event = lite({ actorKind: 'officer', actorId: 'cos' })
    expect(eventMatches(event, { actor: 'cos' })).toBe(true)
    expect(eventMatches(event, { actor: 'officer:cos' })).toBe(true)
    expect(eventMatches(event, { actor: 'system:cos' })).toBe(false)
    expect(eventMatches(event, { actor: 'cto' })).toBe(false)
  })

  it('component and status match exactly', () => {
    const event = lite({ component: 'action-lane', status: 'failed' })
    expect(eventMatches(event, { component: 'action-lane' })).toBe(true)
    expect(eventMatches(event, { component: 'other' })).toBe(false)
    expect(eventMatches(event, { status: 'failed' })).toBe(true)
    expect(eventMatches(event, { status: 'succeeded' })).toBe(false)
  })

  it('time matches inclusive UTC date ranges; unparseable ts never matches', () => {
    const event = lite({ ts: '2026-07-14T23:59:59.000001Z' })
    expect(eventMatches(event, { time: '20260714' })).toBe(true)
    expect(eventMatches(event, { time: '20260701-20260715' })).toBe(true)
    expect(eventMatches(event, { time: '20260715' })).toBe(false)
    expect(eventMatches(lite({ ts: 'garbage' }), { time: '20260714' })).toBe(false)
  })

  it('dimensions AND together on a single event', () => {
    const a = lite({ actorId: 'cos', status: 'failed' })
    const b = lite({ actorId: 'cto', status: 'succeeded' })
    expect(eventMatches(a, { actor: 'cos', status: 'failed' })).toBe(true)
    expect(eventMatches(a, { actor: 'cos', status: 'succeeded' })).toBe(false)
    // one event carrying actor, another carrying status, is NOT a match
    expect(trialMatches([a, b], { actor: 'cto', status: 'failed' })).toBe(false)
    expect(trialMatches([a, b], { actor: 'cos', status: 'failed' })).toBe(true)
  })

  it('no active filters matches everything', () => {
    expect(trialMatches([], {})).toBe(true)
    expect(hasActiveFilters({})).toBe(false)
    expect(hasActiveFilters({ status: 'failed' })).toBe(true)
  })
})

describe('evidenceUtcLabel / summarizeVerifiedTrial', () => {
  it('renders recorder timestamps (fractional seconds) as UTC labels', () => {
    expect(evidenceUtcLabel('2026-07-14T09:00:00.123456Z')).toBe('2026-07-14 09:00:00 UTC')
    expect(evidenceUtcLabel('2026-07-14T09:00:00Z')).toBe('2026-07-14 09:00:00 UTC')
    expect(evidenceUtcLabel('garbage')).toBe('garbage') // shown raw, never reformatted
    expect(evidenceUtcLabel('')).toBe('—')
  })

  it('summarizes a trial: dedupe, caps, ts range, basis embedded', () => {
    const events = [
      lite({ ts: '2026-07-13T08:00:00.000000Z', phase: 'intent', status: 'started' }),
      lite({ ts: '2026-07-14T09:00:00.000000Z' }),
      lite({ ts: '2026-07-14T09:00:01.000000Z', phase: 'verification', status: 'verified' }),
    ]
    const row = summarizeVerifiedTrial('trial-testburg-1', events)
    expect(row.trialId).toBe('trial-testburg-1')
    expect(row.verified).toBe(true)
    expect(row.eventCount).toBe(3)
    expect(row.firstTs).toBe('2026-07-13 08:00:00 UTC')
    expect(row.lastTs).toBe('2026-07-14 09:00:01 UTC')
    expect(row.phases).toEqual(['intent', 'execution', 'verification'])
    expect(row.statuses).toEqual(['started', 'succeeded', 'verified'])
    expect(row.actors).toEqual(['system:testburg-core'])
    expect(row.components).toEqual(['testburg-lane'])
    expect(row.basis).toBe('self-asserted')
    expect(row.contentUnavailable).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// verifier invocation + stdout parsing (the spawn seam, pure parts)
// ---------------------------------------------------------------------------

describe('verifierInvocation', () => {
  it('is a fixed argv — house interpreter, module verb verify, no filter content', () => {
    vi.stubEnv('CABINET_PYTHON', '')
    const spec = verifierInvocation('/fixed/store')
    expect(spec.executable).toBe('python3.12')
    expect(spec.argv).toEqual(['-m', 'framework.evidence', '--store', '/fixed/store', 'verify'])
  })

  it('honors CABINET_PYTHON', () => {
    vi.stubEnv('CABINET_PYTHON', '/opt/testburg/python3.12')
    expect(verifierInvocation('/s').executable).toBe('/opt/testburg/python3.12')
  })
})

describe('parseVerifyStdout', () => {
  it('parses exit 0 and exit 4 payloads (exit 4 = failures recorded IN the payload)', () => {
    const body = JSON.stringify({
      ok: false,
      trials: [
        { ok: true, trial_id: 'trial-a', event_count: 2, errors: [] },
        { ok: false, trial_id: 'trial-b', event_count: 1, errors: ['event:1:signature'] },
      ],
      errors: ['one_or_more_trials_failed'],
    })
    for (const code of [0, 4]) {
      const outcome = parseVerifyStdout(body, code)
      expect(outcome.kind).toBe('result')
      if (outcome.kind === 'result') {
        expect(outcome.result.trials).toHaveLength(2)
        expect(outcome.result.trials[1].errors).toEqual(['event:1:signature'])
      }
    }
  })

  it('maps exit 3 to the typed refusal code', () => {
    const outcome = parseVerifyStdout(JSON.stringify({ ok: false, code: 'ledger_integrity' }), 3)
    expect(outcome).toEqual({ kind: 'failure', code: 'ledger_integrity' })
  })

  it('fails closed on unparseable output, weird exits, and hostile shapes', () => {
    expect(parseVerifyStdout('not json', 0).kind).toBe('failure')
    expect(parseVerifyStdout('[1]', 0).kind).toBe('failure')
    expect(parseVerifyStdout('{}', 1)).toEqual({ kind: 'failure', code: 'verifier_exit_1' })
    expect(parseVerifyStdout('{}', null)).toEqual({ kind: 'failure', code: 'verifier_exit_signal' })
    // trials with invalid ids or non-object rows are dropped, never served
    const outcome = parseVerifyStdout(
      JSON.stringify({ ok: true, trials: [{ ok: true, trial_id: '../escape', event_count: 1 }, 'junk'], errors: [] }),
      0
    )
    expect(outcome.kind).toBe('result')
    if (outcome.kind === 'result') expect(outcome.result.trials).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// readEvidence — fs snapshot + fail-closed join (fake verifier injected)
// ---------------------------------------------------------------------------

describe('readEvidence (tmpdir store, injected verifier)', () => {
  it('serves verified trials with content, newest first', async () => {
    const { trials } = await makeStoreRoot()
    await writeTrial(trials, 'trial-old', [
      ledgerLine({ ts: '2026-07-10T08:00:00.000000Z' }),
    ])
    await writeTrial(trials, 'trial-new', [
      ledgerLine({ ts: '2026-07-14T08:00:00.000000Z' }),
      ledgerLine({
        ts: '2026-07-14T08:00:01.000000Z',
        phase: 'verification',
        status: 'verified',
        actor: { kind: 'captain', id: 'captain' },
        sequence: 2,
      }),
    ])
    const verify = fakeVerify({
      kind: 'result',
      result: okStore([
        { id: 'trial-old', count: 1 },
        { id: 'trial-new', count: 2 },
      ]),
    })
    const payload = await readEvidence({}, { runVerify: verify.fn })
    expect(payload.error).toBeNull()
    expect(payload.rows.map((r) => r.trialId)).toEqual(['trial-new', 'trial-old'])
    expect(payload.rows[0].basis).toBe('human-verified')
    expect(payload.rows[1].basis).toBe('persistence-only')
    expect(payload.unverified).toEqual([])
    expect(payload.totalTrials).toBe(2)
    expect(payload.verifiedCount).toBe(2)
    expect(payload.storeOk).toBe(true)
    expect(verify.calls).toEqual([evidenceDir()])
  })

  it('renders failing trials as UNVERIFIED stubs with the verifier reason and zero content', async () => {
    const { trials } = await makeStoreRoot()
    await writeTrial(trials, 'trial-good', [ledgerLine()])
    await writeTrial(trials, 'trial-tampered', [ledgerLine({ status: 'failed' })])
    const verify = fakeVerify({
      kind: 'result',
      result: okStore([
        { id: 'trial-good', count: 1 },
        { id: 'trial-tampered', ok: false, count: 1, errors: ['event:1:signature', 'event:1:event_hash'] },
      ]),
    })
    const payload = await readEvidence(undefined, { runVerify: verify.fn })
    expect(payload.rows.map((r) => r.trialId)).toEqual(['trial-good'])
    expect(payload.unverified).toHaveLength(1)
    expect(payload.unverified[0].trialId).toBe('trial-tampered')
    expect(payload.unverified[0].verified).toBe(false)
    expect(payload.unverified[0].reason).toContain('event:1:signature')
    // zero content from the failing trial leaks into the payload
    expect(JSON.stringify(payload)).not.toContain('failed"') // its status never rendered
  })

  it('verifier failure = NOTHING served as verified; every trial an UNVERIFIED stub + loud error', async () => {
    const { trials } = await makeStoreRoot()
    await writeTrial(trials, 'trial-a', [ledgerLine()])
    await writeTrial(trials, 'trial-b', [ledgerLine()])
    const verify = fakeVerify({ kind: 'failure', code: 'verifier_timeout' })
    const payload = await readEvidence({}, { runVerify: verify.fn })
    expect(payload.error).toContain('verifier_timeout')
    expect(payload.rows).toEqual([])
    expect(payload.unverified.map((r) => r.trialId)).toEqual(['trial-a', 'trial-b'])
    expect(payload.unverified.every((r) => r.reason.includes('verifier did not run'))).toBe(true)
    expect(payload.unverifiedCount).toBe(2)
  })

  it('a trial on disk that the verifier did not cover renders UNVERIFIED (never silently served)', async () => {
    const { trials } = await makeStoreRoot()
    await writeTrial(trials, 'trial-a', [ledgerLine()])
    await writeTrial(trials, 'trial-raced', [ledgerLine()])
    const verify = fakeVerify({ kind: 'result', result: okStore([{ id: 'trial-a' }]) })
    const payload = await readEvidence({}, { runVerify: verify.fn })
    expect(payload.rows.map((r) => r.trialId)).toEqual(['trial-a'])
    expect(payload.unverified.map((r) => r.trialId)).toEqual(['trial-raced'])
    expect(payload.unverified[0].reason).toContain('not covered')
  })

  it('a verifier-passed trial whose bytes were not captured renders verified with an explicit unknown basis', async () => {
    const { trials } = await makeStoreRoot()
    await writeTrial(trials, 'trial-a', [ledgerLine()])
    const verify = fakeVerify({
      kind: 'result',
      result: okStore([{ id: 'trial-a' }, { id: 'trial-appeared', count: 3 }]),
    })
    const payload = await readEvidence({}, { runVerify: verify.fn })
    const appeared = payload.rows.find((r) => r.trialId === 'trial-appeared')
    expect(appeared).toBeDefined()
    expect(appeared?.contentUnavailable).toBe(true)
    expect(appeared?.basis).toBe('unknown')
    expect(appeared?.eventCount).toBe(3)
  })

  it('a snapshot LONGER than the verified ledger is rollback-shaped and refused', async () => {
    const { trials } = await makeStoreRoot()
    await writeTrial(trials, 'trial-shrunk', [ledgerLine(), ledgerLine({ sequence: 2 }), ledgerLine({ sequence: 3 })])
    const verify = fakeVerify({
      kind: 'result',
      result: okStore([{ id: 'trial-shrunk', count: 2 }]),
    })
    const payload = await readEvidence({}, { runVerify: verify.fn })
    expect(payload.rows).toEqual([])
    expect(payload.unverified[0].trialId).toBe('trial-shrunk')
    expect(payload.unverified[0].reason).toContain('rollback-shaped')
  })

  it('missing store dir = honest empty, verifier NEVER spawned (no store minting)', async () => {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'testburg-nostore-'))
    cleanups.push(async () => fs.rm(root, { recursive: true, force: true }))
    vi.stubEnv('CABINET_ROOT', root)
    const verify = fakeVerify({ kind: 'result', result: okStore([]) })
    const payload = await readEvidence({}, { runVerify: verify.fn })
    expect(payload.missingDir).toBe(true)
    expect(payload.error).toBeNull()
    expect(payload.rows).toEqual([])
    expect(verify.calls).toEqual([])
  })

  it('an invalid filter is refused BEFORE any read — verifier never called', async () => {
    await makeStoreRoot()
    const verify = fakeVerify({ kind: 'result', result: okStore([]) })
    const payload = await readEvidence({ actor: '../../etc/passwd' }, { runVerify: verify.fn })
    expect(payload.filterError).toBeTruthy()
    expect(payload.rows).toEqual([])
    expect(payload.unverified).toEqual([])
    expect(verify.calls).toEqual([])
  })

  it('filters serve matching trials only — but NEVER hide unverified trials', async () => {
    const { trials } = await makeStoreRoot()
    await writeTrial(trials, 'trial-hit', [ledgerLine({ status: 'failed', phase: 'error' })])
    await writeTrial(trials, 'trial-miss', [ledgerLine()])
    await writeTrial(trials, 'trial-bad', [ledgerLine()])
    const verify = fakeVerify({
      kind: 'result',
      result: okStore([
        { id: 'trial-hit' },
        { id: 'trial-miss' },
        { id: 'trial-bad', ok: false, errors: ['partial_tail'] },
      ]),
    })
    const payload = await readEvidence({ status: 'failed' }, { runVerify: verify.fn })
    expect(payload.rows.map((r) => r.trialId)).toEqual(['trial-hit'])
    expect(payload.matchedCount).toBe(1)
    expect(payload.verifiedCount).toBe(2)
    expect(payload.unverified.map((r) => r.trialId)).toEqual(['trial-bad'])
    expect(payload.filters).toEqual({ status: 'failed' })
  })

  it('corrupt ledger lines are counted, never crashed on; good lines still serve', async () => {
    const { trials } = await makeStoreRoot()
    await writeTrial(trials, 'trial-torn', [ledgerLine(), '{torn json', ledgerLine({ sequence: 2 })])
    const verify = fakeVerify({ kind: 'result', result: okStore([{ id: 'trial-torn', count: 2 }]) })
    const payload = await readEvidence({}, { runVerify: verify.fn })
    expect(payload.skippedLines).toBe(1)
    expect(payload.rows[0].eventCount).toBe(2)
  })

  it('an oversized ledger is counted in skippedFiles and served content-free', async () => {
    const { trials } = await makeStoreRoot()
    const dir = path.join(trials, 'trial-huge')
    await fs.mkdir(dir, { recursive: true })
    await fs.writeFile(path.join(dir, 'events.jsonl'), Buffer.alloc(5 * 1024 * 1024 + 1, 0x61))
    const verify = fakeVerify({ kind: 'result', result: okStore([{ id: 'trial-huge', count: 400 }]) })
    const payload = await readEvidence({}, { runVerify: verify.fn })
    expect(payload.skippedFiles).toBe(1)
    expect(payload.rows[0].contentUnavailable).toBe(true)
    expect(payload.rows[0].basis).toBe('unknown')
  })

  it('a planted symlink escape is never followed; the trial serves content-free', async () => {
    const { root, trials } = await makeStoreRoot()
    const outside = path.join(root, 'outside')
    await fs.mkdir(outside, { recursive: true })
    await fs.writeFile(path.join(outside, 'events.jsonl'), ledgerLine({ status: 'refused' }) + '\n')
    await fs.symlink(outside, path.join(trials, 'trial-planted'))
    // the real verifier fails symlinked trial dirs; mirror that verdict
    const verify = fakeVerify({
      kind: 'result',
      result: okStore([{ id: 'trial-planted', ok: false, errors: ['trial_dir_symlink'] }]),
    })
    const payload = await readEvidence({}, { runVerify: verify.fn })
    expect(payload.rows).toEqual([])
    expect(payload.unverified[0].reason).toContain('trial_dir_symlink')
    // the planted content never entered the payload
    expect(JSON.stringify(payload)).not.toContain('refused')
  })

  it('non-trial names on disk (bad charset) are not enumerated at all', async () => {
    const { trials } = await makeStoreRoot()
    await writeTrial(trials, 'trial-ok', [ledgerLine()])
    await fs.mkdir(path.join(trials, '.hidden'), { recursive: true })
    await fs.mkdir(path.join(trials, '__proto__'), { recursive: true })
    await fs.mkdir(path.join(trials, 'bad name'), { recursive: true })
    const verify = fakeVerify({ kind: 'result', result: okStore([{ id: 'trial-ok' }]) })
    const payload = await readEvidence({}, { runVerify: verify.fn })
    expect(payload.totalTrials).toBe(1)
    expect(payload.rows.map((r) => r.trialId)).toEqual(['trial-ok'])
  })

  it('caps served rows at EVIDENCE_SHOW_CAP with honest totals', async () => {
    const { trials } = await makeStoreRoot()
    const ids: string[] = []
    for (let i = 0; i < EVIDENCE_SHOW_CAP + 5; i += 1) {
      const id = `trial-bulk-${String(i).padStart(3, '0')}`
      ids.push(id)
      await writeTrial(trials, id, [
        ledgerLine({ ts: `2026-07-${String((i % 28) + 1).padStart(2, '0')}T00:00:00.000000Z` }),
      ])
    }
    const verify = fakeVerify({
      kind: 'result',
      result: okStore(ids.map((id) => ({ id }))),
    })
    const payload = await readEvidence({}, { runVerify: verify.fn })
    expect(payload.rows).toHaveLength(EVIDENCE_SHOW_CAP)
    expect(payload.matchedCount).toBe(EVIDENCE_SHOW_CAP + 5)
    expect(payload.verifiedCount).toBe(EVIDENCE_SHOW_CAP + 5)
  })

  it('store-level errors surface without hiding per-trial verdicts', async () => {
    const { trials } = await makeStoreRoot()
    await writeTrial(trials, 'trial-a', [ledgerLine()])
    const verify = fakeVerify({
      kind: 'result',
      result: {
        ok: false,
        trials: [{ ok: true, trialId: 'trial-a', eventCount: 1, errors: [] }],
        errors: ['control_signature'],
      },
    })
    const payload = await readEvidence({}, { runVerify: verify.fn })
    expect(payload.storeOk).toBe(false)
    expect(payload.storeErrors).toEqual(['control_signature'])
    expect(payload.rows).toHaveLength(1)
  })
})
