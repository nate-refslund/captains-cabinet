/**
 * T2 LIFE — v3 LIFE grammar-block parser tests: fail-closed everywhere
 * (absent → OFF; malformed → problem + OFF; closed enums refused loudly).
 * This parser IS the contract the feat/world-grammar-v3 PR fulfils.
 */
import { describe, expect, it } from 'vitest'
import { parseLifeGrammar } from './life-grammar'

const CODEX = `
      codex:
        represents: "x"
        mechanism_path: "cabinet/scripts/hooks/post-tool-use.sh"
        day0: "quiet"`

const FULL = `
version: 3
commute:
  window_s: 150
  half_life_s: 75
  eval_every_s: 15
  switch_share: 0.6
  switch_evals: 2
  min_dwell_s: 180
  bubble: pixel
${CODEX.replace(/ {6}/g, '  ')}
sites:
  quick_small_min: 15
  quick_large_min: 90
  great_h: 24
  crew_base: 4
${CODEX.replace(/ {6}/g, '  ')}
fauna:
  kinds: [bird, butterfly, fish, cat, dog]
  day_only: [bird, butterfly]
${CODEX.replace(/ {6}/g, '  ')}
apprentices:
  spawn_verb: tool.call
  spawn_tools: [Agent, Task]
  end_verb: crew.completed
  ttl_ticks: 4800
  cap: 4
${CODEX.replace(/ {6}/g, '  ')}
`

describe('parseLifeGrammar — the v3 LIFE contract', () => {
  it('parses the full lawful document with zero problems', () => {
    const g = parseLifeGrammar(FULL)
    expect(g.problems).toEqual([])
    expect(g.commute).toMatchObject({
      windowS: 150,
      halfLifeS: 75,
      switchShare: 0.6,
      switchEvals: 2,
      minDwellS: 180,
      bubble: 'pixel',
    })
    expect(g.sites).toMatchObject({ quickSmallMin: 15, greatH: 24, crewBase: 4 })
    expect(g.fauna?.kinds).toContain('cat')
    expect(g.fauna?.dayOnly).toEqual(['bird', 'butterfly'])
    expect(g.apprentices).toMatchObject({
      spawnVerb: 'tool.call',
      endVerb: 'crew.completed',
      ttlTicks: 4800,
      cap: 4,
    })
  })

  it('absent blocks parse ABSENT — every behavior defaults OFF', () => {
    const g = parseLifeGrammar('version: 2\nverbs: {}\n')
    expect(g.commute).toBeUndefined()
    expect(g.sites).toBeUndefined()
    expect(g.fauna).toBeUndefined()
    expect(g.apprentices).toBeUndefined()
    expect(g.problems).toEqual([])
  })

  it('bubble is a CLOSED enum — anything but pixel refuses the block', () => {
    const g = parseLifeGrammar(
      FULL.replace('bubble: pixel', 'bubble: dom')
    )
    expect(g.commute).toBeUndefined()
    expect(g.problems.some((p) => p.includes('bubble must be "pixel"'))).toBe(
      true
    )
  })

  it('unknown fauna species are refused, never rendered', () => {
    const g = parseLifeGrammar(
      FULL.replace('[bird, butterfly, fish, cat, dog]', '[bird, unicorn]')
    )
    expect(g.fauna?.kinds).toEqual(['bird'])
    expect(g.problems.some((p) => p.includes('unknown kind unicorn'))).toBe(true)
  })

  it('missing codex loads the block but flags the problem (coverage law)', () => {
    const noCodex = FULL.replace(/ {2}codex:\n(?: {4}.*\n)+/g, '')
    const g = parseLifeGrammar(noCodex)
    expect(g.commute).toBeDefined()
    expect(g.problems.some((p) => p.includes('commute: codex'))).toBe(true)
  })

  it('a sub-dominant switch_share is invalid (could never be dominant)', () => {
    const g = parseLifeGrammar(FULL.replace('switch_share: 0.6', 'switch_share: 0.3'))
    expect(g.commute).toBeUndefined()
  })

  it('unparseable yaml → everything OFF with one honest problem', () => {
    const g = parseLifeGrammar(':\n  - {')
    expect(g.commute).toBeUndefined()
    expect(g.problems[0]).toContain('unparseable')
  })
})
