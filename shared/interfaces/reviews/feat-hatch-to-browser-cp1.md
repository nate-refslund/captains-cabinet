# Checkpoint review — feat/hatch-to-browser cp1

Reviewed-Scope-Digest: 391e7456bffb3386ae50070f1e7c8c5fb27b1f782783ebab57ae034bf2ac8cdc

**Branch:** `feat/hatch-to-browser` off `origin/master` @ `ad8f0d3f`
**Reviewer:** builder session, Opus 5 (1M)
**Scope:** 8 staged paths — 2 units.

## What changed

**U5 — the first briefing is readable in a browser.**
`cabinet/dashboard/src/lib/briefing.ts` (new) + `/briefing` page (new) render
the NEWEST `instance/memory/first-briefing-<date>.md` and
`instance/memory/library/genesis-research-brief.md`. Neither had any dashboard
reader; the Library roots at `org_vault_dir()` and was deliberately NOT
repointed (that would move the whole Library). The page is linked from
`/onboarding`'s page layout — `journey-card.tsx` untouched (a parallel builder
owns it).

**U6 — the hatch ends in a browser.**
`cabinet/scripts/hatch.sh`'s app-feel tail: on the DEFAULT `--no-launchd` path
it now starts `start-dashboard.sh` under `nohup`, waits on `/api/health` with a
bounded, self-narrating loop, copies the password via
`dashboard-password.sh --copy` (still never printed) and opens `/onboarding`.
New `--no-browser` flag (+ `HATCH_NO_BROWSER=1`) skips the handover.

## Review findings

1. **Confinement is load-bearing, not decoration.** The newest-briefing scan
   takes names off the filesystem, so a symlink named
   `first-briefing-9999-12-31.md` pointed outside `instance/memory` is a real
   escape. Verified by mutation: deleting the `lstat` symlink drop and the
   `resolveInMemory` re-confine from `latestFirstBriefingRel()` turns 3 of the
   19 briefing tests red, and the scan then returns the escaping name.
2. **The clean-room arm is unchanged, and that is asserted, not assumed.**
   `test_clean_room_skips_everything` now drives the extracted tail and asserts
   ZERO calls to `open`, `curl`, `nohup`(start) and the password script, plus no
   `~/Applications` write. Previously only `open` was checked.
3. **A test must never write the clipboard.** The password script is invoked
   through a PATH-shimmed `bash` in the harness; the extract itself runs under
   `/bin/bash`. Without this the suite would have copied the running checkout's
   live `DASHBOARD_PASSWORD` onto the developer's clipboard on every run.
4. **The started dashboard outlives the script.** That is the point of the
   feature and therefore has to be said out loud: the tail prints the pid, the
   log path, and `kill $(lsof -ti tcp:<port>)`.
5. **Never a gate.** Every new branch returns 0; the `app_feel || echo` fallback
   is still the file's last line. Forced-failure drives (open, plutil, password,
   probe timeout) all assert exit 0 with an honest line.
6. **Already-serving is reused, not stacked.** The first probe doubles as a
   liveness check so a second hatch cannot start a second server on the port.

## Batteries (this session, this tree)

| Gate | Result |
|---|---|
| `bash -n cabinet/scripts/hatch.sh` + `shellcheck -S warning` | clean |
| `bash cabinet/scripts/null-hatch.sh` | PASS (198 passed, 7 skipped; census + layer-sep OK) |
| `npx tsc --noEmit` (dashboard) | exit 0 |
| `npx vitest run` (dashboard) | 3244 passed, 1 skipped / 159 files |
| `python3.12 -m pytest cabinet/scripts/tests -q` | 5233 passed, 34 skipped |
| `pytest cabinet/scripts/tests/test_hatch_app_feel.py` | 19 passed |
| Mutation drive on the confinement guard | 3 tests go red — the sensor fires |

## Residual

- The login gate still redirects post-auth to `/`, so a first-ever hatch lands
  the operator on `/login` → `/` rather than `/onboarding`. Changing that means
  touching `actions/auth.ts` and adding a redirect-target parameter — an
  open-redirect surface not worth opening for a one-click difference. Orientation
  is in the nav on both nav sets.
- `/briefing` is reachable by URL and linked from Orientation; it is deliberately
  NOT added to `nav-config.ts`, whose tests pin exact nav lengths and label
  lists — churn there collides with concurrent nav work for no user gain.
