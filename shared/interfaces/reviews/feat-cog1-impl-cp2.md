# Review artifact — feat/cog1-impl checkpoint 2 (W2: 047 outbox DDL + capture + harness)

Branch: feat/cog1-impl · Base: 0bf60e69 (origin/master merge of #165)
Plan: docs/plans/cognitive-core-phase-1-contract-2026-07-20.md §5.2 (identity GUC),
§5.3 (ephemeral harness), §8.2/§8.2a (apply seam + gated 047), §12.2 item 3.
S0 pin: production work store is PostgreSQL 17 — harness/CI pinned PG17
(harness ran real PostgreSQL 17.10, /opt/homebrew/opt/postgresql@17/bin, no skips).

## Verdict: APPROVE (independent adversarial review, Fable 5, fresh context)

File-set: cabinet/sql/047-officer-tasks-outbox.sql (NEW — outbox table + capture
trigger, identity stamped from the DB-level app.cabinet_id GUC with fail-closed
RAISE), cabinet/scripts/load-preset.sh (identity-GUC step ordered BEFORE the gated
047 apply), cabinet/scripts/tests/lib_cog1_harness.py (NEW — PG17 ephemeral-cluster
harness), cabinet/scripts/tests/test_cog1_outbox_capture.py (NEW — 24-test sims
battery incl. static ordering/strict-apply gates and B1/B2 latency baselines).

## Findings (all P3, none blocking — orchestrator follow-ups, out of W2 file-set)

1. cabinet-bootstrap.sh schema_apply_list still lacks identity-GUC + 047 (grep
   '047' = 0 hits); gap kept loud by the unlisted-DDL WARN (~:1047-1049) and the
   load-preset.sh COG-1 follow-up comment. No fresh-hatch brick risk (capture
   simply not installed until load-preset runs). Own wave before production arming
   (plan §8.2).
2. 038-officer-tasks.sql:129-142 PG16-era exact constraintdef string fails strict
   fresh-apply on PG 17.10 (reproduced at 038:142). Harness mirrors production's
   fail-soft for 038 only, then verifies the five load-bearing objects (documented
   carve-out). Follow-up: 042-style conname guard in its own wave.
3. Recorded deviation per prior-round option (a): real node-lib B2 mutation run and
   real node-lib sim-6a mix run owed at the §12.2 production-apply gate
   (node_modules absent here); psql replays verified faithful vs tasks.ts:405-445
   and my-tasks.sh verb SQL verbatim. Carried in the test-module docstrings.

## Evidence re-run by the reviewer
test_cog1_outbox_capture.py 24 passed (35.87s, real PG 17.10, no skips); 24 passed
again after all mutant round-trips · TestB1B2Baselines standalone 1 passed, all p95
deltas inside x1.10+10ms (worst B1 done 35.98→37.13ms vs bound 49.58ms) · 3/3
manual mutants killed (drop -1, drop ON_ERROR_STOP=1, 047-before-identity ordering),
restores cmp-verified · red-proof: both static gates RED against HEAD load-preset.sh ·
check-layer-separation.sh new=0 · bash -n load-preset.sh OK · germline-lock status +
ls -lO on W2 paths clean · shadow-law token grep over W2 files clean.
