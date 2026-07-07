# Org Memory — Day-1 Bring-up Runbook

Wave-1 org-memory chain (2026-07-07): how a fresh box goes from empty
Postgres to a living organizational memory — hybrid recall, nightly
reconcile, and a REPORT-ONLY self-improvement loop. Written for the next
deployment (clean Mac Mini) and as the ops reference for the hq MacBook
where this chain first shipped.

Conventions: env vars are referenced by NAME only — values live in
`cabinet/.env` (never in this file, never in plists, never echoed).
All commands run from `$CABINET_ROOT` (this repo's checkout).

---

## 0. Postgres substrate — the wave-1 discovery

**On this hq box, `NEON_CONNECTION_STRING` does NOT point at Neon.** It
points at a **LOCAL Homebrew PostgreSQL 17 (verified 17.10) with pgvector
0.8.3**. Everything in the memory chain (cabinet_memory, cabinet_research,
library, org_events pg slice) rides that one connection-string name, so the
chain is substrate-agnostic — but a clean Mini must provision ONE of:

- **Path A — local Postgres (what hq runs):**
  ```bash
  brew install postgresql@17 pgvector
  brew services start postgresql@17
  createdb cabinet   # or your preferred db name
  # then set NEON_CONNECTION_STRING in cabinet/.env to the local DSN
  psql "$NEON_CONNECTION_STRING" -c "CREATE EXTENSION IF NOT EXISTS vector;"
  ```
  Pros: zero external dependency, no egress, backups ride the 03:00 cabinet
  backup. Cons: the box is the blast radius — off-machine backup posture is
  a known open item.

- **Path B — hosted Postgres + pgvector (Neon or any pg ≥15):**
  create the project/database, enable the `vector` extension, put the DSN
  under the same `NEON_CONNECTION_STRING` name in `cabinet/.env`. Pros:
  survives the box; Cons: latency on the 2s recall budget (§3) and an
  external dependency in the officer hot path — measure before committing.

Either way the rest of this runbook is identical: **nothing else in the
chain knows which substrate is behind the name.**

Note on `org_events` in pg: `framework/events/emitter.py` writes the JSONL
ledger ALWAYS (default `~/Library/Application Support/cabinet/events/`,
override name `CABINET_EVENT_LOG_DIR`) and the org_runtime Store SQLite
mirror; it writes the pg `org_events` table **only when `DATABASE_URL` is
set** (a separate name from `NEON_CONNECTION_STRING`). Canonical pg schema:
`cabinet/sql/045-org-runtime-slice.sql`.

## 1. Bootstrap — apply the SQL list

`cabinet/scripts/cabinet-bootstrap.sh` applies the schema set during
onboarding — `framework/schemas-base.sql` + `presets/<preset>/schemas.sql`
plus **`schema_apply_list()` in the script itself (the single source of
truth; read it rather than a list here)**. As of the 2026-07-07 review fix
it carries, in dependency order: `cabinet_memory.sql`,
`cabinet-memory-content-tsv.sql` (migration), `cabinet_research.sql`,
`library.sql`, `037-library-phase-a.sql`,
`044-library-embedding-hardening.sql`, `contexts-neon-phase1.sql`,
`contexts-neon-phase2.sql`, `cabinet-id-neon-phase1.sql`,
`cabinet-id-neon-phase1b.sql`, `session-memories-context-slug.sql`,
`2026-04-17-spec-034-provisioning-schema.sql`, `038-officer-tasks.sql`,
`041-tasks-due-at.sql`, `039-linear-to-tasks-schema.sql`,
`045-org-runtime-slice.sql`. The only deliberate `cabinet/sql/` omissions
are the three LOCAL-postgres schemas (`cabinet-id-phase1*.sql`,
`contexts-cabinet-phase1.sql`) — anything else unlisted makes the
warn-only self-check fire, and that WARN is a real alarm.

Day-1 memory chain REQUIRES two of these in particular — verify they are
applied (manually via `psql "$NEON_CONNECTION_STRING" -f <file>` if your
bootstrap revision predates wave 1):

- **`cabinet/sql/cabinet_memory.sql`** — the memory store, including the
  **`content_tsv` generated column** (the lexical 0.25 leg of hybrid
  search; without it `search-memory.sh` degrades to vector-only).
- **`cabinet/sql/cabinet_research.sql`** — the research vector store
  (embed/search/supersede scripts in `cabinet/scripts/`).

Smoke: `psql "$NEON_CONNECTION_STRING" -tAc "select to_regclass('cabinet_memory'), to_regclass('cabinet_research');"`

## 2. Instance generation — bind the org shapes

`cabinet/scripts/generate-instance.py` (driven by the `cabinet-init` skill
interview) emits the instance layer:

- **`instance/config/sources.yml`** — on an org-flavor box it binds
  `framework.sources.org:OrgSource` (framework/sources/org.py), giving the
  officers real query-driven recall with no personal-sensing estate.
  **On THIS hq box the live binding stays `ScreenpipeSource` — do not flip
  it**; OrgSource is registered but not bound here.
- **`instance/config/platform.yml`** — gains the `product_brain_dir:` key,
  READ at runtime by `framework.env.product_brain_dir()` (resolution:
  `CABINET_PRODUCT_BRAIN_DIR` env override → this key, relative values
  against `CABINET_ROOT`, existence-gated → in-repo `<root>/product-brain`
  → fail-closed empty). Relocating the corpus = editing this key (or the
  env override). The `product-brain/` directory is the per-product
  knowledge corpus the gather step folds into its corpus section.

## 3. Hooks — capture + recall

- **Capture:** `cabinet/scripts/hooks/post-file-write-memory.sh` watches
  knowledge writes (including `product-brain/` and `shared/interfaces/`)
  and queue-embeds them onto Redis `cabinet:memory:embed_queue` for the
  memory-worker. Best-effort exit-0 by design — the nightly reconcile
  (§4) is the repair half.
- **Recall:** `cabinet/scripts/hooks/pre-captain-dm.sh` injects memory
  recall before Captain-facing DMs under a **2s hard budget** (`timeout`/
  `gtimeout`); a budget loss is counted on Redis
  `cabinet:memory:recall_drops` — visible, never silent.
- **Captain-law append path:** the three captain ledgers
  (`captain-decisions.md`, `captain-patterns.md`, `captain-intents.md`)
  and `memory/skills/**` are germline/hook-write-protected; the ONLY write
  path is `cabinet/scripts/append-interface.sh <ledger>` with the entry on
  stdin (provenance-stamped, append-only). captain-decisions H2 ingestion
  feeds `cabinet_memory` with `trust=captain` rows.

## 4. Services — the standing organs (`cabinet/services.yml`)

| Service | Cadence | Role in the chain |
|---|---|---|
| `memory-worker` | keepalive daemon | drains `cabinet:memory:embed_queue` → embeds → upserts `cabinet_memory` (needs `NEON_CONNECTION_STRING` + `VOYAGE_API_KEY` names from `cabinet/.env`) |
| `memory-reconcile` | nightly 03:30 (after the 03:00 backup, before the 03:45 apoptosis sweep) | re-hashes the watch list, queue-embeds hook-missed / hash-drifted files; summary line in the service log (generated-plist convention `~/Library/Logs/cabinet/memory-reconcile.log`; hq's pre-fix 2026-07-07 install writes `~/.cabinet/logs/memory-reconcile.log`) — installed via the §4 generate-plists pattern like self-improvement-loop |
| `falsifier-daily` | daily 08:05 | daily line carries the per-source_type **memory-ingestion liveness** object + ALERT lines (the observability half over the best-effort hooks) |
| `self-improvement-loop` | every 6h, **`REPORT_ONLY: "1"`** | see §6 — propose+validate runs, apply/promote/graduate withheld until first weekly review |

Install/reload pattern for manifest rows (used for self-improvement-loop,
2026-07-07): `python3.12 cabinet/scripts/generate-plists.py` → cp
`cabinet/launchd/generated/<label>.plist` → `~/Library/LaunchAgents/` →
`launchctl bootout gui/$UID/<label>` → `launchctl bootstrap gui/$UID
~/Library/LaunchAgents/<label>.plist`. Rendering never installs; installing
is the deliberate step.

## 5. Verification checklist (run after bring-up, re-run after changes)

1. **Hybrid search smoke:** `bash cabinet/scripts/search-memory.sh "<known topic>"`
   — expect hits with `[trust:...]` labels; blend = 0.60 vector + 0.25
   lexical (`content_tsv`) + 0.15 recency, floor 0.45; `--as-of <ts>` is a
   fail-closed content-time fence (rows without content-time are excluded,
   never mtime-guessed).
2. **Golden eval:** `memory/golden-evals/eval-022-memory-recall-liveness.md`
   passes.
3. **Falsifier liveness:** today's falsifier line shows the
   `memory_ingestion` per-source_type object populated (`{}` = nothing
   ingested, `null` = UNMEASURABLE → ALERT).
4. **Recall budget:** `redis-cli GET cabinet:memory:recall_drops` — a
   slowly-moving (ideally flat) counter; a fast climb means the 2s budget
   is losing races (check pg substrate latency, §0).
5. **Backfill (first bring-up only):** `bash cabinet/scripts/backfill-memory.sh`
   to seed the corpus; `bash cabinet/scripts/seed-library.sh` for the
   Library starter spaces (work preset seeded on hq).
6. **Reconcile proof:** next morning, one summary line in the
   memory-reconcile service log (path per the §4 table) with plausible
   checked/queued/current counts.
7. **Self-improvement soak proof:** see §6 verification block.

## 6. Self-improvement loop — REPORT_ONLY soak (audit-ratified)

The R8 growth engine (`framework.learning.self_improvement_loop`, wrapper
`cabinet/cron/self-improvement-loop.sh`) chains propose → validate →
**auto-apply** with no Captain wait. The ratified plan requires an
observe-first soak: the fleet row ships `env: { REPORT_ONLY: "1" }`.

**Semantics under `REPORT_ONLY=1`** (wrapper maps the env onto the
driver's `--report-only` flag; `1|true|yes|on`, case-insensitive):

- Propose + the validation gate (scenario evals + golden shells) **run
  for real**; a RED evaluated gate still exits 3 with the FATAL stderr
  marker (pages — a failing safety net is a pathology regardless of soak).
- Every mutation is **withheld**: no `adapt_role`, no proposal YAMLs, no
  hat graduations, no draft-skill files, no `gate.ratify` packs,
  capability gaps route dry.
- The ledger still records the pass: `self_improvement_loop_started` /
  `_completed` carry `report_only: true` + a `would_apply` payload
  (proposal ids, hat candidates, skill-draft count) — in the JSONL ledger
  and the org_runtime Store mirror (pg `org_events` additionally requires
  `DATABASE_URL`, §0).
- The service log (`~/Library/Logs/cabinet/self-improvement-loop.log` —
  generated-plist convention; the retired hand template wrote
  `.out.log`/`.err.log`) shows a `REPORT-ONLY` block + one grep-able
  `REPORT_ONLY_SUMMARY: {...}` JSON line per run.

**Weekly review → arming auto-apply:** read the accumulated
`REPORT_ONLY_SUMMARY` lines / `would_apply` payloads; when the Captain is
satisfied, flip the services.yml row env to `REPORT_ONLY: "0"`, re-render
(`generate-plists.py`), reinstall + reload the one label (§4 pattern).
Flip back to `"1"` any time — the env is the whole switch.

**Caveats (updated by the 2026-07-07 review fix):** REPORT-ONLY is now the
wrapper's DEFAULT — an UNSET `REPORT_ONLY` runs `--report-only`, so manual
runs and the inline call in `cabinet/cron/role-evals-weekly.sh` are soak-safe
without any export. Only an explicit `REPORT_ONLY=0` (or `false`/`no`/`off`)
arms apply-mode; after the soak, arming the weekly chain therefore needs
`REPORT_ONLY=0` in its environment too, not just the 6h LaunchAgent's.

**Verification (as shipped 2026-07-07 on hq):** two launchd report-only
passes logged (RunAtLoad + kickstart), last exit 0; both `_completed`
events carry `report_only: true` + `would_apply` in the JSONL ledger and
Store mirror; zero new files in `memory/skills/evolved/` and
`instance/roles/proposals/` (the 06:34Z pre-change run had auto-promoted a
draft — exactly the behavior the soak now withholds).
