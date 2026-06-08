/**
 * Server-side fetcher for the cabinet's capability-gaps ledger.
 *
 * The live AI org records a "capability gap" every time an officer hits a wall
 * it can't solve with current tools/procedures/integrations (or the cabinet
 * infers one from repeated failed attempts). The org-runtime then classifies
 * each gap, auto-skills the ones it can, and escalates the rest to the Captain
 * for approval (code / credentials needed).
 *
 * This helper shells out to `org-runtime.py gaps list --json` so the dashboard
 * reads the same canonical ledger the CLI does — mirroring the pattern in
 * claude-native-tasks.ts.
 *
 * Returns an empty list (NEVER throws) when the runtime is unreachable, the
 * `gaps` subcommand isn't shipped yet, or we're in mock mode — so the page
 * always renders (it shows an explanatory empty state instead of blank-screening).
 */

import { dockerExec } from '@/lib/docker'

export type GapKind = 'procedure' | 'tool' | 'integration'

export type GapStatus =
  | 'open'
  | 'classified'
  | 'auto_skilling'
  | 'skilled'
  | 'pending_captain'
  | 'approved'
  | 'declined'
  | 'resolved'

export interface CapabilityGap {
  gap_id: string
  need: string
  kind: GapKind
  status: GapStatus
  hit_count: number
  evidence: string
  first_seen: string
  last_seen: string
  recorded_by: string
  resolution: string | null
  touches?: string[]
  proposal?: { summary?: string; approach?: string }
}

/**
 * Fetch the capability-gaps ledger from the org-runtime CLI.
 *
 * Degrades gracefully: any error, mock output, or non-array payload → [].
 */
export async function listCapabilityGaps(): Promise<CapabilityGap[]> {
  const cmd = 'python3 cabinet/scripts/org-runtime.py gaps list --json'

  try {
    const { stdout } = await dockerExec(cmd)
    if (!stdout || stdout === 'mock: command executed') {
      // Mock mode (Mac-native dashboard without REDIS_URL, container offline,
      // or the `gaps` subcommand not shipped yet).
      return []
    }
    const parsed = JSON.parse(stdout)
    if (!Array.isArray(parsed)) return []
    return parsed as CapabilityGap[]
  } catch (err) {
    console.warn('[capability-gaps] list failed:', err)
    return []
  }
}

// ---------------------------------------------------------------------------
// Sorting + bucketing helpers (pure — unit-testable, no I/O).
// ---------------------------------------------------------------------------

/**
 * Status priority for sorting. Lower = more urgent / higher in the list.
 * pending_captain first — those are the Captain's action items. Then the
 * actively-moving states, then the terminal/resolved ones.
 */
const STATUS_PRIORITY: Record<GapStatus, number> = {
  pending_captain: 0,
  open: 1,
  classified: 2,
  auto_skilling: 3,
  approved: 4,
  skilled: 5,
  resolved: 6,
  declined: 7,
}

export function statusPriority(status: string): number {
  return STATUS_PRIORITY[status as GapStatus] ?? 99
}

/**
 * Sort by status priority (pending_captain first), then by hit_count desc
 * (more recurrences = more urgent within the same status). Stable on ties.
 * Returns a new array; does not mutate the input.
 */
export function sortGaps(gaps: CapabilityGap[]): CapabilityGap[] {
  return [...gaps].sort((a, b) => {
    const ps = statusPriority(a.status) - statusPriority(b.status)
    if (ps !== 0) return ps
    return (b.hit_count ?? 0) - (a.hit_count ?? 0)
  })
}

export interface GapCounts {
  open: number
  skilled: number
  pendingCaptain: number
  resolved: number
}

/**
 * The four stat-strip counters.
 * - open: gaps still being worked through the pipeline (not skilled / resolved /
 *   pending the Captain / declined). Captures open + classified + auto_skilling.
 * - skilled: auto-resolved by the cabinet as a skill.
 * - pendingCaptain: awaiting the Captain's approval (needs code/credentials).
 * - resolved: fully closed out.
 */
export function countGaps(gaps: CapabilityGap[]): GapCounts {
  const counts: GapCounts = { open: 0, skilled: 0, pendingCaptain: 0, resolved: 0 }
  for (const g of gaps) {
    switch (g.status) {
      case 'skilled':
        counts.skilled++
        break
      case 'pending_captain':
        counts.pendingCaptain++
        break
      case 'resolved':
        counts.resolved++
        break
      case 'open':
      case 'classified':
      case 'auto_skilling':
        counts.open++
        break
      // approved / declined are terminal-ish and not surfaced as a top counter.
      default:
        break
    }
  }
  return counts
}
