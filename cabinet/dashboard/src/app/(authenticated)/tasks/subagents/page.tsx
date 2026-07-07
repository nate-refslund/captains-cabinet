/**
 * /tasks/subagents — CC native Task ledger (claude_native_tasks projection).
 *
 * Every Agent() / Task tool call across all officer sessions is auto-mirrored
 * into claude_native_tasks by cabinet/scripts/claude-task-bridge.py via the
 * TaskCreated / TaskCompleted hooks in .claude/settings.json. This page
 * surfaces them so the Captain can:
 *
 *   1. See which officers are spawning subagents + how often
 *   2. Detect drift (subagents spawned outside the mission graph — no mission_id)
 *   3. Decide whether to invest more in the Agent Teams workflow
 *
 * Server component — fetched at render time. Light-weight (limit 100 rows).
 */

import Link from 'next/link'
import path from 'node:path'
import { readFile } from 'node:fs/promises'
import { cabinetRoot } from '@/lib/cabinet-root'
import {
  listClaudeNativeTasks,
  countDrift,
  groupByOwner,
  type ClaudeNativeTask,
} from '@/lib/claude-native-tasks'

export const dynamic = 'force-dynamic'

async function resolveActiveContext(): Promise<string | null> {
  if (process.env.CABINET_CONTEXT?.trim()) return process.env.CABINET_CONTEXT.trim()
  const activeFile = path.join(cabinetRoot(), 'instance/config/active-project.txt')
  try {
    const txt = await readFile(activeFile, 'utf-8')
    const slug = txt.trim()
    return slug || null
  } catch {
    return null
  }
}

function relTime(iso: string): string {
  try {
    const ms = Date.now() - new Date(iso).getTime()
    const min = Math.floor(ms / 60000)
    if (min < 1) return 'just now'
    if (min < 60) return `${min}m ago`
    const hr = Math.floor(min / 60)
    if (hr < 24) return `${hr}h ago`
    const day = Math.floor(hr / 24)
    return `${day}d ago`
  } catch {
    return iso
  }
}

function StatusBadge({ status }: { status: string }) {
  const styles =
    status === 'completed'
      ? 'bg-green-900/30 text-green-400 border-green-800'
      : 'bg-blue-900/30 text-blue-400 border-blue-800'
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase ${styles}`}>
      {status}
    </span>
  )
}

function RiskBadge({ level }: { level: string | null }) {
  if (!level) return null
  const styles: Record<string, string> = {
    high: 'bg-red-900/30 text-red-400 border-red-800',
    medium: 'bg-amber-900/30 text-amber-400 border-amber-800',
    low: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  }
  const cls = styles[level.toLowerCase()] || styles.low
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase ${cls}`}>
      risk: {level}
    </span>
  )
}

