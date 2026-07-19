# Checkpoint review — feat/fresh-hatch-wb cp1 (FW-019)

Batch: fresh-hatch Wave B — 6 LANDABLE silent-dead/security fixes (committed) +
2 SCHG-HANDBACK staged patches (#9, #7). Base `origin/master @3e9038b`.
Reviewer: build agent self-review of `git diff --cached` before landing.

## LANDABLE (in this commit)

### #27 measurement seed never installed — role_eval_runner.py, scenario_runner.py, load-preset.sh
- Discovery now walks the canonical framework dir AND an instance seed dir
  (`instance/measurement/<kind>`, resolved via CABINET_ROOT; CABINET_ROLE_EVALS_DIR
  / CABINET_SCENARIOS_DIR test overrides). load-preset.sh copies the preset's
  `measurement/{role_evals,scenarios}` seed there (idempotent).
- Layer-sep: framework→instance read written as a full-path string
  (`f"instance/measurement/{kind}"`), matching env.py house style; check-layer-sep
  stays new=0.
- Tests: test_measurement_seed.py (7), test_load_preset_measurement_seed.py (3).
  Empty/absent seed → clean 0 (no crash). Verified 10 evals + 5 scenarios
  discovered from the real work-preset seed.

### #21 self_improvement_loop.py — validation gate fail-closed on shells_run=0
- `_run_golden_eval_shells` returns `(False, shells_run=0)` on absent/empty dir
  (was `(True, [])`, a vacuous pass). `_validation_gate` restores CABINET_ROOT
  BEFORE running the golden shells (was inside the try, where a scenario setup's
  temp-root leak made the shells glob an empty dir).
- Tests: test_validation_gate_fail_closed.py (5). MUTANT proven: 3/5 red against
  origin/master, all green with the fix.

### #51 generate-plists.py — cabinet/.env SPOF
- Wrapper decouples the best-effort `.env` source from the exec chain: `;` not
  `&&`, `[ -r cabinet/.env ]` guard, `cd … || exit 1` still aborts. Kept the
  `source` builtin (vs spec's `.`) to preserve test_due_at_reminder_tick's literal
  assertion — behaviourally identical; only the `&&`→`;` decoupling is load-bearing.
- Empirically verified: absent .env → execs; malformed (unmatched quote) → execs;
  cd-fail → aborts. services.yml wrapper doc comment updated (docs-track-code).
- Tests: test_wrapper_spof_and_monitor_gating.py (#51 half). Existing plist suites
  green (13).

### #52 services.yml — screenpipe monitors cry-wolf
- healthchecks-drill + memory-curator-health marked `disabled: true` +
  `disabled_reason` (PRIMARY option). Reuses the already-tested skip path in BOTH
  generate-plists (not rendered) AND the watchdog registry (excluded from
  no-silent-cron floors), so no #59-class false-DEAD.
- Tests: test_wrapper_spof_and_monitor_gating.py (#52 half) — rows disabled +
  reason, not rendered, not floored.

### #50/#33 intake.py — blind MAXLEN trim evicts undelivered items
- `ack()` replaces `xtrim(key, _MAXLEN)` with `_safe_trim`: MINID boundary =
  oldest-pending id else group last-delivered-id; skip when != 1 group; probe
  failures no-op. Added xinfo_groups/xpending_min/xtrim_minid to both backends.
- Tests: test_intake_safe_trim.py (8: 6 unit + 2 Redis integration). MUTANT proven:
  blind MAXLEN dropped 400/1400 undelivered items; fix retains all. Existing intake
  suite green (81).

### #32 triggers.sh — ACK-trim erases audit trail before the archive reads it
- `_trigger_trim_processed_prefix` clamps the trim boundary to the exhaust-archive
  cursor (`CABINET_EXHAUST_STATE`); unknown/corrupt cursor → retain all;
  `CABINET_TRIGGER_TRIM_IGNORE_ARCHIVE=1` opts out. Added `_min_stream_id`. The
  JSON state read passes path+stream as argv (no interpolation); `set -e` safe;
  python3.12 with `|| true`.
- Tests: test_triggers_archive_clamp.py (3). The ignore-env test IS the mutant
  contrast (clamp removed → trims to #30). Existing durability suite green (6).

## SCHG-HANDBACK (staged patches, NOT in this commit)

- #9 gen-officer-mcp-config.py: validate server command+args against the trusted
  COMMITTED baseline (never the officer-writable extra-mcps.json), emit the trusted
  spec → closes cross-officer RCE. Patch + tests (32 pass) staged;
  `git apply --check` clean vs the live schg path.
- #7 classifier.py: `-XVERB` bundled + scheme-less-host curl mutations now hit the
  network_write ceiling. Patch + tests (123 pass; authority suite 945) staged;
  apply-check clean.
- Both under `designs/hook-patches/`; handback note documents the one-window
  unlock→apply→relock procedure + the #9 residual (extension servers refused).

## Cross-cutting

- Fail-closed throughout (committed-baseline validation / conservative remote
  classification / MINID-safe + archive-clamped trims that retain on uncertainty /
  decoupled env sourcing that still reports). No product/captain tokens introduced.
  redis-cli + python calls pass values as argv, never shell-interpolated (Corridor
  analyzePlan returned no conflicts).
- Verification: py_compile (11), bash -n (2 shells), YAML valid, layer-sep new=0,
  185 new+affected tests, 1502 framework tests, 171 cabinet/scripts consumers — all
  green with Redis live.

## Risks / notes
- #51 keeps `source` (not `.`) — deliberate, behaviourally identical, avoids
  churning an unrelated test.
- #32 uses python3.12 (repo house interpreter, matches triggers.sh's other python
  call); a missing interpreter fails safe (retain all).
- The 2 handback patches must land together in one Captain germline-unlock window.

Verdict: LANDABLE set ready to commit; handbacks ready to stage.
