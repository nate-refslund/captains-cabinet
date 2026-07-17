/**
 * vault.ts — READ-ONLY filesystem data layer for the /vault browser.
 *
 * Surfaces the cabinet's ORG vault (a directory of markdown notes) to the
 * dashboard. Security is the dominant constraint of this module:
 *
 *   1. ROOT RESOLUTION mirrors framework/env.py org_vault_dir() EXACTLY and
 *      NEVER reads the personal `vault_dir` key (which on this box points at
 *      the captain's private Obsidian brain). Reading the wrong key would
 *      expose that personal vault over the web — the single highest-consequence
 *      constraint here (blueprint §0).
 *   2. PATH CONFINEMENT: every read goes through resolveInVault(), which
 *      realpath-resolves the candidate and asserts it stays under the
 *      realpath'd root — defeating ../ traversal, absolute paths, NUL
 *      injection, and symlink escape. Deny → typed VaultPathError → the caller
 *      maps to 404 (never 403; don't leak existence via status code).
 *   3. READ-ONLY: this module never writes/edits/deletes. No fs.writeFile,
 *      unlink, rm, mkdir, rename, appendFile, copyFile anywhere.
 *   4. NO DATABASE: the vault is read from the FILESYSTEM. This module imports
 *      no '@/lib/db', no pg, issues no query() — the retired Library vector
 *      store stays retired (test_library_retirement_ratchet.py).
 *
 * See docs/runbooks/vault-browser-2026-07-17.md.
 */

import fs from 'fs'
import path from 'path'
import yaml from 'js-yaml'
import { cabinetRoot, cabinetPath } from './cabinet-root'
import { extractHeadings, slugify, type ExtractedHeading } from './vault-wikilinks'

// ============================================================
// Types
// ============================================================

export type VaultEntryKind = 'dir' | 'file'

export interface VaultEntry {
  /** Bare entry name (no path). */
  name: string
  /** POSIX-style path relative to the vault root (URL-safe join units). */
  relPath: string
  kind: VaultEntryKind
}

export interface VaultNote {
  relPath: string
  /** Parsed leading `--- ... ---` YAML frontmatter, or null. Data only — never
   *  rendered as HTML; the page prints values as React text. */
  frontmatter: Record<string, unknown> | null
  /** RAW markdown body (frontmatter stripped). Never pre-rendered to HTML. */
  body: string
  headings: ExtractedHeading[]
}

/** Thrown by resolveInVault on ANY confinement failure. Callers map it to a
 *  generic 404 — a traversal attempt and a genuine miss look identical to the
 *  client, so path existence never leaks through the status code. */
export class VaultPathError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'VaultPathError'
  }
}

const MD_EXT = /\.(md|markdown)$/i
const WALK_DEPTH_CAP = 8
const WALK_FILE_CAP = 20000

// ============================================================
// Root resolution — faithful TS mirror of framework/env.py org_vault_dir()
// ============================================================

interface RootCache {
  raw: string | null
  real: string | null
}
let _cache: RootCache | null = null

/** Read `org_vault_dir` (else legacy `product_brain_dir`) from platform.yml
 *  THEN product.yml — mirroring org_vault_dir() arm 3. Deliberately does NOT
 *  read `vault_dir`. Returns the first config file's value (Python `break`s on
 *  the first file that carries the key). A tiny dedicated reader — NOT
 *  getConfig(), which injects mock fallbacks and would invent a path. */
function readOrgVaultConfigKey(root: string): string | null {
  for (const rel of ['instance/config/platform.yml', 'instance/config/product.yml']) {
    const p = path.join(root, rel)
    let data: unknown
    try {
      if (!fs.existsSync(p)) continue
      data = yaml.load(fs.readFileSync(p, 'utf-8'))
    } catch {
      continue
    }
    if (!data || typeof data !== 'object') continue
    const obj = data as Record<string, unknown>
    const nested =
      obj.product && typeof obj.product === 'object'
        ? (obj.product as Record<string, unknown>)
        : null
    for (const key of ['org_vault_dir', 'product_brain_dir']) {
      let cand = obj[key]
      if ((cand === undefined || cand === null) && nested) cand = nested[key]
      if (typeof cand === 'string' && cand.trim()) {
        // First file carrying the key wins; Python stops scanning here too.
        return cand.trim()
      }
    }
    // No key in this file — fall through to the next.
  }
  return null
}

