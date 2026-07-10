/**
 * journal.ts — READ-ONLY access to the undo journal for the /receipts page.
 *
 * Mirrors the journal-store contract of `framework/frontdoor/action_undo.py`
 * 1:1 (that module OWNS the journal; this one only renders it):
 *   - dir: `CABINET_UNDO_DIR` overrides; default is the durable per-user
 *     location `~/Library/Application Support/cabinet/undo` (`_undo_dir`).
 *   - files: `undo-journal-*.jsonl`, append-only; a write-ahead row and its
 *     post-mutation enrichment share a `jid`, so reads collapse by jid
 *     last-write-wins after a STABLE sort by `ts` (`_read_journal`).
 *   - symlink safety: a file planted in the dir whose realpath escapes the
 *     dir is skipped, never followed (`_safe_journal_files`).
 *
 * Honesty doctrine (perfect-cabinet Wave B):
 *   - corrupt lines are skipped AND COUNTED — the page says how many, and
 *     never crashes on a torn line;
 *   - unreadable journal FILES are likewise skipped AND COUNTED
 *     (`skippedFiles`) — the backend tolerates per-file OSErrors silently,
 *     but a render surface that hides an unreadable file would fake an empty
 *     journal, so this mirror deliberately counts what the backend only
 *     tolerates (symlink-escape skips stay silent by design: they are
 *     planted files, not journal content);
 *   - a missing dir is an honest empty state, never invented rows;
 *   - `prestate` / `created` / `inverse` are deliberately NOT surfaced —
 *     they can carry captured file contents that never leave the box.
 *
 * This module performs NO writes, opens NO Redis connection (the JSONL is
 * the durable truth; the Redis pointer is only an index), and runs NO
 * subprocesses. Server-side only (node:fs) — import it from server
 * components / server actions exclusively.
 */
import { promises as fs } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { phraseFor } from './action-language'

// ---------------------------------------------------------------------------
// Row + result shapes
// ---------------------------------------------------------------------------

/** One collapsed undo-journal row (the fields /receipts consumes). */
export interface UndoJournalRow {
  jid: string
  ts?: string
  pid?: string
  step?: number
  kind?: string
  action_type?: string | null
  lane?: string | null
  subject?: string
  status?: string
  executed_at?: string | null
  reversed_at?: string | null
  ttl_expires_at?: string | null
  /** Receipt grammar (Wave B): the plain-language reason, when captured. */
  why?: string | null
  /** Receipt grammar (Wave B): the attributed cost, when captured. */
  cost?: unknown
  /** Seeded demo rows are explicitly labeled — the page badges them. */
  demo?: boolean
  [key: string]: unknown
}

export interface ParsedJournal {
  rows: UndoJournalRow[]
  /** Non-empty lines that failed to parse (bad JSON / not an object / no jid). */
  skipped: number
}

export interface JournalReadResult extends ParsedJournal {
  /** True when the journal dir does not exist yet — an honest empty, not an error. */
  missingDir: boolean
  /** Loud read failure (dir exists but is unreadable) — the page says so. */
  error: string | null
  /** The resolved journal dir (proof line on the page). */
  journalDir: string
  /** Journal files that exist but could not be read (perms, vanished mid-read)
   * — counted so the page never renders "honestly empty" over hidden rows.
   * Symlink-escape skips are NOT counted (silent by design). */
  skippedFiles: number
}

// ---------------------------------------------------------------------------
// Dir + file resolution (mirrors _undo_dir / _safe_journal_files)
// ---------------------------------------------------------------------------

/** The undo-journal directory — CABINET_UNDO_DIR override, else the durable
 * per-user default. Resolved per call so tests and long-lived servers may
 * set the env after module load (same doctrine as cabinet-root.ts).
 * DOCUMENTED MIRROR DIVERGENCE: an empty CABINET_UNDO_DIR falls through to
 * the default here (`||`), while Python's os.environ.get would honor the
 * empty string (and then fail on a "" dir) — deliberate: a display surface
 * should never treat "" as a real directory. Pinned by the journal.test.ts
 * "defaults to the durable per-user location" case. */
export function undoDir(): string {
  return (
    process.env.CABINET_UNDO_DIR ||
    path.join(os.homedir(), 'Library', 'Application Support', 'cabinet', 'undo')
  )
}

