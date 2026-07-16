# FW-019 checkpoint review — Evidence Phase 1 foundation (cp1)

**Branch:** `feat/evidence-phase1-foundation` (off `eef927f4`)
**Batch:** Phase 1 of the whole-cabinet evidence & self-improvement design
(2026-07-16) — "one ceremony, zero behavior change." Four pre-authored,
pre-critiqued group patches (vocab / helper / anchor-retention / laws)
composed by the integration engineer.
**Diff:** 29 files, ~+6.9k / −224 (over the 300-line FW-019 threshold →
this artifact).
**Amendment:** `docs/proposals/germline-amendment-evidence-phase1-2026-07-16.md`
(the ceremony set: 12 schg paths; NO lock-boundary extension).
**Reviewer:** integration+verify engineer (Fable 5). Each group was authored
and adversarially reviewed in its own lane; this checkpoint verifies the
COMPOSITION — the groups land intact together, the seams between them hold,
the hard invariants survive, and the fast deterministic gate battery is
green.

## The contract that ranks everything

Phase 1 must add vocabulary, one producer seam, retention dials, anchoring,
and laws **without changing a single behavior**: v1 events verify unchanged,
the journey's event stream is byte-identical, officers' read surface is
untouched, no new producer or schedule runs. A finding that threatens any of
those outranks everything else.

## The 4 groups → what landed → teeth

### 1. `vocab.patch` — additive v1.1 vocabulary + field classification
`recorder.py`/`verifier.py`/`evidence-event.schema.json` in lockstep:
absence statuses `missed`/`skipped`/`expired` (design R-2 — absence≠health
enforceable at the vocabulary level; terminal statuses), reserved detail
keys for lineage (`parent_trial_id` — R-3, structured, not free-form
links[]), scheduled-trigger provenance, opaque `egress_approval_ref`,
cost/resource observations, broker/runtime model/effort/skill provenance
(R-4 — never env-derived; env-fallback version/commit stay classed
untrusted). `classification.py` (new): total registry, every detail key
producer-asserted today, only recorder-minted fields independently
established (§2.2 R1). The projection allow-list is hoisted to ONE module
constant `PROJECTION_ALLOWED_DETAIL` shared by code and tests.
**Teeth:** `test_vocabulary_v11.py` (11 tests): lockstep across
recorder/verifier/schema; v1 events still verify AND validate; absence
statuses terminal; reserved keys survive sanitize + project allow-listed;
cost/resource NEVER in the projection; secret-shaped values in reserved keys
redacted BEFORE hashing; lineage convention; classification totality;
registered keys never collide with redaction patterns.

### 2. `helper.patch` — the shared recording seam + byte-identical migration
`lifecycle.py` (new, germline): the 8-event lifecycle (intent → policy →
execution → verification → receipt → outcome with refusal/error branches),
evidence-before-action fail-closed semantics for act-class producers, id
unification, re-mint lineage. Explicitly: no CLI, no `__main__`, no
environment-derived store — an import seam for ceremony-admitted code only
(the standing no-generic-emit ruling, §2.4 write seam). `journey.py` `act()`
migrated onto it.
**Teeth:** `test_lifecycle.py` (13 tests) + `test_act_bytestream.py`
(2 tests): the migrated journey replays the recorded pre-migration fixture
(`premigration_journey_eef927f4.py.txt`) with a **byte-identical event
stream** — the R-8 Phase-1 gate, not "dogfood green with zero callers."

