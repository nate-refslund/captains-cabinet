# Checkpoint review — feat/cog4-w4-v3, cp1 (COG-4 W4, trajectory v2 — §5.5 MR5)

**Scope:** the W4 TRAJECTORY V2 unit of the COG-4 contract
(`docs/plans/cognitive-core-phase-4-contract-2026-07-23.md` §5.5 + §5.2), off
`origin/master` `71171c16`. Two production surfaces land + one NEW test file +
the census allowance bump. Over the FW-019 300-line threshold (the v2 schema is
~430 lines, the new test ~370) → this artifact is required.

`git status --porcelain` — exactly four work files, nothing else:
- `M framework/evolution/contracts.py` (+19 non-comment lines — version dispatch)
- `M cabinet/config/cognitive-architecture-contract.yml` (census allowance bump)
- `?? framework/schemas/cognitive-trajectory.v2.schema.json` (NEW)
- `?? cabinet/scripts/tests/test_cog4_trajectory_v2.py` (NEW)

The v1 schema (`cognitive-trajectory.schema.json`), the germline pair
(`extension-manifest.schema.json` + `validate-extension.sh`), and the W2-t3
corpus (`test_cog4_organ_manifest.py`) are BYTE-UNTOUCHED (`git status
--porcelain --` on each is empty). Corpus law §13 + germline-absolute honored.

## 1. `framework/schemas/cognitive-trajectory.v2.schema.json` (NEW, full Draft-2020-12)

The v1 document reproduced verbatim (every top-level field, every `$def`, the
`allOf`/`if`/`then`/`else` idiom, `additionalProperties:false`) with FOUR
deltas, all §5.5-mandated:
1. `$id`/`title` → v2; `schema_version` const → `"cognitive-trajectory/v2"`.
2. The `effect` def KEEPS every v1 field INCLUDING `action_type`, and ADDS
   `domain_operation` + `enforcement_descriptor` to both `properties` and
   `required` (v1's 11 required → 13; the `attempted_at` conditional `allOf`
   kept verbatim). Proven by `test_v2_effect_keeps_every_v1_field_and_adds_the_two_required`.
3. `action_type` retyped from `#/$defs/id` (which admits `/`) to a NEW
   `#/$defs/compatActionType` whose pattern `^[A-Za-z0-9][A-Za-z0-9._:-]*$`
   EXCLUDES `/` — the never-overload law (charter L184 / §5.5): a namespaced id
   in `action_type` fails structurally. All 30 real `ACTION_TYPES` members match
   this pattern (none carry `/`) — verified live against
   `classifier.ACTION_TYPES`, so a legit compat member is never rejected.
4. New `$defs`: `domainOperation` ({organ non-empty, operation namespaced},
   `additionalProperties:false`, both required); `enforcementDescriptor` (the
   §5.2 block — capability namespaced, action_type compat, risk_class the
   inline 13-enum, ceiling string-array, undo_contract the FULL grammar
   `^(none|delete_window\([0-9]+\)|journal:...)$`); `namespacedId` (`^[a-z0-9_-]+/[a-z0-9._-]+$`,
   the §4.2 shape). The 13-member risk_class enum is grounded to
   `authority_matrix.RISK_CLASSES` by a drift-pin test — vocabulary drift REDs.

The document uses only the closed Draft-2020-12 subset the `contracts.py`
interpreter implements ($ref/allOf/if-then-else/not/anyOf/const/enum/type/
required/properties/additionalProperties/minItems/minLength/pattern/min-max) —
verified by running the real `contracts._structural_issues` against it. The
"status refs" of the §5.2 block (status_vocab + idempotency_key + the four
receipt refs) live at the EFFECT level (kept from v1), NOT duplicated inside
`enforcement_descriptor` — matching the W2-t3 `_valid_v2_effect()` reference.

## 2. `framework/evolution/contracts.py` — version dispatch (the envelope clone)

Decided BEFORE the v1 closed-set check, cloning
`framework/triggers/envelope.py::validate_any` byte-for-shape:
- `_is_v2_record(record)` — the marker test: a mapping whose `schema_version`
  is EXACTLY the v2 literal. (Trajectory's two versions BOTH carry
  schema_version, so the marker is the literal value, not the envelope's
  absent-vs-present.)
- `_structural_issues_v2(record)` — a distinct seam (mirrors `validate_v2`) so
  the dispatch is provable by monkeypatch.
- `structural_issues(record)` — dispatches: v2-marked → the v2 schema; EVERY
  other input (v1 literal, absent/forged version, non-mapping) → the FROZEN v1
  path `_structural_issues(record, TRAJECTORY_SCHEMA)`, byte-for-byte.

