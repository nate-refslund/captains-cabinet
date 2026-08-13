import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { EventEmitter } from 'node:events'
import { afterEach, describe, expect, it, vi } from 'vitest'

const { spawnMock } = vi.hoisted(() => ({ spawnMock: vi.fn() }))
vi.mock('node:child_process', () => ({ spawn: spawnMock }))

import {
  ACTIONS,
  applyOnboardingAction,
  invocation,
  OnboardingBridgeError,
  refusalDetail,
} from './bridge'

/**
 * A stand-in for the Python core that prints one canned response.
 *
 * Real arms below need to see what CROSSES the boundary — the request bytes on
 * stdin and the refusal fields coming back — and spawning the actual
 * interpreter would write into the running checkout's onboarding state. The
 * protocol this fake implements (fixed argv, JSON on stdin, one JSON object on
 * stdout) is pinned against the real core by
 * framework/onboarding/tests/test_journey_cli_surface.py, so the two halves
 * meet at a tested contract rather than at an assumption.
 */
function stubCore(response: unknown, exitCode = 0): { stdin: string } {
  const seen = { stdin: '' }
  spawnMock.mockImplementation(() => {
    const child = new EventEmitter() as EventEmitter & {
      stdout: EventEmitter & { setEncoding: () => void }
      stderr: EventEmitter & { setEncoding: () => void }
      stdin: { end: (value?: string) => void }
      kill: () => void
    }
    child.stdout = Object.assign(new EventEmitter(), { setEncoding: () => undefined })
    child.stderr = Object.assign(new EventEmitter(), { setEncoding: () => undefined })
    child.kill = () => undefined
    child.stdin = {
      end: (value?: string) => {
        seen.stdin = value ?? ''
        setImmediate(() => {
          child.stdout.emit('data', JSON.stringify(response))
          child.emit('close', exitCode)
        })
      },
    }
    return child
  })
  return seen
}

const OK = { ok: true, state: { revision: 1 }, card: { revision: 1 } }

afterEach(() => {
  spawnMock.mockReset()
})

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

// The read lane resolves a connector's credential_env NAME against the spawned
// core's environment. A credential the operator JUST connected was written to
// cabinet/.env after this dashboard started, so it is not in process.env — and
// without reading the file fresh at spawn, the very sweep that connect triggers
// reports it credential_absent. These arms fail against a bridge that only
// forwards process.env.
describe('the bridge feeds the core the freshly-declared credentials', () => {
  it('reads cabinet/.env at spawn so a just-connected credential reaches the core', async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'bridge-env-'))
    const envFile = path.join(dir, '.env')
    fs.writeFileSync(envFile, 'REST_API_TOKEN=freshly-connected-value\nUNRELATED=1\n')
    const previous = process.env.CABINET_ENV_PATH
    process.env.CABINET_ENV_PATH = envFile
    try {
      stubCore(OK)
      await applyOnboardingAction({ action: 'gather_connectors' }, 'dashboard')
      const env = (spawnMock.mock.calls[0]![2] as { env: Record<string, string> }).env
      expect(env.REST_API_TOKEN).toBe('freshly-connected-value')
      // The env NAME the read lane will resolve is present; the credential never
      // needed a dashboard restart to become readable.
    } finally {
      process.env.CABINET_ENV_PATH = previous
      fs.rmSync(dir, { recursive: true, force: true })
    }
  })

  it('is unbothered by an absent env file (a fresh hatch has none)', async () => {
    const previous = process.env.CABINET_ENV_PATH
    process.env.CABINET_ENV_PATH = path.join(os.tmpdir(), `no-such-${Date.now()}`, '.env')
    try {
      stubCore(OK)
      await expect(
        applyOnboardingAction({ action: 'gather_connectors' }, 'dashboard')
      ).resolves.toBeDefined()
    } finally {
      process.env.CABINET_ENV_PATH = previous
    }
  })
})

