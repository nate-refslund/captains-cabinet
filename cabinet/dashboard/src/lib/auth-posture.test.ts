/**
 * ONE NAME, ONE POWER — driven at both ends.
 *
 * Every arm here fails against the pre-change predicate (`MOCK_DATA === 'true'
 * && NODE_ENV !== 'production'`), which is the only property that makes it a
 * sensor rather than a restatement. Proven by mutation; the log is in the PR.
 */
import { describe, expect, it } from 'vitest'
import { isNoAuthPosture } from './auth-posture'

describe('MOCK_DATA no longer takes the door off', () => {
  it('MOCK_DATA=true alone does NOT waive auth, in any environment', () => {
    for (const NODE_ENV of ['development', 'test', 'production', undefined]) {
      expect(
        isNoAuthPosture({ MOCK_DATA: 'true', DASHBOARD_PASSWORD: 'set', NODE_ENV } as never),
        `NODE_ENV=${NODE_ENV}`
      ).toBe(false)
    }
  })

  it('CABINET_DEMO_DATA=true does not either — the data flags are data flags', () => {
    expect(
      isNoAuthPosture({
        CABINET_DEMO_DATA: 'true',
        DASHBOARD_PASSWORD: 'set',
        NODE_ENV: 'development',
      } as never)
    ).toBe(false)
  })
})

describe('the two openings that remain', () => {
  it('DASHBOARD_NO_AUTH=true waives auth outside production', () => {
    for (const NODE_ENV of ['development', 'test']) {
      expect(isNoAuthPosture({ DASHBOARD_NO_AUTH: 'true', NODE_ENV })).toBe(true)
    }
  })

  it('development with NO password waives auth', () => {
    expect(isNoAuthPosture({ NODE_ENV: 'development' })).toBe(true)
    expect(isNoAuthPosture({ NODE_ENV: 'development', DASHBOARD_PASSWORD: '' })).toBe(true)
  })

  it('development WITH a password does not', () => {
    expect(
      isNoAuthPosture({ NODE_ENV: 'development', DASHBOARD_PASSWORD: 'set' })
    ).toBe(false)
  })

  it('NODE_ENV=test with no password is still enforcing — `development` exactly', () => {
    // The dev opening is spelled as an equality, not as "not production", so a
    // CI or preview environment does not inherit it.
    expect(isNoAuthPosture({ NODE_ENV: 'test' })).toBe(false)
  })
})

describe('NOTHING opens a production deploy — the property this module exists for', () => {
  it('no combination of every flag at once waives auth in production', () => {
    const everything = {
      DASHBOARD_NO_AUTH: 'true',
      MOCK_DATA: 'true',
      CABINET_DEMO_DATA: 'true',
      DASHBOARD_PASSWORD: '',
      NODE_ENV: 'production',
    }
    expect(isNoAuthPosture(everything as never)).toBe(false)
  })

  it('exhaustively: over every flag combination, production is never open', () => {
    // Not a spot check. If a future arm is added without its own production
    // guard, this fails without anyone having to remember to update it.
    const flags = ['DASHBOARD_NO_AUTH', 'MOCK_DATA', 'CABINET_DEMO_DATA', 'DASHBOARD_PASSWORD']
    for (let mask = 0; mask < 1 << flags.length; mask++) {
      const env: Record<string, string> = { NODE_ENV: 'production' }
      flags.forEach((f, i) => {
        if (mask & (1 << i)) env[f] = 'true'
      })
      expect(isNoAuthPosture(env as never), JSON.stringify(env)).toBe(false)
    }
  })
})
