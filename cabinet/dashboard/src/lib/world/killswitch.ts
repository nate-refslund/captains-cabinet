/**
 * THE EMERGENCY STOP, AS A READING — three states, never two.
 *
 * WHY THIS FILE EXISTS. The world drew the killswitch from a plain boolean, and
 * every failure path produced `false`:
 *
 *   app/api/world/stream/route.ts   killswitch: false            (no Redis at all)
 *   app/api/world/stream/route.ts   presence?.killswitch ?? false (absent/unparseable)
 *   app/api/world/engine/route.ts   let killswitch = false        (catch swallows)
 *   app/(authenticated)/layout.tsx  value === 'active'            (throws, or mock '')
 *
 * `false` renders the lever UP, the sky calm and the header pill "Stop All" —
 * pixel-identical to a stop the org VERIFIED is not engaged. So "I cannot read
 * the emergency stop" and "the emergency stop is off" were the same picture, on
 * the highest-stakes surface in the system.
 *
 * The enforcement plane never made this mistake. `cabinet/scripts/hooks/
 * killswitch-read.sh` is the ONE reader and returns three verdicts —
 * CLEAR / ACTIVE / INDETERMINATE — because (measured against redis 8.8) a bare
 * `redis-cli GET` prints NOAUTH/NOPERM/WRONGTYPE/LOADING on stdout and exits 0,
 * so "the answer was not the string active" is the absence of evidence, not
 * evidence of absence. Its contract says it in words: INDETERMINATE must behave
 * exactly like ACTIVE for anything that acts, and be REPORTED DISTINCTLY —
 * "he has to be able to tell 'stopped' from 'I cannot tell', and must never be
 * shown 'inactive' for either". The Swift companion (`cabinet/companion/
 * main.swift:315`) already carries `Bool?` for exactly this reason. The
 * dashboard was the one consumer that flattened it.
 *
 * VOCABULARY. Deliberately the same dialect as the attention-census fix
 * (`lib/attention/queue.ts`, `lib/attention/glance.ts`, PR #328): a NULL rather
 * than a value, an `unknownReason` in plain checkable words, and ONE decision
 * function every skin renders from. A second dialect for the same idea is how
 * one of them rots.
 *
 * CLIENT-SAFE BY CONSTRUCTION — zero imports. `killswitch-lever.tsx` is a
 * `'use client'` component; the census fix learned the hard way that pulling a
 * module with `node:fs` in its import graph into a client component breaks the
 * Turbopack client bundle outright (every page 500) while `tsc` and the whole
 * vitest suite stay green. Nothing node-only may ever be imported here.
 */

/** What a surface draws. `clear` is reachable ONLY from a real reading. */
export type KillswitchGlance =
  | { state: 'engaged' }
  | { state: 'clear' }
  | { state: 'unknown'; reason: string }

/**
 * A reading of the emergency stop.
 *
 * `engaged: null` = nobody obtained a reading. There is deliberately no
 * zero-valued constant to reach for — every unknown is built WITH its reason by
 * `unknownKillswitch`, so the reason cannot be forgotten the way the old
 * `?? false` forgot that it was guessing.
 */
export interface KillswitchReading {
  /** true = engaged · false = VERIFIED not engaged · null = nobody knows. */
  engaged: boolean | null
  /** Why nothing was measured, in plain words. Null on a measured reading. */
  unknownReason: string | null
}

/**
 * Freshness bar for the presence snapshot.
 *
 * `cabinet:world:presence` is SET with EX 60 by the chronicle daemon every
 * CABINET_WORLD_TICK_S (2s default), so a key that exists is ≤60s old and this
 * bar should never fire in a healthy world. It exists because the census pass
 * proved the opposite assumption: an unbounded-age reading rendered as a
 * current one is exactly what a staleness bar is for, and "the TTL guarantees
 * it" is a property of a deployment, not of the parser.
 */
export const PRESENCE_MAX_AGE_MS = 90_000

/**
 * Tolerated forward clock skew. A stamp further ahead than this means the clock
 * that wrote it and the clock reading it disagree by more than the freshness
 * window, so the age is not knowable — same arm the census carries.
 */
export const PRESENCE_MAX_SKEW_MS = 90_000

/** What the Captain runs to settle it out of band. Prints STOPPED, never INACTIVE. */
export const KILLSWITCH_CHECK_COMMAND = 'cabinet/scripts/kill-switch.sh status'

