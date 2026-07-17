/**
 * vault-wikilinks.ts — internal-only wikilink support for the Library
 * (/library), the read-only vault reader (Captain naming ruling 2026-07-17:
 * the vault is where it's kept, the Library is where you read; /vault
 * redirects to /library).
 *
 * The three PURE parsers below (parseWikilinks, slugify, extractHeadings) are
 * COPIED VERBATIM from lib/wikilinks.ts (Spec 037; parseWikilinks:84,
 * slugify:122, extractHeadings:135). They are copied, not imported, because
 * lib/wikilinks.ts does `import { query } from './db'` at module load — so
 * importing ANY symbol from it would pull `pg` into the vault module graph and
 * break the DB-free confinement guarantee (blueprint §2/§5;
 * test_library_retirement_ratchet.py). Keep them byte-identical to their
 * source if that file's parsers change.
 *
 * The DB-bound resolveWikilinks/renderWikilinks/indexLinks/getBacklinks from
 * wikilinks.ts are deliberately NOT reused: they hit library_records over pg
 * and emit raw HTML strings with a /library/new create affordance. This module
 * resolves against the vault FILESYSTEM and rewrites wikilinks to ordinary
 * internal markdown links, which react-markdown + rehype-sanitize then render
 * with zero raw HTML.
 */

// ============================================================
// Types (mirrors of the reused wikilinks.ts shapes)
// ============================================================

export interface ParsedWikilink {
  raw: string
  target: string
  alias: string | null
  section: string | null
  startIdx: number
  endIdx: number
}

export interface ExtractedHeading {
  text: string
  level: number
  slug: string
  position: number
}

// ============================================================
// Regex — no nested brackets, no bold-inside-wikilink.
// (copied verbatim from wikilinks.ts:84)
// ============================================================

