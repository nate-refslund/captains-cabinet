'use client'

/**
 * Tiny client island that refreshes the kiosk view on an interval.
 *
 * The /display page itself is a SERVER component (data fetched at render via
 * getDisplayData). This island calls router.refresh() every `intervalMs`,
 * which re-runs the server render and streams fresh RSC payload WITHOUT a
 * full document reload — no flash, scroll position preserved, perfect for a
 * wall monitor that runs untouched for days.
 *
 * It renders nothing visible.
 */

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function AutoRefresh({ intervalMs = 15000 }: { intervalMs?: number }) {
  const router = useRouter()

  useEffect(() => {
    const id = setInterval(() => {
      router.refresh()
    }, intervalMs)
    return () => clearInterval(id)
  }, [router, intervalMs])

  return null
}
