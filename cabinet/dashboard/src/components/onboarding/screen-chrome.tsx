/**
 * The furniture every screen is built from — and the reason it is shared.
 *
 * ONE IDEA, ONE PRIMARY ACTION, ONE WAY BACK. Nine screens written nine times
 * drift into nine dialects: a Continue here, a Next there, a disabled button
 * with a reason on one screen and a disabled button with silence on the next.
 * The vocabulary of an interface is the signposting for someone navigating it,
 * so the shapes live here and each screen supplies only its own words.
 *
 * THE NO-MISTAKE RULE IS ENFORCED BY THE TYPE. `Primary` cannot be disabled
 * without a `reason`: the props make the two a pair, so a screen physically
 * cannot ship the failure this redesign exists to remove — a control that
 * refuses and does not say why (Captain, 2026-08-14: "i clicked ... but
 * nothing happens now and i cant continue").
 *
 * NO HOOKS ANYWHERE IN THIS FILE, deliberately: every disclosure is a native
 * `<details>`, which works without JavaScript and is keyboard-navigable for
 * free, and none of these components enters the hook order that
 * `journey-card.test.ts` scripts by index.
 */
import type { ReactNode } from 'react'

/** The token set a screen uses. Structural, so the card's theme object fits it
 *  without either file importing the other. */
export interface ScreenTheme {
  shell: string
  eyebrow: string
  title: string
  muted: string
  faint: string
  panel: string
  input: string
  primary: string
  secondary: string
  ghost: string
  danger: string
  choice: string
  choiceOn: string
  badge: string
  railOn: string
  railDone: string
  railOff: string
  railLine: string
  railLineDone: string
}

/** What every screen is handed. Screens are PURE: they render and they call
 *  back. Nothing here fetches, and nothing here holds state. */
export interface ScreenProps {
  t: ScreenTheme
  variant: 'dashboard' | 'world'
  /** A round-trip to the core is in flight; every act-firing control waits. */
  working: boolean
  /** Distinguishes ids between the two surfaces rendered on one page. */
  surface: string
}

/**
 * THE ONE QUESTION, at the size of a question rather than of a form label.
 *
 * The front used to set its questions at `text-xl` inside a card that also held
 * six other panels, which is how a question becomes a heading nobody reads.
 * A screen has one, and it is the largest thing on it.
 */
export function ScreenTitle({
  t,
  variant,
  children,
  lead,
}: {
  t: ScreenTheme
  variant: 'dashboard' | 'world'
  children: ReactNode
  /** One quiet sentence under the question. Never two. */
  lead?: ReactNode
}) {
  return (
    <header>
      <h2
        id="onboarding-card-title"
        className={`text-balance font-semibold tracking-[-0.02em] ${
          variant === 'world' ? 'text-xl' : 'text-2xl sm:text-[2rem] sm:leading-[1.15]'
        } ${t.title}`}
      >
        {children}
      </h2>
      {lead && <p className={`mt-3 max-w-prose text-sm leading-6 ${t.muted}`}>{lead}</p>}
    </header>
  )
}

/**
 * The primary act. Disabled and mute is not an option the props allow.
 *
 * The reason renders as live text beside the control AND as its
 * `aria-describedby`, so it reaches a screen reader at the moment focus lands
 * on the button rather than only by sight.
 */
export function Primary(
  props: {
    t: ScreenTheme
    id: string
    label: string
    /** What it says while the round-trip is in flight. */
    busyLabel?: string
    working?: boolean
  } & (
    // A REFUSED CONTROL NEEDS NO ACTION AND MUST CARRY A REASON. Both halves
    // are the type's job: a screen cannot ship a mute disabled button, and it
    // cannot wire an act to one that will not fire.
    | { disabled: true; reason: string; onClick?: undefined; type?: undefined }
    | { disabled?: false; reason?: undefined; onClick: () => void; type?: 'button' }
    | { disabled?: false; reason?: undefined; type: 'submit'; onClick?: undefined }
  )
) {
  const { t, id, label, busyLabel, working } = props
  const blocked = props.disabled === true
  const reason = blocked ? props.reason : ''
  const off = blocked || working === true
  return (
    <div className="flex flex-col gap-2">
      <button
        id={id}
        type={props.type === 'submit' ? 'submit' : 'button'}
        onClick={props.type === 'submit' ? undefined : props.onClick}
        disabled={off}
        aria-describedby={reason ? `${id}-why` : undefined}
        className={`min-h-11 w-fit rounded-xl px-5 py-2.5 text-sm font-semibold transition-[opacity,transform] duration-150 disabled:opacity-45 disabled:shadow-none motion-reduce:transition-none ${t.primary}`}
      >
        {working && busyLabel ? busyLabel : label}
      </button>
      {reason && (
        <p id={`${id}-why`} className={`text-xs leading-5 ${t.faint}`}>
          {reason}
        </p>
      )}
    </div>
  )
}

