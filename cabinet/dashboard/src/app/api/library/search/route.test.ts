// /api/library/search — library search handlers.
//
// GET (2026-07-17) = THE Library search: cabinet_memory org-knowledge search
// via @/lib/memory-search (mocked here — its own SQL/injection controls live
// in memory-search.test.ts). Pins: empty-q short-circuit, trim, limit clamp,
// per-session rate limit (429), {results, degraded} shape, generic 500.
//
// POST = legacy arm (retired library_records ILIKE, kept for CommandPalette):
//   - 400 when query missing or empty/whitespace
//   - 200 with {results} on success
//   - 500 on throw
// Quirks: query is trimmed before searchRecords call; limit defaults to 10 (?? coalesce);
// space_id and labels pass through as-is (no transformation).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NextRequest } from 'next/server'

const { mockSearchRecords, mockSearchMemory } = vi.hoisted(() => ({
  mockSearchRecords: vi.fn(),
  mockSearchMemory: vi.fn(),
}))

vi.mock('@/lib/library', () => ({
  searchRecords: mockSearchRecords,
}))

vi.mock('@/lib/memory-search', () => ({
  searchMemory: mockSearchMemory,
}))

import { GET, POST } from './route'
import { resetSearchRateLimit } from '@/lib/search-rate-limit'

function makeReq(body: unknown): NextRequest {
  return {
    json: async () => body,
  } as unknown as NextRequest
}

function makeBadJsonReq(): NextRequest {
  return {
    json: async () => {
      throw new SyntaxError('Unexpected token < in JSON')
    },
  } as unknown as NextRequest
}

function makeGetReq(qs: string, cookie?: string): NextRequest {
  return new NextRequest(`http://localhost/api/library/search${qs}`, {
    headers: cookie ? { cookie: `cabinet_session=${cookie}` } : {},
  })
}

beforeEach(() => {
  mockSearchRecords.mockReset()
  mockSearchMemory.mockReset()
  mockSearchMemory.mockResolvedValue({ hits: [], degraded: false })
  resetSearchRateLimit()
})

describe('GET /api/library/search — empty query short-circuit', () => {
  it('missing q returns {results: [], degraded: false} without touching the engine', async () => {
    const res = await GET(makeGetReq(''))
    expect(res.status).toBe(200)
    expect(await res.json()).toEqual({ results: [], degraded: false })
    expect(mockSearchMemory).not.toHaveBeenCalled()
  })

  it('whitespace-only q short-circuits too', async () => {
    const res = await GET(makeGetReq('?q=%20%20%20'))
    expect(res.status).toBe(200)
    expect(await res.json()).toEqual({ results: [], degraded: false })
    expect(mockSearchMemory).not.toHaveBeenCalled()
  })
})

describe('GET /api/library/search — query + limit normalization', () => {
  it('trims q and defaults limit to 20', async () => {
    await GET(makeGetReq('?q=%20%20org%20roadmap%20%20'))
    expect(mockSearchMemory).toHaveBeenCalledWith('org roadmap', 20)
  })

  it('caps limit at 20', async () => {
    await GET(makeGetReq('?q=x&limit=500'))
    expect(mockSearchMemory).toHaveBeenCalledWith('x', 20)
  })

  it('floors limit at 1', async () => {
    await GET(makeGetReq('?q=x&limit=0'))
    expect(mockSearchMemory).toHaveBeenCalledWith('x', 1)
  })

  it('non-numeric limit falls back to 20 (no NaN pass-through)', async () => {
    await GET(makeGetReq('?q=x&limit=abc'))
    expect(mockSearchMemory).toHaveBeenCalledWith('x', 20)
  })

  it('honors an in-range limit', async () => {
    await GET(makeGetReq('?q=x&limit=7'))
    expect(mockSearchMemory).toHaveBeenCalledWith('x', 7)
  })

  it('clamps an overlong q to 2048 chars before it reaches the engine (review fix 2026-07-17)', async () => {
    const long = 'a'.repeat(5000)
    await GET(makeGetReq(`?q=${long}`))
    expect(mockSearchMemory).toHaveBeenCalledTimes(1)
    const [qArg] = mockSearchMemory.mock.calls[0] as [string]
    expect(qArg).toBe('a'.repeat(2048))
  })
})