function TaskRow({ task }: { task: ClaudeNativeTask }) {
  const drift = !task.mission_id
  return (
    <div
      className={`rounded-md border bg-zinc-900/40 ${drift ? 'border-amber-900/50' : 'border-zinc-800'}`}
      style={{ padding: '12px' }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
            <code className="font-mono text-xs text-zinc-300">{task.task_id.slice(0, 12)}…</code>
            <StatusBadge status={task.status} />
            <RiskBadge level={task.risk_level} />
            {drift && (
              <span className="rounded border border-amber-800 bg-amber-900/30 px-1.5 py-0.5 text-[10px] font-medium uppercase text-amber-400">
                drift (no mission)
              </span>
            )}
            <span className="text-[11px] text-zinc-500">{relTime(task.updated_at || task.created_at)}</span>
          </div>
          <p className="text-sm text-white truncate" title={task.task_subject || ''}>
            {task.task_subject || <span className="text-zinc-500 italic">(no subject)</span>}
          </p>
          {task.task_description && (
            <p className="mt-1 text-xs text-zinc-400 line-clamp-2" title={task.task_description}>
              {task.task_description}
            </p>
          )}
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-zinc-500">
            <span>
              owner: <span className="text-zinc-300">{task.owner_role || '(unmapped)'}</span>
            </span>
            {task.verifier_role && (
              <span>
                verifier: <span className="text-zinc-300">{task.verifier_role}</span>
              </span>
            )}
            {task.teammate_name && (
              <span>
                agent: <span className="text-zinc-300">{task.teammate_name}</span>
              </span>
            )}
            {task.mission_id && (
              <span>
                mission: <code className="text-zinc-300">{task.mission_id}</code>
              </span>
            )}
            {task.node_id && (
              <span>
                node: <code className="text-zinc-300">{task.node_id}</code>
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default async function SubagentsPage() {
  const productSlug = (await resolveActiveContext()) || undefined
  const tasks = await listClaudeNativeTasks({ productSlug, limit: 100 })

  const driftCount = countDrift(tasks)
  const byOwner = groupByOwner(tasks)
  const completedCount = tasks.filter((t) => t.status === 'completed').length
  const inFlightCount = tasks.filter((t) => t.status !== 'completed').length

  return (
    <div className="mx-auto max-w-6xl" style={{ padding: '24px' }}>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Subagent Activity</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Every <code className="text-zinc-300">Agent()</code> /{' '}
            <code className="text-zinc-300">Task</code> tool call across officer sessions is
            mirrored here via the <code className="text-zinc-300">TaskCreated</code> /
            <code className="text-zinc-300"> TaskCompleted</code> hooks. Use this view to track
            whether the cabinet is leveraging Agent Teams effectively, and to spot drift —
            subagents spawned outside the mission graph.
          </p>
        </div>
        <Link
          href="/tasks"
          className="rounded border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
        >
          ← back to officer board
        </Link>
      </div>

      {/* Stats strip */}
      <div className="mb-6 grid grid-cols-4 gap-3">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900" style={{ padding: '12px' }}>
          <div className="text-[11px] uppercase text-zinc-500">Total (last 100)</div>
          <div className="mt-1 text-2xl font-semibold text-white">{tasks.length}</div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900" style={{ padding: '12px' }}>
          <div className="text-[11px] uppercase text-zinc-500">In flight</div>
          <div className="mt-1 text-2xl font-semibold text-blue-400">{inFlightCount}</div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900" style={{ padding: '12px' }}>
          <div className="text-[11px] uppercase text-zinc-500">Completed</div>
          <div className="mt-1 text-2xl font-semibold text-green-400">{completedCount}</div>
        </div>
        <div
          className={`rounded-lg border bg-zinc-900 ${driftCount > 0 ? 'border-amber-900/50' : 'border-zinc-800'}`}
          style={{ padding: '12px' }}
        >
          <div className="text-[11px] uppercase text-zinc-500">Drift (no mission)</div>
          <div className={`mt-1 text-2xl font-semibold ${driftCount > 0 ? 'text-amber-400' : 'text-zinc-500'}`}>
            {driftCount}
          </div>
        </div>
      </div>

      {/* By-officer summary */}
      {byOwner.size > 0 && (
        <div className="mb-6 rounded-lg border border-zinc-800 bg-zinc-900" style={{ padding: '16px' }}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-400">
            By officer
          </h2>
          <div className="flex flex-wrap gap-2">
            {Array.from(byOwner.entries())
              .sort((a, b) => b[1].length - a[1].length)
              .map(([owner, group]) => (
                <span
                  key={owner}
                  className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300"
                >
                  {owner}: <span className="text-white">{group.length}</span>
                </span>
              ))}
          </div>
        </div>
      )}

      {/* List */}
      {tasks.length === 0 ? (
        <div
          className="rounded-lg border border-zinc-800 bg-zinc-900 text-center"
          style={{ padding: '48px' }}
        >
          <p className="text-zinc-400">
            No subagent activity yet. Officers spawn subagents via{' '}
            <code className="text-zinc-300">Agent()</code> / Task tool — every spawn appears here.
          </p>
          <p className="mt-2 text-xs text-zinc-500">
            If you expect activity but see none, verify{' '}
            <code className="text-zinc-300">.claude/settings.json</code> has{' '}
            <code className="text-zinc-300">TaskCreated</code> /{' '}
            <code className="text-zinc-300">TaskCompleted</code> hooks wired to{' '}
            <code className="text-zinc-300">cabinet/scripts/claude-task-bridge.py</code>.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {tasks.map((t) => (
            <TaskRow key={t.task_id} task={t} />
          ))}
        </div>
      )}
    </div>
  )
}
