/**
 * A MESSAGE FROM THE FIRST MATE — and the one container that is allowed to look
 * like one.
 *
 * WHY IT EXISTS (Captain, 2026-08-14, reading a finding on a live run): "the
 * information is not super useful and it is too much and honestly i don't even
 * know what kind of information this is... if it is from the first mate, make
 * it look like a message from first mate, if it is something else, show or
 * describe that then." Two different things were rendered identically: content
 * somebody AUTHORED — a finding, a caveat, an answer — and page FURNITURE — a
 * form, a table, a progress line. Attribution is the difference, and it was
 * missing.
 *
 * THE LAW, IN TWO HALVES:
 *   1. If it has an author it must be a message. Authored payloads render here.
 *   2. If it does not, it must not look like one. Furniture never renders here,
 *      and cannot: the component takes `disclosures` — the core's authored rows
 *      — and returns null without them. There is no prop through which a form
 *      or a table becomes a message.
 *
 * `data-authored="first-mate"` marks the container. It is asserted UNIQUE to
 * this file by `first-mate-message.test.ts`, which is the arm for half 2: a
 * screen that hand-rolled an avatar-and-name header to make its table look
 * authoritative would either carry the marker (and fail the uniqueness arm) or
 * lack it (and be findable as an impostor). The marker is a sensor, not styling.
 *
 * THE SENDER IS RESOLVED, NEVER WRITTEN DOWN. The core says only that the
 * speaker is the COORDINATING officer; what this deployment calls that officer
 * is `officerTitle`'s answer, so the naming ruling is applied in one place.
 *
 * NO HOOKS: every disclosure is a native `<details>`, for the reasons in
 * screen-chrome.tsx.
 */
import type { ReactNode } from 'react'

import { COORDINATOR_ROLE, officerTitle } from '@/lib/officer-title'
import { disclosureRows } from '@/lib/onboarding/disclosures'
import type {
  OnboardingCard,
  OnboardingCitation,
  OnboardingDisclosure,
} from '@/lib/onboarding/types'
import type { ScreenTheme } from './screen-chrome'

/** The marker that says "a person wrote this". One home, asserted unique. */
export const AUTHORED_MARKER = 'first-mate'

/** The sender's initials, for the avatar. Two words at most. */
export function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? '')
    .join('')
}

/** The time half of an ISO stamp, or '' — locale-free, so SSR and the client
 *  never disagree about what a timestamp says. */
export function clockOf(stamp: string | null | undefined): string {
  const match = /T(\d{2}:\d{2})/.exec(String(stamp ?? ''))
  return match ? match[1] : ''
}

/**
 * One citation, as a chip that opens IN PLACE.
 *
 * WHAT IT REPLACED: a standalone "Receipt — where this came from" panel that
 * sat below an unrelated feedback fieldset, which the Captain read as two
 * disconnected sections — "is represented weirdly... and how can i answer on
 * that based on the 'receipt'?". A citation belongs to the sentence it
 * supports, so it renders inside the message, and opening one does not move
 * anything else on the screen.
 *
 * THE EXCERPT IS TEXT, ALWAYS. It is a verbatim line from the operator's own
 * files, and the withheld ones arrive already replaced by the core's egress
 * gate. Never `dangerouslySetInnerHTML`, never a markdown renderer.
 */
function CitationChip({ t, citation }: { t: ScreenTheme; citation: OnboardingCitation }) {
  return (
    <details className="inline-block align-baseline">
      <summary
        className={`inline-flex min-h-8 cursor-pointer list-none items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[0.7rem] ${t.choice} ${t.muted}`}
      >
        <span aria-hidden>↳</span>
        {citation.path}:{citation.line}
      </summary>
      <span className={`mt-1.5 block rounded-lg border px-3 py-2 text-xs leading-6 ${t.panel} ${t.muted}`}>
        {citation.excerpt}
      </span>
    </details>
  )
}

/**
 * The message. `card.disclosures` is the authored payload; everything else on
 * this component is how it is presented.
 *
 * THE THREE LAYERS, laid out as the ruling set them: the headline rows lead;
 * the fold rows open in place under the question they answer; the ledger rows
 * are the complete record, behind the same fold and after a rule. Nothing is
 * dropped at any level — the core's parity gate proves the rows survive, and
 * `disclosure-render.test.ts` proves this component puts every one of them on
 * the screen.
 */
