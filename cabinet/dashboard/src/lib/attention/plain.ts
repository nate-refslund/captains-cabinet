/**
 * Plain-language renderer for the attention surfaces (PLAIN-LANGUAGE LAW,
 * captain-decisions 2026-07-10 Ruling B).
 *
 * ALL tables come from plain.json, which is GENERATED from
 * framework/attention/plain.py (`python3.12 -m framework.attention.plain
 * --export`) — one source of truth; a pytest drift guard pins the committed
 * JSON to the Python tables, and the vitest jargon tooth lints every string
 * this module can produce.
 *
 * Technical truth (raw kinds, refs, the copyable reply line) is DISCLOSED
 * behind the card's Details block, never deleted (SEC-4 exact-render law).
 */
import { createHash } from 'node:crypto'
import PLAIN from './plain.json'
import type { QueueRow } from './queue'

export type Verb = 'approve' | 'no' | 'later'
export const VERBS: readonly Verb[] = ['approve', 'no', 'later'] as const

type Tables = {
  banned: Record<string, string>
  kind_names: Record<string, string>
  kind_name_default: string
  state_names: Record<string, string>
  state_name_default: string
  decided_states: string[]
  risk_sentences: Record<string, string>
  risk_default: string
  risk_default_ceiling: string
  door_buttons: Record<string, Record<string, string>>
  ritual_kinds: string[]
  messages: Record<string, string>
  results: Record<string, string>
  consequence_templates: Record<string, string>
  undo_templates: Record<string, string>
  copy: Record<string, string>
}

export const TABLES = PLAIN as unknown as Tables
export const COPY = TABLES.copy
export const MESSAGES = TABLES.messages

/** The card, in plain words — everything the default (non-Details) face shows. */
export interface PlainCard {
  headline: string
  /** One supporting sentence: kind + risk + clocks. */
  sentence: string
  kindName: string
  stateName: string
  risk: string
  waiting: string
  buttons: { approve: string; later: string; no: string }
  /** Ritual sign-offs never get a dashboard approve button. */
  ritual: boolean
  decided: boolean
  /** Buttons only render when the row carries a decidable identity. */
  decidable: boolean
  revision: string
}

export function kindName(kind: string | null | undefined): string {
  return TABLES.kind_names[kind ?? ''] ?? TABLES.kind_name_default
}

export function stateName(state: string | null | undefined): string {
  return TABLES.state_names[state ?? ''] ?? TABLES.state_name_default
}

export function riskSentence(row: QueueRow): string {
  const raw = row.blast_worst_case
  if (raw && TABLES.risk_sentences[raw]) return TABLES.risk_sentences[raw]
  if (row.blast?.class === 'ceiling') return TABLES.risk_default_ceiling
  return TABLES.risk_default
}

export function agePlain(ageH: number | null): string {
  if (ageH === null || ageH < 0) return ''
  if (ageH < 1) return 'waiting under an hour'
  if (ageH < 48) {
    const n = Math.round(ageH)
    return `waiting ${n} hour${n === 1 ? '' : 's'}`
  }
  return `waiting ${Math.round(ageH / 24)} days`
}

export function duePlain(iso: string | null, nowMs = Date.now()): string {
  if (!iso) return ''
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) return ''
  const hours = (t - nowMs) / 3_600_000
  if (hours < 0) return 'overdue'
  if (hours < 48) {
    const n = Math.max(1, Math.round(hours))
    return `due in ${n} hour${n === 1 ? '' : 's'}`
  }
  return `due ${iso.slice(0, 10)}`
}

/** Content fingerprint — MUST match framework.attention.verdicts.revision_of
 * (golden-vector pinned in both test suites). */
export function revisionOf(row: {
  pid: string | null
  state: string | null
  what: string | null
  deadline_iso: string | null
}): string {
  const parts = [row.pid, row.state, row.what, row.deadline_iso].map(
    (v) => v ?? ''
  )
  return createHash('sha256').update(parts.join('\n'), 'utf8').digest('hex').slice(0, 16)
}

export function doorButtons(kind: string | null | undefined): {
  approve: string
  later: string
  no: string
} {
  const t = TABLES.door_buttons[kind ?? ''] ?? TABLES.door_buttons['']
  return {
    approve: t.approve ?? '✓ Approve',
    later: t.later ?? 'Later',
    no: t.no ?? '✗ No',
  }
}

function capitalize(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s
}

/** The plain card — big-type headline + ONE supporting sentence. */
export function plainCard(row: QueueRow, nowMs = Date.now()): PlainCard {
  const what = (row.what ?? '').trim() || COPY.no_title
  const kn = kindName(row.kind)
  const risk = riskSentence(row)
  const clocks = [agePlain(row.age_h), duePlain(row.deadline_iso, nowMs)]
    .filter(Boolean)
    .join(' — ')
  const lane = (row.lane ?? '').trim()
  const head = lane ? `${kn} — ${lane}` : kn
  const sentence = [`${head}.`, risk, clocks ? `${capitalize(clocks)}.` : '']
    .filter(Boolean)
    .join(' ')
  const decided = TABLES.decided_states.includes(row.state ?? '')
  const ritual = TABLES.ritual_kinds.includes(row.kind ?? '')
  return {
    headline: what,
    sentence,
    kindName: kn,
    stateName: stateName(row.state),
    risk,
    waiting: clocks,
    buttons: doorButtons(row.kind),
    ritual,
    decided,
    decidable: Boolean(row.pid) && Boolean(row.one_tap) && !decided,
    revision: revisionOf(row),
  }
}

function fill(template: string, row: QueueRow): string {
  const what = ((row.what ?? '').trim() || COPY.no_title).replace(/\.$/, '') + '.'
  return template.replace('{risk}', riskSentence(row)).replace('{what}', what)
}

/** Consequence sentence for the two-step confirm (deck steal #3). */
export function consequenceFor(row: QueueRow, verb: Verb): string {
  const kind = row.kind ?? ''
  const tpl =
    TABLES.consequence_templates[`${verb}:${kind}`] ??
    TABLES.consequence_templates[verb] ??
    TABLES.consequence_templates.later
  return fill(tpl, row)
}

export function undoFor(row: QueueRow, verb: Verb): string {
  if (verb === 'approve' && row.blast?.class === 'ceiling') {
    return TABLES.undo_templates['approve:ceiling']
  }
  const tpl = TABLES.undo_templates[verb] ?? TABLES.undo_templates.later
  return fill(tpl, row)
}

/** Jargon linter (vitest tooth) — case-insensitive word-boundary matches of
 * the banned table. Mirrors framework.attention.plain.lint. */
export function lintJargon(text: string): { term: string; index: number }[] {
  const out: { term: string; index: number }[] = []
  for (const term of Object.keys(TABLES.banned)) {
    const rx = new RegExp(
      `(?<![\\w-])${term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![\\w-])`,
      'gi'
    )
    for (const m of text.matchAll(rx)) {
      out.push({ term, index: m.index ?? 0 })
    }
  }
  return out.sort((a, b) => a.index - b.index || a.term.localeCompare(b.term))
}
