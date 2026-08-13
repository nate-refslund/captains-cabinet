/**
 * The Dashboard's only bridge to the canonical Python onboarding core.
 *
 * Fixed argv, shell:false, request JSON on stdin. Folder paths, purposes, and
 * Charter hashes never enter a shell string or the process list. The Python
 * core owns persistence, locking, event idempotency, validation, and cards;
 * TypeScript owns no shadow state machine.
 */
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { cabinetRoot } from '@/lib/cabinet-root'
import type {
  OnboardingActionRequest,
  OnboardingObservationRequest,
  OnboardingObservationResponse,
  OnboardingRefusalDetail,
  OnboardingResponse,
  OnboardingSurface,
} from './types'

const MODULE = 'framework.onboarding.journey'
const TIMEOUT_MS = 30_000
const MAX_OUTPUT_BYTES = 2 * 1024 * 1024

/**
 * Exported as a ReadonlySet so `parity.test.ts` can compare the LIVE gate with
 * the Python dispatch chain rather than a text mirror of it — a sensor pointed
 * at a copy of the control is the failure class this program keeps finding in
 * its own tests. Readonly because this set IS the admission gate: a caller able
 * to `.add()` could widen what crosses the process boundary.
 *
 * Deliberately a separate literal from `ONBOARDING_ACTIONS` in ./types rather
 * than derived from it. Deriving would make a new type member auto-admit itself
 * here; a core action reaches this surface only when someone writes it down.
 */
export const ACTIONS: ReadonlySet<string> = new Set([
  'propose_window',
  'answer_seed',
  // Declares ONE connector from a curated template + a credential, in onboarding
  // (Captain 2026-08-13). Carries a `template` id, a `name` label, a
  // `credential_env` NAME and an optional `fields` map — bounded below. It never
  // carries a credential VALUE: the dashboard's safe .env writer stores that,
  // so the value never reaches the core. The core does not print this on a card
  // (a credential paste belongs on the local surface), so it needs no Telegram
  // branch; it is reachable only where a surface writes the send, which is why
  // it lives in this admission set at all.
  'declare_connector',
  // Credentialed READ-ONLY connector sweep (Captain ruling 2026-07-29). Carries
  // no payload: what may be read is declared in instance/config/connectors.yml,
  // never in a request, so no surface can widen the read by sending a field.
  'gather_connectors',
  // Who the operator IS, per connector — their own words, never the
  // credential's. Carries a `handles` map, so it is the one action besides
  // answer_seed whose payload the core must bound (it does: unknown connector,
  // empty list and over-long identifier are each refused BY NAME — the last of
  // those was silently truncated to 500 characters until 2026-07-30, which
  // resolved the operator to a clipped string that then matched nothing).
  'record_operator_identity',
  // Where the depth budget is pointed. It carries a `choice` (one offered
  // candidate id, or the escape hatch), a `name` when the escape hatch is
  // picked, and an optional `same_as` merge. Absent from this set until
  // 2026-08-02, which made the ranked question a LIVE DEAD END: the core
  // printed the candidates on the card, the surface rendered them, and the
  // send was refused here as `action_invalid` before the core ever saw it.
  // A bare send is still refused — by the CORE, as `salience_choice_required`,
  // which is the operator-answerable sentence rather than a surface's guess.
  'answer_salience',
  'ratify_charter',
  'continue',
  'pause',
  'revoke',
  'undo',
  'purge',
  // The way back in after a deletion. Payload-free, and NOT destructive: the
  // core mints a new journey only when the current one was purged, and refuses
  // it outright on a live journey (`start_again_unavailable`), so admitting it
  // here can never cost a running orientation. Absent from this set, the purged
  // card's only option would be refused as `action_invalid` before the core saw
  // it — the same live dead end `answer_salience` was.
  'start_again',
])

export class OnboardingBridgeError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status = 400,
    /** Allowlisted refusal fields only — see `refusalDetail`. */
    public readonly detail: OnboardingRefusalDetail = {}
  ) {
    super(message)
  }
}

/** Longest single relation/target/window string a refusal may carry back. */
const MAX_DETAIL_CHARS = 300
const MAX_DETAIL_ITEMS = 8

