# Checkpoint review — feat/evidence-phase4-shadow-judge cp1 (integration)

**Date:** 2026-07-17 · **Reviewer:** evidence Phase-4 integrator (Fable 5) ·
**Scope:** the composed four-group batch off `de3f48c5` — groups
`detectors` (G1), `fuel-integrity` (G2), `calibration` (G3), `drill` (G4),
each adversarially reviewed per-group before integration; this checkpoint
reviews the COMPOSITION and the integrator's seam work. FW-019 artifact for
a >300-line batch.

## What this checkpoint lands

Design-of-record §3 Phase 4 (machine judge in shadow — detect, never act):

- **G1** `framework/evidence_detectors.py` + thin runner
  `cabinet/scripts/evidence-shadow-detectors.py`: read-only failure
  clustering over the Phase-3 query plane via the R-12 seam
  (`eval_pattern_detector.detect_evidence_patterns` — one clusterer, one
  threshold set) + discriminator-shaped FAIL-OPEN triage (NOISE only with
  affirmative degradation attribution, else INCONCLUSIVE passes through);
  one JSON line per run to `shared/interfaces/evidence-shadow-findings.jsonl`.
  Watchdog rows (`evidence-store-invariants`, `evidence-anchor-export-fresh`,
  `evidence-shadow-detector-liveness`) ground in INVARIANTS only (B9);
  services row + watchdog ids ship STAGED DARK (`disabled: true` /
  commented out).
- **G2** `framework/evidence_fuel_integrity.py`: the report-only
  fuel-integrity check — six preconditions re-derived out-of-band per
  fuel-bearing consequence row (verified mirror, sha consistency, HP-2
  third leg, attestation mode, purge overlap, per-cell closure/unknown
  floors with constants IMPORTED from `judge_calibration` — R-8/R-11);
  verdicts to `cabinet/logs/fuel-integrity-report.jsonl`. **The honest
  claim rides every row:** detects retroactive single-plane tamper and
  INCONSISTENT forgery only; consistent same-user forgery of both planes
  stays open until HP-1 — necessary, not sufficient.
- **G3** `framework/evidence_calibration.py`: per-stratum shadow
  calibration (detector flags × Captain governance labels), every counted
  pair re-verified against the store (B1); `JUDGE_HARD_BAR`/`MIN_PAIRS`/
  `STATUS_MAX_AGE_DAYS` by reference, applied per stratum; NO stratum
  grants power in this batch (no power-granting API exists at all).
- **G4** `cabinet/scripts/evidence-tamper-drill.py` +
  `framework/evidence_freeze.py`: the §2.4 tamper game-day against a
  SACRIFICIAL scratch store (restore-to-earlier invisible to
  `verify_store`, caught by the external anchor), the FAIL-CLOSED
  judging-freeze marker (any presence reads FROZEN; freezing is a pure
  narrowing; clearing is Captain-token-only), Chair-not-Captain paging.

**SHADOW LAW pinned everywhere:** every output is a Captain-facing report;
nothing downstream consumes detector/fuel-integrity/calibration output to
gate, block, score, or act. The enforce flip is a LATER Captain-only
narrowing ceremony, deliberately absent from this batch.

## Integration decisions (beyond the four reviewed patches)

1. **Append-append conflicts, keep-both:** `cabinet/scripts/
   evidence-coverage.py` (all four groups appended census rows — detectors
   + calibration rows collided at one anchor; both kept) and
   `cabinet/scripts/docs-sweep-allowlist.txt` (G2's fuel-report entry vs
   G4's drill/marker entries; all kept). No other hunk conflicted.
2. **G1→G3 join reconciled against the REAL journal (the batch's one true
   seam bug):** G1's cluster findings carry `trials` (≤5 sample ids) and
   triage verdicts `noise|inconclusive`; G3's reader joined only on
   `trial_id`/`trial_ids` and scored neither token — on the real artifacts
   every finding row was unjoinable/unscoreable (the per-group fixtures
   used a different dialect). Fix in G3 (its reader is the declared
   tolerant side): `trials` accepted as the trial-id source (sample cap =
   honest join bound), and the triage vocabulary mapped with polarity
   inconclusive⇒flag (passed through un-explained) / noise⇒pass (triage
   affirmatively explained the cluster away). Pinned end-to-end by the new
   composed seam proof.
3. **Freeze respect completed per G4's consumer contract:** G1 shipped
   marker respect; G2 (`main`) and G3 (`run`) did not consult it. Both now
   refuse with one plain line + rc 0 while the marker is present,
   FAIL-CLOSED (a broken freeze probe reads FROZEN). The composed refusal
   of all three services — and re-run after clearing — is pinned by the
   seam proof.
4. **Composed seam proof added:** `framework/tests/test_evidence_phase4_seams.py`
   — one scratch repo root, real store, real Captain-label writer
   (governance-review.py via importlib), real detector run: (a) the actual
   journal joins the actual pairing (2 candidate → 2 counted pairs, both
   polarities, zero silent drops); (b) the freeze marker halts all three
   services, zero writes; (c) two composed passes leave the store
   byte-stable (non-watermark identical after pass 1, fully byte-identical
   after pass 2) with every report surface OUTSIDE the store.
5. **Zero-consumers grep proofs extended, not weakened:** the per-group
   proofs pin exact reference allowlists; composition added sanctioned
   cross-references (G3 reads G1's journal; each proof names the other's
   file; the docs-sweep glob list and runbook name runtime paths; this
   artifact names the modules). Every addition is enumerated with a WHY in
   the proof it extends — all additions are prose/pattern/test references,
   none is a consumer.
6. **Layer-separation kept clean without allowlist growth:** the seam
   test's scratch store now derives from `journey.EVIDENCE_REL` (the ONE
   canonical constant) instead of a mirrored `instance/...` literal —
   layer-sep gate `new=0` with no new allowlist row.
