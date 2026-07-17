/**
 * EvidenceRow — one evidence trial, rendered READ-ONLY.
 *
 * Mirrors the receipt-row doctrine: this surface renders truth and nothing
 * else — it NEVER grows label/purge/export buttons, mutation endpoints, or
 * client JS (labeling is the Captain-token-gated CLI harness, not a web
 * verb). Pure server components: props in, markup out.
 *
 * Badge law: unknown values render an EXPLICIT badge, never coerced into a
 * state the store didn't record. UNVERIFIED trials wear a loud red badge
 * plus the verifier's reason and carry zero content — fail-closed display.
 */
import type {
  EvidenceBasis,
  UnverifiedTrialRow,
  VerifiedTrialRow,
} from '@/lib/evidence/read'

const BASIS_BADGE: Record<EvidenceBasis, string> = {
  'human-verified': 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300',
  'independently-recomputed': 'border-sky-500/30 bg-sky-500/15 text-sky-300',
  'self-asserted': 'border-amber-500/30 bg-amber-500/15 text-amber-300',
  'persistence-only': 'border-zinc-600/40 bg-zinc-700/20 text-zinc-400',
  unknown: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
}

const BASIS_TITLE: Record<EvidenceBasis, string> = {
  'human-verified':
    'a captain-attributed judgment event (or recorded human verdict) exists on this trial',
  'independently-recomputed':
    'a verdict independent of the producer (verdict_judge) exists on this trial',
  'self-asserted':
    'the producer/system vouches for its own work — no independent verification',
  'persistence-only':
    'bytes are intact, but nothing beyond persistence was ever confirmed',
  unknown: 'trial verified, but its content was not captured in this read',
}

export function VerifiedEvidenceRow({ row }: { row: VerifiedTrialRow }) {
  const basisBadge = BASIS_BADGE[row.basis] ?? BASIS_BADGE.unknown
  const basisTitle = BASIS_TITLE[row.basis] ?? BASIS_TITLE.unknown

  return (
    <li className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-emerald-300">
          VERIFIED
        </span>
        <span
          className={`rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold ${basisBadge}`}
          title={`${basisTitle} — ${row.basisReason}`}
        >
          {row.basis}
        </span>
        <span className="break-all font-mono text-sm text-zinc-100">{row.trialId}</span>
      </div>

      {row.contentUnavailable ? (
        <p className="mt-2 text-xs text-amber-300">
          integrity verified ({row.eventCount} event{row.eventCount === 1 ? '' : 's'} on
          disk), but this read could not capture its content — shown, never guessed at.
        </p>
      ) : (
        <>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-zinc-500">
            <span>
              {row.eventCount} event{row.eventCount === 1 ? '' : 's'}
            </span>
            <span>
              {row.firstTs}
              {row.lastTs !== row.firstTs ? ` → ${row.lastTs}` : ''}
            </span>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-zinc-500">
            {row.actors.length > 0 && <span>actors {row.actors.join(', ')}</span>}
            {row.components.length > 0 && (
              <span>components {row.components.join(', ')}</span>
            )}
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-zinc-600">
            {row.phases.length > 0 && <span>phases {row.phases.join(' · ')}</span>}
            {row.statuses.length > 0 && <span>statuses {row.statuses.join(' · ')}</span>}
          </div>
        </>
      )}
    </li>
  )
}

export function UnverifiedEvidenceRow({ row }: { row: UnverifiedTrialRow }) {
  return (
    <li className="rounded-lg border border-red-500/30 bg-red-500/5 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-red-500/40 bg-red-500/15 px-2 py-0.5 font-mono text-[10px] font-semibold text-red-300">
          UNVERIFIED
        </span>
        <span className="break-all font-mono text-sm text-zinc-300">{row.trialId}</span>
      </div>
      <p className="mt-2 text-xs text-red-300">
        reason: <span className="font-mono">{row.reason}</span>
      </p>
      <p className="mt-1 text-xs text-zinc-500">
        content withheld — this trial did not pass the verifier
        {row.reportedEventCount !== null
          ? ` (${row.reportedEventCount} event${row.reportedEventCount === 1 ? '' : 's'} reported unverifiable)`
          : ''}
        ; nothing from it is rendered.
      </p>
    </li>
  )
}
