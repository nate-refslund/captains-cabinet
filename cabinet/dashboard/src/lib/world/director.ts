/**
 * The deterministic director — pure TS reducer, vitest-tested, NO wall clock.
 *
 * Contract (E0/E1 determinism gate): the director is a pure REDUCER —
 * step(state, input) → { state, scenes }. The logical tick is a monotonic
 * integer the render loop advances from frame deltas; the director never
 * reads a wall clock or an unseeded RNG — the CI ratchet greps this tree
 * for those calls. Feeding two directors the identical input sequence
 * yields identical scene sequences, forever — which is exactly the "same
 * chronicle twice → frame-identical render" gate. Wall-clock time enters
 * ONLY as data on the SSE snapshot (`clockHour`); the killswitch enters the
 * same way.
 *
 * Grammar law: verb→station mappings and every v2 behavior (idle_program
 * wander, group_scenes, killswitch freeze) come ONLY from show-grammar.yml.
 * With grammar pending (fail-closed default), officers stand at their desks
 * as static presence markers — text labels still render (labels are not
 * grammar pixels), but no scene is invented, no walk, no chips.
 *
 * BEHAVIOR VOCABULARY (world-alive direction 2026-07-08 §1):
 *  - desk verbs get seeded MICRO-LOOPS (type/stretch/sip/glance) — cosmetic
 *    phenotype inside the work anim, never an activity claim;
 *  - TTL-expired + day (08–20 captain-local) → idle_program wander over the
 *    grammar's waypoints, walked on the walkable grid (path.ts BFS);
 *  - TTL-expired + night (or no clock data) → bunk, asleep, blinking z chip;
 *  - ≥2 officers on a group_scenes verb → seeded seats at the table;
 *  - killswitch → the reducer FREEZES: state passes through untouched and
 *    the last-known scenes re-emit (frozen mid-stride is the point);
 *  - every loop is PHASE-STAGGERED via fnv1a(slug, salt) so no two officers
 *    move in lockstep (sync reads as fake; stagger reads as alive).
 */
import type { ShowGrammar } from './grammar'
import type {
  OfficerPresence,
  OfficerScene,
  SceneChip,
  SceneFacing,
  SceneMicro,
} from './types'
import type { WardroomLayout } from './layout'
import { TABLE_SEAT_OFFSETS } from './layout'
import { fnv1a, jitter } from './hash'
import { blockedTiles, findPath, isWalkable, pathLength, pointAlong } from './path'

/** Logical ticks to cross one tile (integer math — determinism). */
export const TICKS_PER_TILE = 3

// ── behavior constants (§1; 1 tick = 250ms) ────────────────────────────────
/** Micro-loop quantum (~4s). */
export const MICRO = 16
/** One micro-loop window (~32s): a seeded roll per window picks the loop. */
export const MICRO_WINDOW = 8 * MICRO
/** Stretch hold (ticks). */
export const STRETCH_TICKS = 6
/** Glance hold (ticks). */
export const GLANCE_TICKS = 4
/** Sip excursion span (walk to the kettle, pause, walk back) in ticks. */
export const SIP_TICKS = 48
/** Wander walk budget per leg (ticks) — dwell rides on top. */
export const WANDER_WALK_BUDGET = 96
/** Distinct dwell rolls per wander cycle (leg kinds). */
const WANDER_LEG_KINDS = 4
/** Day window for idle wander (captain-local hours, §1.2). */
export const DAY_START_HOUR = 8
export const DAY_END_HOUR = 20
/** Sleep chip blink period: on for the first half of each period (§1.4). */
export const ZZZ_PERIOD = 24
/** Max tile distance for two idle officers to read as chatting (§1.2). */
export const PAIR_DIST = 2

export interface OfficerMotion {
  /** Journey target station id (logical — includes wander/seat targets). */
  stationId: string
  /** Journey target tile. */
  targetX: number
  targetY: number
  /** Walk polyline: exact start position + grid waypoints + target. */
  path: Array<{ x: number; y: number }>
  /** Total polyline length in tiles. */
  pathLen: number
  /** Tick the journey began. */
  startTick: number
  /** Last computed position. */
  x: number
  y: number
  /** Last emitted anim/facing — replayed verbatim under killswitch freeze. */
  anim: OfficerScene['anim']
  facing: SceneFacing
}

