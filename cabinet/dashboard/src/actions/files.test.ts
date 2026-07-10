/**
 * files.ts coverage — the silent-success write kill (perfect-cabinet Wave B,
 * integrator follow-up to the identical governance.ts fix).
 *
 * Pins the contract: role-definition and loop-prompt saves are REAL
 * `node:fs` writes against the two fixed checkout-relative directories
 * (Redis optional — the old docker/mock transport, which console-log
 * no-op'd without REDIS_URL while the action still claimed success, is gone
 * from the source entirely), the role id allowlist refuses anything
 * traversal-shaped, and a genuine write failure returns an honest error.
 *
 * Fixtures are synthetic Testburg content in a mkdtemp CABINET_ROOT —
 * cabinet-root resolves the env per call, so stubbing per test is enough.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { promises as fs, readFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

// Keep the module import hermetic: revalidatePath needs a Next request
// context, which vitest does not provide.
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))

import { updateLoopPrompt, updateRoleDefinition } from './files'

let root: string

beforeEach(async () => {
  root = await fs.mkdtemp(path.join(os.tmpdir(), 'testburg-files-'))
  vi.stubEnv('CABINET_ROOT', root)
  // The write path must be real exactly when the old transport would have
  // silently swallowed the save: no Redis, no MOCK_DATA.
  vi.stubEnv('REDIS_URL', '')
  vi.stubEnv('MOCK_DATA', '')
})

afterEach(async () => {
  vi.unstubAllEnvs()
  await fs.rm(root, { recursive: true, force: true })
})

describe('updateRoleDefinition — real writes, honest failures', () => {
  it('success means the bytes really changed on disk (no Redis configured)', async () => {
    const res = await updateRoleDefinition('cos', '# Testburg CoS\n')
    expect(res).toEqual({ success: true })
    expect(
      await fs.readFile(path.join(root, '.claude/agents/cos.md'), 'utf8')
    ).toBe('# Testburg CoS\n')
  })

  it('creates the fixed directory when the checkout has not materialized it', async () => {
    // mkdtemp root has no .claude/agents — the writer creates exactly it.
    const res = await updateRoleDefinition('cto', '# Testburg CTO\n')
    expect(res.success).toBe(true)
    expect(
      await fs.readFile(path.join(root, '.claude/agents/cto.md'), 'utf8')
    ).toBe('# Testburg CTO\n')
  })

  it('refuses role ids that are not 2-4 lowercase letters — nothing traversal-shaped', async () => {
    for (const bad of ['../x', 'a', 'toolong', 'CoS', 'c.s', 'a/b', '']) {
      const res = await updateRoleDefinition(bad, 'x')
      expect(res.success).toBe(false)
    }
    // Nothing was written anywhere under the root.
    await expect(fs.readdir(path.join(root, '.claude'))).rejects.toMatchObject({
      code: 'ENOENT',
    })
  })

  it('a genuine write failure returns an honest error (directory squatting the file path)', async () => {
    await fs.mkdir(path.join(root, '.claude/agents/coo.md'), { recursive: true })
    const res = await updateRoleDefinition('coo', '# blocked\n')
    expect(res.success).toBe(false)
    expect(res.error).toBeTruthy()
  })
})

describe('updateLoopPrompt — same contract, loop-prompts dir', () => {
  it('success means the bytes really changed on disk', async () => {
    const res = await updateLoopPrompt('cro', 'Ship the Testburg newsletter.\n')
    expect(res).toEqual({ success: true })
    expect(
      await fs.readFile(path.join(root, 'cabinet/loop-prompts/cro.txt'), 'utf8')
    ).toBe('Ship the Testburg newsletter.\n')
  })

  it('refuses invalid role ids', async () => {
    const res = await updateLoopPrompt('../../etc', 'x')
    expect(res.success).toBe(false)
  })
})

describe('source pin — the silent no-op transport is gone', () => {
  it('files.ts contains no dockerWriteFile and no @/lib/docker import', () => {
    const src = readFileSync(path.join(__dirname, 'files.ts'), 'utf8')
    expect(src).not.toContain('dockerWriteFile')
    expect(src).not.toContain("@/lib/docker")
  })
})
