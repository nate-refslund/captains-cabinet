# Spec 057 — Mac Migration Phase 0 Plan

- **Version:** v1.1 (cross-spec META amendment — captain-rules runtime files in host-state tarball)
- **Date:** 2026-05-22 (v1.0) → 2026-05-23 (v1.1 08:00 UTC)
- **Author:** CoS
- **Status:** EXECUTED — Phase 0 baseline doc landed at docs/migration-phase0-baseline.md 2026-05-23 06:30 UTC. v1.1 captures one runtime-state gap discovered during Phase 8 (Spec 065) drafting.

**v1.1 changelog — Cross-spec META (caught during Spec 065 drafting):**
- **(1) Captain-rules runtime files in host-state tarball (Checkpoint 0.6).** `shared/interfaces/captain-patterns.md` + `captain-intents.md` + `captain-decisions.md` are gitignored runtime state (created blank by `cabinet-bootstrap.sh` then mutated by `captain-rule-encoder.sh` during officer sessions). On Mac cutover they regenerate blank from bootstrap — losing accumulated patterns/intents/decisions. v1.1 amends Checkpoint 0.6 host-state tarball + `export-state.sh` manifest to include these 3 files explicitly. Restore-path: on Mac side, copy back into `shared/interfaces/` before first officer session start in Phase 2.
- **Spec class:** Migration phase plan (per Captain Mac Mini Directive, msg 2599)
- **Parent directive:** `cabinet-mac-mini-directive.md` (Captain authored, msg 2599; CoS critical analysis msg 2600+2601; Captain ratifications msg 2603)
- **Successor specs:** Phase 1 plan (mac-base-setup), Phase 2 plan (delete-docker-add-launchd), etc. — drafted as each phase becomes the next-up.

---

## 1. Phase 0 goal (from directive)

Audit and tag current state. **Deliverable:** a clean branch (`mac-native`) plus a baseline snapshot, validated by a successful Neon round-trip restore test (Neon dump → fresh Neon branch → sample queries reproduce production results).

Phase 0 does NOT change production state. It captures it.

## 2. Captain ratifications absorbed (msg 2603)

- **Q1 FileVault:** stays disabled on this Mac (STEP-internal deployment, not commercial-EU). GDPR posture deferred to separate commercial-Cabinet substrate.
- **Q2 Personal Cabinet:** NOT in migration scope. Stays on Hetzner.
- **Q3 4-Mac fleet:** 1-then-clone-to-3. This plan covers the FIRST Mac. Subsequent Macs get a separate "clone" play directive after Phase 8 stable.
- **Q4 Cost-tracking:** infrastructure stays, alert thresholds OFF for personal/STEP-internal use. Spec 050 commercial substrate preserved.
- **Q5 Full native:** no Docker. Confirmed. Spec 050 v1.2 amendment will fold this for commercial Cabinet path.

## 3. Checkpoint structure

Phase 0 decomposes into **8 checkpoints**. Each has: pre-conditions, actions, golden eval, rollback path, effort estimate. Every checkpoint must pass before the next starts. Any failure → halt + investigate + decide go/no-go before resuming.

### Checkpoint 0.1 — Repository state tagged + branch created

- **Pre-conditions:** clean working tree (already shipped via commit 581e214 + 4e1a01a tonight). All Captain ratifications absorbed into git history.
- **Actions:**
  1. `git tag -a v1-hetzner-docker -m "Phase 0 snapshot — pre-Mac-migration"`
  2. `git push origin v1-hetzner-docker`
  3. `git checkout -b mac-native`
  4. `git push -u origin mac-native`
- **Golden eval:**
  - `git tag --list | grep -q '^v1-hetzner-docker$'` returns true
  - `git ls-remote --tags origin v1-hetzner-docker` shows the tag on GitHub
  - `git branch -a | grep -q 'mac-native'` returns true
  - `git show v1-hetzner-docker --no-patch --format='%H'` matches current `master` HEAD SHA
- **Rollback:** `git tag -d v1-hetzner-docker && git push --delete origin v1-hetzner-docker && git checkout master && git branch -D mac-native && git push --delete origin mac-native`. Reversible in <1 min.
- **Effort:** 5 minutes.

### Checkpoint 0.2 — Neon snapshots (Library + /tasks + Cabinet Memory)

- **Pre-conditions:** Neon CLI authenticated; `DATABASE_URL` accessible; `/tmp/cabinet-phase0-snapshots/` writable.
- **Actions:**
  1. Schema dump: `pg_dump $DATABASE_URL --schema-only > /tmp/cabinet-phase0-snapshots/schema.sql`
  2. Library data: `pg_dump $DATABASE_URL --data-only --table='library_*' | gzip > /tmp/cabinet-phase0-snapshots/library-data.sql.gz`
  3. Tasks data: `pg_dump $DATABASE_URL --data-only --table='officer_tasks' | gzip > /tmp/cabinet-phase0-snapshots/tasks-data.sql.gz`
  4. Memory data (including pgvector embeddings): `pg_dump $DATABASE_URL --data-only --table='cabinet_memory*' | gzip > /tmp/cabinet-phase0-snapshots/memory-data.sql.gz`
  5. Record sizes + row counts in `/tmp/cabinet-phase0-snapshots/inventory.txt`