export type DirectorState = Record<string, OfficerMotion>

export interface DirectorInput {
  officers: Record<string, OfficerPresence>
  grammar: ShowGrammar | null
  layout: WardroomLayout
  tick: number
  /** Captain-local hour from the snapshot clock (server-stamped; null = unknown). */
  clockHour?: number | null
  /** cabinet:killswitch — freezes the director (grammar killswitch_scene). */
  killswitch?: boolean
}

/** Resolve the target station id for one officer under the grammar law
 * (v1 base mapping — step() layers wander/group/micro behavior on top). */
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

/** Where an officer wants to be this tick, plus arrival posture. */
interface Intent {
  stationId: string
  x: number
  y: number
  anim: OfficerScene['anim']
  facing: SceneFacing
  micro: SceneMicro
  chip: SceneChip
  /** Set when this intent is an idle_program wander leg (chat pairing). */
  waypointKey: string | null
}

function isDayHour(clockHour: number | null | undefined): boolean {
  return (
    typeof clockHour === 'number' &&
    clockHour >= DAY_START_HOUR &&
    clockHour < DAY_END_HOUR
  )
}

/** Micro-loop roll for a slug + window (exported for test cross-checks). */
export function microRoll(slug: string, window: number): number {
  return fnv1a(`${slug}:${window}`) % 16
}

/** Deterministic wander leg for (slug, tick): leg index + waypoint pick. */
export function wanderLeg(
  slug: string,
  tick: number,
  dwellTicks: number,
  waypointCount: number
): { legIndex: number; waypointIndex: number } {
  const legTicks: number[] = []
  let cycleLen = 0
  for (let j = 0; j < WANDER_LEG_KINDS; j++) {
    const t = WANDER_WALK_BUDGET + dwellTicks + (fnv1a(`${slug}:dwell:${j}`) % 16)
    legTicks.push(t)
    cycleLen += t
  }
  // Phase-stagger per officer so wander loops never sync across the room.
  const t = tick + (fnv1a(`${slug}:wander-phase`) % cycleLen)
  const cycleIdx = Math.floor(t / cycleLen)
  let rem = t - cycleIdx * cycleLen
  let j = 0
  while (j < WANDER_LEG_KINDS - 1 && rem >= legTicks[j]) {
    rem -= legTicks[j]
    j++
  }
  const legIndex = cycleIdx * WANDER_LEG_KINDS + j
  return {
    legIndex,
    waypointIndex: fnv1a(`${slug}:wander:${legIndex}`) % waypointCount,
  }
}

/**
 * Collision-free seeded seat: every participant hashes a preferred seat,
 * conflicts resolve by linear probing in sorted-slug order — deterministic,
 * no two officers share a seat (§1.3).
 */
export function seatFor(slug: string, participants: string[]): number | null {
  const occupied = new Set<number>()
  for (const s of [...participants].sort()) {
    let seat = fnv1a(`${s}:seat`) % TABLE_SEAT_OFFSETS.length
    while (occupied.has(seat)) {
      seat = (seat + 1) % TABLE_SEAT_OFFSETS.length
      if (occupied.size >= TABLE_SEAT_OFFSETS.length) return null
    }
    occupied.add(seat)
    if (s === slug) return seat
  }
  return null
}

