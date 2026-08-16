/**
 * THE EARNED ASKS — three questions that exist only while unanswered.
 *
 * WHAT CHANGED. These were three panels that appeared beside each other, below
 * a sweep table, and STAYED on the page after being answered — so an operator
 * who had told the Cabinet everything still saw a page full of questions and
 * read it as being stuck ("i believe i've answered everything and am now stuck
 * and can't continue again?"). Now each is a screen, each fires only when its
 * answer is genuinely missing, and answering it moves the flow on.
 *
 * EVERY ONE OF THEM CAN BE LEFT. Skipping is a real, quiet control: a question
 * the operator cannot answer must not be a wall, and the Cabinet's honest
 * position on all three is that it will keep saying it cannot tell rather than
 * guessing.
 *
 * ONE ANSWER MODEL. The controls here send the SAME acts the card always sent,
 * with the same payload shapes — a screen is a different place to answer, never
 * a second way of storing an answer.
 */
import type { FormEvent } from 'react'

import type {
  OnboardingEntryPlan,
  OnboardingIdentityAsk,
  OnboardingOption,
  OnboardingSalienceOption,
} from '@/lib/onboarding/types'

/** The identity ask as the core hands it over, named off the plan that owns
 *  it so this file cannot drift into a second definition of the same shape. */
type IdentityQuestion = NonNullable<OnboardingEntryPlan['identity_question']>
import {
  Actions,
  Primary,
  Refusal,
  ScreenTitle,
  Secondary,
  type ScreenProps,
} from '../screen-chrome'

/** How many of a connector's accounts lead the picker. A LAYOUT number: every
 *  account the core offers is rendered, the rest behind a disclosure — never
 *  behind a second request. */
export const IDENTITY_SHOWN = 8

/**
 * WHICH ACCOUNT IS YOU. With a name on record the core proposes ONE per tool,
 * so the ask is a tap rather than a spelling test over dozens of strangers —
 * and nothing is recorded by looking at it. "No, someone else" opens the list;
 * leaving the screen stores nothing at all.
 */
export function IdentityScreen({
  t,
  variant,
  working,
  surface,
  question,
  handles,
  onPick,
  onConfirm,
  onSubmit,
  onSkip,
  error,
}: ScreenProps & {
  question: IdentityQuestion
  handles: Readonly<Record<string, string>>
  onPick: (connector: string, identifier: string) => void
  onConfirm: (connector: string, identifier: string) => void
  onSubmit: (event: FormEvent) => void
  onSkip: () => void
  error: string
}) {
  const picked = Object.values(handles).some((value) => value.trim())
  const choice = (
    ask: OnboardingIdentityAsk,
    candidate: { identifier: string; rows: number }
  ) => {
    const on = handles[ask.connector] === candidate.identifier
    return (
      <label
        key={candidate.identifier}
        className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 transition-colors motion-reduce:transition-none ${on ? t.choiceOn : t.choice}`}
      >
        <input
          type="radio"
          name={`${surface}-identity-${ask.connector}`}
          value={candidate.identifier}
          checked={on}
          onChange={() => onPick(ask.connector, candidate.identifier)}
        />
        <span>
          {candidate.identifier}
          <span className={`block text-xs ${t.faint}`}>
            {candidate.rows} of {ask.rows} here
          </span>
        </span>
      </label>
    )
  }

  return (
    <form onSubmit={onSubmit}>
      <ScreenTitle
        t={t}
        variant={variant}
        lead="Until I know, I will keep saying I cannot tell who did what — rather than guessing at a name that looks close."
      >
        {question.question}
      </ScreenTitle>

      {question.connectors.map((ask: OnboardingIdentityAsk) => (
        <fieldset key={ask.connector} className="mt-6">
          <legend className={`text-sm font-medium ${t.title}`}>{ask.connector}</legend>
          {ask.reports_no_actor ? (
            <p className={`mt-1 text-xs ${t.faint}`}>{ask.note}</p>
          ) : ask.guess && handles[ask.connector] === undefined ? (
            <div className="mt-2">
              <p className={`text-base ${t.title}`}>
                In {ask.connector}, are you <span className="font-semibold">{ask.guess.identifier}</span>?
              </p>
              <p className={`mt-0.5 text-xs ${t.faint}`}>
                {ask.guess.why} — {ask.guess.rows} of {ask.rows} rows here.
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  name={`${surface}-identity-confirm-${ask.connector}`}
                  disabled={working}
                  onClick={() => onConfirm(ask.connector, ask.guess?.identifier ?? '')}
                  className={`min-h-11 rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-45 ${t.primary}`}
                >
                  That&rsquo;s me
                </button>
                <Secondary
                  t={t}
                  tone="outline"
                  name={`${surface}-identity-reject-${ask.connector}`}
                  label="No, someone else"
                  disabled={working}
                  onClick={() => onPick(ask.connector, '')}
                />
              </div>
            </div>
          ) : (
            <>
              {ask.guess_note && <p className={`mt-1 text-xs ${t.faint}`}>{ask.guess_note}</p>}
              <div className="mt-2 space-y-1.5 text-sm">
                {ask.candidates.slice(0, IDENTITY_SHOWN).map((candidate) => choice(ask, candidate))}
              </div>
              {ask.candidates.length > IDENTITY_SHOWN && (
                <details className="mt-1">
                  <summary className={`min-h-11 cursor-pointer py-2 text-xs ${t.faint}`}>
                    Show the other {ask.candidates.length - IDENTITY_SHOWN} account
                    {ask.candidates.length - IDENTITY_SHOWN === 1 ? '' : 's'} in {ask.connector}
                  </summary>
                  <div className="space-y-1.5 text-sm">
                    {ask.candidates.slice(IDENTITY_SHOWN).map((candidate) => choice(ask, candidate))}
                  </div>
                </details>
              )}
              {!ask.complete && (
                <label className="mt-2 block text-xs">
                  <span className={t.faint}>
                    {ask.withheld} more account{ask.withheld === 1 ? '' : 's'} in {ask.connector} than I
                    can list. If yours is one of them, type it exactly as {ask.connector} spells it.
                  </span>
                  <input
                    type="text"
                    name={`${surface}-identity-typed-${ask.connector}`}
                    value={handles[ask.connector] ?? ''}
                    onChange={(event) => onPick(ask.connector, event.target.value)}
                    className={`mt-1 min-h-11 w-full max-w-md rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
                  />
                </label>
              )}
            </>
          )}
        </fieldset>
      ))}

      {error && <Refusal t={t} variant={variant}>{error}</Refusal>}

      <Actions>
        {picked ? (
          <Primary
            t={t}
            id="onboarding-identity-submit"
            type="submit"
            label="That one is me"
            working={working}
          />
        ) : (
          <Primary
            t={t}
            id="onboarding-identity-submit"
            label="That one is me"
            disabled
            reason="Choose an account above, or skip — I will keep saying I cannot tell."
          />
        )}
        <Secondary t={t} label="None of these is me — skip" disabled={working} onClick={onSkip} />
      </Actions>
    </form>
  )
}

