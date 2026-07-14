import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { invocation } from './bridge'

describe('onboarding core invocation', () => {
  it('is a fixed module argv with no user content', () => {
    const spec = invocation('act')
    expect(spec.argv).toEqual(['-m', 'framework.onboarding.journey', 'act'])
    expect(spec.argv.join(' ')).not.toMatch(/source|purpose|charter/i)
  })

  it('pins shell:false and sends request JSON only to stdin', () => {
    const source = fs.readFileSync(path.join(process.cwd(), 'src/lib/onboarding/bridge.ts'), 'utf8')
    expect(source).toMatch(/shell:\s*false/)
    expect(source).toMatch(/child\.stdin\.end\(input \? JSON\.stringify\(input\)/)
    expect(source).not.toMatch(/exec\s*\(/)
    expect(source).not.toMatch(/execSync\s*\(/)
  })
})
