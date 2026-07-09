/**
 * Weather layer suite (T1) — real-signal binding truth table, hysteresis,
 * storm immediacy (killswitch never lags), deterministic rain particles.
 */
import { describe, expect, it } from 'vitest'
import {
  DOCTOR_STALE_SECS,
  WEATHER_HOLD_EVALS,
  initialWeather,
  rainDrops,
  weatherStep,
  weatherTarget,
  type WeatherSignals,
} from './weather'

const GREEN: WeatherSignals = {
  killswitch: false,
  doctorAgeSecs: 600,
  doctorGreen: true,
  probesOk: true,
}

describe('signal → weather truth table (Captain ruling: exact sources)', () => {
  it('sun = green doctor + passing probes', () => {
    const t = weatherTarget(GREEN)
    expect(t.kind).toBe('sun')
    expect(t.why).toContain('GREEN')
  })
  it('storm = killswitch, overriding everything', () => {
    const t = weatherTarget({ ...GREEN, killswitch: true, doctorGreen: null })
    expect(t.kind).toBe('storm')
    expect(t.why).toContain('cabinet:killswitch')
  })
  it('fog = heartbeat absent / stale >26h / verdict unknown (unmeasured)', () => {
    expect(weatherTarget({ ...GREEN, doctorAgeSecs: null }).kind).toBe('fog')
    expect(weatherTarget({ ...GREEN, doctorAgeSecs: DOCTOR_STALE_SECS + 1 }).kind).toBe('fog')
    expect(weatherTarget({ ...GREEN, doctorGreen: null }).kind).toBe('fog')
    expect(weatherTarget({ ...GREEN, doctorAgeSecs: null }).why).toContain('heartbeat absent')
  })
  it('rain = DEAD services or failed probes (elevated incident rate)', () => {
    expect(weatherTarget({ ...GREEN, doctorGreen: false }).kind).toBe('rain')
    expect(weatherTarget({ ...GREEN, probesOk: false }).kind).toBe('rain')
  })
  it('no probe data + green doctor is still sun — with the honest why', () => {
    const t = weatherTarget({ ...GREEN, probesOk: null })
    expect(t.kind).toBe('sun')
    expect(t.why).toContain('no probe data')
  })
})

describe('hysteresis (weather never flaps; storm is immediate)', () => {
  it('non-storm transitions hold WEATHER_HOLD_EVALS consecutive evals', () => {
    let s = initialWeather()
    s = weatherStep(s, weatherTarget(GREEN))
    expect(s.kind).toBe('sun')
    s = weatherStep(s, weatherTarget({ ...GREEN, doctorGreen: false }))
    expect(s.kind).toBe('sun') // one rainy eval — hold
    s = weatherStep(s, weatherTarget({ ...GREEN, doctorGreen: false }))
    expect(s.kind).toBe('rain') // second consecutive → transition
  })
  it('a one-eval blip never changes the sky', () => {
    let s = initialWeather()
    s = weatherStep(s, weatherTarget(GREEN))
    s = weatherStep(s, weatherTarget({ ...GREEN, probesOk: false }))
    s = weatherStep(s, weatherTarget(GREEN))
    s = weatherStep(s, weatherTarget({ ...GREEN, probesOk: false }))
    expect(s.kind).toBe('sun')
  })
  it('storm enters AND clears immediately (killswitch truth never lags)', () => {
    let s = initialWeather()
    s = weatherStep(s, weatherTarget(GREEN))
    s = weatherStep(s, weatherTarget({ ...GREEN, killswitch: true }))
    expect(s.kind).toBe('storm') // no hold on the way in
    s = weatherStep(s, weatherTarget(GREEN))
    expect(s.kind).toBe('sun') // no hold on the way out
  })
  it('hold constant matches the law', () => {
    expect(WEATHER_HOLD_EVALS).toBe(2)
  })
})

describe('deterministic rain', () => {
  it('same tick → byte-identical particle field (two runs)', () => {
    const a = rainDrops(1234, 64, 960, 720)
    const b = rainDrops(1234, 64, 960, 720)
    expect(a).toEqual(b)
    expect(a).toHaveLength(64)
  })
  it('different ticks → different fields (seeded per tick, no wall clock)', () => {
    const a = rainDrops(1234, 64, 960, 720)
    const c = rainDrops(1235, 64, 960, 720)
    expect(a).not.toEqual(c)
  })
  it('drops stay inside the viewport; degenerate sizes are safe', () => {
    for (const d of rainDrops(7, 32, 100, 50)) {
      expect(d.x).toBeGreaterThanOrEqual(0)
      expect(d.x).toBeLessThan(100)
      expect(d.y).toBeGreaterThanOrEqual(0)
      expect(d.y).toBeLessThan(50)
      expect(d.len).toBeGreaterThanOrEqual(2)
      expect(d.len).toBeLessThanOrEqual(5)
    }
    expect(rainDrops(7, 0, 960, 720)).toEqual([])
    expect(rainDrops(7, 4, 0, 0)).toHaveLength(4) // never divides by zero
  })
})
