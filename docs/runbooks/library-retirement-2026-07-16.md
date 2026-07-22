# Library retirement — runbook (2026-07-16)

Captain-ratified 2026-07-16 (recorded in the captain-decisions runtime
ledger; closes memory-study Q4/C7). This is the operator-facing record of
WHY the Library was retired, WHERE the data went, HOW to find it now, and
what remains dormant.

## Why

The Library maintained a **second vector store** (`library_records.embedding`,
voyage-4-large) parallel to `cabinet_memory`. Every record write embedded
twice — once into the record row, once via the cabinet_memory mirror queue —
for a surface whose recall traffic had converged on `memory_search`. The
memory study (Q4/C7) found the record-vector store added cost and drift risk
without adding recall. Retirement makes the Library **write-thin**: records
remain storable, but only the cabinet_memory mirror is maintained.

## What changed (code)

| Surface | Change |
|---|---|
| `cabinet/scripts/lib/library.sh` | `library_create_record` / `library_update_record` no longer call `memory_get_embedding` or write the `embedding` column (rows insert vector-free). The `memory_queue_embed` cabinet_memory mirror stays — search continuity path. `library_search` still ranks over **legacy** vectors where present, ILIKE fallback otherwise. |
| `cabinet/dashboard/src/lib/library.ts` | `getEmbedding` (Voyage) + direct-vector write removed from `createRecord`/`updateRecord`; `queueLibraryRecordInMemory` stays. `searchRecords` is keyword-only (ILIKE title). |
| `.mcp.json` + `.mcp.json.mac-native` | `library` MCP server **deregistered** (both layers lockstep). The server code stays at `cabinet/channels/library-mcp/` and runs standalone for archaeology. |
| `cabinet/mcp-scope.yml` (germline, schg) | **Git-side content lands on master** in the CG-29 danglers diff — `library` dropped from every officer/scaffold grant + `universal:` (tree file, not schg in a clone; the grants were dangling-but-harmless since an unregistered server grants nothing). The schg LIVE inode syncs at the Captain window via checkout-from-master (CG-29 gate_cmd). |
| Agent `tools:` grants | `mcp__library` removed from every **non-germline** agent frontmatter: `instance/agents/cos.md`, `presets/work/agents/{cos,cto,cpo,coo,cro}.md`, `presets/portfolio/agents/cos.md`, `presets/portfolio/agents/_lane-ceo.md.template` (ratcheted — resurrection-by-copy guard). The germline `.claude/settings.json` `permissions.allow` entry drops in the same CG-29 danglers diff (git side); the live inode syncs at the window (below). |
| `CLAUDE.md` + the egg CLAUDE template | "Systems each own one job" no longer routes Cabinet knowledge to the Library MCP: knowledge = the vault (`product-brain/`), recall = `memory_search` (ratcheted; the egg template becomes the public egg's `CLAUDE.md` at export). |
| Dashboard `/library` | Landing page is a read-only retirement notice; space/record/graph deep-links redirect to it. `/api/library/*` routes remain (records still storable; search is keyword-only). |
| `cabinet/scripts/retire-library-export.py` | NEW one-shot export (below). |

## Where the data went

1. **Vault archive** — run the one-shot export on the box that has DB access:

   ```bash
   DATABASE_URL="$NEON_CONNECTION_STRING" cabinet/scripts/retire-library-export.py
   ```

   * Writes one markdown note per `library_records` row (ALL rows, including
     superseded versions and soft-deletes — flagged in frontmatter) into
     `vault/library-archive/` if `vault/` exists, else
     `product-brain/library-archive/` (pre-vault-rename tree).
   * Foldered by space: `<space-slug>-s<space_id>/lib-<id>-<title-slug>.md`.
   * Frontmatter carries `title`, `created`, `updated`,
     `provenance: "library_record:<id>"`, `space`, `space_id`, `version`,
     `status`, `labels`, `created_by_officer`, `superseded`, `deleted`, and
     `schema_data` (when non-empty). Body = `content_markdown` **verbatim**
     (untrusted data stays data).
   * **Idempotent**: deterministic filenames, full overwrite, stale filename
     variants of a record id pruned. Re-run any time to refresh.
   * **Read-only**: single fixed SELECT under
     `default_transaction_read_only=on`; refuses to run without
     `DATABASE_URL` (loud skip, exit 0). Requires the 037 `status` column
     (present on the product Neon).
   * **Runtime-only — never committed.** Both candidate archive roots are
     gitignored (`product-brain/library-archive/`, `vault/library-archive/`;
     ratcheted): `product-brain/` is tracked and ships in the public egg,
     and DB-derived records must never ride a commit into it. The export
     also stays out of `git status` noise on the live multi-writer tree.
   * **Indexing is an operator step, not automatic.** The post-file-write
     memory hook only fires on Claude-session tool writes (not this
     script's), and memory-reconcile's scan roots don't include the
     archive. After (re-)running the export, index it:
     `cabinet/scripts/backfill-memory.sh --files-only` (idempotent upsert;
     its file scan covers the whole product-brain corpus — no new embed
     code was added). Records mirrored to cabinet_memory since the mirror
     existed are already searchable without this; the backfill catches any
     pre-mirror rows.

2. **cabinet_memory** — every record create/update was (and still is)
   mirrored via the Redis embed queue (`source_type=library_record`,
   `source_id=lib-<record_id>`), so `memory_search` finds Library content
   cross-system. This is the primary recall path going forward.

## How to find a record now

* Semantic: `memory_search "<query>"` (memory.sh) — Library rows carry
  `source_type=library_record`.
* Dashboard/world: the Library search box on `/library` (and the consumer
  card) hits `GET /api/library/search` — the same cabinet_memory engine,
  org-knowledge classes only. Contract:
  `docs/runbooks/library-search-2026-07-17.md`.
* Exact: grep the vault archive frontmatter for
  `provenance: "library_record:<id>"`.
* SQL archaeology: the tables are still there (below) — plain read-only
  `psql` works.

## What remains dormant (deliberately NOT dropped)

* `library_records` (with `embedding`, `embedded_at` columns),
  `library_spaces`, `library_record_links`, `library_record_sections`.
* The 044 re-embed-on-edit trigger (`library_records_clear_embedding_trg`)
  and `idx_lr_pending_embed` — inert now that nothing writes vectors; edits
  simply null legacy vectors, which matches the retirement semantics.
* **No destructive DDL shipped with this change.**

### Follow-up (future work row)

* [ ] Eventual DDL drop — after a soak proving nothing reads
  `library_records.embedding`: drop the 044 trigger + `embedded_at` +
  `embedding` + hnsw index, then (much later, Captain call) the tables
  themselves. Ship as its own reviewed migration; never bundle with app
  changes.
* [ ] Germline live-inode sync — ledger row **CG-29** (filed). The git-side
  cleanup of all three dangling germline surfaces lands on master in the
  CG-29 danglers diff: (1) `library` dropped from `cabinet/mcp-scope.yml`
  grants + `universal:`; (2) the `"mcp__library"` entry dropped from
  `.claude/settings.json` `permissions.allow`; (3) the stale
  "notion/linear/neon/library" merge-comment in
  `cabinet/scripts/start-officer-mac.sh` replaced (comment-only, zero
  behavior change). ONE Captain sudo window (schg unlock, relock same day)
  then SYNCS the live inodes to master via `git checkout origin/master --`
  the three files — NOT an in-window patch/commit (the CG-27/CG-31
  checkout-from-master precedent). Durable deliverables, in the private
  source repo: the germline library-retirement addendum (ceremony note,
  master-first, 2026-07-16) + the germline library-retirement patch,
  2026-07-16 (kept as
  the comment-only proof; the ratchet skips it once the mark lands). The
  `library` entry in `cabinet/scripts/lib/officer-env.py`'s per-server env
  map (germline too) is likewise dangling-but-harmless (the server never
  boots) — drop it whenever that map is next touched.

## Ratchet

`cabinet/scripts/tests/test_library_retirement_ratchet.py` greps the tree:
no new record-vector write path (no `memory_get_embedding` in library.sh
create/update, no Voyage/`getEmbedding` in dashboard `library.ts`, no
`embedding` column in `INSERT INTO library_records` outside the dormant SQL
DDL), the MCP registration stays retired, `CLAUDE.md`/`CLAUDE-egg.md` keep
routing knowledge to the vault + `memory_search`, no agent frontmatter
grants `mcp__library`, the two germline grant surfaces stay library-free
(`cabinet/mcp-scope.yml` grant lists + `universal:` and
`.claude/settings.json` `permissions.allow` — the CG-29 danglers landed on
master), the archive dirs stay gitignored, and the staged ceremony patch
stays appliable until its mark lands (then skips). The functional suites
(`cabinet/scripts/lib/tests/test_library_sh_retirement.py`, dashboard
`library.retirement.test.ts`) run the write paths with ARMED tripwires — a
dummy `VOYAGE_API_KEY` plus stubbed curl/fetch — so a resurrected embed
call fails loudly instead of no-opping on a missing key. If you need
vectors on Library-shaped data, the answer is cabinet_memory, not a
resurrected second store.

## Follow-up — the READER returned (2026-07-17)

Captain naming ruling, 2026-07-17: *"keep the name Library — it fits the
world; the vault is where it's kept, the Library is where you read."* One day
after this retirement, `/library` became the **read-only vault reader** (the
phase-1 vault browser moved there from `/vault`, which now redirects), plus a
filesystem-backed wikilink graph at `/library/graph` and per-note backlinks.
Nothing above is reversed: the editable STORE stays retired, the route tree
stays **zero-DB** (pinned by the superseded `library-route.test.ts` contract),
and the dormant tables stay dormant. The full-page retirement notice became a
collapsible **History** note on the Library root. Details:
`docs/runbooks/vault-browser-2026-07-17.md`.
