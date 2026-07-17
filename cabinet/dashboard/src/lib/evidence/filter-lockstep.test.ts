/**
 * filter-lockstep.test.ts — the vitest half of the ONE-validation-truth pin.
 *
 * The dashboard's filter validation mirrors framework/evidence/query.py
 * (it cannot import it). Both sides run the SAME case vector:
 *   - cabinet/scripts/tests/fixtures/evidence-filter-cases.json is the single
 *     truth file;
 *   - the pytest twin (cabinet/scripts/tests/test_evidence_read_lockstep.py)
 *     runs every case through the REAL query.parse_selector (`cli` column),
 *     pins the TS literals (statuses / actor kinds / regexes) against the
 *     Python vocabularies, and enforces the divergence law (dashboard may
 *     differ ONLY via the documented single-day alias or the doorway's
 *     one-token transport budget — and only ever by widening the Captain
 *     page, never the officer CLI);
 *   - this file runs every case through the REAL validateFilters
 *     (`dashboard` column).
 * A rule change on either side that is not mirrored on the other breaks one
 * of the twins.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { validateFilters } from './read'

interface FilterCase {
  filter: 'actor' | 'component' | 'status' | 'time'
  value: string
  cli: boolean
  dashboard: boolean
  alias_of?: string
  transport_budget?: boolean
}

const vectorPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../../../..',
  'cabinet/scripts/tests/fixtures/evidence-filter-cases.json'
)

const vector = JSON.parse(fs.readFileSync(vectorPath, 'utf8')) as {
  cases: FilterCase[]
}

describe('shared filter case vector (lockstep with the Python query plane)', () => {
  it('the vector exists and covers every filter dimension', () => {
    expect(vector.cases.length).toBeGreaterThan(0)
    expect(new Set(vector.cases.map((c) => c.filter))).toEqual(
      new Set(['actor', 'component', 'status', 'time'])
    )
  })

  for (const filterCase of vector.cases) {
    const label = `${filterCase.filter}=${JSON.stringify(filterCase.value)} → ${
      filterCase.dashboard ? 'accept' : 'refuse'
    }`
    it(label, () => {
      const verdict = validateFilters({ [filterCase.filter]: filterCase.value })
      expect(
        verdict.ok,
        'validateFilters no longer agrees with the shared case vector — ' +
          'update fixtures/evidence-filter-cases.json AND the pytest twin ' +
          'together, never one side alone'
      ).toBe(filterCase.dashboard)
      if (verdict.ok && filterCase.dashboard) {
        expect(verdict.filters[filterCase.filter]).toBe(filterCase.value)
      }
    })
  }
})
