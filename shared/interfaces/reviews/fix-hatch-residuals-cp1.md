# Review artifact — fix/hatch-residuals cp1

FW-019 batch review for the three pre-launch-audit fresh-hatch residuals
closed on this branch (re-verify delta 2026-07-19, residuals #52 / #60 / #27).
The diff crosses 300 lines almost entirely because #27 copies five
byte-identical org-discipline scenario files into the portfolio preset; the
hand-written change is small (chair-preflight 13, officer-launch 7, gate 9,
tests ~150, README 25).

## What changed

- **#52 chair-preflight** (`cabinet/scripts/chair-preflight.sh`): check #7
  treats screenpipe as the optional personal source it is — absent
  `~/.screenpipe` prints a `➖` info line (neither pass nor fail) instead of a
  hard `fail`, so a fresh / non-author box no longer reads "NOT READY"
  forever. A present-but-unsilenced screenpipe still `fail`s (real two-channel
  Telegram conflict). Mirrors the file's own check #4 optional-source pattern.
  Machine name "chair" retained (First Mate is display-only, machine ids
  frozen).

- **#60 officer PATH** (`cabinet/scripts/start-officer-mac.sh` + new
  `cabinet/scripts/tests/test_officer_launch_local_bin.py`): the officer
  launch line's `env -i ... PATH="$PATH"` → `PATH="$HOME/.local/bin:$PATH"`
  so the native-installer `claude` (its default location) resolves under
  launchd's minimal service PATH. Twin of the daemon-plist fix
  (`generate-plists.py`, `test_plist_path_local_bin.py`). Content-only change
  to a germline-locked file (no boundary/`FILES[]`/`GERM_PATH_RE` edit);
  lands to master normally and a fresh hatch locks it fresh from master (no
  ceremony needed).

- **#27 measurement seed** (`framework/learning/self_improvement_loop.py`,
  `presets/portfolio/measurement/**`, two new tests): the self-improvement
  scenario-validation gate `_run_scenario_evals_for_validation()` now
  **fails closed** on zero role/learning scenarios (`else True` → `else
  False`), mirroring the already-landed #21 shells-gate fix. The default
  **portfolio** preset is seeded with the five generic org-discipline
  scenarios (byte-identical to the work seed) so it measures for real instead
  of vacuously passing. `personal` (minimal do-not-activate placeholder) is
  deliberately left unseeded — fail-closed surfaces it loudly if it ever
  activates, which is more honest than papering it.

## Adversarial review — 3 fresh-context reviewers (Opus), all SHIP

- **#52 — SHIP**: traced every branch with a faked `$HOME`; fresh box → info
  (bad=0), present+unsilenced → fail (bad=1), no path lets a live unsilenced
  screenpipe slip through as info; `➖` correctly increments neither ok nor
  bad (matches #4); `bash -n` clean, no `set -e` abort risk.
- **#60 — SHIP**: verified the crux — `$HOME`/`$PATH` expand in the calling
  shell before `env -i`, the assignments survive the `-i` scrub, and the
  downstream one-shot launcher never re-sets PATH; prepend wins; germline
  content-only; test mutation-proven (drop-prepend → red, single-quote
  variant → red).
- **#27 — SHIP**: ran real discovery (portfolio seed → `run_all("role")`
  returns the 2 role scenarios, gate non-empty → measures); scenarios grep
  clean of work roster/product names; `else False` flips no currently-green
  path (only `personal` runs the loop unseeded, and its fail-closed is
  deliberate + loud, strictly better than pre-fix vacuous auto-apply); ran
  `load-preset.sh` against portfolio's scenarios-but-no-role_evals shape →
  exit 0, clean; tests mutation-proven; no drift/egg test breaks and the seed
  reaches fresh egg-hatches. Reviewer-recommended follow-up (portfolio↔work
  byte-identity drift pin) was **applied** this pass
  (`test_portfolio_scenarios_byte_identical_to_work`).

## Verification

- New tests: 16 pass (validation-gate fail-closed 6, preset-seed parity 4,
  officer-launch 1 — plus the pre-existing gate tests).
- Regression: `framework/learning/tests` 296 pass, `framework/measurement/tests`
  + `test_load_preset_measurement_seed.py` + `presets/work/measurement` 47 pass.
- `bash -n` clean on both shell scripts; `python3.12` parse clean.

## Noted, out of scope (not fixed here)

- `presets/personal/README.md` is stale (says the loader "fails clean —
  preset not populated" but `personal/preset.yml` now exists). Pre-existing,
  unrelated to these three fixes — flagged for a one-line follow-up, not a
  drive-by.
