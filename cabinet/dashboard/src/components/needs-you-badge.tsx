'use client'

/**
 * ⚑ N need you — the classic skin's glance strip (command-center §4B).
 *
 * Amber badge on EVERY authenticated page (mounted in the authenticated
 * layout), rendering the ONE census int from GET /api/attention/queue.
 * Hidden at N=0 — zero pixels of attention when nothing pends (north star:
 * outcome per unit of Captain attention). Click = navigation to /queue,
 * never actuation (read-only law; verdicts live in the Telegram binder).
 *
 * BUT NEVER HIDDEN AT UNKNOWN (2026-07-30). Hiding is itself a claim — the
 * absence of the badge is how this surface says "nothing needs you" — and for
 * five days it made that claim off a nine-day-old reading. Unknown gets a
 * grey chip, not silence: fewer pixels than an alarm, and honest. It also
 * STARTS unknown rather than 0, because the first paint happens before any
 * reading exists.
 *
 * GET-only by construction (the assertPlainGetFetches ratchet pattern):
 * single-argument fetch, no mutations, no server actions.
 */
import Link from 'next/link'
import { useEffect, useState } from 'react'
// From ./glance, NOT ./queue: queue.ts reads the census off disk (node:fs), and
// importing it from a 'use client' component breaks the client bundle outright.
import { badgeState } from '@/lib/attention/glance'

const POLL_MS = 60_000

export default function NeedsYouBadge() {
  /**
   * undefined = not asked yet (render nothing — "I haven't looked" is not a
   * claim); null = asked and nobody could tell (render the grey chip); a
   * number = a real reading. Never 0-as-a-stand-in for any of the three.
   */
  const [count, setCount] = useState<number | null | undefined>(undefined)

  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const res = await fetch('/api/attention/queue')
        if (!res.ok) {
          if (alive) setCount(null)
          return
        }
        const data: unknown = await res.json()
        if (!alive || typeof data !== 'object' || data === null) return
        const n = (data as { pendingCaptainItems?: unknown }).pendingCaptainItems
        setCount(typeof n === 'number' && Number.isFinite(n) ? n : null)
      } catch {
        // A read that did not happen is not a zero, and a held value with no
        // age on it is a guess: say unknown.
        if (alive) setCount(null)
      }
    }
    load()
    const t = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  // The three-way choice is a tested pure function, not three inline
  // conditions: an inline branch here cannot be driven by any suite in this
  // package (environment: 'node', no DOM renderer), so the logic lives where
  // a mutation to it turns something red.
  const state = badgeState(count)

  if (state.show === 'nothing') return null

  if (state.show === 'unknown') {
    return (
      <Link
        href="/queue"
        className="flex min-h-[32px] items-center gap-1.5 rounded-full border border-zinc-600/60 bg-zinc-500/10 px-3 py-1 text-xs font-medium text-zinc-400 hover:bg-zinc-500/20"
        title="I can't tell what's waiting — the list is not current. Open it for the reason."
      >
        <span aria-hidden>·</span>
        <span>unknown</span>
      </Link>
    )
  }

  return (
    <Link
      href="/queue"
      className="flex min-h-[32px] items-center gap-1.5 rounded-full border border-amber-700/60 bg-amber-500/15 px-3 py-1 text-xs font-medium text-amber-300 hover:bg-amber-500/25"
      title={`${state.n} decision${state.n === 1 ? '' : 's'} waiting on you — open the queue`}
    >
      <span aria-hidden>⚑</span>
      <span>
        {state.n} need{state.n === 1 ? 's' : ''} you
      </span>
    </Link>
  )
}
