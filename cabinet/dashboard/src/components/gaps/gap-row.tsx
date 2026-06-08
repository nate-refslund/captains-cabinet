/**
 * Presentational components for the /gaps view — kind badge, status badge,
 * hit-count pill, and the per-gap row card.
 *
 * Server-compatible (no client hooks). Mirrors the badge + row-card
 * conventions of /tasks/subagents: `rounded border px-1.5 py-0.5 text-[10px]
 * font-medium uppercase` badges on a `rounded-md border bg-zinc-900/40` card.
 *
 * pending_captain rows get an amber left-border so the Captain's action items
 * visually pop.
 */

import type { CapabilityGap, GapKind, GapStatus } from '@/lib/capability-gaps'
import GapApproval from '@/components/gaps/gap-approval'

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

// kind → color: procedure=blue, tool=amber, integration=purple.
const KIND_STYLES: Record<GapKind, string> = {
  procedure: 'bg-blue-900/30 text-blue-400 border-blue-800',
  tool: 'bg-amber-900/30 text-amber-400 border-amber-800',
  integration: 'bg-purple-900/30 text-purple-400 border-purple-800',
}

function KindBadge({ kind }: { kind: string }) {
  const cls = KIND_STYLES[kind as GapKind] || 'bg-zinc-800 text-zinc-400 border-zinc-700'
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase ${cls}`}>
      {kind}
    </span>
  )
}

// status → color by urgency:
//   pending_captain = amber (highlighted — Captain action)
//   approved        = green
//   resolved        = green-dim
//   skilled         = blue (auto-resolved)
//   auto_skilling   = blue (in progress)
//   open/classified = zinc (still in pipeline)
//   declined        = zinc (closed, no action)
const STATUS_STYLES: Record<GapStatus, string> = {
  pending_captain: 'bg-amber-900/40 text-amber-300 border-amber-700',
  approved: 'bg-green-900/30 text-green-400 border-green-800',
  resolved: 'bg-green-900/15 text-green-500/80 border-green-900/50',
  skilled: 'bg-blue-900/30 text-blue-400 border-blue-800',
  auto_skilling: 'bg-blue-900/30 text-blue-400 border-blue-800',
  open: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  classified: 'bg-zinc-800 text-zinc-400 border-zinc-700',
  declined: 'bg-zinc-800 text-zinc-500 border-zinc-700',
}

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_STYLES[status as GapStatus] || 'bg-zinc-800 text-zinc-400 border-zinc-700'
  // Show the human-readable form (snake_case → spaced) on the badge.
  const label = status.replace(/_/g, ' ')
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase ${cls}`}>
      {label}
    </span>
  )
}

/**
 * Hit-count pill — "×N". Bigger / hotter color the more a gap recurs, since a
 * high hit_count is the priority signal. 1 = muted, 2-3 = amber, 4+ = red.
 */
function HitPill({ count }: { count: number }) {
  const n = count ?? 0
  const cls =
    n >= 4
      ? 'bg-red-900/30 text-red-400 border-red-800'
      : n >= 2
        ? 'bg-amber-900/30 text-amber-400 border-amber-800'
        : 'bg-zinc-800 text-zinc-400 border-zinc-700'
  const size = n >= 4 ? 'text-xs px-2 py-0.5' : 'text-[11px] px-1.5 py-0.5'
  return (
    <span
      className={`rounded border font-semibold tabular-nums ${size} ${cls}`}
      title={`Recurred ${n} time${n === 1 ? '' : 's'}`}
    >
      ×{n}
    </span>
  )
}

export function GapRow({ gap }: { gap: CapabilityGap }) {
  const needsCaptain = gap.status === 'pending_captain'
  return (
    <div
      className={`rounded-md border bg-zinc-900/40 ${
        needsCaptain ? 'border-l-2 border-l-amber-500 border-amber-900/50' : 'border-zinc-800'
      }`}
      style={{ padding: '12px' }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {/* Badge row */}
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <KindBadge kind={gap.kind} />
            <StatusBadge status={gap.status} />
            <HitPill count={gap.hit_count} />
            <span className="text-[11px] text-zinc-500">{relTime(gap.last_seen)}</span>
          </div>

          {/* The need — prominent */}
          <p className="text-sm font-medium text-white" title={gap.need}>
            {gap.need || <span className="italic text-zinc-500">(unnamed gap)</span>}
          </p>

          {/* Evidence — smaller */}
          {gap.evidence && (
            <p className="mt-1 text-xs text-zinc-400 line-clamp-2" title={gap.evidence}>
              {gap.evidence}
            </p>
          )}

          {/* Meta row */}
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-zinc-500">
            <code className="text-zinc-600">{gap.gap_id}</code>
            <span>
              recorded by: <span className="text-zinc-300">{gap.recorded_by || '—'}</span>
            </span>
            {gap.touches && gap.touches.length > 0 && (
              <span className="text-amber-500/80">
                touches: {gap.touches.join(', ')}
              </span>
            )}
            {gap.resolution && (
              <span>
                resolution: <span className="text-zinc-300">{gap.resolution}</span>
              </span>
            )}
          </div>

          {/* Pending proposal → show the proposed approach + Approve/Decline */}
          {needsCaptain && (
            <div className="mt-3 rounded border border-amber-900/40 bg-amber-950/20" style={{ padding: '10px' }}>
              {gap.proposal?.approach && (
                <p className="text-xs text-zinc-300">
                  <span className="font-medium text-amber-300">Proposed: </span>
                  {gap.proposal.approach}
                </p>
              )}
              <GapApproval gapId={gap.gap_id} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
