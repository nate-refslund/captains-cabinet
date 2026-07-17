/**
 * read.ts — READ-ONLY access to the evidence store for the /evidence page
 * (whole-cabinet evidence program, Phase 3: humans judge first).
 *
 * Fail-closed display law (design §3 Phase 3): every trial served ANYWHERE
 * passes verification first or renders explicitly UNVERIFIED — never
 * silently unverified, never hidden. This module therefore:
 *   - never re-implements hash-chain verification in TypeScript — it shells
 *     to the canonical Python verifier (`python3.12 -m framework.evidence
 *     --store <dir> verify`, the side-effect-light read: verify_store
 *     re-derives every hash + HMAC signature from raw bytes) with the
 *     bridge.ts spawn discipline CLONED, not imported (bridge.ts is
 *     germline): fixed argv, shell:false, 30s SIGKILL, 2MB stdout cap,
 *     stderr never surfaced to the browser;
 *   - snapshots trial bytes BEFORE the verify pass, so served rows are a
 *     prefix of what the verifier signed off on (the ledger is append-only;
 *     a snapshot that turns out LONGER than the verified count is
 *     rollback-shaped and renders UNVERIFIED);
 *   - serves content only for trials the verifier passed; failing trials
 *     become explicit UNVERIFIED stub rows (reason = bounded verifier error
 *     codes, zero content) and a verifier that did not run turns EVERY
 *     enumerated trial into an UNVERIFIED stub.
 *
 * Store root: FIXED server-side to <cabinet root>/instance/evidence/v1 —
 * the same store the officer doorway (cabinet/scripts/evidence-read.sh)
 * pins. Deliberately NO env override (CABINET_EVIDENCE_DIR is the Python
 * default's business): honoring one here could verify one store while
 * rendering another. No caller input can ever reach a path or the spawn
 * argv — filters are validated against closed vocabularies BEFORE any I/O
 * and compared in memory against parsed event fields only.
 *
 * Honesty doctrine (receipts journal.ts, mirrored): corrupt event lines are
 * counted never crashed on; unreadable/oversized event files are counted in
 * `skippedFiles` so "honestly empty" never renders over hidden rows; a
 * missing store dir is an honest empty, not an error; symlink escapes are
 * skipped, never followed (the Python verifier independently flags those
 * trials as failing). Raw `detail` payloads, hashes and signatures are
 * deliberately NOT surfaced — this view extracts only the enum/identifier
 * fields it needs (phase, status, ts, actor, component name, detail.source,
 * detail.result_code); on a verified trial all of these are
 * charset-constrained by the verifier's shape checks.
 *
 * NO WRITES of any kind. No label verb — Phase 3's one designed write is
 * the Captain-token-gated CLI harness, never this page. Server-side only
 * (node:fs + node:child_process): import from server components / server
 * actions exclusively.
 */
import { spawn } from 'node:child_process'
import { promises as fs } from 'node:fs'
import path from 'node:path'

import { cabinetPath, cabinetRoot } from '@/lib/cabinet-root'

// ---------------------------------------------------------------------------
// Constants — lockstep mirrors of framework/evidence/verifier.py
// ---------------------------------------------------------------------------

/** Render cap per section — the page says "showing latest N of M". */
export const EVIDENCE_SHOW_CAP = 100

/** Bytes we will read per trial ledger. The recorder caps trials at 500
 * events (MAX_TRIAL_EVENTS), so a ledger anywhere near this is anomalous —
 * counted as an unreadable file, never half-parsed. */
const MAX_EVENTS_FILE_BYTES = 5 * 1024 * 1024

const VERIFY_TIMEOUT_MS = 30_000
const MAX_VERIFY_OUTPUT_BYTES = 2 * 1024 * 1024

/** Mirror of verifier.TRIAL_ID_RE — also the actor-id / component-name /
 * doorway-token charset. Anything else in the trials dir is not a trial. */
const TRIAL_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/

/** Mirror of verifier.STATUSES (incl. the v1.1 absence vocabulary).
 * LOCKSTEP: framework/evidence/verifier.py STATUSES is the source of truth;
 * this closed set exists only to refuse out-of-vocabulary filter values. */
export const EVIDENCE_STATUSES = new Set([
  'started', 'allowed', 'proposed', 'succeeded', 'refused', 'failed',
  'retried', 'interrupted', 'recovered', 'verified', 'unverified',
  'undone', 'duplicate', 'paused', 'revoked', 'purged', 'useful',
  'not_useful', 'corrected', 'diagnostic',
  'missed', 'skipped', 'expired',
])

