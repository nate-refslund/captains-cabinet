/**
 * /queue page + needs-you badge — READ-ONLY static ratchet (second-door
 * law): the classic war-room skin renders and deep-links; it NEVER grows an
 * approve/veto verb, a server action, or a mutating fetch. Sister of the
 * mailbox GET-only pin (ui-layer.test.ts) — same doctrine, new surfaces.
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

const SRC = path.resolve(__dirname, '..', '..', '..')
const PAGE = path.join(SRC, 'app', '(authenticated)', 'queue', 'page.tsx')
const BADGE = path.join(SRC, 'components', 'needs-you-badge.tsx')

describe('classic war-room skin is read-only by construction', () => {
  it('queue page: no buttons, no forms, no actions, no mutation verbs', () => {
    const text = fs.readFileSync(PAGE, 'utf8')
    expect(text).not.toMatch(/<button/i)
    expect(text).not.toMatch(/<form/i)
    expect(text).not.toMatch(/['"]use server['"]/)
    expect(text).not.toMatch(/@\/actions\//)
    expect(text).not.toMatch(/method\s*:/i)
    expect(text).not.toMatch(/fetch\(/) // server component reads the lib directly
  })

  it('queue page states the one-door law and carries the binder grammar', () => {
    const text = fs.readFileSync(PAGE, 'utf8')
    expect(text).toMatch(/approve \{row\.pid\}/)
    expect(text).toMatch(/binder/i)
    expect(text).toMatch(/focus=wardroom/)
    expect(text).toMatch(/read-only/i)
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
