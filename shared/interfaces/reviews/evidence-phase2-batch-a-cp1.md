# Checkpoint review — feat/evidence-phase2-batch-a cp1 (integration landing)

**Date:** 2026-07-17 · **Branch:** feat/evidence-phase2-batch-a (fresh clone
off ff26a079) · **Scope:** integration of the four reviewed Phase-2 Batch-A
group diffs (mirrors, identity-envelope, measurement-doctor, harness) +
cross-group seam reconciliation + gate battery. Design of record:
whole-cabinet evidence & self-improvement design 2026-07-16 (§3 Phase 2,
§2 safety envelope, R-1/R-8/R-13, §8 decisions). Phase-2 law: observation
only — this batch may only ADD information, never change behavior.

## Group diffs landed (applied verbatim, in order; all four clean)

- **G1 mirrors** — `framework/evidence_mirror.py` (NEW, non-germline by
  design) + chokepoint hooks in `framework/events/emitter.py` and
  `framework/fidelity/consequence.py` + 39-test suite. Allow-list mirror
  tier (`MIRRORED_ORG_EVENT_TYPES` strict-subset law; trigger/session/
  notification exhaust pinned OUT — allow-list, not deny-list, per the
  59%-plumbing lesson), day-bounded taxonomy trials with chained segments,
  correlation both directions, fixed producer identities, LOUD rate-limited
  degradation (stderr + `cabinet/logs/evidence-mirror-degradations.jsonl`
  marker + `evidence_mirror_degraded` org event, never self-mirrored),
  pytest fence (mirror disabled under pytest without scratch overrides;
  production never env-steered). Registers the latent `captain_gate_bounced`
  class (emitted-but-unregistered since the attention gate shipped; the
  ValueError was swallowed at the call site — additive vocabulary fix).
- **G2 identity-envelope** — the germline content wave (see the amendment
  doc): `MAX_TRIAL_EVENTS = 500` typed cap refusing before any byte,
  recovery-exempt; LOUD lifecycle degradation sidecar (content-free,
  id-validated); freeze-once `identity.py` attestation seam +
  `attestation_mode` classification key + exports; 2 in-dir test files.
- **G3 measurement-doctor** — doctor check 12 (freshness / growth / chain
  pure-bash probes, AMBER-max, store root pinned, env seam refused),
  `cabinet/scripts/evidence-bench.py` (scratch-store-only measurement
  harness; refuses live-store paths), runbook "Measured envelope" section
  (990-append run of record; p95 curves; growth projections; watermark
  axis; cap recommendation 512).
- **G4 harness** — `cabinet/scripts/evidence-coverage.py` (A2 mechanical
  producers-vs-surfaces reconciliation; UNENUMERATED producer = exit 1),
  PR#140/#149 bypass-catalog replay against the new seams (21 probes;
  BLOCK shapes still block, ALLOW doorways still allow; the germline hook
  is NOT edited), Phase-2a acceptance suite (redaction-before-hash on
  mirror-borne fields, determinism, WAL recovery, purge semantics,
  projection exclusion, digest-anchor coexistence).

## Seam reconciliations (the integration's own edits, each reviewed here)

1. **Cap constant (G2 vs G3).** G2 enforces `MAX_TRIAL_EVENTS = 500`
   (provisional); G3's bench measured and recommended 512 and had written
   512 into the doctor default + runbook as if enforced. Reconciled per the
   batch instruction: the ENFORCED constant stays G2's provisional 500;
   the runbook now records BOTH numbers explicitly and names retuning a
   follow-up ceremony, never a silent edit; `EV_CAP_DEFAULT=500` in the
   doctor (+ the pure-probe default), and a new test pins
   `EV_CAP_DEFAULT == recorder.MAX_TRIAL_EVENTS` mechanically. G1's
   `MAX_MIRROR_EVENTS_PER_TRIAL = 500` was already aligned.
