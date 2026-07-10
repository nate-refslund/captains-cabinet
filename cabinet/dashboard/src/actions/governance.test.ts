/**
 * governance.ts coverage — the MOCK_CONTENT kill (perfect-cabinet Wave B).
 *
 * Pins the contract: reads AND writes are REAL `node:fs` operations against
 * the hardcoded allowlist resolved from the checkout root (Redis optional —
 * no mock-mode branch left on either path), a missing file renders an honest
 * "file not found at <rel>" block (never fabricated content), a save either
 * really changes the bytes on disk or really reports an error (the old
 * docker/mock write transport silently no-op'd without Redis while the
 * action still claimed success), the reader's placeholder blocks are refused
 * by the writer, unknown/hostile keys are refused, and the fabricated mock
 * constitution is gone from the source entirely.
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

import {
  readAllGovernanceFiles,
  readGovernanceFile,
  updateGovernanceFile,
} from './governance'

const FIXTURES: Record<string, string> = {
  'framework/constitution-base.md':
    '# Testburg Constitution\n\nAda Testburg governs by receipts.\n',
  'framework/safety-boundaries-base.md': '# Testburg Safety Boundaries\n',
  'instance/config/role-registry.md': '# Testburg Role Registry\n',
  'CLAUDE.md': '# Testburg Operating Context\n',
}

let root: string

beforeEach(async () => {
  root = await fs.mkdtemp(path.join(os.tmpdir(), 'testburg-root-'))
  for (const [rel, content] of Object.entries(FIXTURES)) {
    const full = path.join(root, rel)
    await fs.mkdir(path.dirname(full), { recursive: true })
    await fs.writeFile(full, content)
  }
  vi.stubEnv('CABINET_ROOT', root)
})

afterEach(async () => {
  vi.unstubAllEnvs()
  await fs.rm(root, { recursive: true, force: true })
})

describe('readGovernanceFile — real reads, always', () => {
  it('returns the real file content for every allowlisted key', async () => {
    expect(await readGovernanceFile('constitution')).toBe(
      FIXTURES['framework/constitution-base.md']
    )
    expect(await readGovernanceFile('safety')).toBe(
      FIXTURES['framework/safety-boundaries-base.md']
    )
    expect(await readGovernanceFile('registry')).toBe(
      FIXTURES['instance/config/role-registry.md']
    )
    expect(await readGovernanceFile('operating_manual')).toBe(
      FIXTURES['CLAUDE.md']
    )
  })

  it('reads real content with NO Redis and NO MOCK_DATA set (mock path dead)', async () => {
    vi.stubEnv('REDIS_URL', '')
    vi.stubEnv('MOCK_DATA', '')
    const content = await readGovernanceFile('constitution')
    expect(content).toContain('Testburg Constitution')
    expect(content).not.toContain("Founder's Cabinet") // the old fabricated text
  })

  it('missing file → honest "file not found at <rel>" block, never fabricated', async () => {
    await fs.rm(path.join(root, 'instance/config/role-registry.md'))
    const content = await readGovernanceFile('registry')
    expect(content).toContain('file not found at `instance/config/role-registry.md`')
    expect(content).toContain('No fabricated fallback')
    // and specifically NOT the old mock registry
    expect(content).not.toContain('Active Officers')
  })

  it('unknown and hostile keys are refused (allowlist is the whole universe)', async () => {
    expect(await readGovernanceFile('nonsense')).toBe('')
    expect(await readGovernanceFile('../CLAUDE.md')).toBe('')
    expect(await readGovernanceFile('__proto__')).toBe('')
    expect(await readGovernanceFile('constructor')).toBe('')
  })
})

describe('readAllGovernanceFiles', () => {
  it('returns exactly the four allowlisted documents', async () => {
    const all = await readAllGovernanceFiles()
    expect(Object.keys(all).sort()).toEqual(
      ['constitution', 'operating_manual', 'registry', 'safety'].sort()
    )
    expect(all.constitution).toContain('Testburg Constitution')
  })
})

describe('updateGovernanceFile — real writes, same allowlist guard', () => {
  it('refuses unknown and prototype-chain keys', async () => {
    expect(await updateGovernanceFile('nonsense', 'x')).toEqual({
      success: false,
      error: 'Invalid document',
    })
    expect(await updateGovernanceFile('__proto__', 'x')).toEqual({
      success: false,
      error: 'Invalid document',
    })
  })

  it('success means the bytes really changed — with NO Redis and NO MOCK_DATA', async () => {
    // The exact fresh-hatch setup: the old docker/mock transport no-op'd
    // here while still reporting success, so the save silently vanished.
    vi.stubEnv('REDIS_URL', '')
    vi.stubEnv('MOCK_DATA', '')
    const next = '# Testburg Constitution v2\n\nAda Testburg amended it.\n'
    expect(await updateGovernanceFile('constitution', next)).toEqual({
      success: true,
    })
    expect(
      await fs.readFile(path.join(root, 'framework/constitution-base.md'), 'utf8')
    ).toBe(next)
    // Round-trip through the reader too — the page re-render shows the edit.
    expect(await readGovernanceFile('constitution')).toBe(next)
  })

  it('refuses to persist the reader\'s "file not found" placeholder', async () => {
    await fs.rm(path.join(root, 'instance/config/role-registry.md'))
    const placeholder = await readGovernanceFile('registry')
    expect(placeholder).toContain('file not found at')
    const result = await updateGovernanceFile('registry', placeholder)
    expect(result.success).toBe(false)
    expect(result.error).toContain('placeholder')
    // …and it did NOT materialize the error message as a document.
    await expect(
      fs.access(path.join(root, 'instance/config/role-registry.md'))
    ).rejects.toThrow()
  })

  it('refuses the "could not read" placeholder too (leading whitespace tolerated)', async () => {
    const block = '\n  > **could not read `CLAUDE.md`** — some transient error.'
    const result = await updateGovernanceFile('operating_manual', block)
    expect(result.success).toBe(false)
    expect(await readGovernanceFile('operating_manual')).toBe(FIXTURES['CLAUDE.md'])
  })

  it('restores a genuinely missing document when given REAL content', async () => {
    // Even the parent dir is gone — the writer recreates the fixed
    // allowlisted path, so the editor can restore a lost document.
    await fs.rm(path.join(root, 'instance'), { recursive: true, force: true })
    const restored = '# Testburg Role Registry (restored)\n'
    expect(await updateGovernanceFile('registry', restored)).toEqual({
      success: true,
    })
    expect(await readGovernanceFile('registry')).toBe(restored)
  })

  it('reports an honest error when the write genuinely fails', async () => {
    // A directory squatting on the file path makes writeFile fail (EISDIR).
    await fs.rm(path.join(root, 'CLAUDE.md'))
    await fs.mkdir(path.join(root, 'CLAUDE.md'))
    const result = await updateGovernanceFile('operating_manual', '# nope')
    expect(result.success).toBe(false)
    expect(result.error).toBeTruthy()
  })
})

describe('the fabricated mock is dead in the source', () => {
  it('governance.ts contains no MOCK_CONTENT and no mock-mode branch on either path', () => {
    const source = readFileSync(path.join(__dirname, 'governance.ts'), 'utf8')
    expect(source).not.toContain('MOCK_CONTENT')
    expect(source).not.toMatch(/IS_MOCK/)
    expect(source).not.toContain("Founder's Cabinet exists to serve")
    expect(source).not.toMatch(/dockerReadFile/) // reads are direct fs, not shell
    expect(source).not.toMatch(/dockerWriteFile/) // writes too — the mock
    expect(source).not.toContain('@/lib/docker') // transport no-op'd silently
  })
})
