# Mac Migration Phase 0 — Baseline Snapshot

- **Date:** 2026-05-22 UTC
- **Author:** CoS (autonomous execution per Captain msg 2605+2607 "Go")
- **Branch:** `mac-native`
- **Parent tag:** `v1-hetzner-docker` (SHA: 4e1a01aa548cec943828c4a1db0bf5f1227c2cd5)
- **Spec:** Spec 057 (Mac Migration Phase 0 Plan)
- **Source directive:** `cabinet-mac-mini-directive.md` (Captain msg 2599)

## Checkpoint execution log

### 0.1 — Repository state tagged + branch created ✅

- `v1-hetzner-docker` tag created at 22:54 UTC, pushed to GitHub origin
- `mac-native` branch created from master, pushed and tracking origin
- **Golden eval:** tag exists local + remote, branch exists local + remote, tag SHA matches master HEAD (4e1a01a). PASSED.

### 0.2 — Neon snapshots (partial — pg17 client deferred to Mac-side) ⚠️

Hetzner officer container ships pg_dump 16; Neon server runs PostgreSQL 17.10 — version mismatch prevents full pg_dump on Hetzner. Hetzner-side baseline captured via psql + COPY; full pg_dump runs Mac-side after `brew install postgresql@17`.

**Captured:**
- `all-tables.txt` — 65 tables across `public`, `agent`, `neon_auth` schemas
- `schema-tables.txt` — 67 tables with column-level shape via information_schema
- `inventory.txt` — canonical row counts:
  - `public.library_records`: **648**
  - `public.library_spaces`: **10**
  - `public.officer_tasks`: **582**
  - `public.cabinet_memory`: **807**
  - `public.captain_decisions`: 0 (file-based at `shared/interfaces/captain-decisions.md`, DB table is separate-domain unused)
  - `public.cabinets`: 0 (provisioning table not yet populated)
