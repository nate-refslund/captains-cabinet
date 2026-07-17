/**
 * Library layout — passthrough. Since the Captain's 2026-07-17 naming ruling
 * the Library IS the read-only vault reader (/library/[[...path]] browser +
 * /library/graph); each page carries its own container and all data flows
 * through lib/vault.ts / lib/vault-graph.ts (filesystem, confined, DB-free),
 * so the layout fetches nothing. The pre-retirement Spec 037 sidebar stays
 * gone — the editable STORE is retired (2026-07-16); only the reader
 * returned.
 */

import type { ReactNode } from 'react'

export default function LibraryLayout({
  children,
}: {
  children: ReactNode
}) {
  return <>{children}</>
}
