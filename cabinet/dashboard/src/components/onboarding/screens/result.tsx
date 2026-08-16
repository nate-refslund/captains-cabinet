/**
 * APPROVE → THE LOOK → THE FIND. The three screens either side of the one
 * moment this product asks for something irreversible-feeling.
 */
import type { ReactNode } from 'react'

import { disclosureRows } from '@/lib/onboarding/disclosures'
import type { OnboardingCard } from '@/lib/onboarding/types'
import FirstMateMessage from '../first-mate-message'
import {
  Actions,
  Primary,
  Refusal,
  ScreenTitle,
  Secondary,
  type ScreenProps,
} from '../screen-chrome'

/**
 * S6 — APPROVE. The consent screen, and the ONE place the layering is
 * INVERTED: every fact is unfolded.
 *
 * Everywhere else the headline leads and the detail is one click behind,
 * because the operator is reading. Here they are GRANTING, and a fact behind a
 * fold at the moment of consent is a fact withheld at the moment it matters.
 * So the core hands this card its terms as separate rows (`grant`, `ownership`,
 * `limits`, `fingerprint`, and the binding and breadth notes where they apply)
 * and the screen lays every one of them out.
 *
 * IT IS NOT A MESSAGE. Nobody is talking here — this is a document being
 * signed, and dressing it as a chat line would borrow warmth for the one screen
 * that should read as exact.
 */
export function ApproveScreen({
  t,
  variant,
  working,
  card,
  onApprove,
  onChange,
  error,
}: ScreenProps & {
  card: OnboardingCard
  onApprove: () => void
  onChange: () => void
  error: string
}) {
  const rows = disclosureRows(card).filter((row) => row.layer !== 'headline')
  // THE CORE'S OWN LABEL for the way back. The words on an option are authored
  // there — a screen that renames them puts the operator's vocabulary and the
  // core's out of step, and the rename surface is PR3's, not this one's.
  const change = card.options.find((option) => option.action === 'propose_window')
  return (
    <>
      <ScreenTitle
        t={t}
        variant={variant}
        lead="This is exactly what I would open, in full. Nothing here is folded away, and nothing is read until you approve it."
      >
        Here is what I would read.
      </ScreenTitle>

      <dl className="mt-7 max-w-2xl">
        {rows.map((row) => (
          <div
            key={row.id}
            className="flex flex-col gap-1 border-t border-current/10 py-3 sm:flex-row sm:gap-5"
          >
            <dt
              className={`shrink-0 pt-0.5 text-[0.65rem] font-semibold uppercase tracking-[0.14em] sm:w-40 ${t.eyebrow}`}
            >
              {row.title}
            </dt>
            <dd className={`text-sm leading-6 ${t.muted}`}>{row.text.trim()}</dd>
          </div>
        ))}
      </dl>

      {error && <Refusal t={t} variant={variant}>{error}</Refusal>}

      <Actions>
        <Primary
          t={t}
          id="onboarding-approve"
          label="Approve, and find me one useful thing"
          busyLabel="Reading…"
          working={working}
          onClick={onApprove}
        />
        <Secondary
          t={t}
          label={change?.label ?? 'Change what I may read'}
          disabled={working}
          onClick={onChange}
        />
      </Actions>
    </>
  )
}

/**
 * THE PLAIN WORDS OF THE FIRST READ, in the order the core actually does them.
 *
 * NOT A FAKE PROGRESS BAR. Each line names a step that genuinely happens —
 * `open_ingest` resolves the approved root, the sensitivity rules drop files by
 * name, the window ranks most-informative-first under its file and byte caps,
 * and the finding is chosen from what was opened. The line advances on a timer
 * because the read is one round-trip and the client cannot see inside it; so it
 * says what is being done, never how much is left, and never claims a step
 * finished. The pattern is the hatch's (#342): say what you are doing, in the
 * operator's language, while you do it.
 */