### 3. `anchor-retention.patch` — external anchoring + per-class retention
`cabinet/scripts/evidence-anchor.py` (new, non-germline) + services.yml
STAGED row (not enabled): daily read-only export of trial tip hashes,
watermark rows, control digest, purge-receipt manifest to two Captain-owned
surfaces outside the store (meta-repo JSONL + Telegram receipt, design D3);
`--check` compares the live store against the last exported record and
FATALs on rollback/tip-divergence/watermark regression (closes the
verifier's documented anti-rollback residual; the restore drill). Same run
appends the daily digest-anchor trial over the breadth ledgers (org events,
consequence tip, trigger archive). Collection logic in
`framework/evidence_anchor.py`, deliberately OUTSIDE the germline package
(R-9's spirit: read-plane complexity stays off the trusted write path).
Per-class retention: `retention_classes` map in control.json behind the
Captain token; class = day-bounded trial taxonomy segment; unset ⇒
byte-for-byte prior scalar behavior; "forever" trials skipped WITHOUT
verification (verify advances watermarks — a no-op retention pass must not
have side effects).
**Teeth:** `test_evidence_anchor.py` (11) + `test_evidence_retention_classes.py`
(8): read-only guarantees, rollback/divergence detection, old control files
verify unchanged, scalar-fallback equivalence.

### 4. `laws.patch` — doctrine pinned as executable tests
EVAL-025 never-a-score (`memory/golden-evals/` + `cabinet/evals/never-a-score/`
harness wired into `run-golden-evals.sh`, so FW-025 runs it on every push):
AST-pins the projection allow-list and shape, deny-vector classifier for
score-shaped keys, doctrine-string pins across recorder/verifier/schema/
base-safety/.gitignore, doorway check (evidence-read.sh projects, names no
raw verb), unsanctioned scalar-consumer scan. `test_evidence_doctrine_laws.py`
(14): integrity≠veracity classes, absence≠health, purge/retention discipline
incl. promotion-revocation, diagnostic-annotate-never-suppress,
env-provenance-untrusted.

## Integration findings (found + fixed in this composition)

1. **Runbook 3-way overlap (vocab × helper × anchor-retention).**
   `docs/runbooks/evidence-recorder-v1.md` was edited by three groups;
   helper's hunk conflicted with vocab's at the same insertion point. Both
   paragraphs are additive doctrine (classification; lifecycle helper) —
   resolved keep-both, vocab first. anchor-retention's tail sections then
   applied clean. Docs-track-code sweep green after.
2. **Laws harness AST pin vs vocab's allow-list hoist (real seam defect).**
   `never-a-score/harness.py:extract_allowed_detail` fail-closed-required an
   INLINE set literal for `allowed_detail`; vocab correctly hoisted the
   allow-list to module constant `PROJECTION_ALLOWED_DETAIL` (single source
   of truth). Composed result: 2 red tests + a self-test VIOLATION. Fix (in
   the laws harness, non-germline): `_projection_fn` stashes the module
   tree; `extract_allowed_detail` resolves **exactly one level** of
   module-level Name indirection, and the module constant must itself be a
   set/frozenset literal of string constants — every other shape still
   raises `HarnessError` (fail-closed property preserved, now matching the
   repo's real reviewable shape). After: 14/14 harness tests, self-test
   12/12 checks green.

## Reviewed-and-accepted (not defects)

- `evidence-anchor.py` reads `CABINET_EVENT_LOG_DIR` /
  `CABINET_EXHAUST_ARCHIVE_DIR`: an exact, docstring-declared mirror of
  `framework/events/emitter.py` and `exhaust-archive.py` resolution — the
  digest must checksum the SAME files those emitters write. Launchd
  (Captain-controlled) env, integrity metadata only, never fuel-bearing;
  the evidence STORE itself is an explicit `--store` argument. No new
  officer-controlled seam.
- New germline files (`classification.py`, `lifecycle.py`, 2 test files,
  EVAL-025) fall under the existing `framework/evidence` /
  `memory/golden-evals` recursive dir locks — covered on relock with NO
  lock-set edit (no boundary extension; lockstep meta-test green).

## Gate battery (all green, this tree)

| Gate | Result |
|---|---|
| `python3.12 -m pytest framework/evidence framework/onboarding -q` | 275 passed, 1 skipped |
| Lockstep consistency (`test_germline_lockstep_consistency.py`) | 371 passed |
| `framework/tests` new law/anchor/retention tests | 33 passed |
| `cabinet/scripts/tests/test_never_a_score_eval.py` | 14 passed |
| `check-layer-separation.sh` | OK — new=0 (exit 0) |
| `run-golden-evals.sh` | 27/27 incl. EVAL-025 (exit 0) |
| `docs-track-code-sweep.sh` | GREEN files=39 findings=0 (exit 0) |
| Dashboard `tsc --noEmit` | exit 0 (no dashboard files in batch) |

## Zero-behavior-change proofs

- **Cross-version drill:** store minted by the eef927f4 (baseline) recorder
  → verified by THIS tree's verifier: `ok:true`, all 8 checks pass, exit 0;
  projected by THIS tree's doorway with the untrusted-observations boundary.
- **Byte-identical producer:** `test_act_bytestream.py` 2/2 against the
  recorded pre-migration fixture.
- **No suite shrinkage:** collected test ids baseline→branch: 0 removed,
  26 added (onboarding 173→175, evidence 77→101; delta = exactly the new
  files).
- **Read path:** `evidence-read.sh` untouched (0 hunks); allow-list content
  unchanged (hoisted, same keys + reserved keys explicitly allow-listed and
  cost/resource explicitly excluded — pinned by tests both sides).
- **Runtime:** no enabled service row, no schedule, no new producer calls;
  the helper's only caller is the journey.

**Verdict:** composition sound; both integration findings closed with teeth;
hard invariants (determinism, lockstep byte-identical set, unchanged read
path, no emit CLI, house interpreter) verified. Ready for PR + CI; live
schg application rides the Captain ceremony in the amendment doc.