/** Mirror of verifier.ACTOR_KINDS. */
const ACTOR_KINDS = new Set(['captain', 'system', 'surface', 'officer', 'verifier'])

/** The judgment phases — an event in one of these phases is somebody
 * vouching for (or against) the trial, as opposed to doing the work. */
const JUDGMENT_PHASES = new Set(['verification', 'outcome', 'feedback'])

// ---------------------------------------------------------------------------
// Shapes
// ---------------------------------------------------------------------------

/** Evidence-basis classes (design §2 / classification.py grounding):
 *  - human-verified: a captain-attributed verification/outcome/feedback
 *    event, or a recorded human verdict (detail.source == 'verdict_human');
 *  - independently-recomputed: a verdict minted by a judge independent of
 *    the producer (detail.source == 'verdict_judge');
 *  - self-asserted: a verification/outcome event where the producer/system
 *    vouches for itself (no independent source);
 *  - persistence-only: ABSENCE-derived — the trial verifies (bytes are
 *    intact) but nothing beyond persistence was ever confirmed (no
 *    verification/outcome event beside the execution, or only reconciler
 *    ttl_ok persistence confirmations);
 *  - unknown: the trial verified but its bytes were not captured in this
 *    read — an explicit badge, never a coerced guess.
 * HONESTY CAVEAT (rendered by the page): all of these derive from stored,
 * producer-asserted fields (classification.py registers actor and every
 * detail key as producer_asserted) — a stored actor.kind == 'captain' is an
 * assertion; authenticated-captain provenance comes from the token-gated
 * label path plus external anchoring, not from this projection. */
export type EvidenceBasis =
  | 'human-verified'
  | 'independently-recomputed'
  | 'self-asserted'
  | 'persistence-only'
  | 'unknown'

/** The only per-event fields this surface ever extracts. */
export interface EvidenceEventLite {
  phase: string
  status: string
  ts: string
  actorKind: string
  actorId: string
  component: string
  /** detail.source when it is a string (verdict provenance), else null. */
  source: string | null
  /** detail.result_code when it is a string (e.g. 'ttl_ok'), else null. */
  resultCode: string | null
}

export interface VerifiedTrialRow {
  trialId: string
  verified: true
  /** Events this read actually parsed and served (a verified prefix). */
  eventCount: number
  firstTs: string
  lastTs: string
  /** Raw ISO of the newest event — sorting only. */
  lastTsRaw: string
  phases: string[]
  statuses: string[]
  /** Distinct 'kind:id', first-seen order, capped for display. */
  actors: string[]
  components: string[]
  basis: EvidenceBasis
  basisReason: string
  /** True when the verifier passed the trial but this read could not
   * capture its bytes (oversized/unreadable/raced) — basis is 'unknown'. */
  contentUnavailable: boolean
}

export interface UnverifiedTrialRow {
  trialId: string
  verified: false
  /** Bounded verifier error codes / refusal reason — never trial content. */
  reason: string
  /** The verifier's parse-count for the failing trial, when it reported one. */
  reportedEventCount: number | null
}

export interface EvidenceFilters {
  actor?: string
  component?: string
  status?: string
  time?: string
}

export type RawEvidenceFilters = Partial<
  Record<'actor' | 'component' | 'status' | 'time', unknown>
>

export interface EvidencePayload {
  /** Verified trials matching the active filters, newest first, capped. */
  rows: VerifiedTrialRow[]
  /** UNVERIFIED trials — ALWAYS served (filters never hide them), capped
   * with an honest count. */
  unverified: UnverifiedTrialRow[]
  totalTrials: number
  verifiedCount: number
  unverifiedCount: number
  /** Verified trials matching the filters, before the render cap. */
  matchedCount: number
  /** Corrupt event lines inside captured ledgers (counted, never crashed on). */
  skippedLines: number
  /** Trial ledgers present but unreadable/oversized — counted so the page
   * never claims "honestly empty" over rows it could not read. */
  skippedFiles: number
  /** Store-level verifier verdict (control/receipts/watermarks), distinct
   * from per-trial results. */
  storeOk: boolean
  storeErrors: string[]
  missingDir: boolean
  /** Loud failure (auth / verifier spawn / store unreadable) — rendered,
   * never guessed around. */
  error: string | null
  /** Typed refusal for an invalid filter — zero rows, store never read. */
  filterError: string | null
  /** The validated, active filters (echo — only ever validated values). */
  filters: EvidenceFilters
  /** Resolved store dir (the page's proof line). */
  storeDir: string
  cap: number
}

