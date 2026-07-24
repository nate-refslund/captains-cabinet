# feat/cog4-w4 — W4 LANDING checkpoint 1 (integration + corpus surgery)

Date: 2026-07-24 · Integrator: orchestrator landing agent (Fable 5)
Provenance: per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant; surgery per §13 + the unit
contradictions[] routes, W4 landing 2026-07-24.

## Units landed + review chains

| unit | tip | review chain |
|------|-----|--------------|
| v1 — the ORGANS package (framework/organs: registry + ONE-descriptor, MF-A1) | 1adbb33f | SHIP first-pass |
| v2 — the PARITY CLI (cabinet/scripts/cog4-parity.py, §5.3 N9) | 9df66b12 + fix dc14c0e6 | FIX_FIRST (1: namespace fail-open — flat operation ids accepted at setup) → fixed (exit 3 refusal + regression test) → SHIP |
| v3 — trajectory v2 schema + version-dispatched contracts (§5.5 MR5) | 2c2252a9 (cherry-picked as 0ac8db56) | SHIP first-pass |

Topology: v2 CONTAINS v1 by ancestry — feat/cog4-w4 branched from v2's tip;
v3 cherry-picked on top. ONE conflict, exactly as forecast:
`cabinet/config/cognitive-architecture-contract.yml` (v1 extended the COG-4
line allowance off master; v3 extended off master independently).

## Allowance reconciliation (measured, never hand-computed)

COG-4 `framework_production_noncomment_lines` allowance:
HEAD-side 1378 (organs +405, running 66390) ⊕ v3-side 992 (trajectory
dispatch +19, running 66004) → integrated `additional: 1397`
(295 + 688 − 10 + 405 + 19), reason = the two clause chains merged
(… THEN W4 u1 the organs package +405 … THEN W4 trajectory-v2 version
dispatch +19 …), running total **66409 vs 65012 base**.
COG-4 `framework_production_modules` allowance: 10 (236 vs 226 base) — NOT
conflicted; v3 adds zero modules (its schema is JSON; the census counts *.py).

`cognitive-architecture-census.py --check` on the integrated tree:
**observed == effective max on every budget** — modules 236/236, non-comment
lines **66409/66409**, failures [], ok true, exit 0. Zero headroom holds.

## Corpus surgery ledger (integrator-only §13 power; each retirement follows
## the tripwire's OWN in-file retirement text)

