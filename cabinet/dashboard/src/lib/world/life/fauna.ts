/**
 * T2 LIFE — fauna per the NPC population law (unified spec v2 §15.5,
 * Captain addendum 1.2): FAUNA freely allowed as joy-honest ambience —
 * fly-by birds, butterflies, quay fish, the pettable cat (and the dog,
 * already law) — each answers inspect honestly: "carries no data — exists
 * for joy". HUMAN-SHAPED sprites are real actors only (apprentices.ts).
 *
 * Everything here is a PURE function of (id, tick, anchors, clockHour):
 * seeded via fnv1a, no wall clock, no randomness, no state, no writes.
 * clockHour arrives as snapshot DATA (server-stamped) and gates the
 * day-only kinds; absent clock → day-only fauna stays home (fail-closed
 * to honesty, matching the director's no-clock night rule).
 *
 * "Petting" the cat is a CLIENT-ONLY seeded reaction riding the inspect
 * click — zero state, zero writes (bestiary §6, adopted). Exactly one cat
 * and one dog, forever: scarcity keeps the bound/decorative boundary
 * legible.
 */
import { fnv1a } from '../hash'

export type FaunaKind = 'bird' | 'butterfly' | 'fish' | 'cat' | 'dog' | 'chicken'

export interface FaunaSprite {
  id: string
  kind: FaunaKind
  /** Tile-space position (floats — sub-tile motion is the charm). */
  x: number
  y: number
  /** Anim frame — pure f(tick). */
  frame: number
  facing: 'left' | 'right'
  layer: 'air' | 'ground' | 'water'
}

export interface FaunaInput {
  tick: number
  /** Captain-local hour from the snapshot (null/undefined = unknown). */
  clockHour?: number | null
  /** World bounds in tiles (birds cross it; nothing renders outside). */
  bounds: { w: number; h: number }
  /** Flower/meadow anchors — butterflies orbit these (cap applies). */
  flowerAnchors: Array<{ x: number; y: number }>
  /** Quay-water anchors — fish jump here (cap applies). */
  quayWater: Array<{ x: number; y: number }>
  /** The one cat's perch (null = no cat placed yet). */
  catPerch?: { x: number; y: number } | null
  /** The one dog's perch (cozy pass 2026-07-09 — pack sleep-art landed;
   * null = no Great House porch yet). Exactly one dog, forever. */
  dogPerch?: { x: number; y: number } | null
  /** Chicken-yard spots (pens/barn yard) — a flock, never a crowd. */
  chickenSpots?: Array<{ x: number; y: number }>
  /** Optional salt so two deployments never share fauna schedules. */
  seedSalt?: string
}

// ── day gate (mirrors director DAY_START/END — fauna sleeps at night) ──────
export const FAUNA_DAY_START = 8
export const FAUNA_DAY_END = 20

function isDay(clockHour: number | null | undefined): boolean {
  return (
    typeof clockHour === 'number' &&
    clockHour >= FAUNA_DAY_START &&
    clockHour < FAUNA_DAY_END
  )
}

// ── birds: seeded fly-bys ───────────────────────────────────────────────────
export const BIRD_SLOTS = 3
/** Tiles per tick — a lazy glide. */
export const BIRD_SPEED = 0.2
/** Min/max seconds between one slot's fly-bys (seeded inside the band). */
const BIRD_PERIOD_MIN_TICKS = 1800 // 7.5 min
const BIRD_PERIOD_SPAN_TICKS = 1200 // …to 12.5 min

function birdAt(
  slot: number,
  tick: number,
  bounds: { w: number; h: number },
  salt: string
): FaunaSprite | null {
  const seed = `${salt}bird:${slot}`
  const period =
    BIRD_PERIOD_MIN_TICKS + (fnv1a(`${seed}:period`) % BIRD_PERIOD_SPAN_TICKS)
  const phase = fnv1a(`${seed}:phase`) % period
  const t = (tick + phase) % period
  const span = bounds.w + 8 // enter/exit fully offscreen
  const flightTicks = Math.ceil(span / BIRD_SPEED)
  if (t >= flightTicks) return null
  const cycle = Math.floor((tick + phase) / period)
  const dirRight = fnv1a(`${seed}:dir:${cycle}`) % 2 === 0
  const alt =
    2 + (fnv1a(`${seed}:alt:${cycle}`) % Math.max(1, Math.floor(bounds.h / 3)))
  const along = t * BIRD_SPEED
  const x = dirRight ? -4 + along : bounds.w + 4 - along
  // Gentle seeded bob — pure sinusoid on the tick.
  const y = alt + Math.sin((tick + phase) / 9) * 0.4
  return {
    id: `fauna:bird:${slot}`,
    kind: 'bird',
    x,
    y,
    frame: Math.floor(tick / 3) % 2, // flap
    facing: dirRight ? 'right' : 'left',
    layer: 'air',
  }
}

