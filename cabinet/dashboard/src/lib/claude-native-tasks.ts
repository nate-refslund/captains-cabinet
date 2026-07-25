/**
 * Server-side fetcher for the cabinet's claude_native_tasks projection table.
 *
 * Every CC native Task (TaskCreated / TaskCompleted hook → claude-task-bridge.py)
 * writes a row to claude_native_tasks with mission/node/owner/risk metadata.
 * This helper shells out to `org-runtime.py claude-tasks list --json` so the
 * dashboard reads the same canonical projection the CLI does.
 *
 * Returns an empty list (NOT throws) when the runtime is unreachable so the
 * dashboard never blank-screens — Captain still sees the WIP board.
 */

import { dockerExec } from '@/lib/docker'

export interface ClaudeNativeTask {
  task_id: string
  lane_slug: string
  status: string // 'created' | 'completed'
  mission_id: string | null
  node_id: string | null
  owner_role: string | null
  acceptance_criteria: string | null
  evidence_required: string | null
  verifier_role: string | null
  risk_level: string | null
  task_subject: string | null
  task_description: string | null
  teammate_name: string | null
  team_name: string | null
  session_id: string | null
  transcript_path: string | null
  cwd: string | null
  created_at: string
  updated_at: string
}

export interface ListOptions {
  productSlug?: string
  status?: 'created' | 'completed'
  limit?: number
}

export async function listClaudeNativeTasks(
  opts: ListOptions = {},
): Promise<ClaudeNativeTask[]> {
  const limit = opts.limit ?? 100
  const args: string[] = ['claude-tasks', 'list', '--limit', String(limit)]
  if (opts.productSlug) {
    args.push('--product-slug', opts.productSlug)
  }
  if (opts.status) {
    args.push('--status', opts.status)
  }
  // org-runtime.py defaults to --json output on `print_json`; the CLI already
  // emits JSON, no flag needed.
  const cmd = `python3 cabinet/scripts/org-runtime.py ${args.map((a) => `'${a.replace(/'/g, "'\\''")}'`).join(' ')}`

  try {
    const { stdout } = await dockerExec(cmd)
    if (!stdout || stdout === 'mock: command executed') {
      // Mock mode (Mac-native dashboard without REDIS_URL, or container offline)
      return []
    }
    const parsed = JSON.parse(stdout)
    if (Array.isArray(parsed)) return parsed as ClaudeNativeTask[]
    return []
  } catch (err) {
    console.warn('[claude-native-tasks] list failed:', err)
    return []
  }
}

/**
 * "Drift" = a CC native Task with no mission_id. The officer spawned a
 * subagent outside the mission graph. May be legit (ad-hoc work) or a sign
 * of officer wandering; surfaced as a counter on the dashboard.
 */
export function countDrift(tasks: ClaudeNativeTask[]): number {
  return tasks.filter((t) => !t.mission_id).length
}

/**
 * Group by owner_role (or "(unmapped)" if absent). Useful for the "by officer"
 * view — Captain can see which officer is spawning the most subagents.
 */
export function groupByOwner(
  tasks: ClaudeNativeTask[],
): Map<string, ClaudeNativeTask[]> {
  const groups = new Map<string, ClaudeNativeTask[]>()
  for (const t of tasks) {
    const key = t.owner_role || '(unmapped)'
    const arr = groups.get(key) ?? []
    arr.push(t)
    groups.set(key, arr)
  }
  return groups
}