/** A reading that measured nothing, and says so. */
export function unknownKillswitch(reason: string): KillswitchReading {
  return { engaged: null, unknownReason: reason }
}

/** A reading that measured something. */
export function measuredKillswitch(engaged: boolean): KillswitchReading {
  return { engaged, unknownReason: null }
}

/**
 * The three-way decision every skin renders from — the ONE place it is made.
 *
 * A surface that switches on `active === true ? … : …` re-invents the defect
 * the moment someone adds a skin, so consumers take the GLANCE, never the
 * boolean: a tagged union cannot be coerced to "off" by a stray `??`.
 */
export function killswitchGlance(
  engaged: boolean | null | undefined,
  reason?: string | null
): KillswitchGlance {
  if (engaged === true) return { state: 'engaged' }
  if (engaged === false) return { state: 'clear' }
  return {
    state: 'unknown',
    reason: reason || 'nothing measured the emergency stop',
  }
}

/** Convenience: the glance straight off a reading. */
export function glanceOf(r: KillswitchReading): KillswitchGlance {
  return killswitchGlance(r.engaged, r.unknownReason)
}

/**
 * The lever word, ALREADY A STRING — defence in depth, and the reason it lives
 * here rather than inline in the component. A surface that loses its unknown
 * branch (a stray `??`, a refactor, a new skin) still cannot print "UP" for a
 * reading nobody took: the worst it can do is print UNKNOWN. Static ratchets
 * could not stop that mutation; a value that never carries the word can.
 */
export function killswitchWord(g: KillswitchGlance): string {
  return g.state === 'engaged' ? 'THROWN' : g.state === 'clear' ? 'UP' : 'UNKNOWN'
}

/** Dual-coded glyph (never colour alone). `?` is the honest-absence mark. */
export function killswitchGlyph(g: KillswitchGlance): string {
  return g.state === 'engaged' ? '↓' : g.state === 'clear' ? '↑' : '?'
}

/** The `data-world-lever` attribute — the frame harness and DOM probes read it. */
export function killswitchAttr(g: KillswitchGlance): string {
  return g.state === 'engaged' ? 'thrown' : g.state === 'clear' ? 'up' : 'unknown'
}

/** One plain sentence for a hover title / aria-label. Never says "off". */
export function killswitchTitle(g: KillswitchGlance): string {
  if (g.state === 'engaged') return 'killswitch lever — THROWN (fleet halted)'
  if (g.state === 'clear') return 'killswitch lever — up (fleet running)'
  return `killswitch lever — UNKNOWN: ${g.reason}. Not "off" — unread. Check: ${KILLSWITCH_CHECK_COMMAND}`
}

/**
 * The intent an actuation must pin, or NULL when there is nothing to pin it to.
 *
 * The lever used to send `toggleKillSwitch(active ? 'deactivate' : 'activate')`.
 * Under an unknown reading that expression is a coin flip DERIVED FROM THE
 * GUESS — it would have sent "activate" for a switch that might already be
 * armed, or worse. Null here forces the surface to ask which way, rather than
 * inventing a direction from a state it does not have.
 */
export function intentFor(
  g: KillswitchGlance
): 'activate' | 'deactivate' | null {
  if (g.state === 'engaged') return 'deactivate'
  if (g.state === 'clear') return 'activate'
  return null
}

/** The exact CLI the Captain can run instead, per intent. */
export function fallbackCommandFor(intent: 'activate' | 'deactivate'): string {
  return `cabinet/scripts/kill-switch.sh ${intent}`
}

// ── the readers ─────────────────────────────────────────────────────────────

const NO_STORE_REASON =
  'no store was reached — the world could not ask anything about the emergency stop'

/**
 * The reason for a dashboard that is not talking to the fleet's store.
 *
 * Split in two (2026-07-31) because the single string became FALSE for half
 * the cases it covered. It read "…it is showing demo data, not the fleet" and
 * was used for BOTH postures — but an unconfigured dashboard no longer shows
 * demo data at all, it shows honest absences, so the banner was making a claim
 * about the page that the page had stopped being true of. A wrong sentence in
 * the unknown-reason slot is the same defect one level down.
 */
export const NO_STORE_CONFIGURED_REASON =
  'this dashboard has no store configured (REDIS_URL unset), so it has never asked the fleet anything about the emergency stop'

export const DEMO_STORE_REASON =
  'this dashboard is showing demo data (an explicit non-production opt-in), not the fleet — nothing here was read from your cabinet'


