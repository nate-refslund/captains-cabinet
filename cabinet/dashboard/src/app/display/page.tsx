/**
 * /display — wall-monitor "kiosk" view of the autonomous AI organization.
 *
 * Runs fullscreen in Chrome kiosk mode on the office Mac mini's monitor so
 * people walking past see the live cabinet state. Design target: legible from
 * 3+ metres — big type, generous spacing, high contrast on a zinc-950 canvas.
 *
 * Server component: all data is fetched at render via getDisplayData(). A tiny
 * client island (AutoRefresh) calls router.refresh() every 15s to re-run this
 * render with no full page reload. The clock ticks client-side every second.
 *
 * Robustness: getDisplayData() never throws (every source degrades to a safe
 * default), so this page never blank-screens. We also wrap the whole render in
 * a defensive try/catch that falls back to a minimal "data unavailable" frame.
 */

import fs from 'node:fs'
import yaml from 'js-yaml'
import { getDisplayData, WIP_CAP, type DisplayData } from '@/lib/display-data'
import { getOfficerConfig } from '@/lib/config'
import AutoRefresh from '@/components/display/auto-refresh'
import LiveClock from '@/components/display/live-clock'
import OfficerTile from '@/components/display/officer-tile'

// Always render fresh; the AutoRefresh island re-pulls every 15s.
export const dynamic = 'force-dynamic'

const PLATFORM_PATH =
  process.env.PLATFORM_PATH || '/opt/founders-cabinet/instance/config/platform.yml'

/** Read captain_timezone + captain_name from platform.yml. Safe fallbacks so a
 *  missing/unreadable file never breaks the wall display. */
function readPlatformMeta(): { timezone: string; captainName: string } {
  try {
    const raw = fs.readFileSync(PLATFORM_PATH, 'utf8')
    const cfg = (yaml.load(raw) ?? {}) as Record<string, unknown>
    const timezone = typeof cfg.captain_timezone === 'string' ? cfg.captain_timezone : 'UTC'
    const captainName = typeof cfg.captain_name === 'string' ? cfg.captain_name : 'Captain'
    return { timezone, captainName }
  } catch {
    return { timezone: 'UTC', captainName: 'Captain' }
  }
}

/** Officer slug → human title, best-effort via getOfficerConfig (never throws). */
function titleFor(slug: string): string {
  try {
    return getOfficerConfig(slug).title || slug.toUpperCase()
  } catch {
    return slug.toUpperCase()
  }
}

function OviBadge({ ovi }: { ovi: DisplayData['ovi'] }) {
  const { score, trend } = ovi
  const arrow = trend === 'up' ? '↑' : trend === 'down' ? '↓' : trend === 'flat' ? '·' : ''
  const arrowColor =
    trend === 'up' ? 'text-green-400' : trend === 'down' ? 'text-red-400' : 'text-zinc-500'
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-xs font-semibold uppercase tracking-widest text-zinc-500">OVI</span>
      <span className="text-2xl font-black tabular-nums text-white">
        {score != null ? score.toFixed(2) : '—'}
      </span>
      {arrow && <span className={`text-2xl font-black ${arrowColor}`}>{arrow}</span>}
    </div>
  )
}

