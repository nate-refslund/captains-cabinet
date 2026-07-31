import { getCostHistory, getTokenCostHistory } from '@/lib/redis'
import { BarChart, HorizontalBars, StackedBarChart, ChartLegend } from '@/components/cost-chart'

export const dynamic = 'force-dynamic'

function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`
}

/** Unmeasured money renders as the em-dash, never as $0.00 (world-rail dialect). */
function formatCentsOrDash(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return '—'
  return formatCents(cents)
}

function formatMicro(micro: number): string {
  return `$${(micro / 1000000).toFixed(2)}`
}

function formatMicroOrDash(micro: number | null | undefined): string {
  if (micro === null || micro === undefined) return '—'
  return formatMicro(micro)
}

function formatTokens(tokens: number): string {
  if (tokens >= 1000000) return `${(tokens / 1000000).toFixed(1)}M`
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(0)}K`
  return String(tokens)
}

export default async function CostsPage() {
  const [history, tokenHistory] = await Promise.all([
    getCostHistory(30),
    getTokenCostHistory(7),
  ])
  const today = history[0]
  // A day with NO cost record is not a day that cost nothing. Every aggregate
  // below is computed over the MEASURED days only, and the count of days it
  // could not read is printed next to it — a 30-day total that silently
  // summed absences as zeros is a wrong number about money.
  const measured = history.filter(
    (d): d is typeof d & { total: number } => d.total !== null
  )
  const unmeasuredDays = history.length - measured.length
  const last7 = measured.slice(0, 7).reverse()
  const monthlyTotal =
    measured.length > 0 ? measured.reduce((sum, d) => sum + d.total, 0) : null

  // Token-based data
  const tokenToday = tokenHistory.length > 0 ? tokenHistory[0] : null
  const tokenMeasured = tokenHistory.filter(
    (d): d is typeof d & { totalCostMicro: number } => d.totalCostMicro !== null
  )
  const tokenLast7 = tokenMeasured.slice(0, 7).reverse()
  const token7dTotal =
    tokenMeasured.length > 0
      ? tokenMeasured.reduce((sum, d) => sum + d.totalCostMicro, 0)
      : null

  // Derive officer list from data (not hardcoded)
  const allOfficers = new Set<string>()
  for (const day of history) {
    for (const role of Object.keys(day.officers)) {
      if (day.officers[role] > 0) allOfficers.add(role)
    }
  }
  // Fallback if no cost data yet
  if (allOfficers.size === 0 && today) {
    Object.keys(today.officers).forEach(r => allOfficers.add(r))
  }
  const officerList = Array.from(allOfficers).sort()

  // Per-officer totals for today
  const officerTodayData =
    today && today.total !== null
      ? Object.entries(today.officers)
          .map(([role, value]) => ({ label: role.toUpperCase(), value, role }))
          .sort((a, b) => b.value - a.value)
      : []

  const sevenDayAverage =
    last7.length > 0
      ? Math.round(last7.reduce((s, d) => s + d.total, 0) / last7.length)
      : null

  // 7-day trend data
  const trendData = last7.map((d) => ({
    label: d.date.slice(5), // MM-DD
    value: d.total,
  }))

  // Stacked chart data
  const stackedData = last7.map((d) => ({
    label: d.date.slice(5),
    total: d.total,
    segments: Object.entries(d.officers)
      .map(([role, value]) => ({ role, value }))
      .sort((a, b) => b.value - a.value),
  }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
      <div>
        <h1 className="text-2xl font-bold text-white">Cost Analytics</h1>
        <p className="mt-1 text-sm text-zinc-500">
          API usage costs across all officers
        </p>
      </div>

      {/* Top stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900" style={{ padding: '24px' }}>
          <span className="text-sm text-zinc-500">Today</span>
          {/* This literal was `'$0.00'` — a hardcoded dollar figure standing in
              for "no reading". It is the only place in the app that asserted an
              amount with nothing behind it at all. */}
          <p className="mt-1 text-3xl font-bold text-white">
            {formatCentsOrDash(today?.total)}
          </p>
          {today && today.total === null && (
            <p className="mt-1 text-xs text-amber-300">
              {today.unmeasuredReason ?? 'no cost reading — this is not $0.00'}
            </p>
          )}
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900" style={{ padding: '24px' }}>
          <span className="text-sm text-zinc-500">7-Day Average</span>
          <p className="mt-1 text-3xl font-bold text-white">
            {formatCentsOrDash(sevenDayAverage)}
          </p>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900" style={{ padding: '24px' }}>
          <span className="text-sm text-zinc-500">Monthly Total (30d)</span>
          <p className="mt-1 text-3xl font-bold text-white">
            {formatCentsOrDash(monthlyTotal)}
          </p>
          {unmeasuredDays > 0 && (
            <p className="mt-1 text-xs text-amber-300">
              {unmeasuredDays} of {history.length} days have no cost reading and
              are not counted — absent, not zero.
            </p>
          )}
        </div>
      </div>

      {/* Token-based real costs (from stop hook) */}
      {tokenToday && tokenToday.totalCostMicro !== null && tokenToday.totalCostMicro > 0 && (
        <>
          <div>
            <h2 className="text-lg font-semibold text-white">Real Token Usage</h2>
            <p className="mt-1 text-xs text-zinc-500">
              Actual API token counts and costs from session transcripts
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-xl border border-emerald-800/50 bg-emerald-950/30" style={{ padding: '24px' }}>
              <span className="text-sm text-emerald-400/70">Today (tokens)</span>
              <p className="mt-1 text-3xl font-bold text-emerald-400">
                {formatMicro(tokenToday.totalCostMicro)}
              </p>
            </div>
            <div className="rounded-xl border border-emerald-800/50 bg-emerald-950/30" style={{ padding: '24px' }}>
              <span className="text-sm text-emerald-400/70">7-Day Average</span>
              <p className="mt-1 text-3xl font-bold text-emerald-400">
                {formatMicroOrDash(
                  tokenMeasured.length > 0
                    ? Math.round(
                        tokenMeasured.reduce((s, d) => s + d.totalCostMicro, 0) /
                          tokenMeasured.length
                      )
                    : null
                )}
              </p>
            </div>
            <div className="rounded-xl border border-emerald-800/50 bg-emerald-950/30" style={{ padding: '24px' }}>
              <span className="text-sm text-emerald-400/70">7-Day Total</span>
              <p className="mt-1 text-3xl font-bold text-emerald-400">
                {formatMicroOrDash(token7dTotal)}
              </p>
            </div>
          </div>

          {/* Token breakdown per officer */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-900" style={{ padding: '24px' }}>
            <h2 className="text-lg font-semibold text-white">Today&apos;s Token Breakdown</h2>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-zinc-800">
                    <th className="font-medium text-zinc-500" style={{ padding: '8px 12px' }}>Officer</th>
                    <th className="font-medium text-zinc-500" style={{ padding: '8px 12px' }}>Input</th>
                    <th className="font-medium text-zinc-500" style={{ padding: '8px 12px' }}>Output</th>
                    <th className="font-medium text-zinc-500" style={{ padding: '8px 12px' }}>Cache Write</th>
                    <th className="font-medium text-zinc-500" style={{ padding: '8px 12px' }}>Cache Read</th>
                    <th className="font-medium text-zinc-500" style={{ padding: '8px 12px' }}>Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(tokenToday.officers)
                    .filter(([, d]) => d.costMicro > 0)
                    .sort(([, a], [, b]) => b.costMicro - a.costMicro)
                    .map(([role, d]) => (
                      <tr key={role} className="border-b border-zinc-800/50">
                        <td className="font-medium text-white uppercase" style={{ padding: '10px 12px' }}>{role}</td>
                        <td className="text-zinc-400" style={{ padding: '10px 12px' }}>{formatTokens(d.input)}</td>
                        <td className="text-zinc-400" style={{ padding: '10px 12px' }}>{formatTokens(d.output)}</td>
                        <td className="text-zinc-400" style={{ padding: '10px 12px' }}>{formatTokens(d.cacheWrite)}</td>
                        <td className="text-zinc-400" style={{ padding: '10px 12px' }}>{formatTokens(d.cacheRead)}</td>
                        <td className="font-medium text-emerald-400" style={{ padding: '10px 12px' }}>{formatMicro(d.costMicro)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Estimated costs (byte-based, legacy) */}
      <div>
        <h2 className="text-lg font-semibold text-white">Estimated Costs</h2>
        <p className="mt-1 text-xs text-zinc-500">
          Rough per-tool-call estimates (legacy system)
        </p>
      </div>

      {/* Per-officer breakdown today */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900" style={{ padding: '24px' }}>
        <h2 className="text-lg font-semibold text-white">Today&apos;s Breakdown</h2>
        <div className="mt-4">
          <HorizontalBars data={officerTodayData} />
        </div>
      </div>

      {/* 7-day trend */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900" style={{ padding: '24px' }}>
        <h2 className="text-lg font-semibold text-white">7-Day Trend</h2>
        <div className="mt-4">
          <BarChart data={trendData} height={220} />
        </div>
      </div>

      {/* Stacked bar chart */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900" style={{ padding: '24px' }}>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">7-Day Per-Officer Breakdown</h2>
          <ChartLegend />
        </div>
        <div className="mt-4">
          <StackedBarChart data={stackedData} height={220} />
        </div>
      </div>

      {/* 30-day table */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900" style={{ padding: '24px' }}>
        <h2 className="text-lg font-semibold text-white">Last 30 Days</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-800">
                <th className="font-medium text-zinc-500" style={{ padding: '8px 12px' }}>Date</th>
                <th className="font-medium text-zinc-500" style={{ padding: '8px 12px' }}>Total</th>
                {officerList.map((role) => (
                  <th key={role} className="font-medium text-zinc-500 uppercase" style={{ padding: '8px 12px' }}>
                    {role}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.map((day) => (
                <tr key={day.date} className="border-b border-zinc-800/50">
                  <td className="text-zinc-300" style={{ padding: '10px 12px' }}>{day.date}</td>
                  <td
                    className={
                      day.total === null
                        ? 'font-medium text-amber-300'
                        : 'font-medium text-white'
                    }
                    style={{ padding: '10px 12px' }}
                    title={day.unmeasuredReason ?? undefined}
                  >
                    {formatCentsOrDash(day.total)}
                  </td>
                  {officerList.map((role) => (
                    <td key={role} className="text-zinc-400" style={{ padding: '10px 12px' }}>
                      {/* `day.officers[role] || 0` printed $0.00 for an officer
                          with no row on a day nobody recorded. When the day
                          itself is unmeasured every cell is the em-dash. */}
                      {day.total === null
                        ? '—'
                        : formatCentsOrDash(day.officers[role] ?? null)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
