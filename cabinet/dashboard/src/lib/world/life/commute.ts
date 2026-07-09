/**
 * T2 LIFE — the dominant-focus commute (unified spec v2 §3.4/§12 v1a;
 * direction doc world-unified-direction-2026-07-08 §3).
 *
 * An officer's avatar LIVES in the district their actual work currently
 * belongs to — Harvestholm (village, self-work) or Lantern Quay (quay,
 * mission/product work) — and switching is a visible 20–30 s walk down the
 * one road. This module is the CLASSIFIER + REDUCER only: pure functions of
 * (chronicle records, presence verb, snapshot timestamp, logical tick).
 *
 * Determinism contract (ratchets test #4): no wall clock — "now" is the
 * SERVER-stamped snapshot ts arriving as data; the logical tick is the only
 * time axis; no randomness (classification is pure aggregation, fnv1a-free
 * by design — direction §3.3).
 *
 * Anti-ping-pong law (v1a acceptance, spec §12): switch only when the
 * target district holds ≥ SWITCH_SHARE of the recency-weighted vote for
 * SWITCH_EVALS consecutive evaluations AND ≥ MIN_DWELL since last arrival;
 * the classifier is SUSPENDED mid-walk (no U-turns) and holds position on
 * TTL-expired presence (absence of a verb is never evidence of a move).
 *
 * Thought bubble (Captain T2 ruling 2026-07-09 + ratified grammar v3
 * `commute.bubble: verb_icon`): the bubble is a PIXEL bubble in world
 * space — NOT a DOM chip — and it renders the classified verb's ICON only
 * (never free text in world-space; typography law §9.2). The verb is the
 * REAL verb that flipped the classifier — never invented; the closed
 * VERB_GLOSS phrase + lane slug live on the DOM inspect card, where free
 * text is lawful. Unknown verb → NO bubble (honest absence).
 */
import type { ChronicleRecord } from '../types'

export type District = 'village' | 'quay'

// ── constants (1 tick = 250 ms) ─────────────────────────────────────────────
export const TICKS_PER_SECOND = 4
/** Dominant-focus window (Captain: 2–3 min → 150 s). */
export const COMMUTE_WINDOW_S = 150
/** Recency half-life inside the window: w = 0.5^(age/75s). */
export const COMMUTE_HALF_LIFE_S = 75
/** Classifier evaluation cadence (every 15 s on the logical tick). */
export const EVAL_EVERY_TICKS = 15 * TICKS_PER_SECOND
/** Target district must hold ≥ this share of weighted votes to switch. */
export const SWITCH_SHARE = 0.6
/** …for this many consecutive evaluations… */
export const SWITCH_EVALS = 2
/** …and at least this long since the last arrival (180 s min-dwell). */
export const MIN_DWELL_TICKS = 180 * TICKS_PER_SECOND
/** Full road walk: ~40 tiles × TICKS_PER_TILE(3) = 120 ticks ≈ 30 s. The
 * Captain's 20–30 s emerges from distance ÷ speed, never a timer. */
export const ROAD_WALK_TICKS = 120
/** Crossroads passing glance hold (direction §3.4). */
export const PASS_GLANCE_TICKS = 4

// ── §3.2 closed vote vocabularies ───────────────────────────────────────────
/** Presence verbs with an intrinsic quay vote (hook-stamped vocabulary is
 * otherwise district-neutral — direction §3.2). */
const QUAY_PRESENCE_VERBS = new Set(['deploying', 'shipping'])
/** Chronicle verbs that vote QUAY when lane ≠ system-self. */
const QUAY_EVENT_VERBS = new Set([
  'work.completed',
  'work.assigned',
  'task.created',
  'task.completed',
  'mission.created',
])
/** Lanes that vote VILLAGE (self-work). */
const VILLAGE_LANES = new Set(['system-self', 'captains-cabinet'])
/** Chronicle verbs that vote VILLAGE (loop/skill/fidelity/trust-shaped). */
const VILLAGE_EVENT_VERBS = new Set([
  'loop.started',
  'loop.completed',
  'skill.promoted',
  'fidelity.evaluated',
  'fidelity.scored',
  'trust.transition',
  'trust.unfrozen',
  'policy.shadowed',
  'world.grammar_gap',
])

