# Germline amendment — preset-aware context in the officer launcher (2026-07-17)

**Status:** STAGED DARK. `cabinet/scripts/start-officer-mac.sh` is
schg-locked on the live deployment (`germline-lock.sh` FILES[], verified
`ls -lO` 2026-07-17), so this change ships as a verified patch —
`patches/preset-aware-context-launchers.patch` — awaiting the next
Captain-sudo germline unlock window. Per doctrine the locked file itself is
NOT edited by this wave; nothing here self-applies.

## Why (the config split, audit 2026-07-16)

The tasks subsystem keys its context off
`instance/config/active-project.txt`, but preset deployments (the live box
runs preset `portfolio`) declare lanes via `instance/config/contexts/*.yml`
and never write that file — and NOTHING exported `CABINET_CONTEXT`. Net
effect: `officer_tasks` was structurally unusable on portfolio deployments
(live board: 0 rows ever) because `my-tasks.sh` died at its context gate in
every officer session.

The non-germline half of the fix is already landed by this wave: the shared
resolver `cabinet_resolve_context` (`cabinet/scripts/lib/lanes.sh`, twin of
`framework.env.active_context()` and the dashboard's
`src/lib/active-context.ts`) with the chain

    CABINET_CONTEXT env
    > instance/config/active-project.txt
    > officer→lane derivation from instance/config/contexts/*.yml
      (exact slug, else longest '<lane>-' prefix)
    > single-declared-lane
    > platform.yml lane_default (must be a declared lane)
    > fail-LOUD with a one-line remedy

and `my-tasks.sh` / `task_sync_runner.py` / the dashboard consumers now ride
it. `my-tasks.sh` therefore already works inside a portfolio officer session
(officer identity comes from `CABINET_OFFICER`, which the launcher exports
today). This amendment closes the remaining launcher half.

## What the staged patch does (one file: start-officer-mac.sh)

1. The `CABINET_LANE` block (FIX-4, ~line 395) gains a preset-aware
   fallback: when `active-project.txt` yields nothing, it sources
   `lib/lanes.sh` and resolves `cabinet_resolve_context "$OFFICER"`. The
   existing FW-073 slug validation (`[a-z0-9][a-z0-9-]*`, ≤32) still
   re-checks whatever comes back (resolver output is already shape-gated).
2. On a valid slug it now exports **both** `CABINET_LANE` (authority-cell
   lane, unchanged semantics) and `CABINET_CONTEXT` (the tasks-context twin
   — in this repo the lane enum IS the context enum). On no slug it unsets
   both (the existing fail-safe leg, now also scrubbing a stale inherited
   context).
3. The `--dry-run` summary additionally prints `CABINET_CONTEXT=` next to
   the existing `CABINET_LANE=` line so `test-mac-dry-run.sh` can assert the
   export contract.

Behavior note (deliberate, Captain-visible): on the live portfolio box the
lane officers currently boot with NO lane (unmeasured authority cell →
propose-only at the gate). After this patch they boot with their TRUE lane,
so the earned-posture matrix starts measuring the real `(officer, lane,
action_type)` cells — that is the designed mechanism, not a loosening; a
fresh cell still starts at its earned floor.

## Apply (inside the unlock window, Captain sudo)

    sudo cabinet/scripts/germline-lock.sh unlock cabinet/scripts/start-officer-mac.sh
    git apply --3way patches/preset-aware-context-launchers.patch
    bash -n cabinet/scripts/start-officer-mac.sh
    bash cabinet/scripts/start-officer-mac.sh <lane-officer> --dry-run   # expect CABINET_LANE= + CABINET_CONTEXT= lines
    # commit, then SAME DAY:
    sudo cabinet/scripts/germline-lock.sh lock

Verified in staging (2026-07-17): the patch applies clean (`git apply
--check` + `--3way`) against the gh/master tree, `bash -n` passes on the
patched copy, and the resolver chain itself is test-pinned by
`cabinet/scripts/lib/tests/test_resolve_context_sh.py` (bash↔python parity)
plus `cabinet/scripts/tests/test_my_tasks_context.py` (end-to-end portfolio
simulation).

## Revert

`git apply -R patches/preset-aware-context-launchers.patch` inside an unlock
window (or `git checkout <pre-apply-commit> -- cabinet/scripts/start-officer-mac.sh`).
Reply "revert launcher context resolver" to have a session do it.

## Residual (named, not staged here)

`cabinet/scripts/start-officer.sh` (Linux/Docker, also germline) has the
same gap in its legacy mode (`ACTIVE_SLUG` from `active-project.txt` only,
no `CABINET_CONTEXT` in `EXPORT_VARS`). It is NOT part of this patch — its
one-shot `EXPORT_VARS` env assembly needs its own surgery — but it should
ride the SAME unlock window; until then Linux deployments keep working via
`--project` / `active-project.txt`, and officer sessions there can set
`CABINET_CONTEXT` per-service env as the sanctioned override.
