/**
 * Card 1: YOUR CABINET — Spec 032 Consumer Mode. Server component.
 *
 * WHAT CHANGED, AND WHY (2026-08-14). A freshly hatched cabinet showed
 * `🔴 First Mate is offline · See details`. Red plus "offline" reads as BROKEN,
 * and nothing was broken: the hatch stops short of launchd, so nobody had ever
 * started that officer. An officer that has never been asked to run is a
 * different fact from one that ran and died, and this card now says so — and,
 * because a state with no way out is just a nicer dead end, it carries the one
 * control that resolves it.
 *
 * Three renderings where there used to be one:
 *   NEVER STARTED   a quiet neutral chip and one primary action, "Wake your
 *                   Cabinet". No colour, because there is no fault.
 *   ASLEEP          the operator stopped it. Also quiet, also no fault.
 *   STOPPED REPORTING  it ran, or its helper is installed, and it is silent.
 *                   That is the red alarm, and it keeps "See details".
 *
 * The reading itself — including WHY a heartbeat alone cannot tell the first
 * from the third — is in `lib/crew.ts` and `lib/crew-state.ts`.
 *
 * AND THE CREW NOBODY CHOSE. A portfolio hatch generates a lane CEO for the
 * placeholder lane; it is an on-demand consultant with no keepalive job, so it
 * is silent BY DESIGN. It used to sit beside the First Mate with a red dot and
 * a title-cased slug for a name. It is now named after its lane (see
 * `lib/officer-title.ts`) and lives under a fold, which never hides anything
 * that is working or wrong.
 *
 * Data sources:
 *   - cabinet:heartbeat:<slug>            last heartbeat (SETEX 900)
 *   - cabinet:officer:activity:<slug>     JSON {verb, object, since, blocker_type?}
 *   - cabinet:officer:expected:<slug>     what the operator last asked for
 *   - instance/config/roster.yml          who was hired, and what they are called
 *   - ~/Library/LaunchAgents/…            who has ever been started here
 *
 * CRO v3 amendments, unchanged: activity objects HTML-escaped and visually
 * truncated at 40 chars; "Investigate in Advanced →" only for genuinely
 * abnormal states; "between tasks" ONLY when no blockers.
 */

import Link from 'next/link'
import { isAlarming } from '@/lib/crew'
import { readCrew, type CrewMember } from '@/lib/crew-state'
import { readPosture, postureSentence, POSTURE_ALWAYS } from '@/lib/posture-status'
import CrewWake from './crew-wake'

const STALE_ACTIVITY_MS = 30 * 60 * 1000 // 30 min → show investigate link
const STALE_DISPLAY_MS = 5 * 60 * 1000 // 5 min → append elapsed time

/** Whitelisted verbs (spec §2 Card 1 implementation notes) */
const ALLOWED_VERBS = new Set([
  'drafting', 'reviewing', 'debugging', 'deploying', 'researching',
  'waiting', 'auditing', 'testing', 'shipping', 'planning',
  'investigating', 'triaging', 'working',
])

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** Visual truncation at 40 chars (CRO v3 amendment) */
function truncate40(str: string): string {
  if (str.length <= 40) return str
  return str.slice(0, 37) + '...'
}

function elapsedLabel(sinceMs: number): string {
  const mins = Math.round(sinceMs / 60000)
  if (mins < 60) return `${mins} min`
  const hrs = Math.round(sinceMs / 3600000)
  return `${hrs}h`
}

interface ActivityPayload {
  verb?: string
  object?: string
  since?: string
  blocker_type?: 'captain_approval' | 'founder_action' | null
}

interface Line {
  slug: string
  text: string
  /** Dual-coded mark. Colour never carries the meaning on its own. */
  glyph: string
  glyphClass: string
  /** A calm state gets no chip; a fault does. */
  chip: string | null
  chipClass: string
  investigate: boolean
  elapsed: string | null
}

const CALM_MARK = {
  glyph: '○',
  glyphClass: 'text-zinc-500',
  chipClass: 'border-zinc-700 bg-zinc-800/60 text-zinc-400',
}

/**
 * The chip word for each calm state. It carries the state ON ITS OWN, and the
 * line beside it is then just the officer's name: "First Mate is not awake yet
 * · Not awake yet" said the same thing twice, once to the eye and once to a
 * screen reader.
 */
const CALM_CHIP: Record<string, string> = {
  'not-awake-yet': 'Not awake yet',
  resting: 'Asleep',
  'on-call': 'On call',
}

/**
 * One crew member as a line of text.
 *
 * Note what does NOT happen in the calm branches: no red, no "offline", and no
 * "See details" — a link that offers to investigate a non-event teaches the
 * operator that this card cries wolf.
 */
