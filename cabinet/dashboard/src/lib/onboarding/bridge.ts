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
  OnboardingResponse,
  OnboardingSurface,
} from './types'

const MODULE = 'framework.onboarding.journey'
const TIMEOUT_MS = 30_000
const MAX_OUTPUT_BYTES = 2 * 1024 * 1024

const ACTIONS = new Set([
  'propose_window',
  'answer_seed',
  'ratify_charter',
  'continue',
  'pause',
  'revoke',
  'undo',
  'purge',
])

export class OnboardingBridgeError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status = 400
  ) {
    super(message)
  }
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
        reject(new OnboardingBridgeError(parsed.code || 'action_refused', parsed.error || 'That onboarding action was refused.', 400))
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
