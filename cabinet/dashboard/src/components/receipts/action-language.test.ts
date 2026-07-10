/**
 * action-language parity — the TS mirror in action-language.ts must be
 * IDENTICAL to `HUMAN_PHRASES` in `framework/frontdoor/action_language.py`
 * (the receipt grammar's source of truth, perfect-cabinet Wave B).
 *
 * The dashboard cannot import Python, so the map is mirrored in TS and THIS
 * test is the drift tripwire: it parses the Python dict literal at test time
 * and asserts key-for-key, phrase-for-phrase equality. A missing Python file
 * FAILS (parity cannot be verified — that is drift, not a skip), so CI stays
 * honest whichever side moves first.
 *
 * Plus behavior pins for phraseFor: kind-first (the executor step identity),
 * action_type fallback, the visible de-underscore fallback for unmapped ids
 * (mirroring `human_phrase`), and a prototype-chain guard.
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import { HUMAN_PHRASES, phraseFor } from './action-language'

// <root>/cabinet/dashboard/src/components/receipts → five levels up = <root>
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..', '..')
const PY_MAP = path.join(REPO_ROOT, 'framework', 'frontdoor', 'action_language.py')

/**
 * Extract the first module-level dict assignment whose name contains PHRASE
 * (HUMAN_PHRASES / …) as a plain string→string record.
 *
 * FULL-CONSUMPTION RULE: every non-blank, non-comment line of the dict body
 * MUST parse as a single-line `'key': 'value',` entry, or this THROWS
 * listing the offenders. A tripwire that silently drops what it cannot read
 * is no tripwire: a future entry wrapped across two lines (79-col
 * formatting) or built by implicit string concatenation would vanish from
 * pyMap, and if the TS mirror also lacked it the parity test would stay
 * green while the real maps diverged. Failing loudly turns that hole into a
 * visible seam (fix: keep map entries single-line in action_language.py, or
 * teach this parser the new shape).
 */
