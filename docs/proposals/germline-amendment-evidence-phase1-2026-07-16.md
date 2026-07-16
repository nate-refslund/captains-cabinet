# Germline amendment — EVIDENCE PHASE 1 (whole-cabinet foundation) — 2026-07-16

**Status:** PROPOSED on `feat/evidence-phase1-foundation` (off `eef927f4`).
The Captain's merge of this branch to master (after CI is green) is the
apply; the post-merge on-Mac unlock ceremony below re-materializes the schg
files at the landed bytes and relocks the same day.

**Design of record:** whole-cabinet evidence & self-improvement phased design
(2026-07-16), Phase 1 — "one ceremony, zero behavior change" — §3 Phase 1
items 1/3/4/5/7, under the §2 safety envelope and refinements R-2/R-3/R-4/R-8.
Authored and self-ratified per the 2026-07-07 full-autonomy grant; the
ceremony itself stays Captain-only.

**Checkpoint review:** `shared/interfaces/reviews/evidence-phase1-foundation-cp1.md`
(FW-019 artifact for this >300-line batch).

## What this batch is

Phase 1 makes the record layer able to carry org volume and pins the laws
that keep evidence from ever becoming a score or a lie-amplifier — before a
single new producer is wired. Everything is additive/observational:

1. **Additive schema v1.1 vocabulary** landed in lockstep across recorder,
   verifier, and schema: absence statuses (`missed`/`skipped`/`expired` —
   absence≠health becomes enforceable at the vocabulary level, R-2),
   structured trial lineage (`parent_trial_id` et al., R-3), scheduled-trigger
   provenance, an opaque egress approval reference, cost/resource observation
   keys (never projected to officers), and broker/runtime-sourced
   model/effort/skill provenance (R-4 — never environment-derived).
2. **Field-classification doctrine** (`classification.py`): every detail key
   classed producer-asserted vs independently-established (§2.2 R1); all
   producer detail keys today are producer-asserted, and only recorder-minted
   fields are independently established. Never fuel-bearing without the
   independent class.
3. **Shared recording helper** (`lifecycle.py`) extracted from the onboarding
   journey's `act()`: the 8-event lifecycle with refusal/error branches,
   evidence-before-action fail-closed semantics, id unification, re-mint
   lineage. An import seam for sanctioned code only — **no generic emit
   CLI/API exists or is introduced** (standing ruling preserved). The
   journey is migrated onto it with a **byte-identical event stream**
   (R-8 gate: `framework/onboarding/tests/test_act_bytestream.py` against
   the recorded pre-migration fixture).
4. **Per-class retention** keys in the store control file (Captain-token
   gated, defaults preserve current behavior exactly).
5. **External anchoring** (read-only daily job, non-germline by design
   R-9-adjacent: collection logic outside the trusted write path): store tip
   hashes, watermarks, control digests, purge-receipt manifest exported to
   Captain-owned surfaces outside the store (cabinet-meta repo + Telegram,
   design decision D3), plus the daily digest-anchor trial over the breadth
   ledgers, plus `--check` (the restore drill).
6. **Laws pinned as executable tests:** the never-a-score golden eval
   (EVAL-025, wired into the pre-push suite via `run-golden-evals.sh`) and
   the doctrine-law tests (`test_evidence_doctrine_laws.py`): integrity≠
   veracity field classes, absence≠health, purge/retention discipline incl.
   promotion-revocation, diagnostic-annotate-never-suppress,
   env-provenance-untrusted.

## Why this touches germline

The evidence plane's code, schema, producer seam, and the golden-eval judges
are Ring-0 and `schg`-locked precisely so officers cannot edit, disable, or
forge the audit plane or its laws. Phase 1 changes the CONTENT of that plane
(vocabulary, shared producer seam, retention dial) and adds one behavioral
judge — a germline edit by construction, routed through the Captain sudo
unlock ceremony. Doctrine-correct: the audit plane evolves only under the
Captain's hand.

**No boundary extension.** No path JOINS or LEAVES the locked set: every
germline file below is covered by entries that already exist — the
`framework/evidence` and `memory/golden-evals` directory locks (`-R`, so the
new files inside them arm automatically on relock) and the named
`framework/onboarding/journey.py` / `framework/schemas/evidence-event.schema.json`
FILE entries. `cabinet/scripts/germline-lock.sh` FILES/DIRS,
`framework/policies/immutable-core.yml`, and `pre-tool-use.sh` §5 need NO
edit and receive none — the lock SET is byte-identical and the lockstep
consistency meta-test stays green (371 tests, verified this batch).

## Germline (schg-locked) files changed by this batch — the ceremony set

| Path | Locked via | Change |
|---|---|---|
| `framework/evidence/recorder.py` | `framework/evidence` dir (-R) | v1.1 statuses (`missed`/`skipped`/`expired`), reserved detail keys, `PROJECTION_ALLOWED_DETAIL` single-source constant, structured `parent_trial_id` lineage, per-class retention in `retain` |
| `framework/evidence/verifier.py` | `framework/evidence` dir (-R) | status-vocabulary lockstep (accepts v1.1 statuses; v1 events unchanged) |
| `framework/evidence/redaction.py` | `framework/evidence` dir (-R) | redaction fires on every new reserved key; cost/resource keys never projected |
| `framework/evidence/__init__.py` | `framework/evidence` dir (-R) | package exports for the new modules |
| `framework/evidence/__main__.py` | `framework/evidence` dir (-R) | Captain-token `--retention-class` / `--clear-retention-classes` control verbs |
| `framework/evidence/classification.py` (new) | `framework/evidence` dir (-R) | field-classification registry (producer-asserted vs independently-established) |
| `framework/evidence/lifecycle.py` (new) | `framework/evidence` dir (-R) | shared 8-event lifecycle recording helper (import seam; no CLI) |
| `framework/evidence/tests/test_vocabulary_v11.py` (new) | `framework/evidence` dir (-R) | vocabulary/lockstep/redaction/lineage teeth |
| `framework/evidence/tests/test_lifecycle.py` (new) | `framework/evidence` dir (-R) | helper teeth (fail-closed, refusal/error branches, re-mint) |
| `framework/onboarding/journey.py` | named FILE | `act()` migrated onto the shared helper — byte-identical event stream (R-8) |
| `framework/schemas/evidence-event.schema.json` | named FILE | additive v1.1 vocabulary; v1 events still validate |
| `memory/golden-evals/eval-025-never-a-score.md` (new) | `memory/golden-evals` dir | the never-a-score law as a behavioral judge |

