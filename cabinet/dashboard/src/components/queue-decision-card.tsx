'use client'

/**
 * One decision, one card, plain words (captain-surface v2, Arm A).
 *
 * Big-type headline + ONE supporting sentence; three plain buttons
 * [✓ Approve] [Later ▾] [✗ No]; an inline two-step confirm ON the card
 * showing consequence + undo before anything fires (deck ADAPT #5 — no
 * window.confirm); optimistic ✅ edit-in-place when the door reports the
 * decision landed. Technical truth (raw kinds, refs, the copyable reply
 * line) is disclosed behind Details ▸ — never deleted, never the default.
 *
 * All captain-facing strings arrive as props from the plain tables (the
 * jargon linter's vitest tooth lints them at the source); this file's own
 * literals are limited to glue and are linted by the source tooth.
 */
import { useState } from 'react'

export interface CardDetails {
  kind: string
  state: string
  urgency: string | null
  blastClass: string | null
  blastReach: string | null
  blastWorstCase: string | null
  decayRaw: string | null
  refs: string[]
  pid: string | null
  revision: string
  filedBy: string | null
}

export interface CardCopy {
  confirmYes: string
  confirmBack: string
  laterBriefing: string
  detailsLabel: string
  detailsSources: string
  detailsTyping: string
  openTelegram: string
  noButtons: string
  working: string
}

export interface QueueDecisionCardProps {
  anchorId: string
  headline: string
  sentence: string
  stateName: string
  kindName: string
  buttons: { approve: string; later: string; no: string }
  ritual: boolean
  decided: boolean
  decidable: boolean
  pid: string | null
  revision: string
  csrf: string | null
  telegramHref: string | null
  details: CardDetails
  copy: CardCopy
  /** Decisions get the amber accent; directions stay quiet. */
  accent: boolean
}

type Verb = 'approve' | 'no' | 'later'

interface ArmState {
  verb: Verb
  token: string
  consequence: string
  undo: string
}

type Phase =
  | { name: 'idle' }
  | { name: 'arming'; verb: Verb }
  | { name: 'confirm'; arm: ArmState }
  | { name: 'firing'; verb: Verb }
  | { name: 'done'; result: string; warn?: string }

interface DoorError {
  message: string
  refreshed?: {
    headline?: string
    sentence?: string
    revision?: string
    decided?: boolean
  }
}

async function postDoor(
  csrf: string,
  body: Record<string, unknown>
): Promise<{ status: number; json: Record<string, unknown> }> {
  const res = await fetch('/api/attention/verdict', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'X-Cabinet-CSRF': csrf,
    },
    body: JSON.stringify(body),
  })
  let json: Record<string, unknown> = {}
  try {
    json = (await res.json()) as Record<string, unknown>
  } catch {
    /* non-JSON body — treated as a plain failure below */
  }
  return { status: res.status, json }
}

