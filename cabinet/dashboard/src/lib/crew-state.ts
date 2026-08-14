/**
 * THE CREW, AS MEASURED — the reader the home card and the wake flow share.
 *
 * Three sources, each answering a different question:
 *   `instance/config/roster.yml`            who was HIRED, and what they are called
 *   `cabinet:heartbeat:<slug>`              who is REPORTING right now
 *   `~/Library/LaunchAgents/com.cabinet.officer.<slug>.plist`
 *                                           who has ever been STARTED on this Mac
 *
 * The third one is the addition. Without it a never-started officer and a dead
 * one are indistinguishable fifteen minutes after death (the heartbeat is
 * written `SETEX … 900`), and the card alarmed about both. `lib/crew.ts`
 * carries the decision and the reasoning; this module only takes the readings.
 *
 * SERVER ONLY.
 */

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import redis from './redis'
import { freshnessOf, type Freshness } from './liveness'
import {
  crewState,
  isFolded,
  wakeableSlugs,
  type CrewMemberInput,
  type CrewState,
  type ExpectedMark,
  type InstallReading,
} from './crew'
import { officerNameSources, readRoster, type RosterMember } from './crew-roster'
import { officerTitle } from './officer-title'

/** Same bar the consumer card has always used: 15 minutes without a beat. */
export const OFFLINE_THRESHOLD_MS = 15 * 60 * 1000

/**
 * When the operator last asked an officer to stop.
 *
 * Written by the sleep affordance (`actions/crew.ts`) and cleared by the wake.
 * It exists because the heartbeat outlives a successful stop by up to its
 * 900-second TTL, so the marker alone cannot say whether a beat is a leftover
 * or proof the stop never took — `lib/crew.ts` carries that reasoning.
 */
export const STOP_REQUESTED_KEY = (slug: string) => `cabinet:officer:stop-requested:${slug}`

/** `com.cabinet.officer.<slug>` — the label `deploy-mac.sh` renders and stops. */
export function officerLabel(slug: string): string {
  return `com.cabinet.officer.${slug}`
}

export function launchAgentsDir(): string {
  return (
    process.env.CABINET_LAUNCHD_DIR ||
    path.join(process.env.HOME || os.homedir(), 'Library', 'LaunchAgents')
  )
}

/**
 * Has anybody installed this officer's background helper on this machine?
 *
 * A missing LaunchAgents DIRECTORY is a measured `absent`, not an unknown: a
 * Mac with no LaunchAgents directory certainly has no officer plist in it, and
 * that is the common shape of a brand-new machine — the exact case this whole
 * distinction exists to render calmly.
 *
 * Anything else that goes wrong (a permissions error, a platform with no
 * launchd) is `unknown` WITH ITS REASON, and `crew.ts` deliberately does not
 * let `unknown` buy the calm answer.
 */
export function readInstall(slug: string): InstallReading {
  if (process.platform !== 'darwin') {
    return {
      state: 'unknown',
      reason: 'this dashboard is not running on the Mac that would hold the background helpers',
    }
  }
  const dir = launchAgentsDir()
  try {
    fs.accessSync(dir)
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ENOENT') return { state: 'absent' }
    return {
      state: 'unknown',
      reason: `the folder that holds background helpers could not be read (${dir})`,
    }
  }
  try {
    fs.accessSync(path.join(dir, `${officerLabel(slug)}.plist`))
    return { state: 'installed' }
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === 'ENOENT') return { state: 'absent' }
    return {
      state: 'unknown',
      reason: 'its background helper file could not be read',
    }
  }
}

function asExpected(raw: string | null): ExpectedMark {
  if (raw === 'active' || raw === 'stopped' || raw === 'suspended') return raw
  return null
}

export interface CrewMember {
  slug: string
  /** The name a human reads. Never a slug shout. */
  name: string
  state: CrewState
  reason: string
  /** Under the fold: expected-quiet crew the operator never has to think about. */
  folded: boolean
  onDemand: boolean
  hired: boolean
  heartbeat: Freshness
  /** Raw `cabinet:officer:activity:<slug>` JSON, for the card's own phrasing. */
  activityRaw: string | null
}

