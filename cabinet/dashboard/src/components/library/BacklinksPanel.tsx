/**
 * BacklinksPanel — "Linked from" section under a Library note.
 *
 * Resurrected 2026-07-17 (Captain ruling: the reader returns) from the
 * retired DB-backed panel — now inverted from the FILESYSTEM wikilink graph
 * (lib/vault-graph.ts getBacklinks): notes whose [[wikilinks]] resolve to
 * the current note. Zero DB; every path came through the vault confinement
 * layer. Server component rendered below the note content; links navigate
 * into the Library via vaultHref (always internal /library/... hrefs).
 *
 * "No backlinks yet" stays the honest empty state — many notes have zero
 * inbound links until the linking pattern compounds across the corpus.
 * Fail-closed: if the graph build throws, render nothing.
 */

import Link from 'next/link'
import { getBacklinks, type VaultBacklink } from '@/lib/vault-graph'
import { vaultHref } from '@/lib/vault-wikilinks'

interface Props {
  /** Vault-relative path of the CURRENT note. */
  rel: string
}

export default function BacklinksPanel({ rel }: Props) {
  let backlinks: VaultBacklink[] = []
  try {
    backlinks = getBacklinks(rel)
  } catch (err) {
    console.warn('[library] BacklinksPanel — getBacklinks failed', err)
    return null // fail-closed: don't render anything if the graph errored
  }

  if (backlinks.length === 0) {
    return (
      <section
        aria-label="Backlinks"
        className="rounded-xl border border-zinc-800 bg-zinc-900/30 px-5 py-4"
      >
        <h2 className="text-sm font-medium text-zinc-400">Linked from</h2>
        <p className="mt-2 text-xs text-zinc-600">No backlinks yet.</p>
      </section>
    )
  }

  // Group by top-level vault folder for cleaner reading (the filesystem
  // analog of the old per-Space grouping).
  const grouped = new Map<string, VaultBacklink[]>()
  for (const b of backlinks) {
    const key = b.sourceDir || '(root)'
    const bucket = grouped.get(key)
    if (bucket) bucket.push(b)
    else grouped.set(key, [b])
  }

  return (
    <section
      aria-label="Backlinks"
      className="rounded-xl border border-zinc-800 bg-zinc-900/30 px-5 py-4"
    >
      <h2 className="mb-3 text-sm font-medium text-zinc-400">
        Linked from <span className="text-xs text-zinc-600">({backlinks.length})</span>
      </h2>
      <div className="flex flex-col gap-4">
        {[...grouped.entries()].map(([dir, entries]) => (
          <div key={dir}>
            <div className="mb-1 text-xs uppercase tracking-wide text-zinc-600">{dir}</div>
            <ul className="flex flex-col gap-2">
              {entries.map((b) => (
                <li key={b.sourceRel} className="text-sm">
                  <Link
                    href={vaultHref(b.sourceRel)}
                    className="text-zinc-300 transition-colors hover:text-zinc-100"
                  >
                    {b.sourceTitle}
                  </Link>
                  <p className="mt-0.5 text-xs text-zinc-600">{b.sourceRel}</p>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  )
}
