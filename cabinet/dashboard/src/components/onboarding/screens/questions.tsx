/**
 * THE FRONT — the door and the three questions, one screen each.
 *
 * WHAT CHANGED. These were four stacked panels inside one card, gated by an
 * `inFrontQuestions && wizardStep === …` predicate that could in principle show
 * two at once, above a rail, below a header, with the server's own sentence
 * underneath. Now each is a screen: it replaces the last one, it asks exactly
 * one thing, and its primary control is the only prominent thing on it.
 *
 * ONE VOICE, checked line by line. Every word here is the CABINET speaking to
 * the operator: "I" is the Cabinet, "you" is the person reading. Two rows of
 * the third question had flipped into the operator's voice on a live run
 * (Captain, 2026-08-13) so three lines of one paragraph disagreed about who "I"
 * was; the wording below is his.
 */
import { Actions, ChoiceCard, Field, Primary, ScreenTitle, type ScreenProps } from '../screen-chrome'

/**
 * S1 — THE DOOR. The one screen that asks nothing.
 *
 * IT IS NOT DECORATION. The flow used to open mid-interview, on a text field
 * headed "What is your name? And tell me about you and your work." — so the
 * first thing a new operator had to do was work out what this was and what it
 * would cost them. This screen answers both before anything is asked, states
 * the shape of the whole thing (four steps), and asks for one tap. The
 * Captain's standing complaint about the app is exactly this: "i should
 * basically be taken through the whole thing without being able to make a
 * mistake".
 */
export function WelcomeScreen({
  t,
  variant,
  working,
  onBegin,
}: ScreenProps & { onBegin: () => void }) {
  return (
    <>
      <ScreenTitle
        t={t}
        variant={variant}
        lead="I am the crew you have just hired, and I know nothing about your work yet. Four short steps and I will have read one thing you point me at and told you something useful about it."
      >
        Let&rsquo;s get you set up.
      </ScreenTitle>
      <ol className={`mt-7 max-w-prose space-y-2.5 text-sm leading-6 ${t.muted}`}>
        <li className="flex gap-3">
          <span className={`w-4 shrink-0 tabular-nums ${t.faint}`}>1</span>
          You tell me who you are and what you would love this to become.
        </li>
        <li className="flex gap-3">
          <span className={`w-4 shrink-0 tabular-nums ${t.faint}`}>2</span>
          You choose what I may read — one folder, or the tools you already use.
        </li>
        <li className="flex gap-3">
          <span className={`w-4 shrink-0 tabular-nums ${t.faint}`}>3</span>
          I read it once, read-only, and bring back one useful thing with the
          exact place it came from.
        </li>
        <li className="flex gap-3">
          <span className={`w-4 shrink-0 tabular-nums ${t.faint}`}>4</span>
          You decide what happens next. Nothing is ever opened without your
          approval, and you can delete all of it in one step.
        </li>
      </ol>
      <Actions>
        <Primary t={t} id="onboarding-begin" label="Start" working={working} onClick={onBegin} />
      </Actions>
    </>
  )
}

/**
 * S2 — YOU. Name first, then what you do.
 *
 * THE NAME COMES FIRST because it is the cheapest answer in the whole interview
 * and it makes the next several answerable: with it the Cabinet can propose "in
 * that tool, are you @…?" instead of asking the operator to find themselves
 * among thirty strangers (Captain, 2026-08-14). It stays OPTIONAL — a cabinet
 * that will not start without your name is an interview — so the screen's gate
 * is on the role alone.
 */
export function YouScreen({
  t,
  variant,
  working,
  surface,
  name,
  role,
  onName,
  onRole,
  onNext,
  onBack,
  blocked,
}: ScreenProps & {
  name: string
  role: string
  onName: (value: string) => void
  onRole: (value: string) => void
  onNext: () => void
  onBack: () => void
  /** Why Continue will not fire, or '' when it will. From `wizard.blockedReason`. */
  blocked: string
}) {
  return (
    <>
      <ScreenTitle t={t} variant={variant}>
        First — who am I working for?
      </ScreenTitle>
      <Field
        t={t}
        id={`${surface}-name`}
        label={
          <>
            Your name
            <span className={`ml-1.5 text-xs font-normal ${t.faint}`}>
              optional — it is how I address you, and how I recognise your accounts
            </span>
          </>
        }
      >
        <input
          id={`${surface}-name`}
          type="text"
          value={name}
          onChange={(event) => onName(event.target.value)}
          maxLength={80}
          autoFocus
          autoComplete="name"
          placeholder="However you write it"
          className={`mt-1.5 min-h-11 w-full max-w-md rounded-xl border px-4 py-2.5 text-base outline-none transition-colors motion-reduce:transition-none ${t.input}`}
        />
      </Field>
      <Field
        t={t}
        id={`${surface}-role`}
        label="What do you do?"
        hint="A sentence in your own words — a shopkeeper, a team lead, a researcher. I take it as where to start looking, never as the answer."
      >
        <textarea
          id={`${surface}-role`}
          value={role}
          onChange={(event) => onRole(event.target.value)}
          rows={3}
          maxLength={500}
          placeholder="I run a small ryokan on the coast…"
          className={`mt-1.5 w-full rounded-xl border px-4 py-3 text-base leading-6 outline-none transition-colors motion-reduce:transition-none ${t.input}`}
        />
      </Field>
      <Actions>
        {blocked ? (
          <Primary
            t={t}
            id="onboarding-you-next"
            label="Continue"
            disabled
            reason={blocked}
          />
        ) : (
          <Primary t={t} id="onboarding-you-next" label="Continue" working={working} onClick={onNext} />
        )}
        <BackLink t={t} onBack={onBack} disabled={working} />
      </Actions>
    </>
  )
}

