/**
 * The rail's two laws: every stage has exactly one stop, and the rail never
 * goes backwards.
 *
 * WHY BOTH SENSORS ARE PROVEN TO FIRE HERE. The defect this file exists to
 * catch shipped, was rendered to the Captain, and was reported as being stuck —
 * so "the new mapping passes" is worth very little on its own. Every arm below
 * is therefore run TWICE where it can be: once against the live mapping, and
 * once against `LEGACY_PHASE_INDEX`, the exact mapping this replaced, which
 * must FAIL. A monotonic test that has never seen a non-monotonic mapping is a
 * test of nothing.
 *
 * THE REGISTRY IS PINNED TO THE CORE, not to a copy of it. `journey.STAGES` in
 * framework/onboarding/journey.py is parsed here, and the core's own suite
 * proves that tuple matches the card builder's live branches
 * (`test_every_declared_stage_renders_its_own_card`). So a stage added to the
 * product with no stop on the rail turns this red, in the same way the action
 * vocabulary is held by parity.test.ts.
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  FLOW_STOPS,
  FORWARD_PATH,
  firstReversal,
  OFF_RAIL,
  STAGE_STOPS,
  stopIndex,
} from './flow-rail'
import type { WizardStepId } from './wizard'

// <root>/cabinet/dashboard/src/lib/onboarding → five levels up = <root>
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..', '..')
const CORE = path.join(REPO_ROOT, 'framework', 'onboarding', 'journey.py')

/**
 * THE MAPPING THIS REPLACED, frozen. Six phases, and `orientation_offered`
 * mapped back to phase three while `dividend_ready` sat at phase five — so
 * pressing continue on the first result moved the operator's rail two stops
 * BACKWARD. Kept verbatim (from cabinet/dashboard/src/lib/onboarding/wizard.ts
 * at 268ccdd, `activePhaseIndex`) for one purpose: proving the monotonic arm
 * below can fail. Never imported by product code.
 */
const LEGACY_PHASE_INDEX = (stage: string, step: WizardStepId): number => {
  if (stage === 'welcome') {
    if (step === 'role') return 0
    if (step === 'dream') return 1
    if (step === 'start') return 2
    return 3 // window | discover — the first-window phase
  }
  if (stage === 'charter_pending') return 4
  if (stage === 'dividend_ready') return 5
  if (stage === 'orientation_offered') return 3
  return -1
}

const PLACEHOLDER = /\b(tbd|todo|later|not (yet )?wired|coming soon|n\/?a)\b/i

/**
 * The core's declared stage list. Throws rather than returning a partial set:
 * a parser that silently drops what it cannot read would let the registry
 * diverge while this file went green — the failure class this repo has paid for
 * more than any other.
 */
function coreStages(): string[] {
  const source = fs.readFileSync(CORE, 'utf8')
  const block = source.match(/^STAGES: tuple\[str, \.\.\.\] = \(\n([\s\S]*?)^\)$/m)
  if (!block) throw new Error('no top-level STAGES tuple in framework/onboarding/journey.py')
  const stages: string[] = []
  for (const raw of block[1].split('\n')) {
    const line = raw.trim()
    if (!line || line.startsWith('#')) continue
    const quoted = line.match(/^"([a-z_]+)",$/)
    if (quoted) {
      stages.push(quoted[1])
      continue
    }
    // A stage named through a constant — `COMPLETE_STAGE,` — resolved from its
    // own definition rather than assumed, so a rename of the constant's VALUE
    // cannot slip past.
    const named = line.match(/^([A-Z_]+),$/)
    if (named) {
      const def = source.match(new RegExp(`^${named[1]} = "([a-z_]+)"$`, 'm'))
      if (!def) throw new Error(`STAGES names ${named[1]}, which has no top-level definition`)
      stages.push(def[1])
      continue
    }
    throw new Error(`unreadable line in the core's STAGES tuple: ${line}`)
  }
  if (!stages.length) throw new Error("the core's STAGES tuple parsed as empty")
  return stages
}

describe('the parser that guards the registry', () => {
  it('reads the core, including a stage named through a constant', () => {
    const stages = coreStages()
    expect(stages).toContain('welcome')
    expect(stages).toContain('complete') // written as COMPLETE_STAGE in the tuple
    expect(stages).toContain('orientation_offered')
    expect(new Set(stages).size).toBe(stages.length)
  })
})

