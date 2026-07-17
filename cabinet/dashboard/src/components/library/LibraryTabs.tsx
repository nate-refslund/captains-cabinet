/**
 * LibraryTabs — Browse | Graph tab strip on the Library root surfaces
 * (Captain ruling 2026-07-17: the reader + graph returned; the graph tab
 * sits at its pre-retirement address /library/graph). Pure presentational
 * server component: two internal links, no data, no client JS.
 */

import Link from 'next/link'

export default function LibraryTabs({ active }: { active: 'browse' | 'graph' }) {
  const tabs: Array<{ href: string; label: string; key: 'browse' | 'graph' }> = [
    { href: '/library', label: 'Browse', key: 'browse' },
    { href: '/library/graph', label: 'Graph', key: 'graph' },
  ]
  return (
    <div className="mb-4 flex items-center gap-1 border-b border-zinc-800 pb-3">
      {tabs.map((t) =>
        t.key === active ? (
          <span
            key={t.key}
            aria-current="page"
            className="rounded-md bg-zinc-800 px-3 py-1 text-sm font-medium text-white"
          >
            {t.label}
          </span>
        ) : (
          <Link
            key={t.key}
            href={t.href}
            className="rounded-md px-3 py-1 text-sm text-zinc-400 hover:bg-zinc-900 hover:text-white"
          >
            {t.label}
          </Link>
        )
      )}
    </div>
  )
}
