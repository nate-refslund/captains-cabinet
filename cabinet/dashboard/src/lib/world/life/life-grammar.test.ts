/**
 * T2 LIFE — v3 LIFE grammar-block parser tests: fail-closed everywhere
 * (absent → OFF; malformed → problem + OFF; closed enums refused loudly).
 * The fixtures mirror the RATIFIED feat/world-grammar-v3 blocks; the last
 * test parses the REAL repo file so a drift between law and parser fails
 * loudly the moment the v3 grammar is merged.
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'
import { parseLifeGrammar } from './life-grammar'

const CODEX = `codex:
    represents: "x"
    mechanism_path: "cabinet/scripts/hooks/post-tool-use.sh"
    day0: "quiet"`

const FULL = `
version: 3
commute:
  switch_share: 0.6
  switch_evals: 2
  dwell_s: 180
  walk_s: [20, 30]
  bubble: verb_icon
  ${CODEX}
construction:
  quick_small_min: 15
  quick_large_min: 90
  great_hours: 24
  phases: {clearing: 0.25, raising: 0.75, finishing: 1.0}
  site_ledger: "shared/interfaces/world-sites.jsonl"
  ${CODEX}
fauna:
  cat:
    home: wardroom_kettle_counter
    decorative: true
    ${CODEX.replace(/\n {4}/g, '\n      ')}
  birds:
    home: sky
    decorative: true
    ${CODEX.replace(/\n {4}/g, '\n      ')}
apprentices:
  cap_per_officer: 3
  ${CODEX}
`

describe('parseLifeGrammar — the ratified v3 LIFE contract', () => {
  it('parses the full lawful document with zero problems', () => {
    const g = parseLifeGrammar(FULL)
    expect(g.problems).toEqual([])
    expect(g.commute).toMatchObject({
      switchShare: 0.6,
      switchEvals: 2,
      dwellS: 180,
      walkS: [20, 30],
      bubble: 'verb_icon',
    })
    expect(g.construction).toMatchObject({
      quickSmallMin: 15,
      quickLargeMin: 90,
      greatHours: 24,
      phases: { clearing: 0.25, raising: 0.75, finishing: 1.0 },
      siteLedger: 'shared/interfaces/world-sites.jsonl',
    })
    expect(g.fauna?.cat).toMatchObject({ home: 'wardroom_kettle_counter' })
    expect(g.fauna?.birds).toMatchObject({ home: 'sky' })
    expect(g.apprentices).toMatchObject({ capPerOfficer: 3 })
  })

  it('absent blocks parse ABSENT — every behavior defaults OFF', () => {
    const g = parseLifeGrammar('version: 2\nverbs: {}\n')
    expect(g.commute).toBeUndefined()
    expect(g.construction).toBeUndefined()
    expect(g.fauna).toBeUndefined()
    expect(g.apprentices).toBeUndefined()
    expect(g.problems).toEqual([])
  })

  it('bubble is a CLOSED enum — anything but verb_icon refuses the block', () => {
    const g = parseLifeGrammar(FULL.replace('bubble: verb_icon', 'bubble: free_text'))
    expect(g.commute).toBeUndefined()
    expect(
      g.problems.some((p) => p.includes('bubble must be "verb_icon"'))
    ).toBe(true)
  })

  it('fauna claiming to be non-decorative is refused (population law)', () => {
    const g = parseLifeGrammar(
      FULL.replace('home: sky\n    decorative: true', 'home: sky\n    decorative: false')
    )
    expect(g.fauna?.birds).toBeUndefined()
    expect(g.fauna?.cat).toBeDefined()
    expect(g.problems.some((p) => p.includes('fauna.birds: decorative'))).toBe(
      true
    )
  })

  it('non-ascending construction phases are refused', () => {
    const g = parseLifeGrammar(
      FULL.replace(
        'phases: {clearing: 0.25, raising: 0.75, finishing: 1.0}',
        'phases: {clearing: 0.8, raising: 0.75, finishing: 1.0}'
      )
    )
    expect(g.construction).toBeUndefined()
  })

  it('missing codex loads the block but flags the problem (coverage law)', () => {
    const noCodex = FULL.replace(/ *codex:\n(?: +.*\n)+/g, '')
    const g = parseLifeGrammar(noCodex)
    expect(g.commute).toBeDefined()
    expect(g.problems.some((p) => p.includes('commute: codex'))).toBe(true)
  })

  it('a sub-dominant switch_share is invalid (could never be dominant)', () => {
    const g = parseLifeGrammar(FULL.replace('switch_share: 0.6', 'switch_share: 0.3'))
    expect(g.commute).toBeUndefined()
  })

  it('a descending walk_s band is refused', () => {
    const g = parseLifeGrammar(FULL.replace('walk_s: [20, 30]', 'walk_s: [30, 20]'))
    expect(g.commute).toBeUndefined()
  })

  it('unparseable yaml → everything OFF with one honest problem', () => {
    const g = parseLifeGrammar('{ unclosed: [')
    expect(g.commute).toBeUndefined()
    expect(g.problems[0]).toContain('unparseable')
  })

  it('the REAL repo show-grammar.yml parses without contract drift', () => {
    // life/ → world → lib → src → dashboard → cabinet → repo root
    const repo = path.resolve(__dirname, '..', '..', '..', '..', '..', '..')
    const p = path.join(repo, 'cabinet', 'world', 'show-grammar.yml')
    const g = parseLifeGrammar(fs.readFileSync(p, 'utf8'))
    // Pre-merge (v2): all blocks honestly absent, zero problems.
    // Post-merge (v3): all four blocks present, zero problems.
    expect(g.problems).toEqual([])
    const blocks = [g.commute, g.construction, g.fauna, g.apprentices]
    const present = blocks.filter(Boolean).length
    expect(present === 0 || present === 4).toBe(true)
  })
})
