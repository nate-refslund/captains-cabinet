/**
 * ACCESS — the two ways to give the Cabinet something to read, and what the
 * look found.
 *
 * TWO FIELDS ARE GONE FROM THE FOLDER SCREEN, both by ruling (2026-08-14):
 *
 *   · the per-window PURPOSE box. The operator answered it one screen earlier
 *     as the dream, and being asked again read as the product not listening
 *     ("this question i actually already answered in the second question about
 *     purpose"). The dream now seeds the purpose; the Charter still states it,
 *     and it is still editable — on the Charter screen, where it is a fact
 *     being approved rather than a form field being filled twice.
 *
 *   · the trust-DESTINATION radio. It granted nothing: its own helper text said
 *     "This sets a destination only. It grants no authority." Asking implies
 *     it does something. Where authority actually grows is the trust ladder,
 *     and that is where the question belongs.
 *
 * WHAT SURVIVES IS WHAT THE CORE REFUSES TO GO WITHOUT: the folder, whose data
 * it is, and under what right. Those are consent facts a sweep can never
 * derive, and the core refuses an unclassified source — so this screen refuses
 * first, with the reason on the screen, instead of submitting into a refusal.
 */
import type { FormEvent } from 'react'

import type {
  ConnectorCatalog,
  ConnectorTemplateChoice,
  OnboardingCard,
  OnboardingSweptConnector,
  OwnershipClass,
} from '@/lib/onboarding/types'
import FirstMateMessage from '../first-mate-message'
import { dayOf, sweepLine } from '@/lib/onboarding/sweep-line'
import {
  Actions,
  ChoiceCard,
  Field,
  Primary,
  Refusal,
  ScreenTitle,
  Secondary,
  type ScreenProps,
} from '../screen-chrome'
import { BackLink } from './questions'

/** How many tools the catalog shows before the operator has narrowed it. */
export const CATALOG_SHOWN = 12

/**
 * WHY THE CHARTER CANNOT BE PREPARED YET, in the operator's words — or '' when
 * it can. ONE missing thing at a time, in the order the screen reads, so the
 * reason is an instruction rather than an audit.
 */
export function folderBlockedReason(values: {
  source: string
  ownership: OwnershipClass | ''
  authorityBasis: string
}): string {
  if (!values.source.trim()) return 'Name a folder and I will show you exactly what I would open.'
  if (!values.ownership) return 'Say whose data is in it. I cannot check this, so I will not start without it.'
  if (!values.authorityBasis.trim()) return 'Say under what right you can grant it — a few words is enough.'
  return ''
}