export default function FirstMateMessage({
  t,
  card,
  footer,
  stamp,
}: {
  t: ScreenTheme
  card: OnboardingCard
  /** The rating, and anything else that grades THIS message. Rendered inside
   *  the message's own footer, because a grade detached from the thing it
   *  grades is the disconnection the Captain reported. */
  footer?: ReactNode
  /** When it was said. Absent is fine — an unknown time is not invented. */
  stamp?: string | null
}) {
  const rows: OnboardingDisclosure[] = disclosureRows(card)
  // NO AUTHOR, NO MESSAGE. A card the core did not attribute is not put in
  // somebody's mouth, and furniture has no rows at all.
  if (!card.speaker || rows.length === 0) return null

  const name = officerTitle(COORDINATOR_ROLE)
  const lead = rows.filter((row) => row.layer === 'headline')
  const fold = rows.filter((row) => row.layer === 'fold')
  const ledger = rows.filter((row) => row.layer === 'ledger')
  // AN UNLED CARD SHOWS ITS LEDGER OPEN. With nothing in the headline layer
  // there is no claim for a fold to sit behind, and folding the only text away
  // would render a message with nothing in it.
  const unled = lead.length === 0
  const cited = new Map(card.evidence.map((c) => [`${c.path}:${c.line}`, c]))
  const clock = clockOf(stamp)
  // A CITATION NO ROW CLAIMS IS STILL EVIDENCE. Older cards carry `evidence`
  // with no `cites` on any row, and a citation the operator cannot open is the
  // same as one that was never given — so anything unclaimed renders after the
  // lead rather than being dropped for want of a home.
  const claimed = new Set(rows.flatMap((row) => row.cites))
  const unclaimed = card.evidence.filter((c) => !claimed.has(`${c.path}:${c.line}`))

  return (
    <article
      data-authored={AUTHORED_MARKER}
      aria-label={`Message from ${name}`}
      className={`mt-6 rounded-2xl border border-current/10 p-4 sm:p-5 ${t.panel}`}
    >
      <div className="flex items-center gap-2.5">
        <span
          aria-hidden
          className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[0.65rem] font-bold tracking-tight ${t.railOn}`}
        >
          {initialsOf(name)}
        </span>
        <span className={`text-sm font-semibold ${t.title}`}>{name}</span>
        {clock && <span className={`text-xs tabular-nums ${t.faint}`}>{clock}</span>}
      </div>

      <div className="mt-3 space-y-2.5">
        {lead.map((row, index) => (
          <p
            key={row.id}
            className={`text-pretty break-words ${
              index === 0 ? `text-base leading-7 ${t.title}` : `text-sm leading-6 ${t.muted}`
            }`}
          >
            {row.text}
            {row.cites.length > 0 && (
              <span className="ml-2 inline-flex flex-wrap gap-1.5">
                {row.cites.map((key) => {
                  const citation = cited.get(key)
                  return citation ? <CitationChip key={key} t={t} citation={citation} /> : null
                })}
              </span>
            )}
          </p>
        ))}
      </div>

      {unclaimed.length > 0 && (
        <p className="mt-3 flex flex-wrap items-baseline gap-1.5">
          <span className={`mr-1 text-xs ${t.faint}`}>Where this came from:</span>
          {unclaimed.map((citation) => (
            <CitationChip key={`${citation.path}:${citation.line}`} t={t} citation={citation} />
          ))}
        </p>
      )}

      {unled && (
        <div className="mt-3 space-y-2.5">
          {[...fold, ...ledger].map((row) => (
            <div key={row.id}>
              {row.title && (
                <h3 className={`text-xs font-semibold uppercase tracking-wider ${t.eyebrow}`}>
                  {row.title}
                </h3>
              )}
              <p className={`break-words text-sm leading-6 ${t.muted}`}>{row.text.trim()}</p>
            </div>
          ))}
        </div>
      )}

      {!unled && (fold.length > 0 || ledger.length > 0) && (
        <details className="mt-4">
          <summary
            className={`min-h-11 cursor-pointer py-2 text-xs font-medium ${t.faint}`}
          >
            How I know this — and what I could not see
          </summary>
          <div className="space-y-3 pt-1">
            {fold.map((row) => (
              <div key={row.id}>
                <h3 className={`text-xs font-semibold uppercase tracking-wider ${t.eyebrow}`}>
                  {row.title}
                </h3>
                <p className={`mt-0.5 break-words text-sm leading-6 ${t.muted}`}>
                  {row.text.trim()}
                </p>
              </div>
            ))}
            {ledger.length > 0 && (
              <div className="space-y-3 border-t border-current/10 pt-3">
                <p className={`text-[0.65rem] font-semibold uppercase tracking-[0.18em] ${t.faint}`}>
                  The full record
                </p>
                {ledger.map((row) => (
                  <div key={row.id}>
                    <h3 className={`text-xs font-semibold uppercase tracking-wider ${t.eyebrow}`}>
                      {row.title}
                    </h3>
                    <p className={`mt-0.5 break-words text-sm leading-6 ${t.muted}`}>
                      {row.text.trim()}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </details>
      )}

      {card.egress && card.egress.withheld > 0 && (
        <p className={`mt-3 text-xs leading-5 ${t.faint}`}>
          I am holding back the words of {card.egress.withheld} of {card.egress.items} citation
          {card.egress.items === 1 ? '' : 's'}: this source is not yours to send. The file and
          line are above so you can open them yourself, or reclassify the source if I have it
          wrong.
        </p>
      )}

      {footer && <div className="mt-4 border-t border-current/10 pt-3">{footer}</div>}
    </article>
  )
}
