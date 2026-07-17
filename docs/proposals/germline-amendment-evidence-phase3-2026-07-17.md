# Germline amendment — EVIDENCE PHASE 3 (cross-trial query plane) — 2026-07-17

**Status:** PROPOSED on `feat/evidence-phase3-review-surface` (off
`91dcdc75`). The Captain's merge of this branch to master (after CI is
green) is the apply; the post-merge on-Mac unlock ceremony below
re-materializes the schg paths at the landed bytes and relocks the same day.

**Design of record:** whole-cabinet evidence & self-improvement phased
design (2026-07-16), §3 Phase 3 item 1 (cross-trial read plane) under the
§2 safety envelope (never-a-score §2.5; read seam §2.4; A8 same-projection
law), §8 decisions D1–D9. Authored and self-ratified per the 2026-07-07
full-autonomy grant; the ceremony itself stays Captain-only.

**Checkpoint review:**
`shared/interfaces/reviews/evidence-phase3-review-surface-cp1.md` (FW-019
artifact for this >300-line batch).

## What this batch is (Phase 3 — humans judge first)

Phase 3 is PURE READ-ONLY additions with exactly ONE designed write:

1. **Cross-trial query plane** (germline — this amendment): the existing
   `project` verb learns ONE reserved selector-token namespace
   (`by-actor:` / `by-component:` / `by-status:` / `by-time:`), validated
   fail-closed and matched IN MEMORY against verified rows only; served
   records come verbatim from the existing single-trial
   `cabinet_projection` (verification, redaction, allow-list, banner all
   inherited, never re-implemented). Every served trial passes verification
   or renders as an explicit UNVERIFIED stub. Output is records plus honest
   counts — no rates, no rankings, no aggregates.
2. **Dashboard evidence page** (non-germline): auth-gated, read-only
   `/evidence` in the receipts read-model discipline, real-Python-verifier
   fail-closed display, evidence-basis tag on every row (B6). No label
   verb, no write path.
3. **Weekly governance review** (non-germline): the Captain-token-gated,
   TTY-only labeling ritual (`cabinet/scripts/governance-review.py`) — the
   phase's ONE designed write, through the recorder's EXISTING captain-token
   mechanism (never a new auth scheme, never officer-invokable). Labels
   land as verification/outcome events on the judged trial; content-free
   digests ride the daily external anchor.
4. **Digest citations + coverage/anchor registration** (non-germline):
   ACTED digest items cite their evidence trial id; the ritual registers in
   `evidence-coverage.py`; the labels journal joins the anchor's
   `captain_labels` set.

Everything except the query plane rides the ordinary review path in the
same PR. Seam law for the batch (pinned by tests): ONE validation truth —
the page's filter grammar mirrors the query plane's rules, pinned by
`cabinet/scripts/tests/test_evidence_read_lockstep.py` + the shared case
vector run by BOTH suites; the label join is proven end-to-end
(CLI label → query plane / officer projection → dashboard read model)
by `cabinet/scripts/tests/test_evidence_label_join.py` and
`cabinet/dashboard/src/lib/evidence/label-join.e2e.test.ts`.

## Why this touches germline

The selector grammar is OFFICER-REACHABLE input surface: a selector token
fits the byte-identical doorway (`cabinet/scripts/evidence-read.sh`, one
bounded token — the doorway script is NOT changed), so the code that parses
officer-supplied filter values and decides what evidence officers can see
belongs inside the locked evidence package, where its validation,
redaction-inheritance, and never-a-score shape cannot be edited by the
population it screens. `framework/evidence` is a recursive `DIRS[]` cover,
so the new module and its test are locked the moment they land.

**Design-refinement note (R-9, held honestly):** R-9 recommended a
rebuildable derived read-model OUTSIDE germline to keep query dimensions
ceremony-free. This batch builds NO derived index at all (nothing to
rebuild — bounded verified-read filtering only), and deliberately accepts
that new officer-reachable query dimensions are a ceremony: the selector
namespace is a widening of what officers can ASK the evidence plane, and
widenings of an officer surface are exactly what ceremonies are for. The
Captain-facing read model (the dashboard page) lives outside germline, per
R-9's spirit.

