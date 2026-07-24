# COG-4 §12.3/§15 FROZEN REVIEW — Composable Cognitive Organs + Deterministic Shadow Scheduler

**Scope:** the COG-4 surface at commit `f62094f7c6ee419db20df3d5445a89f5258467bb` (`feat/cog4-w6-e4`,
"COG-4 W6 e4: census done-flip tighten (§9.4/§11) — record final phase actuals, N7 machine-pinned",
over master `fc51fd59`; W1-W5 already on master, W6 e1-e4 = `6502f597`→`b4bc2c34`→`2ab7d607`→`2338d6c9`→tip):
`framework/projection/{__init__,kernel}.py`, `framework/scheduler/{__init__,model,snapshot,fold,serve}.py`,
`framework/organs/{__init__,registry,descriptor}.py`, `framework/schemas/cognitive-trajectory.v2.schema.json` +
the `framework/evolution/contracts.py` version dispatch, `framework/watchdog/registry.py` `_parse_organ_manifests`,
`cabinet/config/boundary-manifest.yml` + the converted engine `cabinet/scripts/cog2-import-gate.py`,
`cabinet/scripts/{cog4-snapshot,cog4-schedule,cog4-dispatch-shadow,cog4-parity,cog4-measure,cog4-organ-runner}.py`,
the W6-e2 compose (`cabinet/services.yml` + 5 organ manifests under `cabinet/config/organs/`), the phase twins
(`verify-cognitive-phase4.sh`, `cognitive-phase4-review-scope.py`, `cognitive-phase4-rollback-rehearsal.py`,
rollback manifest `docs/plans/cognitive-core-phase-4-rollback-manifest-2026-07-24.yml`), the `test_cog4_*`/`lib_cog4_*`
corpus, and the egg-export manifest extension.
**Reviewer:** frozen fresh-context Fable panel (clean-room clone off the canonical remote, zero prior-session
context; 2026-07-24). The F1 lesson bound this review: every public entry point of every new serve surface was
attacked with the panel's OWN tamper code, never only the suite's.
**Contract:** `docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` rev 1 (§15 standing questions answered
below, every one).
**Method:** every claim is bound to bytes (`file:line`) or a run executed by this panel (`python3.12`). No doc or
comment was trusted un-run. 74 independent panel probes + the full committed batteries; the clone worktree was
byte-clean (`git status --porcelain` empty) after every run.

Reviewed-Scope-Digest: 95e6ea8bf1288655a488342ea2675e515d7332829c2ff623664db5cd23a10c42
(As frozen, the panel bound the DECLARED W1-W5 scope: `cognitive-phase4-review-scope.py` EXPECTED_SCOPE
deliberately excluded the e2/e3 sibling surfaces (cog4-organ-runner.py, cog4-measure.py, organ manifests,
their out-of-band tests, the FW-019 sibling artifacts) pending the landing integrator's PAIRED extension of
the §16 rollback manifest + EXPECTED_SCOPE in the same commit — `resolve_scope()` fails closed on any
one-sided edit, and the digest is re-bound at landing per the phase-3 precedent. The e2/e3 surfaces
themselves WERE fully reviewed by this panel; only the mechanical digest scope awaited the pair-extension.)
(Re-bound at the W6 landing, 2026-07-24 — the cp3 precedent, a MECHANICAL-DELTA re-bind, not a restamp.
The panel's original digest was d6625b82fc969ce9958e3eebcb96b58c4c6483cf5e3f14fb6cce8908f086ac6e, binding
tip f62094f7. Four landing commits moved it: (1) 48028427 committed THIS artifact (excluded from the digest
but named in the manifest remove list); (2) 93b26f74 the §13 corpus surgery — the panel's OWN named
discharge of the 5 designed flip-arms, each retired-live per its retirement text, pre-proven green
out-of-band by the panel-reviewed test_cog4_measure_baseline.py + test_cog4_organ_runner_real.py; (3)
eefc9c11 the §16/EXPECTED_SCOPE pair-extension, which pulled the ALREADY-PANEL-REVIEWED e2/e3 surfaces into
the digest scope (+ the P5 egg tidy rows; the L61 draft-lane plist DELETION declared as
out_of_phase_in_range residue — a deleted-at-HEAD path cannot be digest-bound); (4) 5d1547c0 the wave
FW-019 batch proof + its own pair rows. Mechanical deltas only — ZERO behavior bytes changed beyond the
§13 corpus surgery itself. Re-verified on the final bytes: full battery armed 690 passed 1 declared skip /
unarmed 689 passed 2 declared skips (ZERO failures — the designed interim discharged); rollback rehearsal
PASS with the compose-revert arm ARMED (the 12-file sibling residue resolved); egg battery 58 passed 1
declared skip; verify-cognitive-phase4.sh full green end-to-end after this re-bind. The panel verdict
stands. MOVED AGAIN same day (2026-07-24, 3ce64a36… → the value above) by the first-PR-CI root-cause
commit 429fa17b — the REMAINING e2-routed §6.4-6.7 sibling-suite re-anchors (charter-shadow /
judge-calibration / preference-pairs / prediction-scorer locks re-anchored to the composed vehicle; these
four files join restore_from_baseline + EXPECTED_SCOPE, the pair-extension that moved the digest), the
evidence-proof allowlist row for this phase's rollback manifest (that proof file is out-of-phase, unbound
by this digest), and the wave artifact's §6 addendum. Zero behavior bytes beyond that routed §13 surgery;
the full twin re-ran green end-to-end after this second re-bind. The panel verdict stands. FINAL MOVE
(2026-07-24, e2c35aa9… → the value above): the post-flip range-seal commit pinned the manifest's
done_flip_sha to the ledger flip commit c58d4a57 (the §16 retirement condition, the phase-3 e7f95d5a
retrofit shape) — a one-line YAML pin inside the scope; zero behavior bytes; the W6 merge dfb1a00e and the
flip c58d4a57 each carried all 7 CI jobs green. The panel verdict stands.)