/**
 * WHAT TO OPEN FIRST. The ranked candidates, the confirm when the operator's
 * own words already answered it, and the escape hatch that takes a typed name.
 *
 * ASKED ONCE, NOT TWICE (Captain, 2026-08-14: "this question i actually already
 * answered in the second question about purpose"). Where exactly one ranked
 * candidate carries words the operator already gave, the open ask becomes a
 * confirm they can take in one tap — and the full list stays right below it,
 * because a confirmation is not a corner.
 */
export function SalienceScreen({
  t,
  variant,
  working,
  surface,
  offer,
  options,
  choice,
  nameValue,
  merge,
  onChoice,
  onName,
  onMerge,
  onConfirm,
  onSubmit,
  onSkip,
  error,
}: ScreenProps & {
  offer: OnboardingOption | null
  options: OnboardingSalienceOption[]
  choice: string
  nameValue: string
  merge: readonly string[]
  onChoice: (id: string) => void
  onName: (value: string) => void
  onMerge: (id: string) => void
  onConfirm: (option: string) => void
  onSubmit: (event: FormEvent) => void
  onSkip: () => void
  error: string
}) {
  const asksName = options.find((option) => option.id === choice)?.input === 'seed'
  const confirm = offer?.confirm
  const blocked = !choice
    ? 'Choose one above and I will spend my first look there.'
    : asksName && !nameValue.trim()
      ? 'Name the thing you want opened — a word or two is enough.'
      : ''

  return (
    <form onSubmit={onSubmit}>
      <ScreenTitle
        t={t}
        variant={variant}
        lead="These are the names that recur most across everything you connected. I go deep on one of them first."
      >
        {/* THE CORE'S OWN WORDS. The question is authored there — the screen
            supplies layout, never a second phrasing of the same ask. */}
        {confirm ? confirm.question : offer?.label ?? 'Which should I open first?'}
      </ScreenTitle>

      {confirm && (
        <button
          type="button"
          name={`${surface}-salience-confirm`}
          disabled={working}
          onClick={() => onConfirm(confirm.option)}
          className={`mt-6 min-h-11 rounded-xl px-5 py-2.5 text-sm font-semibold disabled:opacity-45 ${t.primary}`}
        >
          Yes — start with {confirm.label}
        </button>
      )}

      <div className="mt-4 max-w-2xl space-y-1.5 text-sm">
        {options.map((option) => (
          <label
            key={option.id}
            className={`flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border px-3 py-2 transition-colors motion-reduce:transition-none ${choice === option.id ? t.choiceOn : t.choice}`}
          >
            <input
              type="radio"
              name={`${surface}-salience`}
              value={option.id}
              checked={choice === option.id}
              onChange={() => onChoice(option.id)}
              className="mt-1"
            />
            <span>
              {option.label}
              {option.you_said && option.you_said.length > 0 && (
                <span className={`ml-2 rounded-full border px-2 py-0.5 text-[0.65rem] font-medium ${t.badge}`}>
                  you said {option.you_said.slice(0, 2).join(', ')}
                </span>
              )}
              <span className={`block text-xs ${t.faint}`}>{option.why}</span>
            </span>
          </label>
        ))}
      </div>

      {asksName && (
        <label className="mt-3 block text-xs">
          <span className={t.faint}>
            {offer?.prefill
              ? 'What should I open instead? I have started from a word you already gave me — change it if it is wrong.'
              : 'What should I open instead? A word or two.'}
          </span>
          <input
            type="text"
            name={`${surface}-salience-name`}
            value={nameValue}
            onChange={(event) => onName(event.target.value)}
            autoComplete="off"
            className={`mt-1 min-h-11 w-full max-w-md rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
          />
        </label>
      )}

      {offer?.merge?.candidates && offer.merge.candidates.length > 1 && (
        <details className="mt-4">
          <summary className={`min-h-11 cursor-pointer py-2 text-xs ${t.faint}`}>
            Are two of these the same thing under different names?
          </summary>
          <p className={`text-xs ${t.faint}`}>{offer.merge.question}</p>
          <div className="mt-1 max-w-2xl space-y-1.5 text-sm">
            {offer.merge.candidates.map((candidate) => (
              <label
                key={candidate.id}
                className={`flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 ${merge.includes(candidate.id) ? t.choiceOn : t.choice}`}
              >
                <input
                  type="checkbox"
                  name={`${surface}-salience-merge`}
                  value={candidate.id}
                  checked={merge.includes(candidate.id)}
                  onChange={() => onMerge(candidate.id)}
                />
                <span>{candidate.label}</span>
              </label>
            ))}
          </div>
          {offer.merge.learned?.length > 0 && (
            <p className={`mt-2 text-xs ${t.faint}`}>
              Already one thing:{' '}
              {offer.merge.learned.map((group) => group.labels.join(' = ')).join('; ')}
            </p>
          )}
        </details>
      )}

      {offer?.not_reached && <p className={`mt-3 max-w-prose text-xs ${t.faint}`}>{offer.not_reached}</p>}

      {error && <Refusal t={t} variant={variant}>{error}</Refusal>}

      <Actions>
        {blocked ? (
          <Primary t={t} id="onboarding-salience-submit" label="Go deep on that one" disabled reason={blocked} />
        ) : (
          <Primary
            t={t}
            id="onboarding-salience-submit"
            type="submit"
            label="Go deep on that one"
            working={working}
          />
        )}
        <Secondary t={t} label="Decide for me — skip" disabled={working} onClick={onSkip} />
      </Actions>
    </form>
  )
}

/**
 * WHOSE WORK THIS IS. Earned — the core asks it only when the operator's own
 * words and their tools' own names leave it genuinely unclear.
 *
 * Never pre-filled from a folder name, a credential or a search result: the
 * core stores this as the operator's own statement, and a default would put
 * words in their mouth.
 */
export function OrganizationScreen({
  t,
  variant,
  working,
  surface,
  prompt,
  why,
  organization,
  onOrganization,
  onSubmit,
  onSkip,
  error,
}: ScreenProps & {
  prompt: string
  why: string
  organization: string
  onOrganization: (value: string) => void
  onSubmit: (event: FormEvent) => void
  onSkip: () => void
  error: string
}) {
  return (
    <form onSubmit={onSubmit}>
      <ScreenTitle t={t} variant={variant} lead={why}>
        {prompt}
      </ScreenTitle>
      <div className="mt-6">
        <label htmlFor={`${surface}-organization`} className="sr-only">
          {prompt}
        </label>
        <input
          id={`${surface}-organization`}
          type="text"
          name={`${surface}-organization`}
          value={organization}
          onChange={(event) => onOrganization(event.target.value)}
          placeholder="A company name, or “just me”"
          autoComplete="organization"
          autoFocus
          className={`min-h-11 w-full max-w-md rounded-xl border px-4 py-2.5 text-base outline-none ${t.input}`}
        />
      </div>

      {error && <Refusal t={t} variant={variant}>{error}</Refusal>}

      <Actions>
        {organization.trim() ? (
          <Primary t={t} id="onboarding-org-submit" type="submit" label="Remember that" working={working} />
        ) : (
          <Primary
            t={t}
            id="onboarding-org-submit"
            label="Remember that"
            disabled
            reason="A company name, or “just me” — either is a complete answer."
          />
        )}
        <Secondary t={t} label="I would rather not say — skip" disabled={working} onClick={onSkip} />
      </Actions>
    </form>
  )
}
