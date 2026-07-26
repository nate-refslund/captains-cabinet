# Checkpoint review — fix/hatch-roster-authz cp1 (FW-019)

Reviewer: Claude Opus 5 (1M), clean clone of origin/master @ 9673867f, own
scratch dir. Baseline re-measured on that clone before any edit.

## What the diff changes

1. `cabinet/scripts/generate-instance.py` — hiring is authorization-gated.
   `authorized_officers(root)` = officer column of
   `cabinet/officer-capabilities.conf` **∩** `agents:` keys of
   `cabinet/mcp-scope.yml`. `render_roster` emits the Chair plus only those
   lane CEOs the intersection covers; the rest become a `PENDING
   AUTHORIZATION` comment block above `roster:` and paste-ready rows in the
   printed next steps. Chair unauthorized *while both files exist* ⇒
   `GenerationError` (refuse, write nothing).
2. `cabinet/scripts/null-hatch.sh` — gitless staging parity: after the tar
   copy, prune what the tree's own `.gitignore` names (throwaway `git init`,
   `ls-files --others --ignored --exclude-standard`, config pinned to
   `/dev/null`), so both staging branches stage the same shipped content.
3. `cabinet/scripts/hatch.sh` — new `[roster-authz]` proof step runs the
   lockstep module against the LIVE tree the hatch just wrote; plan renumbered
   7→8 … 15→16.
4. `cabinet/scripts/hatch-lib/errands.sh` — errand 1 is now marked OPTIONAL /
   non-blocking and tells the Captain the re-run is the hire.
5. Tests: 3 new arms in `framework/tests/test_roster_conf_lockstep.py`
   (fire in CI, no roster.yml needed), 10 new arms in
   `TestRosterAuthorizationGate`, new module
   `cabinet/scripts/tests/test_null_hatch_staging.py` (4 arms).
6. Docs tracked in the same commit: cabinet-init SKILL.md, mac-mini-setup.md,
   hatch-v0 runbook, the rendered lane-CEO header stamp, and the RES-003 line
   cite in `docs/plans/declared-residuals-register.md` (my hatch.sh docstring
   edit moved the anchor 61→69).

## Findings I raised against my own diff

- **F1 — the null-hatch prune removes the only place the live-roster lockstep
  arm ever fired.** Real, accepted, and the reason step 3 exists. Coverage
  delta: on any git checkout the arm was *already* dark under `git archive`
  (unchanged by me); it fired only on a gitless tree. The generated-roster
  case is now impossible by construction, and `hatch.sh [roster-authz]` fires
  the arm on the live tree — the correct premise for it. Residual: a
  hand-edited unauthorized roster on a gitless egg is no longer caught inside
  `null-hatch`; a plain `pytest framework/tests` run in that tree still
  catches it. Recorded, not hidden.
- **F2 — fixture change to `cab_root`.** Adding the germline pair to the
  generator-test fixture keeps every pre-existing assertion (acme lane CEOs in
  the roster, bootstrap seeding all three roles) intact rather than relaxing
  them. The fixture now models "Captain already applied the rows", which is a
  real deployment state; the un-applied state has its own new tests. No
  existing assertion was changed, weakened or deleted.
- **F3 — `cos` is rostered unconditionally when the germline pair is ABSENT.**
  Deliberate: absence is a partial tree (unit fixture, stripped root), and the
  Chair is the surface `hatch.sh` names directly. The dangerous case — pair
  present but not covering `cos` — refuses. A sibling CI arm
  (`test_generated_fresh_hatch_rosters_the_chair`) fails at the source if the
  shipped pair ever stops authorizing the Chair.
- **F4 — `platform.yml`'s `officers:` block still lists un-hired lane CEOs.**
  Left deliberately: that block is the org chart + supervision type
  (`officer-supervisor.sh` greps it for `type:`), while `roster.yml` is the
  hire record every fleet-deriving consumer reads (`deploy-mac.sh`,
  `generate-plists.py`, `lib_roster`, `cabinet-doctor.sh`). Narrowing the
  blast radius was preferred over touching a second surface. Noted as a
  deliberate asymmetry, not an oversight.
- **F5 — two of the fourteen new arms pass against pre-change code**
  (`test_unauthorized_lane_still_generates_its_inert_files`,
  `test_authorization_read_is_read_only`, plus
  `test_gitless_staging_keeps_shipped_files`). They are non-regression
  guards by design, stated as such; the load-bearing arms all fail
  pre-change.

## Both-directions evidence (cache purged, `PYTHONDONTWRITEBYTECODE=1`)

| Arm set | vs pre-change code | vs post-change |
|---|---|---|
| `TestRosterAuthorizationGate` (10) | 8 failed, 2 passed | 10 passed |
| lockstep CI arms (3) | 2 failed | 3 passed |
| `test_null_hatch_staging` (4) | 3 failed | 4 passed |
| Chair guard-mutation (strip `cos` from `mcp-scope.yml`) | 3 lockstep arms fail + generator refuses with the named message | n/a |
| `null-hatch.sh` on a gitless hatched tree | **exit 1** (lockstep + 2 evidence-plane shadow proofs, via a dragged-in `.pytest_cache`) | **exit 0** |

Each fix independently closes the gitless failure (generator-only: exit 0;
null-hatch-only: exit 0) — but only the generator fix makes the *deployment*
sound; the staging fix alone leaves an unauthorized officer hired and merely
stops the sandbox from seeing it. That ordering is why the generator change is
the primary fix.

## Verdict

approve. No existing test, threshold or germline file was modified. Layer
separation unchanged (new=0). Docs sweep green.
