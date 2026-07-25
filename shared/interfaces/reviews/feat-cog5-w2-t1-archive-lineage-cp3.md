# FW-019 checkpoint review — feat/cog5-w2-t1-archive-lineage cp3

COG-5 **W2 corpus unit T1 — ARCHIVE/LINEAGE family**, third checkpoint: closing
a **REGRESSION the cp2 fix batch introduced** plus three qualifications a
fresh-context re-review returned against `b3754a93`. The re-review confirmed
cp2's three must-fixes are genuinely closed with no coverage regression; none
of that work was reworked.

Batch is **two files, both this unit's own** — `lib_cog5_archive_fixtures.py`
and `test_cog5_sim_archive.py`; +453/−54 ⇒ this artifact (FW-019). **Zero
framework/config delta** (census PASS). `lib_cog5_corpus.py` is still
byte-identical to cp1/cp2 (`3732e408`) — verified by `git diff --quiet`; no fix
here needed it, including SF-2, and the reason is recorded below.

## MF — the regression: a correctly-healed store made permanently UNSERVABLE

Found by probing LEGITIMATE states, not by mutation. `_commit` mints the
periodic attestation AFTER the segment append, so there is a real crash window
between `append_exact_line` and `write_anchor`. `heal()` reconciled that state
exactly-once, cleared pending and refreshed the manifest — all correct — and
**never minted the interrupted attestation**.

Reproduced at both ends, crashing in that exact window at sequence 4 with the
default `anchor_every=4` (`rows_per_segment=8`, nothing sealed yet):

| tree | verify | safe_sequence | serves |
|---|---|---|---|
| `3732e408` (pre-anchor-layer) | ok | 4 | **4 of 4** |
| `b3754a93` (cp2) | `ANCHOR_MISSING` **forever** | 0 | **0 of 4** |
| this checkpoint | ok | 4 | **4 of 4** |

Re-healing never recovers it: the second `heal()` returns `None` (nothing left
to reconcile) and the store stays unservable. That is 1 crash position in
`anchor_every` — **25% at the default** — and on a larger store everything past
the last seal is lost, not four rows.

**Fix (the two-line shape the re-reviewer verified):** in `heal()`'s
exactly-once limb, mint the anchor when the reconciled sequence lands on the
cadence. Idempotent by construction — the attestation is a pure function of the
reconciled event, so a crash that landed LATER (anchor already written, pending
not yet cleared) rewrites byte-identical content through the same atomic
replace. `heal()`'s contract is restated as "EXACTLY ONCE — and COMPLETELY":
exactly-once governs the ROW, completely governs everything `_commit` owes for
it.

Two small structural changes came with it, both to stop the fixtures drifting
from the real write path: `_commit`'s segment-append step is extracted as
`_append_only` and reused by the crash fixtures, and a new
`append_crashing_before_anchor` models the TRUE durable state of that window
(row on disk, no attestation, manifest not refreshed, pending still present) —
cp2's `append_crashing_after_commit` sits one step later.

### And the arm that missed it — now parametrised over the cadence

The old arm crashed at sequence 2 only, which is **off-cadence** with
`anchor_every=4`, so it could not see this. Both heal arms are now parametrised
over the cadence position, and the lost-ack arm additionally over both crash
windows inside `_commit`:

```
test_pending_heal_completes_exactly_once_after_a_lost_append[off-cadence]
test_pending_heal_completes_exactly_once_after_a_lost_append[on-cadence]
test_pending_heal_is_exactly_once_after_a_lost_ack[off-cadence-crash-before-the-anchor]
test_pending_heal_is_exactly_once_after_a_lost_ack[off-cadence-crash-before-the-pending-clear]
test_pending_heal_is_exactly_once_after_a_lost_ack[on-cadence-crash-before-the-anchor]
test_pending_heal_is_exactly_once_after_a_lost_ack[on-cadence-crash-before-the-pending-clear]
```

Every heal arm now asserts SERVABILITY (`_assert_healed_store_is_servable`),
not just row identity — verify ok, `safe_sequence == sequence`, the reader
hands out every row, and the attestation is present **exactly when** the
reconciled sequence lands on the cadence. Row identity was correct throughout
the regression; servability was not, so asserting the former alone is what let
it through. Each parametrisation declares its own cadence position and asserts
it, so a future change to `anchor_every` cannot silently turn the on-cadence
params back into off-cadence ones.

## SF-1 — E4, "the complete editor", and an over-absolute claim

The re-reviewer's mutant E4 — edit the segment **and** repair the manifest
**and** re-mint the anchor — **verifies clean; the row is silently lost.**
Measured on this tree: 24 rows → drop the open-segment tail → repair counters →
re-mint at the shortened store's own cadence point (20) ⇒ `ok: True`,
`findings: []`, serves 23, row 24 gone.

