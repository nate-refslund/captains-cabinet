// active-context.ts — shared preset-aware context resolver (config-split fix
// 2026-07-17). Chain under test (dashboard has no officer rung):
//
//   env CABINET_CONTEXT > instance/config/active-project.txt >
//   single-declared-lane (contexts/*.yml `slug:` scan) >
//   lane_default (platform.yml, else product.yml — top-level or
//   product:-nested), only when it IS a declared lane.
//
// Also under test: the slug shape gate ([a-z0-9][a-z0-9-]{0,31}) — untrusted
// env/file values that don't conform SKIP their rung (data, never emitted) —
// and the fail-LOUD remedy of resolveActiveContext(). Twin parity with
// lanes.sh cabinet_resolve_context / framework.env.active_context is pinned
// bash↔python in cabinet/scripts/lib/tests/test_resolve_context_sh.py; this
// suite pins the TS side over mocked fs.

import path from 'node:path'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const { mockReadFile, mockReaddir } = vi.hoisted(() => ({
  mockReadFile: vi.fn(),
  mockReaddir: vi.fn(),
}))

vi.mock('node:fs/promises', () => ({
  readFile: mockReadFile,
  readdir: mockReaddir,
}))

import { resolveActiveContext, resolveActiveContextOrNull } from './active-context'

const ROOT = '/fx'
const ACTIVE = path.join(ROOT, 'instance/config/active-project.txt')
const CONTEXTS = path.join(ROOT, 'instance/config/contexts')
const PLATFORM = path.join(ROOT, 'instance/config/platform.yml')
const PRODUCT = path.join(ROOT, 'instance/config/product.yml')

/** Wire the fs mocks from a declarative fixture. */
function seed(fx: {
  activeProject?: string
  contexts?: Record<string, string>
  platformYml?: string
  productYml?: string
}) {
  mockReaddir.mockImplementation(async (dir: string) => {
    if (dir === CONTEXTS && fx.contexts) return Object.keys(fx.contexts)
    throw new Error(`ENOENT: ${dir}`)
  })
  mockReadFile.mockImplementation(async (p: string) => {
    if (p === ACTIVE && fx.activeProject !== undefined) return fx.activeProject
    if (fx.contexts) {
      for (const [name, body] of Object.entries(fx.contexts)) {
        if (p === path.join(CONTEXTS, name)) return body
      }
    }
    if (p === PLATFORM && fx.platformYml !== undefined) return fx.platformYml
    if (p === PRODUCT && fx.productYml !== undefined) return fx.productYml
    throw new Error(`ENOENT: ${p}`)
  })
}

beforeEach(() => {
  mockReadFile.mockReset()
  mockReaddir.mockReset()
  process.env.CABINET_ROOT = ROOT
  delete process.env.CABINET_CONTEXT
})

afterEach(() => {
  delete process.env.CABINET_ROOT
  delete process.env.CABINET_CONTEXT
})

describe('resolveActiveContextOrNull — rung order', () => {
  it('env wins over everything (no fs touched)', async () => {
    process.env.CABINET_CONTEXT = 'testburg-hq'
    seed({ activeProject: 'bakery\n' })
    expect(await resolveActiveContextOrNull()).toBe('testburg-hq')
    expect(mockReadFile).not.toHaveBeenCalled()
    expect(mockReaddir).not.toHaveBeenCalled()
  })

  it('malformed env value skips its rung (data, never emitted)', async () => {
    process.env.CABINET_CONTEXT = 'evil;$(rm -rf .)'
    seed({ activeProject: 'bakery\n' })
    expect(await resolveActiveContextOrNull()).toBe('bakery')
  })

  it('active-project.txt wins over lanes, whitespace-stripped', async () => {
    seed({
      activeProject: '  newsletter \n',
      contexts: { 'bakery.yml': 'slug: bakery\n' },
    })
    expect(await resolveActiveContextOrNull()).toBe('newsletter')
    expect(mockReaddir).not.toHaveBeenCalled()
  })

  it('traversal-shaped file content skips its rung', async () => {
    seed({
      activeProject: '../../etc/passwd\n',
      contexts: { 'bakery.yml': 'slug: bakery\n', '_default.yml': '# no slug\n' },
    })
    expect(await resolveActiveContextOrNull()).toBe('bakery') // single lane
  })

  it('single declared lane resolves (portfolio-of-one / fresh hatch)', async () => {
    seed({
      contexts: {
        'bakery.yml': 'slug: bakery\nactive: false\n', // active-flag trap: still counts
        '_default.yml': '# defaults only — no slug\n',
      },
    })
    expect(await resolveActiveContextOrNull()).toBe('bakery')
  })

  it('quoted mixed-case slug is stripped + lowercased (lanes.sh parity)', async () => {
    seed({ contexts: { 'market.yml': 'slug: "Testburg-Market"\n' } })
    expect(await resolveActiveContextOrNull()).toBe('testburg-market')
  })

  it('multi-lane needs a declared lane_default', async () => {
    seed({
      contexts: {
        'bakery.yml': 'slug: bakery\n',
        'newsletter.yml': 'slug: newsletter\n',
      },
      platformYml: 'captain_name: Testburg\nlane_default: newsletter\n',
    })
    expect(await resolveActiveContextOrNull()).toBe('newsletter')
  })

  it('an UNdeclared lane_default is refused → null', async () => {
    seed({
      contexts: {
        'bakery.yml': 'slug: bakery\n',
        'newsletter.yml': 'slug: newsletter\n',
      },
      platformYml: 'lane_default: ghost-lane\n',
    })
    expect(await resolveActiveContextOrNull()).toBeNull()
  })

  it('product.yml nested lane_default is honored when platform.yml absent', async () => {
    seed({
      contexts: {
        'bakery.yml': 'slug: bakery\n',
        'newsletter.yml': 'slug: newsletter\n',
      },
      productYml: 'product:\n  name: Testburg\n  lane_default: bakery\n',
    })
    expect(await resolveActiveContextOrNull()).toBe('bakery')
  })

  it('no rung resolves → null (empty deployment)', async () => {
    seed({})
    expect(await resolveActiveContextOrNull()).toBeNull()
  })

  it('unreadable individual context file is skipped, the rest count', async () => {
    seed({
      contexts: {
        'bakery.yml': 'slug: bakery\n',
        'broken.yml': 'slug: broken\n',
      },
    })
    const base = mockReadFile.getMockImplementation()!
    mockReadFile.mockImplementation(async (p: string) => {
      if (p === path.join(CONTEXTS, 'broken.yml')) throw new Error('EACCES')
      return base(p)
    })
    expect(await resolveActiveContextOrNull()).toBe('bakery')
  })
})

describe('resolveActiveContext — fail-LOUD contract', () => {
  it('throws the remedy one-liner naming every rung', async () => {
    seed({})
    await expect(resolveActiveContext()).rejects.toThrow(/CABINET_CONTEXT/)
    await expect(resolveActiveContext()).rejects.toThrow(/active-project\.txt/)
    await expect(resolveActiveContext()).rejects.toThrow(/contexts\/<lane>\.yml/)
    await expect(resolveActiveContext()).rejects.toThrow(/lane_default/)
  })

  it('never invents a default (negative control)', async () => {
    seed({
      contexts: {
        'bakery.yml': 'slug: bakery\n',
        'newsletter.yml': 'slug: newsletter\n',
      },
    })
    await expect(resolveActiveContext()).rejects.toThrow()
  })
})