// ── butterflies: lissajous around flower anchors ────────────────────────────
export const BUTTERFLY_CAP = 4

function butterflyAt(
  i: number,
  anchor: { x: number; y: number },
  tick: number,
  salt: string
): FaunaSprite {
  const seed = `${salt}butterfly:${i}`
  const p1 = fnv1a(`${seed}:p1`) % 97
  const p2 = fnv1a(`${seed}:p2`) % 89
  const dx = Math.sin((tick + p1) / 13) * 1.4 + Math.sin((tick + p2) / 5) * 0.4
  const dy = Math.cos((tick + p2) / 11) * 0.9 + Math.sin((tick + p1) / 7) * 0.3
  return {
    id: `fauna:butterfly:${i}`,
    kind: 'butterfly',
    x: anchor.x + dx,
    y: anchor.y + dy,
    frame: Math.floor(tick / 2) % 2,
    facing: Math.cos((tick + p1) / 13) >= 0 ? 'right' : 'left',
    layer: 'air',
  }
}

// ── quay fish: seeded jump arcs ─────────────────────────────────────────────
export const FISH_CAP = 3
export const FISH_JUMP_TICKS = 12
const FISH_PERIOD_MIN_TICKS = 900 // 3.75 min
const FISH_PERIOD_SPAN_TICKS = 900

function fishAt(
  i: number,
  anchor: { x: number; y: number },
  tick: number,
  salt: string
): FaunaSprite | null {
  const seed = `${salt}fish:${i}`
  const period =
    FISH_PERIOD_MIN_TICKS + (fnv1a(`${seed}:period`) % FISH_PERIOD_SPAN_TICKS)
  const phase = fnv1a(`${seed}:phase`) % period
  const t = (tick + phase) % period
  if (t >= FISH_JUMP_TICKS) return null
  const u = t / FISH_JUMP_TICKS // 0..1 across the arc
  const cycle = Math.floor((tick + phase) / period)
  const dirRight = fnv1a(`${seed}:dir:${cycle}`) % 2 === 0
  return {
    id: `fauna:fish:${i}`,
    kind: 'fish',
    x: anchor.x + (dirRight ? u : -u) * 1.2,
    y: anchor.y - 4 * 0.8 * u * (1 - u), // parabolic arc, 0.8-tile apex
    frame: u < 0.5 ? 0 : 1,
    facing: dirRight ? 'right' : 'left',
    layer: 'water',
  }
}

// ── chickens: seeded peck loop in the pens yard ─────────────────────────────
export const CHICKEN_CAP = 3
export const CHICKEN_WINDOW = 48 // 12 s per posture window

export type ChickenAnim = 'idle' | 'walk' | 'peck'

/** frame encodes anim row * 8 + subframe (renderer: row=frame>>3, sub=&7). */
export function chickenAnimOf(frame: number): { anim: ChickenAnim; sub: number } {
  const row = frame >> 3
  return { anim: row === 0 ? 'idle' : row === 1 ? 'walk' : 'peck', sub: frame & 7 }
}

function chickenAt(
  i: number,
  spot: { x: number; y: number },
  tick: number,
  salt: string
): FaunaSprite {
  const seed = `${salt}chicken:${i}`
  const w = Math.floor((tick + (fnv1a(`${seed}:phase`) % 31)) / CHICKEN_WINDOW)
  const roll = fnv1a(`${seed}:${w}`) % 10
  // mostly pecking about, sometimes a small seeded wander step
  const anim: ChickenAnim = roll < 5 ? 'peck' : roll < 8 ? 'idle' : 'walk'
  const dx =
    anim === 'walk'
      ? (((fnv1a(`${seed}:dx:${w}`) % 3) - 1) * ((tick % CHICKEN_WINDOW) / CHICKEN_WINDOW)) * 0.8
      : 0
  const sub = Math.floor(tick / 6) % (anim === 'peck' ? 4 : 2)
  const row = anim === 'idle' ? 0 : anim === 'walk' ? 1 : 2
  return {
    id: `fauna:chicken:${i}`,
    kind: 'chicken',
    x: spot.x + dx,
    y: spot.y,
    frame: row * 8 + sub,
    facing: fnv1a(`${seed}:face:${w}`) % 2 === 0 ? 'left' : 'right',
    layer: 'ground',
  }
}

