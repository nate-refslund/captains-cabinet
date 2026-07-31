/**
 * The posture decision, at every degenerate end.
 *
 * `resolveStorePosture` is pure and takes its env as an argument precisely so
 * these arms exist: the dangerous combination (`MOCK_DATA=true` in production)
 * is one an environment cannot easily be put into from a test process, and the
 * whole ruling rests on it.
 */
import { describe, expect, it } from 'vitest'
import {
  isNotLiveStore,
  isUnconfiguredInProduction,
  resolveStorePosture,
  storeBannerAttr,
  storeBannerHint,
  storeBannerTitle,
} from './store-posture'

describe('resolveStorePosture — the ruling, arm by arm', () => {
  it('THE DEFECT: REDIS_URL unset is UNCONFIGURED, never fabricated', () => {
    const r = resolveStorePosture({})
    expect(r.posture).toBe('unconfigured')
    expect(r.fabricated).toBe(false)
  })

  it('an EMPTY REDIS_URL is a missing value, not a configured store', () => {
    const r = resolveStorePosture({ REDIS_URL: '' })
    expect(r.posture).toBe('unconfigured')
    expect(r.fabricated).toBe(false)
  })

  it('a real REDIS_URL is live and fabricates nothing', () => {
    const r = resolveStorePosture({ REDIS_URL: 'redis://127.0.0.1:6379' })
    expect(r.posture).toBe('live')
    expect(r.fabricated).toBe(false)
    expect(isNotLiveStore(r)).toBe(false)
  })

  it('MOCK_DATA=true outside production is the explicit demo opt-in', () => {
    const r = resolveStorePosture({ MOCK_DATA: 'true', NODE_ENV: 'development' })
    expect(r.posture).toBe('demo')
    expect(r.fabricated).toBe(true)
  })

  it('CABINET_DEMO_DATA=true is the store-only opt-in (no auth semantics)', () => {
    const r = resolveStorePosture({
      CABINET_DEMO_DATA: 'true',
      NODE_ENV: 'development',
    })
    expect(r.posture).toBe('demo')
    expect(r.fabricated).toBe(true)
  })

  it('only the literal string "true" opts in — no truthiness', () => {
    for (const v of ['1', 'yes', 'TRUE', 'on', '']) {
      expect(resolveStorePosture({ MOCK_DATA: v }).fabricated).toBe(false)
      expect(resolveStorePosture({ CABINET_DEMO_DATA: v }).fabricated).toBe(false)
    }
  })

  describe('PRODUCTION CANNOT FABRICATE — the load-bearing arm', () => {
    it('MOCK_DATA=true in production with a store is LIVE, not demo', () => {
      const r = resolveStorePosture({
        MOCK_DATA: 'true',
        REDIS_URL: 'redis://127.0.0.1:6379',
        NODE_ENV: 'production',
      })
      expect(r.posture).toBe('live')
      expect(r.fabricated).toBe(false)
    })

    it('MOCK_DATA=true in production with NO store is UNCONFIGURED, not demo', () => {
      const r = resolveStorePosture({ MOCK_DATA: 'true', NODE_ENV: 'production' })
      expect(r.posture).toBe('unconfigured')
      expect(r.fabricated).toBe(false)
    })

    it('CABINET_DEMO_DATA=true in production is refused the same way', () => {
      const r = resolveStorePosture({
        CABINET_DEMO_DATA: 'true',
        NODE_ENV: 'production',
      })
      expect(r.fabricated).toBe(false)
    })

    it('NO env combination reaches fabrication under NODE_ENV=production', () => {
      const flags = ['true', 'false', '', '1', undefined]
      const urls = [undefined, '', 'redis://127.0.0.1:6379']
      for (const MOCK_DATA of flags) {
        for (const CABINET_DEMO_DATA of flags) {
          for (const REDIS_URL of urls) {
            const r = resolveStorePosture({
              MOCK_DATA,
              CABINET_DEMO_DATA,
              REDIS_URL,
              NODE_ENV: 'production',
            })
            expect(r.fabricated).toBe(false)
          }
        }
      }
    })
  })

  it('the demo opt-in WINS over a configured store outside production', () => {
    // Otherwise `demo-dashboard.sh` could not be pointed at a machine that
    // happens to have REDIS_URL exported, and would silently show live data
    // in a public demo.
    const r = resolveStorePosture({
      MOCK_DATA: 'true',
      REDIS_URL: 'redis://127.0.0.1:6379',
      NODE_ENV: 'development',
    })
    expect(r.posture).toBe('demo')
  })
})

