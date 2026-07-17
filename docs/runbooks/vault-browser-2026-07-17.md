# Vault browser — read-only dashboard view (2026-07-17) — a.k.a. THE LIBRARY

The dashboard's **Library** (`/library`) is a **read-only** browser over the
cabinet's **org vault** — the `vault/` markdown corpus (architecture,
decisions, incidents, designs, plans, the retired Library archive, any
captain/org doc). It lists directories and renders notes as sanitized HTML in
the browser. It is a filesystem reader: **no database, no vector store, no
mutation.**

## Naming (Captain ruling, 2026-07-17)

> "Keep the name Library — it fits the world; the vault is where it's kept,
> the Library is where you read."

The browser shipped at `/vault` and moved to `/library` the same day:

- `/library` renders the browser (the reader RETURNED one day after the
  Library **store** retired — the store stays retired; see
  `library-retirement-2026-07-16.md`).
- `/vault` is a **redirect alias** — `/vault/architecture.md` →
  `/library/architecture.md` (segments re-percent-encoded; never an open
  redirect; the example is a real tracked note, so the G6 docs sweep vouches
  for it). Old deep links keep working.
- Nav shows a single **Library** entry (both modes); the separate Vault entry
  was dropped.
- The old full-page retirement notice is now a collapsible **History** note
  on the Library root (store retired 2026-07-16 · reader returned 2026-07-17 ·
  content in the vault).
- Legacy 1–2-segment extension-less `/library/...` deep links (retired
  space/record id shapes) redirect to `/library`; note-shaped misses stay
  generic 404s.

## Surfaces

- Route: `cabinet/dashboard/src/app/(authenticated)/library/[[...path]]/page.tsx`
  (one catch-all server component: empty path → root listing + History note +
  Browse|Graph tabs, dir → listing, file → rendered note + backlinks).
  `/vault/[[...path]]/page.tsx` is the redirect stub.
- Graph: `/library/graph` (`graph/page.tsx`, same address as the
  pre-retirement Spec 045 graph) — the `[[wikilink]]` network over the
  FILESYSTEM, built by `src/lib/vault-graph.ts` (confined walk on `listDir`,
  edges from `parseWikilinksBounded` + `resolveNoteTarget`; deduped, no
  self-loops, bounded: depth 8 / 20000 files / **32KB per-note parse cap** /
  8MB corpus-wide parse budget; ~30s TTL cache). The parse itself carries
  linear ReDoS guards (no-`]]` pre-guard + a 500-`[[`-starts cap in
  `parseWikilinksBounded`) — pre-guard-less, a single planted 200KB note of
  `[` cost ~16.5s of synchronous CPU on every cold build. Over-bound bodies
  keep their node and skip their edges (graph flags `truncated`).
  The server component serializes the data as props into the resurrected
  `components/library/GraphCanvas.tsx` client canvas — **zero API routes,
  zero fetch, zero DB**. Node click navigates to `/library/<path>`; the hover
  tooltip label is HTML-escaped in `components/library/graph-tooltip.ts`
  (float-tooltip renders string labels via innerHTML — frontmatter titles and
  dir names must never reach it raw). NOTE: the
  static `graph` segment shadows a top-level vault entry literally named
  `graph` (none exists; deeper paths still reach the browser).
- Backlinks: `components/library/BacklinksPanel.tsx` under each note — the
  graph's edge list inverted (`getBacklinks`), grouped by top-level folder,
  linking back into the Library.
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
  `[[note#section]]` fragment links anchor. Wikilinks rewrite to `/library/…`
  hrefs (`vaultHref`); literal legacy `/vault/…` links in notes stay
  recognized as internal (the alias 307s them).
- Nav: single `Library` entry in BOTH `ADVANCED_NAV` and `CONSUMER_NAV`
  (`src/lib/nav-config.ts`) since the 2026-07-17 naming ruling.

## What it reads — the ORG vault, never the personal vault

Two vault resolvers exist in `framework/env.py`:

| Resolver | Points at | Surfaced by the Library? |
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

