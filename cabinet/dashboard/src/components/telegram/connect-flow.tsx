'use client'

/**
 * CONNECT TELEGRAM — four steps, no terminal, and a round trip you can see.
 *
 * THE SHAPE, AND WHY. Every other setup surface in this app is one-directional:
 * you type something, it is stored, a tick appears. This one goes OUT to a phone
 * and comes BACK, and the operator has no way to check the middle of it. So the
 * message bubble is the through-line of the whole flow: step 3 draws an empty
 * one while the Cabinet listens for the operator's own "hi", and step 4 fills
 * the same bubble with the words that just landed on their phone. They compare
 * the screen to the phone in their hand — that is the proof, and it is the one
 * place this flow spends any boldness. Everything around it is the stepped
 * language the onboarding card already established.
 *
 * The numbered rail is here because this genuinely IS a sequence — you cannot
 * paste a token you have not been given, or capture an address from a bot that
 * does not exist. Where a flow is not a sequence, it should not be numbered.
 *
 * WHAT THE COMPONENTS ARE. Each step is an exported, props-only function: no
 * hooks, no fetching, nothing to script. The container below owns every piece of
 * state and every server call. That split is what lets the tests render a real
 * step in a real state and read the words the operator would read.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  confirmChatAndSend,
  getTelegramStatus,
  listenForFirstMessage,
  verifyBotToken,
  type TelegramStatus,
} from '@/actions/telegram-connect'
import { CONNECTED_MESSAGE, type ChatCandidate } from '@/lib/telegram/contract'

/**
 * The visual system, mirroring the dashboard variant of
 * `components/onboarding/journey-card.tsx themeOf('dashboard')`. Kept as a
 * local object rather than imported: journey-card owns the onboarding journey's
 * state machine and is edited by other work, and a shared import would couple
 * this flow's rendering to that file's churn for four colour strings.
 */
const T = {
  shell:
    'w-full rounded-2xl border border-zinc-800/80 bg-gradient-to-b from-zinc-900 to-zinc-950 text-zinc-100 shadow-2xl shadow-black/40',
  eyebrow: 'text-violet-300/90',
  title: 'text-zinc-50',
  muted: 'text-zinc-400',
  faint: 'text-zinc-500',
  panel: 'rounded-xl border border-zinc-800 bg-zinc-950/50',
  input:
    'border-zinc-700 bg-zinc-950 text-zinc-50 placeholder:text-zinc-600 focus:border-violet-400 focus:ring-2 focus:ring-violet-500/25',
  primary: 'bg-violet-600 text-white hover:bg-violet-500 shadow-lg shadow-violet-950/40',
  secondary:
    'border border-zinc-700 bg-zinc-800/70 text-zinc-100 hover:bg-zinc-800 hover:border-zinc-600',
  ghost: 'text-zinc-300 hover:bg-zinc-800/60 hover:text-white',
  choice: 'border-zinc-700 bg-zinc-900/40 hover:border-zinc-600',
  badge: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  railOn: 'border-violet-500 bg-violet-500/15 text-violet-200',
  railDone: 'border-emerald-500/60 bg-emerald-500/15 text-emerald-300',
  railOff: 'border-zinc-700 bg-transparent text-zinc-600',
  railLine: 'bg-zinc-800',
  railLineDone: 'bg-emerald-500/50',
  warn: 'rounded-xl border border-amber-500/40 bg-amber-950/20 text-amber-200',
  error: 'rounded-xl border border-red-700/70 bg-red-950/30 text-red-200',
}

export const STEPS = [
  { id: 'bot', label: 'Make a bot' },
  { id: 'token', label: 'Paste the token' },
  { id: 'hi', label: 'Say hi' },
  { id: 'done', label: 'Connected' },
] as const

export type StepId = (typeof STEPS)[number]['id']

/** How long the browser keeps listening before it offers to stop, and how often. */
export const LISTEN_INTERVAL_MS = 2500
export const LISTEN_MAX_TRIES = 24

