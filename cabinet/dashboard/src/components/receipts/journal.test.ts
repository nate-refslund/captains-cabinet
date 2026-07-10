/**
 * journal.ts coverage — the /receipts read model (perfect-cabinet Wave B).
 *
 * Pins the backend mirror (framework/frontdoor/action_undo.py):
 *   - dir resolution (CABINET_UNDO_DIR override / durable default)
 *   - jid collapse last-write-wins after a stable ts sort
 *   - corrupt-line tolerance: counted, never crashed on
 *   - unreadable-file tolerance: counted (skippedFiles), never rendered as
 *     an empty journal
 *   - symlink-escape files skipped SILENTLY, never followed, never counted
 *   - honest empty on a missing dir
 * plus the pure display logic: undo-state computation, cost labels, and the
 * shaped view model (DEMO flag, why, raw-slug fallback).
 *
 * All fixture data uses the synthetic Testburg vocabulary — never real
 * names, chats, or paths.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { promises as fs } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import {
  costLabel,
  isJournalFileName,
  parseJournalText,
  readJournal,
  shapeReceipt,
  undoDir,
  undoState,
  utcLabel,
  whyOf,
  type UndoJournalRow,
} from './journal'

const NOW = Date.parse('2026-07-10T12:00:00Z')

function row(over: Partial<UndoJournalRow> = {}): UndoJournalRow {
  return {
    jid: 'j-1',
    ts: '2026-07-10T10:00:00Z',
    pid: 'p-testburg-1',
    step: 0,
    kind: 'monday_task_update',
    action_type: 'board_status',
    lane: 'testburg-lane',
    subject: 'Ada Testburg — follow-up task',
    status: 'executed',
    executed_at: '2026-07-10T10:00:01Z',
    reversed_at: null,
    ttl_expires_at: '2026-07-12T10:00:00Z',
    ...over,
  }
}

// ---------------------------------------------------------------------------
// dir + filename resolution
// ---------------------------------------------------------------------------

describe('undoDir — mirrors action_undo._undo_dir', () => {
  afterEach(() => vi.unstubAllEnvs())

  it('CABINET_UNDO_DIR overrides', () => {
    vi.stubEnv('CABINET_UNDO_DIR', '/tmp/testburg-undo')
    expect(undoDir()).toBe('/tmp/testburg-undo')
  })

  it('defaults to the durable per-user location (never /tmp)', () => {
    vi.stubEnv('CABINET_UNDO_DIR', '')
    expect(undoDir()).toBe(
      path.join(os.homedir(), 'Library', 'Application Support', 'cabinet', 'undo')
    )
  })
})

describe('isJournalFileName — fixed pattern, no request input', () => {
  it('accepts the dated journal files', () => {
    expect(isJournalFileName('undo-journal-2026-07-10.jsonl')).toBe(true)
  })
  it('rejects the sibling fail-safe files in the same dir', () => {
    expect(isJournalFileName('frozen-kinds.jsonl')).toBe(false)
    expect(isJournalFileName('canary-receipts.jsonl')).toBe(false)
    expect(isJournalFileName('undo-journal-2026-07-10.jsonl.bak')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// parsing + collapse
// ---------------------------------------------------------------------------

describe('parseJournalText — well-formed rows', () => {
  it('parses rows and preserves fields', () => {
    const { rows, skipped } = parseJournalText([
      { name: 'undo-journal-2026-07-10.jsonl', text: JSON.stringify(row()) + '\n' },
    ])
    expect(skipped).toBe(0)
    expect(rows).toHaveLength(1)
    expect(rows[0].subject).toBe('Ada Testburg — follow-up task')
  })

  it('collapses write-ahead + enrichment by jid, last write wins', () => {
    // Same jid, same ts (the enrichment re-journals fast) — append order
    // must break the tie, exactly like the backend's stable sort.
    const writeAhead = row({ executed_at: null })
    const enriched = row({ executed_at: '2026-07-10T10:00:01Z' })
    const { rows } = parseJournalText([
      {
        name: 'undo-journal-2026-07-10.jsonl',
        text: `${JSON.stringify(writeAhead)}\n${JSON.stringify(enriched)}\n`,
      },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].executed_at).toBe('2026-07-10T10:00:01Z')
  })

  it('a later reversal row (later ts, other file) wins across files', () => {
    const executed = row()
    const reversed = row({
      ts: '2026-07-11T09:00:00Z',
      status: 'reversed',
      reversed_at: '2026-07-11T09:00:00Z',
    })
    const { rows } = parseJournalText([
      // Deliberately passed newest-file-first: the ts sort must fix the order.
      { name: 'undo-journal-2026-07-11.jsonl', text: JSON.stringify(reversed) + '\n' },
      { name: 'undo-journal-2026-07-10.jsonl', text: JSON.stringify(executed) + '\n' },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].status).toBe('reversed')
  })

  it('a hostile __proto__ jid cannot pollute prototypes (Map collapse)', () => {
    const evil = row({ jid: '__proto__' })
    const { rows } = parseJournalText([
      { name: 'undo-journal-2026-07-10.jsonl', text: JSON.stringify(evil) + '\n' },
    ])
    expect(rows).toHaveLength(1)
    expect(({} as Record<string, unknown>).status).toBeUndefined()
  })
})

describe('parseJournalText — corrupt-line tolerance (counted, never crash)', () => {
  it('skips bad JSON / non-objects / jid-less rows and counts them', () => {
    const text = [
      JSON.stringify(row()),
      '{ torn line …',
      '"just a string"',
      '[1, 2, 3]',
      JSON.stringify({ ts: '2026-07-10T10:00:00Z', status: 'executed' }), // no jid
      '', // blank lines are not corruption
      '   ',
      JSON.stringify(row({ jid: 'j-2' })),
    ].join('\n')
    const { rows, skipped } = parseJournalText([
      { name: 'undo-journal-2026-07-10.jsonl', text },
    ])
    expect(rows).toHaveLength(2)
    expect(skipped).toBe(4)
  })

  it('never throws on a malformed non-string ts', () => {
    const bad = row({ jid: 'j-odd', ts: 12345 as unknown as string })
    const { rows } = parseJournalText([
      {
        name: 'undo-journal-2026-07-10.jsonl',
        text: `${JSON.stringify(bad)}\n${JSON.stringify(row({ jid: 'j-2' }))}\n`,
      },
    ])
    expect(rows).toHaveLength(2)
  })
})

// ---------------------------------------------------------------------------
// undo-state computation
// ---------------------------------------------------------------------------

describe('undoState — computed from row fields only', () => {
  it('executed inside the window → active with hours left', () => {
    const s = undoState(row(), NOW) // ttl 2026-07-12T10:00Z − now 07-10T12:00Z = 46h
    expect(s.kind).toBe('active')
    expect(s.hoursLeft).toBe(46)
    expect(s.label).toBe('active — 46h left to undo')
  })

  it('executed past the ttl → expired', () => {
    const s = undoState(row({ ttl_expires_at: '2026-07-10T11:59:59Z' }), NOW)
    expect(s.kind).toBe('expired')
    expect(s.hoursLeft).toBeNull()
  })

  it('reversed → undone (with the reversal time)', () => {
    const s = undoState(
      row({ status: 'reversed', reversed_at: '2026-07-10T11:00:00Z' }),
      NOW
    )
    expect(s.kind).toBe('undone')
    expect(s.label).toContain('undone')
    expect(s.label).toContain('2026-07-10 11:00:00 UTC')
  })

  it('dead_letter → dead-letter (artifact stands)', () => {
    const s = undoState(row({ status: 'dead_letter' }), NOW)
    expect(s.kind).toBe('dead-letter')
    expect(s.label).toContain('artifact stands')
  })

  it('reversal_failed → undo-failed (manual cleanup)', () => {
    const s = undoState(row({ status: 'reversal_failed' }), NOW)
    expect(s.kind).toBe('undo-failed')
  })

  it('void → void', () => {
    expect(undoState(row({ status: 'void' }), NOW).kind).toBe('void')
  })

  it('executed but never enriched (crash row) → unconfirmed, honestly', () => {
    const s = undoState(row({ executed_at: null }), NOW)
    expect(s.kind).toBe('unconfirmed')
    expect(s.label).toContain('never confirmed')
  })

  it('unreadable ttl → unknown window, never a guessed countdown', () => {
    const s = undoState(row({ ttl_expires_at: 'not-a-time' }), NOW)
    expect(s.kind).toBe('unknown')
  })

  it('an unrecognized status renders as such, never coerced', () => {
    const s = undoState(row({ status: 'weird_future_state' }), NOW)
    expect(s.kind).toBe('unknown')
    expect(s.label).toContain('weird_future_state')
  })
})

// ---------------------------------------------------------------------------
// display helpers
// ---------------------------------------------------------------------------

describe('costLabel — mirrors action_language cost_of/cost_line (fail-closed)', () => {
  it('absent → unattributed', () => {
    expect(costLabel(undefined)).toBe('unattributed')
    expect(costLabel(null)).toBe('unattributed')
  })

  it('a full stamped dict renders usd + tokens + meter source', () => {
    expect(
      costLabel({ usd: 0.0123, tokens_in: 900, tokens_out: 120, source: 'lane-metered' })
    ).toBe('~$0.0123 — 900 in / 120 out tokens (lane-metered)')
  })

  it('subset dicts render what was stamped', () => {
    expect(costLabel({ usd: 1.5 })).toBe('~$1.5000')
    expect(costLabel({ tokens_in: 42, model: 'demo-model' })).toBe(
      '42 in tokens (demo-model)'
    )
  })

  it('a whitespace-exotic source collapses to one line — Python _compact parity', () => {
    // Mirror of action_language.cost_line's line-injection hardening: a
    // newline-bearing meter name must render identically on both surfaces
    // and can never split the rendered line.
    expect(costLabel({ usd: 0.01, source: 'lane\nmetered' })).toBe(
      '~$0.0100 (lane metered)'
    )
    expect(costLabel({ usd: 0.01, source: '  lane\t\n  metered  ' })).toBe(
      '~$0.0100 (lane metered)'
    )
  })

  it('anything malformed fails closed to unattributed — never a number we cannot trust', () => {
    expect(costLabel(0.13)).toBe('unattributed') // bare number: not a stamped dict
    expect(costLabel('$0.13')).toBe('unattributed') // prose: not a stamped dict
    expect(costLabel({ usd: -1 })).toBe('unattributed') // negative figure
    expect(costLabel({ usd: 1, surprise_key: 2 })).toBe('unattributed') // unknown key
    expect(costLabel({ model: 'demo-model' })).toBe('unattributed') // no numeric at all
    expect(costLabel({ usd: true })).toBe('unattributed') // boolean figure
    expect(costLabel({})).toBe('unattributed')
  })
})

describe('whyOf — mirrors action_language.why_of (never invented)', () => {
  it('prefers the journal why, then content.why, then payload.why', () => {
    expect(whyOf(row({ why: ' stamped rationale ' }))).toBe('stamped rationale')
    expect(whyOf(row({ content: { why: 'joined rationale' } }))).toBe('joined rationale')
    expect(whyOf(row({ payload: { why: 'note-leg rationale' } }))).toBe(
      'note-leg rationale'
    )
    expect(
      whyOf(row({ why: 'stamped', content: { why: 'joined' } }))
    ).toBe('stamped')
  })

  it('whitespace-only and absent count as no rationale', () => {
    expect(whyOf(row({ why: '   ' }))).toBeNull()
    expect(whyOf(row())).toBeNull()
  })
})

describe('utcLabel', () => {
  it('renders canonical journal timestamps as UTC', () => {
    expect(utcLabel('2026-07-10T10:00:00Z')).toBe('2026-07-10 10:00:00 UTC')
  })
  it('shows a malformed timestamp raw, and absence as —', () => {
    expect(utcLabel('yesterday-ish')).toBe('yesterday-ish')
    expect(utcLabel(undefined)).toBe('—')
  })
})

describe('shapeReceipt — the serializable view model', () => {
  it('maps a full row: phrase, why, cost, state, pid identifier', () => {
    const v = shapeReceipt(
      row({ why: 'the standup asked for it', cost: { usd: 0.02, source: 'lane-metered' } }),
      NOW
    )
    expect(v.action).toBe('updated a task') // kind-first (monday_task_update)
    expect(v.actionMapped).toBe(true)
    expect(v.why).toBe('the standup asked for it')
    expect(v.costLabel).toBe('~$0.0200 (lane-metered)')
    expect(v.state.kind).toBe('active')
    // The pid is an IDENTIFIER (cross-check against the binder's ·pid·
    // marker), never a typed undo selector — binder grammar takes an index.
    expect(v.pid).toBe('p-testburg-1')
    expect(v.demo).toBe(false)
  })

  it('widened kinds journal action_type null but phrase via kind', () => {
    const v = shapeReceipt(
      row({ kind: 'tier2_note', action_type: null }),
      NOW
    )
    expect(v.action).toBe('wrote a note')
    expect(v.actionMapped).toBe(true)
  })

  it('an unmapped slug renders visible words, flagged unmapped — never invented', () => {
    const v = shapeReceipt(
      row({ kind: 'future_kind_x', action_type: null }),
      NOW
    )
    expect(v.action).toBe('future kind x')
    expect(v.actionMapped).toBe(false)
  })

  it('demo:true rows carry the demo flag; why absent stays null', () => {
    const v = shapeReceipt(row({ demo: true }), NOW)
    expect(v.demo).toBe(true)
    expect(v.why).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// filesystem read (tmp fixtures)
// ---------------------------------------------------------------------------

describe('readJournal — read-only fs access', () => {
  let dir: string

  beforeEach(async () => {
    dir = await fs.mkdtemp(path.join(os.tmpdir(), 'testburg-undo-'))
    vi.stubEnv('CABINET_UNDO_DIR', dir)
  })

  afterEach(async () => {
    vi.unstubAllEnvs()
    await fs.rm(dir, { recursive: true, force: true })
  })

  it('missing dir → honest empty (missingDir), not an error', async () => {
    vi.stubEnv('CABINET_UNDO_DIR', path.join(dir, 'never-created'))
    const res = await readJournal()
    expect(res.missingDir).toBe(true)
    expect(res.rows).toEqual([])
    expect(res.error).toBeNull()
  })

  it('reads, collapses and counts across dated files', async () => {
    await fs.writeFile(
      path.join(dir, 'undo-journal-2026-07-09.jsonl'),
      `${JSON.stringify(row({ jid: 'j-a', ts: '2026-07-09T08:00:00Z' }))}\nbroken {\n`
    )
    await fs.writeFile(
      path.join(dir, 'undo-journal-2026-07-10.jsonl'),
      `${JSON.stringify(row({ jid: 'j-b' }))}\n`
    )
    // A non-journal sibling (fail-safe mirror) must be ignored entirely.
    await fs.writeFile(path.join(dir, 'frozen-kinds.jsonl'), '{"not":"a row"}\n')
    const res = await readJournal()
    expect(res.rows.map((r) => r.jid).sort()).toEqual(['j-a', 'j-b'])
    expect(res.skipped).toBe(1)
    expect(res.skippedFiles).toBe(0)
    expect(res.missingDir).toBe(false)
    expect(res.journalDir).toBe(dir)
  })

  it('skips a symlink that escapes the journal dir (never follows out, never counts)', async () => {
    const outside = await fs.mkdtemp(path.join(os.tmpdir(), 'testburg-outside-'))
    try {
      await fs.writeFile(
        path.join(outside, 'planted.jsonl'),
        `${JSON.stringify(row({ jid: 'j-planted' }))}\n`
      )
      await fs.symlink(
        path.join(outside, 'planted.jsonl'),
        path.join(dir, 'undo-journal-2026-07-08.jsonl')
      )
      await fs.writeFile(
        path.join(dir, 'undo-journal-2026-07-10.jsonl'),
        `${JSON.stringify(row({ jid: 'j-real' }))}\n`
      )
      const res = await readJournal()
      expect(res.rows.map((r) => r.jid)).toEqual(['j-real'])
      // Silent by design: a planted escape link is not journal content, so
      // it must not surface as an "unreadable journal file" either.
      expect(res.skippedFiles).toBe(0)
    } finally {
      await fs.rm(outside, { recursive: true, force: true })
    }
  })

  it('counts an unreadable journal file (skippedFiles) and keeps reading siblings', async () => {
    // A DIRECTORY named like a journal file: realpath resolves inside the
    // journal dir, then readFile fails EISDIR — a deterministic, root-proof
    // per-file read failure (a chmod-000 fixture is a no-op under root).
    await fs.mkdir(path.join(dir, 'undo-journal-2026-07-01.jsonl'))
    await fs.writeFile(
      path.join(dir, 'undo-journal-2026-07-10.jsonl'),
      `${JSON.stringify(row({ jid: 'j-readable' }))}\n`
    )
    const res = await readJournal()
    expect(res.skippedFiles).toBe(1)
    expect(res.rows.map((r) => r.jid)).toEqual(['j-readable'])
    expect(res.error).toBeNull()
  })

  it('zero rows + an unreadable file is NOT an honest empty (skippedFiles carries it)', async () => {
    await fs.mkdir(path.join(dir, 'undo-journal-2026-07-01.jsonl'))
    const res = await readJournal()
    expect(res.rows).toEqual([])
    expect(res.skippedFiles).toBe(1)
    expect(res.missingDir).toBe(false)
    expect(res.error).toBeNull()
  })
})
