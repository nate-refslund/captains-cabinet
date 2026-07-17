/**
 * VaultMarkdown.tsx — the SAFE markdown renderer for the Library (/library),
 * the read-only vault reader (Captain naming ruling 2026-07-17; /vault
 * redirects to /library).
 *
 * A pure, synchronous component: it takes an ALREADY-PREPROCESSED markdown
 * string (wikilinks rewritten to internal links upstream) and renders it with
 * react-markdown. Security posture (blueprint §3):
 *
 *   - react-markdown renders to a React element tree — NO dangerouslySetInnerHTML
 *     anywhere.
 *   - rehype-raw is deliberately ABSENT, so embedded raw HTML (<script>,
 *     <iframe>, on*-handlers) is treated as literal text, never parsed to DOM.
 *   - rehype-sanitize (schema derived from the GitHub defaultSchema, with <img>
 *     dropped to avoid any external image fetch) sanitizes the hast tree as
 *     defense-in-depth; its protocol allowlist drops javascript:/vbscript:/data:
 *     on href.
 *   - react-markdown's default urlTransform independently strips dangerous URL
 *     protocols — double coverage on `[text](javascript:…)`.
 *   - anchors render through a hardened InternalAnchor: internal /library
 *     (and legacy /vault, which 307s to /library) links use next/link; the
 *     unresolved-wikilink sentinel renders inert; external http(s)/mailto
 *     open with rel="noopener noreferrer nofollow"; anything else renders as
 *     inert text.
 */

import Link from 'next/link'
import type { AnchorHTMLAttributes, ReactNode } from 'react'
import Markdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import { VAULT_UNRESOLVED_HREF, slugify } from '@/lib/vault-wikilinks'

// Sanitize schema: the GitHub defaultSchema is already safe (its href protocol
// allowlist excludes javascript:/vbscript:/data:). We additionally drop <img>
// so a note can never make the viewer's browser fetch an external image
// (honors the "no new external calls" posture; wave-1 serves no assets).
const sanitizeSchema = {
  ...defaultSchema,
  tagNames: (defaultSchema.tagNames ?? []).filter((t) => t !== 'img'),
}

function InternalAnchor({
  href,
  children,
}: AnchorHTMLAttributes<HTMLAnchorElement> & { href?: string }) {
  const h = typeof href === 'string' ? href : ''

  // Unresolved wikilink (or empty href) → inert styled text, never a link.
  if (!h || h === VAULT_UNRESOLVED_HREF) {
    return <span className="wikilink-unresolved">{children}</span>
  }
  // App-internal Library link → client-side nav via next/link. Match the
  // route exactly or a path under it — NOT a sibling like `/libraryfoo`.
  // `/vault/...` stays recognized as internal: that route is a permanent
  // redirect alias to `/library/...` (Captain naming ruling 2026-07-17), and
  // older notes may carry literal `/vault/...` markdown links.
  if (
    h === '/library' ||
    h.startsWith('/library/') ||
    h === '/vault' ||
    h.startsWith('/vault/')
  ) {
    return (
      <Link href={h} className="wikilink-resolved">
        {children}
      </Link>
    )
  }
  // External / mail / tel (already protocol-checked by sanitize) → new tab,
  // no referrer, no window.opener.
  if (/^(https?:)?\/\//i.test(h) || h.startsWith('mailto:') || h.startsWith('tel:')) {
    return (
      <a href={h} target="_blank" rel="noopener noreferrer nofollow">
        {children}
      </a>
    )
  }
  // In-page anchor (#heading) → plain internal anchor.
  if (h.startsWith('#')) {
    return <a href={h}>{children}</a>
  }
  // Anything else survived sanitize (safe protocol) but is not a recognized
  // navigation target — render inert rather than fabricate navigation.
  return <span>{children}</span>
}

/** Minimal hast node shape for reading a heading's plain text. */
interface HastNode {
  type?: string
  value?: string
  children?: HastNode[]
}

/** Concatenate the visible text of a hast node (for the heading slug id). */
function hastText(node: HastNode | undefined): string {
  if (!node) return ''
  if (node.type === 'text') return node.value ?? ''
  if (!node.children) return ''
  let s = ''
  for (const c of node.children) s += hastText(c)
  return s
}

type HeadingTag = 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6'

/**
 * Build the react-markdown component overrides. Headings get an `id` slug so
 * `[[note#section]]` fragment links can anchor. The id is assigned by this
 * React component AFTER rehype-sanitize has run on the hast (so the schema
 * never clobbers it), and it is `slugify()` output only (`[a-z0-9-]`, no
 * injection). Duplicate heading slugs are disambiguated with a per-render
 * running count (`dup`, `dup-1`, …), matching extractHeadings/github-slugger
 * and the `slugify(section)` used to build the wikilink hrefs.
 */
function makeComponents(): Components {
  const slugCounts: Record<string, number> = {}
  const heading = (Tag: HeadingTag) => {
    function Heading({ node, children }: { node?: unknown; children?: ReactNode }) {
      const base = slugify(hastText(node as HastNode | undefined))
      const count = slugCounts[base] ?? 0
      slugCounts[base] = count + 1
      const id = count === 0 ? base : `${base}-${count}`
      return <Tag id={id}>{children}</Tag>
    }
    return Heading
  }
  return {
    a: ({ href, children }) => (
      <InternalAnchor href={typeof href === 'string' ? href : undefined}>
        {children}
      </InternalAnchor>
    ),
    h1: heading('h1'),
    h2: heading('h2'),
    h3: heading('h3'),
    h4: heading('h4'),
    h5: heading('h5'),
    h6: heading('h6'),
  }
}

export default function VaultMarkdown({ markdown }: { markdown: string }) {
  // Rebuilt per render so the duplicate-slug counter starts fresh each note.
  const components = makeComponents()
  return (
    <div className="vault-prose">
      <Markdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSanitize, sanitizeSchema]]}
        components={components}
      >
        {markdown}
      </Markdown>
    </div>
  )
}