// ---------------------------------------------------------------------------
// Store dir — fixed server-side
// ---------------------------------------------------------------------------

/** The evidence store this page reads — the SAME store the officer doorway
 * pins ($REPO/instance/evidence/v1). Resolved per call (CABINET_ROOT is
 * honored late, same doctrine as cabinet-root.ts). No env override and no
 * caller input, ever. */
export function evidenceDir(): string {
  return cabinetPath('instance', 'evidence', 'v1')
}

// ---------------------------------------------------------------------------
// Filter validation (pure — runs BEFORE any I/O)
// ---------------------------------------------------------------------------

const FILTER_KEYS = ['actor', 'component', 'status', 'time'] as const
const TIME_RE = /^(\d{8})(?:-(\d{8}))?$/

export type FilterValidation =
  | { ok: true; filters: EvidenceFilters }
  | { ok: false; error: string }

/** Real-calendar day check — LOCKSTEP with the Python query plane's
 * `datetime.strptime(value, "%Y%m%d")` (framework/evidence/query.py): month
 * lengths and leap years included, so `20260231` refuses here exactly as the
 * CLI refuses `by-time:20260231-…`. One validation truth; pinned by
 * cabinet/scripts/tests/test_evidence_read_lockstep.py + the shared case
 * vector both suites run (evidence-filter-cases.json). */
function validDayDigits(value: string): boolean {
  const year = Number(value.slice(0, 4))
  const month = Number(value.slice(4, 6))
  const day = Number(value.slice(6, 8))
  const date = new Date(Date.UTC(year, month - 1, day))
  return (
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  )
}

/**
 * Validate caller-supplied filters against closed vocabularies. Mirrors the
 * G1 store-projection verbs (by-actor / by-component / by-status / by-time)
 * and the officer doorway's validation posture: strict allowlist regex,
 * bounded length, typed refusal on anything else. Values are ONLY ever
 * compared in memory against parsed event fields — never concatenated into
 * a filesystem path, never placed into spawn argv.
 *
 *  - actor:      `<id>` or `<kind>:<id>` where kind ∈ ACTOR_KINDS and both
 *                the whole token and the id match the trial-id charset;
 *                a bare value matches actor.id (a prefix that is not a
 *                known kind is treated as part of a plain id).
 *  - component:  trial-id charset; matches component.name exactly.
 *  - status:     member of the closed STATUSES vocabulary.
 *  - time:       yyyymmdd or yyyymmdd-yyyymmdd (inclusive, UTC event dates).
 *                The single-day form is this page's ONE documented input
 *                alias: it is exactly `<d>-<d>` (the CLI query plane accepts
 *                only the range form). Everything else — charset, closed
 *                vocabularies, real-calendar days, oldest-to-newest ordering
 *                — mirrors framework/evidence/query.py byte-for-byte, pinned
 *                by test_evidence_read_lockstep.py + the shared case vector.
 *
 * Empty strings count as absent. Arrays, non-strings, and unknown filter
 * names are refused loudly (fail-closed) — never silently ignored.
 */
export function validateFilters(raw?: RawEvidenceFilters | null): FilterValidation {
  const filters: EvidenceFilters = {}
  if (raw === undefined || raw === null) return { ok: true, filters }
  if (typeof raw !== 'object' || Array.isArray(raw)) {
    return { ok: false, error: 'filters must be a plain object' }
  }
  const known = new Set<string>(FILTER_KEYS)
  for (const key of Object.keys(raw)) {
    if (!known.has(key)) {
      return { ok: false, error: `unknown filter ${JSON.stringify(key)} — valid filters: actor, component, status, time` }
    }
  }
  for (const key of FILTER_KEYS) {
    const value = (raw as Record<string, unknown>)[key]
    if (value === undefined || value === null || value === '') continue
    if (typeof value !== 'string') {
      return { ok: false, error: `${key}: exactly one plain string value is accepted` }
    }
    if (key === 'time') {
      const match = TIME_RE.exec(value)
      if (!match) return { ok: false, error: 'time: use yyyymmdd or yyyymmdd-yyyymmdd (UTC)' }
      const from = match[1]
      const to = match[2] ?? match[1]
      if (!validDayDigits(from) || !validDayDigits(to)) {
        return { ok: false, error: 'time: not a calendar date' }
      }
      if (from > to) return { ok: false, error: 'time: range start is after its end' }
      filters.time = value
      continue
    }
    if (!TRIAL_ID_RE.test(value)) {
      return {
        ok: false,
        error: `${key}: values are identifier tokens (leading alphanumeric; [A-Za-z0-9._:-]; max 128 chars)`,
      }
    }
    if (key === 'status') {
      if (!EVIDENCE_STATUSES.has(value)) {
        return { ok: false, error: `status: ${JSON.stringify(value)} is not in the evidence status vocabulary` }
      }
      filters.status = value
      continue
    }
    if (key === 'actor') {
      const parsed = parseActorFilter(value)
      if (parsed.kind !== null && !TRIAL_ID_RE.test(parsed.id)) {
        return { ok: false, error: 'actor: kind:id needs a non-empty id after the kind' }
      }
      filters.actor = value
      continue
    }
    filters.component = value
  }
  return { ok: true, filters }
}

