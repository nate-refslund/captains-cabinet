// memory-search — security + parity negative controls.
//
// The dominant claims under test:
//   1. INJECTION: untrusted query text NEVER enters SQL program text — the
//      SQL handed to pg is byte-identical to the static module constants and
//      hostile payloads appear only in the bind-values array.
//   2. READ-ONLY + RETIREMENT: both SQL arms are single SELECTs over
//      cabinet_memory; no mutation verbs, no retired library_records/spaces.
//   3. SOURCE FENCE: the org-knowledge allowlist is bound unconditionally
//      (no empty-filter bypass arm) and excludes conversational/private
//      classes (telegram_dm etc.).
//   4. DEGRADE PARITY: embedding unavailable (keyless/outage/bad dims/seam
//      unwired) → lexical arm, never a throw (memory.sh doctrine).
//   5. RANKING PARITY: the blended weights/half-life pin memory.sh's
//      RANKING-BLOCK so drift is loud.
//   6. deriveLibraryPath is a conservative pure rewrite (traversal-shaped
//      source_ids yield no link).
//
// db is mocked (no pg), fetch is stubbed (no network). Env via vi.stubEnv.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const { mockQuery } = vi.hoisted(() => ({ mockQuery: vi.fn() }))

vi.mock('./db', () => ({ query: mockQuery }))

import {
  searchMemory,
  deriveLibraryPath,
  ORG_KNOWLEDGE_SOURCE_TYPES,
  HYBRID_SQL,
  LEXICAL_SQL,
} from './memory-search'

const DIMS = 1024
const VEC = Array.from({ length: DIMS }, (_, i) => (i % 7) / 7)
const TYPES_PARAM = ORG_KNOWLEDGE_SOURCE_TYPES.join(',')

