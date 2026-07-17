// /vault — source contract (2026-07-17).
//
// The vault browser is READ-ONLY and DB-FREE by construction. This test greps
// the vault source (route + data layer + wikilinks + renderer) so neither
// property can quietly regress:
//   - no filesystem WRITE calls (writeFile/unlink/rm/mkdir/rename/…),
//   - no mutation HTTP handlers (no POST/PUT/PATCH/DELETE exports); MVP adds
//     zero API routes,
//   - no database (no '@/lib/db', no pg, no query()) — keeps the retired
//     vector store retired and clears the library-retirement ratchet,
//   - no raw-HTML escape hatch (no rehype-raw, no dangerouslySetInnerHTML=).

import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC = join(HERE, '..', '..', '..') // → cabinet/dashboard/src

const SOURCES = {
  page: join(HERE, '[[...path]]', 'page.tsx'),
  vaultLib: join(SRC, 'lib', 'vault.ts'),
  wikilinks: join(SRC, 'lib', 'vault-wikilinks.ts'),
  renderer: join(SRC, 'components', 'vault', 'VaultMarkdown.tsx'),
}

// Strip block comments before grepping so the contract checks ACTUAL CODE, not
// the doc prose (these modules deliberately describe '@/lib/db' / query() /
// dangerouslySetInnerHTML / rehype-raw in comments to explain why they are
// absent). Our sources contain no `/*`/`*/` inside string or regex literals.
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, ' ')
}
const read = (p: string) => stripComments(readFileSync(p, 'utf-8'))

// Filesystem WRITE call shapes — matched as calls so read APIs (statSync,
// readdirSync, readFileSync, realpathSync, lstatSync, existsSync) never trip.
const WRITE_CALL =
  /\b(writeFile|writeFileSync|unlink|unlinkSync|rmSync|rmdir|rmdirSync|mkdir|mkdirSync|rename|renameSync|appendFile|appendFileSync|copyFile|copyFileSync|truncate|createWriteStream)\s*\(/

describe('/vault source contract — read-only', () => {
  for (const [name, path] of Object.entries(SOURCES)) {
    it(`${name} makes no filesystem write calls`, () => {
      expect(read(path)).not.toMatch(WRITE_CALL)
    })
  }

  it('the route exports no mutation HTTP handler', () => {
    const src = read(SOURCES.page)
    expect(src).not.toMatch(/export\s+(async\s+)?function\s+(POST|PUT|PATCH|DELETE)\b/)
    expect(src).not.toMatch(/export\s+const\s+(POST|PUT|PATCH|DELETE)\b/)
  })

  it('there is NO /api/vault route surface (pure server components, zero endpoints)', () => {
    expect(existsSync(join(SRC, 'app', 'api', 'vault'))).toBe(false)
  })
})

describe('/vault source contract — DB-free', () => {
  for (const [name, path] of Object.entries(SOURCES)) {
    it(`${name} imports no database layer and issues no query`, () => {
      const src = read(path)
      expect(src).not.toContain('@/lib/db')
      expect(src).not.toMatch(/from ['"]\.\/db['"]/)
      expect(src).not.toMatch(/from ['"]pg['"]/)
      expect(src).not.toMatch(/\bquery\s*\(/)
    })
  }

  it('the wikilinks module does NOT import lib/wikilinks (which pulls in db)', () => {
    // The pure parsers are COPIED, not imported, precisely to keep the vault
    // graph free of the transitive @/lib/db import in lib/wikilinks.ts.
    expect(read(SOURCES.wikilinks)).not.toMatch(/from ['"]@\/lib\/wikilinks['"]/)
    expect(read(SOURCES.vaultLib)).not.toMatch(/from ['"]@\/lib\/wikilinks['"]/)
  })
})

describe('/vault source contract — no raw-HTML escape hatch', () => {
  it('the renderer never uses rehype-raw or dangerouslySetInnerHTML', () => {
    const src = read(SOURCES.renderer)
    expect(src).not.toMatch(/from ['"]rehype-raw['"]/)
    expect(src).not.toMatch(/dangerouslySetInnerHTML\s*=/)
    // Positive: it DOES sanitize.
    expect(src).toContain('rehype-sanitize')
  })
})