export function hasActiveFilters(filters: EvidenceFilters): boolean {
  return Boolean(filters.actor || filters.component || filters.status || filters.time)
}

function parseActorFilter(token: string): { kind: string | null; id: string } {
  const idx = token.indexOf(':')
  if (idx > 0) {
    const prefix = token.slice(0, idx)
    if (ACTOR_KINDS.has(prefix)) return { kind: prefix, id: token.slice(idx + 1) }
  }
  return { kind: null, id: token }
}

// ---------------------------------------------------------------------------
// Pure parsing + matching + basis derivation
// ---------------------------------------------------------------------------

function asRecord(value: unknown): Record<string, unknown> {
  if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return {}
}

/** Parse one ledger line into the lite view, or null when unparseable.
 * Never throws; corrupt lines are the caller's counter. */
export function parseEventLine(line: string): EvidenceEventLite | null {
  let parsed: unknown
  try {
    parsed = JSON.parse(line)
  } catch {
    return null
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return null
  const row = parsed as Record<string, unknown>
  const actor = asRecord(row.actor)
  const component = asRecord(row.component)
  const detail = asRecord(row.detail)
  const str = (v: unknown): string => (typeof v === 'string' ? v : '')
  const strOrNull = (v: unknown): string | null => (typeof v === 'string' ? v : null)
  return {
    phase: str(row.phase),
    status: str(row.status),
    ts: str(row.ts),
    actorKind: str(actor.kind),
    actorId: str(actor.id),
    component: str(component.name),
    source: strOrNull(detail.source),
    resultCode: strOrNull(detail.result_code),
  }
}

/** '2026-07-14T09:00:00.123456Z' → '20260714'; null when unparseable. */
function tsDateDigits(ts: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T/.exec(ts)
  return m ? m[1] + m[2] + m[3] : null
}

/** One event against ALL active filter dimensions (AND semantics). */
export function eventMatches(event: EvidenceEventLite, filters: EvidenceFilters): boolean {
  if (filters.actor) {
    const wanted = parseActorFilter(filters.actor)
    if (wanted.kind !== null) {
      if (event.actorKind !== wanted.kind || event.actorId !== wanted.id) return false
    } else if (event.actorId !== wanted.id) {
      return false
    }
  }
  if (filters.component && event.component !== filters.component) return false
  if (filters.status && event.status !== filters.status) return false
  if (filters.time) {
    const digits = tsDateDigits(event.ts)
    if (digits === null) return false
    const match = TIME_RE.exec(filters.time)
    if (!match) return false
    const from = match[1]
    const to = match[2] ?? match[1]
    if (digits < from || digits > to) return false
  }
  return true
}

/** A trial matches when at least one of its events satisfies every active
 * dimension (no filters → every trial matches). */
export function trialMatches(events: EvidenceEventLite[], filters: EvidenceFilters): boolean {
  if (!hasActiveFilters(filters)) return true
  return events.some((event) => eventMatches(event, filters))
}

/**
 * Derive the trial's evidence basis from its (verified) events. Pure.
 * Field rules per the Phase-3 design + framework/evidence/classification.py
 * grounding; precedence strongest-first:
 *   1. human-verified — a verification/outcome/feedback event whose actor
 *      kind is 'captain' (the token-gated label path mints exactly this),
 *      or a recorded human verdict (detail.source == 'verdict_human').
 *   2. independently-recomputed — a verdict minted by a judge independent
 *      of the producer (detail.source == 'verdict_judge', the
 *      action_reconcile machine-label writer).
 *   3. self-asserted — any other verification/outcome event: the producer
 *      or a system component vouching for its own work (e.g.
 *      'canonical_state_and_receipt_present', 'payload_sha256_reverified').
 *      Reconciler persistence confirmations (result_code == 'ttl_ok') do
 *      NOT count — persisting is not a judgment.
 *   4. persistence-only — nothing beyond integrity + persistence: no
 *      verification/outcome/feedback event beside the execution (a producer
 *      'succeeded' status inside execution rows is itself an assertion
 *      inside persisted bytes, not a verification leg).
 */
export function deriveBasis(events: EvidenceEventLite[]): {
  basis: Exclude<EvidenceBasis, 'unknown'>
  reason: string
} {
  const judgments = events.filter((event) => JUDGMENT_PHASES.has(event.phase))
  if (judgments.some((event) => event.actorKind === 'captain')) {
    return {
      basis: 'human-verified',
      reason: 'captain-attributed verification/outcome/feedback event on this trial',
    }
  }
  const verdicts = judgments.filter(
    (event) => event.phase === 'verification' || event.phase === 'outcome'
  )
  if (verdicts.some((event) => event.source === 'verdict_human')) {
    return { basis: 'human-verified', reason: 'recorded human verdict (source verdict_human)' }
  }
  if (verdicts.some((event) => event.source === 'verdict_judge')) {
    return {
      basis: 'independently-recomputed',
      reason: 'machine verdict independent of the producer (source verdict_judge)',
    }
  }
  const selfAsserting = verdicts.filter((event) => event.resultCode !== 'ttl_ok')
  if (selfAsserting.length > 0) {
    return {
      basis: 'self-asserted',
      reason: 'producer/system verification without an independent source',
    }
  }
  if (verdicts.length > 0) {
    return { basis: 'persistence-only', reason: 'reconciler confirmed persistence only (ttl_ok)' }
  }
  return {
    basis: 'persistence-only',
    reason: 'no verification or outcome event beside the execution',
  }
}

const EVIDENCE_TS = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})(?:\.\d+)?Z$/

