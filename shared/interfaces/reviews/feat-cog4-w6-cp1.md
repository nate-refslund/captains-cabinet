# FW-019 batch proof — feat/cog4-w6 (COG-4 W6 exit wave, landing 2026-07-24)

The W6 landing integrator's batch artifact: the exit wave that ends the
COG-4 build. Branch `feat/cog4-w6` from `origin/feat/cog4-w6-e4` — PURE
ancestry over master `fc51fd59`, no cherry-picks.

## 1. Unit chain (all per-unit review artifacts committed in-branch)

| unit | commit | content | proof |
|---|---|---|---|
| e1 | `6502f597` | phase twins — verify-cognitive-phase4.sh + review-scope + rollback manifest/rehearsal (C1 born-closed, §16 carve-out) | feat-cog4-w6-e1-cp1.md |
| e2 | `b4bc2c34` | C4 compose + retire — five projection rows -> one scheduler-blind organ-runner (per-organ floors COUNT+TUPLE) + draft-lane retirement (L61) | feat-cog4-w6-e2-cp1.md |
| e3 | `2ab7d607` + `2338d6c9` | §10 latency/cost measurement — cog4-measure.py + S0 baseline + armed twin (MR2, phantom-M6 closed); claim-surface fix (phantom `--mode` dropped) | feat-cog4-w6-e3-cp1.md |
| e4 | `f62094f7` | census done-flip tighten (§9.4/§11) — final phase actuals recorded, N7 machine-pinned (52/52, 40/40, observed==max) | sub-threshold commit (no artifact — FW-019 only trips >300 lines) |

## 2. Frozen §12.3/§15 panel review — PASS

Frozen fresh-context Fable panel, clean-room clone at tip `f62094f7`
(2026-07-24): **VERDICT PASS, zero must-fix findings**. 74 independent
adversarial probes + the full committed batteries; every §15 standing
question answered with evidence; the 6 designed pre-surgery REDs confirmed
as the declared interim with named discharge. Artifact committed VERBATIM at
the landing head: `shared/interfaces/reviews/cognitive-core-phase-4-review.md`
(landing commit `48028427`). Panel digest at freeze:
`d6625b82fc969ce9958e3eebcb96b58c4c6483cf5e3f14fb6cce8908f086ac6e`
binding tip `f62094f7` — re-bound at landing per §4 below.

## 3. Landing integrator commits (this batch)

1. `48028427` — the frozen review artifact, verbatim (git add -f; the
   reviews dir is gitignored, FW-019 artifacts are force-added by law).
2. `93b26f74` — §13 corpus surgery: the 5 designed flip-arms retired-live,
   each per its own retirement text (per §13 + the routed contradictions —
   feat-cog4-w6-e2-cp1.md §6, test_cog4_measure_baseline.py §A/§B):
   * floor-conservation `test_real_derivation_arm` -> binds the REAL
     `registry._parse_organ_manifests` end-to-end over the fixture
     manifests, cross-checked against
     `lib_cog4_floors.derive_organ_expectations` (hasattr companion
     inverted);
   * measurement `test_verify_twin_arm` -> keeps exactly the first
     assertion (the twin consumes COG4_ENFORCE_BOUND, §10.3);
   * measurement `test_real_pilot_measurement_arm` -> binds the REAL
     tracked S0 baseline: composed-manifest proxies EXACT-equal + fresh
     per-pilot p95 <= `wall_clock_bound(baseline)` via the corpus
     `wall_clock_violations`;
   * organ-runner both `TestRealRunnerCliArms` arms -> retired per e2's
     routed drop-in (cp1 §6.1-6.2): the §9.5 bindings live in
     `test_cog4_organ_runner_real.py::TestRealRunnerCliBattery` (imports
     the corpus checkers; a corpus back-import would be circular — no
     stubs left);
   * verify twin INTERIM NOTE discharged (comment-only).
3. `eefc9c11` — §16 paired sibling fold, ONE commit (the resolve_scope()
   drift check forces the pair): manifest remove += cabinet/config/organs
   (DIR) + cog4-organ-runner.py + test_cog4_organ_runner_real.py +
   cog4-measure.py + test_cog4_measure_baseline.py + feat-cog4-w6-e2-cp1.md
   + feat-cog4-w6-e3-cp1.md; EXPECTED_SCOPE += the same seven. Real-footprint
   deltas recorded in-file: the S0 baseline rides the fixtures/cog4 DIR
   entry; NO tracked runner plist exists; the e2 L61 draft-lane plist
   DELETION rides out_of_phase_in_range note (c) (retained on rollback —
   deleted-at-HEAD paths cannot be digest-bound). Plus the panel-P5 egg
   tidy: expect-present rows for cog4-snapshot.py + cog4-schedule.py.