- **Golden eval:**
  - Each dump file has non-zero size; `gunzip -t` validates compressed dumps
  - Row counts written to `inventory.txt`: library_records, officer_tasks, cabinet_memory_entries
  - pgvector column present in memory dump (`gunzip -c memory-data.sql.gz | head -200 | grep -q vector`)
- **Rollback:** snapshots don't mutate prod. Delete the directory if needed.
- **Effort:** 15-30 minutes (depends on dataset size).

### Checkpoint 0.3 — Neon round-trip restore test (the directive's gate-deliverable)

- **Pre-conditions:** 0.2 snapshots in hand.
- **Actions:**
  1. Create temp Neon branch: `neon branch create --name cabinet-phase0-restore-test --parent-branch <main>`
  2. Capture temp branch DATABASE_URL
  3. Restore: `gunzip -c schema.sql | psql $TEMP_DB_URL`; same for library + tasks + memory dumps
  4. Verify queries against TEMP_DB_URL:
     - `SELECT COUNT(*) FROM library_records;` matches inventory.txt
     - `SELECT COUNT(*) FROM officer_tasks;` matches inventory.txt
     - `SELECT COUNT(*) FROM cabinet_memory_entries;` matches inventory.txt
     - pgvector semantic-search: pick 3 known queries with known top-K results from prod; same top-K from restored branch
  5. Delete temp branch: `neon branch delete cabinet-phase0-restore-test`
- **Golden eval:** All 3 count queries match within ±0% tolerance; all 3 pgvector queries return same top-K records (by ID) as prod.
- **Rollback:** Neon temp branch destroy on failure is safe (separate isolated branch). If restore itself fails, the dumps are still usable — re-attempt with adjusted flags.
- **Effort:** 30 minutes (round-trip including waits).
- **Stop-the-line gate:** If any restore query mismatches, HALT Phase 0. Investigate before tagging or proceeding.

### Checkpoint 0.4 — Redis state snapshot

- **Pre-conditions:** `cabinet-redis` container running.
- **Actions:**
  1. `docker exec cabinet-redis redis-cli SAVE` (triggers RDB dump)
  2. `docker cp cabinet-redis:/data/dump.rdb /tmp/cabinet-phase0-snapshots/redis-dump.rdb`
  3. Record `redis-cli DBSIZE` in inventory.txt
- **Golden eval:** `dump.rdb` non-zero size; `redis-cli --rdb dump.rdb` parses (read-validates).
- **Rollback:** snapshots don't mutate prod.
- **Effort:** 5 minutes.

### Checkpoint 0.5 — Officer session snapshots (`~/.claude/projects/`)

- **Pre-conditions:** All officer containers running.
- **Actions:**
  1. Discover containers: `docker ps --filter "name=cabinet-officers" --format "{{.Names}}"`
  2. For each container, `docker cp <container>:/home/cabinet/.claude/projects/ /tmp/cabinet-phase0-snapshots/officer-sessions/<container>/`
  3. Per officer, count JSONL files and total lines
- **Golden eval:** All 5 officers have at least one session JSONL; each JSONL is valid line-delimited JSON (`jq -c '.' < file > /dev/null`).
- **Rollback:** snapshots don't mutate prod.
- **Effort:** 10 minutes.

### Checkpoint 0.6 — Host-state snapshot (cabinet/.env + /etc/cabinet + audit logs)

- **Pre-conditions:** export-state.sh shipped (commit 4e1a01a, already on master).
- **Actions:**
  1. Run on Hetzner host: `bash cabinet/scripts/export-state.sh /tmp/cabinet-phase0-snapshots/host-state.tar.gz --include-claude-auth --include-redis-dump`
  2. (The `--include-claude-auth` here is redundant with 0.5 but keeps the tarball self-contained; same for `--include-redis-dump` overlapping 0.4. Safe duplicate.)
- **Golden eval:** Tarball extracts cleanly; manifest text file present; `cabinet/.env` recoverable + non-empty.
- **Rollback:** snapshots don't mutate prod.
- **Effort:** 5-10 minutes.

### Checkpoint 0.7 — Current Cabinet golden-eval baseline

- **Pre-conditions:** `memory/golden-evals/*` exist; Cabinet healthy (heartbeats fresh on all officers).
- **Actions:**
  1. List existing golden evals: `find memory/golden-evals/ -name "*.md" -o -name "*.sh"`
  2. Run each eval against current production state
  3. Record pass/fail per eval in `/tmp/cabinet-phase0-snapshots/golden-eval-baseline.txt`
