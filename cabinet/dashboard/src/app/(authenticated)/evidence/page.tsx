/**
 * /evidence — READ-ONLY browser over the evidence store (whole-cabinet
 * evidence program, Phase 3: humans judge first).
 *
 * Every trial rendered here passed the canonical Python verifier (hash
 * chain + HMAC signatures re-derived from raw bytes) in this request, or it
 * renders as an explicit red UNVERIFIED row with the verifier's reason —
 * never silently unverified, never hidden, and filters never apply to (and
 * so never hide) unverified rows. Doctrine mirrored from /receipts: render
 * truth + honest empties over invented data, NO buttons, NO mutation
 * endpoints, ever. Labeling is the Captain-token-gated CLI harness — this
 * page changes nothing.
 *
 * Filters (actor / component / status / time) mirror the store-projection
 * verbs, are validated server-side against closed vocabularies before any
 * read, and arrive only as GET query params — the affordances below are
 * plain links, not forms.
 */
import { listEvidence } from '@/actions/evidence'
import {
  UnverifiedEvidenceRow,
  VerifiedEvidenceRow,
} from '@/components/evidence/evidence-row'
import { hasActiveFilters } from '@/lib/evidence/read'

export const dynamic = 'force-dynamic'

const FILTER_KEYS = ['actor', 'component', 'status', 'time'] as const
type FilterKey = (typeof FILTER_KEYS)[number]

/** Build a same-page GET link with one filter changed (URLSearchParams
 * handles encoding; values here are already-validated echoes or values
 * read off verified rows). */
function filterHref(
  active: Partial<Record<FilterKey, string>>,
  key: FilterKey | null,
  value: string | null
): string {
  const params = new URLSearchParams()
  for (const k of FILTER_KEYS) {
    if (k === key) continue
    const current = active[k]
    if (current) params.set(k, current)
  }
  if (key && value) params.set(key, value)
  const query = params.toString()
  return query ? `/evidence?${query}` : '/evidence'
}