**No boundary extension.** No path JOINS or LEAVES the locked set:
`cabinet/scripts/germline-lock.sh` `FILES[]`/`DIRS[]`,
`framework/policies/immutable-core.yml`, and the pre-tool-use hook screen
are all byte-identical in this branch (verified: `git diff` empty on all
three). The germline lockstep consistency suite is green (see the review
artifact for the run).

## Exact ceremony file list

The complete set of schg-locked paths whose content this branch changes —
verified mechanically against `germline-lock.sh` `FILES[]` + `DIRS[]` over
the composed diff (3 of 32 changed paths; no other germline path is
touched; `cabinet/scripts/evidence-read.sh` is byte-identical):

1. `framework/evidence/__main__.py` (modified — `DIRS[]` cover
   `framework/evidence`): `project` dispatches a reserved selector token to
   the query plane; trial-id behavior unchanged.
2. `framework/evidence/query.py` (NEW — `DIRS[]` cover
   `framework/evidence`): the cross-trial selector module.
3. `framework/evidence/tests/test_query_plane.py` (NEW — `DIRS[]` cover
   `framework/evidence`): its adversarial suite (bypass-shape replay,
   never-a-score key pins, read-only proof, doorway-argv pins).

## Live application (Captain, same day)

On the armed Mac, after the merge lands on master (the dir unlock is
required for the two NEW files — `chflags -R schg` blocks new-file
creation inside the cover):

```bash
cd /Users/nate/captains-cabinet
sudo cabinet/scripts/germline-lock.sh unlock
git -C . fetch origin && git -C . checkout origin/master -- \
  framework/evidence/__main__.py \
  framework/evidence/query.py \
  framework/evidence/tests/test_query_plane.py
sudo cabinet/scripts/germline-lock.sh lock
cabinet/scripts/germline-lock.sh verify
python3.12 -m pytest framework/evidence \
  framework/tests/test_germline_lockstep_consistency.py \
  cabinet/scripts/tests/test_evidence_label_join.py \
  cabinet/scripts/tests/test_evidence_read_lockstep.py -q
```

Relock the SAME day. `germline-lock.sh verify` and the lockstep suite are
the exit checks; any drift is a stop-and-page, not a workaround.

## Safety envelope conformance (§2, binding)

- **Fail-closed display everywhere:** every trial served by the query
  plane, the doorway, or the dashboard passes verification first or
  renders explicitly UNVERIFIED (pinned:
  `test_query_plane.py::test_tampered_trial_renders_explicit_unverified_stub`,
  dashboard `read.test.ts` fail-closed suite, governance-review
  verify-before-present tests).
- **Officer doorway unchanged and still the only officer read path:**
  `evidence-read.sh` byte-identical; selector tokens fit its existing
  one-token grammar; the PR#140/#149 bypass catalog is replayed against
  the selector argument (`test_selector_validation_refuses_bypass_shapes`,
  `test_doorway_rejects_bypass_shapes_before_any_exec`, the dashboard
  filter replay, and the shared filter case vector).
- **Never-a-score:** no evidence-derived aggregate is officer-visible —
  the query output is records + honest counts only; EVAL-025 and
  `test_never_a_score_eval.py` green; the dashboard is Captain-facing and
  auth-gated.
- **One write, token-gated:** the only mutation in the whole phase is the
  Captain label append through the EXISTING capability-token gate
  (`__main__.py` derivation reused verbatim); no-token / forged-token /
  non-TTY / dry-run paths leave the store byte-identical (pinned).
  Read-only proof: the full projection/page/digest read surface leaves the
  store tree byte-identical at rest (ledger bytes always; the verifier's
  anti-rollback watermark advance on a trial's FIRST verify is the same
  sanctioned side effect `verify` has always had, byte-stable at tip).
- **Determinism:** stored bytes == hashed bytes; v1 and v1.1 events
  verify; identical query inputs yield identical output (pinned:
  `test_deterministic_ordering_and_repeatability`).
- **Untrusted-observations banner** on every served view, byte-identical
  to the single-trial projection (pinned equality test).
- **Observe-only soak (D8):** all additions are reads; the ritual is
  Captain-initiated; zero officer behavior change.
