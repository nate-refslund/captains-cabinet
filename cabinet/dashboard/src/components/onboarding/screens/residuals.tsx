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
import type { OnboardingEntryPlan } from '@/lib/onboarding/types'
import { Refusal, type ScreenProps } from '../screen-chrome'

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
  return (
    <section className={`mt-6 p-4 ${t.panel}`}>
      <h3 className={`text-sm font-semibold ${t.title}`}>What I went and looked for</h3>
      <ul className="mt-2 space-y-3 text-sm">
        {executed.executed.map((probe, index) => (
          <li key={`ran-${probe.kind}-${probe.pattern ?? probe.query ?? index}`}>
            <code className="font-mono text-[0.8rem]">
              {probe.pattern ?? (probe.query ? `“${probe.query}”` : probe.kind)}
            </code>
            {probe.results ? (
              <>
                <span className={`block text-xs ${t.faint}`}>
                  searched the web{probe.provider ? ` with ${probe.provider}` : ''}
                  {probe.truncated && ' — more results than I show'}
                </span>
                <ul className="mt-1.5 space-y-1.5">
                  {probe.results.map((found, position) => (
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
                      {found.url && <span className={`block text-xs ${t.faint}`}>{found.url}</span>}
                      {found.snippet && (
                        <span className={`block text-xs ${t.faint}`}>{found.snippet}</span>
                      )}
                    </li>
                  ))}
                </ul>
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
  questions,
}: {
  t: ScreenProps['t']
  questions: OnboardingEntryPlan['questions'] | undefined
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
          </li>
        ))}
      </ul>
    </section>
  )
}