/**
 * One chronicle record → one district vote (or null = neutral).
 * Product lanes arrive as DATA (instance/config/projects/*.yml roster) —
 * this module hardcodes no launcher's lane names beyond the framework's own
 * system-self/captains-cabinet self-lanes.
 */
export function voteFor(
  record: ChronicleRecord,
  productLanes: ReadonlySet<string>
): District | null {
  const lane = record.attrs?.lane
  // §3.2 exception first: work.*/task.* carrying lane system-self votes
  // VILLAGE — self-lane evidence beats the verb's quay shape.
  if (lane && VILLAGE_LANES.has(lane)) return 'village'
  if (lane && productLanes.has(lane)) return 'quay'
  if (VILLAGE_EVENT_VERBS.has(record.verb)) return 'village'
  if (QUAY_EVENT_VERBS.has(record.verb)) return 'quay'
  return null // session.*, comms.*, tool.call without lane, unknown
}

export interface FocusEvidence {
  district: District | null
  /** Dominant district's share of the weighted vote (0 when no votes). */
  share: number
  votes: { village: number; quay: number }
  /** Strongest-weighted evidence for the dominant district — the REAL verb
   * behind the thought bubble (never invented). */
  trigger: { verb: string; lane: string | null } | null
}

/**
 * Recency-weighted dominant focus over the last COMMUTE_WINDOW_S of this
 * officer's chronicle, plus the presence verb as one standing vote (it is
 * the freshest signal). Pure aggregation — deterministic by construction.
 */
export function dominantFocus(
  slug: string,
  records: ChronicleRecord[],
  presenceVerb: string | null | undefined,
  nowTsMs: number,
  productLanes: ReadonlySet<string>
): FocusEvidence {
  const votes = { village: 0, quay: 0 }
  let best: { w: number; verb: string; lane: string | null; d: District } | null =
    null
  for (const r of records) {
    if (r.actor !== slug || !r.ts) continue
    const t = Date.parse(r.ts)
    if (Number.isNaN(t)) continue
    const age = Math.max(0, (nowTsMs - t) / 1000)
    if (age > COMMUTE_WINDOW_S) continue
    const d = voteFor(r, productLanes)
    if (!d) continue
    const w = Math.pow(0.5, age / COMMUTE_HALF_LIFE_S)
    votes[d] += w
    if (!best || w > best.w || (w === best.w && d !== best.d && votes[d] > votes[best.d])) {
      best = { w, verb: r.verb, lane: r.attrs?.lane ?? null, d }
    }
  }
  if (presenceVerb && QUAY_PRESENCE_VERBS.has(presenceVerb)) {
    votes.quay += 1
    if (!best || 1 >= best.w) {
      best = { w: 1, verb: presenceVerb, lane: null, d: 'quay' }
    }
  }
  const total = votes.village + votes.quay
  if (total === 0) return { district: null, share: 0, votes, trigger: null }
  const district: District = votes.quay > votes.village ? 'quay' : 'village'
  const share = votes[district] / total
  const trigger =
    best && best.d === district
      ? { verb: best.verb, lane: best.lane }
      : presenceVerb && VERB_GLOSS[presenceVerb]
        ? { verb: presenceVerb, lane: null }
        : null
  return { district, share, votes, trigger }
}

// ── the thought bubble (closed table; pixel-rendered) ───────────────────────

/**
 * CLOSED verb → phrase table (direction §3.4). Deterministic, zero free
 * text, zero PII. A verb absent here renders NO bubble — the closed table
 * is the whole vocabulary. The KEYS double as the pixel-icon vocabulary
 * (renderer maps verb → owned icon tile); the phrases appear only on the
 * DOM inspect card (world-space carries no text — §9.2).
 */
export const VERB_GLOSS: Record<string, string> = {
  working: 'get back to it',
  editing: 'finish the edit',
  testing: 'run the tests',
  investigating: 'dig into it',
  researching: 'read up on it',
  reviewing: 'review the queue',
  coordinating: 'sync the crew',
  deploying: 'ship this',
  shipping: 'ship this',
  replying: 'answer the mail',
  'loop.started': 'start the loop',
  'loop.completed': 'write up the retro',
  'skill.promoted': 'shelve the new skill',
  'fidelity.evaluated': 'check the scores',
  'fidelity.scored': 'check the scores',
  'trust.transition': 'consult the charter',
  'trust.unfrozen': 'consult the charter',
  'policy.shadowed': 'consult the charter',
  'world.grammar_gap': 'name the unknown',
  'work.assigned': 'pick up the task',
  'work.completed': 'log the win',
  'task.created': 'plan the task',
  'task.completed': 'close it out',
  'mission.created': 'chart the mission',
}