`semantic_issues` + `validate_trajectory` + `canonical_fingerprint` are
UNCHANGED — they route through `structural_issues`, so a valid v2 record runs
the v1 semantic checks over its shared fields (`action_type` validated against
`context.action_risk_map` at semantic-check time, §5.5). No new semantic
enforcement-descriptor consistency check is minted — that is the §5.3 parity /
§4.3 organ-manifest layer's job, not contracts.py's.

**v1 byte-identity proven:** the existing `framework/evolution/tests/
test_contracts.py` (47 tests, incl. the reference-jsonschema agreement test)
is GREEN UNCHANGED. No existing mutation touches `schema_version`, so every v1
record routes to the frozen path with identical results.

## 3. Census (§11) — allowance bumped to the exact measured total

The census counts only `*.py` under `framework/` (`_production_python_files`
uses `rglob("*.py")`; `_non_comment_line_count`). Verified: the new `.json`
schema adds ZERO modules and ZERO lines; only `contracts.py` (+19 non-comment)
counts. The COG-4 `framework_production_noncomment_lines` allowance is bumped
973 → 992 (running total 65985 → 66004) with an em-dash reason; the COG-4
modules allowance (233) is UNCHANGED (no new module). Census PASS at
66004 <= 66004; YAML parses; no duplicate keys.

## 4. Tests (NEW file, §13 corpus-immutable honored)

`cabinet/scripts/tests/test_cog4_trajectory_v2.py` (23 tests, all green) binds
the REAL landed surface: the accept/reject table (namespaced action_type, the
two missing required members, domain_operation shape, the five descriptor
members, undo grammar, status enum, attempted_at conditional); the dispatch
matrix (valid v2 not refused by v1 const; v1 frozen byte-identical;
forged-version → v1 → rejected; v2-body-tagged-v1 dies on the closed set;
v1-body-tagged-v2 dies on missing fields; non-dict never raises); the wiring
pins (v2 route goes THROUGH the seam; v1/forged never reach it — monkeypatch);
a full garden-rota v2 fixture instance; drift pins to the real matrix +
ACTION_TYPES.

## Verification (all commands re-runnable)

- `test_contracts.py`: 47 passed (v1 byte-identity).
- `test_cog4_trajectory_v2.py`: 23 passed, 0 skipped.
- FULL `cabinet/scripts/tests` sweep: **1 failed, 3117 passed, 32 skipped** —
  the ONE failure is the routed contradiction below; no other regression.
- `cog2-import-gate.py`: exit 0 (boundary intact — no organs/scheduler import
  added).
- §8.4 AST pins (scheduler/dispatch/parity/objectives): 141 passed, 4 skipped
  (unaffected).
- layer-sep: exit 0, no new violations.
- census: PASS (66004 <= 66004; 233 <= 233).

## ROUTED CONTRADICTION (for the integrator — §13, corpus-immutable)

`test_cog4_organ_manifest.py::TestRealSurfacesVacuityArms::
test_real_trajectory_v2_schema_arm` moves SKIPPED → FAILED the moment this
unit lands the v2 schema. This is BY DESIGN: its own docstring is a RETIREMENT
CONDITION ("retire this skip when …cognitive-trajectory.v2.schema.json lands")
and its companion `assert not v2.exists()` is the tripwire that "REDs the
moment the schema lands, so the skip cannot silently persist." The builder MUST
NOT edit the corpus (HARD RULE 5 / §13). **Integrator action:** retire the skip
and bind the arm to the real surface — validate a FULL v2 effect against the
landed schema (PASS) and a namespaced-action_type effect (RED), and assert
`contracts.structural_issues` decides version dispatch before the v1 checks.

**Heads-up for that retirement:** the corpus's `_valid_v2_effect()` (lines
490-505) is a 6-field PARTIAL reference (matched to the partial
`v2_effect_errors` checker) — it lacks the v1 receipt refs + timestamps the
FULL v2 schema requires ("keeps every v1 field", §5.5). It will NOT pass the
real schema's `#/$defs/effect` as-is; use a full effect (this unit's test
`_v2_effect()` is a ready model) or validate at the enforcement sub-shape.

This is the only skip-state change; the germline vacuity arm stays correctly
SKIPPED (germline pair untouched, window unopened).

## Reviewer verdict sought
Confirm: envelope-precedent fidelity of the dispatch; v1 byte-identity;
schema faithfulness to §5.2/§5.5; census exactness; and the routed-contradiction
disposition.