describe('isNotLiveStore — the emergency stop depends on this covering BOTH', () => {
  it('is true for demo AND for unconfigured', () => {
    expect(isNotLiveStore(resolveStorePosture({}))).toBe(true)
    expect(
      isNotLiveStore(resolveStorePosture({ MOCK_DATA: 'true', NODE_ENV: 'test' }))
    ).toBe(true)
  })
})

describe('the banner', () => {
  it('renders NOTHING for a live store', () => {
    const r = resolveStorePosture({ REDIS_URL: 'redis://x' })
    expect(storeBannerTitle(r)).toBeNull()
    expect(storeBannerHint(r)).toBeNull()
  })

  it('never says anything is fine, and never prints a healthy word', () => {
    for (const env of [{}, { MOCK_DATA: 'true', NODE_ENV: 'test' }]) {
      const r = resolveStorePosture(env)
      const text = `${storeBannerTitle(r)} ${r.source} ${storeBannerHint(r)}`
      expect(text.toLowerCase()).not.toMatch(/\b(ok|healthy|all clear|running fine)\b/)
      expect(storeBannerTitle(r)).toBeTruthy()
      expect(r.source.length).toBeGreaterThan(20)
    }
  })

  it('carries a machine-readable posture attribute for DOM probes', () => {
    expect(storeBannerAttr(resolveStorePosture({}))).toBe('unconfigured')
    expect(
      storeBannerAttr(resolveStorePosture({ MOCK_DATA: 'true', NODE_ENV: 'test' }))
    ).toBe('demo')
    expect(storeBannerAttr(resolveStorePosture({ REDIS_URL: 'redis://x' }))).toBe(
      'live'
    )
  })

  it('the unconfigured wording names the missing config AND denies measurement', () => {
    // Both halves matter: WHAT to fix, and that nothing on screen is a reading.
    const r = resolveStorePosture({})
    expect(r.source).toMatch(/REDIS_URL/)
    expect(r.source).toMatch(/has not contacted/i)
    expect(r.source).toMatch(/is a measurement of it/i)
  })

  it('the demo wording says the figures are invented', () => {
    const r = resolveStorePosture({ MOCK_DATA: 'true', NODE_ENV: 'test' })
    expect(r.source).toMatch(/invented/i)
  })
})

describe('isUnconfiguredInProduction — the exclusion `demo` had and this posture did not', () => {
  it('production with no store is TRUE — the case the exec plane spent as a licence', () => {
    expect(isUnconfiguredInProduction({ NODE_ENV: 'production' })).toBe(true)
  })

  it('production with a store is FALSE', () => {
    expect(
      isUnconfiguredInProduction({ REDIS_URL: 'redis://x', NODE_ENV: 'production' })
    ).toBe(false)
  })

  it('outside production it is FALSE — unconfigured there is somebody mid-setup', () => {
    expect(isUnconfiguredInProduction({})).toBe(false)
    expect(isUnconfiguredInProduction({ NODE_ENV: 'development' })).toBe(false)
    expect(isUnconfiguredInProduction({ NODE_ENV: 'test' })).toBe(false)
  })

  it('REDIS_URL="" in production is TRUE — present but empty is not a store', () => {
    // The degenerate end that coerces to a falsy default: `REDIS_URL=` in a
    // .env file is a MISSING value that happens to be set.
    expect(isUnconfiguredInProduction({ REDIS_URL: '', NODE_ENV: 'production' })).toBe(
      true
    )
  })

  it('MOCK_DATA=true in production is TRUE — the demo opt-in cannot buy its way out', () => {
    // Fabrication is refused in production, so the posture stays `unconfigured`
    // and the deploy is still misconfigured. An implementation that read the
    // flag before the posture would answer false here.
    expect(
      isUnconfiguredInProduction({ MOCK_DATA: 'true', NODE_ENV: 'production' })
    ).toBe(true)
    expect(
      isUnconfiguredInProduction({ CABINET_DEMO_DATA: 'true', NODE_ENV: 'production' })
    ).toBe(true)
  })

  it('demo outside production is FALSE — it is a mode, not a broken deploy', () => {
    expect(isUnconfiguredInProduction({ MOCK_DATA: 'true', NODE_ENV: 'test' })).toBe(
      false
    )
  })
})
