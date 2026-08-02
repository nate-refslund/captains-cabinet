// briefing.ts — confinement teeth + newest-briefing selection + honest empties.
//
// /briefing reads two files the hatch writes under instance/memory. Its
// confinement layer is a twin of vault.ts's, so it gets the same negative
// controls: path traversal, absolute paths, NUL injection, and — the star —
// SYMLINK ESCAPE. The symlink arm is not theoretical here: the newest-briefing
// scan takes names off the filesystem, so a symlink NAMED
// `first-briefing-9999-12-31.md` and pointed outside the root is precisely the
// escape the resolver exists to refuse. Fixtures are temp dirs; the real
// instance/memory is never touched.

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import fs from 'fs'
import os from 'os'
import path from 'path'
import {
  hasBriefingRoot,
  resolveInMemory,
  readMemoryDoc,
  tryReadMemoryDoc,
  latestFirstBriefingRel,
  latestFirstBriefing,
  researchBrief,
  resetBriefingRootCache,
  BriefingPathError,
  MEMORY_DIR_REL,
  RESEARCH_BRIEF_REL,
} from './briefing'

let savedRoot: string | undefined
let root: string // the fake CABINET_ROOT
let memory: string // <root>/instance/memory
let outside: string

function pointAt(dir: string | undefined) {
  if (dir === undefined) delete process.env.CABINET_ROOT
  else process.env.CABINET_ROOT = dir
  resetBriefingRootCache()
}

/** A hatched cabinet: instance/memory with two briefings, the research brief,
 *  and two escaping symlinks (one of them named like a briefing). */
function makeFixture(): void {
  root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'brief-root-')))
  outside = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'brief-out-')))
  memory = path.join(root, MEMORY_DIR_REL)
  fs.mkdirSync(memory, { recursive: true })
  fs.mkdirSync(path.join(memory, 'library'))

  fs.writeFileSync(path.join(outside, 'secret.md'), '# TOP SECRET\n\nnot yours')

  fs.writeFileSync(
    path.join(memory, 'first-briefing-2026-07-30.md'),
    '# Briefing\n\nOLDER briefing body\n'
  )
  fs.writeFileSync(
    path.join(memory, 'first-briefing-2026-08-02.md'),
    '---\nkind: first-briefing\n---\n# Briefing\n\nNEWEST briefing body\n'
  )
  fs.writeFileSync(
    path.join(memory, RESEARCH_BRIEF_REL),
    '# Research brief\n\nresearch brief queued\n'
  )
  // Decoys that must never be picked up as "the newest briefing".
  fs.writeFileSync(path.join(memory, 'first-briefing-2026-12-31.md.sh'), 'rm -rf /')
  fs.writeFileSync(path.join(memory, 'demo-receipt.md'), '# Demo')

  // Escapes: a dir symlink, and a file symlink WEARING a briefing name with a
  // date newer than every real one (so a naive scan would prefer it).
  fs.symlinkSync(outside, path.join(memory, 'escape'), 'dir')
  fs.symlinkSync(
    path.join(outside, 'secret.md'),
    path.join(memory, 'first-briefing-9999-12-31.md'),
    'file'
  )
}

beforeEach(() => {
  savedRoot = process.env.CABINET_ROOT
  makeFixture()
  pointAt(root)
})

afterEach(() => {
  pointAt(savedRoot)
  for (const d of [root, outside]) {
    try {
      fs.rmSync(d, { recursive: true, force: true })
    } catch {
      /* best effort */
    }
  }
})

// ---------------------------------------------------------------------------
// Confinement — the negative controls
// ---------------------------------------------------------------------------

describe('resolveInMemory — confinement', () => {
  it('resolves an in-root file to its real path', () => {
    const real = resolveInMemory('first-briefing-2026-08-02.md')
    expect(real).toBe(path.join(fs.realpathSync(memory), 'first-briefing-2026-08-02.md'))
  })

  it('refuses ../ traversal out of instance/memory', () => {
    expect(() => resolveInMemory('../../instance/config/platform.yml')).toThrow(BriefingPathError)
    expect(() => resolveInMemory('../..')).toThrow(BriefingPathError)
  })

  it('refuses an absolute path', () => {
    expect(() => resolveInMemory(path.join(outside, 'secret.md'))).toThrow(BriefingPathError)
    expect(() => resolveInMemory('/etc/passwd')).toThrow(BriefingPathError)
  })

  it('refuses a NUL byte', () => {
    expect(() => resolveInMemory('first-briefing-2026-08-02.md\0.txt')).toThrow(BriefingPathError)
  })

  it('refuses a symlink whose target escapes the root (dir and file)', () => {
    expect(() => resolveInMemory('escape/secret.md')).toThrow(BriefingPathError)
    expect(() => resolveInMemory('first-briefing-9999-12-31.md')).toThrow(BriefingPathError)
  })

  it('refuses a missing path with the same error as an escape (no oracle)', () => {
    let miss = ''
    let escape = ''
    try {
      resolveInMemory('no-such-file.md')
    } catch (e) {
      miss = (e as Error).name
    }
    try {
      resolveInMemory('../../../../etc/passwd')
    } catch (e) {
      escape = (e as Error).name
    }
    expect(miss).toBe('BriefingPathError')
    expect(escape).toBe('BriefingPathError')
  })

  it('fails closed when instance/memory does not exist', () => {
    const bare = fs.mkdtempSync(path.join(os.tmpdir(), 'brief-bare-'))
    pointAt(bare)
    expect(hasBriefingRoot()).toBe(false)
    expect(() => resolveInMemory('first-briefing-2026-08-02.md')).toThrow(BriefingPathError)
    expect(latestFirstBriefingRel()).toBeNull()
    expect(latestFirstBriefing()).toBeNull()
    expect(researchBrief()).toBeNull()
    fs.rmSync(bare, { recursive: true, force: true })
  })
})

