'use client'

/**
 * LibrarySearchBox — consumer-card search (Card 4).
 *
 * Since 2026-07-17 this is a thin wrapper around the shared LibrarySearch
 * component (GET /api/library/search — the cabinet_memory org-knowledge
 * search; see @/lib/memory-search). One engine, one renderer: snippets are
 * escaped React text, vault hits link into the Library reader (/library —
 * see VAULT_NOTE_BASE in LibrarySearch.tsx), other hits show a source badge.
 * The old POST /api/library/search arm (retired library_records ILIKE) is
 * no longer called from here.
 */

import LibrarySearch from '@/components/library/LibrarySearch'

export default function LibrarySearchBox() {
  return <LibrarySearch limit={5} placeholder="Search your cabinet..." />
}
