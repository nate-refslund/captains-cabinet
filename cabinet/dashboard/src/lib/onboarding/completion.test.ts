import { afterEach, describe, it, expect } from 'vitest'
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { isOnboardingComplete } from './completion'

const dirs: string[] = []

function stateFileWith(contents: string): string {
  const dir = mkdtempSync(join(tmpdir(), 'onboarding-state-'))
  dirs.push(dir)
  const path = join(dir, 'state.json')
  writeFileSync(path, contents)
  process.env.ONBOARDING_STATE_PATH = path
  return path
}

afterEach(() => {
  delete process.env.ONBOARDING_STATE_PATH
  for (const d of dirs.splice(0)) rmSync(d, { recursive: true, force: true })
})

describe('isOnboardingComplete — the /onboarding redirect signal', () => {
  it('NO state file → not complete (onboarding never started)', async () => {
    process.env.ONBOARDING_STATE_PATH = join(tmpdir(), 'does-not-exist', 'state.json')
    expect(await isOnboardingComplete()).toBe(false)
  })

  it('ratified charter + a first dividend → complete (renders home)', async () => {
    stateFileWith(
      JSON.stringify({
        stage: 'dividend_ready',
        charter: { status: 'ratified', ratified_at: '2026-08-01T00:00:00Z', hash: 'h', payload: {} },
        first_dividend: { finding: 'one cited useful thing' },
      })
    )
    expect(await isOnboardingComplete()).toBe(true)
  })

  it('charter still pending → not complete', async () => {
    stateFileWith(
      JSON.stringify({
        stage: 'charter_pending',
        charter: { status: 'proposed', hash: 'h', payload: {} },
        first_dividend: null,
      })
    )
    expect(await isOnboardingComplete()).toBe(false)
  })

  it('purged (fresh state, no charter, no dividend) → not complete', async () => {
    // What framework.onboarding.journey._fresh_state(stage="purged") writes.
    stateFileWith(
      JSON.stringify({ stage: 'purged', charter: null, first_dividend: null })
    )
    expect(await isOnboardingComplete()).toBe(false)
  })

  it('ratified charter but NO dividend yet → not complete (both are required)', async () => {
    stateFileWith(
      JSON.stringify({
        stage: 'dividend_ready',
        charter: { status: 'ratified', hash: 'h', payload: {} },
        first_dividend: null,
      })
    )
    expect(await isOnboardingComplete()).toBe(false)
  })

  it('unreadable/blank state → not complete (never assume done)', async () => {
    stateFileWith('{ this is not valid json')
    expect(await isOnboardingComplete()).toBe(false)
  })
})