export default function QueueDecisionCard(props: QueueDecisionCardProps) {
  const [phase, setPhase] = useState<Phase>({ name: 'idle' })
  const [error, setError] = useState<DoorError | null>(null)
  const [headline, setHeadline] = useState(props.headline)
  const [sentence, setSentence] = useState(props.sentence)
  const [revision, setRevision] = useState(props.revision)
  const [decided, setDecided] = useState(props.decided)

  const canAct =
    props.decidable && !props.decided && !decided && props.csrf !== null && props.pid !== null

  function absorb(json: Record<string, unknown>): void {
    const refreshed = json.refreshed as DoorError['refreshed'] | undefined
    if (refreshed) {
      if (typeof refreshed.headline === 'string') setHeadline(refreshed.headline)
      if (typeof refreshed.sentence === 'string') setSentence(refreshed.sentence)
      if (typeof refreshed.revision === 'string') setRevision(refreshed.revision)
      if (refreshed.decided === true) setDecided(true)
    }
    setError({
      message: typeof json.message === 'string' ? json.message : 'Something went wrong — try again.',
      refreshed,
    })
  }

  async function arm(verb: Verb): Promise<void> {
    if (!canAct || !props.csrf || !props.pid) return
    setError(null)
    setPhase({ name: 'arming', verb })
    const { status, json } = await postDoor(props.csrf, {
      pid: props.pid,
      verb,
      revision,
    })
    if (status === 200 && json.armed === true && typeof json.confirm_token === 'string') {
      setPhase({
        name: 'confirm',
        arm: {
          verb,
          token: json.confirm_token,
          consequence: typeof json.consequence === 'string' ? json.consequence : '',
          undo: typeof json.undo === 'string' ? json.undo : '',
        },
      })
      return
    }
    setPhase({ name: 'idle' })
    absorb(json)
  }

  async function fire(arm: ArmState): Promise<void> {
    if (!props.csrf || !props.pid) return
    setError(null)
    // Optimistic edit-in-place: the card flips to its working face at once;
    // the landed result (or the honest failure) replaces it.
    setPhase({ name: 'firing', verb: arm.verb })
    const { status, json } = await postDoor(props.csrf, {
      pid: props.pid,
      verb: arm.verb,
      revision,
      confirm_token: arm.token,
    })
    if (status === 200 && json.ok === true) {
      setDecided(true)
      setPhase({
        name: 'done',
        result: typeof json.plain_result === 'string' ? json.plain_result : '✅',
        warn: typeof json.journal_warn === 'string' ? json.journal_warn : undefined,
      })
      return
    }
    setPhase({ name: 'idle' })
    absorb(json)
  }

  const busy = phase.name === 'arming' || phase.name === 'firing'

  return (
    <div
      id={props.anchorId}
      className={`rounded-lg border bg-zinc-900 target:ring-2 target:ring-sky-500 ${
        props.accent
          ? 'border-l-4 border-zinc-800 border-l-amber-600/70'
          : 'border-zinc-800'
      }`}
      style={{ padding: '14px 16px' }}
    >
      <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
        <div className="min-w-0 flex-1">
          <p className="text-lg font-medium leading-snug text-white">{headline}</p>
          <p className="mt-1 text-sm text-zinc-400">{sentence}</p>
        </div>
        <span className="shrink-0 rounded bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-400">
          {phase.name === 'done' || decided ? '✅' : props.stateName}
        </span>
      </div>

      {phase.name === 'done' ? (
        <div className="mt-3 rounded border border-emerald-900 bg-emerald-950/40 px-3 py-2 text-sm text-emerald-300">
          ✅ {phase.result}
          {phase.warn ? (
            <span className="mt-1 block text-xs text-amber-300">{phase.warn}</span>
          ) : null}
        </div>
      ) : null}

      {error && phase.name !== 'done' ? (
        <div className="mt-3 rounded border border-amber-900 bg-amber-950/30 px-3 py-2 text-sm text-amber-200">
          {error.message}
        </div>
      ) : null}

      {phase.name === 'confirm' ? (
        <div className="mt-3 rounded border border-zinc-700 bg-zinc-950 px-3 py-2">
          <p className="text-sm text-zinc-200">{phase.arm.consequence}</p>
          <p className="mt-1 text-xs text-zinc-500">{phase.arm.undo}</p>
          <div className="mt-2 flex gap-2">
            <button
              onClick={() => void fire(phase.arm)}
              className="rounded bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-600"
            >
              {phase.arm.verb === 'later' ? props.copy.laterBriefing : props.copy.confirmYes}
            </button>
            <button
              onClick={() => setPhase({ name: 'idle' })}
              className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
            >
              {props.copy.confirmBack}
            </button>
          </div>
        </div>
      ) : null}

      {phase.name !== 'done' && !decided ? (
        canAct ? (
          phase.name === 'idle' || phase.name === 'arming' || phase.name === 'firing' ? (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {busy ? (
                <span className="text-sm text-zinc-500">{props.copy.working}</span>
              ) : (
                <>
                  {!props.ritual ? (
                    <button
                      onClick={() => void arm('approve')}
                      className="rounded bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-600"
                    >
                      {props.buttons.approve}
                    </button>
                  ) : null}
                  <button
                    onClick={() => void arm('later')}
                    className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
                  >
                    {props.buttons.later} ▾
                  </button>
                  <button
                    onClick={() => void arm('no')}
                    className="rounded border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
                  >
                    {props.buttons.no}
                  </button>
                  {props.ritual && props.telegramHref ? (
                    <a
                      href={props.telegramHref}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm text-sky-400 hover:underline"
                    >
                      {props.copy.openTelegram}
                    </a>
                  ) : null}
                </>
              )}
            </div>
          ) : null
        ) : (
          <p className="mt-3 text-sm text-zinc-500">
            {props.copy.noButtons}{' '}
            {props.telegramHref ? (
              <a
                href={props.telegramHref}
                target="_blank"
                rel="noreferrer"
                className="text-sky-400 hover:underline"
              >
                {props.copy.openTelegram}
              </a>
            ) : null}
          </p>
        )
      ) : null}

      <details className="mt-3 text-xs text-zinc-500">
        <summary className="cursor-pointer select-none text-zinc-500 hover:text-zinc-300">
          {props.copy.detailsLabel} ▸
        </summary>
        <div className="mt-2 space-y-2 border-t border-zinc-800 pt-2 font-mono text-[11px]">
          <div>
            {props.details.kind} · {props.details.state}
            {props.details.urgency ? ` · ${props.details.urgency}` : ''}
            {props.details.blastClass
              ? ` · ${props.details.blastClass}/${props.details.blastReach ?? ''}`
              : ''}
          </div>
          {props.details.blastWorstCase ? <div>{props.details.blastWorstCase}</div> : null}
          {props.details.decayRaw ? <div>{props.details.decayRaw}</div> : null}
          {props.details.refs.length > 0 ? (
            <div>
              <div className="mb-1 uppercase tracking-wide">{props.copy.detailsSources}</div>
              <ul className="space-y-0.5">
                {props.details.refs.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {props.details.pid ? (
            <div>
              <div className="mb-1">{props.copy.detailsTyping}</div>
              <code className="block select-all rounded bg-zinc-950 px-2 py-1 text-emerald-300">
                approve {props.details.pid}
              </code>
            </div>
          ) : null}
          <div>
            rev {revision}
            {props.details.filedBy ? ` · ${props.details.filedBy}` : ''}
          </div>
        </div>
      </details>
    </div>
  )
}
