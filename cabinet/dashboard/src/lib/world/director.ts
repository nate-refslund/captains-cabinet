/**
 * The deterministic director — pure TS reducer, vitest-tested, NO wall clock.
 *
 * Contract (E0/E1 determinism gate): the director is a pure REDUCER —
 * step(state, input) → { state, scenes }. The logical tick is a monotonic
 * integer the render loop advances from frame deltas; the director never
 * reads a wall clock or an unseeded RNG — the CI ratchet greps this tree
 * for those calls. Feeding two directors
 * the identical input sequence yields identical scene sequences, forever —
 * which is exactly the "same chronicle twice → frame-identical render" gate.
 *
 * Grammar law: verb→station mappings come ONLY from show-grammar.yml. With
 * grammar pending (fail-closed default until the Captain merges the v1 PR),
 * officers stand at their desks as static presence markers — text labels
 * still render (labels are not grammar pixels), but no scene is invented.
 * Unknown verbs under loaded grammar use the grammar's OWN fallback mapping
 * (grey-? discipline; the grammar-gap loop names them later).
 */
import type { ShowGrammar } from './grammar'
import type { OfficerPresence, OfficerScene } from './types'
import type { WardroomLayout } from './layout'
import { jitter } from './hash'

/** Logical ticks to cross one tile (integer math — determinism). */
export const TICKS_PER_TILE = 3

export interface OfficerMotion {
  /** Position the current journey started from (tiles). */
  fromX: number
  fromY: number
  /** Journey target station id. */
  stationId: string
  /** Tick the journey began. */
  startTick: number
  /** Last computed position (journey origin for the next retarget). */
  x: number
  y: number
}

export type DirectorState = Record<string, OfficerMotion>

export interface DirectorInput {
  officers: Record<string, OfficerPresence>
  grammar: ShowGrammar | null
  layout: WardroomLayout
  tick: number
}

/** Resolve the target station id for one officer under the grammar law. */
export function targetStation(
  slug: string,
  presence: OfficerPresence,
  grammar: ShowGrammar | null
): { stationId: string; anim: OfficerScene['anim'] } {
  if (!presence.present || !presence.verb) {
    // Activity TTL expired → honestly asleep (chassis: empty desk is true).
    return { stationId: `bunk:${slug}`, anim: 'asleep' }
  }
  if (!grammar) {
    // Grammar pending Captain merge — static presence marker at the desk.
    return { stationId: `desk:${slug}`, anim: 'idle' }
  }
  const mapping = grammar.verbs[presence.verb] ?? grammar.fallback
  const stationId =
    mapping.station === 'desk' ? `desk:${slug}` : mapping.station
  return { stationId, anim: mapping.anim }
}

/**
 * One deterministic step. Officers walk toward their grammar-resolved
 * station at TICKS_PER_TILE; a retarget (verb change) starts a new journey
 * from the current position. Pure: no clocks, no randomness beyond
 * seeded-per-slug cosmetic phase.
 */
export function step(
  state: DirectorState,
  input: DirectorInput
): { state: DirectorState; scenes: OfficerScene[] } {
  const { officers, grammar, layout, tick } = input
  const next: DirectorState = {}
  const scenes: OfficerScene[] = []
  for (const slug of Object.keys(officers).sort()) {
    const presence = officers[slug]
    const desk = layout.desks.get(slug)
    if (!desk) continue
    const { stationId, anim } = targetStation(slug, presence, grammar)
    const station =
      layout.stations.get(stationId) ?? layout.stations.get(desk.id)!

    const prev: OfficerMotion = state[slug] ?? {
      fromX: desk.x,
      fromY: desk.y,
      stationId: desk.id,
      startTick: tick,
      x: desk.x,
      y: desk.y,
    }
    let motion: OfficerMotion = prev
    if (prev.stationId !== stationId) {
      // Retarget: new journey from wherever the officer currently stands.
      // Grammar pending → NO walk scenes (motion is grammar territory):
      // the marker snaps to the target instead of animating a journey.
      motion = grammar
        ? {
            fromX: prev.x,
            fromY: prev.y,
            stationId,
            startTick: tick,
            x: prev.x,
            y: prev.y,
          }
        : {
            fromX: station.x,
            fromY: station.y,
            stationId,
            startTick: tick,
            x: station.x,
            y: station.y,
          }
    }

    const dx = station.x - motion.fromX
    const dy = station.y - motion.fromY
    const dist = Math.sqrt(dx * dx + dy * dy)
    const journeyTicks = Math.max(1, Math.round(dist * TICKS_PER_TILE))
    const elapsed = Math.max(0, tick - motion.startTick)
    const progress = dist === 0 ? 1 : Math.min(1, elapsed / journeyTicks)
    const x = motion.fromX + dx * progress
    const y = motion.fromY + dy * progress
    const arrived = progress >= 1

    next[slug] = { ...motion, x, y }
    scenes.push({
      slug,
      x,
      y,
      stationId,
      anim: arrived ? anim : 'walk',
      verb: presence.present ? presence.verb ?? null : null,
      facing: dx < 0 ? 'left' : 'right',
    })
  }
  return { state: next, scenes }
}

/** Deterministic idle-bob phase for a slug (cosmetic; render-side only). */
export function bobPhase(slug: string): number {
  return jitter(slug, 'bob-phase')
}