describe('the salience answer crosses the boundary', () => {
  it('carries the pick, the typed name and the merge to the core', async () => {
    const seen = stubCore(OK)
    await applyOnboardingAction(
      { action: 'answer_salience', choice: 'other', name: 'Blue Harbour', same_as: ['redanchor'] },
      'dashboard'
    )
    const sent = JSON.parse(seen.stdin)
    expect(sent.action).toBe('answer_salience')
    expect(sent.choice).toBe('other')
    expect(sent.name).toBe('Blue Harbour')
    expect(sent.same_as).toEqual(['redanchor'])
    expect(sent.surface).toBe('dashboard')
  })

  it('lets a BARE answer through so the CORE refuses it, not this gate', async () => {
    // The distinction is the fix. `action_invalid` is this file saying the
    // operator chose something that does not exist; `salience_choice_required`
    // is the core saying which of the candidates it is still waiting for. Only
    // the second is an answerable sentence, and it only arrives if the request
    // is allowed to cross.
    const seen = stubCore({ ok: false, code: 'salience_choice_required', error: 'Pick one of the candidates, or name your own.' })
    await expect(applyOnboardingAction({ action: 'answer_salience' }, 'dashboard'))
      .rejects.toMatchObject({ code: 'salience_choice_required' })
    expect(JSON.parse(seen.stdin).action).toBe('answer_salience')
  })

  it('bounds the payload before it crosses, without pre-empting the core', () => {
    expect(() => applyOnboardingAction({ action: 'answer_salience', choice: 'x'.repeat(301) }, 'dashboard'))
      .toThrow(/not one of the candidates/)
    expect(() => applyOnboardingAction({ action: 'answer_salience', choice: 'other', name: 'x'.repeat(2_001) }, 'dashboard'))
      .toThrow(/A word or two is enough/)
    expect(() => applyOnboardingAction(
      { action: 'answer_salience', choice: 'other', name: 'x', same_as: Array(65).fill('a') },
      'dashboard'
    )).toThrow(/too many names/)
  })

  it('carries the stated window relation on propose_window', async () => {
    const seen = stubCore(OK)
    await applyOnboardingAction(
      { action: 'propose_window', source: '/tmp/x', purpose: 'p', salience_relation: 'elsewhere' },
      'dashboard'
    )
    expect(JSON.parse(seen.stdin).salience_relation).toBe('elsewhere')
  })
})

describe('a refusal may carry allowlisted material and nothing else', () => {
  it('takes target, window and relations off a core refusal', async () => {
    stubCore({
      ok: false,
      code: 'salience_window_off_target',
      error: 'You pointed me at blueharbour…',
      detail: {
        target: 'blueharbour',
        window: 'quarterly-tax-returns',
        relations: ['elsewhere', 'same_thing'],
      },
    })
    await expect(applyOnboardingAction({ action: 'propose_window', source: '/tmp/x' }, 'dashboard'))
      .rejects.toMatchObject({
        code: 'salience_window_off_target',
        detail: {
          target: 'blueharbour',
          window: 'quarterly-tax-returns',
          relations: ['elsewhere', 'same_thing'],
        },
      })
  })

  it('is empty when the core sends no detail — the normal case today', async () => {
    // `journey._cli` prints {ok, code, error} and drops JourneyError.detail
    // (measured 2026-08-02), so this is what production actually returns. The
    // card must therefore build its fix-up without one — see journey-card.
    stubCore({ ok: false, code: 'salience_window_off_target', error: 'no detail here' })
    const caught = await applyOnboardingAction(
      { action: 'propose_window', source: '/tmp/x' },
      'dashboard'
    ).then(() => null, (error: OnboardingBridgeError) => error)
    expect(caught, 'a refusal must reject, never resolve').toBeInstanceOf(OnboardingBridgeError)
    expect(caught!.detail).toEqual({})
  })
})

describe('refusalDetail — the allowlist itself', () => {
  it('drops every key it does not name', () => {
    expect(refusalDetail({
      target: 'a', window: 'b', relations: ['c'],
      target_words: ['leak'], stack: '/private/secret', root: '/home/nate',
    })).toEqual({ target: 'a', window: 'b', relations: ['c'] })
  })

  it('bounds strings and list length so a refusal cannot ride out a payload', () => {
    const out = refusalDetail({
      target: 'x'.repeat(5_000),
      relations: Array.from({ length: 40 }, (_, i) => `r${i}`),
    })
    expect(out.target!.length).toBe(300)
    expect(out.relations!.length).toBe(8)
  })

  it('is degenerate-safe: absent, null, array and wrong-typed fields all give {}', () => {
    expect(refusalDetail(undefined)).toEqual({})
    expect(refusalDetail(null)).toEqual({})
    expect(refusalDetail(['target'])).toEqual({})
    expect(refusalDetail('target')).toEqual({})
    expect(refusalDetail({ target: 42, window: {}, relations: 'same_thing' })).toEqual({})
    expect(refusalDetail({ target: '   ', relations: [] })).toEqual({})
  })

  it('drops non-string members rather than passing them through a list', () => {
    expect(refusalDetail({ relations: ['same_thing', 7, null, { evil: 1 }] }))
      .toEqual({ relations: ['same_thing'] })
  })
})

describe('the bridge action set', () => {
  // Whole-set equality with the Python dispatch chain is parity.test.ts's job.
  // This arm is the one the salience dead end needed: the gate that refused the
  // action BEFORE the core saw it now admits it.
  it('admits the ranked answer the card offers', () => {
    expect(ACTIONS.has('answer_salience')).toBe(true)
  })
})
