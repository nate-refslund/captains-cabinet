/**
 * /queue — the classic-skin war room (command-center §4B).
 *
 * Ranked Decisions shelf (the framework's deterministic lexicographic
 * order, amber gap-row borders) then Directions (the weekly shelf). Each
 * row expands to canonical refs + the copyable binder grammar
 * (`approve <pid>`) + the Telegram deep-link + the world
 * `?focus=wardroom` link.
 *
 * READ-ONLY BY LAW: no approve buttons — a dashboard verdict would be a
 * second door beside the authenticated Captain-DM receipt (gateway
 * §4.4 / F0.8). This page renders and deep-links; the binder decides.
 */
import Link from 'next/link'
import { readQueue, type QueueRow } from '@/lib/attention/queue'

export const dynamic = 'force-dynamic'

function fmtDeadline(iso: string | null): string {
  if (!iso) return '—'
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) return '—'
  const h = Math.round((t - Date.now()) / 3_600_000)
  if (h < 0) return `${iso.slice(0, 16)} (passed)`
  if (h < 48) return `${iso.slice(0, 16)} (~${h}h)`
  return iso.slice(0, 10)
}

function fmtAge(ageH: number | null): string {
  if (ageH === null) return '—'
  if (ageH < 48) return `${Math.round(ageH)}h`
  return `${Math.round(ageH / 24)}d`
}

function Row({
  row,
  shelf,
  telegram,
}: {
  row: QueueRow
  shelf: 'decisions' | 'directions'
  telegram: string | null
}) {
  const amber = shelf === 'decisions'
  return (
    <details
      className={`rounded-lg border bg-zinc-900 ${
        amber ? 'border-l-4 border-zinc-800 border-l-amber-600/70' : 'border-zinc-800'
      }`}
    >
      <summary
        className="flex cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 text-sm"
        style={{ padding: '10px 14px' }}
      >
        <span className="font-medium text-white">
          {row.what ?? '(untitled situation)'}
        </span>
        <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">
          {row.kind}
        </span>
        {row.lane ? (
          <span className="text-xs text-zinc-500">{row.lane}</span>
        ) : null}
        <span className="ml-auto flex items-center gap-3 text-xs text-zinc-500">
          {row.blast ? (
            <span
              className={
                row.blast.class === 'ceiling' ? 'text-red-400' : 'text-zinc-500'
              }
              title={row.blast_worst_case ?? undefined}
            >
              blast: {row.blast.class}/{row.blast.reach}
            </span>
          ) : null}
          <span>age {fmtAge(row.age_h)}</span>
          <span className={row.deadline_iso ? 'text-amber-300' : ''}>
            due {fmtDeadline(row.deadline_iso)}
          </span>
        </span>
      </summary>
      <div
        className="border-t border-zinc-800 text-xs text-zinc-400"
        style={{ padding: '10px 14px' }}
      >
        {row.why_now?.decay ? (
          <p className="mb-2 text-zinc-400">{row.why_now.decay}</p>
        ) : null}
        {row.refs.length > 0 ? (
          <div className="mb-2">
            <div className="mb-1 text-[10px] uppercase tracking-wide text-zinc-500">
              Proof — canonical refs
            </div>
            <ul className="space-y-0.5 font-mono text-[11px] text-zinc-400">
              {row.refs.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="mb-2">
          <div className="mb-1 text-[10px] uppercase tracking-wide text-zinc-500">
            Verdict — in the binder (HQ Chair), never here
          </div>
          {row.pid ? (
            <code className="block select-all rounded bg-zinc-950 px-2 py-1 font-mono text-[11px] text-emerald-300">
              approve {row.pid}
            </code>
          ) : (
            <p className="text-zinc-500">
              answer via the binder grammar on this card&apos;s standing message
            </p>
          )}
        </div>
        <div className="flex gap-4 text-[11px]">
          {telegram ? (
            <a
              href={telegram}
              target="_blank"
              rel="noreferrer"
              className="text-sky-400 hover:underline"
            >
              open Telegram binder ↗
            </a>
          ) : (
            <span className="text-zinc-500">binder: Telegram (HQ Chair) DM</span>
          )}
          <Link
            href="/world?focus=wardroom"
            className="text-sky-400 hover:underline"
          >
            view in world (wardroom)
          </Link>
        </div>
      </div>
    </details>
  )
}

export default async function QueuePage() {
  const queue = await readQueue()
  const telegram = process.env.HQ_CHAIR_BOT_USERNAME
    ? `https://t.me/${process.env.HQ_CHAIR_BOT_USERNAME}`
    : null
  const n = queue.pendingCaptainItems

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">
            ⚑ Needs you{n > 0 ? ` (${n})` : ''}
          </h1>
          <p className="mt-1 text-sm text-zinc-400">
            The one attention census — ranked decisions first, weekly
            directions after. Read-only: verdicts happen in the Telegram
            binder.
          </p>
        </div>
        <div className="text-right text-xs text-zinc-500">
          <div>
            source: {queue.source}
            {queue.generatedAt ? ` · ${queue.generatedAt}` : ''}
          </div>
          {queue.admissionEnforced ? (
            <div className="text-amber-400">admission law: enforced</div>
          ) : (
            <div>admission law: observing (C3 pending)</div>
          )}
        </div>
      </div>

      {n === 0 && queue.directions.length === 0 ? (
        <div
          className="rounded-lg border border-zinc-800 bg-zinc-900 text-center"
          style={{ padding: '48px' }}
        >
          <p className="text-zinc-300">Nothing needs you.</p>
          <p className="mx-auto mt-2 max-w-2xl text-xs text-zinc-500">
            The polished empty table is the designed reward state — the org is
            deciding what it can and holding only what genuinely needs the
            Captain.
          </p>
        </div>
      ) : (
        <>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-amber-300">
            Decisions{queue.cap ? ` — cap ${queue.cap}` : ''}
            {queue.overflow > 0 ? (
              <span className="ml-2 font-normal normal-case text-zinc-400">
                +{queue.overflow} over the cap → consolidation need filed
              </span>
            ) : null}
          </h2>
          {queue.decisions.length === 0 ? (
            <p className="mb-6 text-sm text-zinc-500">none — shelf clear.</p>
          ) : (
            <div className="mb-6 space-y-2">
              {queue.decisions.map((row) => (
                <Row key={row.id} row={row} shelf="decisions" telegram={telegram} />
              ))}
            </div>
          )}

          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-zinc-400">
            Directions — weekly shelf
          </h2>
          {queue.directions.length === 0 ? (
            <p className="text-sm text-zinc-500">none.</p>
          ) : (
            <div className="space-y-2">
              {queue.directions.map((row) => (
                <Row key={row.id} row={row} shelf="directions" telegram={telegram} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
