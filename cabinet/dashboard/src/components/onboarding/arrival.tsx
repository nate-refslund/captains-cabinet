/**
 * THE ARRIVAL — the screen an operator lands on when orientation is finished,
 * and the management view they get every time they come back to it.
 *
 * WHAT IT REPLACED. The flow had no ending. A finished operator's last screen
 * was headed "Deeper Orientation has not started" over a menu of more
 * onboarding, so — measured live, Captain 2026-08-14 — being done and being
 * stuck looked identical: "i believe i've answered everything and am now stuck
 * and can't continue again?". Nothing announced completion and nothing handed
 * off to the dashboard or the briefing.
 *
 * THE ONE DESIGN IDEA: every line of the summary wears the provenance of its
 * own answer. "you told me" / "you approved" / "I found" sit beside the clause
 * they license, so the no-invention law is visible on the screen rather than
 * merely obeyed behind it. The clauses themselves are assembled in
 * `lib/onboarding/arrival.ts`, where each one declares the path in the journey
 * state it was read from and a test asserts the words came from there.
 *
 * NO HOOKS, DELIBERATELY. Every disclosure here is a native `<details>`, which
 * works without JavaScript, is keyboard-navigable for free, and — the load-
 * bearing reason — keeps this component out of the hook order that
 * `journey-card.test.ts` scripts by index.
 */
import Link from 'next/link'

import { arrivalClauses, ARRIVAL_CLAUSE_LIMIT } from '@/lib/onboarding/arrival'
import { FLOW_STOPS } from '@/lib/onboarding/flow-rail'
import { sweepLine } from '@/lib/onboarding/sweep-line'
import type { OnboardingAction, OnboardingResponse } from '@/lib/onboarding/types'

/**
 * The token subset this screen uses, declared structurally so it can take the
 * card's own theme object without either file importing the other.
 */
export interface ArrivalTheme {
  title: string
  muted: string
  faint: string
  eyebrow: string
  panel: string
  primary: string
  secondary: string
  ghost: string
  danger: string
  badge: string
}

/**
 * The query flag that opens the FULL orientation surface on a finished journey.
 *
 * It exists so that the questions this screen does not draw a form for —
 * "which of these accounts is you", "which one should I open first", "whose
 * work is this" — stay answerable. Every one of them was reachable from the
 * card this screen replaces, and a redesign that quietly removed a way to
 * answer a question would be a worse defect than the one it fixes.
 *
 * It CANNOT reach the wizard. The three welcome questions and the folder branch
 * are gated on `stage === 'welcome'`, and a finished journey's stage is
 * `complete` — so no URL puts a finished operator back at question one. Pinned
 * by `journey-card.test.ts`.
 */
export const FULL_SURFACE_PARAM = 'more'

/** True when the operator asked for the full surface. False during SSR. */
export function wantsFullSurface(): boolean {
  if (typeof window === 'undefined') return false
  return new URLSearchParams(window.location.search).get(FULL_SURFACE_PARAM) === '1'
}

/**
 * The four stops, settled. Not the progress rail — a finished flow has no
 * progress left to report — but a quiet confirmation that all four happened.
 * No numbers, no labels, no connecting lines, and one short settle on mount
 * that never loops. Reduced motion removes it entirely.
 */
function SettledStops({ variant }: { variant: 'dashboard' | 'world' }) {
  const dot = variant === 'world' ? 'bg-emerald-700' : 'bg-emerald-400'
  return (
    <>
      <style>{`
        @keyframes cabinet-stop-settle {
          from { opacity: 0; transform: scale(0.4); }
          to   { opacity: 1; transform: scale(1); }
        }
        .cabinet-stop { animation: cabinet-stop-settle 420ms cubic-bezier(0.2, 0.8, 0.2, 1) both; }
        @media (prefers-reduced-motion: reduce) {
          .cabinet-stop { animation: none; }
        }
      `}</style>
      <ol className="flex items-center gap-2" aria-label="All four steps are done">
        {FLOW_STOPS.map((stop, index) => (
          <li key={stop.id} className="flex items-center gap-2">
            <span
              className={`cabinet-stop block h-2 w-2 rounded-full ${dot}`}
              style={{ animationDelay: `${index * 90}ms` }}
            />
            <span className="sr-only">{stop.label} — done</span>
          </li>
        ))}
      </ol>
    </>
  )
}

/** One labelled block of the management view. */
function Section({
  t,
  title,
  children,
}: {
  t: ArrivalTheme
  title: string
  children: React.ReactNode
}) {
  return (
    <section className={`p-4 ${t.panel}`}>
      <h3 className={`text-sm font-semibold ${t.title}`}>{title}</h3>
      <div className="mt-2 space-y-2 text-sm">{children}</div>
    </section>
  )
}