- **Auth.** `/library`, the `/vault` alias, and any future `/api/vault/*` sit
  under the `(authenticated)` route group and are **not** in the middleware's
  static allowlist, so the HMAC `cabinet_session` cookie gates them
  automatically — unauthenticated requests 307 to `/login` (the gate runs
  BEFORE the alias redirect is computed). No new auth mechanism.
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
  slug + frontmatter-title keys) and rewrite to internal `/library/…` links;
  the resolved relpath is itself re-run through `resolveInVault`. Wikilinks
  inside code are left literal. Unresolved targets render as inert styled text —
  **no create affordance** (read-only). Never an external or `javascript:` href.
- **Read-only / DB-free.** No write/edit/delete endpoints; pure server
  components with zero new API routes — the graph data crosses to the client
  as serialized props, not a fetch. The reader modules import no `@/lib/db`,
  no `pg`, no `@/lib/library`, and issue no `query(` — the retired Library
  vector store stays retired.
- **Graph/backlinks confinement.** The graph walk is built on `listDir`
  (symlinks lstat-skipped, every entry re-confined), so a symlink-escape note
  never becomes a node or an edge; traversal-shaped wikilink targets resolve
  to null and produce no edge.

## Not in this wave (Phase 2)

- Serving binary assets/images referenced by notes (images render broken; a
  confined, content-type-allowlisted asset route is Phase 2).
- Wikilink hovercard previews, full-text search, and repointing the Command
  Palette to a vault search. (The backlinks panel and force-directed graph
  SHIPPED 2026-07-17 with the Library identity move — see Surfaces above.)
- **Tailscale phone exposure.** Reaching the Library from a phone over the
  tailnet is a Phase-2 deployment concern; it inherits the same
  `cabinet_session` auth and confinement — no route is exempted for it.

## Tests

- `src/lib/vault.test.ts` — traversal/symlink/NUL/absolute/dotfile/non-md
  negative controls, positive in-vault resolve, the fail-closed +
  never-reads-`vault_dir` root resolution, title/slug/export-prefix wikilink
  resolution, and the hostile-title-cannot-escape control.
- `src/lib/vault-graph.test.ts` — nodes == fixture note count, edges match
  wikilinks exactly (dedupe, no self-loops, ghosts inert), ★ symlink-escape
  note never enters, traversal-shaped targets produce no edge, backlink
  inversion, TTL-cache seams, empty-vault fail-closed, ★ edge-harvest bounds
  (planted 200KB `[` note / many-starts note / over-32KB note all degrade to
  node-without-edges with a fast build; in-bounds notes keep their edges).
- `src/lib/vault-wikilinks.test.ts` — parse + internal-only rewrite, unresolved
  sentinel, hostile-target inertness, and code-awareness (inline + fenced
  wikilinks stay literal; oversized-body guard). Hrefs pin `/library/…`.
  ★ `parseWikilinksBounded` ReDoS guards: the measured 200KB-`[` DoS case,
  the trailing-`]]` variant, and the max-work case inside the guards all
  timed under CI-safe bounds; differential parity with `parseWikilinks` on
  real-shaped input; exactly-at-the-starts-cap bodies still parse.
- `src/components/library/graph-tooltip.test.ts` — hover-tooltip XSS negative
  controls: `<img onerror>` titles, `<script>` dirs, attribute-breakout
  quotes, and a poisoned non-number degree all yield escaped text (the
  tooltip string feeds float-tooltip's innerHTML branch).
- `src/components/vault/vault-markdown.test.tsx` — XSS negative controls
  (`<script>`, `<img onerror>`, `javascript:`/`data:`/`vbscript:` URLs), heading
  slug ids, exact `/library` prefix (+ legacy `/vault` stays internal), and the
  end-to-end code-span-literal check.
- `library-route.test.ts` (in the `/library` route group) — the superseded
  contract WITH PROVENANCE (Captain ruling 2026-07-17): retired STORE stays
  retired (whole route tree + reader modules DB-free), read-only source
  contract (moved from the old `/vault` contract), the reader-returns asserts
  (browser moved not duplicated; History note), zero-endpoint graph, legacy
  deep-link redirects.
- `vault-route.test.ts` (in the `/vault` route group) — the redirect alias:
  root + deep + encoding parity with `vaultHref`, ★ no-open-redirect control,
  stub-is-only-a-redirect source contract.
- `src/middleware.test.ts` — `/vault` AND `/library` (+ deep paths, graph tab)
  with no cookie → 307 `/login`.

Run: `cd cabinet/dashboard && npm ci && npm test && npm run typecheck`.
