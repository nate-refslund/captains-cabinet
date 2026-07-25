# FW-019 checkpoint review — feat/cog5-w2-t1-archive-lineage cp2

COG-5 **W2 corpus unit T1 — ARCHIVE/LINEAGE family**, second checkpoint: the
FIX batch closing the three must-fixes a fresh-context adversarial review
returned against cp1 (`3732e408`). Contract
`docs/plans/cognitive-core-phase-5-contract-2026-07-24.md` §12 sims 1/9/10 +
X1, §5.2 physics, §5.3 ingest, §6.2 provenance.

Batch is **two files, both this unit's own** — `lib_cog5_archive_fixtures.py`
and `test_cog5_sim_archive.py`; +662/−18 ⇒ this artifact (FW-019). **Zero
framework/config delta** (census PASS). `lib_cog5_corpus.py` is byte-identical
to cp1 — the review found the shared core provably clean and it was not
reworked.

## What the review found, and what closed it

### MF-1 — a row lost from the UNSEALED OPEN SEGMENT was UNDETECTED (X1)
Reproduced first: 24 rows, `rows_per_segment=8` (segments 0/1 sealed on
rollover, segment 2 open); drop the last LINE of `seg-00002.jsonl` at a record
boundary ⇒ `verify_archive(...)["ok"] is True`, `findings == []`, `serve_rows`
hands out 23. No link breaks (the deleted row was the only one pointing
forward), the file still ends on a newline so the truncated-tail detector is
silent, and no seal covers an open segment.

**Root cause named honestly:** the store ALREADY wrote two independent
counters and consulted NEITHER — `manifest.row_count` (24 vs 23 on disk) and
`anchor.sequence` (24 vs a last sequence of 23). A counter that is written and
never read is not a detector.

`verify_archive` now has a third, per-STORE layer, and the docstring states
which escape each layer uniquely owns:

| layer | findings | the escape only it sees |
|---|---|---|
| per-ROW | BITFLIP / FORGED_PREV_HASH / SEQUENCE_GAP / TRUNCATED_TAIL | in-place edits |
| per-SEAL | BROKEN_SEAL (2 limbs) | edits inside a SEALED segment |
| per-STORE | ROW_COUNT_MISMATCH · MANIFEST_HEAD_MISMATCH · ANCHOR_MISSING · ANCHOR_SEQUENCE_MISMATCH · FORGED_ANCHOR | deletion at a record boundary in the OPEN segment |

**Refusal boundary explicitly NOT regressed** — the review measured
`safe_sequence == the last good seal's last_sequence` at 5 corruption
positions. A store-level finding flips `ok`, which pins `safe_sequence` to the
last good seal exactly as before (MF-1's own repro now yields `safe_sequence`
16 and serves 16 of 23 rows — conservative, never over-serving). That property
is now a PINNED non-regression arm, parametrised over **8** corruption
positions, asserting `safe_sequence` equals the last good seal's bound and
that the reader never serves past it.

### MF-2 — `ingest_shadow_rows` dedup was PER-CALL only
Reproduced: two calls ⇒ 3 ingested, then 3 ingested AGAIN. §5.3 routes shadow
accrual through a periodic organ manifest (§11.2), so re-reading an accruing
log is the NORMAL cadence — every cycle re-admitted every row.

**Mechanism chosen: dedup against fingerprints ALREADY IN THE TARGET STORE**
(new `store=` parameter seeding the dedup index through the same `dedupe_key`
the candidates go through), plus `ShadowIngestor`, the disciplined caller that
holds the store across cycles so the cadence is idempotent by construction.

*Why the store and not a caller-threaded `seen` set:* this family already paid
for that answer one section down. `shadow_append_racy` is the recorded P1
defect — a caller deciding what to skip from a snapshot held OUTSIDE the
authority — and `shadow_append_folded` is the fix: derive the skip set from the
store, at use. A threaded set is process-lifetime state a restart silently
empties (re-admitting the whole log) and two ingesters cannot share. Passing
`store=()` is a genuine FIRST cycle, not an escape: an empty store has no
fingerprints to key against. Measured: run 1 = 3 ingested / 1 duplicate; run 2
= **0 ingested / 4 duplicates**; `ShadowIngestor` over 4 cycles = 3,0,0,0.

### MF-3 — the anchor attestation was INERT
`grep -n "anchor" test_cog5_sim_archive.py` returned only two `re-anchor`
prose hits; `verify_archive` never opened `anchor.json`. A §5.2-named
discipline shipping with no assert and no mutant — and precisely the mechanism
that catches MF-1.

