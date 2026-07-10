'use server'

/**
 * files.ts — save the per-officer editable files (role definition + loop
 * prompt) from the officer pages.
 *
 * Writes are REAL `node:fs` operations (perfect-cabinet Wave B — the same
 * silent-success kill as governance.ts): these actions used to route through
 * the docker/mock shell transport, which console-log NO-OP'd whenever Redis
 * was unconfigured (MOCK_DATA=true or no REDIS_URL) while the action still
 * returned `{success: true}` and revalidated — on a fresh hatch a Captain's
 * role-definition/loop-prompt save vanished without a trace. A save now
 * either really changes bytes on disk or really returns
 * `{success: false, error}`.
 *
 * Path safety: the role id is allowlisted to /^[a-z]{2,4}$/ (no separators,
 * no dots — nothing traversal-shaped can pass) and interpolated into two
 * FIXED checkout-relative directories resolved per call (cabinet-root
 * doctrine: the env var is honored per call). No user-supplied path fragment
 * ever reaches the filesystem.
 */

import { promises as fs } from 'node:fs'
import path from 'node:path'
import { cabinetPath } from '@/lib/cabinet-root'
import { revalidatePath } from 'next/cache'

const ROLE_RE = /^[a-z]{2,4}$/

async function writeRoleFile(relDir: string, fileName: string, content: string) {
  // The mkdir only ever creates the fixed directory itself (both are
  // checkout-owned paths), so a save works even on a checkout that has not
  // materialized the directory yet.
  const abs = cabinetPath(relDir, fileName)
  await fs.mkdir(path.dirname(abs), { recursive: true })
  await fs.writeFile(abs, content, 'utf8')
}

export async function updateRoleDefinition(role: string, content: string) {
  try {
    if (!ROLE_RE.test(role)) {
      return { success: false, error: 'Invalid role identifier' }
    }
    await writeRoleFile('.claude/agents', `${role}.md`, content)
    revalidatePath(`/officers/${role}`)
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to update role definition',
    }
  }
}

export async function updateLoopPrompt(role: string, content: string) {
  try {
    if (!ROLE_RE.test(role)) {
      return { success: false, error: 'Invalid role identifier' }
    }
    await writeRoleFile('cabinet/loop-prompts', `${role}.txt`, content)
    revalidatePath(`/officers/${role}`)
    return { success: true }
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Failed to update loop prompt',
    }
  }
}