export default function Arrival({
  journey,
  t,
  variant,
  working,
  choose,
}: {
  journey: OnboardingResponse
  t: ArrivalTheme
  variant: 'dashboard' | 'world'
  working: boolean
  choose: (action: OnboardingAction) => void
}) {
  const { state, card } = journey
  const clauses = arrivalClauses(state).slice(0, ARRIVAL_CLAUSE_LIMIT)
  const source = state.source
  const dividend = (state.first_dividend ?? {}) as {
    finding?: { summary?: string; citations?: unknown[] }
    coverage?: { complete?: boolean; examined_files?: number; eligible_files?: number }
  }
  const swept = state.connector_sweep?.connectors ?? []
  // Offers split by whether this screen can actually carry the answer. A tap
  // action is self-contained; anything with an `input` needs a form, and the
  // forms live on the full surface until PR2 gives each its own screen.
  const offers = card.options.filter(
    (option) => option.action !== 'revoke' && option.action !== 'purge'
  )
  const taps = offers.filter((option) => !option.input)
  const asks = offers.filter((option) => option.input)

  return (
    <section className="w-full" aria-labelledby="onboarding-arrival-title">
      <SettledStops variant={variant} />

      <h2
        id="onboarding-arrival-title"
        className={`mt-6 font-semibold tracking-tight ${
          variant === 'world' ? 'text-2xl' : 'text-3xl sm:text-4xl'
        } ${t.title}`}
      >
        Your Cabinet is ready.
      </h2>
      <p className={`mt-3 max-w-2xl text-sm leading-6 ${t.muted}`}>
        Nothing is running now, and nothing opens without your approval.
      </p>

      {/* THE LEDGER. Each clause beside the act that put it on the record. */}
      {clauses.length > 0 && (
        <dl className="mt-7 max-w-2xl">
          {clauses.map((clause) => (
            <div
              key={clause.id}
              className="flex flex-col gap-1 border-t border-current/10 py-3 sm:flex-row sm:gap-5"
            >
              <dt
                className={`shrink-0 pt-0.5 text-[0.65rem] font-semibold uppercase tracking-[0.14em] sm:w-32 ${t.eyebrow}`}
              >
                {clause.provenance}
              </dt>
              <dd className={`text-sm leading-6 ${t.title}`}>{clause.text}</dd>
            </div>
          ))}
        </dl>
      )}

      {/* THE WAY OUT — one obvious next move, two quieter ones. */}
      <div className="mt-8 flex flex-wrap items-center gap-3">
        <Link
          href="/"
          className={`min-h-11 rounded-xl px-5 py-2.5 text-sm font-semibold ${t.primary}`}
        >
          Go to your Cabinet
        </Link>
        <Link
          href="/briefing"
          className={`min-h-11 rounded-xl px-4 py-2.5 text-sm font-medium ${t.secondary}`}
        >
          Read the full briefing
        </Link>
      </div>

      {/* THE DEEPER OFFERS — what used to be a stage title claiming a non-start.
          Every disclosure the old card carried is here, one click behind. */}
      <details className={`mt-4 max-w-2xl p-4 ${t.panel}`}>
        <summary className={`cursor-pointer text-sm font-medium ${t.title}`}>
          Give me more to read
        </summary>
        <p className={`mt-2 text-sm leading-6 ${t.muted}`}>
          A later, separately approved step could spend longer learning how your work fits
          together, reflect back priorities and conflicts, suggest a useful AI team, and show
          what each officer may observe, propose, or do. That work is disabled and has not
          started. No new access or authority was granted.
        </p>
        {taps.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            {taps.map((option) => (
              <button
                key={option.action}
                type="button"
                disabled={working}
                onClick={() => choose(option.action)}
                className={`min-h-11 rounded-xl px-4 py-2 text-sm font-medium disabled:opacity-50 ${t.secondary}`}
              >
                {option.label}
              </button>
            ))}
          </div>
        )}
        {asks.length > 0 && (
          <p className="mt-3 text-sm">
            <a
              href={`?${FULL_SURFACE_PARAM}=1`}
              className={`font-medium underline underline-offset-4 ${t.title}`}
            >
              I still have {asks.length} question{asks.length === 1 ? '' : 's'} for you
            </a>
            <span className={`ml-2 ${t.faint}`}>
              {asks.map((option) => option.label).join(' · ')}
            </span>
          </p>
        )}
      </details>

      {/* ---------------------------------------------------------------
          THE MANAGEMENT VIEW. Coming back to this page after finishing is
          not a reason to be shown a wizard again — it is a reason to be
          shown what the Cabinet may read, what it found, what it is
          connected to, and how to take any of it back.
      ---------------------------------------------------------------- */}
      {/* One column inside the World's ~30rem overlay panel; two on the page. */}
      <div
        className={`mt-10 grid max-w-3xl gap-3 ${
          variant === 'world' ? '' : 'sm:grid-cols-2'
        }`}
      >
        <Section t={t} title="What I may read">
          {source ? (
            <>
              <p className={t.title}>
                <code className="font-mono text-[0.8rem]">{source.root}</code>
              </p>
              <p className={t.faint}>
                <span
                  className={`mr-2 inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[0.7rem] font-medium ${t.badge}`}
                >
                  <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
                  read-only
                </span>
                {state.charter?.hash
                  ? `Charter fingerprint: ${state.charter.hash.slice(0, 12)}.`
                  : null}
              </p>
              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  type="button"
                  disabled={working}
                  onClick={() => choose('propose_window')}
                  className={`min-h-11 rounded-xl px-3 py-2 text-sm font-medium disabled:opacity-50 ${t.secondary}`}
                >
                  Change it
                </button>
                <button
                  type="button"
                  disabled={working}
                  onClick={() => choose('revoke')}
                  className={`min-h-11 rounded-xl px-3 py-2 text-sm font-medium disabled:opacity-50 ${t.ghost}`}
                >
                  Revoke folder access
                </button>
              </div>
            </>
          ) : (
            <p className={t.muted}>Nothing. No folder has been approved.</p>
          )}
        </Section>

        <Section t={t} title="What I found">
          {dividend.finding?.summary ? (
            <>
              <p className={t.muted}>{dividend.finding.summary}</p>
              {card.evidence.length > 0 && (
                <details>
                  <summary className={`cursor-pointer text-xs ${t.faint}`}>
                    Receipt — where this came from
                  </summary>
                  <ul className="mt-2 space-y-2">
                    {card.evidence.map((citation) => (
                      <li key={`${citation.path}:${citation.line}`}>
                        <code className="font-mono text-[0.75rem]">
                          {citation.path}:{citation.line}
                        </code>
                        <span className={`block text-xs ${t.faint}`}>{citation.excerpt}</span>
                      </li>
                    ))}
                  </ul>
                  {card.egress && card.egress.withheld > 0 && (
                    <p className={`mt-2 text-xs ${t.faint}`}>
                      I am holding back the words of {card.egress.withheld} of{' '}
                      {card.egress.items} citation
                      {card.egress.items === 1 ? '' : 's'}: this source is not yours to send.
                      The file and line are above so you can open them yourself, or reclassify
                      the source if I have it wrong.
                    </p>
                  )}
                </details>
              )}
              {dividend.coverage && dividend.coverage.complete === false && (
                <p className={`text-xs ${t.faint}`}>
                  I read {dividend.coverage.examined_files ?? 0} of{' '}
                  {dividend.coverage.eligible_files ?? 0} supported files, most-informative
                  first. The rest were left unopened by the First Window limits.
                </p>
              )}
            </>
          ) : (
            <p className={t.muted}>Nothing yet.</p>
          )}
        </Section>

        <Section t={t} title="Connected tools">
          {swept.length > 0 ? (
            <ul className={`space-y-1 ${t.muted}`}>
              {swept.map((row) => (
                <li key={row.name}>
                  <span className={t.title}>{row.name}</span>
                  {/* The SAME sentence the journey card prints. This first
                      rendered `row.reason` directly, which would have shown an
                      operator the raw diagnostic string every other surface
                      translates — two surfaces describing one row two ways is
                      how a product stops speaking in one voice. */}
                  <span className={t.faint}> — {sweepLine(row)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className={t.muted}>None. Everything above came from the folder you approved.</p>
          )}
        </Section>

        <Section t={t} title="Stop or delete">
          <p className={t.muted}>
            Revoking stops future reads and keeps what was found. Deleting removes the Charter,
            the history and the derived excerpts, and cannot be undone.
          </p>
          <div className="flex flex-wrap gap-2 pt-1">
            <button
              type="button"
              disabled={working}
              onClick={() => choose('purge')}
              className={`min-h-11 rounded-xl px-3 py-2 text-sm font-medium disabled:opacity-50 ${t.danger}`}
            >
              Delete onboarding data
            </button>
          </div>
        </Section>
      </div>
    </section>
  )
}
