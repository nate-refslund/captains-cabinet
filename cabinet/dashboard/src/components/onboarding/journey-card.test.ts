import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

const component = fs.readFileSync(
  path.join(process.cwd(), 'src/components/onboarding/journey-card.tsx'),
  'utf8'
)
const worldPage = fs.readFileSync(
  path.join(process.cwd(), 'src/app/(authenticated)/world/page.tsx'),
  'utf8'
)

describe('onboarding journey accessibility floor', () => {
  it('uses labeled controls, a fieldset, live status, and minimum 44px targets', () => {
    expect(component).toMatch(/<label htmlFor=/)
    expect(component).toMatch(/<fieldset>/)
    expect(component).toMatch(/<legend/)
    expect(component).toMatch(/aria-live="polite"/)
    expect(component).toMatch(/min-h-11/)
    expect(component).toMatch(/role="status"/)
  })

  it('requires a typed destructive confirmation instead of a one-tap prompt', () => {
    expect(component).toContain("purgeConfirmation !== 'PURGE'")
    expect(component).toContain('Type PURGE to permanently delete')
    expect(component).not.toContain('window.confirm')
  })

  it('keeps evidence as DOM text with path and line, never canvas-only', () => {
    expect(component).toMatch(/citation\.path/)
    expect(component).toMatch(/citation\.line/)
    expect(component).toMatch(/citation\.excerpt/)
    expect(component).not.toMatch(/<canvas/)
  })

  it('uses ordinary product language at the low floor', () => {
    expect(component).toContain('Folder to look through')
    expect(component).toContain('Use my Documents')
    expect(component).not.toMatch(/\bMCP\b/)
    expect(component).not.toMatch(/\bRedis\b/)
    expect(component).not.toMatch(/\bYAML\b/)
  })
})

describe('surface parity without a World mutation fork', () => {
  it('submits every surface action to the one shared API', () => {
    expect(component.match(/fetch\('\/api\/onboarding'/g)?.length).toBe(2)
    expect(component).not.toContain('/api/world/')
    expect(component).not.toMatch(/localStorage|sessionStorage|indexedDB/)
  })

  it('World renders the same component and labels its shared-service seam', () => {
    expect(worldPage).toContain('<OnboardingJourneyCard surface="world" variant="world" />')
    expect(worldPage).toContain('posts to /api/onboarding')
    expect(worldPage).not.toMatch(/fetch\(|axios\.|export\s+async\s+function\s+(POST|PUT|PATCH|DELETE)/)
  })
})
