import Link from 'next/link'
import redis, { getCostHistory } from '@/lib/redis'
import { getTmuxWindows, isClaudeAlive, isTelegramConnected } from '@/lib/docker'
import { getOfficerConfig, getConfig, getDashboardConfig } from '@/lib/config'
import { getProjects } from '@/actions/projects'
import { readKillswitch } from '@/lib/killswitch-state'
import { KILLSWITCH_CHECK_COMMAND } from '@/lib/world/killswitch'
import { freshnessOf } from '@/lib/liveness'
import OfficerCard from '@/components/officer-card'
import { StackedBarChart, HorizontalBars, ChartLegend } from '@/components/cost-chart'
import ConsumerFrontPage from '@/components/consumer/consumer-front-page'
import CardProducts from '@/components/consumer/card-products'
import CardCabinet from '@/components/consumer/card-cabinet'
import CardCosts from '@/components/consumer/card-costs'
import CardTasks from '@/components/consumer/card-tasks'
import CardLibrary from '@/components/consumer/card-library'
import { cookies } from 'next/headers'

export const dynamic = 'force-dynamic'

/**
 * `unknown` added 2026-07-31. `now - new Date(hb).getTime() > 10*60*1000` is
 * FALSE for `NaN`, so an unparseable heartbeat fell out of the ternary's
 * healthy end and the card said "Running"; a future-dated stamp did it forever.
 */
type OfficerStatus = 'running' | 'stopped' | 'no-heartbeat' | 'unknown'

interface OfficerInfo {
  role: string
  title: string
  botUsername: string
  voiceId: string
  claudeAlive: boolean
  telegramConnected: boolean
  status: OfficerStatus
  lastHeartbeat: string | null
}

/**
 * An unreachable store yields NO officers, not officers reported stopped.
 *
 * The roster comes entirely from the store; if the store did not answer, the
 * honest render is an empty roster under the store-posture banner. Falling
 * through with `status: 'stopped'` per officer would be a claim about the fleet
 * derived from a failure to ask — the census defect, one surface over. There are
 * no error boundaries in this app, so letting it throw is a blank 500 instead.
 */
async function getOfficerData(): Promise<OfficerInfo[]> {
  try {
    return await readOfficerData()
  } catch {
    return []
  }
}

async function readOfficerData(): Promise<OfficerInfo[]> {
  // Get all expected officers
  const expectedKeys = await redis.keys('cabinet:officer:expected:*')
  const heartbeatKeys = await redis.keys('cabinet:heartbeat:*')

  // Get running tmux windows
  let runningWindows: string[] = []
  try {
    runningWindows = await getTmuxWindows()
  } catch {
    // Docker may not be available in dev
  }

  // Collect all known roles
  const roles = new Set<string>()
  for (const key of expectedKeys) {
    roles.add(key.replace('cabinet:officer:expected:', ''))
  }
  for (const key of heartbeatKeys) {
    roles.add(key.replace('cabinet:heartbeat:', ''))
  }
  for (const w of runningWindows) {
    roles.add(w)
  }

  // Build officer info with parallel fetches
  const roleArray = Array.from(roles)
  const officers: OfficerInfo[] = await Promise.all(
    roleArray.map(async (role) => {
      const [heartbeat, expected, claudeAliveResult, telegramResult] = await Promise.all([
        redis.get(`cabinet:heartbeat:${role}`),
        redis.get(`cabinet:officer:expected:${role}`),
        isClaudeAlive(role),
        isTelegramConnected(role),
      ])

      const isRunning = runningWindows.includes(role)
      const config = getOfficerConfig(role)

      let status: OfficerStatus
      if (isRunning) {
        const hb = freshnessOf(heartbeat, Date.now(), 10 * 60 * 1000)
        status =
          hb.state === 'fresh'
            ? 'running'
            : hb.state === 'unknown'
              ? 'unknown'
              : 'no-heartbeat'
      } else if (expected === 'stopped') {
        status = 'stopped'
      } else if (expected === 'active') {
        status = 'stopped'
      } else {
        status = 'stopped'
      }

      return {
        role,
        title: config.title,
        botUsername: config.botUsername,
        voiceId: config.voiceId,
        claudeAlive: claudeAliveResult,
        telegramConnected: telegramResult,
        status,
        lastHeartbeat: heartbeat,
      }
    })
  )

  // Sort alphabetically
  officers.sort((a, b) => a.role.localeCompare(b.role))
  return officers
}