/** Identifier-safe lane slug — anything else is dropped, never rendered. */
const LANE_RE = /^[a-z0-9][a-z0-9-]{0,23}$/

export interface BubbleSpec {
  /**
   * The REAL classifier-flipping verb — a key of VERB_GLOSS (closed set).
   * The renderer maps it to an owned pixel icon inside the bubble; the
   * verb never renders as world-space text.
   */
  verb: string
  /** Closed-table phrase for the DOM inspect card ONLY (never world-space). */
  cardText: string
  /**
   * Render class per ratified grammar v3 (`commute.bubble: verb_icon`): a
   * PIXEL bubble in world space carrying the verb's ICON — never a DOM
   * chip, never free text.
   */
  kind: 'verb_icon'
}

/** Bubble for the trigger evidence — null when the verb is off-table. */
export function bubbleFor(
  trigger: { verb: string; lane: string | null } | null
): BubbleSpec | null {
  if (!trigger) return null
  const gloss = VERB_GLOSS[trigger.verb]
  if (!gloss) return null
  const lane =
    trigger.lane && LANE_RE.test(trigger.lane) ? ` · ${trigger.lane}` : ''
  return {
    verb: trigger.verb,
    cardText: `I should ${gloss}${lane}`,
    kind: 'verb_icon',
  }
}

/** Integer pixel box for the icon bubble at ×1 (16-px icon + 2-px frame +
 * 4-px tail). Constant — icons never reflow; renderer scales by integer LOD. */
export const BUBBLE_BOX_PX = { w: 20, h: 22 } as const

export function bubbleBoxPx(_spec: BubbleSpec): { w: number; h: number } {
  return { ...BUBBLE_BOX_PX }
}

// ── the commute reducer ─────────────────────────────────────────────────────

export interface CommuteWalk {
  from: District
  to: District
  startTick: number
  walkTicks: number
  bubble: BubbleSpec | null
}

export interface CommuteState {
  /** District of residence — updates only on ARRIVAL (mid-walk keeps from). */
  district: District
  /** Switch candidate under the consecutive-evals rule. */
  candidate: District | null
  heldEvals: number
  lastArrivalTick: number
  lastEvalTick: number
  walking: CommuteWalk | null
}

/** Fresh officers live in Harvestholm (the village IS the org's home; the
 * egg has no quay work yet). Dwell is pre-satisfied so a clearly
 * quay-classified officer commutes after the ordinary 2-eval hold. */
export function initialCommuteState(): CommuteState {
  return {
    district: 'village',
    candidate: null,
    heldEvals: 0,
    lastArrivalTick: -MIN_DWELL_TICKS,
    lastEvalTick: -1,
    walking: null,
  }
}

export interface CommuteStepInput {
  slug: string
  records: ChronicleRecord[]
  presenceVerb: string | null | undefined
  /** Server-stamped snapshot timestamp (ms epoch) — time as DATA. */
  nowTsMs: number
  tick: number
  productLanes: ReadonlySet<string>
  /** Road journey length in ticks (engine passes the real path length). */
  walkTicks?: number
  /** Grammar-PR constant overrides (ratified v3 commute block values —
   * defaults below ARE the ratified values; the law wins if they differ). */
  switchShare?: number
  switchEvals?: number
  minDwellTicks?: number
}

export interface CommuteStepResult {
  state: CommuteState
  /** Set on the tick a walk begins (the departure — engine stages it). */
  departed: CommuteWalk | null
  /** Set on the tick a walk completes. */
  arrived: District | null
}

/**
 * One deterministic classifier step. Same records + presence + ticks in →
 * same walks out, forever (v1a acceptance replays a recorded chronicle
 * window through exactly this function).
 */