---

## §15 standing questions — findings

### Q1 — Does any serve path return rows it did not hash in the same read?

**NO.** `framework/scheduler/serve.py` has exactly ONE public entry, `serve_schedule` (:126), routing through
`framework/projection/kernel.py::verified_single_read` (:223-285): the store is read ONCE (`read_jsonl_rows`,
:271 "the ONE read"), the chained hash re-derived from the RE-PARSED rows, bound to the manifest, and the
returned rows ARE the hashed rows. Panel probe (own code, store built end-to-end via the real
`cog3-rebuild.py`→`cog4-snapshot.py`→`cog4-schedule.py` CLIs in a tmp root): served rows == disk rows ==
`model.schedule_rows_hash` input; tampered row / REORDERED-but-identical rows (file-order chain, model.py:126-134)
/ forged counts / tampered+missing snapshot record / partial epoch key-set / snapshot echo forgery — 8/8
tamper classes `ScheduleRefused`, 1/1 pristine control ANSWERED. Package roots are import-inert in a fresh
subprocess (forbidden closure EMPTY; loaded = framework{,.organs,.projection,.scheduler} only). The serve
module's public surface is {`serve_schedule`, `ScheduleRefused`} + its imports — no second loader exists;
`cog4-schedule.py` reports THROUGH the loader (:69 "F1: report via the loader"); `cog4-dispatch-shadow.py`
serves through it (`run_shadow_dispatch` :569) and its availability probe returns no rows (Q4/F2).

### Q2 — Does any manifest-absent key skip a limb?

**NO.** The rows-hash key is MANDATORY-PRESENT (kernel :264-269): panel-deleted `schedule_rows_hash` AND
empty-string value both REFUSE ("MANDATORY-PRESENT (§6.3)"); the objectives `is not None and` skip-hole is
closed for this store. Epoch completeness limb refuses a partial wake-input key SET (serve.py:70-72, panel
probe). Snapshot builder: absent cortex `belief_store_hash` / objectives `graph_rows_hash` REFUSE
(snapshot.py:100-104/128-132 — "never an invented wake input"). Dispatcher: manifest-absent
`freshness_needs` => `freshness_underivable` REFUSE; absent `idempotency` => `idempotency_underivable`
REFUSE; missing organ manifest => `organ_manifest_missing` REFUSE (all panel-probed, zero would_dispatch).
Descriptor: absent block/member/idempotency discipline => `DescriptorRefused` (8 panel refusal probes incl.
the unknown-key fail-closed subset guard, descriptor.py:121-126).

### Q3 — Can any non-declared input (env/clock) reach the fold?

