/**
 * EVERY ioredis CLIENT IN THIS APP IS BOUNDED — the coverage fence.
 *
 * WHY THIS FILE EXISTS. The shared client in `lib/redis.ts` is not the only one:
 * there are NINE `new Redis(...)` sites, and bounding one of them is not a wall.
 * Measured in the BUILT app against a store that accepts the connection and
 * never answers, with the shared client already fixed: `/queue` still took
 * **45 seconds and then timed out**, because `lib/attention/queue.ts` builds its
 * own. `/world`'s rail did the same. Nothing in 3 098 tests noticed — proven by
 * mutation: unbinding `queue.ts` again leaves its own 41-test suite fully GREEN.
 *
 * A TEST FENCE'S SCOPE IS ITS CLAIM. That lesson is written down two doors over
 * (`cabinet/scripts/tests/test_killswitch_fail_closed.py` swept `cabinet/` and
 * `framework/` and never saw the four dashboard readers of the same key), and
 * this file is the same idea applied to client construction rather than to key
 * reads. Its scope is stated in `SCAN_ROOT` and asserted below: if the scan
 * finds fewer sites than it has ever seen, that is a fence that stopped looking.
 *
 * WHY A SOURCE SCAN RATHER THAN A BEHAVIOURAL ARM. Each site lives inside a
 * route handler or an SSE stream that would need its whole environment stood up
 * to drive; the property being asserted — "this construction carries bounds" —
 * is a property of the source. It is a weaker kind of evidence than driving the
 * handler, so it is paired with the end-to-end arms in
 * `store-unreachable.e2e.test.ts` that DO drive real clients against real
 * unreachable sockets, and it is mutation-proven per site rather than trusted.
 *
 * WHY NOT `git grep -E`. POSIX ERE treats `\s` as a literal backslash-then-s, so
 * a fence written that way reports GREEN against a defect deliberately put back.
 * That is not hypothetical here — it happened in this exact class one PR ago.
 * This file reads the tree with `node:fs` and matches with a JavaScript regex,
 * where `\s` means what it says.
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  LIVE_CLIENT_OPTIONS,
  REQUEST_CLIENT_OPTIONS,
  SUBSCRIBER_CLIENT_OPTIONS,
} from './store-reachability'

const SCAN_ROOT = path.resolve(__dirname, '..')

/** The named option sets a construction may pass. Anything else is unbounded. */
const SANCTIONED = [
  'LIVE_CLIENT_OPTIONS',
  'REQUEST_CLIENT_OPTIONS',
  'SUBSCRIBER_CLIENT_OPTIONS',
]

/**
 * Sites seen when this fence was written. A LOWER count means the scan stopped
 * seeing files it used to see — the failure mode of every coverage sweep — and
 * fails rather than quietly shrinking its own claim.
 */
const SITES_AT_AUTHORING = 9

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '.next') continue
      sourceFiles(p, out)
    } else if (/\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) {
      out.push(p)
    }
  }
  return out
}

interface Site {
  file: string
  line: number
  text: string
}

function constructionSites(): Site[] {
  const sites: Site[] = []
  for (const file of sourceFiles(SCAN_ROOT)) {
    const src = fs.readFileSync(file, 'utf8')
    const lines = src.split('\n')
    lines.forEach((line, i) => {
      // Skip comment lines: the docstrings in this change quote `new Redis(...)`
      // when describing the defect, and a fence that cannot tell prose from code
      // fails on its own documentation.
      const code = line.trimStart()
      if (code.startsWith('*') || code.startsWith('//') || code.startsWith('/*')) return
      if (!/\bnew\s+Redis\s*\(/.test(line)) return
      // The call may wrap: take the next few lines as the argument window.
      sites.push({
        file: path.relative(SCAN_ROOT, file),
        line: i + 1,
        text: lines.slice(i, i + 6).join('\n'),
      })
    })
  }
  return sites
}

describe('every ioredis client in the app carries bounds', () => {
  it('finds at least as many construction sites as when the fence was written', () => {
    const sites = constructionSites()
    expect(
      sites.length,
      `scan found ${sites.length} sites; a fence that sees fewer than it used to has stopped looking`
    ).toBeGreaterThanOrEqual(SITES_AT_AUTHORING)
  })

  it('passes a sanctioned option set at EVERY site', () => {
    const unbounded = constructionSites().filter(
      (s) => !SANCTIONED.some((name) => s.text.includes(name))
    )
    expect(
      unbounded.map((s) => `${s.file}:${s.line}`),
      'these ioredis clients carry no bounds — against a store that accepts the ' +
        'connection and never answers, each one hangs its caller forever'
    ).toEqual([])
  })

  it('the sanctioned sets are distinct and each actually bounds something', () => {
    // A sanctioned name that resolves to `{}` would turn this fence into a
    // spelling test — the failure this program keeps finding in its own sensors.
    for (const [name, opts] of Object.entries({
      LIVE_CLIENT_OPTIONS,
      REQUEST_CLIENT_OPTIONS,
      SUBSCRIBER_CLIENT_OPTIONS,
    })) {
      const o = opts as Record<string, unknown>
      expect(Object.keys(o).length, name).toBeGreaterThan(0)
      expect(typeof o.connectTimeout, `${name}.connectTimeout`).toBe('number')
      expect(typeof o.maxRetriesPerRequest, `${name}.maxRetriesPerRequest`).toBe('number')
    }
    // The two COMMAND sets must bound a reply as well as a connect — the
    // mute-accept shape completes its connect, so a connect bound alone does
    // nothing for it. The subscriber set deliberately does not (see its
    // docstring); asserting that here keeps the exemption explicit rather than
    // letting it look like an oversight.
    expect(typeof LIVE_CLIENT_OPTIONS.commandTimeout).toBe('number')
    expect(typeof REQUEST_CLIENT_OPTIONS.commandTimeout).toBe('number')
    expect(
      (SUBSCRIBER_CLIENT_OPTIONS as Record<string, unknown>).commandTimeout
    ).toBeUndefined()
  })
})
