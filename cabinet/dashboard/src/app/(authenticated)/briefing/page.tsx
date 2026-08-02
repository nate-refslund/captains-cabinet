/**
 * /briefing — the FIRST BRIEFING, in the browser.
 *
 * The hatch's first receipt (`instance/memory/first-briefing-<UTC date>.md`)
 * and the genesis research brief
 * (`instance/memory/library/genesis-research-brief.md`) were, until this page,
 * readable only by opening a file in a terminal. The hatch now ends in a
 * browser, so the two documents it writes have to be readable there.
 *
 * READ-ONLY server component. Every read goes through lib/briefing.ts's
 * confinement layer, rooted at `instance/memory` — NOT at the Library's
 * `org_vault_dir()` root, which stays exactly where it is. Absent files render
 * an honest empty state (a fresh checkout that has not hatched is not an
 * error); a refused path renders identically, so nothing about the filesystem
 * leaks through this page.
 *
 * Lives under (authenticated), so the edge middleware's cabinet_session gate
 * covers it for free (unauth → 307 /login) — the house pattern, no re-check
 * in the page.
 */

import Link from 'next/link'
import VaultMarkdown from '@/components/vault/VaultMarkdown'
import {
  hasBriefingRoot,
  latestFirstBriefing,
  researchBrief,
  MEMORY_DIR_REL,
  RESEARCH_BRIEF_REL,
  type BriefingDoc,
} from '@/lib/briefing'

export const dynamic = 'force-dynamic'

export const metadata = {
  title: 'First briefing · Cabinet',
}

function writtenAt(doc: BriefingDoc): string {
  try {
    return new Date(doc.mtimeMs).toISOString().replace('T', ' ').slice(0, 16) + ' UTC'
  } catch {
    return 'unknown'
  }
}

/** The honest empty: say which file is missing and the one command that
 *  writes it. Never a stack trace, never a 500 — a cabinet that has not
 *  hatched yet has nothing to show, and that is a true answer. */
function Missing({ what, where, how }: { what: string; where: string; how: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-sm">
      <p className="text-zinc-300">No {what} has been written yet.</p>
      <p className="mt-2 text-zinc-500">
        It lands at{' '}
        <code className="rounded bg-zinc-800 px-1 py-0.5 text-zinc-300">{where}</code> when the
        hatch runs.
      </p>
      <p className="mt-2 text-zinc-500">
        Write it now: <code className="rounded bg-zinc-800 px-1 py-0.5 text-zinc-300">{how}</code>
      </p>
    </div>
  )
}

function Doc({ doc }: { doc: BriefingDoc }) {
  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-5">
      <p className="mb-4 text-xs text-zinc-500">
        <code className="rounded bg-zinc-800 px-1 py-0.5 text-zinc-400">
          {MEMORY_DIR_REL}/{doc.relPath}
        </code>
        <span className="mx-2 text-zinc-700">·</span>
        written {writtenAt(doc)}
      </p>
      <VaultMarkdown markdown={doc.body} />
    </article>
  )
}

export default function BriefingPage() {
  const rooted = hasBriefingRoot()
  const briefing = rooted ? latestFirstBriefing() : null
  const brief = rooted ? researchBrief() : null

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <p className="text-sm font-medium text-purple-300">The first receipt</p>
        <h1 className="mt-1 text-3xl font-bold text-white">Your first briefing</h1>
        <p className="mt-2 max-w-2xl text-zinc-400">
          What your Cabinet proposed to do first, and what it went and read before proposing it.
          Both were written by the hatch. Nothing here can be edited from this page.
        </p>
      </div>

      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-zinc-200">Briefing</h2>
        {briefing ? (
          <Doc doc={briefing} />
        ) : (
          <Missing
            what="briefing"
            where={`${MEMORY_DIR_REL}/first-briefing-<date>.md`}
            how="bash cabinet/scripts/first-briefing.sh --local"
          />
        )}
      </section>

      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-zinc-200">Research brief</h2>
        {brief ? (
          <Doc doc={brief} />
        ) : (
          <Missing
            what="research brief"
            where={`${MEMORY_DIR_REL}/${RESEARCH_BRIEF_REL}`}
            how="bash cabinet/scripts/first-briefing.sh --local"
          />
        )}
      </section>

      <p className="text-sm text-zinc-500">
        Next:{' '}
        <Link href="/onboarding" className="text-purple-300 hover:text-purple-200">
          Orientation
        </Link>{' '}
        — point it at one folder and earn the first responsibility.
      </p>
    </div>
  )
}
