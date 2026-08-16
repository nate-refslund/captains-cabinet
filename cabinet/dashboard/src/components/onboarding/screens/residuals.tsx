/**
 * WHAT I WENT AND LOOKED FOR, AND WHAT I STILL CANNOT WORK OUT.
 *
 * TWO DISCLOSURES THAT ARE NOT MESSAGES. They are page furniture — a log and a
 * list — so they do NOT use the First Mate container: if it has an author it
 * must be a message, and if it does not it must not look like one.
 *
 * WHY THEY HAVE THEIR OWN FILE. They were panels on the accumulating card and
 * the screens they belong to are not the ones that produce them: the probe log
 * is written by the seed's own look-up and is read on three different screens.
 * Extracting them is what stopped the redesign losing them — a redesign that
 * quietly drops a disclosure is the one failure mode this whole branch is
 * guarded against, and `disclosure-render.test.ts` is the sensor.
 */
import type { FormEvent } from 'react'

import type { OnboardingCard, OnboardingEntryPlan } from '@/lib/onboarding/types'
import { Refusal, type ScreenProps } from '../screen-chrome'

/** One web result, as the core hands it over. */
type Found = NonNullable<
  NonNullable<
    NonNullable<OnboardingCard['entry']>['discovery']['executed']
  >['executed'][number]['results']
>[number]

/**
 * THE PROBES: what left this machine, and what came back.
 *
 * TWO KINDS, ONE LIST. A local probe shows the name pattern it matched inside
 * the ratified folder; an outward one shows the QUERY that left this machine
 * and the results that came back.
 *
 * EVERY STRING FROM A RESULT IS RENDERED AS TEXT, never as markup and never as
 * a template. The core scrubs and caps each field before it gets here (control
 * characters, angle brackets, lone surrogates, a length cap, and an address
 * that is not http/https reduced to an empty string) precisely because whoever
 * ranks well for the operator's own words could be an adversary. Keep it this
 * way: `dangerouslySetInnerHTML`, a markdown renderer, or trusting `found.url`
 * without the emptiness check below would each undo that at a stroke.
 */
export function ProbeLog({
  t,
  variant,
  working,
  entry,
  onRerun,
  error,
}: Omit<ScreenProps, 'surface'> & {
  entry: OnboardingEntryPlan | undefined
  onRerun: () => void
  error: string
}) {
  const executed = entry?.discovery?.executed
  if (!executed) return null
  const rerun = entry?.next_actions?.find((action) => action.action === 'run_discovery')
  // WHAT THE LOOK-UP WAS JUDGED AGAINST, named so the miss can be said out loud.
  // Empty means the run was not judged at all, and every sentence below that
  // would claim "none of this is you" stays unwritten — "I did not check" and
  // "I checked and none of it was you" are different facts.
  const lookedFor = executed.looked_for?.[0] ?? ''
  /**
   * ONE result, rendered identically whether it named the operator or not.
   *
   * `matched[].term` is the OPERATOR's own string, quoted back as the reason,
   * so the "why" can never be a claim the core did not make.
   */
  const renderFound = (found: Found, position: number) => (
    <li key={`${found.url || found.title}-${position}`}>
      {found.url ? (
        <a
          href={found.url}
          target="_blank"
          rel="noreferrer noopener"
          className="underline underline-offset-2"
        >
          {found.title || found.url}
        </a>
      ) : (
        <span>{found.title}</span>
      )}
      {(found.matched?.length ?? 0) > 0 && (
        <span className={`block text-xs font-medium ${t.title}`}>
          names {found.matched?.map((hit) => hit.term).join(', ')}
        </span>
      )}
      {found.url && <span className={`block text-xs ${t.faint}`}>{found.url}</span>}
      {found.snippet && <span className={`block text-xs ${t.faint}`}>{found.snippet}</span>}
    </li>
  )
  return (
    <section className={`mt-6 p-4 ${t.panel}`}>
      <h3 className={`text-sm font-semibold ${t.title}`}>What I went and looked for</h3>
      <ul className="mt-2 space-y-3 text-sm">
        {executed.executed.map((probe, index) => (
          <li key={`ran-${probe.kind}-${probe.pattern ?? probe.query ?? probe.url ?? index}`}>
            <code className="font-mono text-[0.8rem]">
              {probe.pattern ?? (probe.query ? `“${probe.query}”` : probe.url ?? probe.kind)}
            </code>
            {probe.results ? (
              <>
                <span className={`block text-xs ${t.faint}`}>
                  {probe.url && !probe.query
                    ? 'read the page you gave me'
                    : `searched the web${probe.provider ? ` with ${probe.provider}` : ''}`}
                  {probe.truncated && ' — more results than I show'}
                </span>
                {/*
                  A COUNT IS NOT A FINDING (Captain, 2026-08-15). Fifteen results
                  about a job title were once listed here as though they answered
                  the question. The core judges each result against the
                  operator's OWN words and orders the ones that name them first;
                  this renders that judgment instead of a list. `relevant ===
                  undefined` means the run was never judged — a different fact
                  from zero, and rendering it as "nothing matched" would be the
                  unearned negative in a new place.
                */}
                {lookedFor && probe.relevant === 0 && (
                  <span className={`block text-xs font-medium ${t.title}`}>
                    I looked, but none of this looks like YOUR {lookedFor} — these may be
                    unrelated.
                  </span>
                )}
                <ul className="mt-1.5 space-y-1.5">
                  {probe.results
                    .filter((found) => (found.matched?.length ?? 0) > 0)
                    .map(renderFound)}
                </ul>
                {/*
                  FOLDED, NEVER DELETED. A result that matches nothing is still
                  the web's answer to the operator's own query, and dropping it
                  would replace an honest miss with a silent one.
                */}
                {probe.results.some((found) => !found.matched?.length) && (
                  <details className="mt-1.5">
                    <summary className={`cursor-pointer text-xs ${t.faint}`}>
                      {probe.results.filter((found) => !found.matched?.length).length}{' '}
                      {lookedFor ? `result(s) that name nothing you told me` : `result(s)`}
                    </summary>
                    <ul className="mt-1.5 space-y-1.5">
                      {probe.results
                        .filter((found) => !found.matched?.length)
                        .map(renderFound)}
                    </ul>
                  </details>
                )}
              </>
            ) : (
              <span className={`block ${t.faint}`}>
                {(probe.matches?.length ?? 0) > 0
                  ? probe.matches?.join(', ')
                  : 'nothing matched by name'}
                {probe.truncated && ' — stopped at my limit before the end of the folder'}
              </span>
            )}
          </li>
        ))}
        {executed.deferred.map((probe, index) => (
          <li key={`skipped-${probe.kind}-${index}`}>
            <code className="font-mono text-[0.8rem]">
              {probe.query ? `“${probe.query}”` : probe.kind}
            </code>
            <span className={`block ${t.faint}`}>
              did not run — {probe.reason.replaceAll('_', ' ')}
            </span>
          </li>
        ))}
      </ul>
      {/* THE RE-RUN, where the results are. The core offers this action only
          once a search tool is declared, so this button never appears unable to
          work — and when it is absent the deferral line above says what to
          connect. */}
      {rerun && (
        <button
          type="button"
          disabled={working}
          onClick={onRerun}
          className={`mt-3 min-h-11 rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-45 ${t.secondary}`}
        >
          {rerun.label}
        </button>
      )}
      {error && (
        <Refusal t={t} variant={variant}>
          {error}
        </Refusal>
      )}
    </section>
  )
}

