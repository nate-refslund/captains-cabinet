/**
 * /receipts static contracts (grep-ratchet style, same as
 * components/world/ui-layer.test.ts):
 *
 *  A. READ-ONLY BY CONSTRUCTION — the page, the row component and the
 *     receipts action never grow buttons, forms, client JS, mutation
 *     endpoints or fs/Redis writes (decision-queue-card doctrine: render
 *     truth + deep-link to the Telegram binder, never actuate).
 *  B. HONESTY STRINGS — the honest-empty state, the counted-corruption
 *     note, the "showing latest N" cap note, the DEMO badge and the
 *     undo-note copy are load-bearing and pinned.
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

const DASH = path.resolve(__dirname, '..', '..', '..')
const src = (...rel: string[]) =>
  fs.readFileSync(path.join(DASH, 'src', ...rel), 'utf8')

const PAGE = ['app', '(authenticated)', 'receipts', 'page.tsx']
const ROW = ['components', 'receipts', 'receipt-row.tsx']
const ACTION = ['actions', 'receipts.ts']
const JOURNAL = ['components', 'receipts', 'journal.ts']

const FS_WRITE_VERBS =
  /\b(writeFile|writeFileSync|appendFile|appendFileSync|unlink|unlinkSync|rm|rmSync|rmdir|rmdirSync|mkdir|mkdirSync|rename|renameSync|chmod|chmodSync|symlink|symlinkSync|truncate|truncateSync|cp|cpSync|copyFile|copyFileSync|writev|createWriteStream)\s*\(/

describe('A. /receipts is read-only by construction', () => {
  it('page + row: server-rendered, no buttons, no forms, no client JS', () => {
    for (const [name, rel] of [
      ['receipts page', PAGE],
      ['receipt row', ROW],
    ] as const) {
      const text = src(...rel)
      expect(text, name).not.toMatch(/['"]use client['"]/)
      expect(text, name).not.toMatch(/<button/i)
      expect(text, name).not.toMatch(/<form/i)
      expect(text, name).not.toMatch(/onClick/)
      expect(text, name).not.toMatch(/dangerouslySetInnerHTML/)
      expect(text, name).not.toMatch(/fetch\(/)
    }
  })

  it('the row component imports no actions (render-only props in)', () => {
    expect(src(...ROW)).not.toMatch(/@\/actions\//)
  })

  it('actions/receipts.ts exports exactly one read (listReceipts), no writes', () => {
    const text = src(...ACTION)
    expect(text).toMatch(/['"]use server['"]/)
    const fnExports = text.match(/export\s+(?:async\s+)?function\s+(\w+)/g) ?? []
    expect(fnExports).toEqual(['export async function listReceipts'])
    expect(text).not.toMatch(FS_WRITE_VERBS)
    expect(text).not.toMatch(/@\/lib\/redis|ioredis/)
    expect(text).not.toMatch(/child_process|execFile|spawn/)
    expect(text).not.toMatch(/revalidatePath/)
  })

  it('journal.ts touches the filesystem read-only, no Redis, no subprocess', () => {
    const text = src(...JOURNAL)
    expect(text).not.toMatch(FS_WRITE_VERBS)
    expect(text).not.toMatch(/@\/lib\/redis|ioredis/)
    expect(text).not.toMatch(/child_process|execFile|spawn/)
  })
})

describe('B. honesty strings are load-bearing', () => {
  it('the page carries the honest-empty, cap and corruption notes', () => {
    const text = src(...PAGE)
    expect(text).toMatch(/no receipts yet — the journal is honestly empty/)
    expect(text).toMatch(/showing latest/)
    expect(text).toMatch(/skipped/)
    expect(text).toMatch(/force-dynamic/)
  })

  it('unreadable journal files are said out loud and suppress "honestly empty"', () => {
    const text = src(...PAGE)
    // The counted note for unreadable files (mirror of the corrupt-line note).
    expect(text).toMatch(/unreadable/)
    expect(text).toMatch(/never guessed at/)
    // The honest-empty copy is GATED on zero unreadable files — zero rows
    // plus an unreadable file on disk must never render as an empty journal.
    expect(text).toMatch(/receipts\.length === 0 && skippedFiles === 0/)
  })

  it('the row carries the DEMO badge and the binder undo NOTE (registered grammar only)', () => {
    const text = src(...ROW)
    expect(text).toMatch(/DEMO/)
    expect(text).toMatch(/seeded demo receipt/)
    expect(text).toMatch(/Telegram binder/)
    // The NOTE teaches ONLY the grammar binder_wire registers: a bare "undo"
    // reply to the act's ·pid·-marked receipt message, or "undo <n>" against
    // a digest line (numeric index — binder_wire._UNDO_RE). A typed pid is
    // NOT a selector (it parses as free-text why), so the pid renders as an
    // identifier only.
    expect(text).toMatch(/to this act&apos;s receipt\s+message/)
    expect(text).toMatch(/undo &lt;n&gt;/)
    expect(text).toMatch(/this row is \{receipt\.pid\}/)
    // Ratchet: never re-teach "undo <pid>" as a typed command — with 0 or 2+
    // open windows the binder silently refuses it, and with exactly 1 the
    // single-open fallback can reverse a DIFFERENT act than the pid named.
    expect(text).not.toMatch(/undo\s*\{receipt\./)
    expect(text).toMatch(/never\s+acts on them/)
  })

  it('DEMO rows get the honest no-op note instead of the undo grammar', () => {
    const text = src(...ROW)
    // Demo rows (demo: true, inverse op none by contract) have no binder
    // receipt message to reply to — the note must say so instead of teaching
    // a verb that cannot bind (demo-kit cross-area suggestion, Wave-B
    // integration).
    expect(text).toMatch(/receipt\.demo \? \(/)
    expect(text).toMatch(/nothing real to reverse/)
    expect(text).toMatch(/reply-to-undo works on real\s+receipts only/)
  })
})
