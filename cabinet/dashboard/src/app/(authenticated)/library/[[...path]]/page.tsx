/**
 * /library/[[...path]] — the LIBRARY: the READ-ONLY vault reader
 * (blueprint §1, §4; Captain naming ruling 2026-07-17: "keep the name
 * Library — it fits the world; the vault is where it's kept, the Library is
 * where you read"). This is the phase-1 vault browser MOVED here verbatim
 * (was /vault/[[...path]]; /vault now redirects to /library).
 *
 * One catch-all server component: empty path → root listing (+ collapsible
 * History note + Browse|Graph tabs), path→dir → directory listing,
 * path→file → rendered note + backlinks. Lives under the (authenticated)
 * route group, so the edge middleware's cabinet_session gate covers it for
 * free (unauth → 307 /login); the layout does no re-check (house pattern).
 * Zero mutation endpoints, zero DB — the retired Library STORE stays
 * retired; the corpus is read from the FILESYSTEM through the confinement
 * layer in lib/vault.ts. Legacy 1–2-segment extension-less deep links (old
 * space/record ids) redirect to /library — miss and confinement-denial
 * behave identically, so no path-existence oracle appears.
 *
 * Docs: docs/runbooks/vault-browser-2026-07-17.md.
 */

import Link from 'next/link'
import { notFound, redirect } from 'next/navigation'
import VaultMarkdown from '@/components/vault/VaultMarkdown'
import BacklinksPanel from '@/components/library/BacklinksPanel'
import LibrarySearch from '@/components/library/LibrarySearch'
import LibraryTabs from '@/components/library/LibraryTabs'
import {
  hasVault,
  classifyPath,
  listDir,
  readNote,
  buildBasenameIndex,
  resolveNoteTarget,
  VaultPathError,
  type VaultEntry,
  type VaultNote,
} from '@/lib/vault'
import { rewriteWikilinks, vaultHref } from '@/lib/vault-wikilinks'

export const dynamic = 'force-dynamic'

export async function generateMetadata({
  params,
}: {
  params: Promise<{ path?: string[] }>
}) {
  const { path: segments } = await params
  const name = segments && segments.length > 0 ? segments[segments.length - 1] : 'root'
  return { title: `Library · ${name}` }
}

// ------------------------------------------------------------
// Breadcrumb
// ------------------------------------------------------------

function Breadcrumb({ rel }: { rel: string }) {
  const parts = rel.split('/').filter(Boolean)
  const crumbs: { label: string; href: string }[] = []
  let acc = ''
  for (const p of parts) {
    acc = acc ? `${acc}/${p}` : p
    crumbs.push({ label: p, href: vaultHref(acc) })
  }
  return (
    <nav className="mb-6 flex flex-wrap items-center gap-1 text-sm text-zinc-500">
      <Link href="/library" className="text-zinc-300 hover:text-white">
        library
      </Link>
      {crumbs.map((c, i) => (
        <span key={c.href} className="flex items-center gap-1">
          <span className="text-zinc-600">/</span>
          {i === crumbs.length - 1 ? (
            <span className="text-white">{c.label}</span>
          ) : (
            <Link href={c.href} className="text-zinc-300 hover:text-white">
              {c.label}
            </Link>
          )}
        </span>
      ))}
    </nav>
  )
}

// ------------------------------------------------------------
// Directory listing
// ------------------------------------------------------------

function DirIcon() {
  return <span aria-hidden className="text-amber-500">▸</span>
}
function NoteIcon() {
  return <span aria-hidden className="text-zinc-500">•</span>
}

/**
 * Collapsible "History" note on the Library root — the successor of the
 * full-page retirement notice (Captain ruling 2026-07-17). The story in one
 * breath: the editable STORE was retired 2026-07-16 (nothing deleted; records
 * exported to `vault/library-archive/`, mirrored into cabinet memory for
 * `memory_search`; DB tables dormant); the READER returned 2026-07-17 as this
 * page. Rendered as a native <details> — no client JS, collapsed by default.
 */
