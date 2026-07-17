# Library search — dashboard + programmatic contract (2026-07-17)

Captain-ratified: "query the library from UI/world". This shipped the org's
ONE search engine — the cabinet_memory hybrid search that already powers
`memory_search` (cabinet/scripts/lib/memory.sh) — onto the dashboard, not a
second engine.

## What shipped

| Surface | Change |
|---|---|
| `cabinet/dashboard/src/lib/memory-search.ts` | Server-side mirror of `memory_search`'s hybrid CTE (vector candidates via HNSW + lexical `content_tsv` + 90-day recency blend, `superseded_by` fence, `cabinet_id` tenant fence, vec `min_score` floor 0.45) and of the lexical-only degrade arm. Query embedding is computed server-side via the EMBED-SEAM (`EMBED_PROVIDER`/`EMBED_MODEL`/`EMBED_DIMS`, Voyage default) with an 8s timeout, and the embed input is built BYTE-IDENTICAL to memory.sh's wire text (`echo \| tr '\n' ' ' \| cut -c1-32000` — newlines flattened, one trailing space, then the 32000-char cut; review fix 2026-07-17 — the bare string shifted cosine similarity ~0.06, enough to cross the vec floor and blank on-topic hits the shell engine returns). ANY embed failure degrades to the lexical arm — never a blank result set, never an error page (memory.sh doctrine). The Voyage cross-encoder rerank stage is deliberately NOT mirrored (residual below). |
| `GET /api/library/search` | The search endpoint (route handler beside the legacy POST). Read-only, behind the dashboard session-cookie middleware, per-session rate-limited. |
| `cabinet/dashboard/src/components/library/LibrarySearch.tsx` | Debounced client search box: escaped/highlighted snippets (React text nodes only — no raw HTML), vault hits link into the Library reader at `/library/<path>` (LINK-TARGET NOTE below), other hits carry a source badge ("decision digest", "research brief", "belief", …). Mounted on the `/library` root; the consumer card's `LibrarySearchBox` is now a thin wrapper around it. |
| `cabinet/dashboard/src/lib/search-rate-limit.ts` | In-memory sliding window (30 req / 60s per session; hashed cookie key). Courtesy brake, not a security boundary — and per-process (the single-process Next server); a multi-instance deploy would need a shared store. |
| `cabinet/dashboard/src/lib/db.ts` | (Review fix 2026-07-17) The shared pool no longer FORCES TLS: `resolvePoolSsl()` mirrors psql's decision from the connection string — explicit `sslmode=disable` → plaintext; `require`/`verify-*` → TLS (legacy `rejectUnauthorized:false` posture, unchanged for Neon); otherwise loopback hosts → plaintext, remote hosts → TLS. Before this, a local no-SSL postgres (`…@localhost:5432/cabinet`) failed every query with "The server does not support SSL connections" → every non-empty search 500ed on such a box. |

Security posture (Corridor-gated, pinned by
`src/lib/memory-search.test.ts`, `src/app/api/library/search/route.test.ts`,
`src/components/library/library-search.test.tsx`, `src/middleware.test.ts`):

* Query text is UNTRUSTED — it reaches Postgres only as a pg bind parameter;
  the SQL program text is a static constant (tests assert byte-identity).
* Source fence: only org-knowledge `source_type` classes are queryable
  (bound unconditionally — no bypass arm, no client-controllable type
  parameter). Conversational/private classes (`telegram_dm`,
  `session_memory`, `captain_decision`, `reflection`, …) are structurally
  unreachable from this surface.
* Read-only: single SELECTs against `cabinet_memory`. The RETIRED
  `library_records`/`library_spaces` tables are untouched (the legacy POST
  arm still reads them for CommandPalette — residual below).
* Keys (`VOYAGE_API_KEY`, `NEON_CONNECTION_STRING`) stay server-side env;
  never logged, never in responses. The query text leaves the box only in
  the TLS body of the embedding call (exactly as memory.sh).
