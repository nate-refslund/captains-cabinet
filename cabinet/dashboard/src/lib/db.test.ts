// db.ts — lazy pg-pool singleton harness.
// Testing strategy: vi.mock('pg') replaces the real Pool class with a fake
// that records constructor opts + query() calls. Each test resets the
// globalThis.__pgPool cache + NEON_CONNECTION_STRING so state from one
// test doesn't bleed into the next.
//
// Invariants pinned:
//  - Pool is NOT created at module import (lazy — required for Next.js
//    build-time page-data collection where NEON_CONNECTION_STRING is unset)
//  - getDbPool()/query() throw when NEON_CONNECTION_STRING is missing
//  - Second call returns the same Pool (globalThis cache)
//  - Pool is created with max:5, 5s connect timeout, and an ssl posture
//    resolved per store by resolvePoolSsl (review fix 2026-07-17): legacy
//    rejectUnauthorized:false for remote/managed stores, plaintext for
//    loopback or sslmode=disable — psql-prefer parity, so a local no-SSL
//    postgres stops 500ing every query while Neon keeps the production
//    footprint unchanged
//  - query<T>() returns result.rows, not the full result object

import { describe, it, expect, beforeEach, vi } from 'vitest'

// Track fake Pool instances across tests so we can assert creation + caching
interface FakePool {
  __opts: Record<string, unknown>
  query: ReturnType<typeof vi.fn>
}
const poolCtorCalls: Record<string, unknown>[] = []

vi.mock('pg', () => {
  class Pool {
    __opts: Record<string, unknown>
    query: ReturnType<typeof vi.fn>
    constructor(opts: Record<string, unknown>) {
      this.__opts = opts
      this.query = vi.fn(async (_text: string, _values?: unknown[]) => ({
        rows: [{ id: 1, name: 'fake' }],
        rowCount: 1,
      }))
      poolCtorCalls.push(opts)
    }
  }
  return { Pool }
})

type DbMod = typeof import('./db')
let mod: DbMod

async function loadFresh(): Promise<DbMod> {
  // Reset module cache to re-run top-level code (not strictly needed here
  // since db.ts has no top-level side effects — but keeps tests hermetic).
  vi.resetModules()
  return import('./db')
}

beforeEach(async () => {
  // Clear the module-level singleton + tracked ctor calls
  delete (globalThis as { __pgPool?: unknown }).__pgPool
  poolCtorCalls.length = 0
  delete process.env.NEON_CONNECTION_STRING
  // NODE_ENV is typed readonly in Next.js 15+ — cast to reset between tests
  delete (process.env as Record<string, string | undefined>).NODE_ENV
  mod = await loadFresh()
})

describe('db — lazy pool creation', () => {
  it('does not create a Pool at module import (build-safe)', () => {
    // After import, no Pool was constructed yet
    expect(poolCtorCalls).toHaveLength(0)
    expect((globalThis as { __pgPool?: unknown }).__pgPool).toBeUndefined()
  })

  it('getDbPool throws when NEON_CONNECTION_STRING is unset', () => {
    expect(() => mod.getDbPool()).toThrow('NEON_CONNECTION_STRING env var is not set')
  })

  it('query throws when NEON_CONNECTION_STRING is unset', async () => {
    await expect(mod.query('SELECT 1')).rejects.toThrow(
      'NEON_CONNECTION_STRING env var is not set'
    )
  })

  it('getDbPool creates Pool on first call with env set', () => {
    process.env.NEON_CONNECTION_STRING = 'postgres://test@host/db'
    const pool = mod.getDbPool() as unknown as FakePool
    expect(poolCtorCalls).toHaveLength(1)
    expect(pool.__opts).toHaveProperty('connectionString', 'postgres://test@host/db')
  })

  it('Pool created with expected configuration values', () => {
    process.env.NEON_CONNECTION_STRING = 'postgres://test@host/db'
    mod.getDbPool()
    const opts = poolCtorCalls[0]
    expect(opts.max).toBe(5)
    expect(opts.idleTimeoutMillis).toBe(30_000)
    expect(opts.connectionTimeoutMillis).toBe(5_000)
    // Remote host, no sslmode → legacy TLS posture (unchanged behavior)
    expect(opts.ssl).toEqual({ rejectUnauthorized: false })
  })

  it('Pool against a loopback store is created WITHOUT forced TLS', () => {
    process.env.NEON_CONNECTION_STRING =
      'postgresql://cabinet@localhost:5432/cabinet'
    mod.getDbPool()
    expect(poolCtorCalls[0].ssl).toBeUndefined()
  })
})

