'use client'

/**
 * The three-tab WHAT / NOW / PROOF inspect card (§10.5 — built ONCE here,
 * reused by every later surface). All content renders as React text nodes
 * (textContent semantics — the CI ratchet rejects innerHTML in this tree).
 *
 * Schema fallbacks (UI-F6): decorative objects get a WHAT-only card;
 * pre-codex entries render "codex pending" + the mechanical binding line —
 * never generated prose.
 */
import { useState } from 'react'
import type { ChronicleRecord, OfficerPresence } from '@/lib/world/types'

export interface InspectTarget {
  kind: 'officer' | 'station' | 'record'
  id: string
  title: string
  /** WHAT: codex (human-authored in grammar law) or fallback text. */
  codex: {
    represents: string
    mechanism_path: string
    day0: string
  } | null
  decorative?: boolean
  /** NOW: live values (T2 — this card renders on the authed dashboard). */
  presence?: OfficerPresence | null
  /** PROOF: the most recent chronicle record touching this object. */
  proof?: ChronicleRecord | null
}

export default function InspectCard({
  target,
  onClose,
}: {
  target: InspectTarget
  onClose: () => void
}) {
  const tabs = target.decorative ? (['WHAT'] as const) : (['WHAT', 'NOW', 'PROOF'] as const)
  const [tab, setTab] = useState<(typeof tabs)[number]>('WHAT')

  return (
    <div className="pointer-events-auto fixed right-4 top-16 z-40 w-96 max-w-[92vw] rounded-lg border border-zinc-700 bg-zinc-900/95 text-zinc-100 shadow-2xl">
      <div className="flex items-center justify-between border-b border-zinc-700 px-3 py-2">
        <span className="truncate text-sm font-semibold">{target.title}</span>
        <button
          onClick={onClose}
          className="ml-2 rounded px-2 py-0.5 text-xs text-zinc-400 hover:bg-zinc-800"
          aria-label="close inspect card"
        >
          esc
        </button>
      </div>
      <div className="flex gap-1 border-b border-zinc-800 px-2 pt-1">
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={
              'rounded-t px-3 py-1 text-xs font-medium ' +
              (tab === t
                ? 'bg-zinc-800 text-zinc-100'
                : 'text-zinc-500 hover:text-zinc-300')
            }
          >
            {t}
          </button>
        ))}
      </div>
      <div className="max-h-80 overflow-y-auto p-3 text-xs leading-relaxed">
        {tab === 'WHAT' && (
          <div className="space-y-2">
            {target.decorative ? (
              <p className="text-zinc-400">
                decorative — carries no data
              </p>
            ) : target.codex ? (
              <>
                <p>{target.codex.represents}</p>
                {/* Machine-derived binding line directly under the prose
                    (UI-F3b): a lying codex is contradicted on its own card. */}
                <div className="rounded bg-zinc-950 p-2 font-mono text-[11px] text-zinc-400">
                  <div>mechanism: {target.codex.mechanism_path}</div>
                  <div>day0: {target.codex.day0}</div>
                </div>
              </>
            ) : (
              <>
                <p className="text-amber-300">codex pending</p>
                <p className="text-zinc-400">
                  This object has no reviewed codex entry yet (grammar-gap
                  discipline: it renders mechanically, never with generated
                  prose).
                </p>
              </>
            )}
          </div>
        )}
        {tab === 'NOW' && !target.decorative && (
          <div className="space-y-1 font-mono text-[11px]">
            {target.presence ? (
              <>
                <div>present: {String(target.presence.present)}</div>
                {target.presence.verb ? (
                  <div>verb: {target.presence.verb}</div>
                ) : (
                  <div className="text-zinc-500">verb: — (activity TTL expired)</div>
                )}
                {target.presence.object ? (
                  <div className="break-all">object: {target.presence.object}</div>
                ) : null}
                {target.presence.since ? (
                  <div>since: {target.presence.since}</div>
                ) : null}
                {typeof target.presence.hb_ttl_s === 'number' ? (
                  <div>heartbeat ttl: {target.presence.hb_ttl_s}s</div>
                ) : (
                  <div className="text-zinc-500">heartbeat: no reading</div>
                )}
              </>
            ) : (
              <div className="text-zinc-500">
                no live binding for this object (dark renders dark — never a
                fake zero)
              </div>
            )}
          </div>
        )}
        {tab === 'PROOF' && !target.decorative && (
          <div className="space-y-2">
            {target.proof ? (
              <>
                <p className="text-zinc-400">
                  latest chronicle record touching this object (PII-scrubbed
                  at ingest; iid {target.proof.iid}):
                </p>
                <pre className="overflow-x-auto rounded bg-zinc-950 p-2 font-mono text-[10px] text-zinc-300">
                  {JSON.stringify(target.proof, null, 2)}
                </pre>
                {target.proof.ref ? (
                  <p className="break-all font-mono text-[10px] text-zinc-500">
                    cite: {target.proof.src} · {target.proof.ref}
                  </p>
                ) : null}
              </>
            ) : (
              <p className="text-zinc-500">
                no chronicle record yet — this object has not been touched
                since the chronicle began (E0b start; honest absence, not an
                error)
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