export interface CrewReading {
  members: CrewMember[]
  /** Hired, always-on officers a wake would actually start. */
  wakeable: string[]
  /** TRUE when at least one always-on officer is reporting right now. */
  anyAwake: boolean
  /** TRUE when the visible crew has never been started on this machine. */
  neverWoken: boolean
  /** The store could not be asked. No rows, and the card says so. */
  unreadable: boolean
}

const EMPTY: CrewReading = {
  members: [],
  wakeable: [],
  anyAwake: false,
  neverWoken: false,
  unreadable: true,
}

/**
 * Read the crew.
 *
 * The roster is the SPINE — a hired officer appears even with no store keys at
 * all, which is what makes "not awake yet" renderable on a cabinet where
 * nothing has ever run. Store keys add anyone the roster does not know about
 * (a hand-created officer, a generated lane CEO a preset marked expected), and
 * those arrive `hired: false`, which is what puts them under the fold instead
 * of in the alarm.
 */
export async function readCrew(nowMs: number = Date.now()): Promise<CrewReading> {
  let roster: RosterMember[] = []
  try {
    roster = readRoster()
  } catch {
    roster = []
  }

  let expectedKeys: string[]
  let heartbeatKeys: string[]
  try {
    expectedKeys = await redis.keys('cabinet:officer:expected:*')
    heartbeatKeys = await redis.keys('cabinet:heartbeat:*')
  } catch {
    // A store that did not answer measured nothing about anyone. The roster
    // alone would render every officer as "not awake yet", which is a claim
    // this process cannot support — so it renders nothing and says why.
    return EMPTY
  }

  const byRoster = new Map(roster.map((m) => [m.slug, m]))
  const slugs = new Set<string>(roster.map((m) => m.slug))
  for (const k of expectedKeys) slugs.add(k.replace('cabinet:officer:expected:', ''))
  for (const k of heartbeatKeys) {
    const slug = k.replace('cabinet:heartbeat:', '')
    // `cabinet:heartbeat:liveness:<slug>` is a different plane's key; its
    // remainder is not an officer id and must not become a crew member.
    if (slug.includes(':')) continue
    slugs.add(slug)
  }

  const names = officerNameSources(roster)

  const inputs: CrewMemberInput[] = []
  const members: CrewMember[] = await Promise.all(
    Array.from(slugs).map(async (slug) => {
      const [heartbeatRaw, expectedRaw, activityRaw, stoppedRaw] = await Promise.all([
        redis.get(`cabinet:heartbeat:${slug}`),
        redis.get(`cabinet:officer:expected:${slug}`),
        redis.get(`cabinet:officer:activity:${slug}`),
        redis.get(STOP_REQUESTED_KEY(slug)),
      ])
      // An unparseable stop time is the same as no stop time: `crew.ts` then
      // takes the conservative arm rather than trusting a NaN comparison.
      const stoppedAt = stoppedRaw ? Date.parse(stoppedRaw) : NaN
      const rosterRow = byRoster.get(slug)
      const input: CrewMemberInput = {
        slug,
        heartbeat: freshnessOf(heartbeatRaw, nowMs, OFFLINE_THRESHOLD_MS),
        expected: asExpected(expectedRaw),
        install: readInstall(slug),
        onDemand: rosterRow?.onDemand ?? false,
        hired: Boolean(rosterRow),
        stoppedAtMs: Number.isFinite(stoppedAt) ? stoppedAt : null,
        nowMs,
      }
      inputs.push(input)
      const reading = crewState(input)
      return {
        slug,
        name: officerTitle(slug, names),
        state: reading.state,
        reason: reading.reason,
        folded: isFolded(input, reading),
        onDemand: input.onDemand,
        hired: input.hired,
        heartbeat: input.heartbeat,
        activityRaw,
      }
    })
  )

  members.sort((a, b) => a.slug.localeCompare(b.slug))

  const crew = members.filter((m) => !m.folded)
  return {
    members,
    // From the SAME inputs the states were read from, via the same predicate
    // the tests drive — not a second derivation off the roster that could
    // disagree with the rows on screen.
    wakeable: wakeableSlugs(inputs).sort(),
    anyAwake: members.some((m) => m.state === 'awake'),
    neverWoken: crew.length > 0 && crew.every((m) => m.state === 'not-awake-yet'),
    unreadable: false,
  }
}
