# Review — world-library cp1 (2026-07-17)

Change: the Cabinet World harbor Library building opens the Library itself —
a world-native READ-ONLY card (browse / read / search over the org vault)
rendered as chrome OVER the live canvas. Lands the lane LIBRARY-P2-1 recorded
as HELD (its required verdict-bearing review is now on record: builder →
2 Fable lens reviews → fix pass → re-verify at the landing base d203c462,
all 8 findings closed). Batch is >300 lines (FW-019), so this artifact rides
the commit. 2045 insertions, 10 files, zero deletions outside one 17-line
additive wiring edit.

## Files

New:
- `cabinet/dashboard/src/app/api/world/library/browse/route.ts` — GET dir
  listing via `lib/vault.ts listDir` (confined).
- `cabinet/dashboard/src/app/api/world/library/note/route.ts` — GET one note
  (frontmatter + wikilink-rewritten markdown) via `lib/vault.ts readNote` +
  the exact `/library` `rewriteWikilinks` pipeline.
- `cabinet/dashboard/src/app/api/world/library/search/route.ts` — GET
  server-side adapter over the landed `GET /api/library/search`
  cabinet_memory contract.
- `cabinet/dashboard/src/lib/world/library-panel.ts` — the ONE module
  encoding the search contract + defensive `normalizeLane2Response`.
- `cabinet/dashboard/src/components/world/library-card.tsx` — the card UI
  (browse tree, note reader, query dialog with typewriter results).
- 3 test files: `world-library-routes.test.ts` (356 L),
  `library-card.test.ts` (242 L), `library-panel.test.ts` (246 L).
- `docs/runbooks/world-library-card-2026-07-17.md`.

Edited (additive, +17):
- `cabinet/dashboard/src/components/world/engine-client.tsx` — import, card
  state, primary-click open at close/mid LOD, Escape close, render.

## Security review (Corridor-gated; all properties test-pinned)

1. **Confinement parity with `/library`.** Browse/note read EXCLUSIVELY
   through the already-reviewed `lib/vault.ts` confined resolvers
   (realpath-under-root; NUL/absolute/`../`/symlink escape all deny). Any
   denial → generic 404 **byte-identical** to a genuine miss (no existence
   oracle) — pinned in `world-library-routes.test.ts`.
2. **Auth.** All three routes GET-only exports + `cabinet_session` cookie
   check with 401 (belt-and-braces under the edge middleware). World
   ratchets pin the export surface.
3. **Search adapter.** Forwards the caller's OWN session cookie only
   (same-origin passthrough, no credential of its own); the query travels
   as search-param DATA (upstream binds it as a pg parameter); never
   logged; upstream error bodies never relayed. `normalizeLane2Response`
   type-checks every field, caps 25 hits / 200-char titles / 500-char
   snippets; only plain vault-relative `libraryPath`s survive
   (`safeRelPath`) and the note route re-confines on open regardless.
4. **Rendering.** Every byte of vault/search content renders as React text
   nodes or through the existing sanitizing `VaultMarkdown`
   (react-markdown + rehype-sanitize; no rehype-raw, no
   `dangerouslySetInnerHTML`). XSS negative controls
   (renderToStaticMarkup on hostile titles/snippets/bodies, at every
   typewriter-reveal step) pinned in `library-card.test.ts`.
5. **World never navigates away.** In-note internal library hrefs open
   IN-CARD (capture phase, `overlayPathFromHref`); internal-shaped hrefs
   that do not map to a safe vault relpath are INERT
   (`isInternalLibraryHref`); external links keep hardened
   `target="_blank" rel="noopener noreferrer nofollow"`; the one
   deep-link opens `/library` in a NEW tab.
6. **No DB.** Zero DB imports on the surface; the retired
   `library_records`/`library_spaces` store stays retired.

## World doctrine

One continuous world: the card is chrome over the live canvas — camera,
canvas, logical tick untouched (test-pinned: canvas mount never gated on
the card; the card exports no navigation API). Far-LOD primary keeps the
navigate-fly law; secondary keeps the era×rung inspect card (Legend Law).
Escape closes via the shell handler.

## Aesthetic harness (recorded honestly)

- Mechanical gates: PASS 0 errors with the card open (foreign palette mass
  0.86% vs 5% limit; storm control frame 14.7% card-open vs 16.0%
  card-closed — the foreign mass is weather; the card, as sanctioned
  ui-rects chrome, LOWERS it). Re-reproduced at landing in this worktree:
  open-card ok 0 err/0 warn; nocard ok 0 err/1 warn (pre-existing baseline
  CLUSTER_FLAT_TEXTURE busy-CV 0.4064 vs 0.4101 fitted min).
- Calibrated vision judge: FOUR runs, all VALID (calibration 55/55 = 1.000
  vs 0.90 floor) — build jr-20260717-133407-5a21 (5/5 vs negatives, 2/11
  vs positives), review jr-20260717-164412-fbd8, fix-pass
  jr-20260717-170138-09f6, post-rebase re-verify jr-20260717-173013-6584
  (each 5/5 vs negatives, 0/11 vs positives) → verdict **ITERATE** (below
  the 0.5 promote bar). Every why-line cites world-BASELINE composition
  (hamlet-era meadow patchwork, the staged library worksite marker, storm
  dither) — none cites the card. Ship rationale: the card is chrome; the
  losses are baseline factors this lane never touched (fix pass changed no
  pixel). Path back above the promote bar = asset-forge library art +
  ground-variation pass, then re-judge. Composition fixes, never
  thresholds.

## Verification at landing (worktree off origin/master @d203c462)

- `npm ci` — 0 vulnerabilities.
- vitest — 120 files passed + 1 skipped; 2204 tests passed + 1 skipped.
- `tsc --noEmit` — clean.
- `docs-track-code-sweep.sh` — GREEN (files=51 findings=0).
- `check-layer-separation.sh` — new=0 (baseline=24 allowlist=18
  current=42).
- world + aesthetic pytest subset (python3.12) — 164 passed / 5 skipped.
- Ledger: WORLD-LIBRARY-1 appended (status=done) + plan-doc §47; A13 +
  id-uniqueness + ledger-status-parity GREEN pre (331) and post (332).

## Residuals (owned in the runbook)

Proper library building art (staged worksite marker until the asset forge
lands it — the expected re-judge trigger); roof-cutaway bookshelf interior
(cutaway program); officer-at-the-shelves live-verb (life-grammar lane);
canonicalized `relPath` echo (upstream `lib/vault` nicety; byte-parity
with `/library` today).
