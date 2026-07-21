# Review artifact — feat/cog1-impl checkpoint 4 (W4: parity monitor + fencing + replay hash)

Branch: feat/cog1-impl · Base: 0bf60e69 (origin/master merge of #165)
Plan: docs/plans/cognitive-core-phase-1-contract-2026-07-20.md §8.3 (per-cycle
parity: asymmetric effective-mapped predicate + freshness floor + verdict JSONL),
§7 (fenced central vocabulary — the extension must not become a fourth writer
family), §4 record-step (rows as the replay/audit substrate), §12.2 (tests-first
order, negative controls/mutants before implementation).
S0 pin: production work store is PostgreSQL (major-agnostic parity/replay logic);
integration gates ran against a real ephemeral cluster, no skips.

## Verdict: APPROVE (independent adversarial review, Fable 5, fresh context)

FW-019 batch artifact for a >300-line commit: task-sync-drift-falsifier.py is
+464/-8 (472 changed) plus three new files (cog1-replay-hash.py 193,
test_cog1_fencing.py 251, test_cog1_parity.py 715, test_cog1_replay_hash.py 312)
— well over the 300-line threshold, so this artifact is owed at commit time.

File-set (this wave — exactly 6 paths):
- cabinet/scripts/task_sync_runner.py (MODIFY — 3 `payload.kind` stamps; +9/-0).
- cabinet/scripts/task-sync-drift-falsifier.py (MODIFY — the COG-1 parity block:
  asymmetric effective-mapped predicate, freshness floor, legacy-plane wiring;
  reused `_read_lines`/`_append_line`/`_previous_date_breached` with param
  additions; +464/-8).
- cabinet/scripts/cog1-replay-hash.py (NEW — deterministic replay hash;
  read-only XRANGE + SELECT, no XADD/emit/write).
- cabinet/scripts/tests/test_cog1_fencing.py (NEW).
- cabinet/scripts/tests/test_cog1_parity.py (NEW).
- cabinet/scripts/tests/test_cog1_replay_hash.py (NEW).

## Findings (verified)

- **P3 (non-blocking, no fix required):** the §8.3 predicate window is
  implemented CUMULATIVE (all planes anchored at MIN(officer_tasks_outbox
  .occurred_at), read to now) rather than a literal rolling 24h "nightly
  window". Disclosed transparently by the fix-agent as a companion fix. It is
  conformant with §8.3's "within the window" language (pilot-span bounded, so
  pre-047 history and pre-047 legacy are windowed out and never false-breach),
  strictly STRONGER (catches a loss on ANY prior soak day, matching the soak's
  "zero unexplained breaches over 7 consecutive days"), and cannot false-breach
  because legacy⊆outbox is asymmetric and the legacy stream is not MAXLEN-trimmed.
  Proven by test_legacy_plane_is_wired_and_window_excludes_pre_pilot,
  test_pre_pilot_history_windowed_out_coverage_sound (pre-pilot exclusion) and
  test_post_pilot_legacy_loss_breaches (a real loss still fires). Recorded for
  orchestrator awareness only — do NOT change thresholds/window semantics.

## Scope discipline

- No out-of-scope EDITS: the wave touched exactly its 6 allowed files. Both
  modified files carry only W4 content.
- Concurrent sibling-wave files present in the shared working tree are EXCLUDED
  from this commit (my-tasks.sh, task-events-watch.py, egg-export-manifest.txt +
  test_egg_export.py [W5 §8.4/§4.1/egg], and the untracked W5 scripts/manifest).
  The commit stages exactly the 6 W4 paths + this artifact (force-added).

## Evidence re-run by the reviewer (house interpreter python3.12, separate invocations)

- test_cog1_fencing.py = **9 passed**; test_cog1_replay_hash.py = **20 passed**;
  test_cog1_parity.py = **43 passed**; test_task_sync_drift_falsifier.py
  (existing falsifier regression) = **27 passed** — 0 skips in every suite.
- PG+redis integration gates GENUINELY RAN (verified via -rs skip-reporting):
  TestPostgresWindowWiresLegacyPlane (5), TestReplayHashOverPostgres (4),
  TestLiveDrainEmitsNothing (1) all executed and passed against a real ephemeral
  cluster.
- py_compile clean on the 3 modified/new scripts; --probe returns NOFILE
  stdlib-only (lazy framework import preserved).
- check-layer-separation.sh → **new=0**; verify-cognitive-architecture.sh census
  **PASS** (central_event_types 91<=91, duplicate_event_writer_sinks 3<=3).
- never-a-score + product/captain hygiene greps CLEAN on all W4 additions.
- No XADD/emit/write in the parity-reader additions (read-only XRANGE + SELECT).
