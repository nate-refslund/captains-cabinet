# Checkpoint review — feat/cog4-w4-v1, cp1 (COG-4 W4 u1: the ORGANS package)

**Scope (one commit, >300 lines → FW-019 artifact required; this is it):**
1. `framework/organs/__init__.py` — import-inert package root (the
   projection/scheduler idiom; subprocess-proven inert by the unit battery).
2. `framework/organs/registry.py` — §4.4 STRUCTURAL organ-manifest loader:
   REQUIRED directory parameter (layer law — no default path, no
   instance-layer literal; CLIs inject), honest fail-closed errors that
   never claim schema validation (CG-33 window unopened), content-addressed
   `registry_hash` (recorder-dialect digest over the canonical-bytes-sorted
   manifest list — an organ edit is an honest epoch bump), and the N-b
   SUITE-level `state_ownership_collisions` sweep helper. The
   canonical-bytes/digest pair is a stdlib REPLICA of the C3 kernel's (a):
   boundary row 6 does not allowlist framework/organs as a projection
   importer, so the dialect is replicated (the objectives/model.py
   precedent) and pinned byte-identical by a standing test tripwire.
3. `framework/organs/descriptor.py` — the §5.2 ONE-descriptor resolution
   (MF-A1): capability → descriptor from MANIFEST-DECLARED values verbatim
   (organ-level block + per-operation override over the four members);
   refusal on missing/mis-shaped members, unknown consumed keys, ambiguous
   or zero declarers, unreadable declarations; ZERO operation-name
   authority; `status_vocab` references the existing 7-status enum. NO
   action-plane import anywhere in the tree.
4. `cabinet/scripts/tests/test_cog4_organs_package.py` — NEW battery (55
   tests): registry load/hash/epoch + refusal matrix; kernel-dialect parity
   tripwire (replica == framework/projection/kernel over non-ASCII probes +
   independent hash recomputation); descriptor resolution + refusals; the
   W2 corpus capability-blindness harness re-armed over descriptors THIS
   package resolved (mutant caught); N-b sweep shape-parity with the corpus
   line-for-line; fixtures (garden-rota = the W2 t3 fixture IMPORTED, plus
   delivery-run + care-rota + notice-board) all pushed through the W2
   reference validator + N-d at test time; boundary disciplines proven NOW
   (AST import law stdlib|yaml|internal only; subprocess transitive closure
   over all three modules against the FULL eight-tree row-5 fenced set —
   green, so the integrator's pin surgery lands green).
5. `docs/plans/cog4-w4-u1-organ-schema-validation-PARKED-2026-07-24.md` —
   the §4.5 dated PARK marker: schema-validated organ manifests + the
   validate-extension.sh organ-block verification unit PARK (CG-33 Captain
   window UNOPENED; HANDBACKS item 19 named); retirement condition +
   rollback note recorded. No schg path read-modified or worked around.
6. `cabinet/config/cognitive-architecture-contract.yml` — the two COG-4
   temporary_allowances rows extended to EXACT measured running totals in
   this same commit (§11 law): modules 7 → 10 (236 vs 226 base), lines
   973 → 1378 (66390 vs 65012 base), reasons appended with the W4 u1
   segment; census re-run green at observed==max (zero headroom preserved);
   duplicate-YAML-key check clean.

**Corpus law (§13):** zero existing test files edited
(`git diff --stat` over `cabinet/scripts/tests/` shows only the NEW file).
ONE designed corpus contradiction routed to the integrator:
`test_cog4_scheduler_ast_pin.py::TestSchedulerTransitiveClosure::test_organs_tree_is_armed_and_absent`
— its companion absence assertion trips RED now that framework/organs
landed, per its own RETIREMENT CONDITION (delete the skip; fold
framework.organs / .registry / .descriptor into `_SCHED_LANDED_MODULES`) —
the exact W3-landing surgery precedent recorded in that file's header. The
unit battery already runs the identical closure scan over all three organs
modules (superset fenced set) and it is GREEN, so the surgery lands green.

**Gates run before commit (this tree):**
- Full `cabinet/scripts/tests` sweep: **3149 passed, 32 skipped, 1 failed**
  — the one failure is the routed companion assertion above; baseline
  (pre-change, same clone) was 3094 passed / 33 skipped / 0 failed; skip
  diff = exactly the organs vacuity skip converting to the designed
  companion failure (measure-only skips differ only in re-recorded timing
  text). 3094 + 55 new = 3149 — no previously-passing test regressed.
- `framework/tests`: 1066 passed, 1 skipped.
- `cog2-import-gate.py`: exit 0 (rows 4/5/6/7 bite over the landed organs
  tree; organs package clean).
- `check-layer-separation.sh`: OK, new=0.
- `cognitive-architecture-census.py`: green at observed==max after the
  allowance rows (expected-RED → allowance path, never conflated with a
  STOP).
- AST pins: parity + dispatch pins green (vacuity skips unchanged);
  scheduler pin green except the routed companion.

**Model routing note (§14.3):** built on Fable 5 as the named
Fable-for-execution unit (the descriptor/adapter class).

Provenance: per the 2026-07-07 full-autonomy grant + the Captain 2026-07-20
cognitive-masterplan continuous grant; COG-4 W4 u1.