That is a real limit of this reference model and it is **acceptable — provided
it is declared**. The unit worded the anchor's protection absolutely in four
places, and minting needs **no secret** here because the recorder's **signed**
anchor is explicitly out of scope (§5.2, "minus the signer"). Corrected
wording, same claim in all four: *the anchor defeats an editor who does not
re-mint it — which is every editor that stops at the manifest, and is what
makes it non-redundant with the manifest. It does not defeat one who does.
Closing that is what SIGNING would buy, and nothing weaker.* Sites:
`verify_archive`, `_anchor_findings`, `repair_manifest_counters`,
`write_anchor`, plus the paired test docstring and the class docstring.

Pinned mechanically by a **known-limit arm in this unit's own idiom** — the
same COMPANION + RETIREMENT CONDITION shape the vacuity arms and the P1 rider
companion already use, so it cannot silently outlive its reason:
`TestStoreLevelDetection::test_known_limit_the_complete_editor_that_also_re_mints_the_anchor`,
with the new `remint_anchor` injector. It asserts **both halves**, so it is a
measurement and not a concession: WITHOUT the re-mint the editor is caught
(`ANCHOR_SEQUENCE_MISMATCH`); WITH it, it is not, and the dropped `record_id`
is provably absent from what the reader serves.

**The non-redundancy claim itself is NOT weakened** — the re-reviewer proved it
by revert and that evidence stands. Only the absolute framing was wrong.

## SF-2 — the MF-2 latent chain-field hazard

`ReferenceArchive.append` stamps `sequence`/`prev_hash`/`record_id`/`row_hash`
onto every row it takes, which changes `content_fingerprint` — so an ingester
whose durable store IS the lineage archive re-admits the whole log every cycle.
Measured before the fix: seeding from `serve_rows(archive_root)` gave **3
ingested, not 0**; stripping those four fields restored **0 ingested / 4
duplicates**. No shipped path composes the two surfaces today, so this was
**latent, not live** — but `ingest_shadow_rows`'s own durability framing invites
exactly that composition, and it is MF-2's defect re-entering through the
durable door.

**Chosen: chain-field invariance (the preferred option), implemented at the
DEDUP KEY — not inside `CORE.content_fingerprint`.** Reasoning:

- **Blast radius.** `content_fingerprint` is the cross-unit shared core that T2
  and T3 import; changing it would alter the §5.3 dedup key's meaning for
  everyone and would break the byte-identity `lib_cog5_corpus.py` has held
  since `3732e408`. Nothing about this hazard requires that.
- **Semantics.** A content fingerprint that silently ignores four named fields
  is no longer a content fingerprint. The invariance belongs to the DEDUP KEY,
  which is the thing that must survive an archive round trip.
- **Information-preserving, which is what makes it safe rather than a
  weakening.** All four are either POSITION in the chain (`sequence`,
  `prev_hash`) or pure DERIVATION of the rest of the row (`record_id` is the
  content-excluded identity over fields that all remain; `row_hash` is the
  digest). Removing them loses no content.

The constraint is ALSO stated explicitly at the API boundary
(`ingest_shadow_rows` and `dedupe_key` docstrings) rather than left implicit,
with `CHAIN_FIELDS`/`strip_chain_fields` as the named surface. Two arms:

- `test_re_seeding_from_the_DURABLE_archive_admits_nothing_twice` — the real
  composition, through `serve_rows` AND through the rehearsed `restore`, with a
  precondition asserting the durable rows actually carry the stamps so the arm
  cannot go vacuous.
- `test_the_dedup_key_is_chain_field_invariant_but_still_content_sensitive` —
  the BOUND, because ignoring fields is a weakening unless the ignored set is
  exactly the store's stamps. `CHAIN_FIELDS` is checked against what `_prepare`
  ACTUALLY adds on a real append (never asserted from memory), and four content
  fields are each shown to still move the key.

The six pre-existing dedup arms are undisturbed (they pass unchanged, and the
content-dedup mutation now REDs 8 arms instead of 6).

## SF-3 — the `sim_replay` characterization, rewritten

The re-reviewer upheld the DECISION and called the justification loose. It was.
"A fold within one vocabulary" described the FOLD (source-slug → source-slug)
while saying nothing about the TOKEN — and `sim_replay` **is** a provenance
token being used as a source-class slug, structurally the same crossing
`record_kind_conflations` forbids. Conceded in the docstring; the shape is not
the defence.

**The defence is the harm test, and it survives:** this fold's OUTPUT is
provenance `sim_replay`, byte-identical to what T2's own table produces for the
same slug, so the token cannot mean anything other than what it already means
on both sides of the join. A conflation harms by making a token mean something
ELSE in its new field; here it means the same thing, and the arms measure that.
`record_kind_conflations` governs the `record_kind` fields where the
disjoint-vocabulary conflation actually lives, is untouched, and stays strict.

