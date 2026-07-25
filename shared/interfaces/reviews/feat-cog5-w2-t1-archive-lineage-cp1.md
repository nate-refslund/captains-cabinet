# FW-019 checkpoint review — feat/cog5-w2-t1-archive-lineage cp1

COG-5 **W2 corpus unit T1 — ARCHIVE/LINEAGE family**. Branch
`feat/cog5-w2-t1-archive-lineage` off `origin/master` a1357829. Contract
`docs/plans/cognitive-core-phase-5-contract-2026-07-24.md` §12 sims 1/9/10 +
X1, §5.2 physics, §5.3 ingest/field-map/P1 rider, §5.4 record shape, §6.2
provenance.

Batch is **three NEW test-surface files — zero framework/config delta**
(census GREEN, observed==max on all 10 budgets; tests are path-excluded).
>300 lines ⇒ this artifact (FW-019).

## What landed
- **`cabinet/scripts/tests/lib_cog5_corpus.py`** (NEW, **pure stdlib**) — THE
  T1-owned CROSS-UNIT SHARED CORE that T2 and T3 already import under guards
  they wrote before it existed. Owns the three genuinely cross-unit
  vocabularies: the §6.2 `provenance` closed enum (exposed under all three
  names T3's probe walks) + stamp/count/laundering predicates; the §5.3
  record_kind FIELD MAP (shadow `{run,decision}` → `shadow_record_kind`,
  never the trajectory enum); the recorder-dialect canonical bytes/digest
  **stdlib REPLICA** + the §5.4 archive record shape built on it.
  Pure-stdlib is a **mergeability law, not taste**: T2's guard is
  `except ModuleNotFoundError`, so a non-stdlib import here would silently
  bind `CORE = None` and RED T2's companion with a misleading message. A test
  asserts the module scope stays stdlib-only.
- **`cabinet/scripts/tests/lib_cog5_archive_fixtures.py`** (NEW) — the
  reference archive substrate implementing the §5.2 PHYSICS over scratch
  roots: append-only JSONL segments (`O_APPEND` + flush + fsync + dir-fsync,
  the recorder `_write_exact_event` :610-623 discipline), sequential
  `prev_hash`/`sequence` chain from ZERO_HASH, periodic anchor attestation,
  `pending.json` write-ahead **exactly-once** heal (recorder :625-670 shape,
  both crash positions), **sealed segments**, and manifest-class artifacts via
  a stdlib **atomic-write replica** (kernel.py:184-199). Plus every corruption
  injector, the seal/copy-out/RESTORE drill, the E1 runner, the ingest, and
  the P1 lock-fold pair.
- **`cabinet/scripts/tests/test_cog5_sim_archive.py`** (NEW) — the battery:
  sim 1 (E1) + X1, sim 9 (corrupt archive), sim 10 (lineage rollback), the
  §5.3 duplicate-tolerant ingest + field map + P1 rider, the §5.4 record
  shape, the §5.2 physical disciplines, and the cross-unit core contract.

## The substrate decision, DEMONSTRATED not asserted (§5.1)
`test_the_kernel_algebra_would_miss_the_reorder` compiles the kernel's own
`chained_rows_hash` algebra and shows its value is **unchanged** by a
reversal (it SORTS by order_key — deliberately arrival-order-invariant,
kernel.py:118-130), while the archive's sequential chain differs. That
inequality is the evidence for "NOT a fourth kernel projection": an archive
built on the kernel's algebra could not have detected the sim-10 reorder
mutant, which this unit proves it does detect.

## Boundary discipline — the ROW-6 non-extension honoured
No file in this unit imports `framework.projection`, statically or
dynamically (a test asserts it by AST over all three files). The canonical
dialect is a **replica with two live parity tripwires**: (a) against the
kernel's own function **compiled from its source BYTES** via `ast`, never
imported; (b) against the shipped PUBLIC surface
`contracts.holdout_receipt_payload_fingerprint`. The archive store token is
assembled at runtime (belt and braces — the cog5 test globs ARE allowlisted
on ROW 9). `cog2-import-gate.py` exit 0; `check-layer-separation.sh` OK
(new=0).

## Mutants — 14 negative controls, every one proven biting NOW
sim 1: archive drops a failed candidate (5 lineage rows vanish, chain still
verifies — proving X1 must be a SEPARATE gate); rank order varies under
PYTHONHASHSEED (**5 distinct orderings over 5 seeds**, not a probabilistic
hope). X1: a run that writes into the live surface. sim 9: skip-verify reader
serves past corruption; tampered write-ahead body; plus five corruption arms
(truncated tail, bit-flip, forged prev_hash, broken seal, **re-signed** seal
forge — the last is internally self-consistent so only the seal-vs-segment
limb catches it, proving both seal limbs load-bearing). sim 10: restore drops
a row; restore reorders a row (row count AND id multiset unchanged — only the
order-sensitive chain catches it). §5.3: dedup-by-idempotency-key (silent
data loss); no-dedup (raced duplicate lands twice); record_kind conflation
(both directions); read-outside-the-lock reproducing the P1 race
**deterministically** (the interleaving is passed explicitly — a flaky race
test proves nothing). §6.2: provenance laundering + out-of-enum refusal.

**Detector mutation run (the reviewer's own check, done here):** six
mutations of the *disciplined* implementation — disabling the bitflip check,
serving past `safe_sequence`, an unconditional heal, an order-invariant
archive chain, content-dedup silently keying on idempotency, and a
provenance stamp that trusts a candidate-supplied value — each RED the suite
(3/2/1/1/3/1 failures respectively); baseline restores 63 passed / 2 skipped.
The gates are load-bearing, not decoration.

## Mergeability — merges GREEN on a tree with no implementation
63 passed / **2 designed skips**. Both skips are real-surface joins, each
with a COMPANION absence assertion that REDs the instant its path lands plus
a RETIREMENT CONDITION in its docstring:
- `test_real_archive_module_vacuity` — retire when
  `framework/evolution/archive.py` lands (W4); companion also watches
  `emitter.py`.
- `test_restore_cli_vacuity` — retire when
  `cabinet/scripts/cog5-archive-restore.py` lands (W4).
Everything else runs LIVE today. The P1 rider needs **no** skip: its target
property is proven live on the reference pair, and a live companion
(`test_shipped_cli_has_not_yet_folded_the_read_companion`, an AST probe of
`append_shadow_log`) REDs the moment the W4 rider lands.

## Cross-unit join (T2/T3) — verified, not assumed
Both sibling branches were fetched and their expectations read from bytes
before this core was designed. T2 needs only a cleanly-importing module
(`import lib_cog5_corpus as CORE`); T3 additionally probes
`PROVENANCE`/`LIB_COG5_CORPUS_PROVENANCE`/`PROVENANCE_ENUM` and requires the
first-found to equal the §6.2 enum — all three are exposed with identical
content. Landing this file flips one designed skip to a live pass in EACH
sibling suite (T2 `TestCorpusCoreJoin::test_core_join_guard`, T3
`TestSharedCorpusIntegration::test_provenance_vocabulary_agrees_with_t1_core`).

**Recorded cross-unit divergence → integrator:** T2 and T3 independently
slugged two source classes differently (`verdict_inbox_labels`/`sim_replay`
vs `verdict_inbox`/`sim`). The contract pins only the PROVENANCE enum, which
both agree on, so this is an un-pinned slug rather than a semantic fork. The
core canonicalises on the short spellings and carries an explicit
`SOURCE_CLASS_ALIASES` table so NEITHER sibling breaks at the join; a test
pins the table as **DEBT** so the integrator's choice cannot be forgotten.

## Verification
- new suite `test_cog5_sim_archive.py`: **63 passed, 2 skipped**
- full sweep `cabinet/scripts/tests`: **3462 passed, 14 skipped** (baseline at
  a1357829 was 3399 passed / 12 skipped ⇒ delta **+63 passed, +2 skipped**,
  exactly this unit's own arms; zero pre-existing tests disturbed)
- `cog2-import-gate.py` exit 0 · `check-layer-separation.sh` OK, new=0 ·
  census PASS (`census_delta` all zeros — tests are path-excluded)
- `ast.parse` over the committed HEAD bytes of all three files: OK

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