## Non-germline files changed by this batch (land with the merge, no ceremony)

- `cabinet/evals/never-a-score/{README.md,harness.py,fixtures/law-pins.json}` (new) — the EVAL-025 harness
- `cabinet/scripts/run-golden-evals.sh` — wires EVAL-025 into the pre-push suite
- `cabinet/scripts/tests/test_never_a_score_eval.py` (new) — harness teeth
- `cabinet/scripts/evidence-anchor.py` (new) + `cabinet/services.yml` — the read-only daily anchor job (staged service row)
- `framework/evidence_anchor.py` (new) — anchor collection/check logic (deliberately outside the germline package)
- `framework/tests/test_evidence_anchor.py`, `framework/tests/test_evidence_retention_classes.py`, `framework/tests/test_evidence_doctrine_laws.py` (new) — teeth
- `framework/onboarding/tests/test_act_bytestream.py` + `framework/onboarding/tests/data/premigration_journey_eef927f4.py.txt` (new) — the byte-identical migration gate
- `instance/config/evidence-anchor.yml.example` (new) — deployment-local anchor bindings template
- `docs/runbooks/evidence-recorder-v1.md` — v1.1 vocabulary, classification, lifecycle helper, per-class retention, anchoring runbook sections
- `docs/proposals/germline-amendment-evidence-phase1-2026-07-16.md` (this doc), `shared/interfaces/reviews/evidence-phase1-foundation-cp1.md`

## Apply ceremony (Captain sudo, on the armed Mac, same day)

The bytes land on master at the merge; the ceremony brings the on-disk
germline files up to the landed ref inside an unlock window and relocks.

```bash
# 0. from a CLEAN /Users/nate/captains-cabinet on master @ the merged tip
git -C /Users/nate/captains-cabinet fetch origin
git -C /Users/nate/captains-cabinet merge --ff-only origin/master

# 1. open the Captain edit window (schg is system-immutable; needs root)
sudo bash cabinet/scripts/germline-lock.sh unlock

# 2. re-materialize ONLY this amendment's germline file set at the merged ref
git -C /Users/nate/captains-cabinet checkout origin/master -- \
  framework/evidence/__init__.py framework/evidence/__main__.py \
  framework/evidence/classification.py framework/evidence/lifecycle.py \
  framework/evidence/recorder.py framework/evidence/redaction.py \
  framework/evidence/verifier.py \
  framework/evidence/tests/test_vocabulary_v11.py \
  framework/evidence/tests/test_lifecycle.py \
  framework/onboarding/journey.py \
  framework/schemas/evidence-event.schema.json \
  memory/golden-evals/eval-025-never-a-score.md

# 3. RELOCK the SAME day (arms schg over the whole set incl. the new files)
sudo bash cabinet/scripts/germline-lock.sh lock

# 4. verify the boundary is armed
bash cabinet/scripts/germline-lock.sh status
bash cabinet/scripts/germline-lock.sh verify
```

Because schg is *system*-immutable, steps 1 and 3 are the ONLY writable
window — the loop/officers cannot perform them. If interactive sudo is
unavailable to the orchestrator, this stays a named handback to Nate
(external limit that survives the standing grant). Do not work around the
lock.

## Zero behavior change — the Phase-1 contract, proven

- **v1 events still verify:** a store written by the pre-change (eef927f4)
  recorder passes the post-change verifier (all checks green) and projects
  through the unchanged officer doorway; pinned forever by
  `test_v1_vocabulary_events_still_verify_and_validate`.
- **Byte-identical producer:** the journey's event stream on the shared
  helper is byte-identical to the recorded pre-migration fixture
  (`test_act_bytestream.py`, 2 tests).
- **No suite shrinkage:** collected test ids at eef927f4 are a strict subset
  of this branch (0 removed, 26 added across evidence+onboarding).
- **Retention defaults:** `retention_classes` unset ⇒ the retention pass is
  byte-for-byte the previous scalar behavior; old control files verify
  unchanged.
- **No new runtime behavior:** the helper's only caller is the journey (same
  events); the anchor job is a STAGED services row (not enabled) and its
  script is read-only toward the store; no producer, no officer read surface,
  no schedule is added or changed.

## What does NOT change

- The locked SET (no boundary extension — see above).
- The officer read path: `cabinet/scripts/evidence-read.sh` is untouched;
  the projection remains the only officer view, `PROJECTION_ALLOWED_DETAIL`
  is the same allow-list hoisted to one reviewable constant, and the
  UNTRUSTED-OBSERVATIONS boundary stays on every record.
- `framework/evidence/policy.py` (the repair gate): zero edits this batch.
- No Monday/PolAds/instance specifics enter the framework layer
  (layer-separation gate green, no new entries).