function lineFor(member: CrewMember, now: number): Line {
  const name = member.name

  const calm = CALM_CHIP[member.state]
  if (calm) {
    return {
      slug: member.slug,
      text: name,
      ...CALM_MARK,
      chip: calm,
      investigate: false,
      elapsed: null,
    }
  }

  if (member.state === 'unknown') {
    return {
      slug: member.slug,
      text: `${name} — ${member.reason}`,
      glyph: '❓',
      glyphClass: 'text-amber-300',
      chip: null,
      chipClass: '',
      investigate: true,
      elapsed: null,
    }
  }

  // The two faults. Both take their red and their link from `isAlarming`
  // rather than restating the condition, so a state added later cannot render
  // calm here while the predicate says otherwise.
  if (isAlarming(member.state)) {
    const stale = member.heartbeat.state === 'stale' ? member.heartbeat.ageMs : 0
    return {
      slug: member.slug,
      text:
        member.state === 'stop-failed'
          ? `${name} was asked to stop and is still working`
          : `${name} has stopped reporting`,
      glyph: '🔴',
      glyphClass: 'text-red-400',
      chip: null,
      chipClass: '',
      investigate: true,
      elapsed: stale > 0 ? elapsedLabel(stale) : null,
    }
  }

  // Awake — the activity phrasing, unchanged.
  let text = `${name} is working`
  let isStale = false
  let elapsed: string | null = null

  if (member.activityRaw) {
    let payload: ActivityPayload = {}
    try {
      payload = JSON.parse(member.activityRaw) as ActivityPayload
    } catch {
      // malformed JSON — treat as no activity
    }

    const sinceMs = payload.since ? now - new Date(payload.since).getTime() : 0
    isStale = sinceMs > STALE_ACTIVITY_MS
    if (sinceMs > STALE_DISPLAY_MS) elapsed = elapsedLabel(sinceMs)

    if (payload.blocker_type === 'captain_approval') {
      const obj = payload.object ? truncate40(escapeHtml(payload.object)) : 'Captain approval'
      text = `${name} is waiting for ${obj}`
    } else if (payload.blocker_type === 'founder_action') {
      const obj = payload.object ? truncate40(escapeHtml(payload.object)) : 'a founder action'
      text = `${name} is blocked on ${obj}`
    } else if (payload.verb) {
      const verb = ALLOWED_VERBS.has(payload.verb) ? payload.verb : 'working'
      text = payload.object
        ? `${name} is ${verb} ${truncate40(escapeHtml(payload.object))}`
        : `${name} is ${verb}`
    } else {
      text = `${name} is between tasks`
    }
  } else {
    text = `${name} is between tasks`
  }

  return {
    slug: member.slug,
    text,
    glyph: isStale ? '🟡' : '🟢',
    glyphClass: isStale ? 'text-amber-400' : 'text-green-400',
    chip: null,
    chipClass: '',
    investigate: isStale,
    elapsed,
  }
}

function Row({ line }: { line: Line }) {
  return (
    <div className="flex items-start gap-2">
      <span className={`text-sm ${line.glyphClass}`} aria-hidden>
        {line.glyph}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm leading-snug text-zinc-200">
          {line.text}
          {line.elapsed && <span className="ml-1 text-zinc-500">({line.elapsed})</span>}
          {line.chip && (
            <span
              className={`ml-2 rounded-full border px-2 py-0.5 align-middle text-[0.65rem] font-medium ${line.chipClass}`}
            >
              {line.chip}
            </span>
          )}
        </p>
        {line.investigate && (
          <Link
            href={`/officers/${line.slug}`}
            className="mt-0.5 inline-flex items-center gap-1 text-xs text-zinc-500 transition-colors hover:text-zinc-300"
          >
            See details
            <span aria-hidden="true">&rarr;</span>
          </Link>
        )}
      </div>
    </div>
  )
}

export default async function CardCabinet() {
  const now = Date.now()
  const crew = await readCrew(now)
  const posture = await readPosture()

  const shown = crew.members.filter((m) => !m.folded)
  const folded = crew.members.filter((m) => m.folded)

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
      <div className="mb-4">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">
          Your Cabinet
        </h2>
      </div>

      {crew.members.length === 0 ? (
        <div className="py-4 text-center">
          <p className="text-sm text-zinc-500">Welcome to your Cabinet.</p>
          <p className="mt-1 text-xs text-zinc-600">
            Your officers will appear here once they come online.
          </p>
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {shown.map((member) => (
              <Row key={member.slug} line={lineFor(member, now)} />
            ))}
          </div>

          {/* The one control. It is absent when there is nothing to control:
              a store that answered nothing cannot be acted on honestly. */}
          {!crew.unreadable && crew.wakeable.length > 0 && (
            <CrewWake
              awake={crew.anyAwake}
              names={shown.filter((m) => crew.wakeable.includes(m.slug)).map((m) => m.name)}
              posture={{
                sentence: postureSentence(posture),
                unreadable: Boolean(posture.error),
                always: POSTURE_ALWAYS,
              }}
            />
          )}

          {folded.length > 0 && (
            <details className="mt-4">
              <summary className="cursor-pointer text-xs text-zinc-500 hover:text-zinc-300">
                {folded.length === 1
                  ? '1 more crew member who does not need waking'
                  : `${folded.length} more crew members who do not need waking`}
              </summary>
              <div className="mt-3 space-y-2">
                {folded.map((member) => (
                  <p key={member.slug} className="text-sm leading-snug text-zinc-400">
                    <span className="text-zinc-200">{member.name}</span>
                    {member.reason ? ` — ${member.reason}` : ''}
                    {!member.hired && ' (not hired yet)'}
                  </p>
                ))}
              </div>
            </details>
          )}
        </>
      )}
    </div>
  )
}