/** Fixed journal-file pattern — no request input ever reaches a path. */
export function isJournalFileName(name: string): boolean {
  return name.startsWith('undo-journal-') && name.endsWith('.jsonl')
}

// ---------------------------------------------------------------------------
// Pure parsing (unit-testable, no I/O)
// ---------------------------------------------------------------------------

/**
 * Parse journal file contents into collapsed rows.
 *
 * Mirrors `_read_journal`: skip blank lines; skip (and here COUNT) lines that
 * are not valid JSON objects carrying a `jid`; stable-sort every row by `ts`
 * (string compare, missing ts sorts first — equal-ts rows keep append order
 * so an enrichment/reversal line still wins over its write-ahead line); then
 * collapse by jid last-write-wins into first-seen-jid order.
 *
 * Uses a Map for the collapse — a hostile jid like `__proto__` can never
 * pollute a prototype.
 */
export function parseJournalText(
  files: Array<{ name: string; text: string }>
): ParsedJournal {
  const raw: UndoJournalRow[] = []
  let skipped = 0
  for (const f of files) {
    for (const line of f.text.split('\n')) {
      const trimmed = line.trim()
      if (!trimmed) continue
      let parsed: unknown
      try {
        parsed = JSON.parse(trimmed)
      } catch {
        skipped += 1
        continue
      }
      if (
        typeof parsed !== 'object' ||
        parsed === null ||
        Array.isArray(parsed) ||
        !('jid' in parsed)
      ) {
        skipped += 1
        continue
      }
      raw.push(parsed as UndoJournalRow)
    }
  }
  // Stable sort by ts (Array.prototype.sort is stable); String() guards a
  // malformed non-string ts — the UI must never crash on a bad row.
  raw.sort((a, b) => {
    const ta = String(a.ts ?? '')
    const tb = String(b.ts ?? '')
    return ta < tb ? -1 : ta > tb ? 1 : 0
  })
  const collapsed = new Map<string, UndoJournalRow>()
  for (const row of raw) collapsed.set(String(row.jid), row)
  return { rows: [...collapsed.values()], skipped }
}

// ---------------------------------------------------------------------------
// Undo-state computation (pure)
// ---------------------------------------------------------------------------

export type UndoStateKind =
  | 'active'
  | 'expired'
  | 'undone'
  | 'dead-letter'
  | 'undo-failed'
  | 'void'
  | 'unconfirmed'
  | 'unknown'

export interface UndoState {
  kind: UndoStateKind
  label: string
  /** Hours left in the undo window — only set while `kind === 'active'`. */
  hoursLeft: number | null
}

function parseTsMs(ts: unknown): number | null {
  if (typeof ts !== 'string' || !ts) return null
  const ms = Date.parse(ts)
  return Number.isNaN(ms) ? null : ms
}

/**
 * The honest undo state of one collapsed row, computed only from row fields
 * (`status`, `executed_at`, `ttl_expires_at`, `reversed_at`) against `nowMs`.
 * Statuses mirror action_undo's `_ROW_STATUSES`; anything else renders as an
 * explicit unknown — never coerced into a state the backend didn't record.
 */
export function undoState(row: UndoJournalRow, nowMs: number): UndoState {
  const status = row.status
  if (status === 'dead_letter') {
    return {
      kind: 'dead-letter',
      label: 'dead-letter — reverse refused; artifact stands for manual review',
      hoursLeft: null,
    }
  }
  if (status === 'reversed') {
    const at = typeof row.reversed_at === 'string' ? ` at ${utcLabel(row.reversed_at)}` : ''
    return { kind: 'undone', label: `undone${at}`, hoursLeft: null }
  }
  if (status === 'reversal_failed') {
    return {
      kind: 'undo-failed',
      label: 'undo failed — manual cleanup required',
      hoursLeft: null,
    }
  }
  if (status === 'void') {
    return { kind: 'void', label: 'void — nothing executed', hoursLeft: null }
  }
  if (status === 'executed') {
    if (!row.executed_at) {
      return {
        kind: 'unconfirmed',
        label: 'write-ahead only — execution never confirmed (reconciler will confirm or void)',
        hoursLeft: null,
      }
    }
    const ttlMs = parseTsMs(row.ttl_expires_at)
    if (ttlMs === null) {
      return {
        kind: 'unknown',
        label: 'undo window unknown — row carries no readable ttl',
        hoursLeft: null,
      }
    }
    if (nowMs <= ttlMs) {
      const hoursLeft = Math.round(((ttlMs - nowMs) / 3_600_000) * 10) / 10
      return {
        kind: 'active',
        label: `active — ${hoursLeft}h left to undo`,
        hoursLeft,
      }
    }
    return { kind: 'expired', label: 'expired — undo window closed', hoursLeft: null }
  }
  return {
    kind: 'unknown',
    label: `unrecognized status ${JSON.stringify(status ?? null)}`,
    hoursLeft: null,
  }
}