/** The numbered rail. Four steps, one of them current, the ones behind it done. */
export function StepRail({ active }: { active: StepId }) {
  const index = STEPS.findIndex((s) => s.id === active)
  return (
    <ol className="mt-5 flex items-center gap-1.5" aria-label="Steps to connect Telegram">
      {STEPS.map((step, i) => {
        const current = i === index
        const done = i < index
        return (
          <li
            key={step.id}
            className="flex flex-1 flex-col items-center gap-1.5"
            aria-current={current ? 'step' : undefined}
          >
            <div className="flex w-full items-center gap-1.5">
              <span
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md border text-xs font-semibold transition-colors motion-reduce:transition-none ${
                  current ? T.railOn : done ? T.railDone : T.railOff
                }`}
              >
                {done ? '✓' : i + 1}
              </span>
              {i < STEPS.length - 1 && (
                <span className={`h-px flex-1 ${i < index ? T.railLineDone : T.railLine}`} />
              )}
            </div>
            <span
              className={`hidden text-center text-[0.65rem] font-medium sm:block ${
                current ? T.eyebrow : T.faint
              }`}
            >
              {step.label}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

/**
 * THE SIGNATURE. A phone bubble, drawn three ways from one component: waiting
 * (empty, breathing), theirs (the message the operator sent), and ours (the one
 * the Cabinet sent back). Same shape each time, so the flow reads as one
 * conversation rather than three unrelated screens.
 */
export function Bubble({
  from,
  text,
  side = 'them',
  state = 'settled',
}: {
  from: string
  text: string
  side?: 'them' | 'us'
  state?: 'settled' | 'waiting' | 'delivered'
}) {
  return (
    <div className={`flex flex-col ${side === 'us' ? 'items-end' : 'items-start'}`}>
      <span className={`px-1 text-[0.7rem] font-medium ${T.faint}`}>{from}</span>
      <div
        className={`mt-1 max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-6 ${
          side === 'us'
            ? 'rounded-br-sm bg-violet-600 text-white'
            : 'rounded-bl-sm border border-zinc-700 bg-zinc-800/80 text-zinc-100'
        } ${state === 'waiting' ? 'border-dashed text-zinc-500' : ''}`}
      >
        {state === 'waiting' ? (
          <span className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="h-1.5 w-1.5 animate-pulse rounded-full bg-zinc-500 motion-reduce:animate-none"
            />
            {text}
          </span>
        ) : (
          text
        )}
      </div>
      {state === 'delivered' && (
        <span className={`mt-1 px-1 text-[0.7rem] font-medium text-emerald-300`}>
          ✓ delivered to your phone
        </span>
      )}
    </div>
  )
}

/** STEP 1 — the part only a person can do, in Telegram itself. */
export function StepCreateBot({ onNext }: { onNext: () => void }) {
  return (
    <div className="mt-6">
      <h3 className={`text-xl font-semibold tracking-tight sm:text-2xl ${T.title}`}>
        Make yourself a bot
      </h3>
      <p className={`mt-2 text-sm leading-6 ${T.muted}`}>
        Telegram only hands out bots to a person, so this first bit happens over there. It takes
        about a minute and you never have to do it again.
      </p>
      <ol className={`mt-4 list-decimal space-y-2 pl-5 text-sm leading-6 ${T.muted}`}>
        <li>
          Open Telegram and start a chat with{' '}
          <a
            href="https://t.me/BotFather"
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-violet-300 underline underline-offset-2 hover:text-violet-200"
          >
            @BotFather
          </a>
          .
        </li>
        <li>
          Send it <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-200">/newbot</code>.
        </li>
        <li>Give it any name you like, then a username ending in “bot”.</li>
        <li>BotFather replies with a long token. Copy the whole line.</li>
      </ol>
      <div className={`mt-4 p-4 ${T.panel}`}>
        <p className={`text-xs font-medium ${T.faint}`}>A token looks like this</p>
        <p className="mt-1 break-all font-mono text-xs text-zinc-300">
          8123456789:AAF3kQ7pLm2xR9tYvB1cN4dW6eZ0hJ8sKqM
        </p>
        <p className={`mt-2 text-xs leading-5 ${T.muted}`}>
          Treat it like a password: anyone holding it can send messages as your bot. It stays on this
          machine, in a file only you can read.
        </p>
      </div>
      <button
        type="button"
        onClick={onNext}
        className={`mt-5 min-h-11 rounded-xl px-5 py-2 text-sm font-semibold ${T.primary}`}
      >
        I have my token
      </button>
    </div>
  )
}

/** STEP 2 — paste it once; the Cabinet checks it with Telegram before storing it. */
export function StepPasteToken({
  token,
  onTokenChange,
  onSubmit,
  onBack,
  busy,
  error,
}: {
  token: string
  onTokenChange: (value: string) => void
  onSubmit: () => void
  onBack: () => void
  busy: boolean
  error: string | null
}) {
  return (
    <form
      className="mt-6"
      aria-label="Paste your bot token"
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit()
      }}
    >
      <h3 className={`text-xl font-semibold tracking-tight sm:text-2xl ${T.title}`}>
        Paste the token
      </h3>
      <p className={`mt-2 text-sm leading-6 ${T.muted}`}>
        I will ask Telegram whether it works before I keep it, and tell you which bot it belongs to.
      </p>
      <label htmlFor="telegram-token" className="sr-only">
        Bot token from BotFather
      </label>
      <input
        id="telegram-token"
        name="telegram-token"
        type="password"
        autoComplete="off"
        spellCheck={false}
        value={token}
        onChange={(e) => onTokenChange(e.target.value)}
        placeholder="Paste the whole line BotFather sent"
        className={`mt-4 w-full rounded-xl border px-4 py-3 font-mono text-base leading-6 outline-none transition-colors motion-reduce:transition-none ${T.input}`}
      />
      {error && <p className={`mt-3 px-4 py-3 text-sm leading-6 ${T.error}`}>{error}</p>}
      <div className="mt-5 flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className={`min-h-11 rounded-xl px-4 py-2 text-sm font-medium ${T.ghost}`}
        >
          Back
        </button>
        <button
          type="submit"
          disabled={busy || token.trim() === ''}
          className={`min-h-11 rounded-xl px-5 py-2 text-sm font-semibold disabled:opacity-50 disabled:shadow-none ${T.primary}`}
        >
          {busy ? 'Checking with Telegram…' : 'Check this token'}
        </button>
      </div>
    </form>
  )
}

/** STEP 3 — the operator messages the bot; the Cabinet captures the address. */
export function StepSayHi({
  botUsername,
  listening,
  attempts,
  candidate,
  others,
  groupOnly,
  onListen,
  onConfirm,
  onBack,
  busy,
  error,
}: {
  botUsername: string
  listening: boolean
  attempts: number
  candidate: ChatCandidate | null
  others: ChatCandidate[]
  groupOnly: boolean
  onListen: () => void
  onConfirm: (chatId: string) => void
  onBack: () => void
  busy: boolean
  error: string | null
}) {
  const handle = botUsername ? `@${botUsername}` : 'your new bot'
  return (
    <div className="mt-6">
      <h3 className={`text-xl font-semibold tracking-tight sm:text-2xl ${T.title}`}>
        Now say hi to {handle}
      </h3>
      <p className={`mt-2 text-sm leading-6 ${T.muted}`}>
        Open {handle} in Telegram and send it anything — “hi” is plenty. That message is how I learn
        which chat is yours. I am watching for it now.
      </p>
      {botUsername && (
        <a
          href={`https://t.me/${botUsername}`}
          target="_blank"
          rel="noopener noreferrer"
          className={`mt-4 inline-flex min-h-11 items-center rounded-xl px-4 py-2 text-sm font-semibold ${T.secondary}`}
        >
          Open {handle} in Telegram
        </a>
      )}

      <div className={`mt-5 p-4 ${T.panel}`}>
        {candidate ? (
          <Bubble from={candidate.label || 'your message'} text="hi" />
        ) : (
          <Bubble
            from={handle}
            text={listening ? 'listening for your message…' : 'nothing yet'}
            state="waiting"
          />
        )}
        {!candidate && (
          <p className={`mt-3 text-xs ${T.faint}`} role="status">
            {listening
              ? `Checked ${attempts} time${attempts === 1 ? '' : 's'}. Nothing is sent or deleted while I look.`
              : attempts > 0
                ? 'I stopped looking. Send your bot a message and I will start again.'
                : 'Not looking yet.'}
          </p>
        )}
      </div>

      {groupOnly && !candidate && (
        <p className={`mt-4 px-4 py-3 text-sm leading-6 ${T.warn}`}>
          I can only see a message from a group. Message the bot directly, in a one-to-one chat, so I
          know which one is you.
        </p>
      )}

      {candidate && others.length > 0 && (
        <p className={`mt-4 px-4 py-3 text-sm leading-6 ${T.warn}`}>
          More than one person has messaged this bot. I will use the first one, {candidate.label || candidate.chatId}
          . The others I saw: {others.map((o) => o.label || o.chatId).join(', ')}. If that first one is
          not you, block them in Telegram, make a fresh bot, and start again.
        </p>
      )}

      {!candidate && !listening && attempts >= LISTEN_MAX_TRIES && (
        <p className={`mt-4 px-4 py-3 text-sm leading-6 ${T.warn}`}>
          I have not heard from you yet. Open {handle} in Telegram, send it any message, and I will
          keep listening.
        </p>
      )}

      {error && <p className={`mt-4 px-4 py-3 text-sm leading-6 ${T.error}`}>{error}</p>}

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className={`min-h-11 rounded-xl px-4 py-2 text-sm font-medium ${T.ghost}`}
        >
          Back
        </button>
        {candidate ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => onConfirm(candidate.chatId)}
            className={`min-h-11 rounded-xl px-5 py-2 text-sm font-semibold disabled:opacity-50 disabled:shadow-none ${T.primary}`}
          >
            {busy
              ? 'Sending you a message…'
              : `Yes, that is me${candidate.label ? ` — ${candidate.label}` : ''}`}
          </button>
        ) : (
          <button
            type="button"
            disabled={listening}
            onClick={onListen}
            className={`min-h-11 rounded-xl px-5 py-2 text-sm font-semibold disabled:opacity-50 ${T.secondary}`}
          >
            {listening ? 'Listening…' : 'Keep listening'}
          </button>
        )}
      </div>
    </div>
  )
}