Now verified: self-consistency (recomputed `anchor_hash`), the attested
sequence against the store's **cadence point** — `(last_sequence //
anchor_every) * anchor_every`, never the last row, or a normal store would RED
— and the attested `chain_head` against the walked chain at that sequence. The
cadence became a declared manifest field (`anchor_every`) so the verifier
reads the store's own parameter instead of assuming one, and `restore` /
`seal_and_copy_out` now CARRY `anchor.json`: a rollback drill that left the
attestation behind was handing over a store that could no longer prove where
its chain stood.

## Both-directions proof — 11 reverts, each REDs its paired arm
Every new detector limb was individually reverted (`PYTHONDONTWRITEBYTECODE=1`
throughout, per the false-green lesson) and the paired arm confirmed RED, then
restored to 87/2:

| revert | RED arms |
|---|---|
| row_count mismatch limb | dropped-open-segment-row + stripped-declaration |
| absent row_count reads as agreement | stripped-declaration |
| manifest chain_head limb | manifest-head mutant |
| anchor layer entirely | 8 arms |
| anchor self-consistency limb | forged anchor [crude] |
| anchor-vs-chain limb | forged anchor [re-signed] + safe_sequence[forged] |
| anchor sequence limb | tail-edit-that-also-rewrites-the-manifest |
| ANCHOR_MISSING tolerated | anchor-dropped + safe_sequence[dropped] + restore-carries |
| sub-cadence attestation branch | store-shrunk-below-first-attestation |
| restore drops the attestation | restore-carries + seal-and-restore |
| ingest store-seeding removed | all 3 MF-2 arms |

**A gap this found and closed:** the first pass shipped the
`ANCHOR_SEQUENCE_MISMATCH` limb with NO arm covering it — reverting it changed
nothing. That is decoration by this unit's own standard, so two arms were
added rather than the limb dropped: `test_mutant_tail_edit_that_also_rewrites_
the_manifest` (the THOROUGH editor — drops the row AND repairs the manifest
counters, so the whole manifest layer is silenced and the arm asserts the
ANCHOR alone carries the detection) and `test_mutant_store_shrunk_below_its_
first_attestation`. This is also the evidence that the two store detectors are
not redundant with each other.

## Mutants — 27 named escapes (re-derivable by grep)
**21** `test_mutant_*` arms (20 functions; `test_mutant_forged_anchor` is
parametrised ×2) + **5** corruption injections in
`test_each_corruption_is_detected` + **1** tampered write-ahead refusal. cp1
counted 18; the **+9** are: open-segment row deletion, stripped row_count
declaration, manifest-head divergence, the thorough tail edit, the
sub-cadence shrink, forged anchor ×2 (crude + re-signed), dropped anchor, and
per-call-only ingest dedup.

## Detector-mutation profile — 3/2/1/1/3/1 ⇒ **4/8/1/1/6/1**
The six break-the-reference mutations were re-run. Every change is an
INCREASE, and each is attributable to a new arm covering the SAME detector —
no detector lost coverage:
- **bitflip disabled 3→4** — `safe_sequence[bit-flipped row]` now re-covers it.
- **serve past safe_sequence 2→8** — six of the eight non-regression params
  RED. The other two (`forged anchor`, `dropped anchor`) correctly do NOT:
  with every segment sealed the last good seal IS 24, so serving all rows is
  not over-serving. The arm is precise, not blanket.
- **naive heal 1→1**, **order-invariant archive chain 1→1**,
  **provenance stamp trusts the candidate 1→1** — untouched.
- **content-dedup keys on idempotency 3→6** — the three MF-2 arms.

## The recorded strictness asymmetry — DECIDED, not deferred
The review flagged that T1 ACCEPTS `sim_replay` (a provenance token) as a
source-class spelling where T3 REFUSES it. **Kept deliberately**, and now
pinned mechanically rather than merely argued:
- It is **not** the §5.3 conflation shape. That one is between two DISJOINT
  vocabularies where a token of one populates the OTHER's field and means
  something else there (`record_kind` — `record_kind_conflations` stays
  strict). This is a fold WITHIN one vocabulary onto a slug stamping the SAME
  provenance.
- Refusing here would unilaterally settle a RECORDED cross-unit divergence
  that the corpus deliberately routed to the integrator, picking T3's spelling
  over T2's on no authority — the contract pins only the provenance enum, which
  both siblings already agree on. T1 is the JOIN point, the one place refusal
  costs mergeability; T3 is not, so its refusal is free and correct for T3.
- Stated exactly, without overclaiming: removing the alias would **not** RED
  T2's suite today — T2 carries its own source table
  (`lib_cog5_scoring_fixtures.py:193-201`, verified from bytes) and imports
  this core only for presence-at-join. The argument is the integrator's
  authority, not a breakage claim.
- New arm `test_the_alias_fold_is_structurally_incapable_of_changing_meaning`
  pins the invariant that makes it inert: an alias whose KEY is a provenance
  token may only target a slug that stamps THAT provenance. Applied to the
  real table (clean) and to a forged one (`real_live -> generator`, flagged),
  so it is not vacuous. The cp1 DEBT pin is untouched.

## Verification
- unit suite: **87 passed, 2 skipped** (cp1: 63/2 ⇒ **+24 arms**, +0 skips)
- full SERIAL sweep from this isolated clone, `cabinet/scripts/tests`:
  **3486 passed, 14 skipped, 0 failed** (master a1357829 baseline 3399/12 ⇒
  delta **+87 / +2**, exactly this unit's own arms; zero pre-existing tests
  disturbed). Sweeps were run serially per the timing-sensitivity lesson.
- THREE-UNIT combined (isolated clone = master + T1 fixed + T2 `27197a63` +
  T3 `1ec1546d`; no file overlaps between the units): cog5 selection
  **353 passed, 16 skipped, 0 failed**; the FULL combined tree
  **3685 passed, 28 skipped, 0 failed**.
- `cog2-import-gate.py` exit 0 · `check-layer-separation.sh` OK, **new=0** ·
  census **PASS** (zero framework delta) · corpus purity: only this unit's two
  files changed · `ast.parse` over the committed HEAD bytes: OK.

## Not fixed here (recorded, out of scope — routed)
X8 part (iii) ledger non-interference has no arm anywhere in W2; per §14.2 it
is a W6 E-run obligation for the integrator. The contract §1 X1 cell still
cites `test_cog5_archive_lineage.py` where the delivered name is
`test_cog5_sim_archive.py` — an integration-time citation sweep. Cosmetic and
left alone: the P1 AST probe flips on any rename of `append_shadow_log`'s
`new_rows` param; `verify_archive` would false-`BROKEN_SEAL` if rows were
appended after `seal_open_segment()` on a non-full segment (no test does
this); `broken_at`'s numeric value is computed but never read.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