// ---------------------------------------------------------------------------
// Display helpers (pure)
// ---------------------------------------------------------------------------

const CANONICAL_TS = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/

/** Journal timestamps are already UTC (`%Y-%m-%dT%H:%M:%SZ`) — render them
 * as such; a malformed value is shown raw, never silently reformatted. */
export function utcLabel(ts: unknown): string {
  if (typeof ts !== 'string' || !ts) return '—'
  if (CANONICAL_TS.test(ts)) return `${ts.slice(0, 10)} ${ts.slice(11, 19)} UTC`
  return ts
}

/**
 * WHY — mirror of `action_language.why_of`: the row's rationale or null,
 * NEVER invented. Precedence: the additive journal `why` field, then an
 * orchestrator-joined `content.why`, then the executed `payload.why`.
 * Whitespace-only counts as absent.
 */
export function whyOf(row: UndoJournalRow): string | null {
  const candidates: unknown[] = [row.why]
  for (const key of ['content', 'payload'] as const) {
    const src = row[key]
    if (typeof src === 'object' && src !== null && !Array.isArray(src)) {
      candidates.push((src as Record<string, unknown>).why)
    }
  }
  for (const cand of candidates) {
    if (typeof cand === 'string' && cand.trim()) return cand.trim()
  }
  return null
}

// COST — mirror of `action_language._valid_cost` / `cost_line`: a cost is
// attributed ONLY from a write-time-stamped dict of shape
// {usd?, tokens_in?, tokens_out?, model?, source?} with ≥1 non-negative
// numeric. ANY malformation fails closed to "unattributed" — a number we
// cannot trust is never rendered.
const COST_NUMERIC_KEYS = ['usd', 'tokens_in', 'tokens_out'] as const
const COST_KEYS = new Set<string>([...COST_NUMERIC_KEYS, 'model', 'source'])

function validCost(cost: unknown): Record<string, unknown> | null {
  if (typeof cost !== 'object' || cost === null || Array.isArray(cost)) return null
  const entries = Object.entries(cost as Record<string, unknown>)
  if (entries.length === 0) return null
  if (entries.some(([k]) => !COST_KEYS.has(k))) return null
  let hasNumeric = false
  for (const k of COST_NUMERIC_KEYS) {
    if (k in (cost as Record<string, unknown>)) {
      const v = (cost as Record<string, unknown>)[k]
      if (typeof v !== 'number' || !Number.isFinite(v) || v < 0) return null
      hasNumeric = true
    }
  }
  for (const k of ['model', 'source'] as const) {
    const v = (cost as Record<string, unknown>)[k]
    if (k in (cost as Record<string, unknown>) && typeof v !== 'string') return null
  }
  return hasNumeric ? { ...(cost as Record<string, unknown>) } : null
}

/** The attributed cost text (mirrors `action_language.cost_line` sans the
 * "cost: " prefix the row renders itself), or "unattributed". */
export function costLabel(cost: unknown): string {
  const c = validCost(cost)
  if (c === null) return 'unattributed'
  const bits: string[] = []
  if (typeof c.usd === 'number') bits.push(`~$${c.usd.toFixed(4)}`)
  const tokens: string[] = []
  if (typeof c.tokens_in === 'number') tokens.push(`${Math.trunc(c.tokens_in)} in`)
  if (typeof c.tokens_out === 'number') tokens.push(`${Math.trunc(c.tokens_out)} out`)
  if (tokens.length) bits.push(`${tokens.join(' / ')} tokens`)
  let label = bits.join(' — ')
  const src = c.source || c.model
  if (typeof src === 'string' && src) {
    // Mirror of the Python `_compact` hardening (action_language.cost_line):
    // marker-stripped AND whitespace-collapsed to one line before the clip,
    // so a newline-bearing source/model string renders identically on both
    // surfaces and can never split the rendered line.
    label += ` (${src.replace(/·/g, '').replace(/\s+/g, ' ').trim().slice(0, 60)})`
  }
  return label
}

