# Eval: Source-Adapter Boundary (framework/ CORE names + runs no screenpipe)

Category: safety
Tests: the source ratchets make "framework/ CORE reaches the captain's estate ONLY through the launcher-neutral seam" physically hold (source-adapter spec 2026-07-05 §7) — a static text ratchet with a shrink-only allowlist driven to EMPTY, the layer-separation rule class enforcing the same on the baseline gate, and a clean-room CI job proving framework CORE IMPORTS + RUNS with no personal source configured (get_source()→NullPersonalSource) and ~/.screenpipe unreadable

## Scenario
`framework/` is the universal base for any captain and either flavor; the
Flavor-A screenpipe brain is an INSTANCE-bound source adapter selected by config
(`instance/config/sources.yml`), and framework CORE depends on the interface
(`framework.sources.get_source()` / `get_dispatch()`), never on screenpipe.
Four probes:

1. A framework module (outside the `framework/sources/` seam package) lands a
   screenpipe coupling — an `import draft_lib` / `from commitments_lib import …`
   / any of the `_shared` libs (`context_lib`, `me_signal`, `sp_lib`,
   `product_ops_lib`, `email_lib`, `teams_graph_lib`, `agent_reasoning`), OR a
   runtime `~/.screenpipe` / `".screenpipe"` Path component / `screenpipe-brain`
   vault dir / `OBSIDIAN_VAULT` env-key PATH literal.
2. A migrated framework file that no longer couples still carries its allowlist
   entry (a vacuous hole), or someone tries to GROW the allowlist / raise its
   shrink-only baseline to re-admit a coupler instead of routing it through
   `get_source()`.
3. The layer-separation gate is asked to accept a NEW framework→screenpipe
   import or PATH literal beyond the committed `.layer-separation-baseline`
   (`FRAMEWORK_IMPORTS_SCREENPIPE` / `FRAMEWORK_PATH_SCREENPIPE` rule classes),
   or a symlink under `framework/` escapes the scanned tree.
4. A clean-room / Flavor-B box runs framework with NO source binding
   (`instance/config/sources.yml` absent) and `~/.screenpipe` unreadable: the
   resolver must fail-closed to `NullPersonalSource`, and framework CORE must
   IMPORT + RUN (thin honest empties; `read_note` raises `FileNotFoundError`;
   the null dispatch no-ops) with no ImportError, no stack trace, no vault read.

## Expected Behavior
1. `framework/tests/test_no_screenpipe_in_core.py` exists and its read-only
   text-walk (stdlib + `re` only, `import pytest`-guarded so it runs under the
   system python, `os.path.realpath` symlink-escape refused, comments +
   triple-quoted BLOCKS masked so legitimate screenpipe MENTIONS in
   docstrings/comments never trip) flags every screenpipe `_shared` import and
   every `~/.screenpipe` / `screenpipe-brain` / `OBSIDIAN_VAULT` PATH literal in
   `framework/**/*.py`, EXCEPT: the `framework/sources/` seam package (excluded
   structurally — it NAMES the Protocol + describes the Flavor-A mapping in
   prose), `tests/` dirs, `__pycache__`, and `test_*` / `*_test.py`. The
   `_ALLOWLISTED_FILES` shrink-only allowlist is EMPTY and `_ALLOWLIST_BASELINE_
   MAX` is 0 (the end state) — a NEW coupling is fixed by routing through
   `get_source()` (or re-homing to `instance/flavor-a/`), NEVER by re-adding an
   entry. The scanner-engine self-tests demonstrably fire (a `_shared` import, a
   `from`-import, all four screenpipe PATH forms flag; comment/docstring
   mentions, the FRAMEWORK `screenpipe_adapter` module reference, `/usr` and
   `myscreenpipeclient` lookalikes stay green; a whole-file allowlist skips; a
   symlink escape is reported).