function resolveIntent(
  slug: string,
  presence: OfficerPresence,
  grammar: ShowGrammar,
  layout: WardroomLayout,
  tick: number,
  clockHour: number | null | undefined,
  groupSlugs: string[],
  blocked: Set<string>
): Intent {
  const desk = layout.desks.get(slug)!
  const bunk = layout.bunks.get(slug)

  const expired = !presence.present || !presence.verb
  if (expired) {
    const ip = grammar.idleProgram
    const waypoints = (ip?.waypoints ?? []).filter((w) =>
      layout.stations.has(w)
    )
    if (ip && waypoints.length > 0 && isDayHour(clockHour)) {
      // §1.2 day: seeded wander — the honest render of "session alive, no
      // tool call in 5 min". Walk waypoint to waypoint, dwell, repeat.
      const { legIndex, waypointIndex } = wanderLeg(
        slug,
        tick,
        ip.dwellTicks,
        waypoints.length
      )
      const wpId = waypoints[waypointIndex]
      const wp = layout.stations.get(wpId)!
      // Small seeded stand offset so co-visiting officers don't stack.
      const wobble = (fnv1a(`${slug}:wob:${legIndex}`) % 3) - 1
      const tx = isWalkable({ x: wp.x + wobble, y: wp.y }, blocked)
        ? wp.x + wobble
        : wp.x
      const gazeUp = wpId.startsWith('window') || wpId === 'bookshelf'
      return {
        stationId: `wander:${wpId}:${legIndex}`,
        x: tx,
        y: wp.y,
        anim: 'idle',
        facing: gazeUp ? 'up' : 'down',
        micro: null,
        chip: null,
        waypointKey: wpId,
      }
    }
    // Night (or no clock data, or no idle_program): honestly asleep (§1.4).
    const rest = bunk ?? desk
    const zPhase = fnv1a(`${slug}:z`) % ZZZ_PERIOD
    const blink = (tick + zPhase) % ZZZ_PERIOD < ZZZ_PERIOD / 2
    return {
      stationId: rest.id,
      x: rest.x,
      y: rest.y,
      anim: 'asleep',
      facing: 'down',
      micro: null,
      chip: blink ? 'zzz' : null,
      waypointKey: null,
    }
  }

  const verb = presence.verb!
  // §1.3 group scene: ≥min officers on the same grouped verb → table seats.
  const group = grammar.groupScenes?.[verb]
  const groupStation = group ? layout.stations.get(group.station) : undefined
  if (group && groupStation && groupSlugs.length >= group.minOfficers) {
    const seat = seatFor(slug, groupSlugs)
    if (seat !== null) {
      const off = TABLE_SEAT_OFFSETS[seat]
      return {
        stationId: `seat:${group.station}:${seat}`,
        x: groupStation.x + off.dx,
        y: groupStation.y + off.dy,
        anim: 'idle',
        facing:
          off.dy > 0 ? 'up' : off.dy < 0 ? 'down' : off.dx < 0 ? 'right' : 'left',
        micro: null,
        chip: null,
        waypointKey: null,
      }
    }
  }

  const mapping = grammar.verbs[verb] ?? grammar.fallback
  if (mapping.station === 'desk') {
    // §1.1 desk verbs: micro-loops on a seeded window schedule. Typing
    // dominates; stretch/sip/glance are brief seeded interruptions.
    const phase = fnv1a(`${slug}:micro`) % MICRO_WINDOW
    const t = tick + phase
    const w = Math.floor(t / MICRO_WINDOW)
    const tIn = t % MICRO_WINDOW
    const r = microRoll(slug, w)
    if ((r === 10 || r === 11) && tIn < STRETCH_TICKS) {
      return {
        stationId: desk.id,
        x: desk.x,
        y: desk.y,
        anim: mapping.anim,
        facing: 'up',
        micro: 'stretch',
        chip: null,
        waypointKey: null,
      }
    }
    if (r === 12 && tIn < SIP_TICKS && layout.stations.has('kettle')) {
      // Kettle absent → fail to nothing, never to invention (§1.1).
      const kettle = layout.stations.get('kettle')!
      return {
        stationId: 'kettle',
        x: kettle.x,
        y: kettle.y,
        anim: 'idle',
        facing: 'down',
        micro: 'sip',
        chip: null,
        waypointKey: null,
      }
    }
    if (r === 13 && tIn < GLANCE_TICKS) {
      return {
        stationId: desk.id,
        x: desk.x,
        y: desk.y,
        anim: mapping.anim,
        facing: fnv1a(`${slug}:${w}:g`) % 2 === 0 ? 'left' : 'right',
        micro: 'glance',
        chip: null,
        waypointKey: null,
      }
    }
    return {
      stationId: desk.id,
      x: desk.x,
      y: desk.y,
      anim: mapping.anim,
      facing: 'down',
      micro: null,
      chip: null,
      waypointKey: null,
    }
  }
  // Civic verb: clean, higher-salience — no micro-loops (§1.1).
  const station = layout.stations.get(mapping.station) ?? desk
  return {
    stationId: station.id,
    x: station.x,
    y: station.y,
    anim: mapping.anim,
    facing: 'up',
    micro: null,
    chip: null,
    waypointKey: null,
  }
}