* Snippets render as escaped React text with `<mark>` highlighting — no
  `dangerouslySetInnerHTML`. Vault links are segment-encoded and the vault
  browser re-confines every path server-side (`lib/vault.ts
  resolveInVault`) — search performs no filesystem access at all.

## Querying the Library programmatically

This is the contract the world librarian (and any in-repo agent surface)
calls. It is the SAME auth surface as the rest of the dashboard: send the
`cabinet_session` cookie (HMAC session minted by `/login`); unauthenticated
calls 307-redirect to `/login`.

```
GET /api/library/search?q=<text>&limit=<1..20>
```

* `q` — the search text (required; empty/whitespace returns an empty result
  without touching the store). Treated as data end-to-end; trimmed, then
  clamped to 2048 chars before it reaches the engine (defense-in-depth for
  the tsquery bind — the embed arm cuts at 32000 chars, memory.sh parity).
* `limit` — max hits, clamped to 1..20 (default 20).

Response `200 application/json`:

```json
{
  "results": [
    {
      "snippet": "whitespace-collapsed head of the note/summary (plain text)",
      "source_type": "product_brain",
      "source_id": "vault/architecture.md",
      "score": 0.91,
      "when_at": "2026-07-01 10:00",
      "libraryPath": "architecture.md"
    }
  ],
  "degraded": false
}
```

* `results` — ranked hits (blended score, higher = better), capped at
  `limit`.
* `source_type` — one of the org-knowledge classes:
  `product_brain` (vault notes), `framework_doc`, `framework_file`,
  `captain_law_summary` (decision digests), `research_brief`,
  `experience_record`, `library_record` (retired-Library mirror rows),
  `product_spec`, `tech_radar`, `consolidated_belief` (officer
  retro/reflection distillates — the individual-reflection and
  cross-officer-retro skills queue these via `memory_queue_embed`).
  Nothing else can appear.
* `libraryPath` — present ONLY when the hit maps to a vault note
  (`product_brain` rows); it is vault-relative and renders at
  `/library/<libraryPath>` in the Library reader (LINK-TARGET NOTE
  below). Hits without it (digests, briefs, beliefs, experience records)
  are content-only — show the snippet + badge.
* `degraded` — `true` when the semantic arm was unavailable (no embed key /
  provider outage) and ranking was lexical-only. Results are still honest;
  callers MAY surface a hint, MUST NOT retry-loop on it.
* `429 {"error":"Rate limited"}` — per-session sliding window (30/min);
  carries `Retry-After: 60` (the full window — an upper bound; budget frees
  as the oldest request ages out). Back off.
* `500 {"error":"Search failed"}` — generic by design; nothing internal is
  echoed.

Curl smoke (from the dashboard host, after logging in once to mint the
cookie):

```bash
curl -s --cookie "cabinet_session=$SESSION" \
  'http://localhost:3100/api/library/search?q=killswitch+doctrine&limit=5' | jq .
```

## Environment

Uses what the dashboard container already receives from `cabinet/.env`
(`env_file` in cabinet/docker-compose.yml): `NEON_CONNECTION_STRING`
(store), `VOYAGE_API_KEY` + optional `EMBED_PROVIDER`/`EMBED_MODEL`/
`EMBED_DIMS` (seam), optional `CABINET_ID` (tenant fence, memory.sh
parity), optional `CABINET_MEMORY_MIN_SCORE` (vec floor). A keyless box
serves lexical-only search (`degraded: true`) — same behavior as a keyless
`memory_search`.

Store SSL: `db.ts` resolves the TLS posture from the connection string
(see the What-shipped table) — a local plaintext postgres now works like it
does under psql, a Neon URL keeps TLS. Two caveats:

* **Container networking**: inside the dashboard CONTAINER,
  `localhost:5432` is the container itself. A box whose store runs on the
  host must point the container's `NEON_CONNECTION_STRING` at a
  container-reachable host (e.g. `host.docker.internal`) or run the
  dashboard outside compose; the degrade seam covers EMBED failures only —
  a store the pool cannot reach is a genuine 500 by design.
* **Smoke before declaring live**: run the curl smoke above once on the
  target box; "hybrid is configured" claims require one real 200 with
  hits, not env inspection. For engine-level parity (no cookie needed),
  the opt-in live smoke does the same below the route:
  `LIBRARY_SEARCH_LIVE_SMOKE=1 NEON_CONNECTION_STRING=… VOYAGE_API_KEY=…
  npx vitest run src/lib/memory-search.live.test.ts` — skipped everywhere
  unless explicitly opted in; compare hit overlap with shell
  `memory_search` on the same query.

## LINK-TARGET NOTE (landed 2026-07-17: /library IS the reader)

Vault-note hits link to `/library/<path>`. The Library-identity lane
(LIB-IDENT) landed in the same integration commit as this search lane and
re-homed the vault browser at `/library` (Captain naming ruling: the vault
is where it's kept, the Library is where you read); `/vault/<path>` lives
on as a redirect alias into `/library/<path>`, so stale `/vault` links
still resolve. The flip this note originally prescribed was executed at
integration: `VAULT_NOTE_BASE` in `LibrarySearch.tsx` is `'/library'` and
the pins in `library-search.test.tsx` assert `/library/...` hrefs. The
integrator also verified the `/library` root page (the LIB-IDENT
catch-all) mounts `<LibrarySearch />` — the search card moved there when
the retirement-notice page this lane originally decorated was deleted.

## Residuals (recorded 2026-07-17)

* **Rerank parity**: memory.sh's R2 Voyage cross-encoder rerank is not
  mirrored (one extra provider round-trip per keystroke). If the world
  librarian needs top-k parity with shell `memory_search`, add the rerank
  stage behind the same fail-soft seam.
* **CommandPalette**: still calls the legacy `POST /api/library/search`
  (retired `library_records` ILIKE). Refit it to the GET contract when the
  Library identity work lands, then retire the POST arm.
* **RANKING-BLOCK drift**: the blended weights here must track memory.sh's
  RANKING-BLOCK; `memory-search.test.ts` pins the constants so a one-sided
  change goes red, but a deliberate re-tune must update BOTH (and re-stamp
  the retrieval eval per memory.sh's marker comment).
* **Vec-floor UX (engine-inherited, do NOT tune unilaterally)**: realistic
  short queries can score below the 0.45 vec floor against this store, so
  the hybrid arm can honestly return 0 hits where the lexical arm would
  find rows — shell `memory_search` behaves identically (parity honest,
  UX rough). Any change (e.g. lexical fallback on 0 hybrid hits, floor
  tweak) is RANKING-BLOCK territory: both engines together + a
  `retrieval-eval-nightly.sh --stamp` re-stamp. A non-ranking alternative
  is a UI affordance hinting that `CABINET_MEMORY_MIN_SCORE` governs the
  floor.
* **TLS verification**: the TLS arm keeps the pre-existing
  `rejectUnauthorized: false` posture (Library Sprint A) — encrypted but
  not chain-verified. Hardening to verified TLS for `verify-*`/Neon hosts
  is a deliberate, estate-wide change (every DB-backed dashboard page
  shares this pool), not this lane's call.
* ~~**`consolidated_belief`**: no writer produces that source_type~~ —
  WRONG at this tip and corrected 2026-07-17: the individual-reflection +
  cross-officer-retro skills DO queue `consolidated_belief` rows
  (terminal step enforced by `test_memory_distill.py`), so the class is
  now IN `ORG_KNOWLEDGE_SOURCE_TYPES` (badge "belief"). The live store had
  0 such rows when this shipped; the first officer retro's beliefs will be
  searchable from day one.
