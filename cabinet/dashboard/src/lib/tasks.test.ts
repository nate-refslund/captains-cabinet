// tasks.ts — pure-logic slice (no DB, no Redis publish).
// Covers: WipCapExceededError constructor message variations, coerceWipCapError
// errcode+message gating, validateContextSlug regex + fs.access happy path /
// throw paths, WIP_CAP + RECENT_DONE_LIMIT constant pins.
//
// DB-touching helpers (getOfficerBoard, startTask, doneTask, blockTask,
// unblockTask, cancelTask) are deferred — they need pg-pool mocks and a
// transaction fixture. The pure functions here carry the invariants that
// route handlers and the WIP-trigger backstop actually rely on.
//
// validateContextSlug uses CONTEXTS_DIR (defaults to
// <checkout-root>/instance/config/contexts via the cabinet-root resolver)
// which contains this checkout's real context YAMLs — those give us a
// happy-path check without any fs mocking. Lane names are instance data, so
// the happy-path slug is DISCOVERED from disk, never hardcoded here.

import path from 'node:path'
import { readdir } from 'node:fs/promises'

import { describe, it, expect } from 'vitest'

import { cabinetRoot } from '@/lib/cabinet-root'
import {
  WIP_CAP,
  RECENT_DONE_LIMIT,
  WipCapExceededError,
  coerceWipCapError,
  validateContextSlug,
} from './tasks'

/** First real context slug on THIS checkout (mirrors tasks.ts CONTEXTS_DIR
 * resolution + CONTEXT_SLUG_RE). The egg prunes lane contexts, so a clean
 * export yields null and the happy-path probes degrade to no-ops there
 * instead of failing. */
async function firstRealContextSlug(): Promise<string | null> {
  const dir =
    process.env.CONTEXTS_DIR || path.join(cabinetRoot(), 'instance/config/contexts')
  try {
    const slugs = (await readdir(dir))
      .filter((f) => f.endsWith('.yml'))
      .map((f) => f.slice(0, -'.yml'.length))
      .filter((s) => /^[a-z0-9][a-z0-9-]{0,63}$/.test(s))
      .sort()
    return slugs[0] ?? null
  } catch {
    return null
  }
}

describe('constants', () => {
  it('WIP_CAP is 3 (Spec 038 AC #5 — per-(officer,context) cap)', () => {
    expect(WIP_CAP).toBe(3)
  })

  it('RECENT_DONE_LIMIT is 20 (Spec 038 v1.2 038.7 — rollup framing)', () => {
    expect(RECENT_DONE_LIMIT).toBe(20)
  })
})

describe('WipCapExceededError — constructor', () => {
  it('extends Error with name=WipCapExceededError', () => {
    const err = new WipCapExceededError('cto', [])
    expect(err).toBeInstanceOf(Error)
    expect(err.name).toBe('WipCapExceededError')
  })

  it('fills titles array + current defaults to titles.length', () => {
    const err = new WipCapExceededError('cto', ['Write tests', 'Fix bug'])
    expect(err.titles).toEqual(['Write tests', 'Fix bug'])
    expect(err.current).toBe(2)
    expect(err.cap).toBe(WIP_CAP)
  })

  it('uses current override when provided', () => {
    const err = new WipCapExceededError('cto', [], 5)
    expect(err.current).toBe(5)
    expect(err.cap).toBe(3)
  })

  it('titles.length > 0 path builds quoted title list', () => {
    const err = new WipCapExceededError('cto', ['Task A', 'Task B'])
    expect(err.message).toContain('cto already has 2 WIP tasks')
    expect(err.message).toContain('"Task A"')
    expect(err.message).toContain('"Task B"')
    expect(err.message).toContain('Finish or cancel one')
  })

  it('titles.length === 0 path falls back to N/CAP framing', () => {
    const err = new WipCapExceededError('cpo', [], 3)
    expect(err.message).toContain('cpo already has 3/3 WIP tasks')
    expect(err.message).not.toContain('""')
  })

  it('single title comma-separation is just one quoted entry', () => {
    const err = new WipCapExceededError('cto', ['Only one'])
    expect(err.message).toContain('"Only one"')
    expect(err.message).not.toContain(', ')
  })

  it('officer slug is echoed verbatim in the message', () => {
    const err = new WipCapExceededError('some-weird-role', ['x'])
    expect(err.message).toContain('some-weird-role')
  })
})