/**
 * The quieter ways on and out. Visually secondary BY RULE: an escape hatch
 * ("a folder instead", "skip this") has to be there — a flow with one door is
 * a trap — and it must not compete with the move the screen is for.
 */
export function Secondary({
  t,
  label,
  onClick,
  disabled,
  tone = 'ghost',
  name,
}: {
  t: ScreenTheme
  label: ReactNode
  onClick: () => void
  disabled?: boolean
  tone?: 'ghost' | 'outline' | 'danger'
  name?: string
}) {
  const skin = tone === 'outline' ? t.secondary : tone === 'danger' ? t.danger : t.ghost
  return (
    <button
      type="button"
      name={name}
      onClick={onClick}
      disabled={disabled}
      className={`min-h-11 rounded-xl px-4 py-2 text-sm font-medium disabled:opacity-45 ${skin}`}
    >
      {label}
    </button>
  )
}

/** The row a screen's actions sit in: the primary first, the quiet ones after. */
export function Actions({ children }: { children: ReactNode }) {
  return <div className="mt-8 flex flex-wrap items-start gap-x-3 gap-y-2">{children}</div>
}

/**
 * A labelled field. The label is always real — a placeholder is an example, not
 * a label, and an interface where the two do double duty loses the label the
 * moment anything is typed.
 */
export function Field({
  t,
  id,
  label,
  hint,
  children,
}: {
  t: ScreenTheme
  id: string
  label: ReactNode
  hint?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="mt-6">
      <label htmlFor={id} className={`block text-sm font-medium ${t.title}`}>
        {label}
      </label>
      {children}
      {hint && <p className={`mt-1.5 max-w-prose text-xs leading-5 ${t.faint}`}>{hint}</p>}
    </div>
  )
}

/** One choice in a set of two or three. Big enough to be a decision. */
export function ChoiceCard({
  t,
  name,
  value,
  checked,
  onChange,
  label,
  detail,
}: {
  t: ScreenTheme
  name: string
  value: string
  checked: boolean
  onChange: () => void
  label: ReactNode
  detail?: ReactNode
}) {
  return (
    <label
      className={`flex min-h-11 cursor-pointer items-start gap-3 rounded-xl border p-4 transition-colors motion-reduce:transition-none ${
        checked ? t.choiceOn : t.choice
      }`}
    >
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={onChange}
        className="mt-1"
      />
      <span>
        <span className={`block font-medium ${t.title}`}>{label}</span>
        {detail && <span className={`mt-0.5 block text-sm leading-6 ${t.muted}`}>{detail}</span>}
      </span>
    </label>
  )
}

/**
 * THE STANDING LINE. The one thing that survives every screen change besides
 * the rail: what the Cabinet may do, said in the same words every time.
 *
 * It replaces a "read-only" pill that sat in the card header and an always-open
 * connector summary that repeated the same promise on every step in different
 * words — the Captain read that repetition as the page not moving.
 */
export function StandingLine({ t }: { t: ScreenTheme }) {
  return (
    <p className={`mt-10 flex items-center gap-2 border-t border-current/10 pt-4 text-xs ${t.faint}`}>
      <span
        aria-hidden
        className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[0.65rem] font-medium ${t.badge}`}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-current" />
        read-only
      </span>
      I read; I never write. Nothing is opened until you approve it.
    </p>
  )
}

/**
 * A refusal, rendered AT the control that caused it.
 *
 * The card had one error line at its foot, several screens below the control an
 * operator had just used, so a refused answer read as a button that did
 * nothing. A screen is one idea, so its refusal belongs on it.
 */
export function Refusal({
  t,
  variant,
  children,
}: {
  t: ScreenTheme
  variant: 'dashboard' | 'world'
  children: ReactNode
}) {
  void t
  return (
    <p
      role="alert"
      className={`mt-3 text-sm font-medium ${
        variant === 'world' ? 'text-red-800' : 'text-red-300'
      }`}
    >
      {children}
    </p>
  )
}
