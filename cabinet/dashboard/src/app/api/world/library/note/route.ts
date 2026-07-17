/**
 * GET /api/world/library/note — a single vault note for the world Library
 * card, prepared by the EXACT /library reader pipeline: confined read
 * (lib/vault readNote — realpath-under-root, deny → generic 404) +
 * internal-only wikilink rewrite (lib/vault-wikilinks rewriteWikilinks over
 * the confined basename index; hrefs resolve to /library/…). The body ships as MARKDOWN — rendering happens only in
 * the card through the existing sanitizing VaultMarkdown renderer (no raw
 * HTML anywhere on this path).
 *
 * READ-ONLY, DB-free; GET only (world ratchet #2); auth gate cloned from
 * the sibling world routes (ratchet #7).
 */
import { NextRequest, NextResponse } from 'next/server'
import { cookies } from 'next/headers'
import {
  buildBasenameIndex,
  hasVault,
  readNote,
  resolveNoteTarget,
  VaultPathError,
} from '@/lib/vault'
import { rewriteWikilinks } from '@/lib/vault-wikilinks'
import type { WorldLibraryNotePayload } from '@/lib/world/library-panel'

export const dynamic = 'force-dynamic'

const NOT_FOUND = { error: 'not found' } as const

export async function GET(req: NextRequest) {
  const cookieStore = await cookies()
  if (!cookieStore.get('cabinet_session')?.value) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const rel = req.nextUrl.searchParams.get('path') ?? ''
  if (!hasVault() || !rel) {
    return NextResponse.json(NOT_FOUND, { status: 404 })
  }

  try {
    const note = readNote(rel)
    const index = buildBasenameIndex()
    const processed = rewriteWikilinks(note.body, (target) =>
      resolveNoteTarget(target, index)
    )
    const title =
      (typeof note.frontmatter?.title === 'string' && note.frontmatter.title) ||
      note.relPath.split('/').pop()?.replace(/\.(md|markdown)$/i, '') ||
      'Note'
    return NextResponse.json({
      relPath: note.relPath,
      title,
      frontmatter: note.frontmatter,
      markdown: processed,
    } satisfies WorldLibraryNotePayload)
  } catch (err) {
    if (err instanceof VaultPathError) {
      return NextResponse.json(NOT_FOUND, { status: 404 })
    }
    return NextResponse.json(NOT_FOUND, { status: 404 })
  }
}