function HistoryNote() {
  return (
    <details className="mb-6 rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-2 text-xs text-zinc-500">
      <summary className="cursor-pointer select-none text-zinc-400">
        History
      </summary>
      <div className="mt-2 flex flex-col gap-1.5 pb-1">
        <p>
          <span className="text-zinc-300">2026-07-16</span> — the editable
          Library store (Spaces/Records + vector search) was retired,
          Captain-ratified. Nothing was deleted: every record was exported to{' '}
          <code className="rounded bg-zinc-800 px-1 py-0.5 text-zinc-300">
            vault/library-archive/
          </code>{' '}
          with provenance frontmatter, mirrored into cabinet memory (find it
          via <code className="rounded bg-zinc-800 px-1 py-0.5 text-zinc-300">memory_search</code>),
          and the database tables remain in place, dormant.
        </p>
        <p>
          <span className="text-zinc-300">2026-07-17</span> — the reader
          returned: this page. The content lives in the vault; the Library is
          where you read it. Runbooks:{' '}
          <code className="rounded bg-zinc-800 px-1 py-0.5 text-zinc-400">
            docs/runbooks/library-retirement-2026-07-16.md
          </code>{' '}
          ·{' '}
          <code className="rounded bg-zinc-800 px-1 py-0.5 text-zinc-400">
            docs/runbooks/vault-browser-2026-07-17.md
          </code>
        </p>
      </div>
    </details>
  )
}