describe('db — resolvePoolSsl (psql-prefer parity; review fix 2026-07-17)', () => {
  const LEGACY_TLS = { rejectUnauthorized: false }

  it('local plaintext store (localhost, no sslmode) → no TLS', () => {
    expect(
      mod.resolvePoolSsl('postgresql://cabinet@localhost:5432/cabinet')
    ).toBeUndefined()
  })

  it('loopback variants → no TLS', () => {
    expect(mod.resolvePoolSsl('postgres://u@127.0.0.1:5432/db')).toBeUndefined()
    expect(mod.resolvePoolSsl('postgres://u@[::1]:5432/db')).toBeUndefined()
  })

  it('managed Neon host (no sslmode) keeps the legacy TLS posture', () => {
    expect(
      mod.resolvePoolSsl(
        'postgres://u:p@ep-x-1.eu-central-1.aws.neon.tech/neondb'
      )
    ).toEqual(LEGACY_TLS)
  })

  it('any remote host (no sslmode) keeps the legacy TLS posture', () => {
    expect(mod.resolvePoolSsl('postgres://u:p@db.internal:5432/db')).toEqual(
      LEGACY_TLS
    )
  })

  it('explicit sslmode=require/verify-* wins over loopback (TLS on localhost)', () => {
    expect(
      mod.resolvePoolSsl('postgres://u@localhost:5432/db?sslmode=require')
    ).toEqual(LEGACY_TLS)
    expect(
      mod.resolvePoolSsl('postgres://u@localhost:5432/db?sslmode=verify-full')
    ).toEqual(LEGACY_TLS)
  })

  it('explicit sslmode=disable wins over a remote host (plaintext)', () => {
    expect(
      mod.resolvePoolSsl('postgres://u:p@ep-x.neon.tech/db?sslmode=disable')
    ).toBeUndefined()
  })

  it('sslmode=prefer behaves like the default (host decides)', () => {
    expect(
      mod.resolvePoolSsl('postgres://u@localhost/db?sslmode=prefer')
    ).toBeUndefined()
    expect(
      mod.resolvePoolSsl('postgres://u@db.remote/db?sslmode=prefer')
    ).toEqual(LEGACY_TLS)
  })

  it('unparseable connection string fails toward the legacy TLS posture', () => {
    expect(mod.resolvePoolSsl('not a url at all')).toEqual(LEGACY_TLS)
    expect(mod.resolvePoolSsl('')).toEqual(LEGACY_TLS)
  })
})

describe('db — singleton caching', () => {
  it('second getDbPool() returns the same instance (only 1 ctor call)', () => {
    process.env.NEON_CONNECTION_STRING = 'postgres://test@host/db'
    const a = mod.getDbPool()
    const b = mod.getDbPool()
    expect(a).toBe(b)
    expect(poolCtorCalls).toHaveLength(1)
  })

  it('caches on globalThis.__pgPool (cross-HMR stability)', () => {
    process.env.NEON_CONNECTION_STRING = 'postgres://test@host/db'
    mod.getDbPool()
    expect((globalThis as { __pgPool?: unknown }).__pgPool).toBeDefined()
  })

  it('query() reuses the cached pool (no second ctor call)', async () => {
    process.env.NEON_CONNECTION_STRING = 'postgres://test@host/db'
    mod.getDbPool()
    await mod.query('SELECT 1')
    expect(poolCtorCalls).toHaveLength(1)
  })

  it('development mode uses globalThis cache too (??= idempotent)', () => {
    ;(process.env as Record<string, string | undefined>).NODE_ENV = 'development'
    process.env.NEON_CONNECTION_STRING = 'postgres://dev@host/db'
    mod.getDbPool()
    mod.getDbPool()
    expect(poolCtorCalls).toHaveLength(1)
  })
})

describe('db — query() delegation', () => {
  it('passes text + values to pool.query', async () => {
    process.env.NEON_CONNECTION_STRING = 'postgres://test@host/db'
    const pool = mod.getDbPool() as unknown as FakePool
    await mod.query('SELECT * FROM users WHERE id = $1', [42])
    expect(pool.query).toHaveBeenCalledWith('SELECT * FROM users WHERE id = $1', [42])
  })

  it('returns result.rows (not the full QueryResult)', async () => {
    process.env.NEON_CONNECTION_STRING = 'postgres://test@host/db'
    const rows = await mod.query<{ id: number; name: string }>('SELECT 1')
    expect(rows).toEqual([{ id: 1, name: 'fake' }])
    // Caller should NOT see rowCount, command, fields etc.
    expect(rows).not.toHaveProperty('rowCount')
  })

  it('forwards undefined values when 2nd arg omitted', async () => {
    process.env.NEON_CONNECTION_STRING = 'postgres://test@host/db'
    const pool = mod.getDbPool() as unknown as FakePool
    await mod.query('SELECT NOW()')
    expect(pool.query).toHaveBeenCalledWith('SELECT NOW()', undefined)
  })

  it('throws when env is set but then cleared between query calls (cached pool survives)', async () => {
    process.env.NEON_CONNECTION_STRING = 'postgres://test@host/db'
    await mod.query('SELECT 1')
    // Clearing env after pool cached doesn't invalidate cache
    delete process.env.NEON_CONNECTION_STRING
    await expect(mod.query('SELECT 2')).resolves.toEqual([{ id: 1, name: 'fake' }])
    expect(poolCtorCalls).toHaveLength(1)
  })
})

describe('db — NODE_ENV=development branch', () => {
  it('dev mode: globalThis ??= creates pool on first call', () => {
    ;(process.env as Record<string, string | undefined>).NODE_ENV = 'development'
    process.env.NEON_CONNECTION_STRING = 'postgres://dev@host/db'
    expect((globalThis as { __pgPool?: unknown }).__pgPool).toBeUndefined()
    mod.getDbPool()
    expect((globalThis as { __pgPool?: unknown }).__pgPool).toBeDefined()
  })

  it('dev mode: pre-populated globalThis.__pgPool is reused (HMR scenario)', () => {
    ;(process.env as Record<string, string | undefined>).NODE_ENV = 'development'
    process.env.NEON_CONNECTION_STRING = 'postgres://dev@host/db'
    // Simulate HMR reload where globalThis.__pgPool is already set
    const precached = { __opts: { fake: 'precache' }, query: vi.fn() }
    ;(globalThis as { __pgPool?: unknown }).__pgPool = precached
    const pool = mod.getDbPool() as unknown as typeof precached
    expect(pool).toBe(precached)
    expect(poolCtorCalls).toHaveLength(0)  // No new pool created
  })
})
