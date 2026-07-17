# The world Library card — runbook (2026-07-17)

The Library building in Cabinet World now opens the Library itself: a
world-native, READ-ONLY card that browses the org vault, reads notes, and
searches the org's knowledge — "the world as an actual library to search
for history and knowledge" (Captain direction), landing the ratified spec
rows: world-unified-spec-v2 §5.2 Memory Library "[v3] card gains GET-only
search (P6)", §9.2 "Library query dialog = input row + typewriter results;
GET-only", and the §9.3 fresh ruling that the library surface stays
read-only.

## The interaction (one continuous world — never a scene swap)

* `/world` (EngineClient): the `library` element renders at its authored
  anchor (world-buildings.ts; today as the honest staged worksite marker —
  `STAGED_VOCAB_ELEMENTS` — until proper library art lands via the asset
  forge).
* **Primary click at close/mid LOD** on the library building → the
  LibraryCard opens as chrome OVER the live canvas. The camera, canvas and
  logical tick are untouched — the world keeps ticking under the card
  (`library-card.test.ts` pins that the canvas mount is never gated on the
  card, and that the card carries no navigation APIs).
* **Primary at far LOD** keeps the navigate-fly camera law (fly closer,
  then enter). **Secondary** keeps the era×rung inspect card (Legend Law —
  the building still cites `growth-ladders.yml`, metric
  `memory_rows_total`).
* **Escape** closes the card (same shell handler as the mailbox).
* In-note wikilinks that resolve to internal library hrefs (`/library/…`,
  or its permanent redirect alias `/vault/…`) are intercepted (capture
  phase, `overlayPathFromHref`) and open IN-CARD; internal-shaped hrefs
  that do NOT map to a safe vault relpath (a note-authored
  `/library/%zz` or `/library/../x`) are INERT (`isInternalLibraryHref` —
  never a same-tab exit off `/world`); external links keep VaultMarkdown's
  hardened `target="_blank" rel="noopener noreferrer nofollow"`. The
  card's one deep-link ("open the full Library ↗") opens a NEW tab — the
  world never navigates away.

## Data routes (all GET-only, auth-gated, READ-ONLY)

| Route | Serves | Source |
|---|---|---|
| `GET /api/world/library/browse?path=` | directory listing | `lib/vault.ts listDir` (confined) |
| `GET /api/world/library/note?path=` | one note: frontmatter + wikilink-rewritten markdown | `lib/vault.ts readNote` + the exact `/library` reader `rewriteWikilinks` pipeline (hrefs → `/library/…`) |
| `GET /api/world/library/search?q=&limit=` | search hits | server-side adapter over the Library search contract (below) |

* World ratchets #2/#7 pin all three: GET-only exports,
  `cabinet_session` + 401 gate (belt-and-braces under the edge middleware).
* Browse/note read EXCLUSIVELY through the confined resolvers in
  `lib/vault.ts` (realpath-under-root; NUL/absolute/`../`/symlink escape
  all deny). Any denial → a generic 404 **byte-identical** to a genuine
  miss (no existence oracle; pinned in `world-library-routes.test.ts`).
* No DB imports anywhere on this surface — the RETIRED
  `library_records`/`library_spaces` tables stay untouched.

## The search seam (lane-2 contract)

`src/lib/world/library-panel.ts` is the ONE module that encodes the
Library-search contract (the Library-search runbook of 2026-07-17,
"Querying the Library programmatically" — lands with the search lane):

* `GET /api/library/search?q=…&limit=…` → `{ results, degraded }` over the
  `cabinet_memory` store; hits `{snippet, source_type, source_id, score,
  when_at, libraryPath?}`; `429` = rate-limited.
* The world adapter forwards the caller's OWN session cookie (same-origin
  auth passthrough — no credential of its own), carries the query as
  search-param DATA (the search route binds it as a pg parameter), NEVER
  logs it, and never relays upstream error bodies.
* Honest degradation: search backend unreachable → `available: false` and
  the card says so (browse/read stay independent); upstream 429 →
  `rateLimited: true`; lane-2 `degraded: true` (lexical-only arm) is
  surfaced as a chip on the results.
* `normalizeLane2Response` is defensive: every field type-checked, lengths
  capped (25 hits / 200-char titles / 500-char snippets), and only plain
  vault-relative `libraryPath`s survive (`safeRelPath`) — the note route
  re-confines on open regardless.

## Rendering safety

Every byte of vault/search content renders as React text nodes or through
the existing sanitizing `VaultMarkdown` pipeline (react-markdown +
rehype-sanitize, no rehype-raw). The card issues plain single-argument GET
fetches only, imports no server actions, and adds no HTML-injection API —
`library-card.test.ts` pins each property plus renderToStaticMarkup XSS
negative controls (hostile titles/snippets/note bodies stay escaped text
at every typewriter-reveal step).

## Aesthetic harness (runs 2026-07-17)

* Mechanical gates: **PASS** (exit 0, zero errors) on the world render
  with the card open — palette foreign mass 0.86% (limit 5%), all label
  boxes sanctioned chrome; map gates skipped-with-info (no map change in
  this lane). A storm+dusk control frame trips the palette gate at 14.7%
  with the card OPEN vs **16.0% with the card closed** — the foreign mass
  is entirely weather/lighting environment; the card (sanctioned chrome,
  ui-rects-excluded) lowers it.
* Calibrated vision judge — three independent runs, consistent:
  * build run `jr-20260717-133407-5a21`: VALID (calibration 55/55 =
    1.000, floor 0.90); sun frame vs-negatives 5/5, vs-positives 2/11 →
    **iterate**.
  * review run `jr-20260717-164412-fbd8` (fresh seed): VALID (55/55);
    sun frame 5/5 · 0/11, storm frame 5/5 · 0/11 → **iterate**.
  * fix-pass run `jr-20260717-170138-09f6` (fresh seed, post-rebase
    tree; renders pixel-identical — the fixes touch no visual): VALID
    (55/55); sun frame 5/5 · 0/11, storm frame 5/5 · 0/11 → **iterate**.
  * Every why-line across all runs cites world-baseline factors
    (hamlet-era meadow patchwork repetition, the staged library worksite
    marker, storm dither) — none cites the card. The path back above the
    promote bar is the residuals below (library art via the asset forge +
    ground-variation/density pass), then re-judge; fix composition, never
    thresholds.

## Not in this lane (residuals)

* **Proper library building art** (STAGED_VOCAB_ELEMENTS) — the honest
  worksite marker stands until the asset forge lands library art; the
  judged frame re-runs then (the expected path back above the promote
  bar).
* **Richer in-place interior** — the roof-cutaway interior for the library
  (bookshelf truth-room furniture per spec §5.2) stays with the cutaway
  interior program; the card is the reading surface either way.
* **Officer/live-verb integration** (e.g. an officer figure "at the
  shelves" while a search runs) — needs the life-grammar lane.
* **Canonicalized `relPath` echo** — `lib/vault readNote` echoes the
  caller's own inside-root dotted path verbatim (e.g.
  `notes/../../<rootdir>/x.md` resolves fine — true escapes still 404 —
  but echoes un-normalized into the card's path strip). Byte-parity with
  the `/library` surface today; the nicety is an upstream `lib/vault`
  change (return the root-relative canonical path) so both surfaces move
  together.

Tests: `cd cabinet/dashboard && npm test && npm run typecheck` — the
world-library suites are `src/lib/world/library-panel.test.ts`,
`src/app/api/world/library/world-library-routes.test.ts`,
`src/components/world/library-card.test.ts`.