function DirectoryView({ rel }: { rel: string }) {
  let entries: VaultEntry[]
  try {
    entries = listDir(rel)
  } catch {
    notFound()
  }

  const isRoot = rel === ''
  return (
    <div className="mx-auto max-w-3xl">
      {isRoot ? <LibraryTabs active="browse" /> : <Breadcrumb rel={rel} />}
      <h1 className="mb-1 text-2xl font-semibold text-white">
        {isRoot ? 'Library' : rel.split('/').pop()}
      </h1>
      <p className="mb-6 text-sm text-zinc-500">
        Read-only reader over the cabinet&apos;s knowledge vault.
      </p>
      {isRoot && <HistoryNote />}

      {/* Memory-search box (SEARCH lane, integrated 2026-07-17): the client
          component calls GET /api/library/search — the cabinet_memory
          org-knowledge engine. This server component stays DB-free; vault
          hits link back into this reader. */}
      {isRoot && (
        <div className="mb-6 rounded-xl border border-zinc-800 bg-zinc-900 p-6">
          <h2 className="text-sm font-semibold text-zinc-300">
            Search the library
          </h2>
          <p className="mt-1 text-xs text-zinc-500">
            Searches cabinet memory across the org-knowledge corpus: vault
            notes, reference docs, decision digests, research briefs, product
            specs and experience records. Vault hits link straight into the
            note.
          </p>
          <div className="mt-3">
            <LibrarySearch />
          </div>
        </div>
      )}

      {entries.length === 0 ? (
        <p className="rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-6 text-sm text-zinc-500">
          This folder is empty.
        </p>
      ) : (
        <ul className="divide-y divide-zinc-800 overflow-hidden rounded-lg border border-zinc-800 bg-zinc-900">
          {entries.map((e) => (
            <li key={e.relPath}>
              <Link
                href={vaultHref(e.relPath)}
                className="flex items-center gap-3 px-4 py-2.5 text-sm text-zinc-300 hover:bg-zinc-800"
              >
                {e.kind === 'dir' ? <DirIcon /> : <NoteIcon />}
                <span className={e.kind === 'dir' ? 'font-medium text-white' : ''}>
                  {e.name}
                  {e.kind === 'dir' ? '/' : ''}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ------------------------------------------------------------
// Note view
// ------------------------------------------------------------

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

function FrontmatterStrip({ frontmatter }: { frontmatter: Record<string, unknown> }) {
  // `title` is already rendered as the note's <h1> heading; skip it here so it
  // is not shown twice.
  const entries = Object.entries(frontmatter).filter(
    ([k, v]) => k !== 'title' && v !== null && v !== ''
  )
  if (entries.length === 0) return null
  return (
    <dl className="mb-6 grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 text-xs">
      {entries.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-zinc-500">{k}</dt>
          {/* Values render as React text — inert data, never markup. */}
          <dd className="text-zinc-300">{formatFrontmatterValue(v)}</dd>
        </div>
      ))}
    </dl>
  )
}

function NoteView({ rel }: { rel: string }) {
  let note: VaultNote
  try {
    note = readNote(rel)
  } catch {
    notFound()
  }

  // Resolve [[wikilinks]] against a confined filesystem basename index and
  // rewrite them to internal links BEFORE the safe renderer runs.
  const index = buildBasenameIndex()
  const processed = rewriteWikilinks(note.body, (target) =>
    resolveNoteTarget(target, index)
  )

  const title =
    (typeof note.frontmatter?.title === 'string' && note.frontmatter.title) ||
    rel.split('/').pop()?.replace(/\.(md|markdown)$/i, '') ||
    'Note'

  return (
    <div className="mx-auto max-w-3xl">
      <Breadcrumb rel={rel} />
      <h1 className="mb-4 text-2xl font-semibold text-white">{title}</h1>
      {note.frontmatter && <FrontmatterStrip frontmatter={note.frontmatter} />}
      <VaultMarkdown markdown={processed} />
      <div className="mt-8">
        <BacklinksPanel rel={rel} />
      </div>
    </div>
  )
}

// ------------------------------------------------------------
// Router
// ------------------------------------------------------------

function EmptyLibrary() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 py-12">
      <h1 className="text-2xl font-bold text-white">Library</h1>
      <p className="text-sm text-zinc-500">
        No vault is configured for this cabinet, so there is nothing to read
        yet. The org vault is the <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-300">vault/</code>{' '}
        directory in the repository.
      </p>
      <HistoryNote />
    </div>
  )
}

/** Markdown-note extension test (local mirror of lib/vault.ts MD_EXT). */
const MD_EXT_RE = /\.(md|markdown)$/i

/**
 * True for the shape of a RETIRED-store deep link: 1–2 segments, last segment
 * without a markdown extension — exactly the old /library/[spaceId] and
 * /library/[spaceId]/[recordId] address space. Those stubs redirected to
 * /library (retirement contract 2026-07-16); the catch-all preserves that
 * honest landing for unresolvable paths of the SAME SHAPE, judged on the
 * request shape only — never on filesystem state — so no existence oracle.
 */
function isLegacyDeepLinkShape(segments: string[]): boolean {
  return (
    segments.length >= 1 &&
    segments.length <= 2 &&
    !MD_EXT_RE.test(segments[segments.length - 1])
  )
}

export default async function LibraryPage({
  params,
}: {
  params: Promise<{ path?: string[] }>
}) {
  const { path: segments } = await params
  // Next has already URL-decoded each route segment. Join to a vault-relative
  // path; the confinement layer rejects any escape.
  const rel = (segments ?? []).join('/')

  if (!hasVault()) {
    if (rel === '') return <EmptyLibrary />
    if (segments && isLegacyDeepLinkShape(segments)) redirect('/library')
    notFound()
  }

  let kind: ReturnType<typeof classifyPath>
  try {
    kind = classifyPath(rel)
  } catch (err) {
    // classifyPath swallows VaultPathError, but be explicit: any denial → 404.
    if (err instanceof VaultPathError) notFound()
    throw err
  }

  if (kind === 'dir') return <DirectoryView rel={rel} />
  if (kind === 'file') return <NoteView rel={rel} />
  // Unresolvable. Old space/record bookmarks (retired store) land on the
  // Library root instead of a 404; note-shaped misses stay a generic 404.
  if (segments && isLegacyDeepLinkShape(segments)) redirect('/library')
  notFound()
}