2. **Degradation marker ↔ doctor join (G1 vs G3).** G3's probes did not
   read the marker G1 writes. Added a fourth pure probe
   `evidence_probe_degradations` (mtime-recency + row count + last
   chokepoint/reason extraction; handles BOTH marker vocabularies — G1's
   mirror ledger and G2's store-root lifecycle sidecar), wired twice in the
   section: the mirror ledger OUTSIDE the store-dir guard (a degradation
   with no store is exactly the loud case) and `<store>/degradations.jsonl`
   inside it. Join proven end-to-end by test: a dead recorder under the
   real org-event chokepoint produces the real marker bytes, and the bash
   probe parses THOSE bytes to WARN (`last=org/recorder_error`); sibling
   test covers the lifecycle sidecar vocabulary. AMBER-max preserved.
3. **Coverage truth (G4 vs G1).** G4 was written against base (mirrors =
   KNOWN-GAP; `framework/evidence_mirror.py` would have been UNENUMERATED
   drift = exit 1; the doctor's read-only verify spot-check flipped
   watchdog-doctor to WIRED). Reconciled: (a) the WIRED python detector now
   recognizes the real chokepoint seam `from framework import
   evidence_mirror` and the real constant name `MIRRORED_ORG_EVENT_TYPES`
   (G4 had guessed `MIRRORED_EVENT_TYPES`, which matches nothing);
   (b) shell evidence-CLI invocations are DETECTOR-ONLY, never producer
   wiring — there is no emit CLI by law, so a read-only probe cannot flip
   an act surface to WIRED; (c) the mirror engine is enumerated under the
   infra row. Post-integration truth, pinned by updated tests:
   `evidence covers 4 of 13 action-taking surfaces` — org-event-mirror and
   consequence-mirror WIRED (G1's producers LIVE), all act surfaces honest
   KNOWN-GAP (Batch B), exit 0 (no drift), `--strict` still fails.
4. **Layer separation.** G3's probe test constructed
   `fake_root / "instance" / "evidence" / "v1"` in a framework test — a new
   FRAMEWORK_PATH_INSTANCE violation (the only new one; baseline is
   shrink-only). Fixed at the root: the test now parses the store path FROM
   the doctor section under test (`_ev_store_rel()`), which is also better
   test design — single source of truth, no independent hardcode. Gate
   green with new=0, no baseline growth.
5. **Docs sweep.** The runbook's reference to the runtime-created
   degradation marker ledger can never be tracked at HEAD; added the
   documented allowlist entry (existing "runtime ledgers" class precedent:
   gate-apply-watch.jsonl, world-chronicle.jsonl) with the WHY and the
   remove-when-mechanism-dies rule. Sweep GREEN (findings=0).

## Gate battery (all runs on this branch, house interpreter python3.12)

- `pytest framework/evidence framework/onboarding framework/tests`:
  **1073 passed, 2 skipped** (base ff26a079 collected 970; now 1075 —
  +105 added, 0 removed; `git diff --diff-filter=MD -- '*test*'` vs base
  is empty = no pre-existing test modified or deleted).
- `pytest cabinet/scripts/tests`: **1096 passed, 4 skipped** (base 1064
  collected; now 1100 — +36 added, 0 removed). Includes the bypass-catalog
  replay (21 probes green) and `test_never_a_score_eval.py`.
- Lockstep consistency (`test_germline_lockstep_consistency.py`):
  **371 passed** — lock SET byte-identical (no join/leave in
  germline-lock.sh FILES[]/DIRS[], immutable-core.yml, hook §5).
- `check-layer-separation.sh`: **OK — new=0** (baseline 24, allowlist 18).
- `run-golden-evals.sh`: **27/27 PASS incl. EVAL-025** (never-a-score:
  12/12 static checks green).
- `docs-track-code-sweep.sh`: **GREEN (files=39 findings=0, exit 0)**.
- Dashboard `tsc --noEmit`: **SKIPPED — not faked**: typescript deps are
  not installed in the fresh integration clone, and this batch changes
  ZERO dashboard files (`git diff --name-only` contains no
  cabinet/dashboard path), so master's CI tsc verdict is unaffected.

## Observation-only proofs (batch law)

- Fence-closed byte-identity: G1's `TestFenceClosedDefault` — without the
  pytest-fence override, org emit payload is the SAME object (by-reference
  behavior preserved) and consequence refs stay `[]`; no store write.
- Journey byte-stream: `framework/onboarding/tests/test_act_bytestream.py`
  green unchanged (28-test bytestream/v1.1/verifier/dogfood block green).
- v1 + v1.1 events verify (`test_vocabulary_v11.py`, `test_verifier.py`);
  recorder determinism pinned again end-to-end by the acceptance suite
  (ledger line == canonical serialization of the returned event).
- Fault injection: recorder dead → domain emit SURVIVES and lands in the
  domain ledger; degradation is loud and rate-limited (one marker + one
  degradation event per window across 5 failures); unimportable recorder
  (system-python-3.9 shape) degrades with the named reason.
- Cap refusal leaves zero bytes (no WAL record, no ledger growth), is
  stable on retry, and the recovery path reconciles a signed pending event
  past a tightened cap exactly once.

## Known residuals (documented, accepted for Batch A)

- Cross-process cap edge: a fresh process meeting an exactly-at-cap day
  trial degrades loud on every allow-listed emit (rate-limited) until the
  day boundary — G1's documented "backstop slop"; volume sits 5–10x below
  the cap so this is a pathological-day signal, not a normal path.
- A forward stamp can dangle when the receipt append later fails (stamp
  before domain emit, receipt after) — surfaced by the daily digest-anchor
  + the Phase-2 effect-vs-evidence reconciler.
- Same-user honesty caveat (R2) unchanged: mirror and domain writer share
  a uid until HP-1; everything here is tamper-EVIDENT audit record, never
  trusted input for self-modification.
- `captain_gate_bounced` events emitted before this batch were swallowed
  and are unrecoverable; recording starts at this pin.

## Verdict

Integration verdict: LAND. All hard invariants hold (determinism, lockstep,
no emit CLI, no new officer surface, redaction-before-hash, identity never
payload-derived, no fuel-bearing env var, never-a-score, exhaust never
signed). Germline content changes ride the amendment
`docs/proposals/germline-amendment-evidence-phase2a-2026-07-17.md`
(7 files, all under the existing framework/evidence dir cover; no boundary
extension). Merge is Captain's, ceremony after merge, relock same day.
