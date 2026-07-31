/**
 * /tasks — per-officer work front view (Spec 038 Phase A v1.2).
 *
 * Layout: Captain column (leftmost) + officer columns (alphabetical slug order).
 * Each column: WIP (0-3, blocked as chain-icon overlay), Queue, Done (last 3).
 *
 * Server component — data fetched at render time.
 * Live refresh via SSE handled by TasksClientRefresh (client component).
 */

import { resolveActiveContext } from '@/lib/active-context'
import { getAllOfficerBoards, getBoardStats, WIP_CAP } from '@/lib/tasks'
import { getLinearFounderActions } from '@/lib/linear-tasks'
import redis from '@/lib/redis'
import { freshnessOf } from '@/lib/liveness'
import { OfficerColumn } from '@/components/tasks/officer-column'
import { CaptainColumn } from '@/components/tasks/captain-column'
import TasksClientRefresh from '@/components/tasks/tasks-client-refresh'
import OfficerColumnsGated from '@/components/tasks/officer-columns-gated'
import { BoardStatStrip } from '@/components/tasks/board-stat-strip'

export const dynamic = 'force-dynamic'

// Context resolution: the shared preset-aware chain in @/lib/active-context
// (same precedence as my-tasks.sh / framework.env.active_context: env >
// active-project.txt > single-declared-lane > lane_default). Throws on miss —
// /tasks without a context can't render a per-(context,officer) WIP board.

const OFFLINE_THRESHOLD_MS = 15 * 60 * 1000

/**
 * officer_slug → is_online (heartbeat < 15min).
 *
 * `now - hbTime < OFFLINE_THRESHOLD_MS` was TRUE for every future-dated stamp
 * (a negative age is under every threshold there is), so a clock-skewed writer
 * painted a dead officer online here permanently. `freshnessOf` is the one
 * reader with that arm; only a genuinely fresh reading counts as online.
 */
async function getOfficerOnlineStatus(): Promise<Record<string, boolean>> {
  const now = Date.now()
  const result: Record<string, boolean> = {}

  try {
    const heartbeatKeys = await redis.keys('cabinet:heartbeat:*')
    await Promise.all(
      heartbeatKeys.map(async (key) => {
        const slug = key.replace('cabinet:heartbeat:', '')
        const val = await redis.get(key)
        result[slug] = freshnessOf(val, now, OFFLINE_THRESHOLD_MS).state === 'fresh'
      })
    )
  } catch {
    // An unreachable store yields NO entries — never entries set to `false`,
    // which the strip would draw as "measured offline". An absent slug renders
    // no online marker at all, and the page banner says why. Uncaught, this
    // would 500 the whole tasks page (no error boundaries exist in this app).
    return {}
  }
  return result
}

export default async function TasksPage() {
  const contextSlug = await resolveActiveContext()
  const [boards, captainTasks, onlineStatus, stats] = await Promise.all([
    getAllOfficerBoards(contextSlug),
    getLinearFounderActions(),
    getOfficerOnlineStatus(),
    getBoardStats(contextSlug),
  ])

  const officerSlugs = Object.keys(boards).sort()

  // WIP integrity check (Spec 038 v1.2 §4.4 — defense-in-depth).
  // v1.2: getOfficerBoard() no longer slices at WIP_CAP, so this banner
  // actually surfaces DB-state violations (advisory lock + trigger should
  // prevent them; if one fires, Sonnet's BLOCKER-3 concern would be real).
  const integrityViolations: string[] = []
  for (const slug of officerSlugs) {
    if (boards[slug].wip.length > WIP_CAP) {
      integrityViolations.push(`${slug} (${boards[slug].wip.length} WIP)`)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Tasks</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Per-officer work front — WIP={WIP_CAP} cap, DB-enforced trigger
          </p>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="/tasks/subagents"
            className="rounded border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800 hover:text-white"
            title="Every Agent() / Task tool call from officer sessions"
          >
            Subagent activity →
          </a>
          <TasksClientRefresh />
        </div>
      </div>

      {/* All-officers rollup strip (Spec 038 v1.2 AC #19) — captainCount
          surfaces founder-action blockers per 038.8. Open = wip + queue
          + blocked; done rows are not "blocking" the Captain anymore. */}
      <BoardStatStrip
        stats={stats}
        captainCount={
          captainTasks.configured
            ? captainTasks.wip.length +
              captainTasks.queue.length +
              captainTasks.blocked.length
            : undefined
        }
      />

      {/* Integrity violation banner (defense-in-depth) */}
      {integrityViolations.length > 0 && (
        <div className="rounded-xl border border-red-500/50 bg-red-900/20 px-5 py-4">
          <p className="text-sm font-semibold text-red-400">
            Data integrity: {integrityViolations.join(', ')} exceed WIP cap of {WIP_CAP}. Fix manually.
          </p>
        </div>
      )}

      {/* Horizontal-scroll column grid */}
      <div className="w-full overflow-x-auto">
        <div
          className="flex gap-4"
          style={{ minWidth: `${(officerSlugs.length + 1) * 296}px` }}
        >
          {/* Captain column — always leftmost, visible in both modes */}
          <CaptainColumn tasks={captainTasks} />

          {/* Officer columns — Advanced mode only (AC #17). Gated on the
              client because dashboard mode lives in localStorage. */}
          <OfficerColumnsGated>
            {officerSlugs.map((slug) => (
              <OfficerColumn
                key={slug}
                officerSlug={slug}
                board={boards[slug]}
                isOnline={onlineStatus[slug] ?? false}
              />
            ))}
          </OfficerColumnsGated>
        </div>
      </div>

    </div>
  )
}