- `pgvector-baseline-topk.txt` — pgvector verification baseline (CTO finding #3):
  - embedding dim: 1024 (voyage-4-large)
  - rows with embedding: 807
  - top-5 IDs for latest-record's embedding: `1022, 744, 785, 741, 740` — this is the round-trip restore comparison anchor.
- Sample COPY exports (50 rows each):
  - `library_records-sample.csv` (757KB)
  - `officer_tasks-sample.csv` (60KB)
  - `cabinet_memory-sample.csv` (222KB)

**Mac-side completion required:**
- Install postgresql-client@17 on Mac via Homebrew
- Run full `pg_dump --schema-only` + per-table `--data-only` against same DATABASE_URL
- CTO finding #1: pre-flight `CREATE EXTENSION vector;` on temp Neon branch before schema restore

### 0.3 — Neon round-trip restore test (deferred to Mac-side) ⏸️

`neon` CLI not installed on Hetzner officer container. Per CTO finding #4, verify `--parent` vs `--parent-branch` flag form on Mac-side install.

Mac-side execution path:
1. `brew install neonctl`
2. `neonctl branches create --name cabinet-phase0-restore-test --parent <main>`
3. Pre-flight on temp branch: `psql $TEMP_URL -c 'CREATE EXTENSION IF NOT EXISTS vector;'`
4. Restore: `pg_restore` from pg17 dumps (created in 0.2 Mac-side completion)
5. Verify counts match `inventory.txt` (within ±0% tolerance)
6. Verify pgvector top-K for the latest-record query returns same IDs as `pgvector-baseline-topk.txt` (1022, 744, 785, 741, 740)
7. `neonctl branches delete cabinet-phase0-restore-test`

**Stop-the-line gate:** if pgvector top-K mismatches, halt before tagging Phase 1.

### 0.4 — Redis state inventory (partial — BGSAVE deferred per CTO finding #2) ✅

Captured Redis state via SCAN (read-only, no production pause). `BGSAVE` + dump.rdb capture is host-agent-gated; deferred until host-agent restarted OR captured Mac-side at first boot.

- `redis-dbsize.txt`: DBSIZE = **101 keys**
- `redis-key-inventory.txt`:
  - `cabinet:heartbeat:*`: 5 (one per officer)
  - `cabinet:triggers:*`: 14 (stream channels)
  - `cabinet:schedule:*`: 40 (cron last-run timestamps)
  - `cabinet:opus-escalations:*`: 0 (post-Move-1 fresh)
  - `cabinet:patterns:seen:*`: 2
  - `cabinet:proxy-spend:*`: 0
  - `cabinet:reflections:count`: 1

Most Redis state is ephemeral (heartbeats, counters). Officer triggers are durable streams; on Mac-side restart, the trigger backlog will be empty — acceptable per Spec 057 §3 "Redis state is mostly ephemeral."

### 0.5 — Officer session JSONLs (CoS-only — others gated on host-agent) ⚠️

CoS officer container holds 771 JSONL files at `/home/cabinet/.claude/projects/`. Captured into `/tmp/cabinet-phase0-snapshots/officer-sessions/cos/projects/`.

Other 4 officers (CTO/CPO/CRO/COO) require `docker cp` from their containers, gated on host-agent restart (Captain founder-action, currently ~22 days down). Mac-side workaround: officers re-OAuth fresh on Mac boot; lose session history but operational state continues. Acceptable per directive §Phase 1.

### 0.6 — Host-state tarball (gated on host-agent) ⏸️

`bash cabinet/scripts/export-state.sh /tmp/cabinet-phase0-snapshots/host-state.tar.gz --include-claude-auth --include-redis-dump` needs sudo on Hetzner host + docker access — both gated on host-agent restart.

**Captain founder-action required:** restart `cabinet-host-agent.service` to unblock 0.6 + full 0.5 + full 0.4.

### 0.7 — Golden eval baseline ✅

13 eval files in `memory/golden-evals/`. Ran 6 .sh scripts; .md specs require interactive validation.

**Aggregate baseline:**
- `phase-0/pre-captain-test.sh`: **32 PASS / 1 FAIL** — 1 pre-existing failure to investigate (folded into Phase 7 soak test bar)
- `phase-1/pre-captain-test.sh`: **35 PASS / 0 FAIL**
- `phase-2/pre-captain-test.sh`: PASS exit
- `framework/fw-019-checkpoint-review.sh`: PASS exit
- `framework/fw-002-spending-limits.sh`: PASS exit
- `library/sprint-a.sh`: **26 PASS / 0 FAIL**

Net: ~93 PASS + 1 FAIL across runnable evals. The 1 FAIL is the pre-existing baseline Phase 7's 48h soak test must clear or higher.

Detailed FAIL output captured in `/tmp/cabinet-phase0-snapshots/golden-eval-failures.txt`.

### 0.8 — Documentation (this file) ✅

This document.

## CTO tech-review findings (Spec 057 → folded into Phase 1 execution)

Per CTO trigger 2026-05-22 22:59 UTC, 4 MUST-fold findings — all Mac-side or pre-restore-test prerequisites:

1. **pgvector extension pre-flight on temp branch BEFORE schema restore.** Add `CREATE EXTENSION vector;` to Mac-side restore script.
2. **BGSAVE not SAVE** for Mac-side Redis dump (avoid prod pause). Hetzner-side I used inventory-only path so no SAVE invoked — clean.
3. **Capture pgvector top-K baseline from PROD BEFORE temp branch create.** DONE — `pgvector-baseline-topk.txt` has 1024-dim, 807 rows, top-5 IDs `1022,744,785,741,740` for the comparison anchor.
4. **Neon CLI flag form verification** — `--parent` vs `--parent-branch`. Verify Mac-side at install time.

Plus 4 SHOULD-fold findings: cabinet_memory* multi-table enumeration, golden-eval side-effect audit, secret hygiene on /tmp snapshots dir, session JSONL size/concurrency. All Mac-side handlable.

## Stop-the-line gates encountered

1. **pg_dump version mismatch (Hetzner pg16 ↔ Neon pg17)** — NOT a stop-the-line; reframed as Mac-side completion. Phase 0 baseline still valid via psql + COPY exports.
2. **host-agent down (~22 days)** — gates checkpoints 0.4-full, 0.5-other-officers, 0.6. Captain founder-action carries forward; doesn't block Phase 1 kickoff since host-state capture can run from Mac-side via SSH+sudo at migration time.
3. **neon CLI absent** — gates 0.3 round-trip restore. Mac-side `brew install neonctl` resolves. Phase 0.3 deferred to Phase 1 start.

## Phase 0 deliverable status

Per Spec 057 §1: "A clean branch and a baseline snapshot, validated by a successful Neon round-trip restore test."

- ✅ Clean branch: `mac-native` exists on GitHub origin
- ✅ Baseline snapshot: row counts + schema docs + pgvector top-K anchor + sample data + Redis inventory + CoS session JSONLs + golden eval baseline
- ⏸️ Round-trip restore test: **deferred to Phase 1 (Mac-side, neonctl + pg17 installed)**. Test plan documented in 0.3 above.

Phase 0 is **COMPLETE TO THE HETZNER-SIDE BAR**. Mac-side completion (0.2 full pg_dump, 0.3 round-trip test) happens early in Phase 1.

## Snapshot inventory

```
/tmp/cabinet-phase0-snapshots/
├── all-tables.txt              # 65 tables across 3 schemas
├── schema-tables.txt           # 67 tables with column-level shape
├── inventory.txt               # canonical row counts
├── pgvector-baseline-topk.txt  # CTO #3 baseline anchor
├── library_records-sample.csv  # 50 newest records
├── officer_tasks-sample.csv    # 50 newest tasks
├── cabinet_memory-sample.csv   # 50 newest memory entries
├── redis-dbsize.txt            # DBSIZE = 101
├── redis-key-inventory.txt     # 7 key prefixes counted
├── officer-sessions/cos/projects/  # 771 JSONL files
├── golden-eval-list.txt        # 13 eval files inventoried
├── golden-eval-baseline.txt    # PASS/FAIL summary
└── golden-eval-failures.txt    # detailed FAIL output
```

**Snapshot directory size:** ~1MB plus officer-sessions/cos/projects (size varies). All on Hetzner box; transfer via export-state.sh + scp during Phase 1.

## Handoff to Phase 1

Captain msg 2605+2607 (full autonomy + "Go"): CoS proceeds to Phase 1 plan drafting next. Phase 0 baseline numbers above are the input.

Phase 1 plan will:
- Sequence Mac setup actions per directive §Phase 1
- Pin cua-driver version (CoS critical-analysis residual)
- Include first-execute of deferred 0.2 (full pg_dump 17) + 0.3 (round-trip restore test)
- Fold CTO's 8 findings inline
- Confirm `--parent` vs `--parent-branch` Neon CLI flag form
