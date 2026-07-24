# Review — feat/cog4-w6-e2 cp1 (COG-4 W6 e2: C4 COMPOSE + RETIRE)

**Batch (one atomic commit):** `cabinet/scripts/cog4-organ-runner.py` (the
§9.5 composed wake vehicle, scheduler-blind) + FIVE real §4.2-shaped organ
manifests `cabinet/config/organs/{charter-shadow,judge-calibration,
prediction-calibration,preference-pairs,world-census}.yml` + the
`cabinet/services.yml` compose surgery (REMOVE the five composed rows, ADD the
one `cog4-organ-runner` row explicitly naming its manifests, RETIRE the
draft-lane row) + `cabinet/launchd/com.cabinet.draft-lane.plist` deleted +
`framework/watchdog/registry.py` `_parse_organ_manifests` per-organ floors
(§9.2 MR3) + the COG-4 census allowance bump (exact running total) + egg
expect-present rows + the NEW pre-proof battery
`cabinet/scripts/tests/test_cog4_organ_runner_real.py` + this artifact.
Contract: `docs/plans/cognitive-core-phase-4-contract-2026-07-23.md`
§9.2/§9.3/§9.4/§9.5 (+§11 census, §13 corpus law, §16 fleet inverse).
Corpus immutable: ZERO edits under existing test files (adds only).

## 1. Fleet delta (the C4 measure, N7's direction)

| measure | before | after | law |
|---|---|---|---|
| services_total | 57 | **52** | −5 composed +1 runner −1 retired; census max TIGHTENED 57→52 IN THIS COMMIT — the brief's VERIFY clause resolved by evidence: `test_pinned_repository_matches_architecture_contract` alone tolerates observed<=max, BUT `test_service_growth_mutant_fails_total_and_enabled_budgets` (and its inside-the-egg twin) REQUIRES +1 row to trip BOTH budgets, i.e. observed==max zero headroom is load-bearing; leaving 57 made the growth mutant vacuous (verified RED pre-fix), so the tighten rides the compose commit (shrink-only). e4's §9.4 done-flip tighten remains for any further shrink |
| services_enabled | 44 | **40** | the composed five were all enabled; census max TIGHTENED 44→40 (same zero-headroom law) |
| services_disabled | 13 | **12** | draft-lane retired (evidence bundle §4 below) |
| row-less template organs | 9 | **9** | fleet-truth guard green — none of the composed five had a template plist; the retired draft-lane plist was a hand-made CONCRETE plist (not a template), deleted with its row |

## 2. Pilot selection (§9.3, from the S0-ratified five) — ALL FIVE composed

