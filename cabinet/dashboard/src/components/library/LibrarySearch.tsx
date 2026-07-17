'use client'

/**
 * LibrarySearch — debounced client search box over the org Library
 * (GET /api/library/search, the cabinet_memory org-knowledge search — see
 * @/lib/memory-search and docs/runbooks/library-search-2026-07-17.md).
 *
 * Rendering safety (Corridor-gated): snippets are UNTRUSTED stored text and
 * are rendered exclusively as React text nodes — highlightSnippet() returns
 * an array of strings and <mark> elements whose children are plain strings.
 * No dangerouslySetInnerHTML, no HTML parsing, anywhere in this component.
 * Hits that map to a vault note link into the vault browser (which
 * re-confines the path server-side); all other hits render a plain-text
 * source badge.
 */

import Link from 'next/link'
import { useCallback, useEffect, useRef, useState } from 'react'

export interface LibrarySearchHit {
  snippet: string
  source_type: string
  source_id: string
  score: number
  when_at: string | null
  libraryPath?: string
}

interface SearchResponse {
  results?: LibrarySearchHit[]
  degraded?: boolean
  error?: string
}

/** Friendly labels for the org-knowledge source classes (badge text). */
export const SOURCE_TYPE_LABELS: Record<string, string> = {
  product_brain: 'vault note',
  framework_doc: 'reference doc',
  framework_file: 'framework',
  captain_law_summary: 'decision digest',
  research_brief: 'research brief',
  experience_record: 'experience',
  library_record: 'library record',
  product_spec: 'product spec',
  tech_radar: 'tech radar',
  consolidated_belief: 'belief',
}

/**
 * Base route of the vault browser that vault-note hits link into.
 *
 * LINK-TARGET NOTE (integration 2026-07-17): '/library' — the LIB-IDENT lane
 * landed in the same commit and re-homed the vault browser at /library
 * (Captain naming ruling: the vault is where it's kept, the Library is where
 * you read). /vault lives on as a redirect alias into /library, so any
 * stale /vault link still resolves; new links go straight to the reader.
 */
export const VAULT_NOTE_BASE = '/library'

/** Segment-encode a vault-relative path into the vault-browser href. */
export function libraryHref(libraryPath: string): string {
  return (
    VAULT_NOTE_BASE +
    '/' +
    libraryPath.split('/').map(encodeURIComponent).join('/')
  )
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

const MAX_HIGHLIGHT_TERMS = 8

/**
 * Split a snippet into React nodes with query terms wrapped in <mark>.
 * Terms are regex-ESCAPED before matching, and every emitted node carries
 * only plain-string children — React escapes them, so stored HTML like
 * `<script>` renders inert as text.
 */
export function highlightSnippet(
  snippet: string,
  query: string
): React.ReactNode[] {
  const terms = query
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length >= 2)
    .slice(0, MAX_HIGHLIGHT_TERMS)
    .map(escapeRegExp)
  if (terms.length === 0 || !snippet) return [snippet]

  let re: RegExp
  try {
    re = new RegExp(`(${terms.join('|')})`, 'gi')
  } catch {
    return [snippet]
  }

  // Single capture group → odd indices are the matched terms.
  const parts = snippet.split(re)
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <mark
        key={i}
        className="rounded-sm bg-amber-400/20 px-0.5 text-amber-200"
      >
        {part}
      </mark>
    ) : (
      <span key={i}>{part}</span>
    )
  )
}

export default function LibrarySearch({
  limit = 20,
  placeholder = 'Search the library…',
}: {
  limit?: number
  placeholder?: string
}) {
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<LibrarySearchHit[]>([])
  const [activeQuery, setActiveQuery] = useState('')
  const [degraded, setDegraded] = useState(false)
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const search = useCallback(
    async (q: string) => {
      abortRef.current?.abort()
      if (!q.trim()) {
        setHits([])
        setActiveQuery('')
        setDegraded(false)
        setError(null)
        setSearching(false)
        return
      }

      const controller = new AbortController()
      abortRef.current = controller
      setSearching(true)
      setError(null)
      try {
        const res = await fetch(
          `/api/library/search?q=${encodeURIComponent(q)}&limit=${limit}`,
          { signal: controller.signal }
        )
        if (res.status === 429) {
          setError('Too many searches — wait a moment.')
          setHits([])
          return
        }
        if (!res.ok) throw new Error('search failed')
        const data = (await res.json()) as SearchResponse
        setHits(Array.isArray(data.results) ? data.results : [])
        setDegraded(data.degraded === true)
        setActiveQuery(q)
      } catch (err) {
        if ((err as Error)?.name === 'AbortError') return
        setError('Search unavailable')
        setHits([])
      } finally {
        if (abortRef.current === controller) setSearching(false)
      }
    },
    [limit]
  )

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      abortRef.current?.abort()
    }
  }, [])

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value
    setQuery(val)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      void search(val)
    }, 300)
  }

  return (
    <div>
      <div className="relative">
        <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-zinc-500">
          <svg
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"
            />
          </svg>
        </span>
        <input
          type="search"
          value={query}
          onChange={handleChange}
          placeholder={placeholder}
          className="w-full rounded-lg border border-zinc-700 bg-zinc-800 py-2.5 pl-9 pr-4 text-sm text-zinc-200 placeholder-zinc-500 outline-none transition-colors focus:border-zinc-500 focus:ring-1 focus:ring-zinc-500"
          aria-label="Search library"
        />
        {searching && (
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center">
            <svg
              className="h-3.5 w-3.5 animate-spin text-zinc-500"
              viewBox="0 0 24 24"
              fill="none"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
          </span>
        )}
      </div>

      {error && <p className="mt-2 text-xs text-zinc-500">{error}</p>}
      {!error && degraded && hits.length > 0 && (
        <p className="mt-2 text-xs text-zinc-600">
          Keyword match only — semantic ranking unavailable.
        </p>
      )}
      {!error && query.trim() && hits.length === 0 && !searching && (
        <p className="mt-2 text-xs text-zinc-500">No results found.</p>
      )}

      {hits.length > 0 && (
        <ul className="mt-2 space-y-1">
          {hits.map((hit, idx) => {
            const badge =
              SOURCE_TYPE_LABELS[hit.source_type] ?? hit.source_type
            const body = (
              <>
                <div className="flex items-baseline justify-between gap-2">
                  <p className="truncate font-medium text-zinc-200">
                    {hit.libraryPath ?? hit.source_id}
                  </p>
                  <span className="shrink-0 rounded bg-zinc-700/60 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">
                    {badge}
                  </span>
                </div>
                {hit.snippet && (
                  <p className="mt-0.5 line-clamp-2 text-xs text-zinc-500">
                    {highlightSnippet(hit.snippet, activeQuery)}
                  </p>
                )}
                {hit.when_at && (
                  <p className="mt-0.5 text-[10px] text-zinc-600">
                    {hit.when_at}
                  </p>
                )}
              </>
            )
            return (
              <li key={`${hit.source_type}:${hit.source_id}:${idx}`}>
                {hit.libraryPath ? (
                  <Link
                    href={libraryHref(hit.libraryPath)}
                    className="block rounded-lg border border-zinc-800 bg-zinc-800/50 p-2.5 text-sm transition-colors hover:border-zinc-700 hover:bg-zinc-800"
                  >
                    {body}
                  </Link>
                ) : (
                  <div className="block rounded-lg border border-zinc-800/60 bg-zinc-800/30 p-2.5 text-sm">
                    {body}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
