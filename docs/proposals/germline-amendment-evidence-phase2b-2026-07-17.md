# Germline amendment — EVIDENCE PHASE 2 BATCH B (act-class producers + authority receipts) — 2026-07-17

**Status:** PROPOSED on `feat/evidence-phase2-batch-b` (off `3fcb340c`).
The Captain's merge of this branch to master (after CI is green) is the
apply; the post-merge on-Mac unlock ceremony below re-materializes the schg
files at the landed bytes and relocks the same day.

**Design of record:** whole-cabinet evidence & self-improvement phased design
(2026-07-16), §3 Phase 2 items 2 (direct producers where act semantics
matter) and 3 (per-class recording contract) under the §2 safety envelope,
refinement R-1 (authority/control-plane producer), §8 decisions D1–D9.
Authored and self-ratified per the 2026-07-07 full-autonomy grant; the
ceremony itself stays Captain-only.

**Checkpoint review:** `shared/interfaces/reviews/evidence-phase2-batch-b-cp1.md`
(FW-019 artifact for this >300-line batch).

## What this batch is (the per-class recording contract, enforced as law)

Batch B wires the design's direct producers — the surfaces where **act
semantics** matter — plus the R-1 authority/control-plane receipts:

1. **Act-first action lane** (`action_exec.py`, `run_action_lane.py`,
   non-germline `action_reconcile.py`): full signed lifecycle trials via the
   Phase-1 `ActLifecycle` helper with **evidence-before-action FAIL-CLOSED
   semantics** — if the evidence plane cannot record, the action DOES NOT
   RUN. This is a DESIGNED behavior change on the evidence-plane-broken
   branch ONLY; the happy path is domain-stable (same actions, same effects,
   same outputs — additive correlation ids into the undo journal per the
   design's two-way correlation law). The hourly reconciler's machine
   outcome labels land as the lane's verification/outcome events, linked to
   the undo-journal row.
2. **Learning/gate machinery recording itself** (`gate.py`,
   `apply_watch.py`): gate verdict and apply-watch decision trials, same
   fail-closed arm on the apply lane; receipt/brake arms degrade loud
   (a tightening is never evidence-gated).
3. **Watchdog/doctor + officer-session lifecycle** (non-germline:
   `framework/watchdog/receipts.py` typed lens, `check.py`,
   `cabinet-doctor.sh`, `cabinet/cron/*watchdog*.sh`,
   `emit-officer-lifecycle-transitions.py`): RECEIPT class — new
   transition-only org event classes signed by the Batch A mirror; never
   per-poll rows, never generic session exhaust (the 59%-plumbing law).
4. **R-1 authority/control-plane receipts** (germline: `needs.py`
   `need_approved` at the Captain's grant verb, `action_undo.py`
   `kind_frozen` symmetry at the freeze brake, `veto_registry.py`
   structured `veto-scope:` consequence refs; non-germline: `binder_wire.py`
   posture-cap verb receipts, `emit-authority-transitions.py` state-diff
   sweep for posture/germline-window/kill-switch transitions). RECEIPT
   class by law: every one describes a control-plane change that ALREADY
   happened; none may ever gate, block, or fail the verb or brake it
   describes.
5. **Field-classification additions** (`framework/evidence/
   classification.py`): the new detail keys registered producer-asserted
   vs independently-established per §2.2 R1; redaction fires on every new
   key before hashing; none join the officer projection allow-list.

Class assignment law (§3 Phase 2 item 3): the moment BEFORE an effect is
act-class (fail-closed); observations AFTER are receipts (degrade LOUD,
never block). Nothing in this batch silently makes a receipt fail-closed.

Everything else in Batch B (the mirror allow-list additions, emitter
vocabulary, watchdog lens, sweeps, services rows — both ship `disabled:
true`, enable is a deploy step — coverage reconciler, tests) is
deliberately NON-germline and rides the ordinary review path in the same PR.

## Why this touches germline

The act-class seams ARE the judged authority plane: the action lane, the
gate/apply machinery, the needs/veto/freeze verbs are schg-locked so
officers cannot edit, disable, or forge the code that grants authority or
renders judgment — and now also cannot detach its evidence. Wiring
evidence-before-action into them is a germline edit by construction, routed
through the Captain sudo unlock ceremony. `classification.py` sits under
the `framework/evidence` Ring-0 dir cover.

**No boundary extension.** No path JOINS or LEAVES the locked set:
`cabinet/scripts/germline-lock.sh` `FILES[]`/`DIRS[]`,
`framework/policies/immutable-core.yml`, and the pre-tool-use hook §5
screen are all byte-identical in this branch (verified: `git diff` empty on
all three).  `framework/tests/test_germline_lockstep_consistency.py` is
green (371 passed).

## Exact ceremony file list

The complete set of schg-locked paths whose content this branch changes —
verified mechanically against `germline-lock.sh` `FILES[]` + `DIRS[]` over
the composed diff (8 of 27 changed files; no other germline path is
touched):

1. `framework/acting/run_action_lane.py` (modified — `FILES[]`)
2. `framework/authority/needs.py` (modified — `FILES[]`)
3. `framework/evidence/classification.py` (modified — `DIRS[]` cover
   `framework/evidence`)
4. `framework/frontdoor/action_exec.py` (modified — `FILES[]`)
5. `framework/frontdoor/action_undo.py` (modified — `FILES[]`)
6. `framework/frontdoor/veto_registry.py` (modified — `FILES[]`)
7. `framework/learning/apply_watch.py` (modified — `FILES[]`)
8. `framework/learning/gate.py` (modified — `FILES[]`)

## Live application (Captain, same day)

On the armed Mac, after the merge lands on master:

```bash
cd /Users/nate/captains-cabinet
sudo cabinet/scripts/germline-lock.sh unlock
git -C . fetch origin && git -C . checkout origin/master -- \
  framework/acting/run_action_lane.py \
  framework/authority/needs.py \
  framework/evidence/classification.py \
  framework/frontdoor/action_exec.py \
  framework/frontdoor/action_undo.py \
  framework/frontdoor/veto_registry.py \
  framework/learning/apply_watch.py \
  framework/learning/gate.py
sudo cabinet/scripts/germline-lock.sh lock
cabinet/scripts/germline-lock.sh verify
python3.12 -m pytest framework/evidence framework/acting/tests/test_action_lane_evidence.py \
  framework/learning/tests/test_gate_evidence.py framework/tests/test_authority_evidence.py \
  framework/tests/test_germline_lockstep_consistency.py -q
```

Relock the SAME day. `germline-lock.sh verify` and the lockstep test are the
exit checks; any drift is a stop-and-page, not a workaround.

## Safety envelope conformance (§2, binding)

- Per-class contract proven both ways: happy-path domain stability (BASE
  suites 5408+24s → composed 5546+24s, +138 producer tests, 0 removed;
  BASE-vs-composed happy-path probe: domain artifacts byte-identical, the
  only deltas are the designed additive receipt classes, mirror correlation
  stamps, and the reviewed `veto-scope:` consequence refs) AND the
  fail-closed / degrade-loud branches firing exclusively under injected
  evidence-plane failure (store-parent-as-file injection: act arms refuse
  typed, receipt arms land the domain write + `evidence_mirror_degraded` +
  marker row + stderr WARN).
- Recorder determinism: stored event bytes == hashed bytes; v1 AND v1.1
  events verify (evidence suite 126 green; dogfood harness ok=true, 15
  scenarios; `test_act_bytestream.py` green).
- No generic emit CLI/API; no new officer read surface
  (`cabinet/scripts/evidence-read.sh` untouched); redaction fires on every
  new detail field before hashing; producer identity process-attested,
  never payload-derived (A6), never env-derived (A10); trigger/heartbeat/
  delivery exhaust never recorded; never-a-score: EVAL-025 green (27/27
  golden evals); layer separation green (new=0).
- Coverage (A2 reconciler, verbatim): `evidence covers 9 of 13
  action-taking surfaces; named gaps: attention-hygiene,
  probes-verification, roles-missions-lifecycle, ops-consequence-scripts`.
  Honest gaps beat implied completeness — the named gaps are future waves,
  UNKNOWN-not-health, Act frozen over them.
- Observe-only soak (D8): recording is append-only observation; both new
  sweep services ship `disabled: true`; zero behavior change until the
  Batch B ceremony enables them.