/** Recorder timestamps are UTC with fractional seconds — render the stable
 * prefix; a malformed value is shown raw, never silently reformatted. */
export function evidenceUtcLabel(ts: string): string {
  if (!ts) return '—'
  const m = EVIDENCE_TS.exec(ts)
  if (!m) return ts
  return `${m[1]} ${m[2]} UTC`
}

function distinct(values: string[], cap: number): string[] {
  const seen: string[] = []
  for (const value of values) {
    if (!value || seen.includes(value)) continue
    seen.push(value)
    if (seen.length >= cap) break
  }
  return seen
}

/** Shape one VERIFIED trial (with captured content) for the page. */
export function summarizeVerifiedTrial(
  trialId: string,
  events: EvidenceEventLite[]
): VerifiedTrialRow {
  const timestamps = events
    .map((event) => event.ts)
    .filter(Boolean)
    .sort()
  const { basis, reason } = deriveBasis(events)
  return {
    trialId,
    verified: true,
    eventCount: events.length,
    firstTs: evidenceUtcLabel(timestamps[0] ?? ''),
    lastTs: evidenceUtcLabel(timestamps[timestamps.length - 1] ?? ''),
    lastTsRaw: timestamps[timestamps.length - 1] ?? '',
    phases: distinct(events.map((event) => event.phase), 12),
    statuses: distinct(events.map((event) => event.status), 12),
    actors: distinct(
      events.map((event) =>
        event.actorKind || event.actorId
          ? `${event.actorKind || '?'}:${event.actorId || '?'}`
          : ''
      ),
      6
    ),
    components: distinct(events.map((event) => event.component), 6),
    basis,
    basisReason: reason,
    contentUnavailable: false,
  }
}

function boundedReason(errors: unknown, fallback: string): string {
  if (!Array.isArray(errors) || errors.length === 0) return fallback
  const codes = errors.filter((item): item is string => typeof item === 'string')
  if (codes.length === 0) return fallback
  const shown = codes.slice(0, 4).join(', ').slice(0, 300)
  const more = codes.length > 4 ? ` (+${codes.length - 4} more)` : ''
  return shown + more
}

// ---------------------------------------------------------------------------
// Verifier bridge (spawn discipline cloned from the germline bridge.ts)
// ---------------------------------------------------------------------------

export interface TrialVerifyResult {
  ok: boolean
  trialId: string
  eventCount: number
  errors: string[]
}

export interface StoreVerifyResult {
  ok: boolean
  trials: TrialVerifyResult[]
  errors: string[]
}

export type VerifyOutcome =
  | { kind: 'result'; result: StoreVerifyResult }
  | { kind: 'failure'; code: string }

/** The exact, fixed invocation — no filter value or caller input is ever
 * part of it. `dir` comes from evidenceDir() alone. */