/**
 * STEP 4 — the round trip, and an honest account of what happens next.
 *
 * `crewAwake` is the state of the officers on this machine, read server-side.
 * The "what does not work yet" panel used to end "that is the next thing to
 * switch on" unconditionally — which is FALSE on a cabinet whose crew is
 * already awake, and the sentence was written before there was any way to
 * switch it on from a screen. It now says which of the two the operator is
 * actually looking at. It defaults to `false` because a caller that does not
 * know the crew's state must not claim it is awake.
 */
export function StepConnected({
  botUsername,
  chatId,
  wrote,
  notes,
  crewAwake = false,
  onRestart,
}: {
  botUsername: string
  chatId: string
  wrote: string[]
  notes: string[]
  crewAwake?: boolean
  onRestart: () => void
}) {
  const handle = botUsername ? `@${botUsername}` : 'your bot'
  return (
    <div className="mt-6">
      <span
        className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[0.7rem] font-medium ${T.badge}`}
      >
        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
        Connected
      </span>
      <h3 className={`mt-2 text-xl font-semibold tracking-tight sm:text-2xl ${T.title}`}>
        Check your phone
      </h3>
      <p className={`mt-2 text-sm leading-6 ${T.muted}`}>
        I just sent this to {handle}. It should be on your phone now — the same words, in the same
        chat.
      </p>
      <div className={`mt-4 p-4 ${T.panel}`}>
        <Bubble from={handle} text={CONNECTED_MESSAGE} side="us" state="delivered" />
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <div className={`p-4 ${T.panel}`}>
          <h4 className={`text-sm font-semibold ${T.title}`}>What arrives here now</h4>
          <p className={`mt-1.5 text-sm leading-6 ${T.muted}`}>
            Briefings, and anything your Cabinet decides is worth your attention — each one when it
            is scheduled to run, not immediately.
          </p>
        </div>
        <div className={`p-4 ${T.panel}`}>
          <h4 className={`text-sm font-semibold ${T.title}`}>What does not work yet</h4>
          <p className={`mt-1.5 text-sm leading-6 ${T.muted}`}>
            {crewAwake ? (
              <>
                Replying to the bot. Your Cabinet is awake in the background, so there is
                someone to answer — the lane that carries your replies back to them is the
                part still being built.
              </>
            ) : (
              <>
                Replying to the bot. Messages you send back are only read once your Cabinet is
                running in the background and has someone awake to answer — you can switch that
                on from your home page, under Your Cabinet.
              </>
            )}
          </p>
        </div>
      </div>

      <div className={`mt-4 p-4 ${T.panel}`}>
        <p className={`text-xs font-medium uppercase tracking-wide ${T.faint}`}>
          Your address: {chatId}
        </p>
        {wrote.length > 0 && (
          <ul className={`mt-2 space-y-1 text-sm leading-6 ${T.muted}`}>
            {wrote.map((line) => (
              <li key={line}>Saved to {line}.</li>
            ))}
          </ul>
        )}
        {notes.map((note) => (
          <p key={note} className={`mt-2 text-sm leading-6 text-amber-200`}>
            {note}
          </p>
        ))}
      </div>

      <button
        type="button"
        onClick={onRestart}
        className={`mt-5 min-h-11 rounded-xl px-4 py-2 text-sm font-medium ${T.ghost}`}
      >
        Connect a different bot
      </button>
    </div>
  )
}

/**
 * The container. Owns the step, the bounded listening loop and every server
 * call; renders one step at a time.
 */
export default function TelegramConnectFlow({
  initialStatus,
  crewAwake = false,
}: {
  initialStatus: TelegramStatus
  crewAwake?: boolean
}) {
  const [step, setStep] = useState<StepId>(initialStatus.connected ? 'done' : 'bot')
  const [token, setToken] = useState('')
  const [botUsername, setBotUsername] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [listening, setListening] = useState(false)
  const [attempts, setAttempts] = useState(0)
  const [candidate, setCandidate] = useState<ChatCandidate | null>(null)
  const [others, setOthers] = useState<ChatCandidate[]>([])
  const [groupOnly, setGroupOnly] = useState(false)
  const [chatId, setChatId] = useState(initialStatus.chatId ?? '')
  const [wrote, setWrote] = useState<string[]>([])
  const [notes, setNotes] = useState<string[]>([])

  // The loop's stop flag. A ref rather than state: the loop reads it between
  // awaits, where a state value would be the one captured when it started.
  const stopped = useRef(false)
  useEffect(() => () => {
    stopped.current = true
  }, [])

  const listen = useCallback(async () => {
    stopped.current = false
    setListening(true)
    setError(null)
    setAttempts(0)
    for (let tries = 1; tries <= LISTEN_MAX_TRIES; tries++) {
      if (stopped.current) break
      setAttempts(tries)
      const result = await listenForFirstMessage()
      if (stopped.current) break
      if (!result.ok) {
        setError(result.error ?? 'I could not check just now.')
        break
      }
      setGroupOnly(Boolean(result.groupOnly))
      if (result.candidate) {
        setCandidate(result.candidate)
        setOthers(result.others ?? [])
        break
      }
      if (tries < LISTEN_MAX_TRIES) {
        await new Promise((resolve) => setTimeout(resolve, LISTEN_INTERVAL_MS))
      }
    }
    setListening(false)
  }, [])

  const submitToken = useCallback(async () => {
    setBusy(true)
    setError(null)
    const result = await verifyBotToken(token)
    setBusy(false)
    if (!result.ok) {
      setError(result.error ?? 'That token did not work.')
      return
    }
    // The token has been proven and stored; there is no reason to keep a copy in
    // this page's memory, and every reason not to.
    setToken('')
    setBotUsername(result.botUsername ?? '')
    setStep('hi')
    void listen()
  }, [token, listen])

  const confirm = useCallback(async (id: string) => {
    stopped.current = true
    setBusy(true)
    setError(null)
    const result = await confirmChatAndSend(id)
    setBusy(false)
    if (!result.delivered) {
      setError(result.error ?? 'The message did not go through.')
      return
    }
    setChatId(id)
    setWrote(result.wrote ?? [])
    setNotes(result.error ? [...(result.notes ?? []), result.error] : (result.notes ?? []))
    setStep('done')
  }, [])

  const restart = useCallback(async () => {
    stopped.current = true
    setStep('bot')
    setToken('')
    setBotUsername('')
    setCandidate(null)
    setOthers([])
    setGroupOnly(false)
    setAttempts(0)
    setError(null)
    setWrote([])
    setNotes([])
    // Re-read rather than assume: another surface may have changed it.
    try {
      const fresh = await getTelegramStatus()
      setChatId(fresh.chatId ?? '')
    } catch {
      // Leaving the last known address on screen is honest enough here.
    }
  }, [])

  return (
    <section className={`p-6 sm:p-7 ${T.shell}`} aria-labelledby="telegram-connect-title">
      <p className={`text-[0.7rem] font-semibold uppercase tracking-[0.2em] ${T.eyebrow}`}>
        Your Cabinet on your phone
      </p>
      <h2 id="telegram-connect-title" className={`mt-1.5 text-2xl font-semibold tracking-tight ${T.title}`}>
        Connect Telegram
      </h2>
      <StepRail active={step} />

      {step === 'bot' && <StepCreateBot onNext={() => setStep('token')} />}
      {step === 'token' && (
        <StepPasteToken
          token={token}
          onTokenChange={setToken}
          onSubmit={submitToken}
          onBack={() => setStep('bot')}
          busy={busy}
          error={error}
        />
      )}
      {step === 'hi' && (
        <StepSayHi
          botUsername={botUsername}
          listening={listening}
          attempts={attempts}
          candidate={candidate}
          others={others}
          groupOnly={groupOnly}
          onListen={() => void listen()}
          onConfirm={(id) => void confirm(id)}
          onBack={() => {
            stopped.current = true
            setStep('token')
          }}
          busy={busy}
          error={error}
        />
      )}
      {step === 'done' && (
        <StepConnected
          botUsername={botUsername}
          chatId={chatId}
          wrote={wrote}
          notes={notes}
          crewAwake={crewAwake}
          onRestart={() => void restart()}
        />
      )}
    </section>
  )
}
