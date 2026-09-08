// PWA readiness tests (Wave D app-feel): /api/health liveness, manifest
// exactness, and the middleware matcher's both-directions intent — the five
// install surfaces leave auth, everything else stays matched (the actual
// cookie-less 307 on a protected route is asserted in the live smoke, which
// exercises the real middleware runtime).
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import manifest from './manifest'
import { GET } from './api/health/route'

describe('GET /api/health', () => {
  it('returns 200 with a liveness-only body (no config, no state, no secrets)', async () => {
    const res = await GET()
    expect(res.status).toBe(200)
    const body = await res.json()
    expect(body.ok).toBe(true)
    expect(body.service).toBe('cabinet-dashboard')
    // The closed key set gained three members with the update path (contract
    // §5, A5.5), and they are three DIFFERENT facts:
    //   source_commit  which cabinet this process was started against (read
    //                  from its environment at request time)
    //   build_commit   which build is serving (inlined at `next build`)
    //   started_at     when this process started (from its own uptime)
    // Collapsing any two of them is how an update lies about itself: identity
    // alone passes an OLD process that survived a failed restart, and a
    // build-only stamp cannot change at all for an update that touched no
    // dashboard file — which rolled every framework-only update back until it
    // was found in review. None is config, state or a secret, and the set
    // stays CLOSED so a fourth field cannot arrive here unnoticed.
    expect(Object.keys(body).sort()).toEqual([
      'build_commit', 'ok', 'service', 'source_commit', 'started_at', 'ts',
    ])
    expect(() => new Date(body.ts).toISOString()).not.toThrow()
    expect(() => new Date(body.started_at).toISOString()).not.toThrow()
    expect(typeof body.source_commit).toBe('string')
    expect(typeof body.build_commit).toBe('string')
  })

  it('answers the installed identity at request time, not once per module load', async () => {
    // The property the update gate stands on. A value captured when this
    // module was first imported would be the environment of whichever process
    // happened to load it first — and after an update that restarted nothing,
    // that is the OLD process. Two calls with two environments must give two
    // answers.
    const before = process.env.CABINET_SOURCE_COMMIT
    try {
      process.env.CABINET_SOURCE_COMMIT = 'a'.repeat(40)
      const first = await (await GET()).json()
      process.env.CABINET_SOURCE_COMMIT = 'b'.repeat(40)
      const second = await (await GET()).json()
      expect(first.source_commit).toBe('a'.repeat(40))
      expect(second.source_commit).toBe('b'.repeat(40))
    } finally {
      if (before === undefined) delete process.env.CABINET_SOURCE_COMMIT
      else process.env.CABINET_SOURCE_COMMIT = before
    }
  })

  it('reports a start time that is this process, not this module', async () => {
    // Derived from process.uptime(), so it is earlier than now and no later
    // than the process itself. A module-scope `new Date()` would drift to the
    // first request that reached the route.
    const body = await (await GET()).json()
    const started = new Date(body.started_at).getTime()
    expect(started).toBeLessThanOrEqual(Date.now())
    expect(Date.now() - started).toBeGreaterThanOrEqual(Math.floor(process.uptime() * 1000) - 1500)
  })
})

describe('manifest()', () => {
  it('returns the exact PWA manifest object', () => {
    expect(manifest()).toEqual({
      name: "Captain's Cabinet",
      short_name: 'Cabinet',
      description: "Admin dashboard for the Captain's Cabinet",
      id: '/',
      start_url: '/',
      scope: '/',
      display: 'standalone',
      background_color: '#09090b',
      theme_color: '#09090b',
      icons: [
        { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
        { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
        {
          src: '/icons/icon-512-maskable.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: 'maskable',
        },
      ],
    })
  })
})

describe('middleware matcher (both directions)', () => {
  // Read the matcher literal from the source (importing middleware.ts would
  // drag next/server into the unit run; the literal IS the contract) and
  // simulate it the way Next applies the regex-group idiom: anchored over
  // the whole pathname.
  const source = readFileSync(join(__dirname, '..', 'middleware.ts'), 'utf-8')
  const m = source.match(/matcher: \['([^']+)'\]/)
  if (!m) throw new Error('middleware.ts matcher literal not found')
  // The Next "match all except" idiom is itself a valid regex when anchored.
  const matcher = new RegExp(`^${m[1]}$`)

  const runs = (path: string) => matcher.test(path)

  it('excludes exactly the five install surfaces (cookie-less fetch must not 307)', () => {
    for (const path of [
      '/manifest.webmanifest',
      '/icon.svg',
      '/apple-icon.png',
      '/icons/icon-192.png',
      '/icons/icon-512.png',
      '/icons/icon-512-maskable.png',
      '/api/health',
      // pre-existing exclusions stay excluded
      '/_next/static/chunks/main.js',
      '/_next/image',
      '/favicon.ico',
    ]) {
      expect(runs(path), `${path} must be EXCLUDED from auth middleware`).toBe(false)
    }
  })

  it('keeps every other route — including every other /api/* — behind the middleware', () => {
    for (const path of [
      '/',
      '/governance',
      '/receipts',
      '/login',
      '/display',
      '/api/tasks',
      '/api/auth',
      '/api/onboarding',
      '/api/world/engine',
      '/iconsmith', // must not ride the icons/ prefix exclusion
    ]) {
      expect(runs(path), `${path} must stay MATCHED by auth middleware`).toBe(true)
    }
  })

  it('documents the prefix hazard: health-prefixed paths ride the api/health exclusion', () => {
    // The exclusions are PREFIX alternatives — these paths are excluded from
    // auth TODAY even though no such routes exist. That is exactly why the
    // filesystem tripwire in cabinet/scripts/tests/test_dashboard_pwa_static.py
    // (test_health_namespace_is_closed_tripwire) pins src/app/api/ to exactly
    // api/health/route.ts under this prefix. If a health-prefixed route is
    // ever consciously added, re-adjudicate both tests together.
    for (const path of ['/api/healthz', '/api/health-report', '/api/health/deep']) {
      expect(runs(path), `${path} rides the api/health prefix exclusion (see tripwire)`).toBe(false)
    }
  })
})
