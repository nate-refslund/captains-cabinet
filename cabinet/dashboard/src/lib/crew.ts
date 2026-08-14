/**
 * IS THIS CREW MEMBER BROKEN, OR HAS NOBODY STARTED IT YET — the difference
 * a fresh operator saw as an alarm.
 *
 * WHAT THIS FIXES. A newly hatched cabinet has never deployed an officer on
 * this machine: the hatch stops short of launchd by default, so nothing has
 * ever run. The home card read that as `🔴 First Mate is offline`, which to a
 * human means BROKEN — on a cabinet whose only fault was that nobody had
 * pressed anything yet. "Offline" is the right word for an officer that WAS
 * running and is gone; it is the wrong word for one that has never been asked
 * to start.
 *
 * WHY A HEARTBEAT ALONE CANNOT TELL THEM APART. `start-officer-mac.sh` writes
 * `cabinet:heartbeat:<slug>` with `SETEX … 900`, so a dead officer's heartbeat
 * key VANISHES fifteen minutes after it dies. From that moment an officer that
 * crashed and an officer that never existed are byte-identical in the store.
 * Any rule derived from the heartbeat alone must therefore either alarm about
 * both or reassure about both, and the card chose to alarm.
 *
 * THE SECOND SIGNAL, and why it is the honest one: `cabinet-doctor.sh` already
 * asks it — is the officer's LaunchAgent INSTALLED (`~/Library/LaunchAgents/
 * com.cabinet.officer.<slug>.plist`)? That file exists if and only if somebody
 * ran the move-in for this officer on this Mac. It is exactly what the wake
 * flow creates and what `deploy-mac.sh --stop` deliberately leaves behind. So:
 * no plist and no heartbeat = never started (calm); a plist and no heartbeat =
 * it was started and it is not reporting (alarm).
 *
 * THE DEGENERATE END IS ITS OWN ANSWER. An install reading that could not be
 * taken — the LaunchAgents directory unreadable, a runtime that has no launchd
 * at all — does NOT buy the calm state. It cannot distinguish the two cases
 * either, so it says `unknown` and says why. A sensor that fails toward
 * reassurance is the failure this whole file exists to avoid, one direction
 * over from the one it fixes.
 *
 * PURE + CLIENT-SAFE BY CONSTRUCTION: zero imports, no clock, no `fs`, no
 * store. Every input is passed in, so every arm is reproducible from a fixed
 * instant, and both the server card and any client surface can share it.
 */

import type { Freshness } from './liveness'

/**
 * Did anybody ever install this officer's background helper on this machine?
 *
 * `absent` is a MEASUREMENT (we looked, and there is no plist). `unknown` is
 * the absence of one, and the two are deliberately different answers — the
 * same distinction `lib/liveness.ts` draws between a missing heartbeat and an
 * unreadable one.
 */
export type InstallReading =
  | { state: 'installed' }
  | { state: 'absent' }
  | { state: 'unknown'; reason: string }

/**
 * What the expectation marker in the store says the operator last asked for.
 * `active` is what a hatch seeds (`load-preset.sh`), `stopped` is what the
 * sleep affordance writes, `suspended` is `suspend-officer.sh`. `null` = no
 * marker.
 */
export type ExpectedMark = 'active' | 'stopped' | 'suspended' | null

export type CrewState =
  /** A current heartbeat. It is working. */
  | 'awake'
  /** It ran, or was told to run, and is not reporting. THIS is the alarm. */
  | 'quiet'
  /** Nobody has ever started it on this machine. Calm — the wake flow's job. */
  | 'not-awake-yet'
  /** The operator put it to sleep. Calm — a deliberate act, not a fault. */
  | 'resting'
  /** Told to stop, and STILL reporting. The other alarm, and the worse one. */
  | 'stop-failed'
  /** On-demand by design (a consultant): started per trigger, never keepalive. */
  | 'on-call'
  /** Something could not be measured, and pretending either way would invent it. */
  | 'unknown'

export interface CrewMemberInput {
  slug: string
  /** Freshness of `cabinet:heartbeat:<slug>`, already resolved by the caller. */
  heartbeat: Freshness
  /** `cabinet:officer:expected:<slug>`, verbatim. */
  expected: ExpectedMark
  /**
   * When the operator asked this officer to stop (epoch ms), or null.
   *
   * WHY A TIME AND NOT JUST THE MARKER. The heartbeat is written `SETEX … 900`,
   * so for a quarter of an hour after a successful stop there is still a FRESH
   * heartbeat in the store. Ranking "it is reporting" above "you stopped it"
   * made the card say `🟢 First Mate is planning your first week` in the same
   * frame as `Your crew is asleep` — caught by driving the flow, 2026-08-14.
   * Ranking the marker above the heartbeat instead would resurrect the defect
   * `actions/officers.ts` is written about: a card reading "stopped" over an
   * agent that is still running and still acting.
   *
   * Neither ordering is right, because they are answers to different
   * questions. The comparison is: a heartbeat OLDER than the stop is a
   * leftover, and a heartbeat NEWER than it means the stop did not take.
   */
  stoppedAtMs: number | null
  /** This instant, so every arm is reproducible from a fixed clock. */
  nowMs: number
  /** Is `com.cabinet.officer.<slug>.plist` installed on this machine? */
  install: InstallReading
  /** Roster `type: consultant` — an on-demand officer with no keepalive job. */
  onDemand: boolean
  /** Present in `instance/config/roster.yml`. False = generated but never hired. */
  hired: boolean
}

export interface CrewMemberReading {
  slug: string
  state: CrewState
  /** Why, in the words a reader needs. Empty for `awake`, which speaks for itself. */
  reason: string
}