export const SCAN_LINES: readonly string[] = Object.freeze([
  'Opening the folder you approved…',
  'Skipping anything that looks like a secret, a person, or pay…',
  'Reading the most informative files first…',
  'Looking for one thing worth your attention…',
])

/**
 * S7 — THE LOOK. It has no controls at all, on purpose: there is nothing for
 * the operator to decide while the read runs, and it flows straight into the
 * find with no click when the result lands.
 */
export function LookScreen({
  t,
  variant,
  line,
  source,
}: ScreenProps & { line: number; source: string | null | undefined }) {
  const step = Math.min(Math.max(line, 0), SCAN_LINES.length - 1)
  return (
    <>
      <style>{`
        @keyframes cabinet-scan-sweep {
          0%   { transform: translateX(-60%); }
          100% { transform: translateX(260%); }
        }
        .cabinet-scan-bar { animation: cabinet-scan-sweep 1.6s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
        @media (prefers-reduced-motion: reduce) {
          .cabinet-scan-bar { animation: none; transform: translateX(0); width: 100%; }
        }
      `}</style>
      <ScreenTitle t={t} variant={variant} lead={source ? `In ${source}. Read-only, once.` : undefined}>
        Reading it now.
      </ScreenTitle>
      <div
        aria-hidden
        className={`mt-7 h-0.5 w-full max-w-md overflow-hidden rounded-full ${t.railLine}`}
      >
        <div className={`cabinet-scan-bar h-full w-1/3 rounded-full ${t.railLineDone}`} />
      </div>
      <p role="status" aria-live="polite" className={`mt-4 text-base ${t.muted}`}>
        {SCAN_LINES[step]}
      </p>
      <ol className={`mt-5 space-y-1.5 text-sm ${t.faint}`}>
        {SCAN_LINES.map((text, index) => (
          <li key={text} className={index < step ? '' : 'opacity-40'}>
            <span aria-hidden className="mr-2">
              {index < step ? '✓' : '·'}
            </span>
            {text.replace('…', '')}
          </li>
        ))}
      </ol>
    </>
  )
}

/**
 * S8 — THE FIND. The first dividend, as a message from the First Mate, with the
 * rating INSIDE it.
 *
 * WHY THE RATING MOVED. It used to be a fieldset headed "Did this earn its
 * keep?" sitting under a separate panel headed "Receipt — where this came
 * from", and the Captain could not tell what he was being asked to grade:
 * "how can i answer on that based on the 'receipt'?". A grade belongs to the
 * thing it grades, so it is the message's own footer — and it carries a
 * correction field, because a grade with no way to say what is wrong is a dead
 * end with a thumbs-down on it.
 */
