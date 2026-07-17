import { Pool } from 'pg'

// Lazy singleton connection pool — created on first use rather than at import
// time. This matters because Next.js's build step collects page data and
// imports every server module; creating the Pool at import time means the
// build fails if NEON_CONNECTION_STRING isn't in the BUILD env (env_file in
// docker-compose.yml only applies at RUNTIME).
//
// In dev (HMR), the pool is cached on globalThis to avoid exhausting
// connections across hot reloads.

declare global {
  // eslint-disable-next-line no-var
  var __pgPool: Pool | undefined
}

/**
 * SSL posture for the pool (review fix 2026-07-17). This used to hardcode
 * `ssl: { rejectUnauthorized: false }`, which breaks any store that cannot
 * speak SSL at all: a local `postgres://…@localhost/…` works under psql
 * (sslmode=prefer silently falls back to plaintext) but node-pg does no such
 * fallback — every query failed with "The server does not support SSL
 * connections". Mirror psql's decision statically from the connection string
 * (never logged; hosts/paths only, no credentials touched):
 *   - explicit `sslmode=disable`                → no TLS
 *   - explicit require / verify-* / no-verify   → TLS (legacy posture:
 *     rejectUnauthorized:false, unchanged for every managed store)
 *   - otherwise ("prefer"): loopback host       → no TLS (local plaintext
 *     postgres); any remote host incl. *.neon.tech → TLS (legacy posture)
 * Unparseable strings keep the legacy TLS posture (fail toward the old
 * behavior, never toward silently downgrading a remote connection).
 * Exported for unit tests (db.test.ts) only.
 */
export function resolvePoolSsl(
  connectionString: string
): { rejectUnauthorized: boolean } | undefined {
  const LEGACY_TLS = { rejectUnauthorized: false }
  let host: string
  let sslmode: string
  try {
    const u = new URL(connectionString)
    host = u.hostname.toLowerCase()
    sslmode = (u.searchParams.get('sslmode') ?? '').toLowerCase()
  } catch {
    return LEGACY_TLS
  }
  if (sslmode === 'disable') return undefined
  if (['require', 'verify-ca', 'verify-full', 'no-verify'].includes(sslmode)) {
    return LEGACY_TLS
  }
  const isLoopback =
    host === '' || // no host = local socket / default
    host === 'localhost' ||
    host === '[::1]' ||
    /^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(host)
  return isLoopback ? undefined : LEGACY_TLS
}

function createPool(): Pool {
  const connectionString = process.env.NEON_CONNECTION_STRING
  if (!connectionString) {
    throw new Error('NEON_CONNECTION_STRING env var is not set')
  }
  return new Pool({
    connectionString,
    max: 5,
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 5_000,
    ssl: resolvePoolSsl(connectionString),
  })
}

function getPool(): Pool {
  if (process.env.NODE_ENV === 'development') {
    return (globalThis.__pgPool ??= createPool())
  }
  // In production, recreate per process; Next.js server runs one process
  // so this effectively caches too.
  if (!globalThis.__pgPool) {
    globalThis.__pgPool = createPool()
  }
  return globalThis.__pgPool
}

/** Convenience: run a parameterized query and return rows */
export async function query<T extends Record<string, unknown>>(
  text: string,
  values?: unknown[]
): Promise<T[]> {
  const result = await getPool().query<T>(text, values)
  return result.rows
}

/** Direct pool accessor if a caller needs transactions / custom client usage */
export function getDbPool(): Pool {
  return getPool()
}