export function verifierInvocation(dir: string): {
  executable: string
  argv: string[]
  cwd: string
} {
  return {
    executable: process.env.CABINET_PYTHON || 'python3.12',
    argv: ['-m', 'framework.evidence', '--store', dir, 'verify'],
    cwd: cabinetRoot(),
  }
}

/** Coerce verifier stdout + exit code into a typed outcome (pure).
 * Exit 0 = store ok; exit 4 = valid JSON with failures recorded (the
 * fail-closed per-trial results are IN the payload); exit 3 = typed
 * EvidenceError refusal. Anything else — or unparseable output — is a
 * loud failure; nothing gets served on a guess. */
export function parseVerifyStdout(stdout: string, exitCode: number | null): VerifyOutcome {
  if (exitCode !== 0 && exitCode !== 3 && exitCode !== 4) {
    return { kind: 'failure', code: `verifier_exit_${exitCode === null ? 'signal' : exitCode}` }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(stdout)
  } catch {
    return { kind: 'failure', code: 'verifier_response' }
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return { kind: 'failure', code: 'verifier_response' }
  }
  const record = parsed as Record<string, unknown>
  if (exitCode === 3) {
    const code = typeof record.code === 'string' ? record.code : 'verifier_refused'
    return { kind: 'failure', code }
  }
  const rawTrials = Array.isArray(record.trials) ? record.trials : []
  const trials: TrialVerifyResult[] = []
  for (const item of rawTrials) {
    if (typeof item !== 'object' || item === null || Array.isArray(item)) continue
    const row = item as Record<string, unknown>
    const trialId = typeof row.trial_id === 'string' ? row.trial_id : ''
    if (!TRIAL_ID_RE.test(trialId)) continue
    trials.push({
      ok: row.ok === true,
      trialId,
      eventCount:
        typeof row.event_count === 'number' && Number.isFinite(row.event_count)
          ? row.event_count
          : 0,
      errors: Array.isArray(row.errors)
        ? row.errors.filter((e): e is string => typeof e === 'string')
        : [],
    })
  }
  return {
    kind: 'result',
    result: {
      ok: record.ok === true,
      trials,
      errors: Array.isArray(record.errors)
        ? record.errors
            .filter((e): e is string => typeof e === 'string')
            .slice(0, 8)
            .map((e) => e.slice(0, 120))
        : [],
    },
  }
}

/** Run the canonical Python verifier over the whole store. Resolves a typed
 * outcome, never rejects. stderr is bounded and never surfaced to the
 * browser (a boolean marker is logged for the operator only). */
function runVerifierSpawn(dir: string): Promise<VerifyOutcome> {
  const spec = verifierInvocation(dir)
  return new Promise((resolve) => {
    let child
    try {
      child = spawn(spec.executable, spec.argv, {
        cwd: spec.cwd,
        env: { ...process.env, CABINET_ROOT: spec.cwd },
        shell: false,
        stdio: ['ignore', 'pipe', 'pipe'],
      })
    } catch {
      resolve({ kind: 'failure', code: 'verifier_unavailable' })
      return
    }
    let stdout = ''
    let stderr = ''
    let oversized = false
    let timedOut = false
    const timer = setTimeout(() => {
      timedOut = true
      child.kill('SIGKILL')
    }, VERIFY_TIMEOUT_MS)
    child.stdout.setEncoding('utf8')
    child.stderr.setEncoding('utf8')
    child.stdout.on('data', (chunk: string) => {
      if (stdout.length + chunk.length > MAX_VERIFY_OUTPUT_BYTES) {
        oversized = true
        child.kill('SIGKILL')
        return
      }
      stdout += chunk
    })
    child.stderr.on('data', (chunk: string) => {
      if (stderr.length < 8_192) stderr += chunk.slice(0, 8_192 - stderr.length)
    })
    child.on('error', () => {
      clearTimeout(timer)
      resolve({ kind: 'failure', code: 'verifier_unavailable' })
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      if (timedOut) {
        resolve({ kind: 'failure', code: 'verifier_timeout' })
        return
      }
      if (oversized) {
        resolve({ kind: 'failure', code: 'verifier_output_limit' })
        return
      }
      const outcome = parseVerifyStdout(stdout, code)
      if (outcome.kind === 'failure') {
        // Never the bytes — only a marker so an operator can tell a silent
        // spawn from a Python-side exit.
        console.error('[evidence-read] verifier outcome unusable', {
          code,
          hadStderr: Boolean(stderr),
        })
      }
      resolve(outcome)
    })
  })
}