export function FindScreen({
  t,
  variant,
  working,
  surface,
  card,
  stamp,
  recorded,
  correction,
  onCorrection,
  onRate,
  onContinue,
  onRevoke,
  error,
}: ScreenProps & {
  card: OnboardingCard
  stamp: string | null | undefined
  recorded: string | null
  correction: string
  onCorrection: (value: string) => void
  onRate: (status: 'useful' | 'not_useful' | 'corrected', note: string) => void
  onContinue: () => void
  onRevoke: () => void
  error: string
}) {
  return (
    <>
      <ScreenTitle t={t} variant={variant}>
        {card.title}
      </ScreenTitle>
      {/* IF IT HAS AN AUTHOR IT IS A MESSAGE; IF NOT, IT IS NOT DRESSED AS ONE.
          An unattributed card still shows every row it carries and is still
          gradeable — the grade belongs to the finding, not to the container —
          but it renders as plain page content. */}
      {card.speaker ? (
        <FirstMateMessage
          t={t}
          card={card}
          stamp={stamp}
          footer={
            <Rating
              t={t}
              surface={surface}
              working={working}
              recorded={recorded}
              correction={correction}
              onCorrection={onCorrection}
              onRate={onRate}
            />
          }
        />
      ) : (
        <div className={`mt-6 p-4 ${t.panel}`}>
          {disclosureRows(card).map((row) => (
            <p key={row.id} className={`break-words text-sm leading-6 ${t.muted}`}>
              {row.text.trim()}
            </p>
          ))}
          {card.evidence.map((citation) => (
            <p key={`${citation.path}:${citation.line}`} className={`mt-2 text-xs ${t.faint}`}>
              <code className="font-mono">{citation.path}:{citation.line}</code>
              <span className="block">{citation.excerpt}</span>
            </p>
          ))}
          {card.egress && card.egress.withheld > 0 && (
            <p className={`mt-2 text-xs leading-5 ${t.faint}`}>
              I am holding back the words of {card.egress.withheld} of {card.egress.items} citation
              {card.egress.items === 1 ? '' : 's'}: this source is not yours to send. The file and
              line are above so you can open them yourself, or reclassify the source if I have it
              wrong.
            </p>
          )}
          <div className="mt-4 border-t border-current/10 pt-3">
            <Rating
              t={t}
              surface={surface}
              working={working}
              recorded={recorded}
              correction={correction}
              onCorrection={onCorrection}
              onRate={onRate}
            />
          </div>
        </div>
      )}

      {error && <Refusal t={t} variant={variant}>{error}</Refusal>}

      <Actions>
        <Primary
          t={t}
          id="onboarding-find-continue"
          label="Finish setting up"
          busyLabel="Finishing…"
          working={working}
          onClick={onContinue}
        />
        <Secondary t={t} label="Revoke folder access" disabled={working} onClick={onRevoke} />
      </Actions>
    </>
  )
}

