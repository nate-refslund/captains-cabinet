/**
 * The outcome read models, and the two surfaces that render them.
 *
 * The home-card line (A1.7) is the point of this file. A ratified outcome that
 * appears only on a page the operator has to go and visit is a receipt nobody
 * reads, so a tap has to be visible where they already are — and the arm that
 * proves it is wired to the LIVE component, not to a helper the component
 * might no longer call.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import nodePath from 'node:path'

const { mockLocalExec } = vi.hoisted(() => ({ mockLocalExec: vi.fn() }))

vi.mock('@/lib/local-exec', () => ({
  localExec: mockLocalExec,
  CABINET_PYTHON: 'python3.12',
}))

import { latestRatified, listProposedOutcomes, takingOnLine } from './outcomes'
import { newestFirst, readReceipts, DOOR_LABEL, type WorkReceipt } from './work-receipts'

const CARD = {
  id: 'acme-001',
  name: 'Ship the storefront',
  what: 'the site answers',
  why: 'the operator asked',
  proof_expected: 'a receipt',
  proposed_digest: 'abc',
}

function receipt(over: Partial<WorkReceipt>): WorkReceipt {
  return {
    ts: null, kind: 'ratified', actor: 'captain', event_id: 'e', outcome_id: null,
    task_id: null, claim_id: null, holder: null, door: null, evidence_path: null,
    name: null,
    ...over,
  } as WorkReceipt
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.unstubAllEnvs())

describe('listProposedOutcomes', () => {
  it('returns the writer’s own rows', async () => {
    mockLocalExec.mockResolvedValue({ stdout: JSON.stringify([CARD]), stderr: '' })
    expect(await listProposedOutcomes()).toEqual([CARD])
    const argv = mockLocalExec.mock.calls[0][0] as string[]
    expect(argv).toContain('framework.outcomes.ratify')
    expect(argv).toContain('--list')
  })

  it.each([
    ['no output', { stdout: '', stderr: '' }],
    ['a non-array', { stdout: '{"nope":1}', stderr: '' }],
    ['unparseable', { stdout: 'not json', stderr: '' }],
  ])('degrades to an honest empty on %s', async (_label, out) => {
    mockLocalExec.mockResolvedValue(out)
    expect(await listProposedOutcomes()).toEqual([])
  })

  it('never throws when the command fails', async () => {
    mockLocalExec.mockRejectedValue(new Error('boom'))
    expect(await listProposedOutcomes()).toEqual([])
  })

  it('drops a row with no id rather than rendering a blank card', async () => {
    mockLocalExec.mockResolvedValue({
      stdout: JSON.stringify([CARD, { id: '', name: 'ghost' }]),
      stderr: '',
    })
    expect(await listProposedOutcomes()).toEqual([CARD])
  })
})

describe('the home-card line (A1.7)', () => {
  it('names the outcome, falling back to the id rather than a blank', () => {
    expect(takingOnLine('acme-001', 'Ship the storefront')).toBe(
      'Taking on: Ship the storefront'
    )
    expect(takingOnLine('acme-001', '   ')).toBe('Taking on: acme-001')
    expect(takingOnLine('acme-001', null)).toBe('Taking on: acme-001')
  })

  it('is null until a tap has actually happened', async () => {
    expect(await latestRatified([])).toBeNull()
    expect(
      await latestRatified([receipt({ kind: 'started', outcome_id: 'acme-001' })])
    ).toBeNull()
  })

  it('reads the NEWEST ratification off the receipts, with its door', async () => {
    const rows = [
      receipt({ outcome_id: 'acme-001', door: 'terminal', ts: '2026-09-01T00:00:00Z' }),
      receipt({ kind: 'started', outcome_id: 'acme-001' }),
      receipt({
        outcome_id: 'acme-002',
        name: 'Ship the storefront',
        door: 'web',
        ts: '2026-09-02T00:00:00Z',
      }),
    ]
    const latest = await latestRatified(rows)
    expect(latest).toMatchObject({
      outcomeId: 'acme-002',
      // A1.7 asks for the NAME. A line reading "Taking on: acme-002" is the
      // id wearing the sentence's clothes.
      line: 'Taking on: Ship the storefront',
      door: 'web',
    })
  })

  it('falls back to the id when the receipt carried no name', async () => {
    const latest = await latestRatified([receipt({ outcome_id: 'acme-002', door: 'web' })])
    expect(latest?.line).toBe('Taking on: acme-002')
  })

  it('is rendered by the live home card', () => {
    // Wired to the artifact: a helper nothing calls is not a home-card line.
    const source = readFileSync(
      nodePath.join(__dirname, '..', 'components', 'consumer', 'card-cabinet.tsx'),
      'utf8'
    )
    expect(source).toContain('latestRatified')
    expect(source).toContain('takenOn.line')
  })

  it('is rendered by the live proposed card and the briefing page', () => {
    const card = readFileSync(
      nodePath.join(__dirname, '..', 'components', 'outcomes', 'proposed-card.tsx'),
      'utf8'
    )
    expect(card).toContain('ratifyOutcome')
    expect(card).toContain('Ratify')
    const page = readFileSync(
      nodePath.join(__dirname, '..', 'app', '(authenticated)', 'briefing', 'page.tsx'),
      'utf8'
    )
    expect(page).toContain('ProposedCard')
    expect(page).toContain('listProposedOutcomes')
  })
})

describe('work receipts', () => {
  it('keeps only the declared kinds', async () => {
    mockLocalExec.mockResolvedValue({
      stdout: JSON.stringify([
        { kind: 'ratified', outcome_id: 'a' },
        { kind: 'not-a-kind', outcome_id: 'b' },
        { kind: 'completed', outcome_id: 'c' },
      ]),
      stderr: '',
    })
    const out = await readReceipts()
    expect(out.receipts.map((r) => r.kind)).toEqual(['ratified', 'completed'])
    expect(out.unreadable).toBeNull()
  })

  it('an unreadable ledger is a REASON, never an empty list', async () => {
    mockLocalExec.mockRejectedValue(new Error('ENOENT: python3.12 not found'))
    const out = await readReceipts()
    expect(out.receipts).toEqual([])
    expect(out.unreadable).toContain('could not be read')
  })

  it('an empty ledger is a fact, not a failure', async () => {
    mockLocalExec.mockResolvedValue({ stdout: '', stderr: '' })
    const out = await readReceipts()
    expect(out).toEqual({ receipts: [], unreadable: null })
  })

  it('renders newest first, capped', () => {
    const rows = [1, 2, 3].map((n) => receipt({ outcome_id: `a-${n}` }))
    expect(newestFirst(rows, 2).map((r) => r.outcome_id)).toEqual(['a-3', 'a-2'])
    expect(rows.map((r) => r.outcome_id)).toEqual(['a-1', 'a-2', 'a-3'])
  })

  it('labels each door for a person', () => {
    expect(DOOR_LABEL.terminal).toBeTruthy()
    expect(DOOR_LABEL.web).toBeTruthy()
    expect(DOOR_LABEL.chat).toBeTruthy()
  })

  it('is rendered as a second section on /receipts, beside the journal', () => {
    const page = readFileSync(
      nodePath.join(__dirname, '..', 'app', '(authenticated)', 'receipts', 'page.tsx'),
      'utf8'
    )
    expect(page).toContain('readReceipts')
    expect(page).toContain('listReceipts')
  })
})