**NO.** Grep over `framework/{scheduler,projection,organs}`
(`os.environ|getenv|datetime.now|utcnow|time.time|getcwd|Path.cwd|expanduser|gethostname|random`): zero code
hits (three docstring prose mentions only). `build_snapshot` takes every input as a declared parameter
(snapshot.py:107-115); `validate_snapshot` recomputes SF2 family hashes + the registry hash from the
snapshot's own data (model.py:207-215). N1 panel probe: 3 subprocess rebuilds under PYTHONHASHSEED 0/1/987654321
from the same snapshot file → identical `schedule_rows_hash` (a9def50c37d7…). AST pins green in the battery
(`test_cog4_scheduler_ast_pin.py`); `test_cog4_sim_fold.py` purity mutants green.

### Q4 — Can the dispatcher execute anything?

**NO.** AST trace over `cog4-dispatch-shadow.py` + the whole planner tree: zero
subprocess/socket/http/urllib imports, zero `os.system/popen/exec*/spawn*` attributes. The CLI writes ONLY
the shadow log (O_EXCL lock + O_EXCL tmp + fsync + os.replace, :625-658). Hermetic mode never calls
`_act_with_undo_gap` (:301 live-only guard). All SIX §7.3 limbs fire in order — panel per-limb fixtures
(violate limb k, satisfy k−1): (1) tamper=>`serve_refused`/`rows_hash_mismatch` rc2 zero records; absent
key=>`rows_hash_key_absent`; missing store=>`safe_fallback` rc4, fixed safe schedule echoed, NEVER permission;
(2) any live-vs-recorded difference incl. recorded-exists/live-null AND live-extra-key (symmetric union,
:583-587) => `stale_snapshot` rc2; (3) `authority:ceiling` / `authority:undo_gap` / `authority:propose_only`
fail-safe, allow-set {auto, act_with_undo, auto_with_veto_window, notify_after} (:166-167); (4)
`budget_overflow` with `planner_admitted: true`; (5) `stale_organ:age=…` + `staleness_flagged`, never
auto-permission; eligibility rechecks (crashed-vs-unhealthy health classification :215-222, fallback honored,
dependency/capability unavailability with ORIGINAL identity); (6) re-derived idempotency key (row-carried keys
never trusted), replay across runs refuses `idempotency_replay` (panel double-run probe). §7.4 pointer
tripwire: a pointer created under a scratch-HOME `~/.cabinet/state/cog4-dispatch-pointer` => rc5
`pointer_tripwire`, zero records, on the DEFAULT path (expanduser proven live); no pointer => normal rc0. The
live machine carries no pointer file. Import pin `test_cog4_dispatch_ast_pin.py` green.

### Q5 — Can `capability` reach any verdict predicate?

**NO.** `_AuthorityJoint.check` (dispatch :257-309) reads ceiling/action_type/risk_class/undo_contract only;
grep for capability-keyed predicates over organs+scheduler+dispatcher: zero. Panel probe: two operations with
identical declared members resolve IDENTICAL enforcement tuples under distinct capabilities
(descriptor.py resolution is identity lookup). The corpus capability-blindness harness
(`test_cog4_exit_fixtures.py::_assert_capability_blindness`, capability-keyed mutant REDs) ran green per
cabinet across all three non-software fixtures.

### Q6 — Does any path grow ACTION_TYPES or bypass the adapter parity?

**NO.** `len(ACTION_TYPES) == 30` incl. `ambiguous`; the consequence-schema closed enum == ACTION_TYPES+null
(byte-mirror probe); census `central_action_types 30 <= 30`; v1 trajectory schema byte-identical to master
(`git diff --quiet` clean); the §16 protected union (classifier/matrix/policy_engine/matrix-yml/consequence
schema/v1 schema/HUMAN_PHRASES both mirrors/graduation/cog3 AST pin/extension gate pair) verified
byte-unchanged over baseline..HEAD by the rehearsal's per-path diff leg (that leg PASSED; the rehearsal's
later red is the sibling-residue ratchet, Q10). Parity: legs independent BY CONSTRUCTION
(`cog4-parity.py` leg b: own declarer scan `_leg_b_owner` :211 + own raw merge `_leg_b_declared` :225; source
between `action_types_leg` and `_leg_tuple` never calls `resolve_descriptor`/`descriptor_leg` — byte-probe).
Panel-seeded divergent manifest (declared `spend` vs matrix-derived `read_only_dispatch`) => exit 2, the
divergence RECORDED in the written record with both legs; flat operation id => setup exit 3 (the
collision guard — load-bearing while CG-33 schema validation is parked); zero-operations => exit 3 (no
vacuous green); the REAL composed pilot manifests => exit 0, zero divergent tuples. Trajectory v2: version
dispatch decided BEFORE v1 checks (contracts.py:265-275, `_is_v2_record` exact-literal marker); a namespaced
id in the effect compat `action_type` FAILS the v2 pattern (`compatActionType` excludes `/` — panel probe:
schema.pattern violation at `$.effects[0].action_type`); forged `v3` and absent versions fall to the FROZEN
v1 path and fail; the full evolution contracts suite green (47 passed).

