/**
 * T3 UI-layer pure helpers — rail ring derivation, mailbox action-card
 * parsing, inspect-card tab coverage, cost formatting.
 *
 * PURE by doctrine: no clocks (callers pass nowMs — server routes only),
 * no I/O, no randomness. Everything here is unit-tested (ui-cards.test.ts)
 * and shared between the API routes (server) and components (client).
 */

// ── inspect-card coverage contract ──────────────────────────────────────────

/**
 * The WHAT/NOW/PROOF contract: every bound element carries all three tabs;
 * decorative elements answer WHAT-only ("carries no data"). This is the one
 * place the tab set derives from — the card component and the coverage test
 * both consume it, so the contract cannot silently fork.
 */
export function tabsFor(decorative: boolean | undefined): readonly string[] {
  return decorative ? (['WHAT'] as const) : (['WHAT', 'NOW', 'PROOF'] as const)
}

// ── portrait rail ───────────────────────────────────────────────────────────

/** Reserved salience palette, dual-coded (color + glyph). Red is NEVER a
 * ring state — red stays killswitch-only (reserved-salience law). */
export type RingState = 'green' | 'amber' | 'grey'

export interface RingInput {
  /** Seconds since the officer's activity `since` stamp; null = no reading. */
  freshS: number | null
  /** An expected-officer key exists (cabinet:officer:expected:<slug>). */
  expected: boolean
  /** Presence entry exists at all. */
  present: boolean
}

/** Activity fresher than this (seconds) = active-verified (green). */
export const RING_FRESH_S = 30 * 60
/** Talk animation plays only while the verb is fresher than this. */
export const TALK_FRESH_S = 5 * 60

/**
 * green = active-verified (fresh activity) · amber = expected but absent/
 * stale (blocked/waiting) · grey = unmeasured/stale. Dual-coded glyphs ride
 * along so color never carries alone.
 */
export function ringFor(input: RingInput): { ring: RingState; glyph: string } {
  if (input.freshS !== null && input.freshS >= 0 && input.freshS <= RING_FRESH_S) {
    return { ring: 'green', glyph: '✓' }
  }
  if (input.expected) return { ring: 'amber', glyph: '!' }
  return { ring: 'grey', glyph: '·' }
}

/**
 * Seconds between an ISO stamp and nowMs; null when unparseable, absent, or
 * FUTURE-DATED beyond tolerated skew.
 *
 * The `Math.max(0, …)` used to swallow arbitrary forward skew: a stamp an hour
 * ahead of this clock clamped to `0`, and `ringFor` reads 0 as maximally fresh,
 * so a skewed or stopped writer painted a PERMANENT green ✓ "active" ring on an
 * officer that had done nothing. The clamp survives only inside the tolerated
 * window, where it is rounding rather than invention — beyond it the age is not
 * knowable, which `null` says and a `0` does not.
 *
 * (nowMs is passed by the SERVER route — lib/world never reads a clock.)
 */
export const MAX_SKEW_S = 90

export function freshSeconds(sinceIso: string | undefined | null, nowMs: number): number | null {
  if (!sinceIso) return null
  const t = Date.parse(sinceIso)
  if (!Number.isFinite(t)) return null
  const secs = Math.round((nowMs - t) / 1000)
  if (secs < -MAX_SKEW_S) return null
  return Math.max(0, secs)
}

/**
 * Strict cost-viz: microdollars → `$X.XX` DOM-mono text; null/absent → the
 * honest grey em-dash (missing ≠ $0.00-as-fact). Numerals are never
 * pixel-font (typography law §9.2).
 */
export function formatMicro(micro: number | null | undefined): string {
  if (micro === null || micro === undefined || !Number.isFinite(micro)) return '—'
  return `$${(micro / 1_000_000).toFixed(2)}`
}

/** Roster ordering: cos (the Chair) first, then alphabetical; the 'unknown'
 * chronicle actor NEVER gets a slot (no attribution guess — ui-pack law). */
export function railOrder(slugs: string[]): string[] {
  return slugs
    .filter((s) => s !== 'unknown')
    .sort((a, b) => (a === 'cos' ? -1 : b === 'cos' ? 1 : a < b ? -1 : 1))
}

// ── mailbox: pending Captain decision queue (read-only view) ────────────────

/** One pending action card, parsed from a cabinet:action:* Redis value. */
export interface DecisionQueueItem {
  cid: string
  subject: string
  lane: string
  urgency: string
  confidence: number | null
  evidenceCount: number
  /** ISO stamp parsed from the key's trailing |<ts> segment; '' if absent. */
  ts: string
}

/**
 * Parse one pending action card. Key shape (binder wire, F0.5):
 *   cabinet:action:<actor>|<action>|<subject-slug>|<ISO-ts>
 * Value: JSON {cid, lane, subject, situation, steps, evidence, confidence,
 * urgency, ...}. Malformed rows return null (skipped, never invented).
 */
export function parseActionCard(key: string, raw: string): DecisionQueueItem | null {
  let v: Record<string, unknown>
  try {
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null) return null
    v = parsed as Record<string, unknown>
  } catch {
    return null
  }
  const seg = key.split('|')
  const ts = seg.length >= 4 ? seg[seg.length - 1] : ''
  const evidence = Array.isArray(v.evidence) ? v.evidence.length : 0
  return {
    cid: typeof v.cid === 'string' ? v.cid : '',
    subject: typeof v.subject === 'string' ? v.subject : '(no subject)',
    lane: typeof v.lane === 'string' ? v.lane : '?',
    urgency: typeof v.urgency === 'string' ? v.urgency : '?',
    confidence: typeof v.confidence === 'number' ? v.confidence : null,
    evidenceCount: evidence,
    ts: /^\d{4}-\d{2}-\d{2}T/.test(ts) ? ts : '',
  }
}

/** Newest first (ISO strings order lexically); undated cards sink last. */
export function sortDecisionQueue(items: DecisionQueueItem[]): DecisionQueueItem[] {
  return [...items].sort((a, b) => {
    if (!a.ts && !b.ts) return a.cid < b.cid ? -1 : 1
    if (!a.ts) return 1
    if (!b.ts) return -1
    return a.ts > b.ts ? -1 : a.ts < b.ts ? 1 : 0
  })
}