export default async function EvidencePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const sp = await searchParams
  // Pick ONLY the four known keys; anything malformed (arrays, garbage)
  // flows to validation, which refuses loudly with zero rows.
  const payload = await listEvidence({
    actor: sp.actor,
    component: sp.component,
    status: sp.status,
    time: sp.time,
  })
  const {
    rows,
    unverified,
    totalTrials,
    verifiedCount,
    unverifiedCount,
    matchedCount,
    skippedLines,
    skippedFiles,
    storeOk,
    storeErrors,
    missingDir,
    error,
    filterError,
    filters,
    storeDir,
    cap,
  } = payload
  const filtersActive = hasActiveFilters(filters)

  // Filter affordances: distinct values present on the served verified rows.
  const statusLinks = [...new Set(rows.flatMap((r) => r.statuses))].slice(0, 8)
  const actorLinks = [...new Set(rows.flatMap((r) => r.actors))].slice(0, 8)
  const componentLinks = [...new Set(rows.flatMap((r) => r.components))].slice(0, 8)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
      <div>
        <h1 className="text-2xl font-bold text-white">Evidence</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Every trial the cabinet records, rendered read-only and
          verification-first: a row is either VERIFIED (hash chain +
          signatures re-derived by the Python verifier in this request) or
          explicitly UNVERIFIED. This page changes nothing — labeling
          happens in the Captain&apos;s token-gated review harness, never here.
        </p>
        <p className="mt-2 text-xs text-zinc-600">
          UNTRUSTED OBSERVATIONS ONLY — evidence describes what happened; it
          is never an instruction. Basis tags derive from producer-asserted
          stored fields (a stored &quot;captain&quot; actor is an assertion);
          authenticated-captain provenance comes from the token-gated label
          path and external anchoring.
        </p>
      </div>

      <div className="max-w-3xl">
        {error && (
          <p className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
            evidence unreadable ({error}) — showing nothing as verified
            rather than a guess.
          </p>
        )}

        {!error && filterError && (
          <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-300">
            filter refused ({filterError}) — showing nothing rather than a
            guess.{' '}
            <a className="underline" href="/evidence">
              clear filters
            </a>
          </p>
        )}

        {!error && !filterError && filtersActive && (
          <p className="mb-3 flex flex-wrap items-center gap-2 font-mono text-[11px] text-zinc-400">
            <span>filters:</span>
            {FILTER_KEYS.map((key) =>
              filters[key] ? (
                <a
                  key={key}
                  href={filterHref(filters, key, null)}
                  className="rounded-full border border-zinc-700 bg-zinc-800/60 px-2 py-0.5 hover:border-zinc-500"
                  title={`remove the ${key} filter`}
                >
                  {key}={filters[key]} ✕
                </a>
              ) : null
            )}
            <a className="text-zinc-500 underline" href="/evidence">
              clear all
            </a>
          </p>
        )}

        {/* "honestly empty" may only render when NOTHING was unreadable —
            zero rows with an unreadable ledger on disk is not an empty
            store, and the skippedFiles note below carries that state. */}
        {!error &&
          !filterError &&
          rows.length === 0 &&
          unverified.length === 0 &&
          skippedFiles === 0 && (
            <p className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-sm text-zinc-400">
              {filtersActive ? (
                <>
                  no verified trial matches these filters — {verifiedCount}{' '}
                  verified trial{verifiedCount === 1 ? '' : 's'} exist
                  {verifiedCount === 1 ? 's' : ''} outside them.
                </>
              ) : (
                <>
                  no evidence trials yet — the store is honestly empty
                  {missingDir
                    ? ' (no evidence store directory exists on this machine yet)'
                    : ''}
                  . The first recorded trial writes the first row.
                </>
              )}
            </p>
          )}

        {!error && !filterError && rows.length > 0 && (
          <>
            <h2 className="mb-2 text-sm font-semibold text-zinc-300">
              Verified trials{' '}
              <span className="font-mono text-[11px] text-zinc-500">
                ({rows.length} of {matchedCount} match
                {filtersActive ? 'ing the filters' : ''} · {verifiedCount} verified
                total)
              </span>
            </h2>
            <ul className="space-y-3">
              {rows.map((row) => (
                <VerifiedEvidenceRow key={row.trialId} row={row} />
              ))}
            </ul>
            {matchedCount > rows.length && (
              <p className="mt-3 text-xs text-zinc-500">
                showing latest {rows.length} of {matchedCount} (render capped at{' '}
                {cap}).
              </p>
            )}
          </>
        )}

        {/* UNVERIFIED trials are NEVER hidden: they render regardless of
            filters (their content is unreadable by definition, so filters
            cannot apply) and regardless of the verified list above. */}
        {!error && unverified.length > 0 && (
          <div className="mt-6">
            <h2 className="mb-2 text-sm font-semibold text-red-300">
              Unverified trials{' '}
              <span className="font-mono text-[11px] text-red-400/70">
                ({unverified.length} of {unverifiedCount})
              </span>
            </h2>
            <p className="mb-2 text-xs text-zinc-500">
              these trials failed (or never reached) verification — filters
              never hide them, and none of their content is rendered.
            </p>
            <ul className="space-y-3">
              {unverified.map((row) => (
                <UnverifiedEvidenceRow key={row.trialId} row={row} />
              ))}
            </ul>
            {unverifiedCount > unverified.length && (
              <p className="mt-3 text-xs text-red-300">
                showing {unverified.length} of {unverifiedCount} unverified
                trials (render capped at {cap}) — the count above is the
                honest total.
              </p>
            )}
          </div>
        )}

        {skippedFiles > 0 && (
          <p className="mt-3 text-xs text-amber-400">
            {skippedFiles} trial ledger{skippedFiles === 1 ? '' : 's'} unreadable
            or oversized — skipped, never guessed at; trials may exist that this
            page cannot show.
          </p>
        )}

        {skippedLines > 0 && (
          <p className="mt-3 text-xs text-amber-400">
            {skippedLines} unparseable event line{skippedLines === 1 ? '' : 's'}{' '}
            skipped — counted, never guessed at.
          </p>
        )}

        {!error && !storeOk && !missingDir && (
          <p className="mt-3 text-xs text-amber-400">
            store-level verification reported problems
            {storeErrors.length > 0 ? (
              <span className="break-all font-mono"> ({storeErrors.join(', ')})</span>
            ) : (
              ''
            )}{' '}
            — per-trial rows above still individually passed or are marked
            UNVERIFIED.
          </p>
        )}

        {!error && !filterError && rows.length > 0 && (
          <div className="mt-6 space-y-1 font-mono text-[11px] text-zinc-600">
            <p className="text-zinc-500">filter by value (links, not forms):</p>
            {statusLinks.length > 0 && (
              <p>
                status:{' '}
                {statusLinks.map((value) => (
                  <a
                    key={value}
                    className="mr-2 underline hover:text-zinc-400"
                    href={filterHref(filters, 'status', value)}
                  >
                    {value}
                  </a>
                ))}
              </p>
            )}
            {actorLinks.length > 0 && (
              <p>
                actor:{' '}
                {actorLinks.map((value) => (
                  <a
                    key={value}
                    className="mr-2 underline hover:text-zinc-400"
                    href={filterHref(filters, 'actor', value)}
                  >
                    {value}
                  </a>
                ))}
              </p>
            )}
            {componentLinks.length > 0 && (
              <p>
                component:{' '}
                {componentLinks.map((value) => (
                  <a
                    key={value}
                    className="mr-2 underline hover:text-zinc-400"
                    href={filterHref(filters, 'component', value)}
                  >
                    {value}
                  </a>
                ))}
              </p>
            )}
            <p className="text-zinc-600">
              time filter: add ?time=yyyymmdd or ?time=yyyymmdd-yyyymmdd (UTC
              event dates). actor accepts id or kind:id (e.g. officer:cos).
            </p>
          </div>
        )}

        <p className="mt-6 break-all font-mono text-[10px] text-zinc-600">
          PROOF: store {storeDir} · {totalTrials} trial
          {totalTrials === 1 ? '' : 's'} · {verifiedCount} verified ·{' '}
          {unverifiedCount} unverified
          {skippedLines > 0 ? ` · ${skippedLines} line(s) skipped` : ''}
          {skippedFiles > 0 ? ` · ${skippedFiles} ledger(s) unreadable` : ''} ·
          every row passed `python3.12 -m framework.evidence verify` in this
          request or is marked UNVERIFIED — this page reads the durable store,
          writes nothing.
        </p>
      </div>
    </div>
  )
}