const WIKILINK_REGEX = /(?<!\\)\[\[([^\]|#\n]+?)(?:#([^\]|]+?))?(?:\|([^\]]+?))?\]\]/g

/** Parse all [[...]] wikilinks from a markdown string. (wikilinks.ts:94) */
export function parseWikilinks(markdown: string): ParsedWikilink[] {
  const results: ParsedWikilink[] = []
  let match: RegExpExecArray | null

  WIKILINK_REGEX.lastIndex = 0
  while ((match = WIKILINK_REGEX.exec(markdown)) !== null) {
    const [raw, target, section, alias] = match
    if (target.includes('*') || target.includes('_') || target.includes('`')) {
      continue
    }
    results.push({
      raw,
      target: target.trim(),
      alias: alias?.trim() ?? null,
      section: section?.trim() ?? null,
      startIdx: match.index,
      endIdx: match.index + raw.length,
    })
  }

  return results
}

// ============================================================
// Bounded parse wrapper (vault-side ReDoS hardening — NOT part of the
// verbatim mirror above; wikilinks.ts has no equivalent)
// ============================================================

/** More `[[` start positions than this marks a body pathological — real
 *  notes carry orders of magnitude fewer links. Bounding the start count
 *  bounds the regex engine's worst case to starts × body-length. */
export const WIKILINK_MAX_STARTS = 500

/**
 * parseWikilinks with linear pre-guards (2026-07-17 review fix). The verbatim
 * WIKILINK_REGEX is quadratic on adversarial bodies: every `[[` start
 * position can rescan toward EOF (measured ~16.5s SYNCHRONOUS on 200KB of
 * `[` — an event-loop-blocking DoS once the graph parses the whole corpus).
 * Guards, all O(n):
 *   1. bodies over `maxBytes` parse to [] (caller-declared budget);
 *   2. no `]]` anywhere → no match is possible → [] (kills the pure-`[`
 *      class outright, where every start scans to EOF and fails);
 *   3. more than WIKILINK_MAX_STARTS `[[` positions → pathological → []
 *      (bounds total regex work to starts × maxBytes even when a trailing
 *      `]]` defeats guard 2).
 * Pathological bodies therefore degrade to "no links harvested" — the same
 * observable behavior as the pre-existing oversize skip. Real notes are
 * untouched: bounded === plain parseWikilinks on them (differential-tested).
 */
export function parseWikilinksBounded(
  markdown: string,
  maxBytes: number
): ParsedWikilink[] {
  if (markdown.length > maxBytes) return []
  if (!markdown.includes(']]')) return []
  let starts = 0
  for (let i = markdown.indexOf('[['); i !== -1; i = markdown.indexOf('[[', i + 1)) {
    if (++starts > WIKILINK_MAX_STARTS) return []
  }
  return parseWikilinks(markdown)
}

/** github-slugger compatible deterministic slug. (wikilinks.ts:122) */
export function slugify(text: string): string {
  return (
    text
      .toLowerCase()
      .replace(/[^\w\s-]/g, '')
      .replace(/[\s_]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'section'
  )
}

/** Extract ATX headings + disambiguated slugs from markdown. (wikilinks.ts:135) */
export function extractHeadings(markdown: string): ExtractedHeading[] {
  const lines = markdown.replace(/\r\n?/g, '\n').split('\n')
  const slugCount: Record<string, number> = {}
  const headings: ExtractedHeading[] = []
  let position = 0

  for (const line of lines) {
    const match = line.match(/^(#{1,6})\s+(.+)$/)
    if (match) {
      const level = match[1].length
      const text = match[2].trim()
      const baseSlug = slugify(text)

      const count = slugCount[baseSlug] ?? 0
      slugCount[baseSlug] = count + 1
      const slug = count === 0 ? baseSlug : `${baseSlug}-${count}`

      headings.push({ text, level, slug, position })
      position++
    }
  }

  return headings
}

// ============================================================
// Internal href helpers + wikilink rewriting (vault-native, no DB)
// ============================================================

/** Hash sentinel marking an UNRESOLVED wikilink. slugify() never emits
 *  underscores, so this can never collide with a real heading anchor. The
 *  renderer turns it into inert styled text — never a link, never a create
 *  affordance (read-only). */
export const VAULT_UNRESOLVED_HREF = '#__vault_unresolved__'

/** Build an app-internal /library href from a vault relpath (+ optional
 *  section slug) — the name stays `vaultHref` because the path addresses a
 *  note IN the vault corpus; the Library route is where it is read (Captain
 *  ruling 2026-07-17). Each path segment is percent-encoded, so the href can
 *  never carry a literal `)` (which would break the surrounding markdown
 *  link) nor an injected protocol — it is ALWAYS a same-origin internal
 *  path. */
export function vaultHref(relPath: string, sectionSlug?: string | null): string {
  const encoded = relPath
    .split('/')
    .filter(Boolean)
    // encodeURIComponent leaves ()!~*' unescaped; a literal ')' would close the
    // surrounding markdown link early, so encode parens too.
    .map((s) => encodeURIComponent(s).replace(/\(/g, '%28').replace(/\)/g, '%29'))
    .join('/')
  const hash = sectionSlug ? `#${sectionSlug}` : ''
  return `/library/${encoded}${hash}`
}

/** Escape markdown-significant characters in wikilink display text so an alias
 *  cannot break out of the `[label]` or re-introduce emphasis / raw angle
 *  brackets. Newlines collapse to spaces. */
function escapeLabel(text: string): string {
  return text.replace(/\s+/g, ' ').replace(/[\\`*_[\]<>|()]/g, '\\$&')
}

/** A resolver injected by the caller: a wikilink target → a confined vault
 *  relpath, or null when it does not resolve to an in-vault note. */
export type WikilinkResolver = (target: string) => string | null

/** Bodies larger than this are rendered WITHOUT wikilink rewriting (the raw
 *  `[[...]]` shows as literal text). Real notes are far smaller. This size
 *  cap alone does NOT tame the parse regex (200KB of `[` still cost ~16.5s);
 *  the linear guards live in parseWikilinksBounded, which rewriteWikilinks
 *  now parses through (defense-in-depth — the wikilink surface is behind
 *  auth + confinement and only reads committed vault files). */
const WIKILINK_REWRITE_MAX_BYTES = 200_000

interface CodeRange {
  /** char offset (inclusive). */
  start: number
  /** char offset (exclusive). */
  end: number
}

const BACKTICK = 96 // '`'

/**
 * Char ranges covered by fenced code blocks (``` / ~~~) and inline code spans,
 * so the wikilink rewrite can leave `[[...]]` inside code LITERAL — an
 * illustrative wikilink in prose (e.g. README's `` `[[wikilinks]]` ``) must
 * render verbatim, never as a rewritten link or the unresolved sentinel.
 * Line pass for fences, then a run-paired pass for inline spans over the
 * non-fenced remainder — no catastrophic backtracking.
 */
function computeCodeRegions(md: string): CodeRange[] {
  const regions: CodeRange[] = []
  const n = md.length
  const nonFenced: CodeRange[] = []

  let spanStart = 0
  let i = 0
  let inFence = false
  let fenceChar = ''
  let fenceLen = 0
  let fenceStart = 0

  while (i <= n) {
    const nl = md.indexOf('\n', i)
    const lineEnd = nl === -1 ? n : nl
    const line = md.slice(i, lineEnd)
    if (!inFence) {
      const m = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line)
      // An opening backtick fence's info string may not contain a backtick.
      if (m && (m[1][0] === '~' || !m[2].includes('`'))) {
        nonFenced.push({ start: spanStart, end: i }) // text before the fence
        inFence = true
        fenceChar = m[1][0]
        fenceLen = m[1].length
        fenceStart = i
      }
    } else {
      const m = /^ {0,3}(`{3,}|~{3,})[ \t]*$/.exec(line)
      if (m && m[1][0] === fenceChar && m[1].length >= fenceLen) {
        const end = nl === -1 ? n : nl + 1 // include the closing fence line
        regions.push({ start: fenceStart, end })
        inFence = false
        spanStart = end
        i = end
        continue
      }
    }
    if (nl === -1) break
    i = nl + 1
  }
  if (inFence) {
    regions.push({ start: fenceStart, end: n }) // unclosed fence runs to EOF
  } else {
    nonFenced.push({ start: spanStart, end: n })
  }

  for (const span of nonFenced) collectInlineCode(md, span.start, span.end, regions)
  regions.sort((a, b) => a.start - b.start)
  return regions
}

/** Append inline-code-span ranges within md[from,to). CommonMark rule: a
 *  backtick run opens; the next run of EQUAL length closes it. Same-length runs
 *  pair off, so the forward search cannot degrade to quadratic on real input. */
function collectInlineCode(md: string, from: number, to: number, out: CodeRange[]): void {
  const runs: Array<{ start: number; len: number }> = []
  let k = from
  while (k < to) {
    if (md.charCodeAt(k) === BACKTICK) {
      let len = 1
      while (k + len < to && md.charCodeAt(k + len) === BACKTICK) len++
      runs.push({ start: k, len })
      k += len
    } else {
      k++
    }
  }
  let a = 0
  while (a < runs.length) {
    const open = runs[a]
    let b = a + 1
    while (b < runs.length && runs[b].len !== open.len) b++
    if (b < runs.length) {
      out.push({ start: open.start, end: runs[b].start + runs[b].len })
      a = b + 1
    } else {
      a++
    }
  }
}

/**
 * Rewrite every [[wikilink]] in `markdown` to an ordinary internal markdown
 * link BEFORE react-markdown runs. Resolved targets become
 * `[alias](/library/<relpath>#<section-slug>)`; unresolved targets become
 * `[alias](VAULT_UNRESOLVED_HREF)` (rendered as inert styled text). Never
 * emits an external or `javascript:` href.
 *
 * Wikilinks INSIDE code (fenced blocks or inline spans) are left LITERAL so
 * illustrative examples render verbatim — the internal sentinel never leaks
 * into displayed code. Oversized or pathological bodies skip rewriting
 * entirely (parseWikilinksBounded returns [] for them — see its guards).
 */
export function rewriteWikilinks(
  markdown: string,
  resolve: WikilinkResolver
): string {
  const links = parseWikilinksBounded(markdown, WIKILINK_REWRITE_MAX_BYTES)
  if (links.length === 0) return markdown

  const regions = computeCodeRegions(markdown)
  const inCode = (idx: number): boolean => {
    for (const r of regions) {
      if (idx < r.start) break // regions are sorted by start
      if (idx < r.end) return true
    }
    return false
  }

  // Reverse order so earlier startIdx values stay valid as we splice.
  const sorted = [...links].sort((a, b) => b.startIdx - a.startIdx)
  let result = markdown

  for (const link of sorted) {
    if (inCode(link.startIdx)) continue // inside code → leave the [[...]] literal
    const label = escapeLabel(link.alias ?? link.target)
    const relPath = resolve(link.target)
    let replacement: string
    if (relPath) {
      const slug = link.section ? slugify(link.section) : null
      replacement = `[${label}](${vaultHref(relPath, slug)})`
    } else {
      replacement = `[${label}](${VAULT_UNRESOLVED_HREF})`
    }
    result = result.slice(0, link.startIdx) + replacement + result.slice(link.endIdx)
  }

  return result
}