function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

/**
 * The one that may be handed a null. `—` is the mark the world rail already
 * uses for an unmeasured amount (`lib/world/ui-cards.ts formatMicro`,
 * `lib/attention/glance.ts UNMEASURED_GLYPH`) — same dialect, not a new one.
 */
function formatCentsOrDash(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return '—'
  return formatCents(cents)
}

/**
 * Read dashboard mode from cookies (server-side best-effort).
 *
 * The canonical source of truth is localStorage (client-side), but for the
 * initial server render we try reading from a cookie that the client optionally
 * sets. If the cookie isn't present, we fall back to 'consumer' (spec default).
 * The client will re-render after hydration if the localStorage value differs.
 */
async function getServerMode(): Promise<'consumer' | 'advanced'> {
  try {
    const cookieStore = await cookies()
    const val = cookieStore.get('cabinet:dashboard:mode')?.value
    if (val === 'advanced' || val === 'consumer') return val
  } catch {
    // cookies() may fail in some environments
  }
  return 'consumer'
}

export default async function DashboardPage() {
  const { consumerModeEnabled } = getDashboardConfig()

  // --- Consumer Mode branch ---
  // Feature flag gate at the PAGE level (not inside ConsumerFrontPage) so the
  // consumer card tree is structurally absent when the flag is off — no hooks,
  // no Redis reads for card data, purely inert. (Spec 032 plan §feature-flag)
  if (consumerModeEnabled) {
    const serverMode = await getServerMode()

    if (serverMode === 'consumer') {
      // Render consumer cards. KillSwitchHeader is in layout.tsx.
      return (
        <ConsumerFrontPage>
          <CardProducts />
          <CardCabinet />
          <CardCosts />
          <CardTasks />
          <CardLibrary />
        </ConsumerFrontPage>
      )
    }
    // If server-side mode is 'advanced', fall through to the advanced render.
    // After client hydration, useDashboardMode() takes over and the client can
    // switch modes without a full page reload.
  }

  // --- Advanced Mode (zero regression from pre-Spec-032 dashboard) ---
  const [officers, killswitch, costHistory, projects] = await Promise.all([
    getOfficerData(),
    readKillswitch(),
    getCostHistory(7),
    getProjects(),
  ])

  const activeProjectName = projects.find((p) => p.active)?.name || 'Unknown'
  const config = getConfig()
  const voiceConfig = config.voice as Record<string, unknown> | undefined
  const voiceGlobalEnabled = voiceConfig?.enabled === true

  const now = new Date().toLocaleString('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })

  const runningCount = officers.filter((o) => o.status === 'running').length
  const totalCount = officers.length
  // Officers whose heartbeat could not be read are neither running nor not —
  // "4/5 running" with a silent unknown in the denominator is a claim about
  // the fifth that nothing measured.
  const unknownCount = officers.filter((o) => o.status === 'unknown').length

  const today = costHistory[0]
  // `today?.total || 0` printed "$0.00" for a day nobody recorded — a measured
  // claim about money from an unanswered store. Null now survives to the pixel.
  const todayCost = today?.total ?? null
  const todayUnmeasuredReason = today?.unmeasuredReason ?? null

  // Per-officer breakdown for today. A null total means there is no breakdown
  // either — a zeroed roster reads as "every officer spent nothing".
  const officerCostData =
    today && today.total !== null
      ? Object.entries(today.officers)
          .map(([role, value]) => ({ label: role.toUpperCase(), value, role }))
          .sort((a, b) => b.value - a.value)
      : []

  // 7-day trend (stacked by officer). Days with NO reading are DROPPED, not
  // plotted at zero: a zero-height bar is a claim that the day cost nothing.
  const measuredDays = costHistory.filter(
    (d): d is typeof d & { total: number } => d.total !== null
  )
  const unmeasuredDayCount = costHistory.length - measuredDays.length
  const trendData = measuredDays
    .slice()
    .reverse()
    .map((d) => ({
      label: d.date.slice(5), // MM-DD
      total: d.total,
      segments: Object.entries(d.officers)
        .map(([role, value]) => ({ role, value }))
        .sort((a, b) => b.value - a.value),
    }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">
            Dashboard <span className="text-zinc-500">&mdash;</span>{' '}
            <span className="text-zinc-300">{activeProjectName}</span>
          </h1>
          <p className="mt-1 text-sm text-zinc-500">Last updated: {now}</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm">
            <span className="text-zinc-500">Daily cost: </span>
            <span className="font-medium text-white">
              {formatCentsOrDash(todayCost)}
            </span>
          </div>
          <div className="rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm">
            <span className="text-zinc-500">Officers: </span>
            <span className="font-medium text-white">
              {runningCount}/{totalCount} running
            </span>
            {unknownCount > 0 && (
              <span className="ml-2 text-amber-300">
                · {unknownCount} unreadable
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Kill switch status shown in Advanced mode — the header pill is always present */}
      {killswitch.engaged === true && (
        <div className="rounded-xl border border-red-500/50 bg-red-900/20 px-5 py-4">
          <p className="text-sm font-semibold text-red-400">
            Kill switch is ACTIVE &mdash; all officer operations are halted.
          </p>
          <p className="mt-0.5 text-xs text-zinc-500">
            Use the Stop All button in the header to resume.
          </p>
        </div>
      )}

      {/* An UNREAD emergency stop gets its own banner. Silence here used to be
          the claim "not engaged": the ACTIVE banner is absent in exactly the
          same way when the org has verified the stop is clear and when nobody
          could read it at all. */}
      {killswitch.engaged === null && (
        <div className="rounded-xl border border-dashed border-amber-400/60 bg-amber-900/10 px-5 py-4">
          <p className="text-sm font-semibold text-amber-300">
            Kill switch state is UNKNOWN &mdash; nobody could read it.
          </p>
          <p className="mt-0.5 text-xs text-amber-100/70">
            {killswitch.unknownReason}
          </p>
          <p className="mt-0.5 text-xs text-zinc-500">
            This is not &ldquo;not engaged&rdquo;. Verify with{' '}
            <code className="font-mono">{KILLSWITCH_CHECK_COMMAND}</code>.
          </p>
        </div>
      )}

      {/* Officer grid */}
      {officers.length === 0 ? (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-12 text-center">
          <p className="text-zinc-500">No officers registered yet.</p>
          <p className="mt-1 text-sm text-zinc-600">
            Officers will appear here once they start sending heartbeats.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {officers.map((officer) => (
            <OfficerCard
              key={officer.role}
              role={officer.role}
              title={officer.title}
              botUsername={officer.botUsername}
              voiceId={officer.voiceId}
              voiceGlobalEnabled={voiceGlobalEnabled}
              claudeAlive={officer.claudeAlive}
              telegramConnected={officer.telegramConnected}
              status={officer.status}
              lastHeartbeat={officer.lastHeartbeat}
            />
          ))}
        </div>
      )}

      {/* Cost Analytics Section */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Today's breakdown */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900" style={{ padding: '24px' }}>
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-white">Today&apos;s Cost</h2>
              <p className="mt-1 text-2xl font-bold text-white">
                {formatCentsOrDash(todayCost)}
              </p>
              {todayCost === null && (
                <p className="mt-1 text-xs text-amber-300">
                  {todayUnmeasuredReason ??
                    'no cost reading — this is not $0.00'}
                </p>
              )}
            </div>
            <Link
              href="/costs"
              className="text-sm text-zinc-500 transition-colors hover:text-zinc-300"
            >
              View all
            </Link>
          </div>
          <div className="mt-4">
            {officerCostData.length > 0 ? (
              <HorizontalBars data={officerCostData} />
            ) : (
              <p className="text-sm text-zinc-600">No cost data for today.</p>
            )}
          </div>
        </div>

        {/* 7-day trend */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900" style={{ padding: '24px' }}>
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white">7-Day Trend</h2>
            <ChartLegend />
          </div>
          <div className="mt-4">
            {trendData.length > 0 ? (
              <StackedBarChart data={trendData} height={180} />
            ) : (
              <p className="text-sm text-zinc-600">No cost data available.</p>
            )}
            {unmeasuredDayCount > 0 && (
              <p className="mt-2 text-xs text-amber-300">
                {unmeasuredDayCount} of the last {costHistory.length} days have
                no cost reading and are not plotted — absent, not zero.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