function stubVoyageOk() {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    json: async () => ({ data: [{ embedding: VEC }] }),
  }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function stubVoyageDown() {
  const fetchMock = vi.fn(async () => {
    throw new Error('ECONNREFUSED')
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

beforeEach(() => {
  mockQuery.mockReset()
  mockQuery.mockResolvedValue([])
  vi.stubEnv('VOYAGE_API_KEY', 'test-key-never-dialed')
  vi.stubEnv('EMBED_PROVIDER', '')
  vi.stubEnv('EMBED_MODEL', '')
  vi.stubEnv('EMBED_DIMS', '')
  vi.stubEnv('CABINET_ID', '')
  vi.stubEnv('CABINET_MEMORY_MIN_SCORE', '')
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

// ============================================================
// 1. SQL-injection negative controls
// ============================================================

const HOSTILE_QUERIES = [
  `'; DROP TABLE cabinet_memory; --`,
  `x' UNION SELECT source_type, content, 1.0, now()::text, content FROM cabinet_memory --`,
  `"; DELETE FROM cabinet_memory WHERE '1'='1`,
  `$1'); INSERT INTO cabinet_memory (content) VALUES ('pwn'); --`,
  `robert'); TRUNCATE cabinet_memory; --`,
]

describe('SQL injection — query text is a bind parameter, never program text', () => {
  for (const payload of HOSTILE_QUERIES) {
    it(`hybrid arm: ${JSON.stringify(payload.slice(0, 24))}… stays out of SQL text`, async () => {
      stubVoyageOk()
      await searchMemory(payload, 5)

      expect(mockQuery).toHaveBeenCalledTimes(1)
      const [sql, values] = mockQuery.mock.calls[0] as [string, unknown[]]
      // Strongest possible assertion: the program text IS the static constant.
      expect(sql).toBe(HYBRID_SQL)
      expect(sql).not.toContain(payload)
      // The payload rides only in the values array (as the tsquery input).
      expect(values).toContain(payload)
    })

    it(`lexical arm: ${JSON.stringify(payload.slice(0, 24))}… stays out of SQL text`, async () => {
      stubVoyageDown()
      await searchMemory(payload, 5)

      expect(mockQuery).toHaveBeenCalledTimes(1)
      const [sql, values] = mockQuery.mock.calls[0] as [string, unknown[]]
      expect(sql).toBe(LEXICAL_SQL)
      expect(sql).not.toContain(payload)
      expect(values[0]).toBe(payload)
    })
  }
})

// ============================================================
// 2. Read-only + retirement ratchet on the SQL constants
// ============================================================

describe('SQL constants — read-only, cabinet_memory only', () => {
  const MUTATION_RE = /\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|CREATE|COPY)\b/i
  for (const [name, sql] of [
    ['HYBRID_SQL', HYBRID_SQL],
    ['LEXICAL_SQL', LEXICAL_SQL],
  ] as const) {
    it(`${name} carries no mutation verbs`, () => {
      expect(sql).not.toMatch(MUTATION_RE)
    })
    it(`${name} never references the retired library tables`, () => {
      expect(sql).not.toMatch(/library_records|library_spaces/i)
      expect(sql).toContain('FROM cabinet_memory')
    })
    it(`${name} keeps the superseded_by fence`, () => {
      expect(sql).toContain('superseded_by IS NULL')
    })
    it(`${name} is a single statement (no stacked ';')`, () => {
      expect(sql.trim().replace(/;\s*$/, '')).not.toContain(';')
    })
  }
})

// ============================================================
// 3. Source-type fence
// ============================================================

describe('source fence — org-knowledge classes only, unconditionally bound', () => {
  it('allowlist excludes conversational/private classes', () => {
    const banned = [
      'telegram_dm',
      'telegram_group',
      'session_memory',
      'officer_trigger',
      'correction',
      'captain_decision',
      'reflection',
      'working_note',
      'skill',
      'role_definition',
      'golden_eval',
    ]
    for (const t of banned) {
      expect(ORG_KNOWLEDGE_SOURCE_TYPES).not.toContain(t)
    }
  })

  it('allowlist includes consolidated_belief (officer retro/reflection distillate)', () => {
    // Writers exist at this tip: memory/skills/individual-reflection.md +
    // cross-officer-retro.md queue `consolidated_belief` via
    // memory_queue_embed (terminal step enforced by
    // cabinet/scripts/tests/test_memory_distill.py). Dropping the class
    // would silently hide every retro's distilled beliefs from the Library
    // (review fix 2026-07-17).
    expect(ORG_KNOWLEDGE_SOURCE_TYPES).toContain('consolidated_belief')
  })

  it('hybrid arm binds exactly the allowlist as $3', async () => {
    stubVoyageOk()
    await searchMemory('roadmap', 5)
    const [, values] = mockQuery.mock.calls[0] as [string, unknown[]]
    expect(values[2]).toBe(TYPES_PARAM)
    expect(values[2]).not.toContain('telegram_dm')
  })

  it('lexical arm binds exactly the allowlist as $2', async () => {
    stubVoyageDown()
    await searchMemory('roadmap', 5)
    const [, values] = mockQuery.mock.calls[0] as [string, unknown[]]
    expect(values[1]).toBe(TYPES_PARAM)
    expect(values[1]).not.toContain('telegram_dm')
  })

  it('the type filter has NO empty-string bypass arm (unlike the cid fence)', () => {
    // memory.sh's optional `:'st_filter' = '' OR` arm is deliberately absent
    // here — the fence must not be disableable by any parameter value.
    expect(HYBRID_SQL).not.toMatch(/\$3 = ''/)
    expect(LEXICAL_SQL).not.toMatch(/\$2 = ''/)
    expect(HYBRID_SQL).toContain("m.source_type = ANY(string_to_array($3, ','))")
    expect(LEXICAL_SQL).toContain("m.source_type = ANY(string_to_array($2, ','))")
  })
})

// ============================================================
// 4. Hybrid vs degrade behavior (memory.sh parity)
// ============================================================

describe('embedding seam — hybrid when available, lexical degrade otherwise', () => {
  it('embeds via Voyage with the server-side key and the query as data', async () => {
    const fetchMock = stubVoyageOk()
    await searchMemory('find the roadmap', 5)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      { headers: Record<string, string>; body: string },
    ]
    expect(url).toContain('api.voyageai.com/v1/embeddings')
    expect(init.headers.Authorization).toBe('Bearer test-key-never-dialed')
    const body = JSON.parse(init.body) as { input: string[]; model: string }
    // PIPELINE bytes, not the bare string: memory.sh memory_get_embedding
    // runs `echo | tr '\n' ' ' | cut -c1-32000`, so the wire text carries a
    // trailing space. Pinning the bare string here is exactly the drift that
    // let the P2 parity break ship (review fix 2026-07-17).
    expect(body.input[0]).toBe('find the roadmap ')
    expect(body.model).toBe('voyage-4-large')

    const [sql, values] = mockQuery.mock.calls[0] as [string, unknown[]]
    expect(sql).toBe(HYBRID_SQL)
    // The vector rides as a bind literal string cast in SQL ($1::vector).
    expect(values[0]).toBe(JSON.stringify(VEC))
    expect(sql).toContain('$1::vector')
  })

  describe('wire-text parity — embed bytes match memory.sh memory_get_embedding', () => {
    // Ground truth (cabinet/scripts/lib/memory.sh):
    //   text=$(echo "$text" | tr '\n' ' ' | cut -c1-32000)
    // i.e. interior \n → ' ', echo's appended \n → ONE trailing space, and
    // the 32000-char cut applies AFTER the append. \r is untouched (tr
    // converts only \n). The SQL tsquery bind stays the BARE query — the
    // shell passes the raw text into plainto_tsquery, transforming only the
    // embedding input.
    async function wireFor(q: string): Promise<{ wire: string; bind: unknown }> {
      const fetchMock = stubVoyageOk()
      await searchMemory(q, 5)
      const [, init] = fetchMock.mock.calls[0] as unknown as [
        string,
        { body: string },
      ]
      const body = JSON.parse(init.body) as { input: string[] }
      // Last query call — wireFor may run more than once per test.
      const [, values] = mockQuery.mock.calls.at(-1) as [string, unknown[]]
      return { wire: body.input[0], bind: values[1] }
    }

    it('appends exactly one trailing space to a plain query', async () => {
      const { wire } = await wireFor('killswitch doctrine')
      expect(wire).toBe('killswitch doctrine ')
    })

    it('flattens interior newlines to spaces (tr parity)', async () => {
      const { wire } = await wireFor('killswitch\ndoctrine\nrows')
      expect(wire).toBe('killswitch doctrine rows ')
    })

    it('leaves \\r alone — only \\n is converted (tr, not \\s)', async () => {
      const { wire } = await wireFor('a\r\nb')
      expect(wire).toBe('a\r b ')
    })

    it('cuts at 32000 chars AFTER the append (cut -c1-32000 parity)', async () => {
      const at = 'x'.repeat(32000)
      expect((await wireFor(at)).wire).toBe(at) // append pushed out by the cut
      const under = 'y'.repeat(31999)
      expect((await wireFor(under)).wire).toBe(under + ' ') // space survives
    })

    it('SQL tsquery bind stays the BARE query (newlines intact)', async () => {
      const q = 'killswitch\ndoctrine'
      const { bind } = await wireFor(q)
      expect(bind).toBe(q)
    })
  })

  it('keyless → lexical arm, fetch never dialed, no throw', async () => {
    vi.stubEnv('VOYAGE_API_KEY', '')
    const fetchMock = stubVoyageOk()
    const res = await searchMemory('quiet box', 5)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(res.degraded).toBe(true)
    const [sql] = mockQuery.mock.calls[0] as [string]
    expect(sql).toBe(LEXICAL_SQL)
    expect(sql).not.toContain('<=>')
  })

  it('unwired EMBED_PROVIDER → lexical arm (seam parity), fetch never dialed', async () => {
    vi.stubEnv('EMBED_PROVIDER', 'openai')
    const fetchMock = stubVoyageOk()
    const res = await searchMemory('seam check', 5)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(res.degraded).toBe(true)
  })

  it('provider outage (fetch throws) → lexical arm, no throw', async () => {
    stubVoyageDown()
    const res = await searchMemory('outage', 5)
    expect(res.degraded).toBe(true)
    const [sql] = mockQuery.mock.calls[0] as [string]
    expect(sql).toBe(LEXICAL_SQL)
  })

  it('non-200 from the provider → lexical arm', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, json: async () => ({}) }))
    )
    const res = await searchMemory('bad status', 5)
    expect(res.degraded).toBe(true)
  })

  it('wrong-dims embedding → lexical arm (never a malformed vector bind)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ data: [{ embedding: [1, 2, 3] }] }),
      }))
    )
    const res = await searchMemory('dims drift', 5)
    expect(res.degraded).toBe(true)
    const [sql] = mockQuery.mock.calls[0] as [string]
    expect(sql).toBe(LEXICAL_SQL)
  })

  it('non-numeric embedding entries → lexical arm', async () => {
    const evil = Array.from({ length: DIMS }, () => 0.1) as unknown[]
    evil[7] = '1); DROP TABLE cabinet_memory; --'
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ data: [{ embedding: evil }] }),
      }))
    )
    const res = await searchMemory('poisoned vector', 5)
    expect(res.degraded).toBe(true)
    const [sql] = mockQuery.mock.calls[0] as [string]
    expect(sql).toBe(LEXICAL_SQL)
  })
})

