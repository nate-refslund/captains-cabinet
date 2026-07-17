# Review — vault-browser cp1 (2026-07-17)

Change: a READ-ONLY dashboard view at `/vault` that browses the cabinet's ORG
vault (`vault/` markdown corpus) — directory listings + sanitized note render +
internal-only wikilinks. Batch is >300 lines (FW-019), so this artifact rides
the commit. ~1820 non-lockfile lines; the rest is `package-lock.json` for three
new local-transform deps.

## Files

New:
- `cabinet/dashboard/src/lib/vault.ts` — root resolution (mirrors
  `framework/env.py org_vault_dir()`), realpath-under-root confinement,
  `listDir`/`readNote`/basename-index. No DB, no writes.
- `cabinet/dashboard/src/lib/vault-wikilinks.ts` — pure parsers COPIED from
  `lib/wikilinks.ts` (not imported — that file imports `./db`) + internal-only
  wikilink rewrite.
- `cabinet/dashboard/src/components/vault/VaultMarkdown.tsx` — react-markdown +
  remark-gfm + rehype-sanitize renderer (no `dangerouslySetInnerHTML`, no
  `rehype-raw`).
- `cabinet/dashboard/src/app/(authenticated)/vault/[[...path]]/page.tsx` —
  catch-all server component (empty→root, dir→listing, file→note).
- 4 test files (`vault.test.ts`, `vault-wikilinks.test.ts`,
  `vault-markdown.test.tsx`, `vault-route.test.ts`).
- `docs/runbooks/vault-browser-2026-07-17.md`.

Edited (additive):
- `src/lib/nav-config.ts` (+ test) — `Vault` in `ADVANCED_NAV` only.
- `src/app/(authenticated)/library/page.tsx` (+ `library-route.test.ts`) — the
  retirement notice links onward to `/vault`.
- `src/app/globals.css` — `.vault-prose` styles.
- `src/middleware.test.ts` — `/vault` (and `/api/vault/*`) gating assertions.
- `package.json` / `package-lock.json` — react-markdown@10.1.0,
  remark-gfm@4.0.1, rehype-sanitize@6.0.0.

## Security review (Corridor-gated; all NON-NEGOTIABLES met)

1. **ORG vault, never the personal vault.** `vaultRoot()` mirrors
   `org_vault_dir()` and deliberately does NOT read the `vault_dir` key (on
   this box `~/obsidian/screenpipe-brain`, the captain's private brain). Test:
   a fixture `platform.yml` carrying ONLY `vault_dir` resolves to `<repo>/vault`
   and never the personal path.
2. **Path confinement.** `resolveInVault()` rejects NUL + absolute inputs,
   `path.resolve`-normalizes `..`, then `realpathSync` + prefix-asserts under
   the realpath'd root. Negative controls (all deny): `../../etc/passwd`,
   `/etc/passwd`, mid-path `decisions/../../../x`, NUL, and — the star — a
   dir symlink AND a `.md`-named symlink whose targets escape the vault.
   Listings `lstat` and never follow symlinks; the escaping symlinks are
   excluded. Deny → 404 (never 403 — no existence leak).
3. **Safe markdown.** react-markdown (React tree, no `dangerouslySetInnerHTML`);
   `rehype-raw` intentionally absent so raw `<script>/<iframe>/on*=` stay literal
   text; rehype-sanitize (defaultSchema, `<img>` dropped to avoid external image
   fetch) + default `urlTransform` strip `javascript:/data:/vbscript:`. Negative
   controls verify no `<script>/<img>/<iframe>`, no `on*` attribute, no dangerous
   href in output.
4. **Wikilinks internal-only.** Resolved → `/vault/...` internal link (relpath
   re-confined); unresolved → inert styled text (no create affordance);
   hostile/external targets → never an escaping or external href. `vaultHref`
   percent-encodes segments incl. parens (a `)` would else break the markdown
   link).
5. **Read-only, DB-free, auth-gated.** Zero mutation endpoints; pure server
   components, zero API routes. No `@/lib/db`/`pg`/`query()` in the vault graph
   (parsers copied, not imported). Route under `(authenticated)` → edge
   middleware `cabinet_session` gate; `/vault` + `/api/vault/*` proven to 307
   `/login` unauthenticated.

## Verification

- `npm test` — 106 files, 1841 tests pass (62 new vault tests; nav-config +
  library-route pins updated and green).
- `npm run typecheck` (tsc --noEmit) — exit 0.
- `cabinet/scripts/check-layer-separation.sh` — 0 new violations.
- `test_library_retirement_ratchet.py` (python3.12) — 9 passed, 1 state-aware
  skip (the vault reader adds no DB/vector path; ratchet stays green).
- No dashboard eslint config/script present → no lint step.

## Notes / residuals

- MVP serves no binary assets (images render broken); backlinks/graph/hovercard/
  full-text search + Tailscale phone exposure are Phase-2.
- Wikilink basename ambiguity resolves deterministically (shortest path, then
  alpha); basename index is a bounded (depth 8, 20k-file) walk with a 10s TTL
  cache.

## Integration deltas (landing pass, 2026-07-17)

Mechanics applied by the integrator on top of the reviewed diff — no logic
changes to the reviewed modules:

1. This artifact renamed `vault-browser-cp1.md` → `feat-vault-browse-cp1.md`
   (FW-019 matches review filenames on the branch slug `feat-vault-browse`).
2. `cabinet/scripts/tests/test_vault_rename_ratchet.py` — three ALLOWED
   entries declared (vault.ts / vault.test.ts / the runbook): the TS mirror
   deliberately carries org_vault_dir()'s legacy `CABINET_PRODUCT_BRAIN_DIR` /
   `product_brain_dir` / `<repo>/product-brain` arms, and the vault-rename
   ratchet (landed in the parallel vault-consolidation wave, after this lane
   was reviewed) reds any undeclared `product[-_]brain` token. Same seam
   class as the pre-declared `framework/env.py` entry — drop them together.
3. Runbook prose: two docs-track-code-sweep tokenizer artifacts fixed
   (`[/vault/...]` → `/vault/…`; the `(authenticated)`-split test path
   reworded) — the sweep's path tokenizer read them as dead repo paths.