/**
 * One deterministic step. Officers walk toward their resolved station along
 * the walkable grid at TICKS_PER_TILE; a retarget (verb change, wander leg,
 * micro-loop excursion) starts a new journey from the current position —
 * transitions are ALWAYS walked, never teleported (grammar-pending snap is
 * the single sanctioned exception). Pure: no clocks, no randomness beyond
 * seeded-per-slug phases.
 */
export function step(
  state: DirectorState,
  input: DirectorInput
): { state: DirectorState; scenes: OfficerScene[] } {
  const { officers, grammar, layout, tick, clockHour, killswitch } = input

  // §1.5 killswitch: the director halts — positions/anims re-emit verbatim
  // (officers frozen mid-stride). Each frozen tick shifts startTick forward
  // so in-flight journeys resume EXACTLY where they froze on reset (no
  // teleport on unfreeze).
  if (killswitch) {
    const frozen: DirectorState = {}
    const scenes: OfficerScene[] = []
    for (const slug of Object.keys(state)) {
      frozen[slug] = { ...state[slug], startTick: state[slug].startTick + 1 }
    }
    for (const slug of Object.keys(officers).sort()) {
      const m = state[slug]
      if (!m || !layout.desks.has(slug)) continue
      const presence = officers[slug]
      scenes.push({
        slug,
        x: m.x,
        y: m.y,
        stationId: m.stationId,
        anim: m.anim,
        verb: presence.present ? presence.verb ?? null : null,
        facing: m.facing,
        micro: null,
        chip: null,
      })
    }
    return { state: frozen, scenes }
  }

  const blocked = blockedTiles(layout)

  // Present-officer slugs per verb (group-scene trigger + seat assignment).
  const slugsByVerb: Record<string, string[]> = {}
  for (const slug of Object.keys(officers).sort()) {
    const p = officers[slug]
    if (p.present && p.verb && layout.desks.has(slug)) {
      ;(slugsByVerb[p.verb] ??= []).push(slug)
    }
  }

  const next: DirectorState = {}
  const scenes: OfficerScene[] = []
  const intents = new Map<string, Intent>()

  for (const slug of Object.keys(officers).sort()) {
    const presence = officers[slug]
    const desk = layout.desks.get(slug)
    if (!desk) continue

    let intent: Intent
    if (!grammar) {
      // Grammar pending — static presence markers only (v1 fail-closed).
      const expired = !presence.present || !presence.verb
      const rest = layout.bunks.get(slug) ?? desk
      intent = expired
        ? {
            stationId: rest.id,
            x: rest.x,
            y: rest.y,
            anim: 'asleep',
            facing: 'down',
            micro: null,
            chip: null,
            waypointKey: null,
          }
        : {
            stationId: desk.id,
            x: desk.x,
            y: desk.y,
            anim: 'idle',
            facing: 'down',
            micro: null,
            chip: null,
            waypointKey: null,
          }
    } else {
      intent = resolveIntent(
        slug,
        presence,
        grammar,
        layout,
        tick,
        clockHour,
        presence.present && presence.verb
          ? slugsByVerb[presence.verb] ?? []
          : [],
        blocked
      )
    }
    intents.set(slug, intent)

    const prev: OfficerMotion = state[slug] ?? {
      stationId: desk.id,
      targetX: desk.x,
      targetY: desk.y,
      path: [{ x: desk.x, y: desk.y }],
      pathLen: 0,
      startTick: tick,
      x: desk.x,
      y: desk.y,
      anim: 'idle',
      facing: 'down',
    }

    let motion = prev
    if (prev.stationId !== intent.stationId) {
      if (!grammar) {
        // Grammar pending → NO walk scenes (motion is grammar territory):
        // the marker snaps to the target instead of animating a journey.
        motion = {
          stationId: intent.stationId,
          targetX: intent.x,
          targetY: intent.y,
          path: [{ x: intent.x, y: intent.y }],
          pathLen: 0,
          startTick: tick,
          x: intent.x,
          y: intent.y,
          anim: prev.anim,
          facing: prev.facing,
        }
      } else {
        // Retarget: new grid journey from wherever the officer stands.
        const start = { x: prev.x, y: prev.y }
        const tiles = findPath(layout, start, { x: intent.x, y: intent.y })
        const pts = tiles
          ? [start, ...tiles]
          : [start, { x: intent.x, y: intent.y }]
        motion = {
          stationId: intent.stationId,
          targetX: intent.x,
          targetY: intent.y,
          path: pts,
          pathLen: pathLength(pts),
          startTick: tick,
          x: prev.x,
          y: prev.y,
          anim: prev.anim,
          facing: prev.facing,
        }
      }
    }

    const totalTicks = Math.max(1, Math.round(motion.pathLen * TICKS_PER_TILE))
    const elapsed = Math.max(0, tick - motion.startTick)
    const arrived = motion.pathLen === 0 || elapsed >= totalTicks

    let x: number
    let y: number
    let anim: OfficerScene['anim']
    let facing: SceneFacing
    let micro: SceneMicro = null
    let chip: SceneChip = null
    if (arrived) {
      x = motion.targetX
      y = motion.targetY
      anim = intent.anim
      facing = intent.facing
      micro = intent.micro
      chip = intent.chip
    } else {
      const dist = (elapsed / totalTicks) * motion.pathLen
      const p = pointAlong(motion.path, dist)
      x = p.x
      y = p.y
      anim = 'walk'
      facing =
        Math.abs(p.dx) >= Math.abs(p.dy)
          ? p.dx < 0
            ? 'left'
            : 'right'
          : p.dy < 0
            ? 'up'
            : 'down'
    }

    next[slug] = { ...motion, x, y, anim, facing }
    scenes.push({
      slug,
      x,
      y,
      stationId: intent.stationId,
      anim,
      verb: presence.present ? presence.verb ?? null : null,
      facing,
      micro,
      chip,
    })
  }

  // §1.2 chat pairing: two idle wanderers on the same waypoint within
  // PAIR_DIST tiles face each other + share a DOM ellipsis chip. Pairing is
  // computable because both schedules are seeded (deterministic co-presence).
  if (grammar?.idleProgram?.chatChip) {
    const byWaypoint = new Map<string, OfficerScene[]>()
    for (const s of scenes) {
      const intent = intents.get(s.slug)
      if (intent?.waypointKey && s.anim !== 'walk') {
        const list = byWaypoint.get(intent.waypointKey) ?? []
        list.push(s)
        byWaypoint.set(intent.waypointKey, list)
      }
    }
    for (const group of byWaypoint.values()) {
      group.sort((a, b) => (a.slug < b.slug ? -1 : 1))
      for (let i = 0; i + 1 < group.length; i += 2) {
        const a = group[i]
        const b = group[i + 1]
        const d = Math.hypot(a.x - b.x, a.y - b.y)
        if (d > PAIR_DIST) continue
        a.chip = 'ellipsis'
        b.chip = 'ellipsis'
        if (a.x <= b.x) {
          a.facing = 'right'
          b.facing = 'left'
        } else {
          a.facing = 'left'
          b.facing = 'right'
        }
        next[a.slug] = { ...next[a.slug], facing: a.facing }
        next[b.slug] = { ...next[b.slug], facing: b.facing }
      }
    }
  }

  return { state: next, scenes }
}

/** Deterministic idle-bob phase for a slug (cosmetic; render-side only). */
export function bobPhase(slug: string): number {
  return jitter(slug, 'bob-phase')
}
