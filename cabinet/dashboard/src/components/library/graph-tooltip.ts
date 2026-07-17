/**
 * graph-tooltip.ts — PURE hover-tooltip label builder for GraphCanvas.
 *
 * SECURITY (2026-07-17 review fix): react-force-graph-2d hands the nodeLabel
 * accessor's return value to float-tooltip, and float-tooltip renders STRING
 * content via d3-selection `.html()` — i.e. innerHTML (verified in
 * float-tooltip@1.7.5 dist: `tooltipEl.html(state.content)`). Node titles
 * come VERBATIM from vault note frontmatter `title:` and dirs from folder
 * names, so an unescaped label string is a stored-XSS sink on hover — the
 * one DOM-HTML sink in the graph view (canvas fillText and the vaultHref
 * click path are not HTML). Every interpolated string MUST pass through
 * escapeHtml() here; degree is coerced to a Number so nothing stringly can
 * ride through it. Keep this module DOM-free and side-effect-free so the
 * escaping contract stays unit-testable without a browser.
 */

/** Label shown for root-level notes (dir === ''). */
export const ROOT_DIR_LABEL = '(root)'

/** Minimal HTML entity escaping — neutralizes tag/attribute breakouts for
 *  content interpolated into an innerHTML sink. */
export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export interface TooltipNodeFields {
  /** Frontmatter title (UNTRUSTED — escaped here). */
  title: string
  /** Top-level vault folder, '' for root (UNTRUSTED — escaped here). */
  dir: string
  /** In+out wikilink degree. */
  degree: number
}

/**
 * The hover-tooltip label for a graph node. Returns an HTML-ESCAPED string —
 * safe to hand to float-tooltip's innerHTML string branch; renders as the
 * literal text `<title> · <dir> · degree <n>`.
 */
export function graphNodeTooltipHtml(node: TooltipNodeFields): string {
  const title = escapeHtml(String(node.title))
  const dir = escapeHtml(String(node.dir) || ROOT_DIR_LABEL)
  return `${title} · ${dir} · degree ${Number(node.degree)}`
}
