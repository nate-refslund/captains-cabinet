/**
 * /queue — everything waiting on you, in plain words (captain-surface v2).
 *
 * PLAIN-LANGUAGE LAW (Ruling B): big-type one-sentence cards, plain buttons,
 * technical truth behind each card's Details ▸ disclosure. WRITE-CLASS-2
 * (Ruling A): the buttons POST to the equal-authority verdict door — two-tap
 * confirm, verified server-side, executed through the org's own gate.
 *
 * Deck laws kept: big-count masthead; "Nothing needs you." dark face; no
 * auto-refresh over interactive cards; nothing pulses; reload is honest.
 */
import { cookies } from 'next/headers'
import { readQueue, type QueueRow } from '@/lib/attention/queue'
import { COPY, plainCard } from '@/lib/attention/plain'
import { COOKIE_NAME, csrfTokenFor, verifySessionValue } from '@/lib/attention/verdict'
import QueueDecisionCard from '@/components/queue-decision-card'

export const dynamic = 'force-dynamic'

function fmtUpdated(iso: string | null): string {
  if (!iso) return ''
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) return ''
  return `${COPY.updated_prefix} ${new Date(t).toISOString().slice(11, 16)}`
}

function Card({
  row,
  accent,
  csrf,
  telegram,
}: {
  row: QueueRow
  accent: boolean
  csrf: string | null
  telegram: string | null
}) {
  const plain = plainCard(row)
  return (
    <QueueDecisionCard
      anchorId={row.pid ?? row.id}
      headline={plain.headline}
      sentence={plain.sentence}
      stateName={plain.stateName}
      kindName={plain.kindName}
      buttons={plain.buttons}
      ritual={plain.ritual}
      decided={plain.decided}
      decidable={plain.decidable}
      pid={row.pid}
      revision={plain.revision}
      csrf={csrf}
      telegramHref={telegram}
      accent={accent}
      copy={{
        confirmYes: COPY.confirm_yes,
        confirmBack: COPY.confirm_back,
        laterBriefing: COPY.later_briefing,
        detailsLabel: COPY.details_label,
        detailsSources: COPY.details_sources,
        detailsTyping: COPY.details_typing,
        openTelegram: COPY.open_telegram,
        noButtons: COPY.no_buttons,
        working: COPY.working,
      }}
      details={{
        kind: row.kind,
        state: row.state,
        urgency: row.urgency,
        blastClass: row.blast?.class ?? null,
        blastReach: row.blast?.reach ?? null,
        blastWorstCase: row.blast_worst_case,
        decayRaw: row.why_now?.decay ?? null,
        refs: row.refs,
        pid: row.pid,
        revision: plain.revision,
        filedBy: row.filed_by,
      }}
    />
  )
}

export default async function QueuePage() {
  const queue = await readQueue()
  const cookieStore = await cookies()
  const session = cookieStore.get(COOKIE_NAME)?.value
  const csrf = session && verifySessionValue(session) ? csrfTokenFor(session) : null
  const telegram = process.env.HQ_CHAIR_BOT_USERNAME
    ? `https://t.me/${process.env.HQ_CHAIR_BOT_USERNAME}`
    : null
  const n = queue.pendingCaptainItems
  const dark = n === 0 && queue.directions.length === 0

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-8">
        {dark ? (
          <div className="rounded-lg border border-zinc-800 bg-zinc-900 text-center" style={{ padding: '56px 24px' }}>
            <p className="text-2xl italic text-zinc-100">{COPY.masthead_dark}</p>
            <p className="mt-3 text-sm text-emerald-400">{COPY.masthead_dark_sub}</p>
          </div>
        ) : (
          <div className="flex items-end justify-between">
            <div>
              <div
                className="font-semibold leading-none text-white"
                style={{ fontSize: 'clamp(56px, 12vw, 104px)', letterSpacing: '-0.04em', fontVariantNumeric: 'tabular-nums' }}
              >
                {n}
              </div>
              <div className="mt-1 text-lg text-zinc-400">
                {n === 1 ? COPY.masthead_need_one : COPY.masthead_need_many}
              </div>
            </div>
            <div className="text-right text-xs text-zinc-500">{fmtUpdated(queue.generatedAt)}</div>
          </div>
        )}
      </div>

      {!dark ? (
        <>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-amber-300">
            {COPY.decisions_header}
            {queue.overflow > 0 ? (
              <span className="ml-2 font-normal normal-case text-zinc-400">
                +{queue.overflow} {COPY.overflow_note}
              </span>
            ) : null}
          </h2>
          {queue.decisions.length === 0 ? (
            <p className="mb-8 text-sm text-zinc-500">{COPY.decisions_empty}</p>
          ) : (
            <div className="mb-8 space-y-3">
              {queue.decisions.map((row) => (
                <Card key={row.id} row={row} accent csrf={csrf} telegram={telegram} />
              ))}
            </div>
          )}

          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-zinc-400">
            {COPY.directions_header}
          </h2>
          {queue.directions.length === 0 ? (
            <p className="text-sm text-zinc-500">{COPY.directions_empty}</p>
          ) : (
            <div className="space-y-3">
              {queue.directions.map((row) => (
                <Card key={row.id} row={row} accent={false} csrf={csrf} telegram={telegram} />
              ))}
            </div>
          )}

          <p className="mt-10 text-xs text-zinc-600">
            {COPY.footer_hint}
            {telegram ? (
              <>
                {' '}
                <a href={telegram} target="_blank" rel="noreferrer" className="text-sky-500 hover:underline">
                  {COPY.open_telegram}
                </a>
              </>
            ) : null}
          </p>
        </>
      ) : null}
    </div>
  )
}