// ── the dog: asleep on the Great House porch (pack sleep frames) ────────────
function dogAt(
  perch: { x: number; y: number },
  tick: number,
  salt: string
): FaunaSprite {
  return {
    id: 'fauna:dog',
    kind: 'dog',
    x: perch.x,
    y: perch.y,
    // slow breathing loop over the two pack sleep frames
    frame: Math.floor(tick / 16) % 2,
    facing: fnv1a(`${salt}dog:facing`) % 2 === 0 ? 'left' : 'right',
    layer: 'ground',
  }
}

// ── the cat: perch loop + client-only pet reaction ──────────────────────────
export const CAT_LOOP_WINDOW = 64 // 16 s per posture window
export const PET_REACTION_TICKS = 12

export type CatPosture = 'sit' | 'tail_flick' | 'loaf'

export function catPosture(tick: number, salt = ''): CatPosture {
  const w = Math.floor(tick / CAT_LOOP_WINDOW)
  const r = fnv1a(`${salt}cat:${w}`) % 8
  return r < 4 ? 'sit' : r < 6 ? 'loaf' : 'tail_flick'
}

function catAt(
  perch: { x: number; y: number },
  tick: number,
  salt: string
): FaunaSprite {
  const posture = catPosture(tick, salt)
  return {
    id: 'fauna:cat',
    kind: 'cat',
    x: perch.x,
    y: perch.y,
    // Frame encodes the posture row; tail_flick animates 2 frames.
    frame:
      posture === 'sit' ? 0 : posture === 'loaf' ? 2 : 4 + (Math.floor(tick / 4) % 2),
    facing: fnv1a(`${salt}cat:facing`) % 2 === 0 ? 'left' : 'right',
    layer: 'ground',
  }
}

/**
 * CLIENT-ONLY pet reaction: the inspect click captures the logical tick it
 * happened on; for PET_REACTION_TICKS after it the cat shows a seeded
 * heart-wiggle. Zero state, zero writes — the reaction is a pure function
 * of (clickTick, tick) and vanishes on its own.
 */
export function petReaction(
  clickTick: number | null,
  tick: number
): { active: boolean; frame: number } {
  if (clickTick === null || tick < clickTick) return { active: false, frame: 0 }
  const dt = tick - clickTick
  if (dt >= PET_REACTION_TICKS) return { active: false, frame: 0 }
  return { active: true, frame: Math.floor(dt / 3) % 2 }
}

// ── inspect: a creature answers through the GROUND card, and only that ──────
//
// THERE WAS A `faunaCard(kind)` HERE, and it was a dead twin — deleted
// 2026-07-30 after an audit found it had no production consumer in EITHER
// kernel, only its own tests. `PickKind` has no fauna member: no click anywhere
// in the world can name a creature, so nothing could ever open what it built.
// What a click on a creature actually gets is the pick's `ground` fallback,
// whose card reads "ground / water — carries no data" and is flagged
// `decorative: true` (engine-client.tsx) — which is the same promise
// show-grammar.yml §15.5 makes ("carries no data — exists for joy"), minus the
// joy, and the grammar's own `codex.represents` per species carries the rest.
//
// It is not stubbed and not commented out. A card function nobody can open is a
// claim surface asserting the world answers something it does not, and this
// programme has paid for that class repeatedly. WHEN FAUNA IS PORTED to iso
// (BACKLOG: the fauna row), the pick kind and the card land in the SAME unit or
// neither lands — re-deriving thirty lines of copy is free; shipping the promise
// without the path is not.

/**
 * All fauna visible at a tick — pure and deterministic. Day-only kinds
 * (birds, butterflies) require a known daytime clockHour; fish and the cat
 * live at all hours.
 */
export function faunaAt(input: FaunaInput): FaunaSprite[] {
  const salt = input.seedSalt ? `${input.seedSalt}:` : ''
  const out: FaunaSprite[] = []
  if (isDay(input.clockHour)) {
    for (let s = 0; s < BIRD_SLOTS; s++) {
      const b = birdAt(s, input.tick, input.bounds, salt)
      if (b) out.push(b)
    }
    input.flowerAnchors.slice(0, BUTTERFLY_CAP).forEach((a, i) => {
      out.push(butterflyAt(i, a, input.tick, salt))
    })
  }
  input.quayWater.slice(0, FISH_CAP).forEach((a, i) => {
    const f = fishAt(i, a, input.tick, salt)
    if (f) out.push(f)
  })
  if (isDay(input.clockHour)) {
    ;(input.chickenSpots ?? []).slice(0, CHICKEN_CAP).forEach((s, i) => {
      out.push(chickenAt(i, s, input.tick, salt))
    })
  }
  if (input.catPerch) out.push(catAt(input.catPerch, input.tick, salt))
  if (input.dogPerch) out.push(dogAt(input.dogPerch, input.tick, salt))
  return out
}