function boundedString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim()
    ? value.slice(0, MAX_DETAIL_CHARS)
    : undefined
}

/**
 * The refusal fields a surface may see, taken ONE BY ONE and never spread.
 *
 * A refusal that only says no leaves the operator with nothing to do about it:
 * `salience_window_off_target` names the answered target, the folder that
 * missed it, and the two relations that resolve it — the material the fix-up
 * control is built from. But this is the process boundary between a Python
 * core that can put anything in a refusal and a browser, so widening it is a
 * deliberate act: an unrecognised key never crosses, a string is bounded, and a
 * list is bounded in both length and element size.
 *
 * RESIDUAL, stated rather than implied: as of this change the core's CLI
 * (`framework/onboarding/journey.py::_cli`) prints `{ok, code, error}` and
 * DROPS `JourneyError.detail`, so nothing reaches this function in production
 * yet — the surface therefore builds the same fix-up from the state it already
 * holds (see `relationFixUp` in journey-card.tsx) and treats this as
 * enrichment. This is the receiving half, tested against a core that does emit
 * it; teaching the CLI to emit it is a germline+cognitive-contract unit of its
 * own, and doing it here would have been a half-wire in the other direction.
 */
export function refusalDetail(raw: unknown): OnboardingRefusalDetail {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const source = raw as Record<string, unknown>
  const detail: OnboardingRefusalDetail = {}
  const target = boundedString(source.target)
  if (target) detail.target = target
  const window = boundedString(source.window)
  if (window) detail.window = window
  if (Array.isArray(source.relations)) {
    const relations = source.relations
      .map(boundedString)
      .filter((value): value is string => Boolean(value))
      .slice(0, MAX_DETAIL_ITEMS)
    if (relations.length > 0) detail.relations = relations
  }
  return detail
}

type CoreCommand = 'snapshot' | 'act' | 'observe'

export function invocation(command: CoreCommand): {
  executable: string
  argv: string[]
  cwd: string
} {
  return {
    executable: process.env.CABINET_PYTHON || 'python3.12',
    argv: ['-m', MODULE, command],
    cwd: cabinetRoot(),
  }
}

function run<T extends OnboardingResponse | OnboardingObservationResponse>(
  command: CoreCommand,
  input?: object
): Promise<T> {
  const spec = invocation(command)
  return new Promise((resolve, reject) => {
    let child: ChildProcessWithoutNullStreams
    try {
      child = spawn(spec.executable, spec.argv, {
        cwd: spec.cwd,
        env: { ...process.env, CABINET_ROOT: spec.cwd },
        shell: false,
        stdio: ['pipe', 'pipe', 'pipe'],
      })
    } catch {
      reject(new OnboardingBridgeError('core_unavailable', 'The onboarding core could not start.', 503))
      return
    }

    let stdout = ''
    let stderr = ''
    let oversized = false
    const timer = setTimeout(() => {
      child.kill('SIGKILL')
    }, TIMEOUT_MS)

    child.stdout.setEncoding('utf8')
    child.stderr.setEncoding('utf8')
    child.stdout.on('data', (chunk: string) => {
      if (stdout.length + chunk.length > MAX_OUTPUT_BYTES) {
        oversized = true
        child.kill('SIGKILL')
        return
      }
      stdout += chunk
    })
    child.stderr.on('data', (chunk: string) => {
      // Never expose stderr to the browser. Keep a small bounded diagnostic
      // only so an operator can distinguish a silent spawn from a Python exit.
      if (stderr.length < 8_192) stderr += chunk.slice(0, 8_192 - stderr.length)
    })
    child.on('error', () => {
      clearTimeout(timer)
      reject(new OnboardingBridgeError('core_unavailable', 'The onboarding core is unavailable.', 503))
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      if (oversized) {
        reject(new OnboardingBridgeError('core_output_limit', 'The onboarding core returned too much data.', 502))
        return
      }
      let parsed: T | null = null
      try {
        parsed = JSON.parse(stdout) as T
      } catch {
        // stderr can contain local paths or interpreter detail; log only a
        // boolean marker, never the bytes.
        console.error('[onboarding-bridge] invalid core response', { code, hadStderr: Boolean(stderr) })
        reject(new OnboardingBridgeError('core_response', 'The onboarding core returned an unreadable response.', 502))
        return
      }
      if (!parsed.ok) {
        reject(new OnboardingBridgeError(
          parsed.code || 'action_refused',
          parsed.error || 'That onboarding action was refused.',
          400,
          refusalDetail((parsed as { detail?: unknown }).detail)
        ))
        return
      }
      if (code !== 0) {
        reject(new OnboardingBridgeError('core_exit', 'The onboarding core stopped before completing.', 502))
        return
      }
      resolve(parsed)
    })
    child.stdin.end(input ? JSON.stringify(input) : '')
  })
}

