# Germline amendment — EVIDENCE PHASE 2 BATCH A (telemetry-tier envelope + identity) — 2026-07-17

**Status:** PROPOSED on `feat/evidence-phase2-batch-a` (off `ff26a079`).
The Captain's merge of this branch to master (after CI is green) is the
apply; the post-merge on-Mac unlock ceremony below re-materializes the schg
files at the landed bytes and relocks the same day.

**Design of record:** whole-cabinet evidence & self-improvement phased design
(2026-07-16), §3 Phase 2 items 1/3/4/5 under the §2 safety envelope and
refinements R-1/R-8/R-13, §8 decisions D1–D9. Authored and self-ratified per
the 2026-07-07 full-autonomy grant; the ceremony itself stays Captain-only.

**Checkpoint review:** `shared/interfaces/reviews/evidence-phase2-batch-a-cp1.md`
(FW-019 artifact for this >300-line batch).

## What this batch is (Phase 2 law: observation only)

Batch A may only ADD information, never change behavior. Its two germline
touch-points harden the envelope and the identity seam of the plane that the
new (non-germline) telemetry mirrors write through:

1. **Per-trial event envelope** (`recorder.py`): `MAX_TRIAL_EVENTS = 500`
   (PROVISIONAL code constant — never env- or `control.json`-derived).
   Every append re-verifies the whole trial (O(n²)); the cap refuses NEW
   mints only, as a typed `trial_event_cap` error raised before any byte is
   produced. Already-signed write-ahead events always reconcile
   (exactly-once), and legacy over-cap trials keep verifying and reading —
   v1 and v1.1 events still verify; stored bytes == hashed bytes. The
   bench's measured recommendation (512) is recorded beside the enforced
   provisional (500) in the runbook; retuning is a follow-up ceremony,
   never a silent edit (Batch-A seam reconciliation).
2. **LOUD act-class degradation** (`lifecycle.py`): the existing
   purge-degradation flip (`degraded_evidence`, shape unchanged) now also
   appends ONE content-free, id-validated marker line to the store-root
   `degradations.jsonl` sidecar (unsigned — NOT evidence; never an officer
   surface), emits a rate-limited stderr warning, and fires an optional
   producer `on_degrade` callback. Strictly additive loudness; the flip
   still never raises and never blocks a purge. The doctor's (non-germline)
   check 12 reads the sidecar's recency.
3. **Broker-attested producer identity seam** (`identity.py`, NEW inside the
   locked dir): freeze-once `attest_process_identity()` — identity enters
   once at process start from explicit values, validated against the
   recorder vocabulary (actor kinds, id alphabet, provenance shape,
   secret-shape refusal), idempotent identical re-attest, typed
   `identity_conflict` refusal, fail-closed accessors, defensive copies.
   Never payload-derived (A6), never env-derived (A10). Not an emit
   surface: returns identity dicts only; Ring-0 modules never import it.
4. **`attestation_mode` detail key** (`classification.py`): registered
   producer-asserted (R2 honesty caveat — process attestation is not broker
   attestation; Phase 6 hard-requires the out-of-process broker). NOT in
   the officer projection allow-list.
5. **Package exports** (`__init__.py`): the five identity names.
6. **Tests inside the locked dir** (`tests/test_envelope.py`,
   `tests/test_identity.py`): pin the cap laws (typed refusal before any
   byte; recovery exemption; code-constant law), the degradation-loudness
   laws (one marker per flip; content-free id-validated fields; best-effort
   writes; sidecar-is-not-evidence), and the identity contracts
   (freeze-once, fail-closed, redaction survival, officer-projection
   exclusion, no-emit-surface posture).

Everything else in Batch A (the chokepoint mirrors, the doctor probes, the
bench, the coverage reconciler, their tests) is deliberately NON-germline
and rides the ordinary review path in the same PR.

## Why this touches germline

`framework/evidence/**` is Ring-0 (`schg` dir lock): officers must not be
able to edit, disable, or forge the audit plane. Batch A changes the CONTENT
of that plane (envelope constant, degradation loudness, identity seam,
classification vocabulary) — a germline edit by construction, routed through
the Captain sudo unlock ceremony. Doctrine-correct: the audit plane evolves
only under the Captain's hand.

**No boundary extension.** No path JOINS or LEAVES the locked set:
`cabinet/scripts/germline-lock.sh` `FILES[]`/`DIRS[]`,
`framework/policies/immutable-core.yml`, and the pre-tool-use hook §5 screen
are all byte-identical in this branch. Every germline file below is covered
by the EXISTING `framework/evidence` directory lock (recursive), including
the new `identity.py` and the two new test files.
`framework/tests/test_germline_lockstep_consistency.py` is green (371
passed).

## Exact ceremony file list

The complete set of schg-locked paths whose content this branch changes
(all under the existing `framework/evidence` dir cover; no other germline
path is touched):

1. `framework/evidence/__init__.py` (modified — identity exports)
2. `framework/evidence/classification.py` (modified — `attestation_mode`)
3. `framework/evidence/identity.py` (NEW — auto-covered by the dir lock)
4. `framework/evidence/lifecycle.py` (modified — loud degradation)
5. `framework/evidence/recorder.py` (modified — `MAX_TRIAL_EVENTS` cap)
6. `framework/evidence/tests/test_envelope.py` (NEW — auto-covered)
7. `framework/evidence/tests/test_identity.py` (NEW — auto-covered)

## Live application (Captain, same day)

On the armed Mac, after the merge lands on master:

```bash
cd /Users/nate/captains-cabinet
sudo cabinet/scripts/germline-lock.sh unlock
git -C . fetch origin && git -C . checkout origin/master -- \
  framework/evidence/__init__.py \
  framework/evidence/classification.py \
  framework/evidence/identity.py \
  framework/evidence/lifecycle.py \
  framework/evidence/recorder.py \
  framework/evidence/tests/test_envelope.py \
  framework/evidence/tests/test_identity.py
sudo cabinet/scripts/germline-lock.sh lock
cabinet/scripts/germline-lock.sh verify
python3.12 -m pytest framework/evidence framework/tests/test_germline_lockstep_consistency.py -q
```

Relock the SAME day. `germline-lock.sh verify` and the lockstep test are the
exit checks; any drift is a stop-and-page, not a workaround.

## Safety envelope conformance (§2, binding)

- Observation-only: with the pytest fence closed, every existing code path
  is byte-identical; the journey byte-stream test
  (`framework/onboarding/tests/test_act_bytestream.py`) is green unchanged.
- Recorder determinism: stored event bytes == hashed bytes; hash chain +
  per-event signature + anchor + watermark all verify; v1 AND v1.1 events
  verify (`test_vocabulary_v11.py`, `test_verifier.py`, dogfood: green).
- No generic emit CLI/API; no new officer read surface
  (`cabinet/scripts/evidence-read.sh` untouched); redaction fires on every
  new detail field before hashing; producer identity never payload-derived;
  no env var becomes fuel-bearing (pytest fences only); never-a-score:
  EVAL-025 green (27/27 golden evals).
