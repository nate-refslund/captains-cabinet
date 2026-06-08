'use client'

/**
 * Live wall clock for the kiosk header. Ticks every second on the client so
 * the time stays correct between the 15s server-data refreshes.
 *
 * Timezone is passed from the server (read from platform.yml captain_timezone)
 * so the displayed time is always the Captain's local time — never UTC, never
 * an ambiguous CET/CEST abbreviation (per the Cabinet timezone rule).
 */

import { useEffect, useState } from 'react'

function fmt(tz: string): string {
  try {
    return new Intl.DateTimeFormat('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
      timeZone: tz,
    }).format(new Date())
  } catch {
    // Bad/unknown TZ → fall back to local without crashing the wall display.
    return new Intl.DateTimeFormat('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(new Date())
  }
}

export default function LiveClock({ timezone = 'UTC' }: { timezone?: string }) {
  // Start null to avoid a hydration mismatch (server time ≠ first client tick).
  const [time, setTime] = useState<string | null>(null)

  useEffect(() => {
    setTime(fmt(timezone))
    const id = setInterval(() => setTime(fmt(timezone)), 1000)
    return () => clearInterval(id)
  }, [timezone])

  return (
    <span className="tabular-nums font-bold tracking-tight text-white">
      {time ?? '--:--:--'}
    </span>
  )
}
