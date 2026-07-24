# Checkpoint review — feat/cog4-w4-v2, cp1 (COG-4 W4 v2: the PARITY CLI, §5.3)

**Scope (one commit, >300 lines → FW-019 artifact required; this is it):**
1. `cabinet/scripts/cog4-parity.py` — the N9 outcome/evidence parity
   comparator, THE one sanctioned dual-plane importer (§5.3, MF-A1;
   boundary-manifest allowlists it for framework.organs and deliberately
   NOT for framework.scheduler nor the schedule-store data plane). Per
   declared organ operation it computes TWO INDEPENDENT tuples
   `(risk_class, ceiling, undo_contract, shadow_verdict)`:
   * leg (a) descriptor path — organs PUBLIC surface only
     (`load_organ_registry` + `resolve_descriptor`; manifest-declared
     constitutional members verbatim);
   * leg (b) ACTION_TYPES path — its OWN raw scan of the same loaded
     manifests (never leg a's output): `classify_action(tool_name,
     tool_input)` where the injected `--tool-map` carries a mapping for the
     operation, else the manifest's DECLARED compat member (leg b's own
     merge of the §5.2 block + per-op override); matrix-derived risk_class
     via `risk_of` over the loaded policy's `risk_classes`; ceiling from
     the policy's `ceiling_frozenset_map` (hard-ceiling class → its
     HARD_CEILING_TOUCHES member, else the empty set), sanity-checked
     against `ceiling_members()` + `RISK_CLASSES`.
   * shadow verdict per leg from the leg's OWN (risk_class, action_type):
     cell state → `resolve_verdict` over the policy tables. HERMETIC mode
     (default — the deterministic record): `graduation.evaluate` on the
     `ledger=`/`now=` seams (empty ledger ⇒ honestly unmeasured), folded
     through the `read_cell_state` fail-closed mapping (exception→demote,
     None→unmeasured, out-of-vocab→demote), and `_act_with_undo_gap` is
     NEVER called (its probes import framework.acting/frontdoor at call
     time — the §8.4 closure law + canonical-bytes determinism both forbid
     it on the record path). LIVE mode (`--live-state`): `read_cell_state`
     + the act_with_undo → propose_only undo-gap fall-through — the
     §7.3-faithful joint; documented machine-state-dependent, never the
     tracked record.
   * output `cog4-parity-record.json`: canonical bytes (compact,
     sort_keys, ensure_ascii=False, utf-8), rows sorted by operation,
     ceilings sorted (set semantics), schema `cog4-parity-record/v1` — the
     exact W2 reference shape. Record written ONLY when every operation
     resolves on both legs; divergent rows ARE written (the evidence).
   * exit contract: 0 = zero divergent tuples; 2 = divergences and/or
     unresolved operations (list printed; structural build failure, never a
     warning); 3 = setup failure (unusable inputs; zero declared operations
     = the R-A non-empty refusal; tool-map naming undeclared ops).
2. `cabinet/scripts/tests/test_cog4_parity_cli.py` — NEW battery (20
   tests; §13: corpus immutable, new files sanctioned): clean fixtures
   (garden-rota non-software idiom + a ceiling-class organ) → exit 0 and
   the record passes the W2 REFERENCE checkers imported from
   `test_cog4_parity.py` (`record_errors`/`divergent_rows` — the same
   functions the retired N9 arm will gate the tracked record with);
   hermetic semantics pinned (read_only_dispatch→notify_after,
   external_comms→always_gated, per-op undo override reaching BOTH legs'
   independent merges); byte-determinism across runs; empty-seeded-ledger
   == default; --live-state over CABINET_EVENT_LOG_DIR=empty-dir ==
   hermetic bytes; N-d divergence (declared reversible under
   external_email compat) → exit 2 + members named + the record REDs under
   the W2 divergent_rows checker; single-member divergence named without
   blanketing; tool-map arms (consistent green / inconsistent diverges /
   undeclared-op setup failure); fail-closed arms (ambiguous compat →
   UNRESOLVED exit 2 + NO record; duplicate declarers; missing dir; zero
   ops; garbage ledger; mode exclusion); the §8.4 pin over the REAL file
   (`parity_import_violations(REPO) == []`); the run-closure law over the
   REAL file (runpy: no framework.acting/frontdoor in the hermetic run's
   module closure — the exact check the corpus closure arm's RETIREMENT
   CONDITION names); reversible-class hermetic verdict = act_with_undo
   verbatim (no gap probe); a no-stray-record-in-repo tripwire.

**Independence law (the §15 standing panel question):** leg (b) never reads
leg (a)'s output — behaviorally proven by the divergence arms (a derived leg
could never diverge). The legs share only loaded INPUTS (registry record's
raw manifests, matrix policy, tool map) and the pure verdict derivation
applied to each leg's own (risk_class, action_type).

**Designed corpus flips (routed to the integrator, §13 — never edited
here):** landing the CLI flips three W2 vacuity companion assertions
skip→FAIL exactly per their docstrings ("the skip cannot silently
persist"): `test_cog4_parity.py::TestParityGateRealArtifact::
test_real_record_arm` (CLI landed; tracked record still absent — retire per
its RETIREMENT CONDITION at W5/W6 when the tracked record lands),
`test_cog4_parity_ast_pin.py::TestParityImportPin::
test_real_cli_is_armed_and_absent` and `::TestParityTransitiveClosure::
test_real_cli_closure_armed_and_absent` (retire the skips; the real-file
pin + closure checks are ALREADY live in the new battery meanwhile). The
fourth pre-existing tripwire (`test_cog4_scheduler_ast_pin.py::
test_organs_tree_is_armed_and_absent`) is v1's, unchanged.

**Verification on this tree:** full sweep 4 failed / 3169 passed / 29
skipped — baseline was 1 / 3149 / 32; delta = +20 new tests passing, the 3
designed flips above (−3 skips), nothing else. cog2-import-gate exit 0;
census green with ZERO framework delta (modules 236==236, lines
66390==66390 — cabinet-side unit, budget-exempt; COG-4 allowance rows
untouched at v1 totals); layer-sep exit 0; §8.4 pin clean over the landed
file; no yml/json committed (py + md only). Corpus untouched:
`git status --porcelain` shows only the two new files.

Provenance: per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; Fable-for-execution named unit
(Captain 2026-07-23 calibration). Model of record: claude-fable-5.
