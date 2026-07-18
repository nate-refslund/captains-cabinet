# Checkpoint review — feat/fresh-hatch-wa cp1 (Fresh-Hatch Wave A)

Reviewer: build agent (self-review of staged diff, FW-019). Base: origin/master `8dced97b`.
Scope: 6 first-boot blockers (#56 #58 #59 #57 #60 #13) — unlocked files only; no schg path edited.

## What changed (by fix)

- **#56 `cabinet/scripts/setup-mac.sh` (Step 3):** bare `pip install ... 2>/dev/null` (warn-only) →
  capture pip stderr, retry `--break-system-packages` (PEP-668), verify by import, and on total
  failure `fail` LOUD + surface the real stderr + append an `ISSUES` entry. Set-e-safe idiom
  (`A=$(...) && rc=0 || rc=$?`). Captain-agnostic.
- **#58 `cabinet/scripts/cabinet-doctor.sh` §3+§5:** §5 roster-gates scope grants via
  `lib_roster.load_roster` (non-deployed product lanes dropped; unregistered-but-granted → WARN not
  DEAD). §3 gates MCP-env DEAD on base-vs-overlay (shipped base connector missing env → WARN;
  deliberately-wired `extra-mcps.json` MCP missing env → DEAD). NAMES-only env contract preserved;
  `mcp-scope.yml` (schg) only READ, never written.
- **#59 `lib_roster.py` + doctor §1:** `officer_service_rows` emits `on_demand` from roster `type`
  (consultant→True), keeps `schedule=keepalive`. Doctor §1 carries a trailing `on_demand` TSV
  column; a not-loaded on-demand consultant → `skip`, not `dead`.
- **#57 `cabinet/scripts/load-preset.sh`:** derive the work-store conn string from `cabinet/.env`
  when the process env is empty (Mac-native path writes it only to the FILE). grep/cut, quote-
  tolerant, never `source`; both `psql` calls in the block use the derived `$CONN`.
- **#60 `cabinet/scripts/generate-plists.py`:** officer plists prepend `$HOME/.local/bin` to PATH so
  native-installer `claude` resolves. **DEVIATION FROM SPEC (see below).**
- **#13 skill relocation:** `memory/skills/evolved/chair-front-door-loop.md` (gitignored, absent on
  fresh clone) → tracked `memory/skills/chair-front-door-loop.md` (byte-identical copy). All 6
  tracked referrers repointed (chair-preflight.sh, both cos.md, cos.txt, 2 docs — the spec listed 5;
  cos.txt was a 6th, a `.txt` the spec's grep filter missed). chair-preflight brain MCP check made
  non-fatal (optional personal memory source).

## #60 deviation — flagged for the landing session (candor)

The spec wrote `PATH_ENV = os.path.expanduser("~/.local/bin") + ":..."`. That **breaks a real
cross-pin**: `test_dependency_radar.py` pins the dependency-radar registry `service_path` to
generate-plists `PATH_ENV` via a regex expecting a plain `PATH_ENV = "<absolute literal>"`, and the
radar validator (`dependency-radar.py:312`) requires every segment absolute. A user-specific
`~/.local/bin` cannot live in a tracked, captain-agnostic, absolute-dirs registry, and reconciling
it would mean weakening that invariant across `dependency-radar.py` + `test_dependency_radar.py` +
registry + runbook — files an in-flight lane actively owns (RESUME-BOARD / task board).
Resolution: keep `PATH_ENV` the exact captain-agnostic absolute literal (radar cross-pin stays
GREEN, zero cross-lane collision) and prepend `$HOME/.local/bin` in the officer **wrapper**, where
bash expands `$HOME` per-user at boot. Verified: `test_dependency_radar.py` green; no test pins the
wrapper string (`git grep 'set -a && source cabinet/.env' -- '*.py'` empty outside the generator).
Known nuance to hand off: the radar still models the launchd literal PATH, so a `claude` installed
*only* in `~/.local/bin` (no brew symlink) reads a conservative RED on the radar even though the
wrapper makes officers work — the radar's remedy (symlink into `/opt/homebrew/bin`) remains valid
belt-and-suspenders. A future radar-lane change could teach the probe about `~/.local/bin`.

## Tests added (all `.py`, CI-collected — `.sh` would be invisible to `pytest cabinet/scripts/tests`)

`test_setup_mac_pep668_fallback.py`, `test_doctor_fresh_hatch_green.py` (hermetic fixture root +
isolated HOME + closed Redis port), `test_load_preset_workstore_schema.py`, `test_plist_path_local_bin.py`,
`test_portfolio_chair_resources.py`, and 4 new cases + 3 updated exact-match assertions in
`test_lib_roster.py`. Deviation from the spec's `.sh` naming is deliberate: CI runs
`pytest cabinet/scripts/tests` (only `test_*.py` collected); `.sh` tests would never run.

## Risk / blast-radius notes

- `lib_roster` `on_demand` key is additive; verified other consumers read specific keys only
  (generate-services-officers, deploy-mac.sh, cabinet-deploy.sh, test-recovery.sh) — full suite green.
- No schg path edited. `mcp-scope.yml` germline collision is READ-only here; deeper product-lane
  prune remains a Captain HANDBACK (unchanged).
- bash 3.2 footgun paid: an apostrophe inside a quoted heredoc within `$(...)` breaks `bash -n` —
  the §5 comment is kept apostrophe-free.

## Verification

- New/updated tests: 28 pass. Full `cabinet/scripts/tests`: green except one PRE-EXISTING failure
  (`test_evidence_seam_bypass_replay.py::...[evidence-access.sh]`) that fails identically on clean
  origin/master `8dced97b` — not introduced here.
- `bash -n` clean on all 4 edited shells. layer-sep gate: 0 new violations. docs-sweep: 13 pass.
  `git grep evolved/chair-front-door-loop` clean across all tracked files.