describe('GET /api/library/search — response shape', () => {
  it('200 with {results, degraded} passthrough', async () => {
    const hits = [
      {
        snippet: 'Decision: adopt',
        source_type: 'product_brain',
        source_id: 'vault/decisions/a.md',
        score: 0.91,
        when_at: '2026-07-01 10:00',
        libraryPath: 'decisions/a.md',
      },
    ]
    mockSearchMemory.mockResolvedValueOnce({ hits, degraded: false })
    const res = await GET(makeGetReq('?q=decision'))
    expect(res.status).toBe(200)
    expect(await res.json()).toEqual({ results: hits, degraded: false })
  })

  it('degraded: true surfaces to the client', async () => {
    mockSearchMemory.mockResolvedValueOnce({ hits: [], degraded: true })
    const res = await GET(makeGetReq('?q=outage'))
    expect((await res.json()).degraded).toBe(true)
  })
})

describe('GET /api/library/search — rate limit (per session)', () => {
  it('blocks the 31st request in a window with 429 and stops calling the engine', async () => {
    for (let i = 0; i < 30; i++) {
      const res = await GET(makeGetReq(`?q=r${i}`, 'tok.sig'))
      expect(res.status).toBe(200)
    }
    const blocked = await GET(makeGetReq('?q=r30', 'tok.sig'))
    expect(blocked.status).toBe(429)
    expect((await blocked.json()).error).toBe('Rate limited')
    // Review fix 2026-07-17: 429 carries a Retry-After hint (full window).
    expect(blocked.headers.get('Retry-After')).toBe('60')
    expect(mockSearchMemory).toHaveBeenCalledTimes(30)
  })

  it('a different session is not affected by an exhausted one', async () => {
    for (let i = 0; i < 31; i++) await GET(makeGetReq(`?q=r${i}`, 'tok.sig'))
    const other = await GET(makeGetReq('?q=fresh', 'other.sig'))
    expect(other.status).toBe(200)
  })
})

describe('GET /api/library/search — error path (500, generic only)', () => {
  it('500 with generic error when the engine throws', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockSearchMemory.mockRejectedValueOnce(new Error('pg down'))
    const res = await GET(makeGetReq('?q=x'))
    expect(res.status).toBe(500)
    expect((await res.json()).error).toBe('Search failed')
    spy.mockRestore()
  })

  it('never leaks internals (connection strings) in the body', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockSearchMemory.mockRejectedValueOnce(
      new Error('secret: conn=pg://u:pw@host/db')
    )
    const res = await GET(makeGetReq('?q=x'))
    const body = await res.json()
    expect(JSON.stringify(body)).not.toContain('pw@host')
    expect(body.error).toBe('Search failed')
    spy.mockRestore()
  })
})

describe('POST /api/library/search — body validation (400)', () => {
  it('400 when query is missing', async () => {
    const res = await POST(makeReq({ space_id: 'abc' }))
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error).toBe('query is required')
  })

  it('400 when query is empty string', async () => {
    const res = await POST(makeReq({ query: '' }))
    expect(res.status).toBe(400)
    const body = await res.json()
    expect(body.error).toBe('query is required')
    expect(mockSearchRecords).not.toHaveBeenCalled()
  })

  it('400 when query is whitespace only', async () => {
    const res = await POST(makeReq({ query: '   ' }))
    expect(res.status).toBe(400)
    expect(mockSearchRecords).not.toHaveBeenCalled()
  })

  it('400 when body is empty object (null query)', async () => {
    const res = await POST(makeReq({}))
    expect(res.status).toBe(400)
  })
})