// ============================================================
// 5. Ranking parity pins (memory.sh RANKING-BLOCK)
// ============================================================

describe('ranking parity — blended weights track memory.sh', () => {
  it('hybrid weights: 0.60 vec + 0.25 lex + 0.15 recency (0.80/0.20 renorm)', () => {
    expect(HYBRID_SQL).toContain('0.60 * s.vec_sim + 0.25 * s.lex + 0.15 * s.recency')
    expect(HYBRID_SQL).toContain('0.80 * s.vec_sim + 0.20 * s.recency')
  })
  it('lexical weights: 0.80 lex + 0.20 recency', () => {
    expect(LEXICAL_SQL).toContain('0.80 * s.lex + 0.20 * s.recency')
  })
  it('90-day recency half-life in both arms', () => {
    expect(HYBRID_SQL).toContain('90.0 * 86400.0')
    expect(LEXICAL_SQL).toContain('90.0 * 86400.0')
  })
  it('vec floor is bound ($5) in the hybrid arm and defaults 0.45', async () => {
    stubVoyageOk()
    await searchMemory('floor', 5)
    const [sql, values] = mockQuery.mock.calls[0] as [string, unknown[]]
    expect(sql).toContain('WHERE vec_sim >= $5::float8')
    expect(values[4]).toBe(0.45)
  })
  it('CABINET_MEMORY_MIN_SCORE env override honored; junk falls back', async () => {
    stubVoyageOk()
    vi.stubEnv('CABINET_MEMORY_MIN_SCORE', '0.6')
    await searchMemory('floor', 5)
    expect((mockQuery.mock.calls[0] as [string, unknown[]])[1][4]).toBe(0.6)

    mockQuery.mockClear()
    vi.stubEnv('CABINET_MEMORY_MIN_SCORE', 'DROP TABLE')
    await searchMemory('floor', 5)
    expect((mockQuery.mock.calls[0] as [string, unknown[]])[1][4]).toBe(0.45)
  })
})

