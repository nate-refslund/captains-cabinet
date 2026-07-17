'use client'

/**
 * LibraryCard — the Library building's world-native reading surface
 * (spec v2 §5.2 Memory Library "[v3] card gains GET-only search (P6)";
 * §9.2 library query dialog = input row + typewriter results; §9.3 fresh
 * ruling: the library stays READ-only).
 *
 * Opened by the Library building's primary interaction in the engine shell
 * (one continuous world — the card is chrome OVER the live canvas; the
 * world keeps ticking; NEVER a scene swap, NEVER a route change).
 *
 * Read-only by construction, mailbox-card pattern: this file issues plain
 * single-argument GET fetches ONLY (no request-init object), imports no
 * server actions, and renders every byte of vault/search content either
 * as React text nodes or through the existing sanitizing VaultMarkdown
 * pipeline (react-markdown + rehype-sanitize; no rehype-raw; no
 * HTML-injection API anywhere — the world tree ratchet greps for them).
 * Wikilinks that resolve to internal
 * library hrefs are intercepted (capture phase) and opened IN-CARD — the
 * world stays where it is; internal-shaped hrefs that do NOT map to a safe
 * vault relpath are INERT (never a same-tab exit off /world); external
 * links keep VaultMarkdown's hardened
 * target="_blank" rel="noopener noreferrer nofollow" behavior.
 *
 * Data: GET /api/world/library/browse|note (org vault via lib/vault's
 * confined resolvers) and GET /api/world/library/search (server-side
 * adapter over the lane-2 library-search contract → cabinet_memory).
 * Determinism ratchet: no Date.now / Math.random — the typewriter reveal
 * rides a plain interval counter.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import VaultMarkdown from '@/components/vault/VaultMarkdown'
import {
  crumbsFor,
  isInternalLibraryHref,
  overlayPathFromHref,
  parentPath,
  type WorldLibraryBrowsePayload,
  type WorldLibraryNotePayload,
  type WorldLibrarySearchHit,
  type WorldLibrarySearchPayload,
} from '@/lib/world/library-panel'
import PixelFrame from './pixel-frame'

const MD_EXT_RE = /\.(md|markdown)$/i
/** Typewriter reveal: characters added per interval step (§9.2 results). */
const TYPE_STEP_CHARS = 24
const TYPE_STEP_MS = 16

type Status = 'idle' | 'loading' | 'error'

/**
 * Search-hit list — presentational and PURE (exported for the XSS negative
 * controls: hostile titles/snippets must render as escaped React text).
 * The typewriter reveal is a plain character count supplied by the card.
 */
export function LibrarySearchHitList({
  hits,
  reveal,
  onOpen,
}: {
  hits: WorldLibrarySearchHit[]
  reveal: number
  onOpen: (vaultPath: string) => void
}) {
  return (
    <ul className="space-y-1.5">
      {hits.map((h, i) => (
        <li key={`${h.ref}:${i}`} className="rounded bg-zinc-950/70 p-2">
          {h.vaultPath ? (
            <button
              onClick={() => {
                if (h.vaultPath) onOpen(h.vaultPath)
              }}
              className="block w-full truncate text-left font-medium text-zinc-100 hover:text-amber-200"
            >
              {h.title}
            </button>
          ) : (
            <div className="truncate font-medium text-zinc-100">{h.title}</div>
          )}
          {/* typewriter reveal — data as React text, always */}
          <div className="text-[11px] text-zinc-400">{h.snippet.slice(0, reveal)}</div>
          <div className="font-mono text-[10px] text-zinc-600">
            {h.ref ? `ref ${h.ref}` : 'unreferenced'}
            {h.score !== null ? ` · score ${h.score.toFixed(2)}` : ''}
          </div>
        </li>
      ))}
    </ul>
  )
}

function formatFrontmatterValue(v: unknown): string {
  if (v === null || v === undefined) return ''
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
    return String(v)
  }
  try {
    return JSON.stringify(v)
  } catch {
    return ''
  }
}

