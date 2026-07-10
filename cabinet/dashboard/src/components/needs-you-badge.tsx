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
 * GET-only by construction (the assertPlainGetFetches ratchet pattern):
 * single-argument fetch, no mutations, no server actions.
 */
import Link from 'next/link'
import { useEffect, useState } from 'react'

const POLL_MS = 60_000

export default function NeedsYouBadge() {
  const [count, setCount] = useState<number>(0)

  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const res = await fetch('/api/attention/queue')
        if (!res.ok) return
        const data: unknown = await res.json()
        if (!alive || typeof data !== 'object' || data === null) return
        const n = (data as { pendingCaptainItems?: unknown }).pendingCaptainItems
        setCount(typeof n === 'number' && Number.isFinite(n) ? n : 0)
      } catch {
        /* keep the last honest value */
      }
    }
    load()
    const t = setInterval(load, POLL_MS)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  if (count <= 0) return null

  return (
    <Link
      href="/queue"
      className="flex min-h-[32px] items-center gap-1.5 rounded-full border border-amber-700/60 bg-amber-500/15 px-3 py-1 text-xs font-medium text-amber-300 hover:bg-amber-500/25"
      title={`${count} decision${count === 1 ? '' : 's'} waiting on you — open the queue`}
    >
      <span aria-hidden>⚑</span>
      <span>
        {count} need{count === 1 ? 's' : ''} you
      </span>
    </Link>
  )
}
