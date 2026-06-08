/**
 * /gaps — Capability Gaps tracking view.
 *
 * The live AI org records a "capability gap" whenever an officer hits a wall it
 * can't cross with current tools / procedures / integrations (or the cabinet
 * infers one from repeated failed attempts). The org-runtime classifies each
 * gap, auto-resolves the ones it can as skills, and escalates the rest to the
 * Captain for approval (code or credentials needed).
 *
 * This page surfaces the ledger so the Captain can track unmet capabilities and
 * approve fixes — pending_captain gaps are pulled to the top and visually
 * highlighted as their action items.
 *
 * Server component — data fetched at render via listCapabilityGaps(), which
 * shells out to `org-runtime.py gaps list --json` and degrades to [] on any
 * error. A tiny client island (AutoRefresh) re-renders every 30s so the board
 * stays live without a full reload.
 */

import Link from 'next/link'
import {
  listCapabilityGaps,
  sortGaps,
  countGaps,
} from '@/lib/capability-gaps'
import { GapRow } from '@/components/gaps/gap-row'
import AutoRefresh from '@/components/display/auto-refresh'

export const dynamic = 'force-dynamic'

export default async function GapsPage() {
  const gaps = await listCapabilityGaps()
  const sorted = sortGaps(gaps)
  const counts = countGaps(gaps)

  return (
    <div className="mx-auto max-w-6xl" style={{ padding: '24px' }}>
      {/* Re-render every 30s so the ledger stays live on the wall display. */}
      <AutoRefresh intervalMs={30000} />

      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Capability Gaps</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Unmet capabilities the cabinet hit — auto-resolved as skills, or
            proposed to you for approval.
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
          <div className="text-[11px] uppercase text-zinc-500">Open</div>
          <div className="mt-1 text-2xl font-semibold text-white">{counts.open}</div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900" style={{ padding: '12px' }}>
          <div className="text-[11px] uppercase text-zinc-500">Auto-resolved</div>
          <div className="mt-1 text-2xl font-semibold text-blue-400">{counts.skilled}</div>
        </div>
        <div
          className={`rounded-lg border bg-zinc-900 ${
            counts.pendingCaptain > 0 ? 'border-amber-900/50' : 'border-zinc-800'
          }`}
          style={{ padding: '12px' }}
        >
          <div className="text-[11px] uppercase text-zinc-500">Awaiting your approval</div>
          <div
            className={`mt-1 text-2xl font-semibold ${
              counts.pendingCaptain > 0 ? 'text-amber-400' : 'text-zinc-500'
            }`}
          >
            {counts.pendingCaptain}
          </div>
        </div>
        <div className="rounded-lg border border-zinc-800 bg-zinc-900" style={{ padding: '12px' }}>
          <div className="text-[11px] uppercase text-zinc-500">Resolved</div>
          <div className="mt-1 text-2xl font-semibold text-green-400">{counts.resolved}</div>
        </div>
      </div>

      {/* List */}
      {sorted.length === 0 ? (
        <div
          className="rounded-lg border border-zinc-800 bg-zinc-900 text-center"
          style={{ padding: '48px' }}
        >
          <p className="text-zinc-400">No capability gaps yet.</p>
          <p className="mx-auto mt-2 max-w-2xl text-xs text-zinc-500">
            They appear here when officers hit a wall they can&apos;t solve with
            current tools — auto-resolved as skills where possible, proposed to
            you where they need code or credentials.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {sorted.map((g) => (
            <GapRow key={g.gap_id} gap={g} />
          ))}
        </div>
      )}
    </div>
  )
}
