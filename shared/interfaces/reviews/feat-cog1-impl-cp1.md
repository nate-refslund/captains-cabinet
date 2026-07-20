# Review artifact — feat/cog1-impl checkpoint 1 (W1: envelope v2 + registry)

Branch: feat/cog1-impl · Base: 0bf60e69 (origin/master merge of #165)
Plan: docs/plans/cognitive-core-phase-1-contract-2026-07-20.md §4.1 (version dispatch),
§10.1 (census allowances), §10.3 (phase-0 gate frozen-historical), §12.2 items 1-2.

## Verdict: APPROVE (independent adversarial review, Fable 5, fresh context)

File-set: framework/triggers/envelope.py (v2 dispatch appended, v1 bytes frozen —
lines 1-376 and validate() region 199-214 cmp-verified byte-identical to HEAD),
framework/triggers/schema_registry.py (NEW), framework/schemas/domains/tasks/
task-event.v1.json (NEW), framework/triggers/tests/test_envelope_v2.py (NEW, 167
tests), framework/triggers/tests/test_schema_registry.py (NEW, 63 tests).
This commit additionally carries the commit-step-owned §10.1 allowance rows in
cabinet/config/cognitive-architecture-contract.yml (+1 module, +517 lines,
census-measured at commit time) and the §10.3 frozen-historical note on the COG-0
ledger row — required to land in the SAME commit as the first new framework module.

## Findings (all P3, none blocking)

1. Census --check BLOCKed pre-allowance (209>208 modules, 61840>61323 lines) —
   expected state; resolved by the §10.1 rows in this commit; census PASS re-verified
   pre-commit. Enum pins hold: central_event_types 91/91, central_action_types 30/30
   (M4), layer_debt 24/24, allowlist 19/19.
2. validate_v2 sentinel refusal is exact-match vs the Phase-0 .strip().lower()
   normalization (contracts.py:293,:388,:548). Vocabulary drift-pinned by test;
   normalization deviation recorded, optional hardening deferred to the relay wave.
   Low practical risk: cabinet_id is stamped DB-side with fail-closed RAISE.
3. Shadow-law token sweeps enumerate git ls-files, so untracked W1 files were
   invisible pre-add; reviewer closed the gap with a manual 6-token grep over all
   wave files (clean). Tracked-file sweeps re-run post-add in the commit battery.

## Evidence re-run by the reviewer
test_envelope_v2.py 167 passed · test_schema_registry.py 63 passed (jsonschema
Draft 2020-12 cross-checks ran, not skipped) · full framework/triggers/tests 393
passed (163 baseline preserved, v1 suites byte-untouched) · framework/events +
framework/outbox tests 63 passed · test_my_tasks_events.py 25 passed ·
check-layer-separation.sh new=0 (probe-verified it scans untracked files) ·
never-a-score --self-test 12/12 · tests-first RED reproduced at HEAD 0bf60e69
(158 failed/9 passed; registry ImportError) · 4/4 mutants killed (sentinel-off,
dispatch-inverted, M4 fence-off, closed-keyword-guard-off), restores cmp-verified.
Emission-scoped posture verified: zero emission/Redis/subprocess surface in W1.
