'use server'

/**
 * governance.ts — read/write the four governance documents.
 *
 * The fabricated mock-constitution fallback is DEAD (perfect-cabinet Wave B):
 * a fresh hatch used to see an invented constitution exactly when it mattered
 * most (no Redis configured ⇒ mock mode). Reads AND writes are now REAL
 * `node:fs` operations, always — the documents live in the checkout, so Redis
 * stays optional for this page. A genuinely missing file renders an honest
 * "file not found" block, never invented content. Writes used to route
 * through the docker/mock shell transport, which silently NO-OP'd whenever
 * Redis was unconfigured while the action still reported success — on a
 * fresh hatch a Captain's save vanished without a trace. A save now either
 * really writes the file or really returns an error.
 *
 * Path safety: `GOVERNANCE_FILES` is a hardcoded allowlist of repo-relative
 * paths — the WHOLE universe this module can touch. Keys are checked with an
 * own-property guard (a hostile key like `__proto__` must never resolve
 * through the prototype chain), paths resolve against the checkout root per
 * call (cabinet-root doctrine: the env var is honored per call), and no
 * user-supplied path fragment ever reaches the filesystem.
 */

import { promises as fs } from 'node:fs'
import path from 'node:path'
import { cabinetPath } from '@/lib/cabinet-root'
import { revalidatePath } from 'next/cache'

const GOVERNANCE_FILES: Record<string, string> = {
  constitution: 'framework/constitution-base.md',
  safety: 'framework/safety-boundaries-base.md',
  registry: 'instance/config/role-registry.md',
  operating_manual: 'CLAUDE.md',
}

// Heads of the two honest failure blocks readGovernanceFile can render IN
// PLACE of content. The editor loads whatever the read returns, so a Captain
// hitting Save on an untouched placeholder would otherwise persist an error
// message as a governance document — updateGovernanceFile refuses content
// that begins with either. Built here and interpolated below so the guard
// and the renderer can never drift apart.
const MISS_BLOCK_HEAD = '> **file not found at `'
const READ_ERROR_BLOCK_HEAD = '> **could not read `'

/** The allowlisted relative path for a key, or null — never a prototype hit. */
function allowlistedPath(fileKey: string): string | null {
  return Object.prototype.hasOwnProperty.call(GOVERNANCE_FILES, fileKey)
    ? GOVERNANCE_FILES[fileKey]
    : null
}

export async function updateGovernanceFile(fileKey: string, content: string) {
  const rel = allowlistedPath(fileKey)
  if (!rel) return { success: false, error: 'Invalid document' }

  const head = content.trimStart()
  if (head.startsWith(MISS_BLOCK_HEAD) || head.startsWith(READ_ERROR_BLOCK_HEAD)) {
    return {
      success: false,
      error:
        'refusing to save: this is the "file not found / could not read" ' +
        'placeholder the reader rendered, not document content — replace it ' +
        'with the real document before saving',
    }
  }

  try {
    // Real write, mirroring the real-read contract below — never the docker/
    // mock shell transport (which no-op'd without Redis yet reported success).
    // The mkdir only ever creates the fixed allowlisted path's parents, so a
    // Captain can restore a genuinely missing document from the editor.
    const abs = cabinetPath(rel)
    await fs.mkdir(path.dirname(abs), { recursive: true })
    await fs.writeFile(abs, content, 'utf8')
    revalidatePath('/governance')
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to save',
    }
  }
}

export async function readGovernanceFile(fileKey: string): Promise<string> {
  const rel = allowlistedPath(fileKey)
  if (!rel) return ''

  try {
    return await fs.readFile(cabinetPath(rel), 'utf8')
  } catch (err) {
    const code = (err as NodeJS.ErrnoException).code
    if (code === 'ENOENT' || code === 'ENOTDIR') {
      // HONEST MISS — the block says exactly what is absent and where;
      // fabricating a constitution here is what Wave B killed.
      return (
        `${MISS_BLOCK_HEAD}${rel}\`** — this checkout has no such ` +
        `document, so there is nothing to show. (No fabricated fallback: ` +
        `if you expected content here, restore the file in the repo.)`
      )
    }
    return (
      `${READ_ERROR_BLOCK_HEAD}${rel}\`** — ` +
      `${err instanceof Error ? err.message : 'unknown read error'}. ` +
      `(Real read failed; nothing is fabricated in its place.)`
    )
  }
}

export async function readAllGovernanceFiles(): Promise<Record<string, string>> {
  const entries = Object.keys(GOVERNANCE_FILES)
  const results: Record<string, string> = {}

  for (const key of entries) {
    results[key] = await readGovernanceFile(key)
  }

  return results
}
