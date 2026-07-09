/**
 * Killswitch lever two-tap machine — unit suite (T3).
 *
 * The lever is THE one in-world actuator (Captain ruling 2026-07-09); this
 * suite pins the ceremony: arm → 10s auto-expire, second tap fires ONLY
 * with the captain cookie, aborts always disarm, results resolve honestly.
 */
import { describe, expect, it } from 'vitest'
import {
  ARM_EXPIRE_TICKS,
  fallbackCommand,
  LEVER_IDLE,
  leverReduce,
  type LeverState,
} from './lever'

const CAPTAIN = { tick: 100, canActuate: true }
const VISITOR = { tick: 100, canActuate: false }

describe('killswitch lever two-tap machine', () => {
  it('tap 1 arms (never fires)', () => {
    const out = leverReduce(LEVER_IDLE, { type: 'tap' }, CAPTAIN)
    expect(out.state.phase).toBe('armed')
    expect(out.state.armedAtTick).toBe(100)
    expect(out.fire).toBe(false)
  })

  it('tap 2 with the captain cookie fires exactly once', () => {
    const armed = leverReduce(LEVER_IDLE, { type: 'tap' }, CAPTAIN).state
    const out = leverReduce(armed, { type: 'tap' }, CAPTAIN)
    expect(out.fire).toBe(true)
    expect(out.state.phase).toBe('pending')
    // A third tap while pending is ignored (no double-fire).
    const again = leverReduce(out.state, { type: 'tap' }, CAPTAIN)
    expect(again.fire).toBe(false)
    expect(again.state.phase).toBe('pending')
  })

  it('view-only law: without the cookie tap 2 NEVER fires', () => {
    const armed = leverReduce(LEVER_IDLE, { type: 'tap' }, VISITOR).state
    const out = leverReduce(armed, { type: 'tap' }, VISITOR)
    expect(out.fire).toBe(false)
    expect(out.state.phase).toBe('armed') // truth still renders; no act
  })

  it('arming auto-expires after 10s of logical ticks', () => {
    const armed = leverReduce(LEVER_IDLE, { type: 'tap' }, CAPTAIN).state
    const early = leverReduce(
      armed,
      { type: 'tick', tick: 100 + ARM_EXPIRE_TICKS - 1 },
      CAPTAIN
    )
    expect(early.state.phase).toBe('armed')
    const expired = leverReduce(
      armed,
      { type: 'tick', tick: 100 + ARM_EXPIRE_TICKS },
      CAPTAIN
    )
    expect(expired.state.phase).toBe('idle')
    expect(expired.fire).toBe(false)
  })

  it('abort disarms from armed and closes from resolved, never from pending', () => {
    const armed = leverReduce(LEVER_IDLE, { type: 'tap' }, CAPTAIN).state
    expect(leverReduce(armed, { type: 'abort' }, CAPTAIN).state.phase).toBe('idle')
    const pending: LeverState = { phase: 'pending', armedAtTick: null, error: null }
    expect(leverReduce(pending, { type: 'abort' }, CAPTAIN).state.phase).toBe('pending')
  })

  it('results resolve honestly: ok clears, failure carries the exact text', () => {
    const pending: LeverState = { phase: 'pending', armedAtTick: null, error: null }
    expect(leverReduce(pending, { type: 'result', ok: true }, CAPTAIN).state.phase).toBe('ok')
    const failed = leverReduce(
      pending,
      { type: 'result', ok: false, error: 'redis down — run: cabinet/scripts/kill-switch.sh activate' },
      CAPTAIN
    ).state
    expect(failed.phase).toBe('fail')
    expect(failed.error).toContain('kill-switch.sh activate')
    // Stray results outside pending are ignored (no phantom transitions).
    expect(leverReduce(LEVER_IDLE, { type: 'result', ok: true }, CAPTAIN).state.phase).toBe('idle')
  })

  it('re-arming after a result restarts the ceremony from tap 1', () => {
    const okState: LeverState = { phase: 'ok', armedAtTick: null, error: null }
    const out = leverReduce(okState, { type: 'tap' }, CAPTAIN)
    expect(out.state.phase).toBe('armed')
    expect(out.fire).toBe(false)
  })

  it('honest-degradation fallback names the exact CLI command per direction', () => {
    expect(fallbackCommand(false)).toBe('cabinet/scripts/kill-switch.sh activate')
    expect(fallbackCommand(true)).toBe('cabinet/scripts/kill-switch.sh deactivate')
  })
})