describe('coerceWipCapError — errcode gate', () => {
  it('returns null for null input', () => {
    expect(coerceWipCapError(null, 'cto')).toBeNull()
  })

  it('returns null for undefined input', () => {
    expect(coerceWipCapError(undefined, 'cto')).toBeNull()
  })

  it('returns null for primitive (string)', () => {
    expect(coerceWipCapError('boom', 'cto')).toBeNull()
  })

  it('returns null for error with wrong code', () => {
    const err = { code: '42P01', message: 'relation does not exist' }
    expect(coerceWipCapError(err, 'cto')).toBeNull()
  })

  it('returns null for code=23514 without WIP limit in message', () => {
    // check_violation errcode but unrelated trigger — e.g. some other CHECK
    const err = { code: '23514', message: 'new row for relation violates check constraint' }
    expect(coerceWipCapError(err, 'cto')).toBeNull()
  })

  it('returns null for empty-string message even with code=23514', () => {
    const err = { code: '23514', message: '' }
    expect(coerceWipCapError(err, 'cto')).toBeNull()
  })

  it('returns WipCapExceededError when code=23514 + WIP limit substring', () => {
    const err = {
      code: '23514',
      message: 'WIP limit (3) exceeded for officer cto in context acme',
    }
    const coerced = coerceWipCapError(err, 'cto')
    expect(coerced).toBeInstanceOf(WipCapExceededError)
    expect(coerced!.current).toBe(WIP_CAP)
    expect(coerced!.cap).toBe(WIP_CAP)
    expect(coerced!.titles).toEqual([])
  })

  it('returns null when message is missing (undefined)', () => {
    // Branch: const msg = e.message || '' — undefined → '' → no WIP limit → null
    const err = { code: '23514' }
    expect(coerceWipCapError(err, 'cto')).toBeNull()
  })

  it('coerced error echoes the officerSlug passed in (not from msg)', () => {
    const err = {
      code: '23514',
      message: 'WIP limit (3) exceeded for officer cto',
    }
    const coerced = coerceWipCapError(err, 'cpo')  // officer mismatch on purpose
    expect(coerced!.message).toContain('cpo')
  })

  it('case-sensitive WIP limit match (all-caps WIP required)', () => {
    // Branch: msg.includes('WIP limit') — substring is case-sensitive
    const err = { code: '23514', message: 'wip limit exceeded' }  // lowercase
    expect(coerceWipCapError(err, 'cto')).toBeNull()
  })
})

describe('validateContextSlug — regex + fs.access', () => {
  it('throws on null slug', async () => {
    await expect(validateContextSlug(null)).rejects.toThrow('context_slug is required')
  })

  it('throws on undefined slug', async () => {
    await expect(validateContextSlug(undefined)).rejects.toThrow('required')
  })

  it('throws on empty string', async () => {
    await expect(validateContextSlug('')).rejects.toThrow('required')
  })

  it('throws on whitespace-only (trim → empty)', async () => {
    await expect(validateContextSlug('   ')).rejects.toThrow('required')
  })

  it('throws on uppercase slug (regex rejects)', async () => {
    await expect(validateContextSlug('Acme')).rejects.toThrow('is invalid')
  })

  it('throws on slug with underscore (regex rejects)', async () => {
    await expect(validateContextSlug('my_slug')).rejects.toThrow('is invalid')
  })

  it('throws on slug starting with dash (regex requires alnum first)', async () => {
    await expect(validateContextSlug('-acme')).rejects.toThrow('is invalid')
  })

  it('throws on slug with path traversal', async () => {
    await expect(validateContextSlug('../../etc/passwd')).rejects.toThrow('is invalid')
  })

  it('throws on slug with slash', async () => {
    await expect(validateContextSlug('foo/bar')).rejects.toThrow('is invalid')
  })

  it('throws on slug over 64 chars (regex caps at 63 after initial char)', async () => {
    const tooLong = 'a' + 'b'.repeat(64)  // 65 chars total
    await expect(validateContextSlug(tooLong)).rejects.toThrow('is invalid')
  })

  it('throws on valid regex but missing YAML file', async () => {
    // 'nosuch' matches the regex but the contexts dir has no nosuch.yml
    await expect(validateContextSlug('nosuch')).rejects.toThrow('not found')
  })

  it('resolves to trimmed slug for a real on-disk context YAML', async () => {
    const slug = await firstRealContextSlug()
    if (!slug) return // egg/clean checkout: lane contexts pruned — nothing to probe
    expect(await validateContextSlug(slug)).toBe(slug)
  })

  it('resolves for adhoc + personal (all 3 real contexts)', async () => {
    const slug = await firstRealContextSlug()
    if (!slug) return // egg/clean checkout: lane contexts pruned — nothing to probe
    expect(await validateContextSlug('adhoc')).toBe('adhoc')
    expect(await validateContextSlug('personal')).toBe('personal')
  })

  it('trims whitespace before validation + returns trimmed', async () => {
    const slug = await firstRealContextSlug()
    if (!slug) return // egg/clean checkout: lane contexts pruned — nothing to probe
    expect(await validateContextSlug(`  ${slug}  `)).toBe(slug)
  })

  it('accepts single-char slug (regex min length 1)', async () => {
    // 'a' matches regex but no a.yml → not-found path
    await expect(validateContextSlug('a')).rejects.toThrow('not found')
  })

  it('error message includes the offending slug value', async () => {
    try {
      await validateContextSlug('BadSlug')
      expect.fail('should have thrown')
    } catch (e) {
      expect((e as Error).message).toContain('BadSlug')
    }
  })

  it('not-found error includes CONTEXTS_DIR path hint', async () => {
    try {
      await validateContextSlug('definitely-not-there')
      expect.fail('should have thrown')
    } catch (e) {
      expect((e as Error).message).toContain('definitely-not-there.yml')
    }
  })
})