### Q7 — Does composing rows drop a floor or LOOSEN its (cadence, threshold, probe) tuple?

**NO — recomputed by this panel from the pre-compose tree.** Pre-compose services.yml (master `fc51fd59`):
57 rows / 44 enabled; the five absorbed rows (charter-shadow, judge-calibration, prediction-calibration,
preference-pairs, world-census) all ENABLED, all daily. Post: 52 rows / 40 enabled; runner row
`interval_s: 43200` ≤ every absorbed 86400 period (cadence leg). Threshold leg: every organ
`max_staleness_seconds` 90000 ≤ the absorbed row's `_floor_for_entry` floor 93600 (all five, computed via the
REAL registry functions against the pre-compose text). Probe leg: five DISTINCT per-organ
`cabinet/cache/organs/<name>/last-run.json` receipt artifacts — never the shared runner log; the runner stamps
receipts only on HEALTHY completion (ok|honest_failure — judge-calibration's exit-1-by-design encoded as
`health_proof.exit_codes.honest_failure`), so a silent organ trips ITS OWN floor. COUNT leg: the REAL
`_parse_organ_manifests` over the post manifest derives exactly the 5 floors, zero problems; disabled rows
derive none (belt-and-braces re-filter, registry.py). `test_cog4_organ_runner_real.py`
TestRealDerivationCrossCheck + TestRealComposeForwardTree green (incl. thresholds-do-not-loosen and
per-organ-probe cells). Draft-lane: the ONE disabled-row retirement (L61 evidence bundle in
`feat-cog4-w6-e2-cp1.md`), row + hand-made plist deleted together.

### Q8 — Can the organ-runner observe the schedule store at all?

**NO — three independent ways.** (a) Behavioral, panel's own variant on the REAL CLI: a full schedule
artifact set injected under the runner's run-root `cabinet/cache/scheduler/` => byte-identical behavior JSON
vs the clean run, and the injected store byte-untouched after the wake. (b) Static: zero
`framework.scheduler` imports and zero store-path literals in the runner source (the two grep hits are
docstring prose :13/:70); `test_cog4_organ_runner_real.py::test_real_cli_source_is_statically_scheduler_blind`
green. (c) Boundary DELIBERATE ABSENCE bites: panel scratch-tree mutants — runner importing
`framework.scheduler` REDs `UNALLOWLISTED_SCHEDULER_IMPORTER`; runner naming the store (assembled token)
REDs `FORBIDDEN_SCHEDULER_DATAPLANE` (rows 4/7 `deliberately_absent`). Row→manifest association is DECLARED
(`organs:` block, services.yml:946-951; bare-name discovery refused without `--manifest-dir`).

### Q9 — The boundary ENGINE + exit gates N1-N9 (table below).

Engine: committed-tree run OK rc0; legacy suites `test_cog2_import_gate.py` + `test_cog3_import_gate.py`
116 passed (byte-compat + completeness invariant + every legacy mutant); per-row generated mutants
(`test_cog4_boundary_rows.py`) green in the battery; panel's own six mutants all RED with the row-correct
rule ids (runner→scheduler, runner→store, frontdoor→scheduler, scheduler→authority reverse, organs→frontdoor
reverse MF-A1, un-curated kernel importer).

### Q10 — Anything else that would refuse ship?