// ============================================================
// 6. Tenant scope (memory.sh memory_cabinet_scope parity)
// ============================================================

describe('cabinet scope', () => {
  it('unset CABINET_ID → unscoped ("")', async () => {
    stubVoyageOk()
    await searchMemory('scope', 5)
    expect((mockQuery.mock.calls[0] as [string, unknown[]])[1][3]).toBe('')
  })
  it('valid CABINET_ID passes through', async () => {
    stubVoyageOk()
    vi.stubEnv('CABINET_ID', 'hq-macbook')
    await searchMemory('scope', 5)
    expect((mockQuery.mock.calls[0] as [string, unknown[]])[1][3]).toBe('hq-macbook')
  })
  it('invalid charset resolves to main (never unscoped)', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    stubVoyageOk()
    vi.stubEnv('CABINET_ID', 'acme.eu')
    await searchMemory('scope', 5)
    expect((mockQuery.mock.calls[0] as [string, unknown[]])[1][3]).toBe('main')
    warn.mockRestore()
  })
})

// ============================================================
// 7. Limit clamp + hit mapping
// ============================================================

describe('limit clamp', () => {
  it.each([
    [999, 20],
    [0, 1],
    [-5, 1],
    [7, 7],
    [undefined, 20],
    [Number.NaN, 20],
  ])('limit %s → %s', async (input, expected) => {
    stubVoyageOk()
    await searchMemory('clamp', input as number | undefined)
    expect((mockQuery.mock.calls[0] as [string, unknown[]])[1][5]).toBe(expected)
  })
})