/** S5A — THE FOLDER. */
export function FolderScreen({
  t,
  variant,
  working,
  surface,
  source,
  ownership,
  authorityBasis,
  onSource,
  onUseDocuments,
  onOwnership,
  onAuthorityBasis,
  onSubmit,
  onBack,
  backLabel,
  error,
  managing,
}: ScreenProps & {
  source: string
  ownership: OwnershipClass | ''
  authorityBasis: string
  onSource: (value: string) => void
  onUseDocuments: () => void
  onOwnership: (value: OwnershipClass) => void
  onAuthorityBasis: (value: string) => void
  onSubmit: (event: FormEvent) => void
  onBack: () => void
  backLabel: string
  error: string
  /** Reached from a finished journey's "Change it" rather than from the flow. */
  managing: boolean
}) {
  const blocked = folderBlockedReason({ source, ownership, authorityBasis })
  return (
    <form onSubmit={onSubmit}>
      <ScreenTitle
        t={t}
        variant={variant}
        lead="One specific folder. I will show you exactly what I would open before I read a single file."
      >
        {managing ? 'Change what I may read' : 'Which folder may I read?'}
      </ScreenTitle>

      <Field
        t={t}
        id={`${surface}-source`}
        label="Folder to look through"
        /* BREADTH IS ALLOWED; DEPTH IS WHAT IT COSTS. This used to read "The
           whole home folder is refused", which taught the operator that breadth
           was forbidden when the real trade-off is that a wider window makes the
           FIRST look shallower.
           LAYERED, NOT SHORTENED: the headline is the trade-off in one line and
           the whole caveat is one click behind — folding a disclosure keeps it,
           and this screen is over its word ceiling without the fold. The Charter
           states the same trade-off again before it is approved. */
        hint={
          <>
            One specific folder gives you a sharper first result.{' '}
            <details className="mt-1 inline-block">
              <summary className="cursor-pointer underline underline-offset-2">
                Can I point you at something bigger?
              </summary>
              <span className="mt-1 block">
                Yes — your whole home folder if you like, still read-only and still skipping
                secrets and personal files. My first look will only skim the surface of
                something that wide. The whole disk, and folders that belong to the system or
                to other people, I cannot take.
              </span>
            </details>
          </>
        }
      >
        <div className="mt-1.5 flex flex-col gap-2 sm:flex-row">
          <input
            id={`${surface}-source`}
            value={source}
            onChange={(event) => onSource(event.target.value)}
            className={`min-h-11 flex-1 rounded-xl border px-4 py-2.5 text-base outline-none ${t.input}`}
            autoComplete="off"
            autoFocus
          />
          <Secondary t={t} tone="outline" label="Use my Documents" onClick={onUseDocuments} />
        </div>
      </Field>

      <fieldset className="mt-6">
        <legend className={`text-sm font-medium ${t.title}`}>Whose data is in this folder?</legend>
        <div className="mt-2 grid max-w-2xl gap-2 text-sm">
          {(
            [
              ['self', 'Mine', 'My own machine, my own files.'],
              ['employer', "My employer's", 'I have a seat in it. I do not own it.'],
              ['third_party', "Someone else's", 'A client, a customer, a counterparty.'],
            ] as const
          ).map(([value, label, detail]) => (
            <ChoiceCard
              key={value}
              t={t}
              name={`${surface}-ownership`}
              value={value}
              checked={ownership === value}
              onChange={() => onOwnership(value)}
              label={label}
              detail={detail}
            />
          ))}
        </div>
        <p className={`mt-2 max-w-prose text-xs leading-5 ${t.faint}`}>
          Anything that is not yours is read-only and never written to. I cannot check this
          answer — I can only refuse to start without one.
        </p>
      </fieldset>

      <Field
        t={t}
        id={`${surface}-authority-basis`}
        label="Under what right?"
      >
        <input
          id={`${surface}-authority-basis`}
          value={authorityBasis}
          onChange={(event) => onAuthorityBasis(event.target.value)}
          maxLength={300}
          placeholder="my own laptop / read access granted to my seat / our engagement"
          className={`mt-1.5 w-full max-w-xl rounded-xl border px-4 py-2.5 text-base outline-none ${t.input}`}
          autoComplete="off"
        />
      </Field>

      {error && <Refusal t={t} variant={variant}>{error}</Refusal>}

      <Actions>
        {blocked ? (
          <Primary
            t={t}
            id="onboarding-folder-submit"
            label="Show me what you would read"
            disabled
            reason={blocked}
          />
        ) : (
          <Primary
            t={t}
            id="onboarding-folder-submit"
            type="submit"
            label="Show me what you would read"
            busyLabel="Preparing…"
            working={working}
          />
        )}
        <BackLink t={t} onBack={onBack} disabled={working} label={backLabel} />
      </Actions>
    </form>
  )
}

/**
 * S5B — CONNECT. The catalog, the connected list, and the one button that goes
 * and looks across all of them.
 *
 * THE STEP STAYS OPEN UNTIL THE OPERATOR CLOSES IT. It used to close itself the
 * moment a sweep produced anything, which made connecting a one-shot: the first
 * tool's results replaced the step and a second could never be added (Captain,
 * 2026-08-14: "i want to connect MANY connectors at once"). Only "go look"
 * hands the screen on.
 */