/**
 * S3 — THE DREAM. The one question no amount of reading can answer.
 *
 * Genuinely optional, and it says so: pressing for it would teach the operator
 * that this is an interview. Skipping is a real control rather than an empty
 * Continue, so nobody has to guess that a blank box may be left blank.
 */
export function DreamScreen({
  t,
  variant,
  working,
  surface,
  name,
  dream,
  onDream,
  onNext,
  onBack,
}: ScreenProps & {
  name: string
  dream: string
  onDream: (value: string) => void
  onNext: () => void
  onBack: () => void
}) {
  const called = name.trim()
  return (
    <>
      {/* ADDRESSED BY NAME FROM THE MOMENT IT IS GIVEN — the cheapest proof
          that an answer went somewhere, and the opposite (asking for a name
          and never using it) is what makes a form feel like a form. */}
      <ScreenTitle
        t={t}
        variant={variant}
        lead="Think bigger than today. This is the one thing no amount of reading can tell me — it is a choice, and it is yours."
      >
        {called ? `${called}, what would you love this Cabinet to become?` : 'What would you love this Cabinet to become?'}
      </ScreenTitle>
      <Field t={t} id={`${surface}-dream`} label={<span className="sr-only">Your dream for the Cabinet</span>}>
        <textarea
          id={`${surface}-dream`}
          value={dream}
          onChange={(event) => onDream(event.target.value)}
          rows={3}
          maxLength={300}
          autoFocus
          placeholder="A calmer front desk, and guests who leave feeling looked after…"
          className={`mt-1.5 w-full rounded-xl border px-4 py-3 text-base leading-6 outline-none transition-colors motion-reduce:transition-none ${t.input}`}
        />
      </Field>
      <Actions>
        <Primary
          t={t}
          id="onboarding-dream-next"
          label={dream.trim() ? 'Continue' : 'Skip this for now'}
          working={working}
          onClick={onNext}
        />
        <BackLink t={t} onBack={onBack} disabled={working} />
      </Actions>
    </>
  )
}

/**
 * S4 — WHERE I BEGIN. The branch, and the last screen before anything is
 * granted.
 *
 * Both answers are real and neither is a default: the operator picks, and until
 * they do the primary says why it will not move. Continuing sends all three
 * answers as ONE act, so role, dream and preference land together.
 */
export function BeginScreen({
  t,
  variant,
  working,
  surface,
  startPreference,
  onPreference,
  onNext,
  onBack,
  blocked,
}: ScreenProps & {
  startPreference: '' | 'point' | 'decide'
  onPreference: (value: 'point' | 'decide') => void
  onNext: () => void
  onBack: () => void
  blocked: string
}) {
  return (
    <>
      <ScreenTitle
        t={t}
        variant={variant}
        lead="Either way, nothing is read until you have seen exactly what I would open and approved it."
      >
        Where should I begin?
      </ScreenTitle>
      <div className="mt-6 grid max-w-2xl gap-3">
        <ChoiceCard
          t={t}
          name={`${surface}-start-preference`}
          value="point"
          checked={startPreference === 'point'}
          onChange={() => onPreference('point')}
          label="Point me somewhere"
          detail="You name one folder, and I read it under a Charter you approve."
        />
        <ChoiceCard
          t={t}
          name={`${surface}-start-preference`}
          value="decide"
          checked={startPreference === 'decide'}
          onChange={() => onPreference('decide')}
          label="Go and find where I am most useful"
          detail="I look across what you have connected and propose where to start."
        />
      </div>
      <Actions>
        {blocked ? (
          <Primary t={t} id="onboarding-begin-next" label="Continue" disabled reason={blocked} />
        ) : (
          <Primary
            t={t}
            id="onboarding-begin-next"
            label="Continue"
            busyLabel="Setting up…"
            working={working}
            onClick={onNext}
          />
        )}
        <BackLink t={t} onBack={onBack} disabled={working} />
      </Actions>
    </>
  )
}

/**
 * BACK, EVERYWHERE, AND IT KEEPS WHAT WAS TYPED. The values live in the router
 * above these screens, so stepping back shows the operator their own words
 * rather than a blank — which is what makes going back safe enough to be worth
 * offering.
 */
export function BackLink({
  t,
  onBack,
  disabled,
  label = 'Back',
}: {
  t: { ghost: string }
  onBack: () => void
  disabled?: boolean
  label?: string
}) {
  return (
    <button
      type="button"
      onClick={onBack}
      disabled={disabled}
      className={`min-h-11 self-start rounded-xl px-4 py-2 text-sm font-medium disabled:opacity-45 ${t.ghost}`}
    >
      {label}
    </button>
  )
}