// ---------------------------------------------------------------------------
// Filesystem snapshot (read-only; taken BEFORE the verify pass)
// ---------------------------------------------------------------------------

interface TrialSnapshot {
  events: EvidenceEventLite[]
  skippedLines: number
  /** Bytes not captured (oversized / unreadable / symlink-escape). */
  unavailable: boolean
}

interface StoreSnapshot {
  /** Map defeats hostile names like __proto__ (never object keys). */
  snapshots: Map<string, TrialSnapshot>
  skippedFiles: number
}

async function snapshotStore(dir: string): Promise<StoreSnapshot> {
  const snapshots = new Map<string, TrialSnapshot>()
  let skippedFiles = 0
  const trialsDir = path.join(dir, 'trials')

  let names: string[]
  try {
    names = await fs.readdir(trialsDir)
  } catch {
    // No trials dir yet — the verifier still reports on the store itself.
    return { snapshots, skippedFiles }
  }
  let realBase: string
  try {
    realBase = await fs.realpath(trialsDir)
  } catch {
    return { snapshots, skippedFiles }
  }

  for (const name of names.filter((n) => TRIAL_ID_RE.test(n)).sort()) {
    const trialDir = path.join(trialsDir, name)
    const ledger = path.join(trialDir, 'events.jsonl')
    // Never follow a planted symlink out of the store (mirror of the
    // receipts journal containment; the Python verifier independently fails
    // such trials, which is what actually reaches the page).
    let contained = true
    for (const candidate of [trialDir, ledger]) {
      try {
        const real = await fs.realpath(candidate)
        if (real !== realBase && !real.startsWith(realBase + path.sep)) contained = false
      } catch {
        // ENOENT on the ledger is a legitimately empty trial dir; the
        // trial-dir itself resolving nowhere means it vanished mid-read.
        if (candidate === trialDir) contained = false
      }
      if (!contained) break
    }
    if (!contained) {
      snapshots.set(name, { events: [], skippedLines: 0, unavailable: true })
      continue
    }
    let stat
    try {
      stat = await fs.stat(ledger)
    } catch {
      snapshots.set(name, { events: [], skippedLines: 0, unavailable: false })
      continue
    }
    if (!stat.isFile() || stat.size > MAX_EVENTS_FILE_BYTES) {
      skippedFiles += 1
      snapshots.set(name, { events: [], skippedLines: 0, unavailable: true })
      continue
    }
    let text: string
    try {
      text = await fs.readFile(ledger, 'utf8')
    } catch {
      skippedFiles += 1
      snapshots.set(name, { events: [], skippedLines: 0, unavailable: true })
      continue
    }
    const events: EvidenceEventLite[] = []
    let skippedLines = 0
    for (const line of text.split('\n')) {
      const trimmed = line.trim()
      if (!trimmed) continue
      const parsed = parseEventLine(trimmed)
      if (parsed === null) {
        skippedLines += 1
        continue
      }
      events.push(parsed)
    }
    snapshots.set(name, { events, skippedLines, unavailable: false })
  }
  return { snapshots, skippedFiles }
}

// ---------------------------------------------------------------------------
// Orchestrator
// ---------------------------------------------------------------------------

export interface ReadDeps {
  /** Test seam — production always uses the fixed-argv Python spawn. */
  runVerify?: (dir: string) => Promise<VerifyOutcome>
}

function basePayload(storeDir: string): EvidencePayload {
  return {
    rows: [],
    unverified: [],
    totalTrials: 0,
    verifiedCount: 0,
    unverifiedCount: 0,
    matchedCount: 0,
    skippedLines: 0,
    skippedFiles: 0,
    storeOk: false,
    storeErrors: [],
    missingDir: false,
    error: null,
    filterError: null,
    filters: {},
    storeDir,
    cap: EVIDENCE_SHOW_CAP,
  }
}

/**
 * Read the evidence store, fail-closed. Order of operations:
 *   1. validate filters (typed refusal BEFORE any I/O);
 *   2. missing store dir → honest empty (the verifier is not even spawned —
 *      pointing tools at an absent store must never create one);
 *   3. snapshot trial bytes;
 *   4. run the canonical Python verifier over the store;
 *   5. join: content ONLY for verifier-passed trials; everything else is an
 *      explicit UNVERIFIED stub; a verifier that did not run renders EVERY
 *      trial UNVERIFIED.
 */
