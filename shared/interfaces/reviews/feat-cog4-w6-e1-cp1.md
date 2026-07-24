# Review — feat/cog4-w6-e1 cp1 (COG-4 W6 e1: phase twins — verify + review-scope + rollback manifest/rehearsal)

**Batch:** the four W6-e1 phase-twin deliverables + the two egg-manifest
anchors + this artifact, one unit commit off master fc51fd59. Contract:
`docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` §14.1 (phase
twins), §7.3 (pointer tripwire), §10 (armed consumer, MR2), §15
(review-to-bytes), §16 (rollback manifest — C1 closed range, real footprint,
services.yml carve-out). Structural precedents read IN FULL:
verify-cognitive-phase3.sh, cognitive-phase3-review-scope.py, the phase-3
rollback manifest + rehearsal, test_cognitive_phase3_rollback.py.

## Files

* `cabinet/scripts/verify-cognitive-phase4.sh` — composed committed-tree exit
  gate: clean-tree/work-tree guards; §10 armed-mode leg (consumes
  `COG4_ENFORCE_BOUND` — the N6 anti-phantom arm keys on this consumer;
  self-retiring SKIP-note while cog4-measure.py is absent, W6-e3); §15
  review-binding leg (SKIP-note until the frozen digest lands — the phase-3
  precedent); §7.3 pointer tripwire (`~/.cabinet/state/cog4-dispatch-pointer`
  existing = RED); enduring-architecture gate; explicit layer-sep; the FULL
  `test_cog4_*` battery; census `--check`; the C2 boundary engine; the
  universal A13 heredoc (byte-identical to the phase-1/2/3 twins); the egg
  battery; the rollback rehearsal. Ends READY_FOR_CI (honest reach).
* `cabinet/scripts/cognitive-phase4-review-scope.py` — EXPECTED_SCOPE
  frozenset (73 entries) == (manifest.remove − review artifact) ∪
  restore_from_baseline, drift-checked both ways; dir-wholesale resolution via
  `git ls-tree -r`; --print/--record-less --verify per the phase-3 tool;
  fail-closed on absent scope entries (the sibling-landing forcing function).
* `docs/plans/cognitive-core-phase-4-rollback-manifest-2026-07-24.yml` —
  BORN-CLOSED range: baseline de5d16c4 (contract landing), done_flip_sha =
  PENDING-DONE-FLIP sentinel pinned at the flip (C1 convention; both named
  anti-patterns cited). REAL footprint only — the full de5d16c4..HEAD range
  partitioned per-commit: 64 remove (3 framework dirs + fixtures dir + v2
  schema + boundary yml + 4 CLIs + 26 corpus files + 4 PARK docs + 18 wave
  FW-019 proofs + the twins + the one allowed-absent frozen review), 10
  restore (incl. services.yml + watchdog registry with the sibling-landing
  tolerance note; rider-overlap on cog2-import-gate.py/egg manifest recorded),
  19 out_of_phase_in_range rows (WR rider lane 0d8a74d4 + W1 C1
  retrofit/re-freeze cee6741e — retained on rollback, never reverted).
  must_remain_unchanged = the §16 carve-out: Phase-0∪1∪2∪3 union MINUS
  services.yml with the three superseding protections NAMED (fleet-truth,
  floor-conservation COUNT+TUPLE, census maxima-tighten) + the §16 COG-4 pins
  + the byte-untouched germline pair (window unopened — real state of record).
* `cabinet/scripts/cognitive-phase4-rollback-rehearsal.py` — proves the code
  inverse on a scratch worktree: sentinel-aware anchor; STRICT inverse-diff
  equality (retained ledgers + declared out-of-phase residue — doubles as the
  completeness ratchet until a phase-4 closure test lands); A13 on the inverse
  tree (byte-identical constant); ledger-status-parity + layer-sep + docs
  sweep; census `--check` on the inverse tree (allowance_removal validity);
  pre-adoption REFOLD arm (the phase-3 pre-bump lesson — byte-compat analog:
  the unmodified cortex determinism suite over the RESTORED pre-kernel
  belief.py/engine.py); restored-contracts arm; compose-revert round-trip arm
  VACUITY-ARMED with the explicit self-arming retirement condition (W6-e2
  compose: services.yml departs baseline / cog4-organ-runner.py exists);
  framework batteries + install-extensions gate + golden evals.
* `cabinet/scripts/egg-export-manifest.txt` — phase-4 private-tool delete +
  expect-absent rows (the COG-0..3 class; the rollback manifest archives out
  with docs/plans, R145).

## Key verifications at authoring

* A13 byte-identity: rehearsal constant == phase-4 twin heredoc == phase-3
  twin heredoc (the universal assertion — zero drift).
* resolve_scope(): manifest ↔ frozenset equality, 73 entries, review artifact
  excluded, operative ledgers unbound.
* Manifest closure: 64/10/19 partition covers the ENTIRE de5d16c4..HEAD
  name-status output (zero unclassified paths); every named path exists except
  the two documented landing-time artifacts; must_remain paths all diff-quiet
  over the range (germline pair byte-untouched confirmed).
* W2-t3 verify-twin arm retirement form PRE-PROVEN out-of-band (§13 corpus
  untouched): `_consuming_files` finds the twin; `_SH_CONSUME` matches its
  non-comment `export COG4_ENFORCE_BOUND=1` line. Landing this twin flips
  `test_cog4_measurement.py::test_verify_twin_arm` to its DESIGNED companion
  failure — integrator corpus surgery retires the skip at landing.
* Boundary engine green over the working tree with the new files present; no
  contiguous cache tokens in any new cabinet/scripts file.

Verdict: SHIP.