function expandUser(p: string): string {
  if (p === '~') return process.env.HOME || p
  if (p.startsWith('~/')) return path.join(process.env.HOME || '~', p.slice(2))
  return p
}

/** The resolved ORG vault root (unrealpathed), or null (fail-closed). Mirrors
 *  org_vault_dir(): env override → config key (existence-gated) → <repo>/vault
 *  → <repo>/product-brain → null. */
function resolveVaultRoot(): string | null {
  // 1 + 2. Env overrides (honored verbatim, ~-expanded), mirroring
  // CABINET_ORG_VAULT_DIR / the legacy CABINET_PRODUCT_BRAIN_DIR alias.
  for (const envName of ['CABINET_ORG_VAULT_DIR', 'CABINET_PRODUCT_BRAIN_DIR']) {
    const v = (process.env[envName] || '').trim()
    if (v) return expandUser(v)
  }

  let root: string
  try {
    root = cabinetRoot()
  } catch {
    return null
  }

  // 3. Config key (existence-gated). Relative values resolve against the repo
  // root; absolute / ~ honored as-is. Key-present-but-dir-absent falls through
  // to the in-repo defaults (Python `break`), never short-circuits to null.
  const configVal = readOrgVaultConfigKey(root)
  if (configVal) {
    const expanded = expandUser(configVal)
    const abs = path.isAbsolute(expanded) ? expanded : path.join(root, expanded)
    try {
      if (fs.statSync(abs).isDirectory()) return abs
    } catch {
      /* dir absent — fall through */
    }
  }

  // 4 + 5. In-repo defaults (the corpus ships in-repo).
  for (const relDefault of ['vault', 'product-brain']) {
    const cand = cabinetPath(relDefault)
    try {
      if (fs.statSync(cand).isDirectory()) return cand
    } catch {
      /* not present */
    }
  }

  // 6. No corpus — fail closed.
  return null
}

function computeCache(): RootCache {
  const raw = resolveVaultRoot()
  let real: string | null = null
  if (raw) {
    try {
      real = fs.realpathSync(raw)
    } catch {
      real = null
    }
  }
  return { raw, real }
}

/** The resolved ORG vault root, or null when no corpus is configured/present.
 *  Cached per-process (env.py parity); resettable in tests. */
export function vaultRoot(): string | null {
  if (!_cache) _cache = computeCache()
  return _cache.raw
}

/** The realpath'd vault root (canonicalized once, up front) — the anchor for
 *  every confinement assertion. null when unresolved. */
function vaultRootReal(): string | null {
  if (!_cache) _cache = computeCache()
  return _cache.real
}

/** Test seam: drop the memoized root so a fresh env/config resolves. */
export function resetVaultRootCache(): void {
  _cache = null
}

/** True when a vault corpus is resolved and present. */
export function hasVault(): boolean {
  return vaultRootReal() !== null
}

// ============================================================
// THE confinement mechanism (Corridor-gated; realpath-under-root)
// ============================================================

/**
 * Resolve a vault-relative path to an absolute, confined, EXISTING real path.
 * Throws VaultPathError on any escape or miss.
 *
 *   - NUL byte            → deny (belt-and-suspenders; fs also rejects it)
 *   - absolute input      → deny (only vault-relative paths are addressable)
 *   - lexical escape      → path.resolve normalizes '..'; prefix-assert denies
 *   - symlink escape      → realpath moves an in-vault symlink to its true
 *                           target; if that target is outside root the final
 *                           prefix-assert denies
 *   - missing path        → realpathSync throws ENOENT → VaultPathError → 404
 *
 * Encoded traversal (%2e%2e%2f) is already URL-decoded by Next before the
 * param reaches us; resolve + realpath + prefix-assert catch it regardless.
 */