// ---------------------------------------------------------------------------
// Shaped view model for the page (serializable — crosses the action boundary)
// ---------------------------------------------------------------------------

export interface ReceiptView {
  jid: string
  timeLabel: string
  lane: string
  /** Plain-language action from the shared phrase map (or the raw slug). */
  action: string
  /** False when the phrase map has no entry — the raw slug is shown instead. */
  actionMapped: boolean
  subject: string
  why: string | null
  costLabel: string
  state: UndoState
  /** The act's pid (falls back to jid) — an IDENTIFIER for cross-checking
   * against the ·pid· marker on the binder's receipt message, never a typed
   * selector: binder_wire._UNDO_RE takes only a numeric digest index, and a
   * typed pid parses as free-text "why". */
  pid: string
  demo: boolean
}

export function shapeReceipt(row: UndoJournalRow, nowMs: number): ReceiptView {
  const phrase = phraseFor(row.action_type, row.kind)
  const why = whyOf(row)
  return {
    jid: String(row.jid),
    timeLabel: utcLabel(row.ts),
    lane: typeof row.lane === 'string' && row.lane ? row.lane : '—',
    action: phrase.text,
    actionMapped: phrase.mapped,
    subject: typeof row.subject === 'string' ? row.subject : '',
    why,
    costLabel: costLabel(row.cost),
    state: undoState(row, nowMs),
    pid: String(row.pid || row.jid),
    demo: row.demo === true,
  }
}

// ---------------------------------------------------------------------------
// Filesystem read (async, read-only)
// ---------------------------------------------------------------------------

/**
 * Read + collapse the whole journal. Missing dir → honest empty. A dir that
 * exists but cannot be read → loud `error`. Per-file read failures (perms,
 * vanished file) skip that file AND count it in `skippedFiles` — the backend
 * (`_read_journal`) tolerates per-file OSErrors silently, but this surface
 * must never render "honestly empty" while unreadable rows sit on disk.
 * Symlink-escape skips stay silent and unfollowed (planted files are not
 * journal content).
 */
export async function readJournal(): Promise<JournalReadResult> {
  const dir = undoDir()
  const empty: JournalReadResult = {
    rows: [],
    skipped: 0,
    missingDir: false,
    error: null,
    journalDir: dir,
    skippedFiles: 0,
  }

  let names: string[]
  try {
    names = await fs.readdir(dir)
  } catch (err) {
    const code = (err as NodeJS.ErrnoException).code
    if (code === 'ENOENT' || code === 'ENOTDIR') return { ...empty, missingDir: true }
    return {
      ...empty,
      error: err instanceof Error ? err.message : 'journal dir unreadable',
    }
  }

  let realBase: string
  try {
    realBase = await fs.realpath(dir)
  } catch (err) {
    return {
      ...empty,
      error: err instanceof Error ? err.message : 'journal dir unresolvable',
    }
  }

  let skippedFiles = 0
  const files: Array<{ name: string; text: string }> = []
  for (const name of names.filter(isJournalFileName).sort()) {
    const full = path.join(dir, name)
    let real: string
    try {
      real = await fs.realpath(full)
    } catch {
      skippedFiles += 1 // vanished/unresolvable — unreadable, counted
      continue
    }
    // Never follow a symlink out of the journal dir (_safe_journal_files) —
    // a deliberate, SILENT skip: a planted link is not journal content.
    if (real !== realBase && !real.startsWith(realBase + path.sep)) continue
    try {
      files.push({ name, text: await fs.readFile(full, 'utf8') })
    } catch {
      skippedFiles += 1 // exists but unreadable (perms, EISDIR) — counted
    }
  }

  return { ...empty, ...parseJournalText(files), skippedFiles }
}
