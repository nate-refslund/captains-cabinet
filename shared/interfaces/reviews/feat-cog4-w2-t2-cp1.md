# Checkpoint review — feat/cog4-w2-t2 (COG-4 W2 unit T2 dispatch/integrity corpus) — cp1

**FW-019 artifact** for the >300-line corpus batch (self-review; the phase's binding
review is the §15 frozen fresh-context panel run by the orchestrator). Ground tip
`cee6741e`; branch `feat/cog4-w2-t2` off origin/master. Contract:
`docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` §12 (rows 3/5/6/9/10/11/
12/14/15) + §7.3 + §9.5 + §13 (corpus law).

## Batch (test-only; NO framework/production code, NO services.yml/launchd edits)
- `cabinet/scripts/tests/test_cog4_sim_dispatch.py` — the §7.3 dispatcher spec encoded
  as a pure reference simulator over scratch schedule stores (serve → snapshot-staleness
  → authority → budget → organ-freshness → IDEMPOTENCY, the charter-quadruple order),
  carrying the T2 sims' seeds + asserts + named-escape mutants, the §7.3 order battery,
  and the shipped-COG-3-store tamper-precedent arm (subprocess, tmp roots, reader CLI).
- `cabinet/scripts/tests/test_cog4_organ_runner.py` — the §9.5/MF-AC2 runner-invariance
  battery on a reference runner fixture (byte-identical behavior with/without an injected
  schedule artifact; schedule-cache byte-untouched; declared row→manifest association)
  with schedule-READER / schedule-WRITER / manifest-DISCOVERY mutants.

## Mutants proven to bite NOW (each fails at its NAMED escape — §12 discipline)
14 dispatch-side + 3 runner-side, verified outside `pytest.raises` (failure point
inspected per mutant): staleness-implies-dispatch (sim 3), floor-consults-dispatch
(sim 3 supplementary), crash-suppresses-floor (sim 5), exit-1-lumped-as-crash (the S0
finding, sim 5), dispatch-anyway (sim 6), silent-substitute (sim 9), verdict-ignoring
(sim 10), capability-keyed verdict (§5.2), skip-when-absent rows-hash (sim 11 — the
objectives `query.py:214-215` shape, §6.3), planner-said-yes (sim 12), null-hole
comparator (sim 14), fallback-implies-permission (sim 15), budget-before-authority
order swap (§7.3), trusts-row-key (limb 6/SF1); runner schedule-READER,
schedule-WRITER, manifest-DISCOVERY (§9.5/§8.3).

## Vacuity arms (the W1-u2 idiom — §13)
12 skips total: 10 real-CLI arms for `cabinet/scripts/cog4-dispatch-shadow.py` (one per
T2 sim + the order battery) and 2 for `cabinet/scripts/cog4-organ-runner.py`. Every arm
asserts the target's ABSENCE first (the companion tripwire that REDs the instant the CLI
lands) and carries its RETIREMENT CONDITION naming the `_check_*` property to bind to
the real CLI. Fixture-machinery tests run LIVE — no skip.

## Fixture-shape honesty (for the panel)
- Fixture descriptors omit the presentation-only compat `action_type` member and use
  obviously-fixture risk-class spellings — no coupling to the classifier/matrix surfaces
  (L1111); the real authority joint binds via the retirement arms (§7.3(3)).
- The fixture rows-hash chains FULL canonical row bytes (§6.3 strict shape) so content
  edits bite — deliberately stricter than the shipped objectives identity-hash dialect
  (a statement edit does NOT move that chain; the precedent arm forges a row instead,
  which the shipped serve REFUSES loudly: exit 2, artifact withheld).
- Sims 6/9 eligibility rechecks sit between the pinned limbs 5 and 6 as FIXTURE-LOCAL
  placement; their properties assert refusal + explicit reason + identity preservation,
  never limb position — the §7.3 order battery asserts only the six named limbs, so a
  W5 implementation choice on eligibility placement cannot contradict this corpus.

## Verification evidence (re-run by reviewers; claims are DATA, §13/L1105)
- `python3.12 -m pytest cabinet/scripts/tests/test_cog4_sim_dispatch.py
  cabinet/scripts/tests/test_cog4_organ_runner.py -q` → **61 passed, 12 skipped**
  (the 12 = the vacuity arms above).
- Full W1 guard set + new suites (`test_cog4_*`) → 255 passed / 19 skipped.
- FULL `python3.12 -m pytest cabinet/scripts/tests -q` → **2885 passed, 29 skipped, 0
  failed** (the new files join the sweep + completeness invariant cleanly).
- `cabinet/scripts/cog2-import-gate.py` → exit 0 (no cortex/objectives import; no
  fenced data-plane literal — tmp-path stores only; scheduler-store token allowlisted
  for test_cog4_* by ROW 7 regardless).
- `bash cabinet/scripts/check-layer-separation.sh` → exit 0.
- `cognitive-architecture-census.py` → PASS at the observed==max baselines (test-only
  files touch no counted quantity — tests are budget-exempt).

## Known limitations / assumptions (for the panel)
- The reference simulator is CORPUS MACHINERY (the spec encoded), not the W5
  implementation; the real `cog4-dispatch-shadow.py` must satisfy the same properties
  via the retirement arms, with verdicts from the REAL read-only authority joint.
- The safe-fallback split is encoded as: unparseable/missing store ⇒ fixed safe
  schedule (§7.4); parseable-but-integrity-violating ⇒ REFUSE (§6.3) — both grant
  nothing. Corrupt-beats-row-level is asserted; corrupt-vs-forged precedence follows
  from parseability by construction.
- The in-run idempotency arm treats duplicate (organ, operation, wake) rows as replay;
  cross-wake replay is seeded via the shadow log. Key derivation context is fixture-
  minimal ({organ, operation, wake_id}); the manifest's `key_fields` discipline is the
  binding surface.