export function resolveInVault(rel: string): string {
  const root = vaultRootReal()
  if (!root) throw new VaultPathError('no vault configured')
  if (typeof rel !== 'string') throw new VaultPathError('invalid path')
  if (rel.includes('\0')) throw new VaultPathError('null byte in path')
  if (path.isAbsolute(rel)) throw new VaultPathError('absolute path rejected')

  const candidate = path.resolve(root, rel)
  // Pre-symlink lexical guard (catches ../ before we touch the filesystem).
  if (!(candidate === root || candidate.startsWith(root + path.sep))) {
    throw new VaultPathError('path escapes vault root')
  }

  let real: string
  try {
    real = fs.realpathSync(candidate)
  } catch {
    // ENOENT / EACCES / symlink loop — treat all as "not found", never leak.
    throw new VaultPathError('path not found')
  }

  // THE assertion — post-symlink. A symlink whose target is outside the vault
  // dies here.
  if (!(real === root || real.startsWith(root + path.sep))) {
    throw new VaultPathError('resolved path escapes vault root')
  }
  return real
}

/** Classify a vault-relative path without throwing: 'dir' | 'file' (markdown)
 *  | null (missing / denied / non-markdown file). Used by the page router. */
export function classifyPath(rel: string): VaultEntryKind | null {
  let real: string
  try {
    real = resolveInVault(rel)
  } catch {
    return null
  }
  let st: fs.Stats
  try {
    st = fs.statSync(real)
  } catch {
    return null
  }
  if (st.isDirectory()) return 'dir'
  if (st.isFile() && MD_EXT.test(real)) return 'file'
  return null
}

// ============================================================
// Directory listing (confined; symlinks NOT followed)
// ============================================================

function isHidden(name: string): boolean {
  return name.startsWith('.')
}

/**
 * List a confined vault directory. Includes only real subdirectories and
 * `.md`/`.markdown` files; excludes dotfiles/dotdirs (.git, .obsidian,
 * .gitkeep) and symlinks (lstat, never followed). Dirs first, then files, each
 * alpha (case-insensitive). Throws VaultPathError if `rel` is not a confined
 * directory.
 */
export function listDir(rel: string): VaultEntry[] {
  const real = resolveInVault(rel)
  if (!fs.statSync(real).isDirectory()) {
    throw new VaultPathError('not a directory')
  }

  const relBase = rel.replace(/\/+$/, '')
  const out: VaultEntry[] = []
  for (const name of fs.readdirSync(real)) {
    if (isHidden(name)) continue
    const childRel = relBase ? `${relBase}/${name}` : name
    let lst: fs.Stats
    try {
      lst = fs.lstatSync(path.join(real, name))
    } catch {
      continue
    }
    if (lst.isSymbolicLink()) continue // never follow symlinks in a listing
    let kind: VaultEntryKind
    if (lst.isDirectory()) kind = 'dir'
    else if (lst.isFile() && MD_EXT.test(name)) kind = 'file'
    else continue
    // Defense in depth: re-confine each entry (a non-symlink still gets the
    // realpath prefix-assert; anything that somehow escapes is dropped).
    try {
      resolveInVault(childRel)
    } catch {
      continue
    }
    out.push({ name, relPath: childRel, kind })
  }

  out.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === 'dir' ? -1 : 1
    return a.name.toLowerCase().localeCompare(b.name.toLowerCase())
  })
  return out
}

// ============================================================
// Note read (confined; frontmatter split; RAW body)
// ============================================================

const FRONTMATTER_RE = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/

/**
 * Read a confined markdown note. Returns parsed frontmatter (data only),
 * the RAW markdown body (never pre-rendered), and its headings. Throws
 * VaultPathError if `rel` is not a confined markdown file.
 */