**No must-fix.** Full COG-4 battery: armed `5 failed, 687 passed, 1 skipped`; unarmed `5 failed, 686 passed,
2 skipped` — ALL five failures are DESIGNED retire-me flip signals ("<artifact> has LANDED — retire this
vacuity skip") awaiting the landing integrator's §13 corpus surgery: the floor derivation arm
(test_cog4_floor_conservation), the verify-twin + real-pilot measurement arms (test_cog4_measurement), and
the runner invariance + store-blindness arms (test_cog4_organ_runner). Every flipped property is pre-proven
GREEN out-of-band: `test_cog4_measure_baseline.py` 16/16; `test_cog4_organ_runner_real.py` (e2's routed
drop-in) full green. Both skips declared (wall-clock posture skip, armed by the twin; CG-33 germline-window
vacuity skip — the §4.5 amendment is FILED, window unopened, PARK marker present). `verify-cognitive-phase4.sh`:
every pre-battery leg green — `cog4-measure --check` ARMED within bound ("proxies EXACT, wall-clock <= bound"),
review-absent skip-loud branch, pointer tripwire clean, `verify-cognitive-architecture.sh` 76 passed,
census PASS at the e4-TIGHTENED maxima (`services_total 52<=52`, `services_enabled 40<=40`,
`central_action_types 30<=30`, modules `236<=236`, lines `66548<=66548` — zero headroom, observed==max),
layer-sep OK (new=0); overall exit 1 at the battery leg = the documented pre-surgery interim, and the
ROLLBACK REHEARSAL is likewise DESIGNED-RED at HEAD (12-file e2/e3 sibling residue — the §16 manifest's
`sibling_landing_note` + e3 cp1 §6 declare it; the strict inverse-diff equality is the completeness ratchet
WORKING; its protected-surface and A13 legs passed before the ratchet). The §16/scope pair is
force-coupled: `resolve_scope()` fails closed on a one-sided edit. Standalone: A13 parity OK (351 rows);
egg battery 58 passed + 1 declared machine-shape skip (twin delete + expect-absent pairs for all three
phase-4 twins; expect-present for parity/dispatch/runner/measure CLIs + the tracked parity record + S0
baseline); anti-phantom probe — `COG4_ENFORCE_BOUND` is the only COG4_* flag in the twin and has live
non-twin consumers (cog4-measure.py, test_cog4_measurement.py, test_cog4_measure_baseline.py); the e3
claim-surface fix (2338d6c9) removed the phantom `--mode` flag. All four PARK markers exist (officer-plist
cleanup W1-u3; cortex serve adoption W3-u3; objectives kernel adoption W3-u4; organ schema validation W4-u1).
Fleet truth: rowless template-organ set pinned to EXACTLY the 9 (conservation guard green; officer-leakage
subset tolerant pending parked u3). N8: the three non-software cabinets (garden-delivery extended +
harbor-warehouse + care-rota, MR4) ran end-to-end through the REAL CLIs in the battery with the enum-growth
walls asserted and the operation-name-authority mutant exercised per cabinet.

---

## Findings register

| id | severity | finding | file:line | disposition |
|---|---|---|---|---|
| P1 | NOTE | Shadow-log replay window: `replay_keys` are read BEFORE `append_shadow_log`'s O_EXCL lock, so two dispatchers racing one log could each record `would_dispatch` for the same idempotency key (the log itself cannot corrupt; single-process replay refusal panel-proven). Zero effect surface exists this phase. | cog4-dispatch-shadow.py:858-877 vs :625-658 | Recorded; MUST be folded into the future cutover amendment's requirements (read+check+append under one lock) before any dispatch becomes real. Not ship-blocking in shadow. |
| P2 | NOTE (as designed) | After a `ScheduleRefused`, `_classify_refusal`/`_probe_availability` re-read store bytes to CLASSIFY the refusal (availability vs integrity). No rows are served from the probe; a raced re-read degrades conservative (`store_corrupt`). Documented in the CLI header. | cog4-dispatch-shadow.py:315-356 | As designed; recorded so the second read is never mistaken for a serve path. |
| P3 | INFO | `framework/organs` imports third-party `yaml` — a declared allowance in the organs package pin (stdlib \| yaml \| internal), unlike the stdlib-only kernel/watchdog surfaces; the canonical-bytes stdlib replica is parity-pinned against the kernel. | framework/organs/registry.py:54; test_cog4_organs_package.py:622 | As designed (module docstring states the row-6 rationale). |
| P4 | INFO | Designed interim at this tip: 5 corpus flip-arms RED + rollback rehearsal RED (sibling residue) + review-scope EXPECTED_SCOPE excludes e2/e3 surfaces; verify twin exits 1 overall. All declared in-tree with forcing functions; discharge = the landing integrator's §13 surgery + §16-manifest/EXPECTED_SCOPE paired extension + review re-freeze/digest re-bind. | verify-cognitive-phase4.sh:14-22; rollback manifest sibling_landing_note; e3 cp1 §6-7 | The integrator's named move at landing; this panel's verdict binds the reviewed bytes. |
| P5 | INFO | `cog4-snapshot.py` and `cog4-schedule.py` have no `expect-present` egg lines (they ship by default; the other four cog4 CLIs + records are asserted) — consistency nit vs the cog3 expect-present precedent. | cabinet/scripts/egg-export-manifest.txt:489-520 | Optional tidy at landing; egg battery green either way. |

## N1-N9 exit-gate table

| gate | mechanical proof | run + result |
|---|---|---|
| N1 determinism | panel triple: 3 subprocess rebuilds × PYTHONHASHSEED {0,1,987654321} from one snapshot → identical chained hash; delete→rebuild = the kernel rollback grammar; file-order chain refuses reorder | PASS (panel probe + sim-fold battery green) |
| N2 starvation | declared bounds are snapshot inputs (organ `starvation_bound` else scheduler_policy default, fold.py:99-107); sim-7 battery | PASS (battery) |
| N3 forged/stale | tamper/absent-key/reorder/counts/snapshot-binding all REFUSE at serve; stale/null/extra-key symmetric union REFUSES at dispatch | PASS (8 serve + 3 dispatch panel probes) |
| N4 budget | `budget_overflow` at dispatch though planner admitted (`planner_admitted: true`) | PASS (panel probe) |
| N5 authority | ceiling/undo-gap/propose_only/gated refuse via the pinned read-only joint; allow-set exact | PASS (panel probes + exit fixtures) |
| N6 latency/cost | armed `cog4-measure --check` vs the tracked S0 baseline within bound; proxies EXACT always-on; `COG4_ENFORCE_BOUND` consumers live (anti-phantom probe) | PASS (verify leg + probe) |
| N7 service-retirement | 57/44 → 52/40 recounted by panel parser; census maxima TIGHTENED to actuals (52<=52, 40<=40, observed==max); fleet-truth conservation green (rowless == the pinned 9) | PASS |
| N8 three non-software cabinets | garden-delivery (extended) + harbor-warehouse + care-rota end-to-end via real CLIs; zero new central members (30 pinned, mirrors byte-intact) | PASS (battery + panel walls) |
| N9 parity | real pilot manifests → exit 0 zero divergent tuples; seeded divergence exit 2 + recorded; legs independent at bytes; tracked record gated by test_cog4_parity_record.py | PASS |

## Command log (this run)

1. clone canonical remote + checkout `f62094f7c6ee419db20df3d5445a89f5258467bb` (chain verified over master fc51fd59)
2. `verify-cognitive-phase4.sh` full → N6 armed within bound; census PASS (52/40/30/236/66548 observed==max); layer-sep OK; battery `5 failed 687 passed 1 skipped` (the 5 = designed flip-arms) → exit 1 (documented interim)
3. unarmed battery → `5 failed 686 passed 2 skipped` (both skips declared)
4. `cog2-import-gate.py` → OK rc0; legacy engine suites → 116 passed
5. A13 heredoc → OK 351 rows; `test_egg_export.py` → 58 passed 1 declared skip
6. `cognitive-phase4-rollback-rehearsal.py` → protected-surface + A13 legs PASS, then DESIGNED-RED on the declared 12-file e2/e3 sibling residue (completeness ratchet)
7. panel probe battery 1 (31): real-CLI store build; 8 serve tamper classes REFUSE + pristine control; dispatch limbs 1-6 per-limb fixtures; pointer tripwire under scratch HOME (rc5) + clean run (rc0); no-subprocess AST trace; import-inertness (subprocess re-probe)
8. panel probe battery 2 (43): 8 organ refusals + collision + capability-blindness + registry refusals; trajectory v2 dispatch/namespaced/forged/absent + v1 suite 47 passed; parity divergence rc2 + record / flat-id rc3 / vacuity rc3 / real pilot rc0 / leg-independence bytes; 6 boundary mutants RED with row-correct ids; runner injection byte-identical + store untouched; N1 triple; census recount; floor COUNT+TUPLE recompute; anti-phantom flags
9. panel sweep 3: A-M6 grep clean; freshness/idempotency/manifest underivable refusals; ACTION_TYPES walls; egg lines; PARK markers ×4; draft-lane plist gone; v1 schema byte-untouched; worktree clean
10. `cognitive-phase4-review-scope.py --print` → `d6625b82fc969ce9958e3eebcb96b58c4c6483cf5e3f14fb6cce8908f086ac6e`

## Must-fix list

**None.** The five corpus flip-arms + the rehearsal sibling-residue red are the DOCUMENTED pre-surgery
interim (pre-proven green out-of-band), discharged by the landing integrator's §13 corpus surgery + the
force-paired §16-manifest/EXPECTED_SCOPE extension + review re-freeze; P1 binds the future cutover
amendment, not this phase.

Verdict: PASS
