import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { applyOnboardingAction, invocation, OnboardingBridgeError } from './bridge'

describe('onboarding core invocation', () => {
  it('is a fixed module argv with no user content', () => {
    const spec = invocation('act')
    expect(spec.argv).toEqual(['-m', 'framework.onboarding.journey', 'act'])
    expect(spec.argv.join(' ')).not.toMatch(/source|purpose|charter/i)
  })

  // The allowlist is the bridge's only action gate, so an action the core
  // accepts and this set omits is unreachable from every web surface — which
  // is how the seed question could be printed with nothing able to answer it.
  it('accepts answer_seed and still refuses an action the core does not have', () => {
    // These guards throw SYNCHRONOUSLY, before any child process is spawned.
    expect(() => applyOnboardingAction({ action: 'not_a_real_action' } as never, 'dashboard'))
      .toThrow(OnboardingBridgeError)
    expect(() => applyOnboardingAction({ action: 'answer_seed', seed: 'x'.repeat(2_001) }, 'dashboard'))
      .toThrow(/A sentence or two is enough/)
  })

  it('pins shell:false and sends request JSON only to stdin', () => {
    const source = fs.readFileSync(path.join(process.cwd(), 'src/lib/onboarding/bridge.ts'), 'utf8')
    expect(source).toMatch(/shell:\s*false/)
    expect(source).toMatch(/child\.stdin\.end\(input \? JSON\.stringify\(input\)/)
    expect(source).not.toMatch(/exec\s*\(/)
    expect(source).not.toMatch(/execSync\s*\(/)
  })
})