export function readNote(rel: string): VaultNote {
  const real = resolveInVault(rel)
  if (!MD_EXT.test(real)) throw new VaultPathError('not a markdown note')
  if (!fs.statSync(real).isFile()) throw new VaultPathError('not a file')

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

  return {
    relPath: rel.replace(/\/+$/, ''),
    frontmatter,
    body,
    headings: extractHeadings(body),
  }
}

// ============================================================
// Basename index (confined recursive walk) for wikilink resolution
// ============================================================

interface IndexCache {
  root: string
  builtAt: number
  index: Map<string, string[]>
}
let _indexCache: IndexCache | null = null
const INDEX_TTL_MS = 10_000

/** Library-export filename prefix (`lib-<id>-<slug>.md`) that retire-library
 *  stamped onto title-addressed notes. Stripped before slugging so a
 *  `[[Product Overview]]` wikilink resolves to `lib-2-product-overview.md`. */
const LIB_EXPORT_PREFIX = /^lib-\d+-/
/** Only the leading bytes of a note are scanned for a frontmatter title —
 *  frontmatter always sits at the very top, so this bounds per-file index cost
 *  regardless of note size. */
const FRONTMATTER_SCAN_BYTES = 8192

/** Bounded, READ-ONLY frontmatter `title` read: opens the note and reads only
 *  the leading FRONTMATTER_SCAN_BYTES bytes, then parses the leading fence with
 *  the same safe js-yaml load as readNote. Returns a trimmed string title, or
 *  null. Never writes (open/read/close only); used to key the basename index by
 *  a note's declared title so a title-addressed corpus resolves. */
function readFrontmatterTitle(real: string): string | null {
  let fd: number | null = null
  try {
    fd = fs.openSync(real, 'r')
    const buf = Buffer.alloc(FRONTMATTER_SCAN_BYTES)
    const n = fs.readSync(fd, buf, 0, FRONTMATTER_SCAN_BYTES, 0)
    const head = buf.toString('utf-8', 0, n)
    const m = FRONTMATTER_RE.exec(head)
    if (!m) return null
    let parsed: unknown
    try {
      parsed = yaml.load(m[1])
    } catch {
      return null
    }
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const t = (parsed as Record<string, unknown>).title
      if (typeof t === 'string' && t.trim()) return t.trim()
    }
    return null
  } catch {
    return null
  } finally {
    if (fd !== null) {
      try {
        fs.closeSync(fd)
      } catch {
        /* best-effort close */
      }
    }
  }
}

/**
 * Index every confined note under several resolution keys, each → sorted
 * relpaths. Keys per note (all lowercased/slugged so a wikilink target can hit
 * any of them):
 *   - the exact lowercased basename (file-name addressing, e.g. `[[n]]`);
 *   - the slugified basename;
 *   - the slugified basename with the `lib-<id>-` export prefix stripped;
 *   - the slugified frontmatter `title` (title addressing, e.g.
 *     `[[Product Overview]]` → `lib-2-product-overview.md`).
 * Bounded walk (depth cap, file cap, symlinks not followed, hidden excluded);
 * short TTL cache keyed on the resolved root. Resolution NEVER trusts these
 * keys to name a path — resolveNoteTarget re-confines the chosen relpath.
 */
