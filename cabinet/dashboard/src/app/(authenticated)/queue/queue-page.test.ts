/**
 * /queue + attention API — ONE-DOOR static ratchet.
 *
 * SUPERSEDES the read-only ratchet (this file's previous body) per Ruling A
 * (captain-decisions 2026-07-10): WRITE-CLASS-2 = YES with the
 * equal-authority-door law. The dashboard may now decide — through exactly
 * ONE write route that speaks the org's own reply grammar through the org's
 * own gate. The ratchet therefore pins:
 *
 *  1. Exactly ONE write route under app/api/attention/** — verdict/route.ts.
 *     Every other attention route stays GET-only.
 *  2. The door executes NOTHING itself: the verdict lib must spawn the
 *     framework bridge (`framework.attention.verdicts`) — fixed argv, no
 *     shell — and the route must go through that lib.
 *  3. The client card POSTs ONLY to /api/attention/verdict, with the CSRF
 *     header, and never imports server actions.
 *  4. The needs-you badge stays a plain-GET glance surface.
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

const SRC = path.resolve(__dirname, '..', '..', '..')
const API_ATTENTION = path.join(SRC, 'app', 'api', 'attention')
const PAGE = path.join(SRC, 'app', '(authenticated)', 'queue', 'page.tsx')
const CARD = path.join(SRC, 'components', 'queue-decision-card.tsx')
const BADGE = path.join(SRC, 'components', 'needs-you-badge.tsx')
const VERDICT_LIB = path.join(SRC, 'lib', 'attention', 'verdict.ts')
const VERDICT_ROUTE = path.join(API_ATTENTION, 'verdict', 'route.ts')

function routeFiles(dir: string): string[] {
  const out: string[] = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name)
    if (entry.isDirectory()) out.push(...routeFiles(p))
    else if (entry.name === 'route.ts') out.push(p)
  }
  return out
}

describe('one door: exactly one write route under /api/attention', () => {
  it('verdict/route.ts is the only attention route exporting a mutation', () => {
    const routes = routeFiles(API_ATTENTION)
    expect(routes).toContain(VERDICT_ROUTE)
    for (const file of routes) {
      const text = fs.readFileSync(file, 'utf8')
      const writes = text.match(
        /export\s+(async\s+)?function\s+(POST|PUT|PATCH|DELETE)\b/g
      )
      if (file === VERDICT_ROUTE) {
        expect(writes, 'verdict route must export POST').toHaveLength(1)
        expect(writes?.[0]).toMatch(/POST/)
      } else {
        expect(writes, `${file} must stay read-only`).toBeNull()
      }
    }
  })

  it('the door speaks through the framework bridge, never locally', () => {
    const lib = fs.readFileSync(VERDICT_LIB, 'utf8')
    // Fixed argv into the org's own module — the equal-authority path.
    expect(lib).toMatch(/framework\.attention\.verdicts/)
    expect(lib).toMatch(/execFile\(/)
    expect(lib).not.toMatch(/\bexec\(/) // no shell, ever
    const route = fs.readFileSync(VERDICT_ROUTE, 'utf8')
    expect(route).toMatch(/@\/lib\/attention\/verdict/)
    expect(route).toMatch(/verifyConfirmToken/)
    expect(route).toMatch(/spendNonce/)
    expect(route).toMatch(/rateLimiter/)
  })
})

describe('surfaces stay inside the one-door contract', () => {
  it('client card: POSTs only to the verdict door, with the CSRF header', () => {
    const text = fs.readFileSync(CARD, 'utf8')
    const fetches = text.match(/fetch\(\s*['"`]([^'"`]+)['"`]/g) ?? []
    expect(fetches.length).toBeGreaterThan(0)
    for (const call of fetches) {
      expect(call).toMatch(/\/api\/attention\/verdict/)
    }
    expect(text).toMatch(/X-Cabinet-CSRF/)
    expect(text).not.toMatch(/['"]use server['"]/)
    expect(text).not.toMatch(/@\/actions\//)
  })

  it('queue page: server component, no fetches, hands the csrf to the card', () => {
    const text = fs.readFileSync(PAGE, 'utf8')
    expect(text).not.toMatch(/fetch\(/) // reads the lib directly
    expect(text).not.toMatch(/['"]use server['"]/)
    expect(text).toMatch(/csrfTokenFor/)
    expect(text).toMatch(/QueueDecisionCard/)
  })

  it('badge: single-argument GET fetch only, hidden at zero, links to /queue', () => {
    const text = fs.readFileSync(BADGE, 'utf8')
    const calls = text.match(/fetch\(([^)]*)\)/g) ?? []
    expect(calls.length).toBeGreaterThan(0)
    for (const call of calls) {
      expect(call).not.toMatch(/,/) // no init object → plain GET
    }
    expect(text).not.toMatch(/method\s*:/i)
    expect(text).not.toMatch(/['"]use server['"]/)
    expect(text).toMatch(/count <= 0/)
    expect(text).toMatch(/href="\/queue"/)
  })
})
