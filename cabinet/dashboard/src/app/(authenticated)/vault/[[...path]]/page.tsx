/**
 * /vault/[[...path]] — READ-ONLY vault browser (blueprint §1, §4).
 *
 * One catch-all server component: empty path → root listing, path→dir →
 * directory listing, path→file → rendered note. Lives under the
 * (authenticated) route group, so the edge middleware's cabinet_session gate
 * covers it for free (unauth → 307 /login); the layout does no re-check
 * (house pattern). Zero mutation endpoints, zero DB — the vault is read from
 * the FILESYSTEM through the confinement layer in lib/vault.ts.
 *
 * Docs: docs/runbooks/vault-browser-2026-07-17.md.
 */

import Link from 'next/link'
import { notFound } from 'next/navigation'
import VaultMarkdown from '@/components/vault/VaultMarkdown'
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
  return { title: `Vault · ${name}` }
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
      <Link href="/vault" className="text-zinc-300 hover:text-white">
        vault
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

function DirectoryView({ rel }: { rel: string }) {
  let entries: VaultEntry[]
  try {
    entries = listDir(rel)
  } catch {
    notFound()
  }

  return (
    <div className="mx-auto max-w-3xl">
      <Breadcrumb rel={rel} />
      <h1 className="mb-1 text-2xl font-semibold text-white">
        {rel === '' ? 'Vault' : rel.split('/').pop()}
      </h1>
      <p className="mb-6 text-sm text-zinc-500">
        Read-only view of the cabinet&apos;s knowledge vault.
      </p>

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
    </div>
  )
}

// ------------------------------------------------------------
// Router
// ------------------------------------------------------------

function EmptyVault() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4 py-12">
      <h1 className="text-2xl font-bold text-white">Vault</h1>
      <p className="text-sm text-zinc-500">
        No vault is configured for this cabinet, so there is nothing to browse
        yet. The org vault is the <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-300">vault/</code>{' '}
        directory in the repository.
      </p>
    </div>
  )
}

export default async function VaultPage({
  params,
}: {
  params: Promise<{ path?: string[] }>
}) {
  const { path: segments } = await params
  // Next has already URL-decoded each route segment. Join to a vault-relative
  // path; the confinement layer rejects any escape.
  const rel = (segments ?? []).join('/')

  if (!hasVault()) {
    if (rel === '') return <EmptyVault />
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
  notFound()
}