export default async function DisplayPage() {
  let data: DisplayData
  try {
    data = await getDisplayData()
  } catch {
    // Last-resort frame — getDisplayData shouldn't throw, but a wall display
    // must never crash to a Next error page.
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-zinc-950 p-12">
        <AutoRefresh intervalMs={15000} />
        <h1 className="text-4xl font-black text-white">Captain&apos;s Cabinet</h1>
        <p className="text-xl text-zinc-500">Live data temporarily unavailable — retrying…</p>
      </main>
    )
  }

  const { timezone, captainName } = readPlatformMeta()
  const onlineCount = data.officers.filter((o) => o.online).length
  const totalOfficers = data.officers.length
  const { subagentActivity: sub } = data

  const updatedLabel = (() => {
    try {
      return new Intl.DateTimeFormat('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
        timeZone: timezone,
      }).format(new Date(data.meta.generatedAt))
    } catch {
      return new Date(data.meta.generatedAt).toISOString().slice(11, 19)
    }
  })()

  return (
    <main className="flex min-h-screen flex-col gap-6 bg-zinc-950 p-8 xl:p-10">
      {/* Client islands (render nothing visible except the clock value) */}
      <AutoRefresh intervalMs={15000} />

      {/* ===== Header strip ===== */}
      <header className="flex flex-wrap items-center justify-between gap-6 rounded-2xl border border-zinc-800 bg-zinc-900/60 px-8 py-5">
        <div className="flex items-baseline gap-4">
          <h1 className="text-3xl font-black tracking-tight text-white xl:text-4xl">
            Captain&apos;s Cabinet
          </h1>
          <span className="text-2xl font-semibold text-zinc-500">/</span>
          <span className="text-2xl font-semibold text-zinc-300 xl:text-3xl">
            {data.meta.activeProject}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-8">
          <OviBadge ovi={data.ovi} />

          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-black tabular-nums text-white">
              {onlineCount}
              <span className="text-zinc-500">/{totalOfficers}</span>
            </span>
            <span className="text-xs font-semibold uppercase tracking-widest text-zinc-500">
              officers online
            </span>
          </div>

          <div className="text-4xl xl:text-5xl">
            <LiveClock timezone={timezone} />
          </div>
        </div>
      </header>

      {/* ===== Officer grid ===== */}
      {totalOfficers === 0 ? (
        <div className="flex flex-1 items-center justify-center rounded-2xl border border-zinc-800 bg-zinc-900/40">
          <p className="text-2xl text-zinc-600">No officers registered yet.</p>
        </div>
      ) : (
        <section className="grid flex-1 grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {data.officers.map((officer) => (
            <OfficerTile key={officer.slug} officer={officer} title={titleFor(officer.slug)} />
          ))}
        </section>
      )}

      {/* ===== Active work strip ===== */}
      <section className="rounded-2xl border border-zinc-800 bg-zinc-900/60 px-8 py-5">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-zinc-500">
            Active work
          </h2>
          <span className="text-sm font-medium text-zinc-600">
            {data.activeTasks.length} in flight (WIP cap {WIP_CAP}/officer)
          </span>
        </div>

        {data.activeTasks.length === 0 ? (
          <p className="text-xl italic text-zinc-600">No active tasks right now.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-zinc-800/80">
            {data.activeTasks.slice(0, 8).map((t) => (
              <li key={`${t.officer}-${t.id}`} className="flex items-center gap-4 py-2.5">
                <span
                  className={`w-14 shrink-0 text-base font-black uppercase ${t.blocked ? 'text-red-400' : 'text-blue-400'}`}
                >
                  {t.officer}
                </span>
                <span className="min-w-0 flex-1 truncate text-xl font-medium text-zinc-100">
                  {t.blocked && <span className="mr-2 text-red-400" aria-hidden>⛓</span>}
                  {t.title}
                </span>
                <span className="shrink-0 text-base font-semibold tabular-nums text-zinc-500">
                  {t.age ?? '—'}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ===== Footer: subagent stats + recent events + generatedAt ===== */}
      <footer className="flex flex-wrap items-center justify-between gap-6 rounded-2xl border border-zinc-800 bg-zinc-900/40 px-8 py-4">
        <div className="flex flex-wrap items-center gap-8">
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-black tabular-nums text-blue-400">{sub.inFlight}</span>
            <span className="text-xs font-semibold uppercase tracking-widest text-zinc-500">
              subagents in flight
            </span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-black tabular-nums text-green-400">
              {sub.completedToday}
            </span>
            <span className="text-xs font-semibold uppercase tracking-widest text-zinc-500">
              completed today
            </span>
          </div>
          <div className="flex items-baseline gap-2">
            <span
              className={`text-2xl font-black tabular-nums ${sub.drift > 0 ? 'text-amber-400' : 'text-zinc-500'}`}
            >
              {sub.drift}
            </span>
            <span className="text-xs font-semibold uppercase tracking-widest text-zinc-500">
              drift
            </span>
          </div>
        </div>

        <div className="text-sm font-medium text-zinc-600">
          {captainName}&apos;s Cabinet · updated {updatedLabel}
        </div>
      </footer>
    </main>
  )
}
