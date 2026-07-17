/**
 * /library — retirement notice (Library retirement, 2026-07-16,
 * Captain-ratified; closes memory-study Q4/C7).
 *
 * The Library's editable Spaces/Records UI is retired. Content was exported
 * to the vault archive (cabinet/scripts/retire-library-export.py) and every
 * record write is mirrored into cabinet_memory, so memory_search finds it.
 * The route stays as a read-only notice so nav links and bookmarks land
 * somewhere honest instead of a 404. No DB access on this page.
 *
 * Full story: docs/runbooks/library-retirement-2026-07-16.md
 */

import Link from 'next/link'

export const dynamic = 'force-static'

export default function LibraryRetiredPage() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 py-12">
      <div>
        <h1 className="text-2xl font-bold text-white">Library — retired</h1>
        <p className="mt-1 text-sm text-zinc-500">
          The Library was retired on 2026-07-16 (Captain-ratified). Nothing was
          deleted — the content moved home to the vault.
        </p>
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
        <h2 className="text-sm font-semibold text-zinc-300">
          Where the records live now
        </h2>
        <ul className="mt-3 flex list-disc flex-col gap-2 pl-5 text-sm text-zinc-500">
          <li>
            Vault archive:{' '}
            <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-300">
              vault/library-archive/
            </code>{' '}
            — one markdown note per record, with provenance frontmatter.
          </li>
          <li>
            Search: every record is mirrored into cabinet memory — use{' '}
            <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-300">
              memory_search
            </code>{' '}
            (cross-system search) instead of the old Library search.
          </li>
          <li>
            Database tables remain in place, dormant — no data was dropped.
          </li>
          <li>
            Browse the vault:{' '}
            <Link href="/vault" className="text-blue-300 underline hover:text-blue-200">
              open the read-only vault browser
            </Link>{' '}
            to read the markdown corpus (including{' '}
            <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-xs text-zinc-300">
              vault/library-archive/
            </code>
            ) note-by-note in your browser.
          </li>
        </ul>
        <p className="mt-4 text-xs text-zinc-600">
          Runbook:{' '}
          <code className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">
            docs/runbooks/library-retirement-2026-07-16.md
          </code>
        </p>
      </div>
    </div>
  )
}