Strengthening evidence recorded, all measured on the combined tree:

- Deleting the alias leaves **T2 121/5 and T3 84/9 fully green**, with only
  T1's own two arms RED (`test_sibling_source_class_spellings_both_resolve`,
  `test_the_alias_fold_is_structurally_incapable_of_changing_meaning`) — so the
  argument is the integrator's authority, not a breakage claim.
- Three laundering aliases all RED: `arena→live_emission` (2 arms),
  `sim→live_emission` (4 arms), `real_live→generator` (2 arms).

**Named honestly:** `meaning_changing_aliases` inspects only PROVENANCE-KEYED
aliases, so it is what catches `real_live→generator`. The other two are keyed
on non-provenance slugs and are caught by the pre-existing
count-toward-minimum arms. The guarantee is therefore **SUITE-level, not
predicate-level** — a future reader who deleted those count arms would not be
protected by this one.

## Both-directions proof — 4 reverts, each REDs its paired arm

`PYTHONDONTWRITEBYTECODE=1` + a `__pycache__` purge on every revert-and-rerun.

| revert | RED arms |
|---|---|
| `heal()` no longer mints the interrupted attestation | the 2 **on-cadence** lost-ack params (the 2 off-cadence stay GREEN — the blind spot, demonstrated) |
| dedup key not chain-field invariant | both SF-2 arms |
| `remint_anchor` made a no-op | known-limit arm (second half) |
| `ANCHOR_SEQUENCE_MISMATCH` limb removed | known-limit arm (first half) + the thorough-editor arm |

## Detector-mutation profile — 4/8/1/1/6/1 ⇒ **4/8/4/1/8/1**

The six break-the-reference mutations were re-run. **No decrease anywhere**;
both increases are attributable to new arms covering the SAME detector:

- bitflip disabled **4→4**, serve past safe_sequence **8→8**, order-invariant
  archive chain **1→1**, provenance stamp trusts the candidate **1→1** —
  untouched.
- **naive heal 1→4** — the parametrised lost-ack arm; all four params RED.
- **content-dedup keys on idempotency 6→8** — the two SF-2 arms.

Mutant census unchanged at **27** named escapes (21 `test_mutant_*` nodes + 5
corruption injections + 1 tampered write-ahead refusal) — this batch added no
mutant. It added 1 **known-limit** arm, which is a declared residual, not a
mutant, and is counted separately on purpose.

## Verification

- unit suite: **94 passed, 2 skipped** (cp2: 87/2 ⇒ **+7 arms**, +0 skips)
- full SERIAL sweep from an isolated clone, `cabinet/scripts/tests`: **3493
  passed, 14 skipped, 0 failed**. Master baseline `a1357829` **re-measured in
  an isolated clone this session: 3399 passed, 12 skipped** ⇒ delta **+94/+2**,
  exactly this unit's own arms; zero pre-existing tests disturbed.
- THREE-UNIT combined (isolated clone = master + T1 fixed + T2 `da413d4b` +
  T3 `1ec1546d`; no file overlaps between the units — verified by name): cog5
  selection **366 passed, 16 skipped, 0 failed** (was 359/16); the FULL
  combined tree **3698 passed, 28 skipped, 0 failed** (was 3691/28). Per unit
  on that tree: T1 94/2, T2 121/5, T3 84/9.
- `cog2-import-gate.py` exit 0 · `check-layer-separation.sh` OK, **new=0** ·
  census **PASS** (zero framework/config delta) · corpus purity: only this
  unit's two files changed · `lib_cog5_corpus.py` byte-identical to `3732e408`
  · `ast.parse` over the committed HEAD bytes: OK.

## Not fixed here (recorded, out of scope — routed)

Unchanged from cp2: X8 part (iii) ledger non-interference has no arm anywhere
in W2 (§14.2, a W6 E-run obligation for the integrator); the contract §1 X1
cell still cites `test_cog5_archive_lineage.py` where the delivered name is
`test_cog5_sim_archive.py` (integration-time citation sweep). Cosmetic and left
alone: the P1 AST probe flips on any rename of `append_shadow_log`'s `new_rows`
param; `verify_archive` would false-`BROKEN_SEAL` if rows were appended after
`seal_open_segment()` on a non-full segment (no test does this); `broken_at`'s
numeric value is computed but never read.

**Newly declared, deliberately NOT closed:** the E4 complete-editor escape is a
known limit of an UNSIGNED attestation, pinned by its own arm with a retirement
condition. Closing it requires signing, which §5.2 places with the recorder and
outside this corpus.

Provenance: authored per the 2026-07-07 full-autonomy grant + the 2026-07-20
cognitive-masterplan continuous grant.