/**
 * The ONE decision. Ordered so that every arm is defensible on its own:
 *
 *  1. a current heartbeat outranks every expectation — an officer that is
 *     reporting IS working, whatever any marker says;
 *  2. an unreadable heartbeat is unknown, never a health claim;
 *  3. a STALE heartbeat proves it ran, so its absence of life is a fault (or a
 *     deliberate stop) — never "never started";
 *  4. with no heartbeat at all, the expectation marker, then the roster shape,
 *     then the install reading decide; and only a MEASURED absence of the
 *     install buys the calm never-started answer.
 */
export function crewState(input: CrewMemberInput): CrewMemberReading {
  const { slug, heartbeat, expected, install, onDemand, stoppedAtMs, nowMs } = input
  const stopped = expected === 'stopped' || expected === 'suspended'

  // An unreadable stamp is unknown before anything else is decided: no arm
  // below may treat "we could not read it" as evidence in either direction.
  if (heartbeat.state === 'unknown') {
    return { slug, state: 'unknown', reason: heartbeat.reason }
  }

  if (stopped) {
    // Did it beat AFTER we told it to stop?  With no recorded stop time we
    // cannot say, and the safe direction is to surface the anomaly rather than
    // reassure: a stop that silently did not take is the worse of the two
    // errors. (`suspend-officer.sh` records no time; the sleep affordance does.)
    const beatAfterStop =
      heartbeat.state === 'fresh' &&
      (stoppedAtMs === null || nowMs - heartbeat.ageMs > stoppedAtMs)
    if (beatAfterStop) {
      return {
        slug,
        state: 'stop-failed',
        reason: 'it was asked to stop and is still reporting',
      }
    }
    return { slug, state: 'resting', reason: 'you put this one to sleep' }
  }

  if (heartbeat.state === 'fresh') return { slug, state: 'awake', reason: '' }

  if (heartbeat.state === 'stale') {
    return {
      slug,
      state: 'quiet',
      reason: 'it was running and has stopped reporting',
    }
  }

  // No heartbeat at all from here down.

  if (onDemand) {
    return {
      slug,
      state: 'on-call',
      reason: 'this one is on call — it starts when there is work for it',
    }
  }

  if (install.state === 'absent') {
    return {
      slug,
      state: 'not-awake-yet',
      reason: 'nothing has started it on this Mac yet',
    }
  }

  if (install.state === 'unknown') {
    return {
      slug,
      state: 'unknown',
      reason: `whether this one has ever been started here could not be established — ${install.reason}`,
    }
  }

  return {
    slug,
    state: 'quiet',
    reason: 'its background helper is installed but it is not reporting',
  }
}

/**
 * TRUE only for a state that should draw the operator's eye as a FAULT.
 *
 * ONE predicate, three consumers: the card's red mark, the card's "See
 * details" link, and `isFolded` below. Restating "quiet or stop-failed" at
 * each of them is how a fourth state gets added and quietly renders calm at
 * one of the three.
 */
export function isAlarming(state: CrewState): boolean {
  return state === 'quiet' || state === 'stop-failed'
}

/**
 * Belongs under the fold rather than in the crew list.
 *
 * WHAT THIS IS FOR. A fresh portfolio hatch generates a lane CEO for the
 * placeholder lane the operator never renamed, and a lane CEO is a
 * `type: consultant` — an on-demand session with no keepalive job at all, which
 * `cabinet-doctor.sh` already SKIPs rather than calls dead. Listing it beside
 * the First Mate with a red dot alarms about a crew member the operator never
 * chose and which is behaving exactly as designed.
 *
 * The rule names no lane, no slug and no product — it is structural: a member
 * is folded when it is not part of the always-on crew (on-demand, or generated
 * but never hired into `roster.yml`). Anything that is WORKING or WRONG is
 * never folded: the fold hides expected quiet, never a fault.
 */
export function isFolded(input: CrewMemberInput, reading: CrewMemberReading): boolean {
  // Working, wrong, or unmeasured is never folded — the fold hides expected
  // quiet, never a fault and never a thing nobody could read.
  if (reading.state === 'awake' || reading.state === 'unknown') return false
  if (isAlarming(reading.state)) return false
  return input.onDemand || !input.hired
}

/**
 * ONE STEP of a wake or a sleep, as the operator sees it.
 *
 * These live HERE, in the pure module, rather than beside the server action
 * that produces them: a `'use server'` file is a POST-endpoint manifest, and a
 * client component that imports from it for two interfaces is one bundler
 * change away from pulling a server module into the browser. The pure module
 * has no `node:` imports at all, so it is safe on both sides by construction.
 */
export interface CrewStep {
  /** Stable id for list keys; never shown. */
  id: string
  /** What is happening, in the words the operator reads. */
  label: string
  ok: boolean
  /** The script's own last line — folded away in the UI unless asked for. */
  detail: string
}

export interface CrewOpOutcome {
  ok: boolean
  /** One plain sentence, rendered verbatim — so it is written to be read. */
  message: string
  steps: CrewStep[]
}

/**
 * Which of the crew a wake would actually start — used by `readCrew` to fill
 * `CrewReading.wakeable`, which is what decides whether the card offers the
 * control at all.
 *
 * Consultants are excluded because `deploy-mac.sh` REFUSES them without
 * `--force` (a keepalive LaunchAgent contradicts the on-demand lifecycle), so
 * counting them would promise something the wake cannot deliver.
 */
export function wakeableSlugs(members: CrewMemberInput[]): string[] {
  return members.filter((m) => m.hired && !m.onDemand).map((m) => m.slug)
}