// ---------------------------------------------------------------------------
// Reads
// ---------------------------------------------------------------------------

describe('readMemoryDoc', () => {
  it('splits frontmatter and returns the RAW body', () => {
    const doc = readMemoryDoc('first-briefing-2026-08-02.md')
    expect(doc.frontmatter).toEqual({ kind: 'first-briefing' })
    expect(doc.body).toContain('NEWEST briefing body')
    expect(doc.body.startsWith('---')).toBe(false)
    expect(doc.mtimeMs).toBeGreaterThan(0)
  })

  it('leaves a body without frontmatter untouched', () => {
    const doc = readMemoryDoc('first-briefing-2026-07-30.md')
    expect(doc.frontmatter).toBeNull()
    expect(doc.body).toContain('OLDER briefing body')
  })

  it('refuses a non-markdown file even inside the root', () => {
    expect(() => readMemoryDoc('first-briefing-2026-12-31.md.sh')).toThrow(BriefingPathError)
  })

  it('refuses a directory', () => {
    expect(() => readMemoryDoc('library')).toThrow(BriefingPathError)
  })

  it('tryReadMemoryDoc returns null instead of throwing on a refusal', () => {
    expect(tryReadMemoryDoc('../../etc/passwd')).toBeNull()
    expect(tryReadMemoryDoc('escape/secret.md')).toBeNull()
    expect(tryReadMemoryDoc('nope.md')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// Newest-briefing selection
// ---------------------------------------------------------------------------

describe('latestFirstBriefing', () => {
  it('picks the newest date in the NAME, not the newest mtime', () => {
    // Make the OLDER file the most recently modified — date-in-name must win.
    const older = path.join(memory, 'first-briefing-2026-07-30.md')
    const future = new Date(Date.now() + 60_000)
    fs.utimesSync(older, future, future)
    expect(latestFirstBriefingRel()).toBe('first-briefing-2026-08-02.md')
    expect(latestFirstBriefing()?.body).toContain('NEWEST briefing body')
  })

  it('never picks an escaping symlink, even with the newest name', () => {
    // first-briefing-9999-12-31.md sorts first by date and points outside.
    const rel = latestFirstBriefingRel()
    expect(rel).toBe('first-briefing-2026-08-02.md')
    expect(latestFirstBriefing()?.body).not.toContain('TOP SECRET')
  })

  it('ignores names that only look like a briefing', () => {
    fs.writeFileSync(path.join(memory, 'first-briefing-2026-08-03.markdown'), 'x')
    fs.writeFileSync(path.join(memory, 'xfirst-briefing-2026-08-04.md'), 'x')
    fs.writeFileSync(path.join(memory, 'first-briefing-not-a-date.md'), 'x')
    expect(latestFirstBriefingRel()).toBe('first-briefing-2026-08-02.md')
  })

  it('returns null (honest empty) when no briefing has been written', () => {
    for (const n of fs.readdirSync(memory)) {
      if (n.startsWith('first-briefing-')) fs.rmSync(path.join(memory, n), { force: true })
    }
    expect(latestFirstBriefingRel()).toBeNull()
    expect(latestFirstBriefing()).toBeNull()
    // …while the research brief, a separate file, still reads.
    expect(researchBrief()?.body).toContain('research brief queued')
  })
})

describe('researchBrief', () => {
  it('reads the genesis research brief off the library shelf', () => {
    const doc = researchBrief()
    expect(doc?.relPath).toBe(RESEARCH_BRIEF_REL)
    expect(doc?.body).toContain('research brief queued')
  })

  it('returns null when the shelf is empty', () => {
    fs.rmSync(path.join(memory, RESEARCH_BRIEF_REL), { force: true })
    expect(researchBrief()).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// The Library root must NOT move — /briefing carries its own root
// ---------------------------------------------------------------------------

describe('root independence', () => {
  it('roots at instance/memory regardless of the org vault env overrides', () => {
    process.env.CABINET_ORG_VAULT_DIR = outside
    resetBriefingRootCache()
    expect(hasBriefingRoot()).toBe(true)
    expect(resolveInMemory('first-briefing-2026-08-02.md')).toContain(MEMORY_DIR_REL)
    expect(() => resolveInMemory('secret.md')).toThrow(BriefingPathError)
    delete process.env.CABINET_ORG_VAULT_DIR
  })
})