/**
 * The reading carried by the chronicle daemon's presence snapshot.
 *
 * The daemon reads through the ONE shared reader and, since 2026-07-31, writes
 * its verdict verbatim as `killswitch_verdict`. Before that it wrote only the
 * boolean `killswitch = verdict != "CLEAR"` — fail-closed for behaviour but
 * LOSSY for reporting, because it folded INDETERMINATE into the same `true` as
 * a genuinely armed stop. Both shapes are handled; the legacy `true` is read as
 * engaged (that is what the daemon meant by it) and the ambiguity is why the
 * verdict field exists.
 *
 * Every degenerate end is an arm here rather than a hope: not an object, no
 * timestamp, an unparseable timestamp, a FUTURE timestamp, a stale one, an
 * unrecognised verdict, and a snapshot carrying no emergency-stop field at all.
 */
export function readingFromPresence(
  presence: unknown,
  nowMs: number
): KillswitchReading {
  if (typeof presence !== 'object' || presence === null || Array.isArray(presence)) {
    return unknownKillswitch(
      'the world could not read the presence snapshot that carries the emergency stop'
    )
  }
  const p = presence as Record<string, unknown>

  const stamped = typeof p.ts === 'string' ? Date.parse(p.ts) : NaN
  if (!Number.isFinite(stamped)) {
    return unknownKillswitch(
      'the presence snapshot carries no readable timestamp, so how old its emergency-stop reading is cannot be established'
    )
  }
  const ageMs = nowMs - stamped
  if (ageMs > PRESENCE_MAX_AGE_MS) {
    return unknownKillswitch(
      `the presence snapshot stopped updating ${humanAgeMs(ageMs)} ago (it is rewritten every couple of seconds) — its emergency-stop reading is not current`
    )
  }
  if (-ageMs > PRESENCE_MAX_SKEW_MS) {
    return unknownKillswitch(
      'the presence snapshot is stamped in the future — the clock that wrote it and this one disagree, so the age of its emergency-stop reading cannot be established'
    )
  }

  const verdict = p.killswitch_verdict
  if (typeof verdict === 'string') {
    if (verdict === 'ACTIVE') return measuredKillswitch(true)
    if (verdict === 'CLEAR') return measuredKillswitch(false)
    if (verdict === 'INDETERMINATE') {
      return unknownKillswitch(
        'the emergency-stop reader could not get a verifiable answer from the control plane (auth, permission, wrong type, loading or timeout) — treat it as stopped until it can'
      )
    }
    return unknownKillswitch(
      'the presence snapshot carries an unrecognised emergency-stop verdict'
    )
  }

  // Legacy snapshots: the boolean alone.
  if (p.killswitch === true) return measuredKillswitch(true)
  if (p.killswitch === false) return measuredKillswitch(false)
  return unknownKillswitch(
    'the presence snapshot carries no emergency-stop reading'
  )
}

/**
 * The reading from a direct GET of `cabinet:killswitch`.
 *
 * `contacted` is the caller's own proof that a live client answered: an ioredis
 * client REJECTS on NOAUTH/NOPERM/WRONGTYPE/LOADING rather than resolving them
 * as data (which is what defeated the shell readers), so a resolved `null`
 * after a successful round trip really is an absent key. A throw, a missing
 * client, or a store nobody configured is not a reading at all.
 *
 * Any value other than the literal `active` is UNKNOWN, not clear — the same
 * closed-enum rule the shared reader applies (`killswitch-read.sh`:
 * "unrecognised value" ⇒ INDETERMINATE). This also catches the mock store's
 * seeded `''`, which used to render as a confident "not engaged".
 */
export function readingFromKey(
  value: string | null,
  contacted: boolean,
  notContactedReason: string = NO_STORE_REASON
): KillswitchReading {
  if (!contacted) return unknownKillswitch(notContactedReason)
  if (value === null) return measuredKillswitch(false)
  if (value === 'active') return measuredKillswitch(true)
  return unknownKillswitch(
    'the emergency-stop key holds an unrecognised value — the store answered, but not with a state this cabinet knows'
  )
}

/** How long ago, in the words the Captain's surfaces already use. */
export function humanAgeMs(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000))
  if (s < 90) return `${s}s`
  const m = Math.round(s / 60)
  if (m < 90) return `${m} min`
  const h = m / 60
  if (h < 48) return `${h.toFixed(1)}h`
  return `${(h / 24).toFixed(1)} days`
}
