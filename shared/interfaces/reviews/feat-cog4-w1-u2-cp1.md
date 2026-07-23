# Checkpoint review — feat/cog4-w1-u2 (COG-4 W1 unit u2-guards) — cp1

**FW-019 artifact** for the >300-line guards batch (self-review; the phase's binding
review is the §15 frozen fresh-context panel run by the orchestrator). Ground tip
`de5d16c4`; branch `feat/cog4-w1-u2` off origin/master. Contract:
`docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` §8.4 + §9.1.

## Batch (test-only; NO framework/production code, NO services.yml/launchd edits)
- `cabinet/scripts/tests/lib_cog4_ast_pins.py` — pure-stdlib `ast` symbol-level import
  scanners (imports no framework module; self-contained, no cross-unit lib coupling).
- `cabinet/scripts/tests/test_cog4_scheduler_ast_pin.py` — §8.4 pin #1: planner-tree
  import allow-list + cloned defaults-only `as_of` pin + no-subprocess/no-socket pin.
- `cabinet/scripts/tests/test_cog4_dispatch_ast_pin.py` — §8.4 pin #2: the dispatch CLI
  import allow-list (4 policy_engine read symbols + graduation.evaluate + scheduler.serve).
- `cabinet/scripts/tests/test_cog4_parity_ast_pin.py` — §8.4 pin #3: the parity CLI
  import allow-list (dual-plane comparator surface) + a COG-3-shaped transitive-closure
  backstop (consequence-import edge-following mutant + executor-reach mutant + clean control).
- `cabinet/scripts/tests/test_cog4_fleet_truth.py` — §9.1 fleet-truth: the exact 9 row-less
  template organs (re-derived from the tree) + the pairing law + tolerant officer-leakage pin.

## What each guard enforces (and how it is armed tests-first)
- The three §8.4 pins pin EXACTLY the §8.4 symbol lists. Where the target tree/CLI is
  absent this phase (`framework/scheduler/`, `cabinet/scripts/cog4-dispatch-shadow.py`,
  `cabinet/scripts/cog4-parity.py`), the REAL-target arm SKIPS with a vacuity-guard
  docstring carrying its RETIREMENT CONDITION **and** a companion `assert not
  <path>.exists()` tripwire — proven to go RED the instant the target lands (so the skip
  cannot silently persist). Scratch-tree positive controls + negative-control mutants run
  NOW and prove every scanner bites (a gate without a biting mutant is decoration, §12).
- Fleet-truth re-derives the row-less set from the launchd tree × services.yml (never
  trusts a literal); the pinned `EXPECTED_ROWLESS_ORGANS` is the exact-9 tripwire, and the
  `no_new_rowless` / pairing-law tests catch a new row-less template OR a service moved out
  of the manifest. Officer leakage is a TOLERANT subset assertion (present-as-today OR
  absent — u3 removes them — never a new committed concrete officer plist).

## Verification evidence (re-run by reviewers; claims are DATA, §13/L1105)
- `python3.12 -m pytest <the 4 test files> -q -rs` → **104 passed, 6 skipped** (the 6 skips
  are the vacuity-guarded real-target arms).
- Tripwire proof: materializing the three targets flips all 6 real-target arms to FAILED,
  then cleanup leaves only the 5 new files (no stray).
- `cabinet/scripts/cog2-import-gate.py` → exit 0 (shadow boundary intact; my files add no
  cortex/objectives imports).
- `test_cog2_import_gate.py` (incl. `test_every_first_party_py_is_on_scan_surface`) → 58
  passed WITH the new files present (they fall under the `cabinet/scripts` sweep — no
  registration needed).
- `cognitive-architecture-census.py` → PASS (test-only files touch no counted quantity:
  `framework_production_modules`/`_lines` exclude `tests/`; services.yml + enums untouched).

## Known limitations / assumptions (for the panel)
- Static AST scanners do not see dynamically-assembled imports (documented HONEST
  LIMITATION, mirrors lib_cog3); the parity transitive-closure subprocess test is the
  runtime backstop for the comparator half.
- Matrix "mapping surface" is read as `{RISK_CLASSES, load_matrix, matrix_policy,
  ceiling_members}` (the accessors exposing the `ceiling_frozenset_map` policy key, which
  is a policy-dict key, not a python symbol — grounded against matrix.py + the codebase
  import precedent). The parity pin allows the organs registry/descriptor MODULES only,
  not the `framework.organs` package root.
- `officer` is special-cased as the roster mechanism (deploy-mac.sh + instance/config/
  roster.yml, which is instance-local/gitignored — absent from the repo by design).