/** The grade, and the one line that says what is wrong with it. */
function Rating({
  t,
  surface,
  working,
  recorded,
  correction,
  onCorrection,
  onRate,
}: {
  t: ScreenProps['t']
  surface: string
  working: boolean
  recorded: string | null
  correction: string
  onCorrection: (value: string) => void
  onRate: (status: 'useful' | 'not_useful' | 'corrected', note: string) => void
}) {
  if (recorded) {
    return (
      <p role="status" className={`text-sm ${t.muted}`}>
        Thank you — recorded as “{recorded.replace('_', ' ')}”
        {correction.trim() ? ', with your correction.' : '.'}
      </p>
    )
  }
  return (
    <div>
      <p className={`text-xs font-medium ${t.faint}`}>Was that any use?</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <RateButton t={t} label="Yes, useful" onClick={() => onRate('useful', correction)} disabled={working} />
        <RateButton
          t={t}
          label="Not useful yet"
          onClick={() => onRate('not_useful', correction)}
          disabled={working}
        />
        <RateButton
          t={t}
          label="Something is wrong"
          onClick={() => onRate('corrected', correction)}
          disabled={working}
        />
      </div>
      <label htmlFor={`${surface}-correction`} className={`mt-3 block text-xs ${t.faint}`}>
        What did I get wrong? One line, optional — it travels with your answer.
      </label>
      <input
        id={`${surface}-correction`}
        type="text"
        value={correction}
        onChange={(event) => onCorrection(event.target.value)}
        maxLength={200}
        autoComplete="off"
        className={`mt-1 min-h-11 w-full max-w-md rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
      />
    </div>
  )
}

function RateButton({
  t,
  label,
  onClick,
  disabled,
}: {
  t: ScreenProps['t']
  label: string
  onClick: () => void
  disabled: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`min-h-11 rounded-xl px-3 py-2 text-sm font-medium disabled:opacity-45 ${t.secondary}`}
    >
      {label}
    </button>
  )
}

/**
 * THE NOTICES — paused, revoked, purged, and the stage this build has no screen
 * for. They are states, not steps: the rail hides, and each carries every way
 * back that the core offers.
 */
export function NoticeScreen({
  t,
  variant,
  working,
  card,
  onChoose,
  error,
}: ScreenProps & {
  card: OnboardingCard
  onChoose: (action: OnboardingCard['options'][number]['action']) => void
  error: string
}) {
  return (
    <>
      <ScreenTitle t={t} variant={variant} lead={card.body}>
        {card.title}
      </ScreenTitle>
      {error && <Refusal t={t} variant={variant}>{error}</Refusal>}
      <Actions>
        {card.options.map((option, index) =>
          index === 0 && !option.danger ? (
            <Primary
              key={option.action}
              t={t}
              id={`onboarding-notice-${option.action}`}
              label={option.label}
              working={working}
              onClick={() => onChoose(option.action)}
            />
          ) : (
            <Secondary
              key={option.action}
              t={t}
              tone={option.danger ? 'danger' : 'outline'}
              label={option.label}
              disabled={working}
              onClick={() => onChoose(option.action)}
            />
          )
        )}
      </Actions>
    </>
  )
}

/**
 * THE TYPED CONFIRMATION. Deliberately the one screen where the primary control
 * stays refused until an exact word is typed — and the disabled reason says the
 * word, because a gate whose key is a secret is an obstacle, not a safeguard.
 *
 * The UI gate is convenience only: the core refuses any purge whose
 * confirmation is not exactly PURGE, server-side.
 */
export function PurgeScreen({
  t,
  variant,
  working,
  surface,
  confirmation,
  onConfirmation,
  onSubmit,
  onCancel,
  error,
}: ScreenProps & {
  confirmation: string
  onConfirmation: (value: string) => void
  onSubmit: (event: React.FormEvent) => void
  onCancel: () => void
  error: string
}) {
  return (
    <form onSubmit={onSubmit}>
      <ScreenTitle t={t} variant={variant}>
        Delete everything from this orientation?
      </ScreenTitle>
      <Facts t={t}>
        <li>
          <strong className={t.title}>Destroyed, permanently:</strong> the Charter, onboarding
          history, evidence trail, manifest, and derived excerpts. None of it comes back.
        </li>
        <li>
          <strong className={t.title}>Kept on purpose:</strong> the content-free record that a read
          happened — whose data, under what claimed right — with the folder path removed and no
          content in it. Explicitly exported review bundles are kept until you delete them.
        </li>
        <li>
          <strong className={t.title}>Afterwards:</strong> you can start a new orientation whenever
          you like. It begins from nothing, with a new evidence trail, and cannot see anything
          deleted here.
        </li>
      </Facts>
      <label
        htmlFor={`${surface}-purge-confirmation`}
        className={`mt-6 block text-sm font-medium ${t.title}`}
      >
        Type PURGE to confirm
      </label>
      <input
        id={`${surface}-purge-confirmation`}
        value={confirmation}
        onChange={(event) => onConfirmation(event.target.value)}
        autoComplete="off"
        className={`mt-1.5 min-h-11 w-full max-w-xs rounded-xl border px-4 py-2.5 text-base outline-none ${t.input}`}
      />

      {error && <Refusal t={t} variant={variant}>{error}</Refusal>}

      <div className="mt-8 flex flex-wrap items-start gap-3">
        <button
          type="submit"
          disabled={working || confirmation !== 'PURGE'}
          className="min-h-11 rounded-xl border border-red-600 bg-red-700 px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-45"
        >
          Permanently delete onboarding data
        </button>
        <Secondary t={t} tone="outline" label="Keep it" disabled={working} onClick={onCancel} />
      </div>
      {confirmation !== 'PURGE' && (
        <p className={`mt-2 text-xs ${t.faint}`}>
          Type PURGE above, in capitals, and this will delete.
        </p>
      )}
    </form>
  )
}

function Facts({ t, children }: { t: ScreenProps['t']; children: ReactNode }) {
  return <ul className={`mt-6 max-w-prose space-y-2 text-sm leading-6 ${t.muted}`}>{children}</ul>
}
