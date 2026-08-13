/**
 * The connector catalog projection — the seam between a DATA pack and the UI.
 *
 * WHAT THESE ARE POINTED AT. The pack is meant to grow to hundreds of entries by
 * editing one YAML file, with no code change and therefore no code review. That
 * makes this projection the only place a malformed entry can be caught before it
 * reaches an operator, so the arms below are about DEGENERATE packs as much as
 * good ones: an entry with no id, a category nobody declared, a `fields` list
 * that is not a list, a file that does not parse at all. Every one of those must
 * leave the rest of the catalog usable, because the alternative — onboarding
 * failing because a tool nobody asked for is malformed — is strictly worse.
 *
 * The auth guard is pinned too: this reads a file off the cabinet root, so an
 * unauthenticated call must never reach the filesystem.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import nodePath from 'node:path'

const { mockAuth } = vi.hoisted(() => ({ mockAuth: vi.fn<() => Promise<boolean>>() }))
vi.mock('@/lib/provisioning/guard', () => ({ requireDashboardAuth: mockAuth }))
vi.mock('@/lib/cabinet-root', () => ({ cabinetPath: (p: string) => `/nonexistent/${p}` }))

import { getConnectorCatalog } from './connectors'

let dir: string

function pack(body: string): void {
  const file = nodePath.join(dir, 'templates.yml')
  writeFileSync(file, body, 'utf8')
  process.env.CABINET_CONNECTOR_TEMPLATES = file
}

/** One well-formed template, so an arm can vary exactly one thing. */
function entry(over: Record<string, string> = {}): string {
  const o = { id: 'alpha', label: 'Alpha', category: 'code', ...over }
  return `  - id: ${o.id}
    label: ${o.label}
    category: ${o.category}
    summary: What a sweep of Alpha shows.
    host: api.alpha.test
    credential_env: ALPHA_TOKEN
    credential_help: An Alpha token.
    key_looks_like: "starts with al_"
    how_to_connect:
      - "Open Alpha settings."
      - "Make a read-only key."
    fields: []
    connector:
      inventory:
        url: https://api.alpha.test/things
        method: GET
        name_field: name
        updated_field: updated_at
`
}

beforeEach(() => {
  mockAuth.mockReset()
  mockAuth.mockResolvedValue(true)
  dir = mkdtempSync(nodePath.join(tmpdir(), 'catalog-'))
})

afterEach(() => {
  delete process.env.CABINET_CONNECTOR_TEMPLATES
  rmSync(dir, { recursive: true, force: true })
  vi.restoreAllMocks()
})

describe('getConnectorCatalog', () => {
  it('refuses an unauthenticated caller before reading anything', async () => {
    mockAuth.mockResolvedValue(false)
    pack(`schema: cabinet.connector-templates/v1\ncategories:\n  code: Code\ntemplates:\n${entry()}`)
    await expect(getConnectorCatalog()).rejects.toThrow('Unauthorized')
  })

  it('projects the fields a surface draws, and resolves the shelf label', async () => {
    pack(`schema: cabinet.connector-templates/v1
categories:
  code: Where your code lives
templates:
${entry()}`)
    const catalog = await getConnectorCatalog()
    expect(catalog.templates).toHaveLength(1)
    expect(catalog.templates[0]).toMatchObject({
      id: 'alpha',
      label: 'Alpha',
      host: 'api.alpha.test',
      credential_env: 'ALPHA_TOKEN',
      key_looks_like: 'starts with al_',
      category: 'code',
      category_label: 'Where your code lives',
    })
    expect(catalog.templates[0].how_to_connect).toEqual([
      'Open Alpha settings.',
      'Make a read-only key.',
    ])
    expect(catalog.categories).toEqual([
      { id: 'code', label: 'Where your code lives', count: 1 },
    ])
  })

  it('never leaks the connector body — a surface gets the host, not the read shape', async () => {
    pack(`schema: cabinet.connector-templates/v1
categories:
  code: Code
templates:
${entry()}`)
    const catalog = await getConnectorCatalog()
    const blob = JSON.stringify(catalog)
    expect(blob).not.toContain('https://api.alpha.test/things')
    expect(blob).not.toContain('updated_field')
  })

  it('puts a tool with an undeclared category on a shelf rather than losing it', async () => {
    // A data typo must not make a connectable tool unreachable — the operator
    // would have no way to know it was ever there.
    pack(`schema: cabinet.connector-templates/v1
categories:
  code: Code
templates:
${entry({ id: 'orphan', label: 'Orphan', category: 'no-such-shelf' })}`)
    const catalog = await getConnectorCatalog()
    expect(catalog.templates[0].category).toBe('other')
    expect(catalog.categories).toEqual([{ id: 'other', label: 'Anything else', count: 1 }])
  })

  it('offers no shelf that nothing sits on — an empty filter is a dead tap', async () => {
    pack(`schema: cabinet.connector-templates/v1
categories:
  code: Code
  finance: Money
templates:
${entry()}`)
    const catalog = await getConnectorCatalog()
    expect(catalog.categories.map((c) => c.id)).toEqual(['code'])
  })

  it('drops one malformed entry and keeps the rest of the catalog usable', async () => {
    pack(`schema: cabinet.connector-templates/v1
categories:
  code: Code
templates:
  - label: No id at all
    connector:
      inventory:
        url: https://api.broken.test/x
  - id: no-connector
    label: Half built
${entry()}`)
    const catalog = await getConnectorCatalog()
    expect(catalog.templates.map((t) => t.id)).toEqual(['alpha'])
  })

  it('keeps the open template last, whatever it is called alphabetically', async () => {
    pack(`schema: cabinet.connector-templates/v1
categories:
  code: Code
templates:
${entry({ id: 'rest', label: 'Another REST list', category: 'code' })}${entry({ id: 'zebra', label: 'Zebra', category: 'code' })}`)
    const catalog = await getConnectorCatalog()
    expect(catalog.templates.map((t) => t.id)).toEqual(['zebra', 'rest'])
  })

  it('returns an empty catalog when the pack is absent or will not parse', async () => {
    process.env.CABINET_CONNECTOR_TEMPLATES = nodePath.join(dir, 'not-here.yml')
    expect(await getConnectorCatalog()).toEqual({ templates: [], categories: [] })

    pack('templates: "this is not a list"')
    expect(await getConnectorCatalog()).toEqual({ templates: [], categories: [] })

    pack(': : not yaml at all : :')
    expect(await getConnectorCatalog()).toEqual({ templates: [], categories: [] })
  })

  it('treats a stepless or single-string how_to_connect as data, not a crash', async () => {
    pack(`schema: cabinet.connector-templates/v1
categories:
  code: Code
templates:
  - id: terse
    label: Terse
    category: code
    summary: One line.
    host: api.terse.test
    credential_env: TERSE_TOKEN
    how_to_connect: "Make a key in settings."
    connector:
      inventory:
        url: https://api.terse.test/things
        method: GET
`)
    const catalog = await getConnectorCatalog()
    expect(catalog.templates[0].how_to_connect).toEqual(['Make a key in settings.'])
    expect(catalog.templates[0].key_looks_like).toBe('')
    expect(catalog.templates[0].fields).toEqual([])
  })
})