describe('POST /api/library/search — query pass-through', () => {
  it('trims query before passing to searchRecords', async () => {
    mockSearchRecords.mockResolvedValueOnce([])
    await POST(makeReq({ query: '  spec 037  ' }))
    expect(mockSearchRecords).toHaveBeenCalledWith(
      expect.objectContaining({ query: 'spec 037' })
    )
  })

  it('limit defaults to 10 when absent (?? coalesce)', async () => {
    mockSearchRecords.mockResolvedValueOnce([])
    await POST(makeReq({ query: 'test' }))
    expect(mockSearchRecords).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 10 })
    )
  })

  it('passes explicit limit through', async () => {
    mockSearchRecords.mockResolvedValueOnce([])
    await POST(makeReq({ query: 'test', limit: 25 }))
    expect(mockSearchRecords).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 25 })
    )
  })

  it('passes space_id through when provided', async () => {
    mockSearchRecords.mockResolvedValueOnce([])
    await POST(makeReq({ query: 'test', space_id: 'space-abc' }))
    expect(mockSearchRecords).toHaveBeenCalledWith(
      expect.objectContaining({ space_id: 'space-abc' })
    )
  })

  it('space_id undefined when not provided', async () => {
    mockSearchRecords.mockResolvedValueOnce([])
    await POST(makeReq({ query: 'test' }))
    expect(mockSearchRecords).toHaveBeenCalledWith(
      expect.objectContaining({ space_id: undefined })
    )
  })

  it('passes labels array through', async () => {
    mockSearchRecords.mockResolvedValueOnce([])
    await POST(makeReq({ query: 'test', labels: ['spec', 'research'] }))
    expect(mockSearchRecords).toHaveBeenCalledWith(
      expect.objectContaining({ labels: ['spec', 'research'] })
    )
  })

  it('labels undefined when not provided', async () => {
    mockSearchRecords.mockResolvedValueOnce([])
    await POST(makeReq({ query: 'test' }))
    expect(mockSearchRecords).toHaveBeenCalledWith(
      expect.objectContaining({ labels: undefined })
    )
  })

  it('full arg object matches expected shape', async () => {
    mockSearchRecords.mockResolvedValueOnce([])
    await POST(makeReq({ query: '  find me  ', space_id: 's1', labels: ['a'], limit: 5 }))
    expect(mockSearchRecords).toHaveBeenCalledWith({
      query: 'find me',
      space_id: 's1',
      labels: ['a'],
      limit: 5,
    })
  })
})

describe('POST /api/library/search — success (200)', () => {
  it('200 with {results} on success', async () => {
    const rows = [
      { id: '1', title: 'Spec 037', score: 0.9 },
      { id: '2', title: 'Spec 038', score: 0.8 },
    ]
    mockSearchRecords.mockResolvedValueOnce(rows)
    const res = await POST(makeReq({ query: 'spec' }))
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body).toEqual({ results: rows })
  })

  it('200 with empty results array', async () => {
    mockSearchRecords.mockResolvedValueOnce([])
    const res = await POST(makeReq({ query: 'zzznonexistent' }))
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body).toEqual({ results: [] })
  })
})

describe('POST /api/library/search — error paths (500)', () => {
  it('500 when searchRecords throws', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockSearchRecords.mockRejectedValueOnce(new Error('pgvector error'))
    const res = await POST(makeReq({ query: 'test' }))
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error).toBe('Search failed')
    spy.mockRestore()
  })

  it('500 when req.json() throws (malformed body)', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const res = await POST(makeBadJsonReq())
    expect(res.status).toBe(500)
    const body = await res.json()
    expect(body.error).toBe('Search failed')
    spy.mockRestore()
  })

  it('500 never leaks internal error detail', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockSearchRecords.mockRejectedValueOnce(new Error('secret: db=pg://u:pw@host/db'))
    const res = await POST(makeReq({ query: 'test' }))
    const body = await res.json()
    expect(body.error).toBe('Search failed')
    expect(JSON.stringify(body)).not.toContain('pw@host')
    spy.mockRestore()
  })
})