Criteria per row (projection-class · no actor writes · state_ownership ·
cadence): **charter-shadow** (read policy.shadow_decision stream → one series
append/day, owns `shared/interfaces/charter-shadow-series.jsonl`, daily
05:10) · **preference-pairs** (mine correction verdicts → pairs append, owns
`shared/interfaces/preference-pairs.jsonl`, daily 05:20) ·
**judge-calibration** (measure agreement → atomic status rewrite, owns
`$CABINET_EVENT_LOG_DIR/judge-calibration-status.json`, daily 05:35) ·
**world-census** (fenced local reads → one keyframe append/day, owns
`shared/interfaces/world-chronicle.jsonl` — DISTINCT from the world-chronicle
daemon's `shared/interfaces/world/chronicle-YYYY-MM-DD.jsonl`, verified),
daily 08:15 · **prediction-calibration** (Brier joiner → one series
append/day, owns `shared/interfaces/prediction-calibration.jsonl`, daily
08:20). All five: rebuild-from-source idempotent per date, zero actor writes,
pairwise-disjoint ownership (`state_ownership_collisions` == [] over the five
manifests, test-bound), cadence-compatible (all daily; runner interval 43200s
is stricter than every absorbed period). **Excluded: none.** Every candidate
in the ratified five composes; each carries an immutable row-presence lock
that flips RED by design of this compose — routed as contradictions with
drop-in surgery (§6 below), per §13 (builders never edit tests).

Cadence note (honest behavior delta): the absorbed rows' intra-day calendar
ordering (census/prediction after the 08:05 falsifier; judge after the 04:30
regression-corpus refresh) is traded for interval wakes twice daily. Every
composed script is idempotent per date and degrades cleanly on stale upstream
inputs; the second daily wake refreshes what the first missed. The
judge-calibration "before the 06:45 curator-health watch" ordering is moot in
the repo manifest (memory-curator-health is `disabled: true`; live-fleet
drift noted §5).

## 3. Floor conservation (§9.2 COUNT+TUPLE, SF5) — pre-proven

Reference checker `lib_cog4_floors.check_floor_conservation` run over the
REAL before (master `fc51fd59` services.yml) and after texts with the five
real manifests: **violations == []** (recorded in §7 verification log).
Per-organ tuple vs the absorbed rows (all were daily-calendar: period 86400s,
derived floor `_floor_for_entry` = 93600s):

| organ | cadence (runner 43200s <= period) | threshold (<= 93600s) | probe |
|---|---|---|---|
| charter-shadow | 43200 <= 86400 | 90000 | `cabinet/cache/organs/charter-shadow/last-run.json` |
| judge-calibration | 43200 <= 86400 | 90000 | `cabinet/cache/organs/judge-calibration/last-run.json` |
| prediction-calibration | 43200 <= 86400 | 90000 | `cabinet/cache/organs/prediction-calibration/last-run.json` |
| preference-pairs | 43200 <= 86400 | 90000 | `cabinet/cache/organs/preference-pairs/last-run.json` |
| world-census | 43200 <= 86400 | 90000 | `cabinet/cache/organs/world-census/last-run.json` |

Probe design: the runner rewrites each organ's receipt ATOMICALLY on every
HEALTHY completion only (ok or declared honest_failure) — a persistently
failing organ stops stamping and trips ITS OWN floor while the shared runner
log stays fresh (the §9.2 probe law's exact intent; the receipt path shape is
the W2 floor-corpus fixture shape `cabinet/cache/organs/<name>/last-run.json`,
gitignored via `cabinet/cache/*`). Receipts were chosen over the real series
artifacts deliberately: preference-pairs' ledger only advances when NEW
Captain verdicts exist (a quiet ledger is normal, a stale receipt is not) and
judge-calibration's status path is env-dependent; the artifact-level floors
that exist stay (cabinet-doctor's chronicle >2d = DEAD probe unchanged).
Threshold 90000s (25h) = one missed/errored wake tolerated, strictly under
the absorbed 26h floor; > one 43200s wake period so a healthy cycle can never
false-page (test-bound both directions).

`registry._parse_organ_manifests` (stdlib-only narrow parser per the
survival contract, registry.py:13/:663-665; placed beside
`_parse_services_manifest`) derives ONE expectation per composed organ from
the runner row's DECLARED `organs:` list and probes each artifact BESIDE the
per-row floors in `verify_no_silent_cron_failure`; derivation failures are
LOUD problem lines (a lost floor is a page, never a skip). Cross-checked
against `lib_cog4_floors.derive_organ_expectations` over BOTH the corpus
fixture dicts (serialized) and the five real manifest files —
`test_cog4_organ_runner_real.py::TestRealDerivationCrossCheck`, green.
judge-calibration's exit-1-by-design is encoded as
`health_proof.exit_codes.honest_failure: [1]` (test-bound).

## 4. Evidence-gated retirement (§9.3 / foundry §3 L61) — draft-lane

The ONE disabled row whose L61 bundle is genuinely buildable this unit:

* **Supersession:** the Captain's 2026-07-03 act-not-draft ruling (the row's
  own notes: "superseded by the Captain's act-not-draft ruling"; the
  action-lane row carries the function). The contract names draft-lane as the
  §9.3 retirement-class example.
* **Reader inventory (clean):** generate-plists skips disabled rows; the
  watchdog excludes disabled rows from floors; NO test pins the real row
  (framework/watchdog/tests/test_registry.py's draft-lane is a SYNTHETIC
  fixture manifest; test_no_screenpipe_in_core references the
  `run_draft_lane.py` MODULE, which stays — code compaction is Phase-7 work,
  not fleet truth); nothing pins `com.cabinet.draft-lane.plist` (grep over
  tests + deploy scripts + egg manifest: zero hits).
* **Parity:** the acting function lives in the enabled action-lane row
  (run_action_lane.py is the ruled pivot of run_draft_lane.py).
* **Quiet-fallback soak:** disabled since 2026-07-04 (20 days), expected =
  "(parked — nothing asserted while disabled)"; the live box's LaunchAgents
  copy already sits as `.plist.disabled` (per the row's own notes).
* **Rehearsed rollback:** revert of this atomic commit restores row + plist
  byte-identically (compose-revert round-trip proven, §7).

**Evaluated and NOT retired (blockers named):**
* `healthchecks-drill` + `memory-curator-health` — L61 reader inventory is
  NON-EMPTY: `test_wrapper_spof_and_monitor_gating.py` pins both rows PRESENT
  with `#52` disabled_reason (row-absence errors the test). LIVE-FLEET DRIFT
  NOTED EXPLICITLY: per S0 both are LIVE-LOADED on the current box despite
  `disabled: true` — the REPO MANIFEST is the truth being edited; the live
  fleet is disposable per the 2026-07-21 ownership-on-GO and converges at the
  fresh-repo relaunch. Retirement stays available to a later unit WITH the
  corpus surgery.
* `killswitch-watchdog` — row presence hard-pinned
  (test_killswitch_watchdog.py:455-456); relaunch machinery, staged not
  superseded.
* `mission-supervisor` — STAGED (pull-only ratified 2026-07-04; enabling is a
  Captain call); its template plist pairs with the row (fleet-truth).
* `officer-lifecycle-transitions` — STAGED dark (evidence program Phase 2
  Batch B; the Batch B Captain ceremony enables it).
* `research-sweep` + `backlog-refine` — ABSENCE-DISABLE with explicit
  re-enable path (Captain's return); rows pinned present by
  test_cron_officer_targets.
* the five staged evidence-plane rows (anchor / authority transitions /
  shadow detectors / signing broker / recompute verifier) — ship-dark
  surfaces of the whole-cabinet evidence design, not superseded machinery.
  (Named generically on purpose: several of those services carry shadow-law
  zero-consumer grep proofs over the tracked tree, and this artifact must not
  register as a reference.)

## 5. Runner (§9.5) — scheduler-blind, pre-proven against the armed battery

`cog4-organ-runner.py`: loads EXACTLY the manifests its row names (declared
list; bare-name fixture refs resolve only under an explicit --manifest-dir;
path refs resolve against the services manifest's repo root); refuses
state_ownership collisions and non-periodic trigger_policy (exit 2);
entrypoint mode runs each absorbed command via /bin/bash -c with rc
classified per health_proof.exit_codes; manifests without entrypoints get the
corpus reference projection (the W2 fixture semantic), so the REAL CLI passes
the REAL invariance battery: `test_cog4_organ_runner_real.py::
TestRealRunnerCliBattery` runs it twice as a subprocess with and without a
schedule artifact injected — byte-identical behavior, cache untouched,
stray manifests never run, deterministic across runs (all green; the
retirement-condition binding for both W2 vacuity arms). fallback skip /
safe_noop = quiet degrade (the per-organ floor is the pager); escalate =
FATAL marker (JOB_ERROR_MARKERS) + exit 1. Boundary: imports
framework.organs only (allowlisted row 5); DELIBERATELY ABSENT from the
scheduler-token and schedule-store allowlists (rows 4/7) — `cog2-import-gate`
exit 0 over the tree; AST-level blindness test in the new battery.

Live-fleet note: the repo manifest is the edited truth. The five absorbed
rows' generated plists on the CURRENT box keep running until a
generate-plists + bootstrap cycle (or the fresh-repo relaunch) applies this
manifest; the scripts are idempotent per date, so double-running during the
window is harmless (per the 2026-07-21 ownership grant the live fleet is
disposable — no live-fleet action taken by this unit, launchctl untouched).

## 6. Designed corpus flips → contradictions (integrator surgery, §13)

Every flip below is PRE-PROVEN green out-of-band by
`test_cog4_organ_runner_real.py` (committed) before the arms flip; surgery
text rides the unit's contradictions[].

1. `test_cog4_organ_runner.py::TestRealRunnerCliArms::
   test_real_runner_invariance_battery` — absence tripwire REDs (CLI landed).
   Surgery: retire the vacuity skip; the binding exists at
   `test_cog4_organ_runner_real.py::TestRealRunnerCliBattery::test_real_cli_invariance`.
2. `...::test_real_runner_store_blindness` — same; binding =
   `test_real_cli_leaves_schedule_cache_untouched` +
   `test_real_cli_declared_list_never_discovery`.
3. `test_cog4_floor_conservation.py::TestRealParseOrganManifestsArm::
   test_real_derivation_arm` — hasattr tripwire REDs (function landed).
   Surgery: retire the skip; cross-check =
   `TestRealDerivationCrossCheck::test_fixture_dicts_cross_check` (+ real
   files variant).
4. `cabinet/scripts/tests/test_charter_shadow.py::test_services_row_is_scheduled`
   — row composed. Surgery: accept dedicated-row OR composed-organ: assert
   `cabinet/config/organs/charter-shadow.yml` is named by the enabled
   `cog4-organ-runner` row, its entrypoint contains `charter-shadow.py`, and
   its freshness floor derives (the §3 tuple) — deletion evidence continues
   from inside the runner.
5. `framework/learning/tests/test_preference_pairs.py::test_services_row_is_scheduled`
   — same shape (manifest `preference-pairs.yml`, entrypoint
   `framework.learning.preference_pairs`).
6. `framework/fidelity/tests/test_prediction_scorer.py::test_services_row_is_scheduled_daily`
   — same shape (manifest `prediction-calibration.yml`, entrypoint
   `framework.fidelity.prediction_scorer`; "daily" = runner interval 43200 <=
   86400).
7. `cabinet/scripts/tests/test_judge_calibration_scheduling.py` (3 of 5
   tests: `test_row_is_enabled_cron_on_daily_calendar`,
   `test_row_runs_the_existing_offline_cli`,
   `test_row_renders_through_generate_plists`) — row composed. Surgery:
   re-anchor `_row()` to the composed vehicle: the runner row is enabled kind
   cron interval <= 172800s (14-day proof stays fresh — the lock's stated
   intent; actual 43200), the judge manifest's entrypoint contains
   `cabinet/scripts/judge-calibration.py` (CLI exists, OFFLINE/NO LLM head
   pins unchanged), and the RENDER test targets the runner row (Label
   com.cabinet.cog4-organ-runner, StartInterval, ProgramArguments contains
   cog4-organ-runner.py). `test_stale_future_b5_comment_is_gone` +
   `test_cli_*` stay green untouched.

No other suite state changes: world-census has no row lock;
`test_wrapper_spof_and_monitor_gating` (renders the full manifest through the
real generator — proves the runner row renders) stays green;
`test_cog4_measurement.py`'s real-baseline vacuity arm does NOT flip (its
trigger is the e3 baseline artifact, absent).

## 7. Verification log (this unit, at commit time)

* Census: `--check` green after the allowance bump — framework lines 66548
  observed == effective max (base 65012 + COG-4 allowance 1536, exact
  running total; +139 = the registry floors); modules 236 unchanged;
  services 52/52 + 40/40 observed==max (maxima tightened in-commit, §1);
  action_types 30. The growth-mutant test + its egg twin re-verified green
  post-tighten.
* `cog2-import-gate.py` exit 0; layer-sep green (new=0); egg-export green
  with the six new expect-present rows; generate-plists renders the manifest
  (runner plist included, screenpipe monitors still excluded).
* Full `cabinet/scripts/tests` sweep + the framework suites: every non-green
  vs base is one of the §6 designed flips (counts in the unit's
  StructuredOutput claims).
* Floor conservation: `check_floor_conservation(before=fc51fd59 text,
  after=this tree, runner=cog4-organ-runner, composed=the five, organs=the
  five real manifests)` == [] (§3).
* Compose-revert round-trip (§16 fleet inverse): `git revert --no-commit
  <this commit>` restores services.yml + registry.py + the five rows + the
  draft-lane row/plist byte-identically (then aborted) — the atomic-commit
  inverse works.
* HEAD-bytes parse: `git archive HEAD` services.yml + the five manifests
  parse (PyYAML) with the §1 counts.

Model: authored on Fable 5 (Fable-for-execution per the Captain 2026-07-23
calibration — THE live-behavior unit). Per the 2026-07-07 full-autonomy
grant + the 2026-07-20 cognitive-masterplan continuous grant; fleet
composition/retirement additionally per the 2026-07-21 ownership-on-GO.
