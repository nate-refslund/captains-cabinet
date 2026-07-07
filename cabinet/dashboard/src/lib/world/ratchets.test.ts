/**
 * Cabinet World CI ratchets — land AT route creation, not later (chassis
 * consensus graft; kickoff step 3 "CI ratchets at route creation").
 *
 * These greps are the mechanical form of the doctrine:
 *  1. NO write server-actions anywhere under the world trees ('use server').
 *  2. NO POST/PUT/PATCH/DELETE exports from /api/world routes (GET-only —
 *     the world never grows a write path).
 *  3. Text-only rendering: no dangerouslySetInnerHTML / innerHTML /
 *     insertAdjacentHTML in world components.
 *  4. Determinism: no Math.random / Date.now in the render path
 *     (lib/world + components/world). Seeded hashes + the logical tick are
 *     the only variation sources.
 *  5. CSP header pinned for /world in next.config.ts.
 *  6. Opaque handles: the URL layer never writes a raw officer slug param.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'

const DASH = path.resolve(__dirname, '..', '..', '..')
const WORLD_TREES = [
  path.join(DASH, 'src', 'lib', 'world'),
  path.join(DASH, 'src', 'components', 'world'),
  path.join(DASH, 'src', 'app', 'api', 'world'),
  path.join(DASH, 'src', 'app', '(authenticated)', 'world'),
]

function collectSources(dir: string): string[] {
  if (!fs.existsSync(dir)) return []
  const out: string[] = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name)
    if (entry.isDirectory()) out.push(...collectSources(p))
    else if (/\.(ts|tsx)$/.test(entry.name) && !entry.name.endsWith('.test.ts'))
      out.push(p)
  }
  return out
}

const sources = WORLD_TREES.flatMap(collectSources)
const read = (p: string) => fs.readFileSync(p, 'utf8')

describe('world CI ratchets', () => {
  it('world trees exist and are non-empty', () => {
    expect(sources.length).toBeGreaterThan(4)
  })

  it('1. no server actions under any world tree', () => {
    for (const p of sources) {
      expect(read(p), p).not.toMatch(/['"]use server['"]/)
    }
  })

  it('2. /api/world routes are GET-only (no write verbs exported)', () => {
    const apiSources = sources.filter((p) =>
      p.includes(path.join('app', 'api', 'world'))
    )
    expect(apiSources.length).toBeGreaterThan(0)
    for (const p of apiSources) {
      const text = read(p)
      expect(text, p).not.toMatch(
        /export\s+(async\s+)?function\s+(POST|PUT|PATCH|DELETE)/
      )
      expect(text, p).toMatch(/export\s+async\s+function\s+GET/)
    }
  })

  it('3. text-only rendering — no HTML injection surfaces', () => {
    for (const p of sources) {
      const text = read(p)
      expect(text, p).not.toMatch(/dangerouslySetInnerHTML/)
      expect(text, p).not.toMatch(/\binnerHTML\s*=/)
      expect(text, p).not.toMatch(/insertAdjacentHTML/)
      expect(text, p).not.toMatch(/document\.write/)
    }
  })

  it('4. determinism — no Math.random / Date.now in the render path', () => {
    const renderPath = sources.filter(
      (p) =>
        p.includes(path.join('lib', 'world')) ||
        p.includes(path.join('components', 'world'))
    )
    expect(renderPath.length).toBeGreaterThan(3)
    for (const p of renderPath) {
      const text = read(p)
      expect(text, p).not.toMatch(/Math\.random\s*\(/)
      expect(text, p).not.toMatch(/Date\.now\s*\(/)
    }
  })

  it('5. CSP header for /world pinned in next.config.ts', () => {
    const cfg = read(path.join(DASH, 'next.config.ts'))
    expect(cfg).toMatch(/source:\s*['"]\/world['"]/)
    expect(cfg).toMatch(/Content-Security-Policy/)
    expect(cfg).toMatch(/frame-ancestors 'none'/)
    expect(cfg).toMatch(/default-src 'self'/)
  })

  it('6. URL layer writes opaque sel handles, never slug params', () => {
    const client = read(
      path.join(DASH, 'src', 'components', 'world', 'world-client.tsx')
    )
    // The only sel writes must come from the server-issued handle field.
    expect(client).not.toMatch(/set\(['"]slug['"]/)
    expect(client).not.toMatch(/[?&]slug=/)
    // And the stream route must issue hashed handles.
    const route = read(
      path.join(DASH, 'src', 'app', 'api', 'world', 'stream', 'route.ts')
    )
    expect(route).toMatch(/selHandle/)
    expect(route).toMatch(/sha256/)
  })

  it('7. stream route clones the auth gate (cookie check present)', () => {
    for (const rel of [
      ['app', 'api', 'world', 'stream', 'route.ts'],
      ['app', 'api', 'world', 'grammar', 'route.ts'],
    ]) {
      const text = read(path.join(DASH, 'src', ...rel))
      expect(text).toMatch(/cabinet_session/)
      expect(text).toMatch(/401/)
    }
  })
})
