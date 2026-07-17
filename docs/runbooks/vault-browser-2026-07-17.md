# Vault browser — read-only dashboard view (2026-07-17)

The dashboard `/vault` route is a **read-only** browser over the cabinet's
**org vault** — the `vault/` markdown corpus (architecture, decisions,
incidents, designs, plans, the retired Library archive, any captain/org doc).
It lists directories and renders notes as sanitized HTML in the browser. It is
a filesystem reader: **no database, no vector store, no mutation.**

- Route: `cabinet/dashboard/src/app/(authenticated)/vault/[[...path]]/page.tsx`
  (one catch-all server component: empty path → root listing, dir → listing,
  file → rendered note).
- Data layer: `cabinet/dashboard/src/lib/vault.ts` (root resolution +
  confinement + `listDir`/`readNote`/note index). The index keys each note by
  basename **and** by slug — slugified basename, slugified basename with the
  `lib-<id>-` export prefix stripped, and slugified frontmatter `title` — so a
  title-addressed archive (`[[Product Overview]]` → `lib-2-product-overview.md`)
  resolves. Every chosen relpath is re-run through `resolveInVault`, so a
  hostile title only ever selects another in-vault note, never an escape.
- Wikilinks: `cabinet/dashboard/src/lib/vault-wikilinks.ts` (parse + rewrite to
  internal links only). The rewrite is **code-aware**: `[[...]]` inside fenced
  blocks or inline code spans is left literal, so illustrative wikilinks render
  verbatim and the internal unresolved-sentinel never leaks into shown code.
- Renderer: `cabinet/dashboard/src/components/vault/VaultMarkdown.tsx`
  (react-markdown + remark-gfm + rehype-sanitize). Headings get a `slugify()`
  `id` (assigned by the React component, after sanitize; slug chars only) so
  `[[note#section]]` fragment links anchor.
- Nav: `Vault` entry in `ADVANCED_NAV` (`src/lib/nav-config.ts`), Advanced mode
  only. The retired `/library` notice links onward to `/vault`.

## What it reads — the ORG vault, never the personal vault

Two vault resolvers exist in `framework/env.py`:

| Resolver | Points at | Surfaced by `/vault`? |
|----------|-----------|------------------------|
| `vault_dir()` | the **captain's personal** brain/Obsidian vault (on this box `~/obsidian/screenpipe-brain`) | **NEVER** |
| `org_vault_dir()` | the **org** corpus = `<repo>/vault/` | **Yes** |

`lib/vault.ts` `vaultRoot()` is a faithful TS mirror of `org_vault_dir()`:

1. env `CABINET_ORG_VAULT_DIR` →
2. env `CABINET_PRODUCT_BRAIN_DIR` (legacy alias) →
3. `org_vault_dir` (else legacy `product_brain_dir`) key in
   `instance/config/platform.yml` then `product.yml`, if the dir exists →
4. `<repo>/vault` if it is a directory →
5. `<repo>/product-brain` if it is a directory →
6. `null` (fail-closed — no vault ⇒ an empty browser, never a crash).

It **deliberately does not read the `vault_dir` key.** Reading the wrong key
would expose the captain's personal Obsidian vault over the web — the single
highest-consequence constraint of this view. To relocate the org vault, set
`CABINET_ORG_VAULT_DIR` or the `org_vault_dir` config key; do **not** repoint
`vault_dir`.

## Security posture

- **Auth.** `/vault` (and any future `/api/vault/*`) sit under the
  `(authenticated)` route group and are **not** in the middleware's static
  allowlist, so the HMAC `cabinet_session` cookie gates them automatically —
  unauthenticated requests 307 to `/login`. No new auth mechanism.
- **Path confinement.** Every read goes through `resolveInVault()`:
  `path.resolve` normalizes `..`, then `fs.realpathSync` resolves symlinks, and
  a prefix-assert requires the result to stay under the realpath'd vault root.
  This defeats `../` traversal, absolute paths, URL-encoded traversal, NUL
  injection, and **symlink escape** (an in-vault symlink whose target is
  outside the root is denied). Listings `lstat` entries and never follow
  symlinks. Any denial → a generic **404** (never 403 — status never leaks
  path existence).
- **Safe markdown.** Rendered via react-markdown (React element tree, **no**
  `dangerouslySetInnerHTML`). `rehype-raw` is intentionally **absent**, so raw
  HTML (`<script>`, `<iframe>`, `on*=` handlers) is literal text, never DOM.
  `rehype-sanitize` (GitHub `defaultSchema`, `<img>` dropped) + react-markdown's
  default `urlTransform` both strip `javascript:`/`vbscript:`/`data:` URLs.
- **Wikilinks are internal-only.** `[[note]]` / `[[note#section]]` /
  `[[note|alias]]` resolve against a **confined** filesystem index (basename +
  slug + frontmatter-title keys) and rewrite to internal `/vault/…` links;
  the resolved relpath is itself re-run through `resolveInVault`. Wikilinks
  inside code are left literal. Unresolved targets render as inert styled text —
  **no create affordance** (read-only). Never an external or `javascript:` href.
- **Read-only / DB-free.** No write/edit/delete endpoints; MVP is pure server
  components with zero new API routes. The vault modules import no `@/lib/db`,
  no `pg`, and issue no `query(` — the retired Library vector store stays
  retired.

## Not in this wave (Phase 2)

- Serving binary assets/images referenced by notes (images render broken; a
  confined, content-type-allowlisted asset route is Phase 2).
- Backlinks panel, force-directed graph, wikilink hovercard previews,
  full-text search, and repointing the Command Palette to a vault search.
- **Tailscale phone exposure.** Reaching `/vault` from a phone over the tailnet
  is a Phase-2 deployment concern; it inherits the same `cabinet_session` auth
  and confinement — no route is exempted for it.

## Tests

- `src/lib/vault.test.ts` — traversal/symlink/NUL/absolute/dotfile/non-md
  negative controls, positive in-vault resolve, the fail-closed +
  never-reads-`vault_dir` root resolution, title/slug/export-prefix wikilink
  resolution, and the hostile-title-cannot-escape control.
- `src/lib/vault-wikilinks.test.ts` — parse + internal-only rewrite, unresolved
  sentinel, hostile-target inertness, and code-awareness (inline + fenced
  wikilinks stay literal; oversized-body guard).
- `src/components/vault/vault-markdown.test.tsx` — XSS negative controls
  (`<script>`, `<img onerror>`, `javascript:`/`data:`/`vbscript:` URLs), heading
  slug ids, exact `/vault` prefix, and the end-to-end code-span-literal check.
- `vault-route.test.ts` (beside the route's `page.tsx`, in the `/vault` route
  group) — source contract: read-only (no write fs calls / no mutation HTTP
  verbs), DB-free.
- `src/middleware.test.ts` — `/vault` with no cookie → 307 `/login`.

Run: `cd cabinet/dashboard && npm ci && npm test && npm run typecheck`.
