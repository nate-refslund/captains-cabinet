/**
 * T2 LIFE — officer life-state derivation (unified spec v2 §5.2 cottage
 * night-cutaway payoff + director behavior vocabulary).
 *
 * One closed enum naming what an officer is HONESTLY doing right now, for
 * cards, the portrait rail, and cutaway staging. Derivation only — the
 * director stays the sole mover; this module never invents state, it names
 * the state the inputs already prove.
 *
 * Night-asleep law (director §1.4, carried): activity-TTL-expired presence
 * plus night (or NO clock data — absence fail-closes to rest, never to
 * invented work) = asleep. Presence-TTL honesty is what makes the sleeping
 * officer in the night cutaway TRUE.
 */
import { DAY_END_HOUR, DAY_START_HOUR } from '../director'
import type { OfficerPresence } from '../types'

export type OfficerLifeState =
  | 'working' // live verb at a work station
  | 'meeting' // live grouped verb, seated at a group scene
  | 'wandering' // session alive, verb TTL expired, daytime idle program
  | 'commuting' // mid road-walk (dominant-focus re-classification)
  | 'asleep' // TTL expired + night (or no clock data)
  | 'frozen' // killswitch active — the world halts

export interface LifeStateInput {
  presence: OfficerPresence
  /** Captain-local hour (server-stamped snapshot data; null = unknown). */
  clockHour?: number | null
  killswitch?: boolean
  /** True while the commute reducer has this officer walking the road. */
  commuting?: boolean
  /** True when the director seated this officer in a group scene. */
  inGroupScene?: boolean
}

export function isDayHour(clockHour: number | null | undefined): boolean {
  return (
    typeof clockHour === 'number' &&
    clockHour >= DAY_START_HOUR &&
    clockHour < DAY_END_HOUR
  )
}

/** Closed, total, deterministic — every input combination names one state. */
export function officerLifeState(input: LifeStateInput): OfficerLifeState {
  if (input.killswitch) return 'frozen'
  if (input.commuting) return 'commuting'
  const expired = !input.presence.present || !input.presence.verb
  if (expired) return isDayHour(input.clockHour) ? 'wandering' : 'asleep'
  if (input.inGroupScene) return 'meeting'
  return 'working'
}

/** Honest one-line card text per state (rail/card surface). */
export function lifeStateLabel(
  state: OfficerLifeState,
  verb: string | null
): string {
  switch (state) {
    case 'working':
      return verb ? `working — ${verb}` : 'working'
    case 'meeting':
      return verb ? `in a meeting — ${verb}` : 'in a meeting'
    case 'wandering':
      return 'idle — session alive, no tool call in 5 min'
    case 'commuting':
      return 'on the road — dominant focus re-classified'
    case 'asleep':
      return 'asleep — activity TTL expired'
    case 'frozen':
      return 'frozen — killswitch active'
  }
}
