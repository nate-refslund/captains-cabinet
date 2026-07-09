/**
 * Killswitch lever — the two-tap state machine (Captain ruling 2026-07-09:
 * the killswitch lever is the ONE in-world actuator; everything else stays
 * read/inspect/deep-link only).
 *
 * PURE + tick-based: no wall clock — determinism ratchet #4; arming expiry
 * counts logical director ticks (250ms each), so the machine is unit-testable
 * and replay-identical. The component owns side effects; this module owns
 * every transition:
 *
 *   idle ──tap──▶ armed (10s auto-expire) ──tap+cookie──▶ pending ──▶ ok|fail
 *                    │ abort / expiry ▶ idle                   fail carries the
 *                    │ tap without cookie: stays armed          exact CLI
 *                    ▼                                          fallback text
 *
 * View-only law: without the captain session (canActuate=false) the lever
 * still renders TRUE state — visitors see truth, can't act.
 */

/** Logical ticks (250ms) before an armed lever disarms itself: 10 s. */
export const ARM_EXPIRE_TICKS = 40

export type LeverPhase = 'idle' | 'armed' | 'pending' | 'ok' | 'fail'

export interface LeverState {
  phase: LeverPhase
  /** Tick at which the lever was armed (expiry anchor); null unless armed. */
  armedAtTick: number | null
  /** Honest failure text (exact fallback command) — never a silent failure. */
  error: string | null
}

export const LEVER_IDLE: LeverState = {
  phase: 'idle',
  armedAtTick: null,
  error: null,
}

export type LeverEvent =
  | { type: 'tap' }
  | { type: 'abort' }
  | { type: 'tick'; tick: number }
  | { type: 'result'; ok: boolean; error?: string }

export interface LeverContext {
  /** Current logical tick (the shell's director clock). */
  tick: number
  /** Captain session cookie present — the actuation gate. */
  canActuate: boolean
}

export interface LeverTransition {
  state: LeverState
  /** True exactly when the machine authorizes firing the actuator. */
  fire: boolean
}

/** The exact honest-degradation fallback the dialog must print on failure. */
export function fallbackCommand(killswitchActive: boolean): string {
  return `cabinet/scripts/kill-switch.sh ${killswitchActive ? 'deactivate' : 'activate'}`
}

export function leverReduce(
  state: LeverState,
  ev: LeverEvent,
  ctx: LeverContext
): LeverTransition {
  switch (ev.type) {
    case 'tap': {
      if (state.phase === 'idle' || state.phase === 'ok' || state.phase === 'fail') {
        // Tap 1 — arm (amber glow; 10s auto-expire starts counting).
        return {
          state: { phase: 'armed', armedAtTick: ctx.tick, error: null },
          fire: false,
        }
      }
      if (state.phase === 'armed') {
        if (!ctx.canActuate) {
          // View-only: truth renders, action refuses (no cookie, no PULL).
          return { state, fire: false }
        }
        // Tap 2 — PULL.
        return {
          state: { phase: 'pending', armedAtTick: null, error: null },
          fire: true,
        }
      }
      return { state, fire: false } // pending: taps ignored
    }
    case 'abort':
      if (state.phase === 'pending') return { state, fire: false }
      return { state: LEVER_IDLE, fire: false }
    case 'tick': {
      if (
        state.phase === 'armed' &&
        state.armedAtTick !== null &&
        ev.tick - state.armedAtTick >= ARM_EXPIRE_TICKS
      ) {
        // Arming auto-expires after 10 s — never a standing hair-trigger.
        return { state: LEVER_IDLE, fire: false }
      }
      return { state, fire: false }
    }
    case 'result': {
      if (state.phase !== 'pending') return { state, fire: false }
      return {
        state: ev.ok
          ? { phase: 'ok', armedAtTick: null, error: null }
          : { phase: 'fail', armedAtTick: null, error: ev.error ?? 'actuation failed' },
        fire: false,
      }
    }
  }
}
