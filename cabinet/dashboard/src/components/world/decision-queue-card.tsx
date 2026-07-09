'use client'

/**
 * DecisionQueueCard — the mailbox's READ-only pending view (T3).
 *
 * Captain ruling 2026-07-09: mailbox click → dashboard decision-queue view,
 * READ-only render + deep-link out to the real queue — NO actuation
 * in-world (the killswitch lever is the ONE actuator; this component never
 * mutates anything — the ui-layer vitest statically asserts this file
 * contains only GET fetches and no server-action imports).
 *
 * Data: GET /api/world/mailbox → pending cabinet:action:* cards (the
 * binder-wire proposal chains awaiting the Captain's verdict). Verdicts are
 * given in the Captain's Telegram binder (HQ Chair) — this card renders
 * truth and points there; it never grows approve/skip buttons.
 */
import { useEffect, useState } from 'react'
import type { MailboxPayload } from '@/app/api/world/mailbox/route'
import PixelFrame from './pixel-frame'

export default function DecisionQueueCard({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<MailboxPayload | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    fetch('/api/world/mailbox')
      .then((r) => (r.ok ? (r.json() as Promise<MailboxPayload>) : null))
      .then((p) => {
        if (!alive) return
        if (p) setData(p)
        else setFailed(true)
      })
      .catch(() => {
        if (alive) setFailed(true)
      })
    return () => {
      alive = false
    }
  }, [])

  return (
    <PixelFrame
      theme="parchment"
      className="pointer-events-auto fixed right-4 top-16 z-40 w-[26rem] max-w-[92vw]"
    >
      <div className="flex items-center justify-between border-b border-zinc-700/60 px-3 py-2">
        <span className="text-sm font-semibold">
          Mailbox — pending Captain decisions
        </span>
        <button
          onClick={onClose}
          className="ml-2 rounded px-2 py-0.5 text-xs text-zinc-400 hover:bg-zinc-800"
          aria-label="close mailbox"
        >
          esc
        </button>
      </div>
      <div className="max-h-96 overflow-y-auto p-3 text-xs leading-relaxed">
        {failed && (
          <p className="text-amber-300">
            queue unreadable — the mailbox renders nothing rather than a
            guess (loud failure, never silent).
          </p>
        )}
        {!failed && data === null && <p className="text-zinc-500">reading the queue…</p>}
        {data && data.items.length === 0 && !failed && (
          <p className="text-zinc-400">
            no pending decisions — the queue is honestly empty (flag down).
          </p>
        )}
        {data && data.items.length > 0 && (
          <ul className="space-y-1.5">
            {data.items.map((it) => (
              <li
                key={it.cid || it.subject}
                className="rounded bg-zinc-950/70 p-2"
              >
                <div className="truncate font-medium text-zinc-100">
                  {it.subject}
                </div>
                <div className="font-mono text-[10px] text-zinc-500">
                  lane {it.lane} · urgency {it.urgency}
                  {it.confidence !== null ? ` · conf ${it.confidence.toFixed(2)}` : ''}
                  {it.evidenceCount > 0 ? ` · ${it.evidenceCount} evidence refs` : ''}
                  {it.ts ? ` · ${it.ts.slice(0, 16).replace('T', ' ')}` : ''}
                </div>
              </li>
            ))}
          </ul>
        )}
        {data && data.pendingTotal > data.items.length && (
          <p className="mt-2 text-[10px] text-zinc-500">
            +{data.pendingTotal - data.items.length} more pending (render capped)
          </p>
        )}
        <div className="mt-3 space-y-1 border-t border-zinc-800 pt-2">
          {data?.queueHref ? (
            <a
              href={data.queueHref}
              target="_blank"
              rel="noreferrer"
              className="inline-block rounded bg-zinc-800 px-2 py-1 font-medium text-zinc-200 hover:bg-zinc-700"
            >
              open the real queue ↗
            </a>
          ) : (
            <p className="text-[10px] text-zinc-500">
              verdicts are given in the Captain&apos;s Telegram binder (HQ
              Chair) — the world renders this queue, never acts on it.
            </p>
          )}
          <p className="break-all font-mono text-[10px] text-zinc-600">
            PROOF: redis {data?.proof.keyPattern ?? 'cabinet:action:*'} ·{' '}
            {data ? `${data.pendingTotal} pending` : '—'}
          </p>
        </div>
      </div>
    </PixelFrame>
  )
}