| id | test | action | result |
|----|------|--------|--------|
| S1 | test_cog4_scheduler_ast_pin.py::TestSchedulerTransitiveClosure::test_organs_tree_is_armed_and_absent | organs landed (v1) → skip leg DELETED per its retirement text; framework.organs + .registry + .descriptor folded into `_SCHED_LANDED_MODULES` so `test_landed_trees_real_closure_is_clean` real-scans all three protected trees (the W3 precedent; v1's eight-tree battery pre-proved the scan green) | real closure scan PASSES |
| S2a | test_cog4_parity_ast_pin.py::TestParityImportPin::test_real_cli_is_armed_and_absent | CLI landed (v2) → converted to `test_real_cli_scans_clean`: live `parity_import_violations` scan over the real file + subject-present assertion | PASSES |
| S2b | test_cog4_parity_ast_pin.py::TestParityTransitiveClosure::test_real_cli_closure_armed_and_absent | converted to `test_real_cli_run_closure_excludes_executor_doors`: hermetic runpy run of the REAL CLI (empty manifest dir → the documented exit-3 zero-ops refusal AFTER the full import surface loads; fw-modules-loaded assertion proves the closure is populated, never vacuous); doors == []. The rc==0 full-pipeline closure lives in test_cog4_parity_cli.py (the battery the retirement text names) | PASSES |
| S3 | test_cog4_parity.py::TestParityGateRealArtifact::test_real_record_arm | retirement text keys on CLI **AND** record with either-artifact companions — the CLI landed while the tracked cog4-parity-record.json DELIBERATELY rides W5/W6, so the arm was converted to RECORD-existence-keyed: still ARMED (skips; companion REDs the moment a record appears or the CLI vanishes), retirement = the tracked record landing. The N9 exit tripwire never went dead | SKIPS (armed) |
| S4 | test_cog4_organ_manifest.py::TestRealSurfacesVacuityArms::test_real_trajectory_v2_schema_arm | v2 schema landed (v3) → flipped to the LIVE v2-schema validation arm per its docstring: binds the REAL Draft-2020-12 document (compat action_type passes / namespaced REDs; descriptor + domain-operation vocabulary + grammars byte-equal to the transcriptions; the two v2 additions REQUIRED) and asserts contracts.py decides version dispatch BEFORE the v1 checks (a v2-tagged record's issues are v2 judgments at `$`, never v1's schema_version const — verified against the forged-version counterfactual which DOES yield `$.schema_version`). Full landed-surface battery = test_cog4_trajectory_v2.py (v3's designed retirement of this arm) | PASSES |
| S5 | sweep law | ZERO unexplained failures on the integrated tree | 3196 P / 29 S / **0 F** |

Untouched by design: `test_real_germline_validator_arm` (the CG-33
germline-pair arm) STAYS SKIPPED — the Captain window is unopened
(HANDBACKS item 19); the schema-validated-organ-manifests micro-unit stays
PARKED per docs/plans/cog4-w4-u1-organ-schema-validation-PARKED-2026-07-24.md.
schg never worked around.

## Sweep reconciliation (exact)

cabinet/scripts/tests: master baseline 3094 P / 33 S / 0 F
→ +55 (v1 organs battery) +20 (v2 CLI battery) +1 (v2-fix regression test)
+23 (v3 trajectory battery) +3 (arms converted skip→live-pass: S2a, S2b, S4)
= **3196 passed**; skips 33 − 4 (S1 deleted; S2a/S2b/S4 → pass; S3 stays
armed-skip) = **29 skipped**; **0 failed**. Total 3225 collected =
3127 + 55 + 21 + 23 − 1 (deleted S1 leg). Observed: 3196/29/0 — EXACT match.

framework/tests: 1066 passed / 1 skipped (baseline-identical; v3's contracts
dispatch left the 47-test evolution suite green unchanged).
cog2-import-gate exit 0 · layer-sep new=0 (baseline 24 / allowlist 19) ·
verify-cognitive-architecture PASS · egg test battery 58 P / 1 S.

## Germline-untouched verification

`git diff master..HEAD -- framework/schemas/extension-manifest.schema.json
cabinet/scripts/validate-extension.sh` → **EMPTY** (three units + surgery —
none touch the schg pair).

## Egg manifest (the R1/R3 rider precedent)

Two expect-present anchors added: `cabinet/scripts/cog4-parity.py` (the N9
comparator ships with the other cog CLIs) and
`framework/schemas/cognitive-trajectory.v2.schema.json` (contracts.py
hard-routes v2 dispatch through it — an egg without it breaks at runtime;
sibling of the existing v1 anchor). Observed non-blocking gap, recorded for
a future pass: the W3 projection/scheduler packages and W4 organs package
ship by default (no delete rule touches them) but carry no expect-present
anchors — consistent with the W3 landing's choice, left unchanged here.

## Post-push CI fix (cp1 addendum, 2026-07-24)

PR-range gitleaks REDs on two generic-api-key false positives in v3's
trajectory battery (the fake fixture `idempotency_key:
"garden-rota-week-30"` — digits crossed the entropy bar). Fixed by the
recorded house pattern (the PR #139 / organ-manifest:495 precedent):
value de-entropied at HEAD to the W2 twin's `"garden-rota"` (schema
$defs/id still satisfied; no test pins the value) + the introducing
cherry-pick's two fingerprints appended to .gitleaksignore. No history
rewrite; egg/tree bytes clean post-fix, so no no-git twins.
