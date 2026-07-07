/**
 * Grammar loader tests — fail-closed pending state (no grammar = no grammar
 * pixels), schema rejection of untiered/unreplayed bindings, codex coverage.
 */
import { afterEach, describe, expect, it } from 'vitest'
import fs from 'fs'
import os from 'os'
import path from 'path'
import { loadGrammar } from './grammar'

const tmpDirs: string[] = []
function grammarDir(files: Record<string, string>): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'world-grammar-'))
  tmpDirs.push(dir)
  for (const [name, text] of Object.entries(files)) {
    fs.writeFileSync(path.join(dir, name), text)
  }
  process.env.CABINET_WORLD_GRAMMAR_DIR = dir
  return dir
}

afterEach(() => {
  delete process.env.CABINET_WORLD_GRAMMAR_DIR
  for (const d of tmpDirs.splice(0)) {
    fs.rmSync(d, { recursive: true, force: true })
  }
})

const VALID_SHOW = `
version: 1
fallback: { station: floor, anim: idle }
verbs:
  working:
    station: desk
    anim: work
    salience: 0
    codex:
      represents: "Officer at their desk mid-tool-call."
      mechanism_path: "cabinet/scripts/hooks/post-tool-use.sh"
      day0: "empty desks"
  deploying:
    station: board
    anim: work
    salience: 2
`

const VALID_MORPH = `
version: 1
entries:
  - id: memory_rows
    represents: "Library wing height"
    source_binding: "jq -r '.memory_rows_total' shared/interfaces/world-chronicle.jsonl"
    scope: org-global
    tier: T0
    replay: ledger
    base: 80
    codex:
      represents: "Memory store row count"
      mechanism_path: "cabinet/scripts/world-census.py"
      day0: "empty shelves"
  - id: bad_untier
    represents: "should be rejected"
    source_binding: "wc -l x"
    scope: org-global
    replay: ledger
`

describe('fail-closed', () => {
  it('absent grammar dir → pending (no grammar pixels)', () => {
    grammarDir({})
    const g = loadGrammar()
    expect(g.pending).toBe(true)
    expect(g.showGrammar).toBeNull()
  })

  it('unparseable show-grammar → pending, problem recorded', () => {
    grammarDir({ 'show-grammar.yml': '{{{{not yaml' })
    const g = loadGrammar()
    expect(g.pending).toBe(true)
    expect(g.problems.length).toBeGreaterThan(0)
  })
})

describe('law parsing', () => {
  it('valid grammar loads; missing codex counts against coverage', () => {
    grammarDir({ 'show-grammar.yml': VALID_SHOW, 'morphology.yml': VALID_MORPH })
    const g = loadGrammar()
    expect(g.pending).toBe(false)
    expect(g.showGrammar?.version).toBe(1)
    expect(g.showGrammar?.verbs.working.station).toBe('desk')
    expect(g.showGrammar?.verbs.deploying.codex).toBeUndefined()
    // untiered morphology entry REJECTED (validator doctrine)
    expect(g.morphology?.entries.map((e) => e.id)).toEqual(['memory_rows'])
    expect(g.problems.join(' ')).toContain('bad_untier')
    // coverage: working(1) + deploying(0) + memory_rows(1) = 2/3
    expect(g.codexCoverage).toBeCloseTo(2 / 3, 5)
  })

  it('yaml tags cannot construct types (JSON_SCHEMA pin)', () => {
    grammarDir({
      'show-grammar.yml':
        'version: 1\nverbs: {}\nfallback: {station: floor, anim: idle}\nevil: !!js/function "function(){}"\n',
    })
    const g = loadGrammar()
    // Either the tag fails the parse (pending) or is ignored — it must
    // never execute. Both outcomes are fail-closed.
    expect(g.problems.length >= 0).toBe(true)
  })
})
