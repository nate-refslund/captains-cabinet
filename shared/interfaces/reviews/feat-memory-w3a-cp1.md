# Checkpoint review — feat/memory-w3a cp1 (FW-019)

- **Date:** 2026-07-16
- **Branch:** `feat/memory-w3a` (worktree off origin/master `aa56f43e`)
- **Reviewer:** memory-w3a integrator session (Fable 5), integration-level
  review over the full staged diff (`git diff --cached`), on top of the
  lanes' own upstream reviews (lane A: all three recheck findings closed;
  ci-collect: both findings closed on base `aa56f43e`).
- **Scope:** two review-cleared lane diffs + the ledger/plan bookkeeping:
  1. **Lane A — memory supersession closure.** New apply organ
     `cabinet/scripts/memory-supersede-apply.py` (1198 lines) + suite
     `cabinet/scripts/tests/test_memory_supersede_apply.py` (1620 lines, 74
     tests), detector docstring cross-ref, `cabinet/services.yml` row
     `memory-supersede-apply` (Sun 05:45) + updated `memory-contradictions`
     row notes, `instance/config/memory-supersession.yml` (+ byte-identical
     `.example` twin), `.gitignore` soak-ledger entry,
     `cabinet/scripts/egg-export-manifest.txt` R120 delete +
     expect-present rules.
  2. **ci-collect — CI census close.** `.github/workflows/cabinet-ci.yml`:
     stale "ETL transforms (FW-023)" step renamed to the honest
     "cabinet/scripts/lib/tests (full lib suite)" with WHY comment; two new
     steps for the genuinely-uncollected dirs (task_adapters,
     world-aesthetic); `cabinet/scripts/lib/tests/conftest.py` docstring
     de-staled; `framework/frontdoor/tests/test_sov6_binder_grant.py` gains
     parametrized `test_apply_refuses_denied_need`
     (denied/snoozed/expired/superseded/granted — pins the
     authority-minting layer; mutant M1 killer).
  3. **Ledger bookkeeping.** MEMORY-W3-A row (done) + plan-doc §34 parity
     row; the "lane A not landed" drop-note superseded in place (yml
     comment + plan prose); MEMORY-W3-D note gains the CI-COLLECT addendum.

## Integration verification (all in this worktree, python3.12)

- Both diffs applied `git apply --3way`, **zero conflicts**; applied organ +
  test suite verified **byte-identical** to the lane's reviewed FIXED
  copies.
- schg guard: `ls -lO` over every touched path in the live checkout — no
  immutable flags anywhere in the batch; no germline path touched.
- Tests: `test_memory_supersede_apply.py` **74 passed**;
  `test_sov6_binder_grant.py` **35 passed** (incl. the 5 new params);
  `cabinet/scripts/lib/tests` **185 passed** (matches the renamed CI step's
  documented count); `task_adapters/tests` **26 passed**;
  `world-aesthetic/tests` **87 passed + 5 skipped** (matches the new CI
  steps' documented expectations).
- Full `cabinet/scripts/tests` pre-commit: 979 passed, 3 skipped; the only
  failures were 1 F + 22 E in `test_egg_export.py`, all one construction
  artifact — `egg-export.sh` cuts from HEAD but reads the manifest from the
  working tree, so the new `expect-present
  instance/config/memory-supersession.yml.example` rule cannot be satisfied
  until this very commit exists. Pristine `aa56f43e` baseline (fresh
  detached worktree, same command): **928 passed, 3 skipped, 0 failed** —
  nothing else regressed; egg-export re-verified green post-commit.
- Gates: A13 parity exit 0; `ledger-status-parity.sh` GREEN (ids=314,
  md_rows=314, findings=0); LEDGER-HYGIENE-1 uniqueness exit 0;
  `docs-track-code-sweep.sh` GREEN (files=39, findings=0);
  `check-layer-separation.sh` new=0 (baseline 24 / allowlist 18 / current
  42); `generate-plists.py --output-dir <staging>` renders BOTH memory rows
  lint=OK (supersede row: Weekday 0 / 05:45, single exec'd command —
  confirming the one-command-per-row rationale); `py_compile` clean on all
  touched .py; `yaml.safe_load` clean on services.yml, cabinet-ci.yml and
  both instance-config twins. No .sh files in the batch (bash -n N/A).

## Review judgments (integration-level)

- **Security shape of the organ (re-checked, not just trusted):** entire
  store write surface is two module-constant parameterized UPDATEs
  (`_APPLY_SQL` guarded by `superseded_by IS NULL`, `_UNDO_SQL` guarded by
  the exact pointer) + one read-only by-id probe SELECT; ids
  `int()`-validated before binding; no DELETE/DROP/TRUNCATE verb in the
  module (pinned by its own test); conn VALUE argv/env-only, never printed;
  psycopg2 lazy with loud `blocked-db` degrade; config fails CLOSED
  (missing file = ratified `soak`; unreadable/bad-yaml/unknown = `hold`).
  Proposals/soak/needs JSONL treated as untrusted input everywhere.
- **Egg safety:** live `instance/config/memory-supersession.yml` deleted by
  manifest rule; `.example` twin expect-present; organ treats a missing
  live file as the ratified default, so a fresh egg behaves correctly.
  Soak ledger is gitignored runtime (ids + hashes only, never content).
- **CI workflow edits:** step-level `if: ${{ !cancelled() }}` preserved on
  the renamed step and present on both new steps; new suites verified
  hermetic locally at their documented counts; separation rationale
  (basename `tests` collision, 59 collection errors) recorded in-line.
- **Ledger:** supersession-in-place honored (no row/note deleted anywhere);
  MEMORY-W3-A gate_cmd is read-only; statuses within the §9 vocabulary.

**Findings:** none blocking. One deliberate residual, recorded in the
MEMORY-W3-A note: the launchd agent for the new services row is NOT
installed from this worktree (live-fleet mutation out of integration
scope) — rides the normal generate-plists + bootstrap path, mirroring
lane D precedent.

**Verdict:** LAND. Both lanes are self-consistent, upstream-reviewed,
re-verified in the integrated tree; bookkeeping passes every mechanical
gate.
