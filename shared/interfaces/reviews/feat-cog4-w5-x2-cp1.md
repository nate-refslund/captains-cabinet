# Review — feat/cog4-w5-x2 cp1 (COG-4 W5 x2: three non-software fixture cabinets)

**Batch:** `cabinet/scripts/tests/test_cog4_exit_fixtures.py` (new N8/MR4
battery, 8 tests) + `cabinet/scripts/tests/fixtures/cog4/cabinets/
{garden-delivery,harbor-warehouse,care-rota}/*.yml` (six committed §4.2-shaped
organ manifests, two per cabinet) + this artifact. Contract:
`docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` §12 N8 (three
heterogeneous non-software operation-to-effect fixtures), MR4 (extend COG-3
fixture #2 + two NEW cabinets), §5.2 (capability carries no authority), §5.4
(the three kept enum-growth mutants), §5.5 (trajectory v2), §13 (corpus
immutable — ZERO edits under existing tests; `git status` scope = adds only).

## Self-review findings (checked before commit)

1. **End-to-end is the REAL CLI chain, not a harness shortcut** — per cabinet:
   seeded cortex (lib_cog3_fixtures fold+persist) + objectives via
   `cog3-rebuild.py` subprocess, then `cog4-snapshot.py` -> `cog4-schedule.py`
   -> `cog4-dispatch-shadow.py` (via lib_cog4_dispatch_adapter.run_cli,
   hermetic joint, REAL `matrix_policy(load_matrix())` document). Mutation
   probe P4 proved the bite: dropping cabinet A's declared
   `ceiling: [external_comms]` flips the dispatcher's decision
   (`authority:always_gated` != expected `authority:ceiling`) and REDs the
   end-to-end test at the decision assert.
2. **The ONE descriptor rides untouched** — `rec["descriptor"] ==
   resolve_descriptor(...)` asserted dict-exact per operation: manifest
   resolution -> snapshot excerpt -> fold row -> kernel serve -> shadow
   record, byte-identical (ASCII canonical round-trip).
3. **§4.2 shape through the W2 reference** — every committed manifest passes
   `t3.validate_organ_manifest` (probe P1: an N-d-inconsistent risk_class
   REDs); `state_ownership` disjointness suite-level (probe P3: a duplicated
   path REDs); matrix consistency (N-d) on every RESOLVED per-op descriptor.
   The germline gate pair is byte-untouched (window unopened; builds against
   the CG-33 proposal text per §4.5).
4. **Enum-growth walls asserted DURING each cabinet run** — census
   `central_action_types` maximum 30 == len(ACTION_TYPES); consequence-event
   schema enum == set(ACTION_TYPES) + null; `load_matrix()` totality green,
   13 risk classes; every fixture op id namespaced and not a member.
5. **§5.2 mutant per cabinet** — the W2 blindness harness over a
   same-descriptor pair: REAL dispatch records are name-blind; a
   capability-keyed mutant predicate is CAUGHT per cabinet; cabinet A also
   catches the W2 corpus's own `garden/water.plots` mutant.
6. **Trajectory v2 per cabinet** — records minted from the shadow decisions
   (status proposed|denied only — shadow mints intent, never execution)
   validate via the REAL `contracts.structural_issues` (Draft-2020-12);
   `domain_operation` carries the granular identity; the never-overload
   mutant (namespaced id in `action_type`) FAILS validation per cabinet.
   Refused rows never reached limb 6, so the mint derives the same
   context-bound key the dispatcher would (v2 `id` pattern forbids the
   free-text §4.2 discipline strings — deliberate).
7. **SF1 replay (cabinet A)** — same wake re-dispatch refuses every granted
   op `idempotency_replay`; a fresh wake_id grants again; the shadow log
   carries exactly {run, decision} record kinds across three runs.
8. **Token sweep** — committed fixture files + the module-level CABINETS
   seed payloads swept for 18 parts-assembled technical tokens with
   word-boundary matching (probe P2: an injected token REDs). Fixture
   freshness/state paths are extension-free domain tokens by design.
9. **Known accepted shapes** — (a) the dispatcher's organ-manifests input
   derives from the §4.2 manifest with `idempotency: {key_fields: [...]}`
   (the W2 dispatch-corpus shape; the §4.2 per-op discipline strings stay
   packaging metadata — limb 6 re-derives keys from run context, never rows).
   (b) urgency/trigger_due are per-wake declarations the cabinet supplies to
   the snapshot, not manifest fields. (c) `import test_cog4_organ_manifest` /
   `test_cog4_trajectory_v2` follows the established test-imports-test idiom
   (test_cog4_organs_package.py precedent) — the W2 corpus is read as the
   executable spec, never edited.

## Inherited, NOT this unit's (integrator-owned corpus surgery, §13)

The full `cabinet/scripts/tests` sweep carries 11 pre-existing REDs on the
x1 base (7272db13): 10 × `test_cog4_sim_dispatch.py::TestRealDispatchCliArms`
+ 1 × `test_cog4_dispatch_ast_pin.py::TestDispatchImportPin::
test_real_cli_is_armed_and_absent` — the W2 vacuity arms' COMPANION asserts
that go RED by design the moment `cog4-dispatch-shadow.py` lands ("retire
this vacuity skip ... integrator move, §13"). Base-vs-branch sweep diff:
identical failure set, zero delta from this unit (this unit only adds files;
no repo file references the new surfaces).
