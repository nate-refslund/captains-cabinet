# Cognitive Core Phase 0 — Executable Contract Implementation Plan

**Parent:** `docs/cognitive-core-foundry.md`  
**Baseline:** `8f9c555d2064d55a159a53fcedd6df33434a9291`, CI run `29687917451` green  
**Behavioral floor:** 2,050 targeted tests passed (2,040 compatibility plus 10 extension-gate tests), five skipped; the same commands reproduce those counts on the pinned baseline  
**Runtime posture:** additive, import-inert, no service, no event emission, no store mutation, no authority change

## 1. Purpose

Phase 0 converts the architecture from persuasive prose into executable constraints before any runtime migration. It provides:

1. a machine-readable contract for architectural budgets and ownership;
2. a deterministic, gitless-compatible census that checks the largest centralization pressures;
3. the immutable trajectory contract future Cortex and Foundry phases exchange;
4. tests with mutants proving the contracts reject central-registry growth and Goodhart-prone trajectory shapes;
5. the masterplan and a review artifact mapping implementation evidence back to its gates.

It does not implement envelope v2, a world model, a scheduler, a league, or a promotion path.

For every later phase component, the masterplan requires a `reuse | extend | compose | retire | new` disposition. Phase 0 therefore records architecture, language, and budgets only; it must not create placeholder implementations that future phases feel obliged to preserve.

## 2. Proposed file surface

| File | Purpose |
|---|---|
| `cabinet/config/cognitive-architecture-contract.yml` | Repository baseline, shrink-only budgets, domain/projection ownership declarations, declared program invariants, and the closed portable architecture gate. Build/runtime facts do not live in the universal framework layer; the census does not pretend declarations are enforcement. |
| `cabinet/scripts/cognitive-architecture-census.py` | Pure read-only census with `--root`, `--json`, and `--check`; no git or runtime state. |
| `cabinet/scripts/tests/test_cognitive_architecture_census.py` | Positive baseline plus central-event/action/service growth mutants and gitless-copy proof. |
| `cabinet/scripts/tests/test_cognitive_phase0_rollback.py` | Exact inverse-manifest inventory. Private-side phase test, excluded from the public egg and run only by the source-instance landing gate. |
| `cabinet/scripts/verify-cognitive-architecture.sh` | Portable enduring gate for the architecture contract, trajectory contract, census mutants, and layer boundary. Ships and runs in a public egg. |
| `cabinet/scripts/verify-cognitive-phase0.sh` | One complete committed-tree exit gate; it refuses to run without a frozen `Verdict: PASS` review and includes every subordinate proof below. It additionally refuses a dirty tree, an untracked review artifact, and a scope-digest mismatch, and ends `READY_FOR_CI` (never a CI-green claim). Private-side phase tooling, excluded from the public egg. |
| `cabinet/scripts/cognitive-phase0-review-scope.py` | Mechanical review-to-bytes binder. Canonical SHA-256 over the sorted committed-tree `(mode, blob-sha, path)` of the 20 Phase-0 implementation paths (manifest-single-sourced; review artifact and both operative ledgers excluded). `--print` records the digest; `--verify` re-derives it over HEAD and refuses on drift. Private-side; excluded from the public egg. |
| `cabinet/scripts/cognitive-phase0-rollback-rehearsal.py` | Executes the declared inverse in a disposable worktree and proves only append-only operative history remains. Private-side phase tooling, excluded from the public egg. |
| `cabinet/scripts/egg-export-manifest.txt`, `cabinet/scripts/null-hatch.sh`, and `cabinet/scripts/tests/test_egg_export.py` | Pin the living contracts into the public egg and exercise them in a clean hatch. |
| `framework/evolution/__init__.py` | Package boundary only; no import-time work. |
| `framework/evolution/contracts.py` | Pure trajectory normalization, externally resolved receipt validation, authority-catalog binding, and canonical fingerprint. |
| `framework/evolution/tests/test_contracts.py` | Scope, time fence, truth-channel relabeling, receipt forgery, authority parity, holdout isolation, and deterministic fingerprint tests. |
| `framework/schemas/cognitive-trajectory.schema.json` | Language-neutral observation-only v1 shape; raw content stays in content-addressed artifacts. |
| `framework/schemas/holdout-evaluation-receipt.schema.json` | Oracle-owned aggregate-only holdout receipt; no cases, case fingerprints, or per-case results. |
| operative egg ledger + plan parity rows | One existing execution-state joint for `COG-0` through mandatory compaction `COG-7` and optional federation `COG-8`; no competing program ledger. |
| masterplan + this plan | Human intent, phase gates, and rollback. |
| `docs/plans/cognitive-core-phase-0-rollback-manifest-2026-07-19.yml` | Exact remove/restore/retain inverse for a scratch rollback rehearsal. |
| `shared/interfaces/reviews/codex-cognitive-foundry-masterplan-cp1.md` | Independent review findings, fixes, commands, and plan-parity verdict. |