describe('hit mapping', () => {
  it('vault rows gain libraryPath; other org rows stay badge-only', async () => {
    stubVoyageOk()
    mockQuery.mockResolvedValueOnce([
      {
        source_type: 'product_brain',
        source_id: 'vault/decisions/adr-001.md',
        score: 0.91,
        when_at: '2026-07-01 10:00',
        snippet: 'Decision: adopt the thing',
      },
      {
        source_type: 'captain_law_summary',
        source_id: 'claw-2026-07',
        score: 0.83,
        when_at: null,
        snippet: 'Captain law digest',
      },
    ])
    const res = await searchMemory('decision', 5)
    expect(res.degraded).toBe(false)
    expect(res.hits[0].libraryPath).toBe('decisions/adr-001.md')
    expect(res.hits[1].libraryPath).toBeUndefined()
    expect(res.hits[1].source_type).toBe('captain_law_summary')
  })

  it('a stored XSS-shaped snippet passes through as plain JSON data', async () => {
    stubVoyageOk()
    const hostile = '<script>alert(1)</script><img src=x onerror=alert(2)>'
    mockQuery.mockResolvedValueOnce([
      {
        source_type: 'framework_doc',
        source_id: 'docs/x.md',
        score: 0.5,
        when_at: null,
        snippet: hostile,
      },
    ])
    const res = await searchMemory('xss', 5)
    // Data stays data here; the RENDER-side escape is pinned in
    // library-search.test.tsx (highlightSnippet static-markup controls).
    expect(res.hits[0].snippet).toBe(hostile)
  })
})

// ============================================================
// 8. deriveLibraryPath — conservative pure rewrite
// ============================================================

describe('deriveLibraryPath', () => {
  it.each([
    ['vault/decisions/foo.md', 'decisions/foo.md'],
    ['vault/a/b/c.markdown', 'a/b/c.markdown'],
    ['product-brain/legacy.md', 'legacy.md'],
  ])('maps %s → %s', (sourceId, expected) => {
    expect(deriveLibraryPath('product_brain', sourceId)).toBe(expected)
  })

  it.each([
    ['vault/../secrets.md'], // traversal segment
    ['vault/./x.md'], // dot segment
    ['vault//x.md'], // empty segment
    ['vault/x.txt'], // non-markdown
    ['vault/'], // empty rel
    ['vault/a\\b.md'], // backslash
    ['vault/evil\0.md'], // NUL
    ['/etc/passwd.md'], // absolute (no vault/ prefix)
    ['docs/x.md'], // not a vault-prefixed id
    ['lib-42'], // library_record-shaped id
  ])('rejects %s', (sourceId) => {
    expect(deriveLibraryPath('product_brain', sourceId)).toBeUndefined()
  })

  it('only product_brain rows map', () => {
    expect(deriveLibraryPath('framework_doc', 'vault/x.md')).toBeUndefined()
    expect(deriveLibraryPath('telegram_dm', 'vault/x.md')).toBeUndefined()
    expect(deriveLibraryPath('product_brain', null)).toBeUndefined()
    expect(deriveLibraryPath('product_brain', undefined)).toBeUndefined()
  })
})