7. **Docs:** runbook `docs/runbooks/evidence-recorder-v1.md` gains the
   "Machine judge in shadow (Phase 4)" section (detectors, fuel-integrity
   + honest claim, calibration, drill + freeze/unfreeze, staged-dark
   enablement, Phase-4 invariants); `docs-sweep-allowlist.txt` gains the
   three newly-named runtime surfaces (findings journal, calibration
   report + series).

## Zero germline diff — the headline

Every touched path was checked against `germline-lock.sh` FILES[] (73) +
DIRS[] (7): **no schg-locked path changes in this batch.** All Phase-4
logic lives in NEW non-germline siblings (`framework/evidence_*.py`,
`cabinet/scripts/evidence-*.py`) reading germline surfaces through public
APIs. **No ceremony, no amendment doc, no `test_egg_export.py` pin needed
— there is nothing to unlock.** The germline lockstep consistency suite
(371 tests) is green untouched.

## Gate battery (this clone, `python3.12` throughout)

| Gate | Result |
|---|---|
| `python3.12 -m pytest framework -q` | 5689 passed, 29 skipped, 2 pre-existing-class failures fixed in-batch (grep proofs; final run green — see below) |
| `python3.12 -m pytest cabinet/scripts/tests -q` | 1530 passed, 5 skipped; 2 environmental failures REPRODUCED AT PRISTINE BASE `de3f48c5` (see below) |
| Germline lockstep consistency (`test_germline_lockstep_consistency.py`) | 371 passed |
| `check-layer-separation.sh` | OK — baseline=24 allowlist=19 new=0 |
| `run-golden-evals.sh` (incl. EVAL-025-NEVER-A-SCORE) | 27/27 PASS (EVAL-025: 12/12 checks green) |
| `docs-track-code-sweep.sh` | GREEN at commit (the two mid-flight findings were this artifact + the seam test entering the index in the same commit, exactly the sweep's same-commit contract) |
| Dashboard `npm ci` + `tsc` + `vitest` | SKIPPED — zero dashboard files in the batch (skipped-not-faked) |

**Pre-existing environmental failures (NOT this batch):** in this sandbox
clone, `test_evidence_seam_bypass_replay.py::…[evidence-access.sh]` fails
because the germline hook's fail-closed control-plane probe denies even the
sanctioned ALLOW cases (no live Redis/kill-switch plane in the sandbox) —
reproduced byte-for-byte on a pristine shared clone at base `de3f48c5`
(same 2 FAIL rows: "Bounded projection", "Ordinary onboarding read"). The
batch touches no hook and no germline path, so it cannot move this
surface; CI is the authority for it. `test_docs_sweep.py::…
test_real_script_green_on_real_repo` passes at base and turns on the git
index — green once this commit stages the two new reference targets.

## Shadow + read-only proof (integrator-level, beyond per-module pins)

- Repo-wide `git grep` of every new module name and output path
  (`evidence_detectors`, `evidence_calibration`, `evidence_fuel_integrity`,
  `evidence_freeze`, `evidence-shadow-findings`, `fuel-integrity-report`,
  `evidence-calibration-status`, `tamper-drills`,
  `evidence-judging-freeze`) over ALL acting/gating/officer surfaces —
  `framework/{authority,fidelity,learning,frontdoor,acting,attention,
  events,evidence,onboarding}`, `cabinet/scripts/hooks`,
  `cabinet/scripts/evidence-read.sh`, `cabinet/dashboard` — returns **zero
  hits**. No officer, acting, or gating surface consumes any Phase-4
  output. (The watchdog registry sits outside those surfaces and reads the
  journal's MTIME only — pinned by `test_evidence_detectors.py`.)
- Store byte-stability across the composed surface: the seam proof's
  two-pass tree digest plus each group's own read-only proof
  (fuel-integrity `TestReadOnlyProof`, calibration
  `test_measurement_leaves_store_byte_stable`, drill
  `test_anchor_check_is_byte_stable`). The sanctioned first-verify
  watermark advance is the only byte that moves, identical to the existing
  `verify` verb.
- Exit codes carry no verdict signal (G2 pin); no power-granting API
  exists anywhere in the batch (G3 pin: `dir()` scan for `may_*`/`allow`).

## Verdict

Composition sound; the one real cross-group defect (the G1→G3 dialect
mismatch) is fixed on the tolerant side and pinned by a composed test that
would have failed loudly on the unreconciled tree. Shadow law, never-a-score,
read-only store, weak-signal doctrine, R-11 single-constant discipline, and
the zero-germline boundary all hold with mechanical evidence. Ready for PR;
merge remains the Captain's/CI's call.