No listed file is in the germline set at the baseline. The phase must re-check this immediately before editing and before commit.

## 3. Contract decisions

### 3.1 Architecture budgets

The census checks the largest pressures that otherwise grow silently:

- central event enum: at most 91;
- central action enum: at most 30;
- services manifest: at most 57 rows and 44 enabled;
- layer separation: existing checker remains authoritative at 24 debt and 19 ratified allowlist entries, with zero new violations;
- framework production size: base maximum 206 non-test modules and 60,067 non-comment lines; Phase 0 records its exact temporary allowance of two modules and 1,256 lines with a dated `COG-7` deletion gate;
- named production compiler modules: at most one;
- the known event-emitter duplicate-authority family: at most three `_write_to_*` sinks called from `emit`.

The budgets are not claims that the counts are intrinsically optimal and never justify deleting a necessary safety boundary. They force future phases to add domain schemas/effects and composed cognition instead of expanding central concepts. A phase that truly needs a temporary shadow component must keep it disabled/manual, retire or merge an equal permanent surface, or add a time-bounded allowance to this contract with a named phase, fault-boundary reason, owner, sunset, and deletion gate. Silent growth still fails.

### 3.2 Trajectory separation

A `cognitive-trajectory/v1` record contains:

- authority_scope (stable organizational authority): `cabinet_id` always; `scope_kind: cabinet | lane | project`; `lane_id` required for lane/project scope; `project_id` required only for project scope. Missing levels are absent, never inferred defaults;
- execution_scope (transient run identity): `run_id`, `correlation_id`, and `causation_id`;
- genome: candidate id/version and incumbent champion id/version, all externally bound with the exact component set by a pre-cutoff genome-manifest receipt;
- timing: started, decision cutoff, and completed timestamps;
- intent: content-addressed objective and constraint references, never raw bodies; compiler-produced objectives resolve an immutable root to an authenticated Captain direction and constraints are Captain/constitutional-authority attested;
- content-addressed input snapshots with externally bound id, artifact, authority_scope, and maximum content/recorded times;
- per-span closed/acyclic causation, completed/failed/aborted status, manifest/snapshot-constrained genome and input references, model/tool/skill/context/output references, output-or-prediction proof for completion, bound failure receipts otherwise, fixed-point confidence, timestamps, and externally metered local costs;
- effects identified by canonical `action_type`, with request/decision/attempt/observation time, idempotency, separate classification and authority allow/deny, execution, and undo receipt references resolved against the existing authority/evidence joints rather than a second enum; denied attempts and violations remain valid observations;
- independent machine outcomes that name causal basis, a declared span-output/effect target, and a post-target measurement window; only fresh interventions satisfy machine evidence, while observational/baseline/correction rows remain context;
- authenticated human verdicts and LLM/automated judge observations in disjoint fields;
- `evaluation_basis: machine_verifiable | human_judgment | mixed`;
- externally metered total cost vector, privacy classification, and a trusted run-recorder attestation over every trajectory claim except its own pointer.