export default function LibraryCard({ onClose }: { onClose: () => void }) {
  // Browse state
  const [path, setPath] = useState('')
  const [dir, setDir] = useState<WorldLibraryBrowsePayload | null>(null)
  const [dirStatus, setDirStatus] = useState<Status>('loading')
  // Note state (non-null = note view)
  const [note, setNote] = useState<WorldLibraryNotePayload | null>(null)
  const [noteStatus, setNoteStatus] = useState<Status>('idle')
  // Search state (activeQuery non-null = results view)
  const [q, setQ] = useState('')
  const [activeQuery, setActiveQuery] = useState<string | null>(null)
  const [results, setResults] = useState<WorldLibrarySearchPayload | null>(null)
  const [searchStatus, setSearchStatus] = useState<Status>('idle')
  // Typewriter reveal counter (chars visible per snippet).
  const [reveal, setReveal] = useState(0)
  // Stale-response guards, one per fetch surface: a response applies ONLY if
  // it is still the latest issue of ITS counter (rapid clicks / Enter
  // presses / close-then-reopen can land out of order).
  const browseSeqRef = useRef(0)
  const noteSeqRef = useRef(0)
  const searchSeqRef = useRef(0)

  // ── browse feed ──────────────────────────────────────────────────────────
  useEffect(() => {
    const seq = ++browseSeqRef.current
    setDirStatus('loading')
    fetch('/api/world/library/browse?path=' + encodeURIComponent(path))
      .then((r) => (r.ok ? (r.json() as Promise<WorldLibraryBrowsePayload>) : null))
      .then((p) => {
        if (seq !== browseSeqRef.current) return
        if (p) {
          setDir(p)
          setDirStatus('idle')
        } else {
          setDirStatus('error')
        }
      })
      .catch(() => {
        if (seq === browseSeqRef.current) setDirStatus('error')
      })
  }, [path])

  // ── note open / close ────────────────────────────────────────────────────
  const openNote = useCallback((rel: string) => {
    const seq = ++noteSeqRef.current
    setNoteStatus('loading')
    setNote(null)
    fetch('/api/world/library/note?path=' + encodeURIComponent(rel))
      .then((r) => (r.ok ? (r.json() as Promise<WorldLibraryNotePayload>) : null))
      .then((p) => {
        if (seq !== noteSeqRef.current) return // a newer open/close won
        if (p) {
          setNote(p)
          setNoteStatus('idle')
        } else {
          setNoteStatus('error')
        }
      })
      .catch(() => {
        if (seq === noteSeqRef.current) setNoteStatus('error')
      })
  }, [])
  const closeNote = useCallback(() => {
    ++noteSeqRef.current // drop any in-flight note response
    setNote(null)
    setNoteStatus('idle')
  }, [])

  // ── search ───────────────────────────────────────────────────────────────
  const runSearch = useCallback((query: string) => {
    const trimmed = query.trim()
    if (!trimmed) {
      ++searchSeqRef.current // drop any in-flight search response
      setActiveQuery(null)
      setResults(null)
      setSearchStatus('idle')
      return
    }
    const seq = ++searchSeqRef.current
    ++noteSeqRef.current // leaving the note view — its in-flight fetch too
    setActiveQuery(trimmed)
    setNote(null)
    setNoteStatus('idle')
    setSearchStatus('loading')
    setResults(null)
    fetch('/api/world/library/search?q=' + encodeURIComponent(trimmed))
      .then((r) => (r.ok ? (r.json() as Promise<WorldLibrarySearchPayload>) : null))
      .then((p) => {
        if (seq !== searchSeqRef.current) return // a newer search/clear won
        if (p) {
          setResults(p)
          setSearchStatus('idle')
        } else {
          setSearchStatus('error')
        }
      })
      .catch(() => {
        if (seq === searchSeqRef.current) setSearchStatus('error')
      })
  }, [])
  const clearSearch = useCallback(() => {
    ++searchSeqRef.current // drop any in-flight search response
    setQ('')
    setActiveQuery(null)
    setResults(null)
    setSearchStatus('idle')
  }, [])

  // Typewriter reveal for search results (§9.2): plain interval counter —
  // no wall clock, no RNG; resets whenever a result set lands.
  useEffect(() => {
    if (!results || results.hits.length === 0) return
    setReveal(0)
    const maxLen = results.hits.reduce((m, h) => Math.max(m, h.snippet.length), 0)
    const t = setInterval(() => {
      setReveal((r) => {
        if (r >= maxLen) {
          clearInterval(t)
          return r
        }
        return r + TYPE_STEP_CHARS
      })
    }, TYPE_STEP_MS)
    return () => clearInterval(t)
  }, [results])

  // ── in-card wikilink interception (capture phase, before next/link) ──────
  const onContentClickCapture = useCallback(
    (ev: React.MouseEvent) => {
      const el = ev.target as HTMLElement | null
      const anchor = el?.closest ? (el.closest('a') as HTMLAnchorElement | null) : null
      if (!anchor) return
      const href = anchor.getAttribute('href')
      const mapped = overlayPathFromHref(href)
      if (mapped === null) {
        // Internal-shaped but UNMAPPABLE (a note-authored '/library/%zz' or
        // '/library/../x'): INERT — never let the anchor's next/link
        // same-tab-navigate the world away. Genuinely external / mailto /
        // fragment anchors keep their own (hardened) behavior.
        if (isInternalLibraryHref(href)) {
          ev.preventDefault()
          ev.stopPropagation()
        }
        return
      }
      ev.preventDefault()
      ev.stopPropagation()
      if (mapped === '') {
        closeNote()
        setPath('')
      } else if (MD_EXT_RE.test(mapped)) {
        openNote(mapped)
      } else {
        closeNote()
        setPath(mapped)
      }
    },
    [closeNote, openNote]
  )

  // Keep typing in the card from driving the world's hotkeys (w/a/s/d pan,
  // +/- zoom). Escape is deliberately NOT stopped — the shell closes the
  // card, same as the mailbox.
  const stopWorldHotkeys = useCallback((ev: React.KeyboardEvent) => {
    if (ev.key !== 'Escape') ev.stopPropagation()
  }, [])

  const view: 'note' | 'search' | 'dir' =
    note || noteStatus === 'loading' || noteStatus === 'error'
      ? 'note'
      : activeQuery !== null
        ? 'search'
        : 'dir'
  const crumbs = crumbsFor(view === 'note' && note ? note.relPath : path)

  return (
    <PixelFrame
      theme="parchment"
      className="pointer-events-auto fixed right-4 top-16 z-40 w-[30rem] max-w-[94vw]"
    >
      <div
        data-world-library
        onWheel={(ev) => ev.stopPropagation()}
        onPointerDown={(ev) => ev.stopPropagation()}
        onPointerMove={(ev) => ev.stopPropagation()}
      >
        {/* header */}
        <div className="flex items-center justify-between border-b border-zinc-700/60 px-3 py-2">
          <span className="text-sm font-semibold">
            The Library — org knowledge &amp; history
          </span>
          <button
            onClick={onClose}
            className="ml-2 rounded px-2 py-0.5 text-xs text-zinc-400 hover:bg-zinc-800"
            aria-label="close library"
          >
            esc
          </button>
        </div>

        {/* search input row (§9.2 library query dialog) */}
        <div className="flex items-center gap-2 border-b border-zinc-800/80 px-3 py-2">
          <input
            value={q}
            onChange={(ev) => setQ(ev.target.value)}
            onKeyDown={(ev) => {
              stopWorldHotkeys(ev)
              if (ev.key === 'Enter') runSearch(q)
            }}
            placeholder="search the library…"
            aria-label="search the library"
            className="w-full rounded bg-zinc-950/70 px-2 py-1 font-mono text-xs text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-amber-700/60"
          />
          {activeQuery !== null && (
            <button
              onClick={clearSearch}
              className="rounded px-2 py-0.5 text-[10px] text-zinc-400 hover:bg-zinc-800"
              aria-label="clear search"
            >
              clear
            </button>
          )}
        </div>

        {/* breadcrumb (browse + note views) */}
        {view !== 'search' && (
          <nav className="flex flex-wrap items-center gap-1 px-3 pt-2 text-[11px] text-zinc-500">
            <button
              onClick={() => {
                closeNote()
                setPath('')
              }}
              className="rounded px-1 text-zinc-300 hover:bg-zinc-800 hover:text-white"
            >
              library
            </button>
            {crumbs.map((c, i) => (
              <span key={c.path} className="flex items-center gap-1">
                <span className="text-zinc-600">/</span>
                {i === crumbs.length - 1 ? (
                  <span className="text-zinc-200">{c.label}</span>
                ) : (
                  <button
                    onClick={() => {
                      closeNote()
                      setPath(c.path)
                    }}
                    className="rounded px-1 text-zinc-300 hover:bg-zinc-800 hover:text-white"
                  >
                    {c.label}
                  </button>
                )}
              </span>
            ))}
          </nav>
        )}

        {/* body */}
        <div className="max-h-[26rem] overflow-y-auto p-3 text-xs leading-relaxed">
          {view === 'dir' && (
            <>
              {dirStatus === 'loading' && (
                <p className="text-zinc-500">
                  opening the shelves<span className="animate-pulse">…</span>
                </p>
              )}
              {dirStatus === 'error' && (
                <p className="text-amber-300">
                  shelf unreadable — the library renders nothing rather than a
                  guess (loud failure, never silent).
                </p>
              )}
              {dirStatus === 'idle' && dir && !dir.vaultConfigured && (
                <p className="text-zinc-400">
                  no vault corpus is configured — the shelves are honestly
                  empty. The org vault is the <code>vault/</code> directory in
                  the repository.
                </p>
              )}
              {dirStatus === 'idle' && dir && dir.vaultConfigured && (
                <>
                  {path !== '' && (
                    <button
                      onClick={() => setPath(parentPath(path))}
                      className="mb-1 block w-full rounded px-2 py-1 text-left text-zinc-400 hover:bg-zinc-800"
                    >
                      ↑ ..
                    </button>
                  )}
                  {dir.entries.length === 0 ? (
                    <p className="text-zinc-500">this shelf is empty.</p>
                  ) : (
                    <ul className="space-y-0.5">
                      {dir.entries.map((e) => (
                        <li key={e.relPath}>
                          <button
                            onClick={() =>
                              e.kind === 'dir' ? setPath(e.relPath) : openNote(e.relPath)
                            }
                            className="block w-full rounded px-2 py-1 text-left text-zinc-200 hover:bg-zinc-800"
                          >
                            {e.kind === 'dir' ? (
                              <span aria-hidden className="mr-2 text-amber-500">
                                ▸
                              </span>
                            ) : (
                              <span aria-hidden className="mr-2 text-zinc-500">
                                •
                              </span>
                            )}
                            {e.name}
                            {e.kind === 'dir' ? '/' : ''}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </>
          )}

          {view === 'note' && (
            <>
              <button
                onClick={closeNote}
                className="mb-2 rounded px-2 py-0.5 text-[10px] text-zinc-400 hover:bg-zinc-800"
              >
                ← back to the shelf
              </button>
              {noteStatus === 'loading' && (
                <p className="text-zinc-500">
                  fetching the volume<span className="animate-pulse">…</span>
                </p>
              )}
              {noteStatus === 'error' && (
                <p className="text-amber-300">
                  that volume is unavailable — nothing is rendered in its
                  place (loud failure, never silent).
                </p>
              )}
              {note && (
                <div onClickCapture={onContentClickCapture}>
                  <h2 className="mb-1 text-sm font-semibold text-zinc-100">{note.title}</h2>
                  <p className="mb-2 break-all font-mono text-[10px] text-zinc-500">
                    {note.relPath}
                  </p>
                  {note.frontmatter && (
                    <dl className="mb-3 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-0.5 rounded bg-zinc-950/60 px-2 py-1.5 font-mono text-[10px]">
                      {Object.entries(note.frontmatter)
                        .filter(([k, v]) => k !== 'title' && v !== null && v !== '')
                        .slice(0, 6)
                        .map(([k, v]) => (
                          <div key={k} className="contents">
                            <dt className="text-zinc-500">{k}</dt>
                            {/* data only — rendered as React text, never markup */}
                            <dd className="break-all text-zinc-300">
                              {formatFrontmatterValue(v)}
                            </dd>
                          </div>
                        ))}
                    </dl>
                  )}
                  <VaultMarkdown markdown={note.markdown} />
                </div>
              )}
            </>
          )}

          {view === 'search' && (
            <>
              {searchStatus === 'loading' && (
                <p className="text-zinc-500">
                  consulting the index<span className="animate-pulse">…</span>
                </p>
              )}
              {searchStatus === 'error' && (
                <p className="text-amber-300">
                  the index did not answer — no results are invented (loud
                  failure, never silent).
                </p>
              )}
              {searchStatus === 'idle' && results && !results.available && (
                <p className="text-zinc-400">
                  the search index is unreachable — no results are invented.
                  Browsing and reading work regardless.
                </p>
              )}
              {searchStatus === 'idle' && results?.available && results.rateLimited && (
                <p className="text-zinc-400">
                  the index is catching its breath (rate limit) — try again in
                  a moment.
                </p>
              )}
              {searchStatus === 'idle' && results?.available && !results.rateLimited && (
                <>
                  {results.degraded && (
                    <p className="mb-1.5 text-[10px] text-amber-300/90">
                      semantic arm down — lexical-only ranking (honest degrade)
                    </p>
                  )}
                  {results.hits.length === 0 ? (
                    <p className="text-zinc-500">
                      nothing in the library answers “{activeQuery}”.
                    </p>
                  ) : (
                    <LibrarySearchHitList
                      hits={results.hits}
                      reveal={reveal}
                      onOpen={openNote}
                    />
                  )}
                </>
              )}
            </>
          )}
        </div>

        {/* footer: deep-link out + PROOF (mailbox-card pattern) */}
        <div className="space-y-1 border-t border-zinc-800 px-3 py-2">
          <a
            href="/library"
            target="_blank"
            rel="noreferrer"
            className="inline-block rounded bg-zinc-800 px-2 py-1 text-[11px] font-medium text-zinc-200 hover:bg-zinc-700"
          >
            open the full Library ↗
          </a>
          <p className="break-all font-mono text-[10px] text-zinc-600">
            PROOF: org vault via lib/vault confined read · search:{' '}
            {results?.backend ?? '/api/library/search → cabinet_memory'} · read-only
            (ruling 2026-07-09)
          </p>
        </div>
      </div>
    </PixelFrame>
  )
}
