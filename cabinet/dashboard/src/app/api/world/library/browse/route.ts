/**
 * GET /api/world/library/browse — the world Library card's directory feed.
 *
 * READ-ONLY window onto the org vault for the Cabinet World's Library
 * building (spec v2 §5.2 Memory Library; §9.3 fresh ruling: the library
 * stays read-only — browse/read/search only, never a write).
 *
 * Every path resolves EXCLUSIVELY through lib/vault's confined resolvers
 * (realpath-under-root; NUL / absolute / ../ traversal / symlink escape all
 * deny). ANY denial → the same generic 404 body as a genuine miss, so path
 * existence never leaks through this route. No fs calls of our own, no DB
 * (the retired Library store stays retired), no writes.
 *
 * GET only — the world never grows a write path (CI ratchet #2); auth gate
 * cloned from the sibling world routes (ratchet #7).
 */
import { NextRequest, NextResponse } from 'next/server'
import { cookies } from 'next/headers'
import { hasVault, listDir, VaultPathError } from '@/lib/vault'
import type { WorldLibraryBrowsePayload } from '@/lib/world/library-panel'

export const dynamic = 'force-dynamic'

const NOT_FOUND = { error: 'not found' } as const

export async function GET(req: NextRequest) {
  const cookieStore = await cookies()
  if (!cookieStore.get('cabinet_session')?.value) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const rel = req.nextUrl.searchParams.get('path') ?? ''

  if (!hasVault()) {
    return NextResponse.json({
      vaultConfigured: false,
      relPath: '',
      entries: [],
    } satisfies WorldLibraryBrowsePayload)
  }

  try {
    const entries = listDir(rel).map((e) => ({
      name: e.name,
      relPath: e.relPath,
      kind: e.kind,
    }))
    return NextResponse.json({
      vaultConfigured: true,
      relPath: rel.replace(/\/+$/, ''),
      entries,
    } satisfies WorldLibraryBrowsePayload)
  } catch (err) {
    if (err instanceof VaultPathError) {
      return NextResponse.json(NOT_FOUND, { status: 404 })
    }
    // Unexpected fs failure: same opaque 404 — never a stack, never a hint.
    return NextResponse.json(NOT_FOUND, { status: 404 })
  }
}