export function buildBasenameIndex(): Map<string, string[]> {
  const root = vaultRootReal()
  if (!root) return new Map()

  const now = Date.now()
  if (
    _indexCache &&
    _indexCache.root === root &&
    now - _indexCache.builtAt < INDEX_TTL_MS
  ) {
    return _indexCache.index
  }

  const index = new Map<string, string[]>()
  let fileCount = 0

  const addKey = (key: string, rel: string): void => {
    if (!key) return
    const arr = index.get(key)
    if (arr) {
      if (!arr.includes(rel)) arr.push(rel)
    } else {
      index.set(key, [rel])
    }
  }

  const walk = (real: string, rel: string, depth: number): void => {
    if (depth > WALK_DEPTH_CAP || fileCount >= WALK_FILE_CAP) return
    let names: string[]
    try {
      names = fs.readdirSync(real)
    } catch {
      return
    }
    for (const name of names) {
      if (isHidden(name)) continue
      if (fileCount >= WALK_FILE_CAP) return
      const childRel = rel ? `${rel}/${name}` : name
      let lst: fs.Stats
      try {
        lst = fs.lstatSync(path.join(real, name))
      } catch {
        continue
      }
      if (lst.isSymbolicLink()) continue // never follow symlinks
      if (lst.isDirectory()) {
        walk(path.join(real, name), childRel, depth + 1)
      } else if (lst.isFile() && MD_EXT.test(name)) {
        fileCount++
        const baseNoExt = name.replace(MD_EXT, '')
        // (a) exact lowercased basename — original file-name addressing.
        addKey(baseNoExt.toLowerCase(), childRel)
        // (b) slugified basename — tolerate a title-cased wikilink to a file.
        addKey(slugify(baseNoExt), childRel)
        // (c) slugified basename with the lib-<id>- export prefix stripped, so
        //     a renamed title-addressed archive note still resolves.
        const stripped = baseNoExt.replace(LIB_EXPORT_PREFIX, '')
        if (stripped !== baseNoExt) addKey(slugify(stripped), childRel)
        // (d) slugified frontmatter title — the primary archive addressing
        //     ([[Product Overview]]). Bounded, read-only head read; the child
        //     is a real (non-symlink) file under the confined root by walk
        //     construction, so reading its real path here cannot escape.
        const title = readFrontmatterTitle(path.join(real, name))
        if (title) addKey(slugify(title), childRel)
      }
    }
  }

  walk(root, '', 0)
  for (const arr of index.values()) {
    // Deterministic ambiguity resolution: shortest path first, then alpha.
    arr.sort((a, b) => a.length - b.length || a.localeCompare(b))
  }

  _indexCache = { root, builtAt: now, index }
  return index
}

/** Test seam: drop the memoized basename index. */
export function resetBasenameIndexCache(): void {
  _indexCache = null
}

/**
 * Resolve a wikilink target to a confined vault relpath, or null.
 * Order: (1) direct path match (`target`, `target.md`, `target.markdown`) that
 * confines and is a real markdown file; (2) exact lowercased basename lookup;
 * (3) slug lookup (`slugify(target)`) for title-addressed / export-prefixed
 * corpora (`[[Product Overview]]` → `lib-2-product-overview.md`). Every chosen
 * relpath is re-run through resolveInVault, so a hostile target — or a hostile
 * frontmatter title that produced a colliding index key — can at most select
 * another in-vault note, NEVER a path outside the vault.
 */
export function resolveNoteTarget(
  target: string,
  index: Map<string, string[]>
): string | null {
  const t = target.trim().replace(/^\/+/, '')
  if (!t) return null

  const tryConfinedFile = (rel: string): string | null => {
    try {
      const real = resolveInVault(rel)
      if (MD_EXT.test(real) && fs.statSync(real).isFile()) {
        return rel.replace(/\/+$/, '')
      }
    } catch {
      /* denied / missing */
    }
    return null
  }

  // (1) Path-ish target.
  const candidates = MD_EXT.test(t) ? [t] : [`${t}.md`, `${t}.markdown`, t]
  for (const c of candidates) {
    const hit = tryConfinedFile(c)
    if (hit) return hit
  }

  // (2) Exact lowercased basename lookup.
  const base = t.replace(MD_EXT, '').toLowerCase()
  const byBase = index.get(base)
  if (byBase) {
    for (const rel of byBase) {
      const hit = tryConfinedFile(rel)
      if (hit) return hit
    }
  }

  // (3) Slug lookup — title-addressed / export-prefixed notes. Keys were
  //     slugged at index time; tryConfinedFile still re-confines each relpath.
  const slug = slugify(t.replace(MD_EXT, ''))
  if (slug && slug !== base) {
    const bySlug = index.get(slug)
    if (bySlug) {
      for (const rel of bySlug) {
        const hit = tryConfinedFile(rel)
        if (hit) return hit
      }
    }
  }
  return null
}