export function commuteStep(
  state: CommuteState,
  input: CommuteStepInput
): CommuteStepResult {
  const { tick } = input
  const walkTicks = input.walkTicks ?? ROAD_WALK_TICKS
  const switchShare = input.switchShare ?? SWITCH_SHARE
  const switchEvals = input.switchEvals ?? SWITCH_EVALS
  const minDwellTicks = input.minDwellTicks ?? MIN_DWELL_TICKS

  // Mid-walk: classifier suspended (no U-turns) — direction §3.3.
  if (state.walking) {
    if (tick - state.walking.startTick >= state.walking.walkTicks) {
      const to = state.walking.to
      return {
        state: {
          ...state,
          district: to,
          walking: null,
          candidate: null,
          heldEvals: 0,
          lastArrivalTick: tick,
        },
        departed: null,
        arrived: to,
      }
    }
    return { state, departed: null, arrived: null }
  }

  // Evaluate every EVAL_EVERY_TICKS on the logical tick (modulo — replay-
  // stable regardless of reducer start tick); never twice on one tick.
  if (tick % EVAL_EVERY_TICKS !== 0 || tick === state.lastEvalTick) {
    return { state, departed: null, arrived: null }
  }

  // TTL-expired presence: stay where you are (idle program / sleep is the
  // states module's story). Candidate resets — absence is not evidence.
  if (!input.presenceVerb) {
    return {
      state: { ...state, candidate: null, heldEvals: 0, lastEvalTick: tick },
      departed: null,
      arrived: null,
    }
  }

  const focus = dominantFocus(
    input.slug,
    input.records,
    input.presenceVerb,
    input.nowTsMs,
    input.productLanes
  )

  let candidate = state.candidate
  let heldEvals = state.heldEvals
  if (
    focus.district &&
    focus.district !== state.district &&
    focus.share >= switchShare
  ) {
    if (candidate === focus.district) heldEvals += 1
    else {
      candidate = focus.district
      heldEvals = 1
    }
  } else {
    candidate = null
    heldEvals = 0
  }

  if (
    candidate &&
    heldEvals >= switchEvals &&
    tick - state.lastArrivalTick >= minDwellTicks
  ) {
    const walk: CommuteWalk = {
      from: state.district,
      to: candidate,
      startTick: tick,
      walkTicks,
      bubble: bubbleFor(focus.trigger),
    }
    return {
      state: {
        ...state,
        walking: walk,
        candidate: null,
        heldEvals: 0,
        lastEvalTick: tick,
      },
      departed: walk,
      arrived: null,
    }
  }

  return {
    state: { ...state, candidate, heldEvals, lastEvalTick: tick },
    departed: null,
    arrived: null,
  }
}

/** Road progress 0..1 for a walk at a tick (engine maps onto the road
 * polyline; village→quay walks run 0→1, quay→village walks 1→0). */
export function commuterProgress(walk: CommuteWalk, tick: number): number {
  const p = (tick - walk.startTick) / walk.walkTicks
  return Math.min(1, Math.max(0, p))
}

/**
 * Crossroads passing glance (direction §3.4): two commuters heading in
 * OPPOSITE directions within ε of each other in road-progress space face
 * each other for PASS_GLANCE_TICKS. Pure — both walks are deterministic,
 * so co-presence is computable.
 */
export function passingGlance(
  a: { walk: CommuteWalk; tick: number },
  b: { walk: CommuteWalk; tick: number }
): boolean {
  if (a.walk.to === b.walk.to) return false
  const pa = commuterProgress(a.walk, a.tick)
  const pb = commuterProgress(b.walk, b.tick)
  // Opposite walks share the road coordinate: village→quay progress p maps
  // to road position p; quay→village maps to 1−p.
  const posA = a.walk.to === 'quay' ? pa : 1 - pa
  const posB = b.walk.to === 'quay' ? pb : 1 - pb
  return Math.abs(posA - posB) <= PASS_GLANCE_TICKS / ROAD_WALK_TICKS
}

/** Honesty codex for any walking officer (direction §3.6). */
export const COMMUTE_CODEX =
  `District = dominant class of this officer's last ${COMMUTE_WINDOW_S} s of ` +
  `chronicled verbs (recency-weighted, half-life ${COMMUTE_HALF_LIFE_S} s; switch at ` +
  `≥${SWITCH_SHARE} share held ${SWITCH_EVALS} evaluations, ≥${MIN_DWELL_TICKS / TICKS_PER_SECOND} s dwell). ` +
  `The walk is a re-classification, not a claim the officer 'went somewhere'.`