export async function readEvidence(
  raw?: RawEvidenceFilters | null,
  deps: ReadDeps = {}
): Promise<EvidencePayload> {
  const storeDir = evidenceDir()
  const payload = basePayload(storeDir)

  const validation = validateFilters(raw)
  if (!validation.ok) {
    return { ...payload, filterError: validation.error }
  }
  payload.filters = validation.filters

  try {
    await fs.stat(storeDir)
  } catch (err) {
    const code = (err as NodeJS.ErrnoException).code
    if (code === 'ENOENT' || code === 'ENOTDIR') return { ...payload, missingDir: true }
    return { ...payload, error: 'evidence store unreadable' }
  }

  const { snapshots, skippedFiles } = await snapshotStore(storeDir)
  payload.skippedFiles = skippedFiles

  const runVerify = deps.runVerify ?? runVerifierSpawn
  const outcome = await runVerify(storeDir)

  if (outcome.kind === 'failure') {
    // Fail-closed display: nothing verified means nothing served as
    // content — every enumerated trial renders as an explicit UNVERIFIED
    // stub, never silently and never as a guess.
    const stubs: UnverifiedTrialRow[] = [...snapshots.keys()].sort().map((trialId) => ({
      trialId,
      verified: false,
      reason: `verifier did not run (${outcome.code})`,
      reportedEventCount: null,
    }))
    return {
      ...payload,
      error: `evidence verifier did not run (${outcome.code}) — nothing is served unverified`,
      unverified: stubs.slice(0, EVIDENCE_SHOW_CAP),
      unverifiedCount: stubs.length,
      totalTrials: stubs.length,
    }
  }

  const { result } = outcome
  payload.storeOk = result.ok
  payload.storeErrors = result.errors

  const verifyRows = new Map<string, TrialVerifyResult>()
  for (const row of result.trials) verifyRows.set(row.trialId, row)

  const allIds = new Set<string>([...snapshots.keys(), ...verifyRows.keys()])
  const verified: VerifiedTrialRow[] = []
  const unverified: UnverifiedTrialRow[] = []
  let skippedLines = 0

  for (const trialId of [...allIds].sort()) {
    const verdict = verifyRows.get(trialId)
    const snapshot = snapshots.get(trialId)
    if (!verdict) {
      unverified.push({
        trialId,
        verified: false,
        reason: 'not covered by the verifier run',
        reportedEventCount: null,
      })
      continue
    }
    if (!verdict.ok) {
      unverified.push({
        trialId,
        verified: false,
        reason: boundedReason(verdict.errors, 'verification failed'),
        reportedEventCount: verdict.eventCount,
      })
      continue
    }
    if (!snapshot || snapshot.unavailable) {
      verified.push({
        trialId,
        verified: true,
        eventCount: verdict.eventCount,
        firstTs: '—',
        lastTs: '—',
        lastTsRaw: '',
        phases: [],
        statuses: [],
        actors: [],
        components: [],
        basis: 'unknown',
        basisReason: 'trial verified, but its bytes were not captured in this read',
        contentUnavailable: true,
      })
      continue
    }
    if (snapshot.events.length > verdict.eventCount) {
      // The ledger SHRANK between our snapshot and the verify pass —
      // rollback-shaped; a snapshot is only a verified prefix when the
      // verified ledger is at least as long. Fail closed.
      unverified.push({
        trialId,
        verified: false,
        reason: 'ledger changed shape during the read (rollback-shaped) — refused',
        reportedEventCount: verdict.eventCount,
      })
      continue
    }
    skippedLines += snapshot.skippedLines
    verified.push(summarizeVerifiedTrial(trialId, snapshot.events))
  }

  const filtersActive = hasActiveFilters(payload.filters)
  const matched = verified.filter((row) => {
    if (!filtersActive) return true
    if (row.contentUnavailable) return false // cannot be evaluated — fail closed
    const snapshot = snapshots.get(row.trialId)
    return snapshot ? trialMatches(snapshot.events, payload.filters) : false
  })

  matched.sort((a, b) => {
    const ta = a.lastTsRaw
    const tb = b.lastTsRaw
    return ta < tb ? 1 : ta > tb ? -1 : a.trialId < b.trialId ? -1 : 1
  })
  unverified.sort((a, b) => (a.trialId < b.trialId ? -1 : a.trialId > b.trialId ? 1 : 0))

  return {
    ...payload,
    rows: matched.slice(0, EVIDENCE_SHOW_CAP),
    unverified: unverified.slice(0, EVIDENCE_SHOW_CAP),
    totalTrials: allIds.size,
    verifiedCount: verified.length,
    unverifiedCount: unverified.length,
    matchedCount: matched.length,
    skippedLines,
  }
}