The trajectory is observation-only. It contains no promotion, eligibility, fitness, graduation-credit, or holdout-case field. A trusted validation context outside the record resolves every receipt digest and binds Cabinet, actor, kind, subject, content time, recorded time, and channel. A trajectory-recorder attestation binds record kind, authority and execution scope, decision window, intent, genome, spans, outcomes, evaluation basis, and costs as one immutable body. Objective compiler receipts bind the exact scoped objective and resolve an immutable root to a Captain-direction attestation. Snapshot receipts bind id, artifact, maximum content time, and authority_scope. Outcome/effect/verdict receipts additionally bind trajectory, run, and candidate identity; machine receipts bind causal basis/target, measurement window, metric, value, status, and observation time; resource receipts bind span and total costs; the genome manifest binds candidate/incumbent identity and component set. Machine outcomes accept only machine receipts; Captain verdicts only Captain attestations; judge observations only judge artifacts; effects require separate classification, authority-decision, effect-outcome, and undo receipts. Missing or unverifiable receipts remain unknown/ineligible. The existing Gate alone joins the immutable trajectory fingerprint to independently verified consequence, private-benchmark, and frozen-holdout receipts.

Validation refuses:

- an invalid hierarchical authority_scope, including project without lane, lane/project ids at the wrong scope kind, a missing Cabinet id, or inferred/sentinel authority scope; a missing run, correlation, or causation id in execution_scope;
- blank/sentinel run, correlation, causation, or genome identities;
- invalid ordering or non-UTC started/cutoff/completed/observation times;
- no objective reference;
- outcomes that mix judge scores into machine outcomes;
- judge observations relabeled as human verdicts, or human verdicts without authenticated Captain provenance;
- unresolved, digest-mismatched, cross-Cabinet, post-cutoff, or missing-content-time input/evidence receipts;
- judge artifacts used as machine evidence, self-labeled Captain attestations, or fabricated paired receipts;
- candidate/system-minted objective roots, unbound constraints, or scoped intent receipts that diverge from the trajectory's authority_scope;
- effect `action_type`/risk mappings that diverge from the existing classifier/matrix catalog, classification substituted for authorization, or any effect whose allow/deny decision, idempotency, execution status, or undo contract is not externally bound; denied/violating effects remain observations but never implicit success;
- duplicate snapshot/span/effect/outcome/verdict/observation ids, one-to-one receipt replay, foreign genome credit, undeclared inputs, provenance-empty completed spans, fabricated failed spans, or a broken causal tree;
- unlinked or stale intervention outcomes, measurement before cause, or baseline/correction/observational rows used as candidate credit;
- receipt content after recording, run-bound receipts before the run, classification/undo after the authority decision, or outcome/verdict evidence recorded before its observation;
- self-reported or non-additive costs, non-wall-clock total latency, and non-canonical numeric/timestamp spellings;
- unknown/abstain observations used as evidence completeness;
- private/holdout inputs, outputs, case bodies, fingerprints, per-case scores, decryption material, arbitrary threshold keys, or arbitrary extension blobs; holdout threshold ids must exactly match the trusted opaque suite registry;
- non-finite, negative, or non-portable integers and over-complex/oversized envelopes;
- fields not admitted by the schema.

The contract does not compute fitness or promotion. It cannot mutate a candidate, Gate, champion pointer, or live runtime.

`framework/schemas/cognitive-trajectory.schema.json` is authoritative for structural shape. A complete stdlib interpreter covers the schema subset used by v1; CI cross-checks the same structural corpus against `jsonschema`. Python adds only the named semantic rules above. Structural fixtures must agree. Semantic-only invalid fixtures must pass schema and fail Python with an expected named semantic error. Every rejection is classified `structural` or `semantic`; unclassified divergence fails the suite.

### 3.3 Fingerprint