/**
 * WHAT I STILL CANNOT WORK OUT — the residual questions, printed.
 *
 * THE ONE THAT HAS AN ACTION IS A SCREEN, NOT A ROW. `answer_organization` is
 * the only residual the core can take an answer for, so it is routed to as its
 * own screen and filtered out here — a question rendered twice is a question
 * the operator answers twice.
 *
 * The rest are printed with no way to answer them. That is a real gap in the
 * product and it is NOT hidden here by rendering a field that would send
 * nothing: an honest list of open questions is a disclosure, and a field that
 * goes nowhere is a dead end.
 */
export function OpenQuestions({
  t,
  variant,
  working,
  surface,
  questions,
  confirmDomain,
  orgLink,
  onOrgLink,
  onSubmitOrgLink,
  onConfirmDomain,
  error,
}: ScreenProps & {
  questions: OnboardingEntryPlan['questions'] | undefined
  /** The domain one of the cabinet's OWN searches returned, carried on the
   *  action — so this surface never picks a domain out of the results itself. */
  confirmDomain: { label: string; domain?: string } | undefined
  orgLink: string
  onOrgLink: (value: string) => void
  onSubmitOrgLink: (event: FormEvent) => void
  onConfirmDomain: (domain: string | undefined) => void
  error: string
}) {
  const open = (questions ?? []).filter(
    (question) => question.action !== 'answer_organization'
  )
  if (open.length === 0) return null
  return (
    <section className={`mt-6 p-4 ${t.panel}`}>
      <h3 className={`text-sm font-semibold ${t.title}`}>What I cannot work out for myself</h3>
      <ul className="mt-2 space-y-2 text-sm">
        {open.map((question) => (
          <li key={question.id}>
            {question.prompt}
            <span className={`block ${t.faint}`}>{question.why}</span>
            {/*
              THE PAGE, when the web could not find them. The core offers this
              only after a look-up ran and nothing that came back named their
              organisation, so this field never appears on a search that was
              never made.
            */}
            {question.action === 'answer_org_link' && (
              <form className="mt-2 flex flex-col gap-2 sm:flex-row" onSubmit={onSubmitOrgLink}>
                <input
                  type="url"
                  name={`${surface}-org-link`}
                  value={orgLink}
                  onChange={(event) => onOrgLink(event.target.value)}
                  placeholder="https://…"
                  inputMode="url"
                  className={`min-h-11 flex-1 rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
                />
                <button
                  type="submit"
                  disabled={working || !orgLink.trim()}
                  className={`min-h-11 rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-45 ${t.secondary}`}
                >
                  Read that page
                </button>
              </form>
            )}
            {/*
              THE CHIP, for the other outcome. One tap records an address one of
              the cabinet's OWN searches returned.
            */}
            {question.action === 'confirm_organization_domain' && confirmDomain && (
              <button
                type="button"
                disabled={working}
                onClick={() => onConfirmDomain(confirmDomain.domain)}
                className={`mt-2 min-h-11 rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-45 ${t.secondary}`}
              >
                {confirmDomain.label}
              </button>
            )}
            {(question.id === 'org_link' || question.id === 'org_domain') && error && (
              <Refusal t={t} variant={variant}>
                {error}
              </Refusal>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
