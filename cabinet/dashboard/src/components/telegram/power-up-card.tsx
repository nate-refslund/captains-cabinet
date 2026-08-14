'use client'

/**
 * THE POWER-UP — one calm offer, on the home page, after onboarding is done.
 *
 * WHY IT IS NOT A WIZARD STEP. Connecting a phone is the most useful thing a
 * fresh cabinet can do next, and it is also the one thing that needs a second
 * app, a second device and a token from a third party. Putting it inside the
 * first-run wizard would put the highest-friction moment in front of the
 * operator before they have seen the Cabinet do anything at all. So it waits
 * here, once the home page renders, as an offer rather than a step.
 *
 * WHY IT CANNOT NAG. Three things switch it off, and each is honest:
 *   - Telegram is already connected. The server decides that from the stored
 *     address, so a connected cabinet never offers this again.
 *   - the operator said "not now". That answer is remembered in this browser,
 *     the same way the dashboard remembers consumer/advanced mode, and the flow
 *     stays reachable from Integrations forever after.
 *   - it renders nothing until it has read that answer, so a dismissed card
 *     never flashes back onto the screen for a frame.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'

/** Where "not now" is remembered. Namespaced like the dashboard-mode key. */
export const DISMISS_KEY = 'cabinet:telegram:power-up-dismissed'

export default function TelegramPowerUpCard({ connected }: { connected: boolean }) {
  // `null` = have not looked yet, and nothing renders in that state.
  const [dismissed, setDismissed] = useState<boolean | null>(null)

  useEffect(() => {
    try {
      setDismissed(window.localStorage.getItem(DISMISS_KEY) === '1')
    } catch {
      // Storage unavailable (private browsing): show the offer. A card the
      // operator can dismiss again is better than one they never see.
      setDismissed(false)
    }
  }, [])

  if (connected || dismissed !== false) return null

  return (
    <section
      aria-labelledby="telegram-power-up-title"
      className="rounded-2xl border border-zinc-800/80 bg-gradient-to-b from-zinc-900 to-zinc-950 p-5 shadow-xl shadow-black/30 sm:p-6"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[0.7rem] font-semibold uppercase tracking-[0.2em] text-violet-300/90">
            Power up
          </p>
          <h2 id="telegram-power-up-title" className="mt-1.5 text-lg font-semibold text-zinc-50">
            Want me to reach you on your phone?
          </h2>
          <p className="mt-1 max-w-xl text-sm leading-6 text-zinc-400">
            Four steps in Telegram and you get your briefings where you already read things. I will
            send you a message at the end so you can see it work.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setDismissed(true)
              try {
                window.localStorage.setItem(DISMISS_KEY, '1')
              } catch {
                // Nothing to do: the card is gone for this visit either way.
              }
            }}
            className="min-h-11 rounded-xl px-3 py-2 text-sm font-medium text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100"
          >
            Not now
          </button>
          <Link
            href="/integrations/telegram"
            className="min-h-11 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-violet-950/40 hover:bg-violet-500"
          >
            Connect Telegram
          </Link>
        </div>
      </div>
      <p className="mt-3 text-xs text-zinc-500">
        Not now is fine — it stays in Integrations whenever you want it.
      </p>
    </section>
  )
}