export function ConnectScreen({
  t,
  variant,
  working,
  surface,
  catalog,
  connected,
  picked,
  credential,
  fields,
  search,
  category,
  connectError,
  gatherLabel,
  onPick,
  onClearPick,
  onCredential,
  onField,
  onSearch,
  onCategory,
  onSubmit,
  onReconnect,
  onLook,
  onFolderInstead,
  onBack,
}: ScreenProps & {
  catalog: ConnectorCatalog | null
  connected: { name: string; label: string; row: OnboardingSweptConnector | undefined }[]
  picked: ConnectorTemplateChoice | null
  credential: string
  fields: Readonly<Record<string, string>>
  search: string
  category: string
  connectError: string
  gatherLabel: string | null
  onPick: (id: string) => void
  onClearPick: () => void
  onCredential: (value: string) => void
  onField: (key: string, value: string) => void
  onSearch: (value: string) => void
  onCategory: (value: string) => void
  onSubmit: (event: FormEvent) => void
  onReconnect: (id: string) => void
  onLook: () => void
  onFolderInstead: () => void
  onBack: () => void
}) {
  const templates = catalog?.templates ?? []
  const shelves = catalog?.categories ?? []
  const needle = search.trim().toLowerCase()
  // Free text over everything an operator might type: the tool's name, what it
  // is for, the shelf it sits on, and the host — so "invoice", "billing" and
  // "stripe.com" all find the same card.
  const matches = templates.filter((tpl) => {
    if (category && tpl.category !== category) return false
    if (!needle) return true
    return [tpl.label, tpl.summary, tpl.category_label, tpl.host, tpl.id]
      .join(' ')
      .toLowerCase()
      .includes(needle)
  })
  // Narrowed lists are shown WHOLE — a search that hides its own tail is worse
  // than no search. Only the unnarrowed catalog is capped, and the count says so.
  const narrowed = needle !== '' || category !== ''
  const shown = narrowed ? matches : matches.slice(0, CATALOG_SHOWN)
  const declared = new Set(connected.map((row) => row.name))
  const missingRequired = picked
    ? picked.fields.some((field) => field.required && !(fields[field.key] ?? '').trim())
    : false
  const connectBlocked = !picked
    ? ''
    : missingRequired
      ? 'Fill in the fields marked above and I can try the key.'
      : !credential.trim()
        ? 'Paste the key from step two and I will check what it can read.'
        : ''

  return (
    <>
      <ScreenTitle
        t={t}
        variant={variant}
        /* HONEST WHEN THERE IS NOTHING TO READ. "Go and find where I am most
           useful" needs a source; with none connected this says so and routes
           to the folder, rather than pretending to go looking at nothing. */
        lead={
          connected.length > 0
            ? 'Connect as many as you like — I read across all of them at once, only ever read, and then tell you where to start.'
            : 'To find where I am most useful, I need something to read. Connect as many tools as you like and I will read across all of them — only ever read. Or point me at a single folder now, which works with nothing connected.'
        }
      >
        What do you already use?
      </ScreenTitle>

      {connected.length > 0 && (
        <div className="mt-6">
          <h3 className={`text-sm font-semibold ${t.title}`}>Connected so far ({connected.length})</h3>
          <ul className="mt-2 space-y-1.5">
            {connected.map(({ name, row, label }) => {
              const ok = row?.connected === true
              const pending = row === undefined
              return (
                <li
                  key={name}
                  className={`flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-3 py-2 ${t.choice}`}
                >
                  <span
                    aria-hidden
                    className={`h-2 w-2 shrink-0 rounded-full ${ok ? 'bg-emerald-500' : pending ? 'bg-amber-500' : 'bg-red-500'}`}
                  />
                  <span className={`font-medium ${t.title}`}>{label}</span>
                  <span
                    className={`text-sm ${ok || pending ? t.faint : variant === 'world' ? 'text-red-800' : 'text-red-300'}`}
                  >
                    {pending ? 'not read yet' : sweepLine(row)}
                  </span>
                  {!ok && !pending && (
                    <Secondary
                      t={t}
                      tone="outline"
                      label="Try a different key"
                      disabled={working}
                      onClick={() => onReconnect(name)}
                    />
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {catalog === null ? (
        <p className={`mt-6 text-sm ${t.faint}`}>Finding the tools you can connect…</p>
      ) : templates.length > 0 && !picked ? (
        <div className="mt-6">
          <label htmlFor={`${surface}-connect-search`} className={`block text-sm font-medium ${t.title}`}>
            {connected.length > 0 ? 'Connect another tool' : 'Connect a tool'}
          </label>
          <input
            id={`${surface}-connect-search`}
            type="search"
            value={search}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="Search by name, or by what it holds"
            autoComplete="off"
            className={`mt-1.5 w-full max-w-md rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
          />

          {shelves.length > 1 && (
            <div className="mt-2.5 flex flex-wrap gap-1.5" role="group" aria-label="Filter by kind of tool">
              <button
                type="button"
                aria-pressed={category === ''}
                onClick={() => onCategory('')}
                className={`min-h-11 rounded-full border px-3 py-1 text-xs font-medium ${category === '' ? t.railOn : t.choice}`}
              >
                Everything
              </button>
              {shelves.map((shelf) => (
                <button
                  key={shelf.id}
                  type="button"
                  aria-pressed={category === shelf.id}
                  onClick={() => onCategory(category === shelf.id ? '' : shelf.id)}
                  className={`min-h-11 rounded-full border px-3 py-1 text-xs font-medium ${category === shelf.id ? t.railOn : t.choice}`}
                >
                  {shelf.label} <span className="opacity-60">{shelf.count}</span>
                </button>
              ))}
            </div>
          )}

          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {shown.map((tpl) => (
              <li key={tpl.id}>
                <button
                  type="button"
                  onClick={() => onPick(tpl.id)}
                  className={`flex h-full w-full flex-col items-start gap-1 rounded-xl border p-3 text-left transition-colors motion-reduce:transition-none ${t.choice}`}
                >
                  <span className={`flex w-full items-baseline justify-between gap-2 font-medium ${t.title}`}>
                    {tpl.label}
                    {declared.has(tpl.id) && (
                      <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[0.65rem] font-medium ${t.badge}`}>
                        connected
                      </span>
                    )}
                  </span>
                  <span className={`text-sm leading-5 ${t.muted}`}>{tpl.summary}</span>
                </button>
              </li>
            ))}
          </ul>

          {matches.length === 0 ? (
            <p className={`mt-3 max-w-prose text-sm ${t.muted}`}>
              Nothing here matches that. Every tool with a web address and a key can still be
              connected — choose{' '}
              <button
                type="button"
                onClick={() => onPick('rest')}
                className={`underline underline-offset-2 ${t.title}`}
              >
                Another REST list
              </button>{' '}
              and describe it yourself.
            </p>
          ) : (
            <p className={`mt-2.5 text-xs ${t.faint}`}>
              {narrowed
                ? `${matches.length} of ${templates.length} tools`
                : matches.length > shown.length
                  ? `Showing ${shown.length} of ${templates.length} tools — search or pick a kind to see the rest.`
                  : `${templates.length} tools`}
            </p>
          )}
        </div>
      ) : null}

      {picked && (
        <form onSubmit={onSubmit} aria-label="Connect a tool" className="mt-6">
          <div className={`space-y-3 rounded-xl border p-4 ${t.panel}`}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className={`text-base font-semibold ${t.title}`}>Connect {picked.label}</h3>
              <Secondary t={t} label="Choose a different tool" onClick={onClearPick} />
            </div>

            {/* WHERE THE KEY COMES FROM, in that product's own words. An ordered
                list because the steps ARE one — the key cannot be copied before
                it is made — and because the scope named in step two is the
                difference between handing over a reader and handing over a
                writer. */}
            {picked.how_to_connect.length > 0 && (
              <div>
                <p className={`text-sm font-medium ${t.title}`}>How to get the key</p>
                <ol className={`mt-1.5 list-decimal space-y-1 pl-5 text-sm leading-6 ${t.muted}`}>
                  {picked.how_to_connect.map((step, index) => (
                    <li key={`${picked.id}-step-${index}`}>{step}</li>
                  ))}
                </ol>
              </div>
            )}

            {picked.fields.map((field) => (
              <div key={field.key}>
                <label htmlFor={`${surface}-connect-${field.key}`} className={`block text-sm font-medium ${t.title}`}>
                  {field.label}
                  {!field.required && <span className={`ml-1 text-xs font-normal ${t.faint}`}>optional</span>}
                </label>
                <input
                  id={`${surface}-connect-${field.key}`}
                  type="text"
                  value={fields[field.key] ?? ''}
                  onChange={(event) => onField(field.key, event.target.value)}
                  placeholder={field.placeholder}
                  autoComplete="off"
                  spellCheck={false}
                  className={`mt-1 w-full rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
                />
                {field.help && <p className={`mt-1 text-xs ${t.faint}`}>{field.help}</p>}
              </div>
            ))}

            <div>
              <label htmlFor={`${surface}-connect-credential`} className={`block text-sm font-medium ${t.title}`}>
                Credential
              </label>
              <input
                id={`${surface}-connect-credential`}
                type="password"
                value={credential}
                onChange={(event) => onCredential(event.target.value)}
                placeholder="Paste your token or key"
                autoComplete="off"
                spellCheck={false}
                className={`mt-1 w-full rounded-lg border px-3 py-2 text-sm outline-none ${t.input}`}
              />
              {picked.credential_help && <p className={`mt-1 text-xs ${t.faint}`}>{picked.credential_help}</p>}
              {picked.key_looks_like && (
                <p className={`mt-1 text-xs ${t.faint}`}>A right-looking key: {picked.key_looks_like}.</p>
              )}
            </div>

            <p className={`text-xs leading-5 ${t.muted}`}>
              {picked.host ? (
                <>
                  This sends your credential to <span className={`font-medium ${t.title}`}>{picked.host}</span>, and
                  reads only — I list what is there, and never write.
                </>
              ) : (
                <>
                  This sends your credential only to the address you enter above, and reads only — I list what is
                  there, and never write.
                </>
              )}
            </p>

            {connectError && <Refusal t={t} variant={variant}>{connectError}</Refusal>}

            {connectBlocked ? (
              <Primary
                t={t}
                id="onboarding-connect-submit"
                label={`Connect ${picked.label}`}
                disabled
                reason={connectBlocked}
              />
            ) : (
              <Primary
                t={t}
                id="onboarding-connect-submit"
                type="submit"
                label={`Connect ${picked.label}`}
                busyLabel="Connecting…"
                working={working}
              />
            )}
          </div>
        </form>
      )}

      <Actions>
        {/* NEVER A BUTTON THAT CANNOT WORK. The core offers the look only once
            something is declared or a probe found something unreadable; where
            it does not, the folder is the primary and no gather is fabricated. */}
        {gatherLabel ? (
          <Primary
            t={t}
            id="onboarding-look"
            label={gatherLabel}
            busyLabel="Looking…"
            working={working}
            onClick={onLook}
          />
        ) : (
          <Primary
            t={t}
            id="onboarding-folder-instead"
            label="Point me at a folder instead"
            working={working}
            onClick={onFolderInstead}
          />
        )}
        {gatherLabel && (
          <Secondary
            t={t}
            label="Point me at a folder instead"
            disabled={working}
            onClick={onFolderInstead}
          />
        )}
        <BackLink t={t} onBack={onBack} disabled={working} />
      </Actions>
    </>
  )
}

/**
 * WHAT ONE SWEEP FOUND, PER TOOL — and the way on.
 *
 * Contents-free by construction: the core never puts a row's body on this
 * state, so this screen can only ever show counts, stamps and the reason a tool
 * gave for answering with nothing.
 *
 * IT ALWAYS CARRIES THE WAY FORWARD. The live "I cannot continue" report was
 * exactly this state with no onward control on the page: the connect panel had
 * handed over and the option row was gated out.
 */
export function SweepScreen({
  t,
  variant,
  working,
  swept,
  sweptAt,
  answeredTarget,
  onChooseFolder,
  onConnectMore,
  onRepoint,
  repointable,
  error,
  card,
}: ScreenProps & {
  swept: OnboardingSweptConnector[]
  sweptAt: string | null | undefined
  answeredTarget: string
  onChooseFolder: () => void
  onConnectMore: () => void
  onRepoint: () => void
  repointable: boolean
  error: string
  /** The welcome card, so the core's own sentence lands where the look did. */
  card: OnboardingCard | undefined
}) {
  const live = swept.filter((row) => row.connected).length
  const refused = swept.length - live
  return (
    <>
      <ScreenTitle
        t={t}
        variant={variant}
        lead={
          answeredTarget
            ? `You pointed me at ${answeredTarget}, so that is where I will spend depth. Now choose the folder that holds it — if it is called something else there, I will ask you what it is.`
            : 'Now name a folder I may read, and I will show you exactly what I would open before I open it.'
        }
      >
        {/* A COUNT THAT CANNOT OVERSTATE ITSELF. "all N" over the declared
            list would claim reads that were refused, so a refusal is named in
            the same sentence as the successes. */}
        {live === 0
          ? 'None of them answered yet.'
          : refused > 0
            ? `I read across ${live} of ${swept.length}.`
            : `I read across ${live === 1 ? 'it' : `all ${live}`}.`}
      </ScreenTitle>

      {/* THE CORE'S OWN SENTENCE, where the look it describes happened. This is
          the welcome card's message — its opening move, what it cannot know,
          what it probed and could not reach — and the sweep is the one screen
          of the welcome stage where the core has something to say. */}
      {card && <FirstMateMessage t={t} card={card} />}

      <ul className="mt-6 max-w-2xl space-y-1.5 text-sm">
        {swept.map((row) => (
          <li key={row.name} className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
            <span
              aria-hidden
              className={`h-2 w-2 shrink-0 self-center rounded-full ${row.connected ? 'bg-emerald-500' : 'bg-red-500'}`}
            />
            <span className={`font-medium ${t.title}`}>{row.name}</span>
            <span className={row.connected ? t.faint : variant === 'world' ? 'text-red-800' : 'text-red-300'}>
              {sweepLine(row)}
            </span>
          </li>
        ))}
      </ul>
      {sweptAt && (
        <p className={`mt-2 max-w-prose text-xs ${t.faint}`}>
          Read {dayOf(sweptAt)}. I list what is there and never write, and none of what is in them is
          stored here.
        </p>
      )}

      {error && <Refusal t={t} variant={variant}>{error}</Refusal>}

      <Actions>
        <Primary
          t={t}
          id="onboarding-sweep-folder"
          label="Choose a folder I may read"
          working={working}
          onClick={onChooseFolder}
        />
        <Secondary t={t} label="Connect another tool" disabled={working} onClick={onConnectMore} />
        {repointable && (
          <Secondary t={t} label="Point me somewhere else" disabled={working} onClick={onRepoint} />
        )}
      </Actions>
    </>
  )
}
