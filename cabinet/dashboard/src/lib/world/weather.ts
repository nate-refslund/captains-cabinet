/**
 * WEATHER LAYER — bound to REAL signals (Captain ruling 2026-07-09:
 * weather is never decor; every state names its exact source honestly).
 *
 * The binding (exact sources, defined here once):
 *   STORM = `cabinet:killswitch` set (red is killswitch-only — the storm is
 *           the world-wide red-wash weather; immediate BOTH directions:
 *           killswitch truth never lags behind hysteresis).
 *   FOG   = telemetry degraded / unknown: doctor heartbeat
 *           (`cabinet:doctor:heartbeat`) absent or stale >26h — yesterday's
 *           OK is never rendered as today's (infra-viz staleness law).
 *   RAIN  = elevated error/incident rate: doctor reports DEAD services,
 *           or a probe verdict failed (probe-* verdict supply).
 *   SUN   = doctor GREEN and no failing probes — the measured good day.
 *
 * Non-storm transitions hold 2 consecutive evals (hysteresis — weather
 * never flaps on one noisy reading). Rain particles are a pure function of
 * the logical tick, seeded fnv1a per drop — two runs at the same tick are
 * byte-identical (determinism ratchet).
 */
import { fnv1a } from './hash'

export type WeatherKind = 'sun' | 'rain' | 'fog' | 'storm'

/** Honest signal set — null = unknown/unmeasured (drives FOG, never SUN). */
export interface WeatherSignals {
  /** cabinet:killswitch present. */
  killswitch: boolean
  /** Seconds since the doctor heartbeat was written; null = absent. */
  doctorAgeSecs: number | null
  /** Doctor verdict: true = all green, false = DEAD lines present;
   * null = unknown (no parse / no heartbeat). */
  doctorGreen: boolean | null
  /** Probe verdicts: false = a probe failed recently; null = no probe data. */
  probesOk: boolean | null
}

/** Staleness gate (infra-viz law: >26h ⇒ everything grey/unmeasured). */
export const DOCTOR_STALE_SECS = 26 * 3600

export interface WeatherTarget {
  kind: WeatherKind
  /** Honest inspect line naming the exact source of this state. */
  why: string
}

export function weatherTarget(s: WeatherSignals): WeatherTarget {
  if (s.killswitch) {
    return { kind: 'storm', why: 'cabinet:killswitch active — the storm is the red wash' }
  }
  if (s.doctorAgeSecs === null || s.doctorAgeSecs > DOCTOR_STALE_SECS || s.doctorGreen === null) {
    return {
      kind: 'fog',
      why:
        s.doctorAgeSecs === null
          ? 'cabinet:doctor:heartbeat absent — telemetry unknown (fog = unmeasured)'
          : s.doctorAgeSecs > DOCTOR_STALE_SECS
            ? 'doctor heartbeat stale >26h — never render yesterday’s OK as today’s'
            : 'doctor verdict unparseable — telemetry degraded',
    }
  }
  if (s.doctorGreen === false || s.probesOk === false) {
    return {
      kind: 'rain',
      why:
        s.doctorGreen === false
          ? 'doctor reports DEAD services — elevated incident rate'
          : 'probe verdict failed — elevated error rate',
    }
  }
  return {
    kind: 'sun',
    why:
      s.probesOk === true
        ? 'doctor GREEN + probes passing'
        : 'doctor GREEN (no probe data — sun on the doctor alone)',
  }
}

/** Non-storm transitions hold this many consecutive evals. */
export const WEATHER_HOLD_EVALS = 2

export interface WeatherState {
  kind: WeatherKind
  why: string
  candKind: WeatherKind | null
  candStreak: number
}

export function initialWeather(): WeatherState {
  return { kind: 'sun', why: 'no eval yet — default sun', candKind: null, candStreak: 0 }
}

/** One eval of the weather machine (pure reducer). */
export function weatherStep(state: WeatherState, target: WeatherTarget): WeatherState {
  // Storm is immediate both directions — killswitch truth never lags.
  if (target.kind === 'storm') {
    return { kind: 'storm', why: target.why, candKind: null, candStreak: 0 }
  }
  if (state.kind === 'storm') {
    return { kind: target.kind, why: target.why, candKind: null, candStreak: 0 }
  }
  if (target.kind === state.kind) {
    return { ...state, why: target.why, candKind: null, candStreak: 0 }
  }
  const streak = target.kind === state.candKind ? state.candStreak + 1 : 1
  if (streak >= WEATHER_HOLD_EVALS) {
    return { kind: target.kind, why: target.why, candKind: null, candStreak: 0 }
  }
  return { ...state, candKind: target.kind, candStreak: streak }
}

// ── deterministic rain particles ────────────────────────────────────────────

export interface RainDrop {
  /** Viewport-relative px (renderer draws at these exact positions). */
  x: number
  y: number
  /** Streak length px (2..5, seeded). */
  len: number
}

/**
 * The rain particle field at one logical tick — pure f(tick, count, size),
 * seeded fnv1a per (tick, drop). Same tick ⇒ byte-identical field.
 */
export function rainDrops(tick: number, count: number, w: number, h: number): RainDrop[] {
  const out: RainDrop[] = []
  const n = Math.max(0, Math.floor(count))
  for (let i = 0; i < n; i++) {
    const hx = fnv1a(`rain:${tick}:${i}:x`)
    const hy = fnv1a(`rain:${tick}:${i}:y`)
    out.push({
      x: hx % Math.max(1, Math.floor(w)),
      y: hy % Math.max(1, Math.floor(h)),
      len: 2 + (fnv1a(`rain:${tick}:${i}:l`) % 4),
    })
  }
  return out
}
