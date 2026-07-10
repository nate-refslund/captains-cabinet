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
    expect(Object.keys(body).sort()).toEqual(['ok', 'service', 'ts'])
    expect(() => new Date(body.ts).toISOString()).not.toThrow()
  })
})

describe('manifest()', () => {
  it('returns the exact PWA manifest object', () => {
    expect(manifest()).toEqual({
      name: "Founder's Cabinet",
      short_name: 'Cabinet',
      description: "Admin dashboard for the Founder's Cabinet",
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
