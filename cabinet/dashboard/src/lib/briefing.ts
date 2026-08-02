/**
 * briefing.ts — READ-ONLY filesystem data layer for /briefing, the FIRST
 * BRIEFING reader.
 *
 * The hatch writes two documents that no dashboard surface could read until
 * this module existed:
 *
 *   - `instance/memory/first-briefing-<UTC date>.md` — the genesis first
 *     receipt (framework/frontdoor/run_briefing.py `_run_local_render`, via
 *     cabinet/scripts/first-briefing.sh).
 *   - `instance/memory/library/genesis-research-brief.md` — the genesis
 *     research brief, or its honest IOU note
 *     (framework/onboarding/genesis.py `BRIEF_REL`).
 *
 * The Library (/library, lib/vault.ts) roots at `org_vault_dir()` — normally
 * `<repo>/vault` — and MUST keep doing so: repointing that root would move the
 * whole Library. So this module carries its OWN root, `instance/memory`, and
 * its own confinement.
 *
 * SECURITY POSTURE — a deliberate twin of lib/vault.ts's confinement layer
 * (`resolveInVault`, blueprint §2). Every read goes through
 * `resolveInMemory()`, which realpath-resolves the candidate and asserts it
 * stays under the realpath'd `instance/memory` root — defeating `../`
 * traversal, absolute paths, NUL injection, and symlink escape. That is not
 * decoration here: the newest-briefing scan reads DIRECTORY ENTRIES, so a
 * symlink dropped into `instance/memory` named `first-briefing-9999-12-31.md`
 * and pointed at `/etc/passwd` is exactly the escape the resolve step exists to
 * refuse. Deny → typed `BriefingPathError` → the caller renders "not found",
 * never a stack trace and never the file.
 *
 * READ-ONLY: no writes anywhere in this module (no writeFile/mkdir/unlink/
 * rename/appendFile). NO DATABASE: filesystem only.
 *
 * Kept as a separate module rather than a second root inside vault.ts on
 * purpose — vault.ts's single highest-consequence constraint is that it never
 * resolves anything but `org_vault_dir()`, and adding a second root to it is
 * how that constraint gets weakened by accident.
 */

import fs from 'fs'
import path from 'path'
import yaml from 'js-yaml'
import { cabinetPath } from './cabinet-root'

// ============================================================
// Types
// ============================================================

export interface BriefingDoc {
  /** POSIX-style path relative to the instance/memory root. */
  relPath: string
  /** Parsed leading `--- ... ---` YAML frontmatter, or null. Data only. */
  frontmatter: Record<string, unknown> | null
  /** RAW markdown body (frontmatter stripped). Never pre-rendered to HTML. */
  body: string
  /** File mtime in ms, for an honest "written at" line. */
  mtimeMs: number
}

/** Thrown on ANY confinement failure or miss. Callers treat a traversal
 *  attempt and a genuine miss identically — path existence never leaks. */
export class BriefingPathError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'BriefingPathError'
  }
}

/** Where the hatch's genesis surfaces live, relative to the cabinet root. */
export const MEMORY_DIR_REL = 'instance/memory'
/** genesis.py BRIEF_REL, minus the `instance/memory/` prefix. */
export const RESEARCH_BRIEF_REL = 'library/genesis-research-brief.md'

/** `first-briefing-<UTC date>.md` — the exact shape run_briefing.py writes.
 *  Anchored, so `first-briefing-2026-01-01.md.sh` and
 *  `evil/first-briefing-2026-01-01.md` never match. */
const FIRST_BRIEFING_RE = /^first-briefing-(\d{4}-\d{2}-\d{2})\.md$/

const FRONTMATTER_RE = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/

// ============================================================
// Root resolution
// ============================================================

interface RootCache {
  raw: string | null
  real: string | null
}
let _cache: RootCache | null = null

function computeCache(): RootCache {
  let raw: string | null
  try {
    raw = cabinetPath(MEMORY_DIR_REL)
  } catch {
    return { raw: null, real: null }
  }
  let real: string | null = null
  try {
    const st = fs.statSync(raw)
    real = st.isDirectory() ? fs.realpathSync(raw) : null
  } catch {
    real = null
  }
  return { raw, real }
}

/** The realpath'd `instance/memory` root — the anchor for every confinement
 *  assertion. null when the directory is absent (a cabinet that has not
 *  hatched yet), which is an honest empty state, not an error. */
function memoryRootReal(): string | null {
  if (!_cache) _cache = computeCache()
  return _cache.real
}

/** Test seam: drop the memoized root so a fresh CABINET_ROOT resolves. */
export function resetBriefingRootCache(): void {
  _cache = null
}

/** True when `instance/memory` exists and resolved. */
export function hasBriefingRoot(): boolean {
  return memoryRootReal() !== null
}

// ============================================================
// THE confinement mechanism (realpath-under-root; twin of resolveInVault)
// ============================================================