The canonical SHA-256 is computed over normalized JSON with sorted keys. Sequence-bearing spans/effects/outcomes preserve order; declared set-like reference collections are sorted canonically and reject duplicates. All numeric contract fields are fixed-point integers (confidence uses parts-per-million; spend uses integer micro-units), integral JSON spellings normalize identically, and timestamps admit one UTC-second spelling. The trajectory contract never calls the clock or randomness. Equivalent key, set, or integral-number ordering/spelling yields the same fingerprint; any semantic change changes it. The architecture census is path-independent and deterministic for identical bytes plus an explicit `--as-of` date; without `--as-of`, only temporary-allowance expiry intentionally consults the local date.

## 4. Tests-first sequence

1. Add failing trajectory tests and the schema fixture.
2. Add failing census tests against a minimal copied tree.
3. Run tests to prove the implementation is absent or rejects the valid case.
4. Implement only enough pure code to make the contract pass.
5. Run negative controls:
   - insert a 92nd central event type;
   - insert a 31st central action type;
   - append a 58th/45th-enabled service;
   - inject or rename a nested holdout payload and attempt smuggling through every remaining string field;
   - relabel a judge receipt as a machine outcome while preserving destination shape;
   - relabel a judge observation as a human verdict or provide a self-labeled/fake Captain receipt;
   - pair fabricated consequence/private/holdout references and prove they confer nothing;
   - record a verified effect without separate externally resolved classification/authority-decision/effect/undo receipts, substitute classification for permission, or preserve a denial/violation as positive credit;
   - duplicate snapshot/other ids or receipts, import a foreign genome component/undeclared snapshot, complete a provenance-empty span, fabricate a failed span, or break the causal tree;
   - mint an objective without an authenticated Captain root, rebind its scope, or use a candidate-authored constraint;
   - credit an unlinked/old machine outcome, start measurement before its declared cause, or relabel a baseline/correction as intervention evidence;
   - submit huge integers or oversized/cyclic envelopes and prove validation returns bounded issues rather than throwing;
   - erase metered costs or make total additive costs/latency inconsistent;
   - remove `authority_scope.cabinet_id` or `decision_cutoff_at`;
   - prove valid Cabinet-wide and lane-wide authority_scope, then reject project-without-lane and a cross-Cabinet authority-scope mismatch;
   - add post-cutoff evidence and a late-recorded pre-cutoff correction outcome;
   - permute set-like references and integral JSON spellings without changing the fingerprint, reject duplicates/noncanonical times, then mutate one objective/effect and assert the fingerprint changes;
   - remove each architecture-contract invariant section, add unknown keys/budgets, and mutate the protected enum through reassignment, augmented assignment, and mutating calls;
   - remove one enum/service/debt row and prove shrinkage stays green.
6. Copy only the census fixture to a directory without `.git` and re-run `--check`.
7. Run the focused tests under `python3.12` on macOS and through CI's Linux job.

The mutants live in temporary directories or in-memory mappings. Tests never edit the checkout, safety switches, runtime ledgers, or live stores.

## 5. Review loop

Before implementation, independent reviewers must answer:

- Does this phase accidentally create a competing Gate, evidence schema, event registry, or store?
- Does “logical membrane” preserve independent hook, `schg`, Seatbelt, and broker failure domains?
- Are the budgets enforceable without freezing necessary domain evolution?
- Can the trajectory contract leak hidden holdout content?
- Do JSON Schema and Python agree on the structural corpus, and are all semantic-only divergences explicitly named and tested?
- Is any field Captain/product/officer-specific?
- Does the census parse source deterministically without imports, git, or shell tools?
- Are the tests meaningful negative controls rather than self-confirming fixtures?
- Does the phase preserve fresh hatch, egg export, Linux CI, and the existing launch program?
- Does any contract become an officer-visible scalar or a selection input, violating the never-a-score law?

Any blocker causes a plan revision before code. After implementation, a fresh reviewer compares the staged diff against this plan and the masterplan. The checkpoint artifact records every finding and fix.

## 6. Verification commands

Focused pre-commit:

```bash
python3.12 -m pytest \
  framework/evolution/tests/test_contracts.py \
  cabinet/scripts/tests/test_cognitive_architecture_census.py -q
python3.12 cabinet/scripts/cognitive-architecture-census.py --check
bash cabinet/scripts/check-layer-separation.sh
```

Compatibility floor:

```bash
python3.12 -m pytest \
  framework/authority/tests framework/acting/tests framework/attention/tests \
  framework/events/tests framework/outbox/tests framework/missions/tests \
  framework/sources/tests framework/ovi/tests framework/triggers/tests -q
python3.12 -m pytest cabinet/scripts/lib/tests/test_install_extensions_gate.py -q
```

Repository gates after commit, because export/archive gates read `HEAD`:

```bash
bash cabinet/scripts/run-golden-evals.sh
bash cabinet/scripts/docs-track-code-sweep.sh
bash cabinet/scripts/check-layer-separation.sh
python3.12 -m pytest cabinet/scripts/tests/test_egg_export.py -q
bash cabinet/scripts/null-hatch.sh
```

The enduring architecture contract points only to the portable gate that ships:

```bash
bash cabinet/scripts/verify-cognitive-architecture.sh
```

The authoritative source-instance landing gate is not any abbreviated subset
above. It is:

```bash
bash cabinet/scripts/verify-cognitive-phase0.sh
```

That command additionally binds the frozen review verdict to the exact tested
bytes with a committed-tree scope digest, refuses a dirty tree, checks ledger
id/A13 parity, runs the scratch inverse rehearsal, and ends `READY_FOR_CI`
rather than claiming CI is green. The three one-time Phase-0 gate
scripts depend on source-instance planning/review history and are therefore
explicitly removed from the public egg; the enduring verifier, contract,
census, schemas, and pure evolution validation package ship and are exercised
by null hatch. COG-0 flips to `done` only after the push lands, every branch CI
job is green per-job, and the resulting SHA and run-id are recorded, in a
status-only commit that touches only the two out-of-scope operative ledgers so
the scope-digest binding is preserved.

The branch then merges current `origin/master`, repeats focused and fast gates, pushes without force, and inspects every job of the resulting master CI run.

## 7. Exit evidence

Phase 0 is done only when:

- architecture census matches or improves the pinned baseline;
- every count-growth mutant fails and the original passes;
- valid trajectory passes, every malformed/Goodhart mutant fails, and fingerprint tests pass;
- focused tests, compatibility floor, layer separation, docs, golden evals, export/null-hatch, and every CI job are green;
- no runtime file, service manifest row, event log, runtime/business store, authority file, or germline file changed;
- operative ledger and plan rows are unique, in parity, and report later phases as `todo` rather than implying they are built;
- independent review says implementation matches both plans and the frozen `Verdict: PASS` artifact records a `Reviewed-Scope-Digest` that the committed-tree gate recomputes and matches;
- rollback is proven from an explicit inverse manifest in a scratch checkout: new implementation files are removed, while append-only operative ledger/plan rows remain and receive a supersession/rollback note; the pre-phase compatibility suite remains unchanged.

The inverse is machine-readable at `docs/plans/cognitive-core-phase-0-rollback-manifest-2026-07-19.yml`. New Phase-0 paths are removed; the three pre-existing export/hatch files are restored from the pinned baseline; the operative ledger and plan are deliberately not reverted or row-deleted. Their `COG-0` through `COG-8` rows remain and receive matching dated rollback notes, preserving the ledger's status vocabulary and history.

## 8. Phase-1 handoff, not implementation

The next detailed plan must compare at least two pilot domains and select one using blast radius, existing transaction boundary, current outbox need, testability, and lock/active-wave collision. It then designs:

- envelope v2 with v1 compatibility;
- a schema registry interface local to each domain;
- one domain-owned transaction plus outbox row;
- a relay with adapter-level idempotency;
- mirror/parity/cutover/rollback;
- the full crash and concurrency matrix from Masterplan Phase 1.

No second domain starts until the pilot has landed, master CI is green, crash simulations pass, and its rollback has been rehearsed.