export function getOnboarding(): Promise<OnboardingResponse> {
  return run<OnboardingResponse>('snapshot')
}

export function applyOnboardingAction(
  request: OnboardingActionRequest,
  surface: OnboardingSurface
): Promise<OnboardingResponse> {
  if (!request || !ACTIONS.has(request.action)) {
    throw new OnboardingBridgeError('action_invalid', 'Choose a valid onboarding action.')
  }
  if (request.source && request.source.length > 2_048) {
    throw new OnboardingBridgeError('source_too_long', 'That folder path is too long.')
  }
  if (request.purpose && request.purpose.length > 300) {
    throw new OnboardingBridgeError('purpose_too_long', 'Keep the first purpose under 300 characters.')
  }
  // The core bounds the seed too (it is what persists it); this is the cheap
  // outer bound so a paste never crosses the process boundary at all.
  if (request.seed && request.seed.length > 2_000) {
    throw new OnboardingBridgeError('seed_too_long', 'A sentence or two is enough.')
  }
  // The salience answer, bounded the same way and for the same reason: the core
  // validates `choice` against the offer it built and `same_as` against what it
  // ranked (both refuse by name, which is the operator-answerable behaviour and
  // must not be pre-empted here). These are only the cheap outer bounds so a
  // paste never crosses the process boundary at all.
  if (request.choice && request.choice.length > 300) {
    throw new OnboardingBridgeError('choice_too_long', 'That is not one of the candidates.')
  }
  if (request.name && request.name.length > 2_000) {
    throw new OnboardingBridgeError('name_too_long', 'A word or two is enough.')
  }
  if (request.same_as && request.same_as.length > 64) {
    throw new OnboardingBridgeError('merge_too_many', 'That is too many names in one merge.')
  }
  // declare_connector's own inputs. The core resolves the template, validates
  // the env var NAME, bounds each field value and refuses an unknown field key
  // BY NAME — these are only the cheap outer bounds so a paste never crosses the
  // process boundary. A credential VALUE is deliberately not among them: it does
  // not travel on this request at all.
  if (request.template && request.template.length > 64) {
    throw new OnboardingBridgeError('template_invalid', 'That is not a tool I can set up.')
  }
  if (request.credential_env && request.credential_env.length > 128) {
    throw new OnboardingBridgeError('credential_env_too_long', 'That credential name is too long.')
  }
  if (request.fields && JSON.stringify(request.fields).length > 8_192) {
    throw new OnboardingBridgeError('fields_too_long', 'Those details are too long.')
  }
  return run<OnboardingResponse>('act', {
    ...request,
    action_id: request.action_id || `web-${randomUUID()}`,
    surface,
  })
}

export function recordOnboardingEvidence(
  request: OnboardingObservationRequest,
  surface: OnboardingSurface
): Promise<OnboardingObservationResponse> {
  const phase = request?.phase
  if (!['transport', 'ui', 'feedback'].includes(phase)) {
    throw new OnboardingBridgeError('observation_phase', 'Choose a valid evidence observation.')
  }
  return run<OnboardingObservationResponse>('observe', {
    ...request,
    action_id: request.action_id || `observe-${randomUUID()}`,
    trace_id: request.trace_id || `trace-${randomUUID()}`,
    correlation_id: request.correlation_id || `corr-${randomUUID()}`,
    surface,
  })
}
