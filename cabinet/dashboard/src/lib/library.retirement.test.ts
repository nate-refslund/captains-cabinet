// Library retirement (2026-07-16) — dashboard write path is vector-free.
//
// Pins the surgery on createRecord/updateRecord/searchRecords:
//   - NO Voyage call ever (global fetch is a tripwire that throws),
//   - INSERT/UPDATE SQL carries no embedding/embedded_at column,
//   - the cabinet_memory mirror queue still fires (redis-cli XADD via
//     execFile — argv transport, mocked here) with the record as DATA,
//   - searchRecords is keyword-only (ILIKE, no vector operator).
//
// db + wikilinks + node:child_process are mocked — no network, no pg, no
// redis. See docs/runbooks/library-retirement-2026-07-16.md.

import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mockQuery, mockExecFile, mockIndexLinks, mockIndexSections } = vi.hoisted(() => ({
  mockQuery: vi.fn(),
  mockExecFile: vi.fn((_cmd: string, _args: string[], cb?: (err: Error | null) => void) => {
    if (cb) cb(null)
  }),
  mockIndexLinks: vi.fn(async () => {}),
  mockIndexSections: vi.fn(async () => {}),
}))

vi.mock('./db', () => ({ query: mockQuery }))
vi.mock('./wikilinks', () => ({
  indexLinks: mockIndexLinks,
  indexSections: mockIndexSections,
}))
vi.mock('node:child_process', () => ({ execFile: mockExecFile }))

import { createRecord, updateRecord, searchRecords } from './library'

const RECORD_ROW = {
  id: '42', space_id: '7', title: 'T', content_markdown: 'B',
  schema_data: {}, labels: [], version: 1, superseded_by: null,
  status: 'draft', superseded_by_record_id: null,
  created_by_officer: 'cos', created_at: 'x', updated_at: 'x',
}
const SPACE_ROW = { id: '7', name: 'Test Space' }

function installQueryRouter() {
  mockQuery.mockImplementation(async (sql: string) => {
    if (sql.includes('WITH locked')) return [{ ...RECORD_ROW, id: '43', version: 2 }]
    if (sql.includes('INSERT INTO library_records')) return [RECORD_ROW]
    if (sql.includes('FROM library_spaces s')) return [SPACE_ROW]
    return []
  })
}

beforeEach(() => {
  mockQuery.mockReset()
  mockExecFile.mockClear()
  mockIndexLinks.mockClear()
  mockIndexSections.mockClear()
  installQueryRouter()
  // Voyage tripwire: ANY fetch on this path is the retired embed resurfacing.
  vi.stubGlobal('fetch', vi.fn(() => {
    throw new Error('fetch called — record-vector embed path resurfaced')
  }))
  // ARM it: the historic getEmbedding early-returned null on a missing key,
  // so a resurrected copy could silently no-op past the fetch stub. Dummy
  // value only — the stub above throws before any network could happen.
  vi.stubEnv('VOYAGE_API_KEY', 'test-dummy-never-dialed')
})

const HOSTILE = 'body with $(boom) `tick` "quotes" <script>x</script>'

describe('createRecord — vector-free + memory-queue only', () => {
  it('INSERT has no embedding column and no Voyage fetch', async () => {
    const rec = await createRecord({
      space_id: '7',
      title: 'T',
      content_markdown: HOSTILE,
      created_by_officer: 'cos',
    })
    expect(rec.id).toBe('42')

    const insertCall = mockQuery.mock.calls.find(([sql]) =>
      (sql as string).includes('INSERT INTO library_records')
    )
    expect(insertCall).toBeTruthy()
    const [sql, params] = insertCall as [string, unknown[]]
    expect(sql).not.toMatch(/embedding/i)
    expect(sql).not.toMatch(/embedded_at/i)
    // Hostile content rides a $n parameter, never the SQL text.
    expect(sql).not.toContain('$(boom)')
    expect(params).toContain(HOSTILE)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('queues exactly one cabinet_memory XADD with the record as data', async () => {
    await createRecord({ space_id: '7', title: 'T', content_markdown: HOSTILE })
    await vi.waitFor(() => expect(mockExecFile).toHaveBeenCalledTimes(1))

    const [cmd, args] = mockExecFile.mock.calls[0] as [string, string[]]
    expect(cmd).toBe('redis-cli')
    expect(args).toContain('XADD')
    expect(args).toContain('cabinet:memory:embed_queue')
    const payload = JSON.parse(args[args.length - 1])
    expect(payload.source_type).toBe('library_record')
    expect(payload.source_id).toBe('lib-42')
    expect(payload.content).toContain('$(boom)') // data, not executed
    expect(payload.metadata.record_id).toBe('42')
  })
})

describe('updateRecord — vector-free + memory-queue only', () => {
  it('versioned-insert CTE has no embedding column; queue fires for lib-43', async () => {
    const rec = await updateRecord('42', { title: 'T2', content_markdown: 'B2' })
    expect(rec.id).toBe('43')

    const cteCall = mockQuery.mock.calls.find(([sql]) =>
      (sql as string).includes('WITH locked')
    )
    expect(cteCall).toBeTruthy()
    const [sql, params] = cteCall as [string, unknown[]]
    expect(sql).not.toMatch(/embedding/i)
    expect(sql).not.toMatch(/embedded_at/i)
    expect(params).toHaveLength(6) // id, title, content, schema, labels, officer
    expect(fetch).not.toHaveBeenCalled()

    await vi.waitFor(() => expect(mockExecFile).toHaveBeenCalledTimes(1))
    const [, args] = mockExecFile.mock.calls[0] as [string, string[]]
    const payload = JSON.parse(args[args.length - 1])
    expect(payload.source_id).toBe('lib-43')
  })
})

describe('searchRecords — keyword-only since retirement', () => {
  it('single ILIKE query, no vector operator, no fetch', async () => {
    mockQuery.mockImplementation(async () => [])
    await searchRecords({ query: "x' OR 1=1 --", limit: 5 })

    expect(mockQuery).toHaveBeenCalledTimes(1)
    const [sql, params] = mockQuery.mock.calls[0] as [string, unknown[]]
    expect(sql).toContain('ILIKE')
    expect(sql).not.toMatch(/vector/i)
    expect(sql).not.toContain('<=>')
    // Query text is a parameter — SQLi-shaped input stays data.
    expect(sql).not.toContain('OR 1=1')
    expect(params[1]).toBe("x' OR 1=1 --")
    expect(fetch).not.toHaveBeenCalled()
  })

  it('labels filter passes as a parameter array', async () => {
    mockQuery.mockImplementation(async () => [])
    await searchRecords({ query: 'q', labels: ['a', 'b'] })
    const [sql, params] = mockQuery.mock.calls[0] as [string, unknown[]]
    expect(sql).toContain('labels && $3::text[]')
    expect(params[2]).toEqual(['a', 'b'])
  })
})