4. THIS commit — the FW-019 wave artifact + its own manifest/scope pair
   rows (same-commit law: the artifact exists in the commit that binds it).
5. The re-bind commit (follows this one; edits ONLY the digest-excluded
   review artifact): Reviewed-Scope-Digest updated to the post-surgery
   digest + a dated administrative note (the phase-3 cp3 precedent) — see §4.

## 4. Digest re-bind (§15 review-to-bytes)

The panel digest `d6625b82…` bound the DECLARED W1-W5 scope at `f62094f7`.
The landing moved the digest MECHANICALLY: the review-artifact commit, the
§13 corpus surgery (the panel's named discharge — pre-proven green
out-of-band by test_cog4_measure_baseline.py + test_cog4_organ_runner_real.py,
both reviewed by the panel), the §16/scope pair-extension (which pulls the
already-panel-reviewed e2/e3 surfaces into the digest), the egg P5 tidy, and
this artifact's pair rows. Zero behavior bytes beyond the corpus surgery.
The FULL battery + the armed verify twin are re-run end-to-end on the final
bytes before the re-bind commit lands; the re-bound digest value + the full
provenance chain live in the review artifact's dated administrative note.

## 5. Verification (landing head, committed bytes)

* Full COG-4 battery: ZERO failures (armed; the former 5 designed REDs are
  live-green); unarmed keeps only the two declared skips (wall-clock
  posture + CG-33 germline-window vacuity).
* Rollback rehearsal: PASS — the 12-file e2/e3 sibling residue RESOLVED by
  the §16 fold; compose-revert round-trip arm ARMED and green; golden evals
  29/29 inside it.
* Egg battery: 58 passed + 1 declared machine-shape skip (P5 rows green).
* verify-cognitive-phase4.sh: FULL GREEN END-TO-END (exit 0) — the phase
  exit criterion — run after the re-bind commit; per-leg results in the PR.
* Census actuals (e4-tightened, observed==max): services 52/52, enabled
  40/40, action_types 30, modules 236, lines 66548. Fleet N7: 57→52, 44→40.
* N9 parity: real pilot manifests exit 0, zero divergent tuples (33/33
  operation tuples, record-gated).

## 6. CI root-cause addendum (post-panel, 2026-07-24 — first PR run)

The first PR CI run went red on SEVEN framework-suite tests OUTSIDE the
panel's COG-4 battery scope — all designed/known classes, discharged in a
follow-up commit (root-cause fixes, no gate skipped):

1. **e2 cp1 §6 items 4-7 — the REMAINING routed sibling-suite surgery** (my
   §3.2 wave-summary read them as already-landed; they were designed-red on
   the unit branches, outside the panel's `test_cog4_*` battery, and are the
   integrator's to apply): `test_charter_shadow.py::test_services_row_is_
   scheduled` (§6.4), `test_preference_pairs.py::test_services_row_is_
   scheduled` (§6.5), `test_prediction_scorer.py::test_services_row_is_
   scheduled_daily` (§6.6), and the three `test_judge_calibration_
   scheduling.py` row locks (§6.7) — each re-anchored EXACTLY per the routed
   text (accept dedicated-row OR composed-organ; runner NAMES the manifest;
   entrypoints keep the absorbed commands; judge interval <= 172800s; render
   targets the runner row Label/StartInterval/ProgramArguments). The four
   files join restore_from_baseline + EXPECTED_SCOPE (paired, same commit) —
   restoring them re-arms the dedicated-row locks with the restored fleet.
2. **Shadow-law grep** (the WR-rider evidence-detector proof's
   zero-consumers test): the W6-e1 rollback manifest names that proof FILE
   as an out_of_phase_in_range retained-path row — a path row in
   phase-rollback accounting, never a consumer. Fixed the test's own
   designed way: an allowlist row with the reason. (The recompute sibling
   proof's grep was verified unaffected — different tokens; and THIS
   artifact deliberately avoids spelling either grep token, or it would
   itself become an offender.)

Digest re-bound a second time in the same follow-up (the wave-artifact
addendum + the restore/scope pair rows moved it); the review artifact's
administrative note carries the final value + full provenance.

Model: landing integrator on Fable 5 (the two-tier law — integration
judgment). Per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; fleet/runtime acts additionally per
the 2026-07-21 ownership-on-GO.