- **Golden eval:** Baseline written to file; any failing evals documented (these are pre-existing issues, not migration-introduced — but they're the bar Phase 7's 48h soak test must clear).
- **Rollback:** N/A (read-only test).
- **Effort:** 20-30 minutes.
- **Note:** Existing evals may be sparse (we've been adding the `cabinet/tests/test-spec-049.sh` pattern recently but not many others). If light, document what we have + what we'd want to add in Phase 8.

### Checkpoint 0.8 — Document baseline + retrospective skeleton

- **Pre-conditions:** All prior checkpoints passed.
- **Actions:**
  1. Write `docs/migration-phase0-baseline.md` with:
     - Tag SHA: `v1-hetzner-docker` (from 0.1)
     - Branch SHA: `mac-native` HEAD (from 0.1)
     - Library record count, task count, memory entry count (from 0.2 inventory)
     - Neon round-trip verification result (from 0.3)
     - Redis DBSIZE (from 0.4)
     - Officer count + session JSONL counts (from 0.5)
     - Golden-eval pass/fail summary (from 0.7)
     - Snapshot directory inventory (`ls /tmp/cabinet-phase0-snapshots/`)
  2. Stub `docs/migration-phase0-retrospective.md` with sections to fill in post-Phase-8:
     - What worked
     - What surprised
     - Phase A planning notes (Library Activation hooks captured)
     - Phase B planning notes (dev-tasks integration hooks captured)
     - Any constitutional or framework changes that emerged
  3. Commit both docs to `mac-native` branch.
- **Golden eval:** Both docs exist on `mac-native` branch; baseline doc has filled numbers; retro doc has empty stub sections.
- **Rollback:** Git revert.
- **Effort:** 30-45 minutes.

## 4. Effort estimate (whole Phase 0)

**Realistic: 2-3 hours of focused work** (compresses the directive's 1-day estimate). Critical path: 0.1 → 0.2 → 0.3 → 0.8. Checkpoints 0.4 + 0.5 + 0.6 + 0.7 parallelize after 0.2. The bottleneck is 0.2 Neon dump speed (depends on dataset size) and 0.3 round-trip-restore (depends on Neon branch-create latency).

**Worst-case escalation paths:**
- If 0.2 dumps fail (network / auth): contact Neon support; fall back to direct DATABASE_URL query exports per-table.
- If 0.3 round-trip mismatches: pgvector restoration is the most likely culprit (embedding column types). Halt; manually inspect mismatched rows; either fix snapshot format or document as known limitation before tagging.
- If 0.7 golden evals all fail: probably a config drift, not a migration concern. Document + proceed; Phase 7 soak test is the real validation gate.

## 5. Rollback policy (whole Phase 0)

- Checkpoints 0.1: reversible in <1 minute (delete tag + branch).
- Checkpoints 0.2-0.7: read-only operations, no rollback needed; failures just trigger re-attempt or investigation.
- Checkpoint 0.8: docs commit reversible via `git revert`.

**If Phase 0 ABORTS partway:** the partial snapshots in `/tmp/cabinet-phase0-snapshots/` are preserved; the `v1-hetzner-docker` tag (if 0.1 ran) remains useful for future attempts. No prod state was touched.

## 6. Stop-the-line gates

These gates require Captain decision before proceeding:

1. **Golden-eval baseline (0.7) finds critical failures.** If existing prod is broken in a way Phase 0 surfaces, the migration's "leave Cabinet functional" rule (directive Part 8 #5) demands we fix prod first.
2. **Neon round-trip (0.3) embeddings mismatch.** If pgvector restoration loses semantic-search fidelity, we can't migrate without fixing it.
3. **Any unexpected destructive operation needed.** Phase 0 is read-only; if scope creep emerges, halt and surface.

No other gates expected.

## 7. Phase 0 → Phase 1 handoff

When Phase 0 completes successfully:
- `v1-hetzner-docker` tag is the recovery anchor for the cloud deployment forever.
- `mac-native` branch is where ALL migration work happens. No commits to `master` during Phases 1-7. Phase 8 merges `mac-native` → `master`.
- `/tmp/cabinet-phase0-snapshots/` is the data export ready for Mac-side restore in Phase 1/2.
- `docs/migration-phase0-baseline.md` is the bar Phase 7 soak test must beat.
- CoS DMs Captain: "Phase 0 complete, baseline numbers attached, ready for Phase 1 authorization."

## 8. Open items folded into later phases

Per CoS critical-analysis residuals (msg 2600+2601):
- **cua-driver version pin** → Phase 1 install step.
- **Stagehand v3 vs cua-driver routing** → Phase 8 constitution clause.
- **Lead failover ladder enhancement** → Phase 7 watchdog enhancement.
- **Hetzner decommission decision** → Phase 8 post-tag step (worth Captain decision at that time).
- **dev-tasks STEP-coupling** → Phase B documentation when authorized.

## 9. Sign-off

This Phase 0 plan is **DRAFT, awaiting Captain ratification.** Once ratified, CoS executes the 8 checkpoints in sequence. Estimated wall time: 2-3 hours focused, or one evening session at relaxed pace.

CRO + COO multi-failure-mode adversary on this plan welcomed in parallel but not gating — Phase 0 is read-only + reversible.

---

**Captain decision queue entry:**

> Ratify Spec 057 (Mac Migration Phase 0 Plan)? If yes, CoS executes checkpoints 0.1-0.8 in sequence. Expected wall time 2-3 hours focused.