describe('registry parity — every stage has exactly one stop', () => {
  it('covers every stage the core can render, and invents none', () => {
    const stages = new Set(coreStages())
    const mapped = new Set([...Object.keys(STAGE_STOPS), ...Object.keys(OFF_RAIL)])
    expect([...mapped].filter((s) => !stages.has(s))).toEqual([])
    expect([...stages].filter((s) => !mapped.has(s))).toEqual([])
  })

  it('never puts a stage both on and off the rail', () => {
    const both = Object.keys(STAGE_STOPS).filter((stage) => stage in OFF_RAIL)
    expect(both).toEqual([])
  })

  it('maps every on-rail stage to a real stop', () => {
    for (const [stage, stop] of Object.entries(STAGE_STOPS)) {
      expect(Number.isInteger(stop), stage).toBe(true)
      expect(stop, stage).toBeGreaterThanOrEqual(0)
      expect(stop, stage).toBeLessThan(FLOW_STOPS.length)
    }
  })

  it('gives every off-rail stage a real reason, not a filed to-do', () => {
    for (const [stage, why] of Object.entries(OFF_RAIL)) {
      expect(why.length, stage).toBeGreaterThan(20)
      expect(PLACEHOLDER.test(why), `${stage}: ${why}`).toBe(false)
    }
    for (const stage of Object.keys(OFF_RAIL)) {
      expect(stopIndex(stage, 'role'), stage).toBe(-1)
    }
  })

  it('is four stops: You, Access, First look, Done', () => {
    expect(FLOW_STOPS.map((stop) => stop.label)).toEqual([
      'You',
      'Access',
      'First look',
      'Done',
    ])
  })
})

describe('the rail never goes backwards', () => {
  it('is monotonic along the whole forward path', () => {
    expect(firstReversal(stopIndex)).toBeNull()
  })

  it('THE SENSOR FIRES: the mapping this replaced is NOT monotonic', () => {
    const reversal = firstReversal(LEGACY_PHASE_INDEX)
    expect(reversal).not.toBeNull()
    // …and it is exactly the transition the Captain hit: pressing continue on
    // the first result took him from phase five back to phase three. (`complete`
    // does not appear in this pair because the legacy mapping had never heard
    // of it — there was no terminal stage to map, which is the other half of
    // the same defect.)
    expect(reversal).toEqual({
      from: 'dividend_ready',
      to: 'orientation_offered',
      fromStop: 5,
      toStop: 3,
    })
  })

  it('the forward path walks the real transitions, ending at the arrival', () => {
    const stages = FORWARD_PATH.map(([stage]) => stage)
    expect(stages).toContain('welcome')
    expect(stages).toContain('charter_pending')
    expect(stages).toContain('dividend_ready')
    expect(stages).toContain('complete')
    // The legacy terminal stage is on the path deliberately: it is where the
    // reversal used to happen, so dropping it would retire the evidence.
    expect(stages).toContain('orientation_offered')
  })
})

describe('where each stage lights up', () => {
  it('puts the three questions on You and the folder branch on Access', () => {
    expect(stopIndex('welcome', 'role')).toBe(0)
    expect(stopIndex('welcome', 'dream')).toBe(0)
    expect(stopIndex('welcome', 'start')).toBe(0)
    expect(stopIndex('welcome', 'window')).toBe(1)
    expect(stopIndex('welcome', 'discover')).toBe(1)
  })

  it('puts the Charter on Access, the result on First look, the ending on Done', () => {
    expect(stopIndex('charter_pending', 'role')).toBe(1)
    expect(stopIndex('dividend_ready', 'role')).toBe(2)
    expect(stopIndex('complete', 'role')).toBe(3)
    expect(stopIndex('orientation_offered', 'role')).toBe(3)
  })

  it('a stale client step cannot drag a later stage backwards', () => {
    // The step only refines the position INSIDE welcome; every server stage
    // ignores it. This is the structural half of the monotonic law.
    for (const step of ['role', 'dream', 'start', 'window', 'discover'] as WizardStepId[]) {
      expect(stopIndex('dividend_ready', step)).toBe(2)
      expect(stopIndex('complete', step)).toBe(3)
    }
  })

  it('hides rather than lies for a stage it has never heard of', () => {
    expect(stopIndex('a_stage_from_the_future', 'role')).toBe(-1)
  })
})