/**
 * Resolve a memory-relative path to an absolute, confined, EXISTING real path.
 * Throws BriefingPathError on any escape or miss.
 *
 *   - NUL byte       → deny (belt-and-suspenders; fs also rejects it)
 *   - absolute input → deny (only memory-relative paths are addressable)
 *   - lexical escape → path.resolve normalizes '..'; prefix-assert denies
 *   - symlink escape → realpath moves an in-tree symlink to its true target;
 *                      if that target is outside the root the final
 *                      prefix-assert denies
 *   - missing path   → realpathSync throws ENOENT → BriefingPathError
 */
export function resolveInMemory(rel: string): string {
  const root = memoryRootReal()
  if (!root) throw new BriefingPathError('no instance memory directory')
  if (typeof rel !== 'string') throw new BriefingPathError('invalid path')
  if (rel.includes('\0')) throw new BriefingPathError('null byte in path')
  if (path.isAbsolute(rel)) throw new BriefingPathError('absolute path rejected')

  const candidate = path.resolve(root, rel)
  // Pre-symlink lexical guard (catches ../ before we touch the filesystem).
  if (!(candidate === root || candidate.startsWith(root + path.sep))) {
    throw new BriefingPathError('path escapes instance memory root')
  }

  let real: string
  try {
    real = fs.realpathSync(candidate)
  } catch {
    // ENOENT / EACCES / symlink loop — all read as "not found", never leak.
    throw new BriefingPathError('path not found')
  }

  // THE assertion — post-symlink. A symlink whose target is outside dies here.
  if (!(real === root || real.startsWith(root + path.sep))) {
    throw new BriefingPathError('resolved path escapes instance memory root')
  }
  return real
}

// ============================================================
// Reads
// ============================================================

/**
 * Read a confined markdown document under `instance/memory`. Returns parsed
 * frontmatter (data only), the RAW markdown body, and the mtime. Throws
 * BriefingPathError if `rel` is not a confined regular markdown file.
 */
export function readMemoryDoc(rel: string): BriefingDoc {
  const real = resolveInMemory(rel)
  if (!/\.(md|markdown)$/i.test(real)) {
    throw new BriefingPathError('not a markdown document')
  }
  const st = fs.statSync(real)
  if (!st.isFile()) throw new BriefingPathError('not a file')

  const raw = fs.readFileSync(real, 'utf-8')
  let frontmatter: Record<string, unknown> | null = null
  let body = raw

  const m = FRONTMATTER_RE.exec(raw)
  if (m) {
    let parsed: unknown
    try {
      // js-yaml v4 load == the safe DEFAULT_SCHEMA (no !!js/function tags).
      parsed = yaml.load(m[1])
    } catch {
      parsed = null
    }
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      frontmatter = parsed as Record<string, unknown>
      body = raw.slice(m[0].length)
    }
    // Unparseable / non-object frontmatter: leave the fence in the body.
  }

  return { relPath: rel, frontmatter, body, mtimeMs: st.mtimeMs }
}

/** Same as readMemoryDoc but returns null instead of throwing — the shape the
 *  page wants, where "absent" and "refused" both render an honest empty. */
export function tryReadMemoryDoc(rel: string): BriefingDoc | null {
  try {
    return readMemoryDoc(rel)
  } catch {
    return null
  }
}

/**
 * The NEWEST `first-briefing-<UTC date>.md` directly under `instance/memory`,
 * or null when none exists.
 *
 * The scan is the reason confinement is load-bearing: names come off the
 * filesystem, so each candidate is lstat'd (a symlink is dropped outright,
 * mirroring vault.ts listDir) AND re-confined through resolveInMemory before
 * it is offered to a reader. Ordering is by the ISO date IN THE NAME — the
 * date the briefing is FOR, which is what an operator means by "the newest
 * briefing"; mtime would reorder them on any copy or restore.
 */
export function latestFirstBriefingRel(): string | null {
  const root = memoryRootReal()
  if (!root) return null

  let names: string[]
  try {
    names = fs.readdirSync(root)
  } catch {
    return null
  }

  const candidates: { name: string; date: string }[] = []
  for (const name of names) {
    const m = FIRST_BRIEFING_RE.exec(name)
    if (!m) continue
    let lst: fs.Stats
    try {
      lst = fs.lstatSync(path.join(root, name))
    } catch {
      continue
    }
    // Never follow a symlink out of the root (twin of listDir's rule).
    if (lst.isSymbolicLink() || !lst.isFile()) continue
    // Defense in depth: the confinement layer gets the final word.
    try {
      resolveInMemory(name)
    } catch {
      continue
    }
    candidates.push({ name, date: m[1] })
  }
  if (candidates.length === 0) return null

  // Newest date first; ties (impossible for a fixed name shape, but free)
  // break on the name so the pick is deterministic.
  candidates.sort((a, b) => (a.date === b.date ? b.name.localeCompare(a.name) : b.date.localeCompare(a.date)))
  return candidates[0].name
}

/** The newest first briefing as a readable doc, or null. */
export function latestFirstBriefing(): BriefingDoc | null {
  const rel = latestFirstBriefingRel()
  if (!rel) return null
  return tryReadMemoryDoc(rel)
}

/** The genesis research brief (or its honest IOU note), or null. */
export function researchBrief(): BriefingDoc | null {
  return tryReadMemoryDoc(RESEARCH_BRIEF_REL)
}