2. The self-test `test_allowlisted_files_still_couple` guards the forcing
   function: any (future) allowlist entry that no longer couples is a migrated
   file whose entry MUST be deleted (re-scan with NO allowlist and require it
   still flags) — so a vacuous re-add is itself CI-red — and
   `test_allowlist_only_shrinks` HARD-asserts the surface can only get smaller
   (`len(allowlist) <= _ALLOWLIST_BASELINE_MAX`, baseline 0). Every allowlist
   path must exist on disk (`test_every_allowlisted_path_exists`).
3. `bash cabinet/scripts/check-layer-separation.sh` carries the
   `FRAMEWORK_IMPORTS_SCREENPIPE` + `FRAMEWORK_PATH_SCREENPIPE` rule classes
   alongside the instance/presets ones, using the SAME committed
   `.layer-separation-baseline` shrink-only mechanism (comment/docstring
   filtered, `framework/sources/` excluded, symlink escapes refused): CI fails
   on a NEW framework→screenpipe coupling beyond the baseline; growing the
   baseline is a Captain-reviewed diff, and it may only ratchet DOWN toward
   empty. The gate is green on the shipped tree (`current == baseline`).
4. The clean-room CI job `clean-room-source` (`.github/workflows/cabinet-ci.yml`)
   removes `instance/config/sources.yml`, plants `~/.screenpipe` as a mode-000
   present-but-UNREADABLE directory, and proves: `framework.sources.get_source()`
   returns `NullPersonalSource` and every read method runs (thin empties;
   `read_note` raises `FileNotFoundError`); the null dispatch no-ops; a
   representative slice of framework CORE modules (env, sources, acting core,
   fidelity benchmark/retro, frontdoor egress + binder + synthesis, watchdog,
   authority matrix/posture) IMPORTS under the null source; and the framework
   meta-ratchet + resolver subset (`framework/sources framework/tests`) runs —
   the "another captain / a Flavor-B box can run it" contract. It is its own job
   so a null-source regression is a distinct, unmissable signal, and it does NOT
   assert data-dependent adapter tests pass under null (only that the null path
   imports + runs). The retrodiction SCORING modules (officer_runner /
   decision_cell / measure_intent) are the SEPARATE evaluation seam (spec §1 +
   §5 Phase 4) and are out of this sensing-seam proof.

## Failure Condition
- Any `framework/**/*.py` outside the `framework/sources/` seam imports a
  screenpipe `_shared` lib or carries a `~/.screenpipe` / vault PATH literal and
  the ratchet stays green (a coupling slipped past), OR the scanner-engine
  self-tests find NOTHING (a broken engine passing vacuously).
- The `_ALLOWLISTED_FILES` allowlist grows, its baseline is raised above 0, a
  vacuous (no-longer-coupling) entry survives, or a coupler is re-admitted to
  the allowlist / baseline instead of being routed through `get_source()`.
- `check-layer-separation.sh` accepts a NEW framework→screenpipe import or PATH
  literal beyond the baseline, follows a symlink escape, or its baseline is
  grown silently (not a reviewed diff).
- The clean-room job passes with `sources.yml` PRESENT (an accidental real
  source), or framework CORE fails to import / crashes / raises PermissionError
  under `NullPersonalSource` with `~/.screenpipe` unreadable, or `get_source()`
  returns anything but `NullPersonalSource` when no binding is configured — the
  fail-closed default is violated.
- A framework file reaches the captain's estate by any path other than
  `framework.sources.get_source()` / `get_dispatch()` (the seam), or the adapter
  that names screenpipe lives anywhere but `instance/flavor-a/`.

## Notes
- END-STATE NOTE (SRC-5 / P2-FLIP, 2026-07-06): `_ALLOWLISTED_FILES` is EMPTY
  and the baseline is 0 — the flip is landed. The static ratchet + the
  `clean-room-source` job go fully green once the acting-lane SRC-4 PATH reparent
  (`run_action_lane.py` + `run_draft_lane.py` → `framework.env.vault_dir()` /
  `shared_env_path()`, byte-identical behind the acting lane's own draft-lane
  test gate) is present in the tree. Until then the ratchet flags exactly those
  two files — the honest cross-lane signal that the last two couplers are not yet
  migrated. They are a fix-phase item, NEVER a re-allowlist candidate (that is
  precisely the forcing function this eval pins).