const ENTRY_RE = /^\s*(['"])(.+?)\1\s*:\s*(['"])(.*?)\3\s*,?\s*(?:#.*)?$/
const COMMENT_RE = /^\s*#/

function parsePythonPhraseMap(source: string): Record<string, string> {
  const assignment = source.match(
    /^([A-Z][A-Z0-9_]*PHRASE[A-Z0-9_]*)\s*(?::[^=\n]+)?=\s*\{([\s\S]*?)^\}/m
  )
  if (!assignment) {
    throw new Error(
      'no module-level *PHRASE* dict found in action_language.py — ' +
        'the parity test needs the phrase map as a literal dict'
    )
  }
  const body = assignment[2]
  const entries: Record<string, string> = {}
  const unparseable: string[] = []
  for (const line of body.split('\n')) {
    if (!line.trim() || COMMENT_RE.test(line)) continue
    const m = line.match(ENTRY_RE)
    if (!m) {
      unparseable.push(line.trim())
      continue
    }
    entries[m[2]] = m[4]
  }
  if (unparseable.length > 0) {
    throw new Error(
      'unparseable phrase-map line(s) — every non-comment line of the dict ' +
        "body must be a single-line 'key': 'value' entry, or it would be " +
        'silently missing from the parity check (that is a hole in the ' +
        'drift tripwire, not a formatting nit):\n  ' +
        unparseable.join('\n  ')
    )
  }
  return entries
}

describe('parity with framework/frontdoor/action_language.py', () => {
  const exists = fs.existsSync(PY_MAP)

  it('the python phrase map exists (receipt-grammar seam)', () => {
    expect(
      exists,
      `expected ${PY_MAP} — the receipt-grammar area ships the phrase map ` +
        'there; the TS mirror in action-language.ts cannot be parity-checked ' +
        'without it (a missing source IS drift)'
    ).toBe(true)
  })

  it.skipIf(!exists)('TS mirror is identical to HUMAN_PHRASES', () => {
    const pyMap = parsePythonPhraseMap(fs.readFileSync(PY_MAP, 'utf8'))
    expect(
      Object.keys(pyMap).length,
      'parsed zero entries — the python map is not a plain literal dict'
    ).toBeGreaterThan(0)
    expect(HUMAN_PHRASES).toEqual(pyMap)
  })
})

describe('the parser itself (so a green parity run is trustworthy)', () => {
  it('parses literal dicts with comments, both quote styles, apostrophes', () => {
    const parsed = parsePythonPhraseMap(
      [
        '"""doc"""',
        'OTHER = {"not": "this one"}',
        'HUMAN_PHRASES: Dict[str, str] = {',
        '    # reversible',
        '    "task_status_move": "moved a task\'s status",',
        "    'label': 'changed a label',",
        '    "ambiguous": "performed an unclassified action",  # backstop',
        '}',
      ].join('\n')
    )
    expect(parsed).toEqual({
      task_status_move: "moved a task's status",
      label: 'changed a label',
      ambiguous: 'performed an unclassified action',
    })
  })

  it('throws loudly when no phrase dict exists', () => {
    expect(() => parsePythonPhraseMap('X = 1')).toThrow(/no module-level/)
  })

  it('throws on an entry wrapped across two lines — never silently drops it', () => {
    expect(() =>
      parsePythonPhraseMap(
        [
          'HUMAN_PHRASES = {',
          '    "ok": "fine",',
          '    "wrapped_key":',
          '        "a value pushed to the next line by 79-col formatting",',
          '}',
        ].join('\n')
      )
    ).toThrow(/unparseable phrase-map line/)
  })

  it('throws on implicit string concatenation — the fragment must not pass', () => {
    expect(() =>
      parsePythonPhraseMap(
        [
          'HUMAN_PHRASES = {',
          '    "concat": "part one "',
          '        "part two",',
          '}',
        ].join('\n')
      )
    ).toThrow(/unparseable phrase-map line/)
  })
})

describe('phraseFor', () => {
  it('prefers the executor kind (mechanical identity) over the action_type', () => {
    expect(phraseFor('board_status', 'monday_task_update').text).toBe(
      'updated a task'
    )
  })

  it('falls back to the action_type when the kind is unmapped/absent', () => {
    expect(phraseFor('board_status', null).text).toBe('updated a board column')
    expect(phraseFor('task_create', 'unmapped_future_kind')).toEqual({
      text: 'created a task',
      mapped: true,
    })
  })

  it('widened kinds (action_type null) phrase via the kind', () => {
    expect(phraseFor(null, 'tier2_note')).toEqual({
      text: 'wrote a note',
      mapped: true,
    })
  })

  it('unmapped ids render the visible de-underscore words, flagged — never invented', () => {
    // Mirrors human_phrase("quantum_flux_write") == "quantum flux write"
    expect(phraseFor(null, 'quantum_flux_write')).toEqual({
      text: 'quantum flux write',
      mapped: false,
    })
    expect(phraseFor(null, 'some-dashed-kind').text).toBe('some dashed kind')
    expect(phraseFor(null, null)).toEqual({ text: 'acted', mapped: false })
  })

  it('strips the reserved pid-marker char from fallback text (SEC-4 mirror)', () => {
    expect(phraseFor(null, 'evil·pid·slug').text).toBe('evil·pid·slug'.replace(/·/g, ''))
  })

  it('never resolves through the prototype chain', () => {
    expect(phraseFor('__proto__', 'constructor').mapped).toBe(false)
  })

  it('the mirror covers every classifier action_type slug', () => {
    // framework/authority/classifier.py::ACTION_TYPES + the ambiguous
    // backstop — pinned here so a new enum member forces a phrase. (Exact
    // whole-map equality with the python source is the parity test's job —
    // the python map additionally carries the executor step kinds.)
    const enumSlugs = [
      'task_status_move', 'label', 'tier2_note', 'draft_only', 'local_edit',
      'investigation_run', 'task_create', 'board_status',
      'calendar_event_create', 'internal_message', 'internal_email',
      'officer_dispatch', 'external_message', 'external_email',
      'vercel_deploy_preview', 'git_push_nonmain', 'vercel_deploy_prod',
      'git_push_main', 'purchase', 'provision_paid', 'billing',
      'secret_read', 'secret_write', 'env_write', 'mcp_post', 'mcp_put',
      'mcp_delete', 'oauth_grant', 'token_grant', 'ambiguous',
    ]
    for (const slug of enumSlugs) {
      expect(HUMAN_PHRASES[slug], `missing phrase for ${slug}`).toBeTruthy()
    }
  })
})
