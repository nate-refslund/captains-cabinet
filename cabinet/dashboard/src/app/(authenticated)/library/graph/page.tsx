/**
 * /library/graph — the Library's [[wikilink]] graph (Captain ruling
 * 2026-07-17: the reader returned; same address as the pre-retirement Spec
 * 045 graph). The retired DB-backed graph stays retired — this one is built
 * on lib/vault-graph.ts: a confined FILESYSTEM walk + the wikilink resolver,
 * zero database, zero API routes. The server component computes the data and
 * hands it to the client canvas as serialized props.
 *
 * Routing note: this static segment takes precedence over the
 * /library/[[...path]] catch-all, so a top-level vault entry literally named
 * `graph` would be shadowed here (none exists; deeper paths like
 * /library/graph/x.md still reach the browser).
 */

import GraphCanvas from '@/components/library/GraphCanvas'
import LibraryTabs from '@/components/library/LibraryTabs'
import { hasVault } from '@/lib/vault'
import { buildVaultGraph, type VaultGraphData } from '@/lib/vault-graph'

export const dynamic = 'force-dynamic'
export const metadata = { title: 'Library · graph' }

export default async function LibraryGraphPage() {
  const data: VaultGraphData = hasVault()
    ? buildVaultGraph()
    : { nodes: [], edges: [], truncated: false }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <LibraryTabs active="graph" />
        <h1 className="text-2xl font-bold text-white">Library graph</h1>
        <p className="mt-1 text-sm text-zinc-500">
          [[wikilink]] network across the vault. Click a node to open the note.
          Filter by top-level folder using the chips; toggle labels to
          declutter dense areas.
        </p>
      </div>
      <GraphCanvas data={data} />
    </div>
  )
}
