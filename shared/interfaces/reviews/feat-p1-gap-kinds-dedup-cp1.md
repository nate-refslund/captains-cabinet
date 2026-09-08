# Checkpoint review — feat/p1-gap-kinds-dedup (cp1)

Reviewed-Scope-Digest: a80ae979b7e37eb24c5479402c18e61acbe1e70ceb7dbcf08aceadd0ea87be15

Unit U3a of the phase-1 contract (`phase1-contracts-v2-2026-09-07.md` §3 —
the `capability_gaps.py` half only — plus amendments A3.1, A3.2, A0.3).
Reviewer: the building session, on a fresh clone of origin/master 1d1aec53,
against the staged bytes above.

## What the staged bytes do

1. `framework/learning/capability_gaps.py`
   - `VALID_KINDS` gains `skill | authority | information`, held as
     `STRUCTURAL_KINDS` and separated from `ACTIONABLE_KINDS`. Surface-only in
     three independent places, so no single edit re-opens the lane:
     `route_open_gaps` buckets them under a new `surfaced` key and returns
     before any `propose_gap`/`notify_fn`; `can_auto_apply` vetoes them ahead of
     the policy lookup; `load_autonomy` reads `defaults:` for actionable kinds
     only, so `autonomy.yml` cannot grant an auto lane that does not exist.
   - `classify()`'s ambiguity fallback is narrowed from "any VALID_KIND that is
     not `procedure`" to the two propose kinds. Without this, widening
     `VALID_KINDS` would let an ambiguous need resolve to a structural kind and
     go SILENT — the inverse of the module's err-toward-human-in-loop rule.
   - `record_gap(..., dedup_key=None)`: keyed records dedupe on identity
     (`gap-<sha1(key)[:8]>`), never run the Jaccard scan, and are never a merge
     target (the scan skips any gap carrying a `dedup_key`). Both directions,
     as A3.1 requires. Re-observing a LIVE keyed gap returns it and emits
     nothing; a resolved/declined one re-opens, which the projection already
     models.
   - The keyed check-then-emit runs under `_gaps_lock()` — `flock` on a file
     beside the JSONL ledger the projection replays, so the lock's scope is the
     dedupe's scope. Lock order is always gaps-lock → ledger-lock.
2. `cabinet/dashboard/src/lib/capability-gaps.ts` — `GapKind` widened;
   `gap-row.tsx`'s `KIND_STYLES` becomes `Partial<Record<GapKind, string>>` so
   an unknown kind renders by name through the badge fallback that already
   existed (zero new UI, and no code change needed for the next kind).
3. A0.3: the two `/gaps` exec strings pin `${CABINET_PYTHON:-python3.12}`
   (bash expands both the native and the container path), and the module stays
   3.9-parseable with a test pinning it.
4. Docs tracking code in the same commit: the officer-facing skill doc and
   `record-capability-gap.sh --help` now name the third, surface-only lane.

## What I checked, and what I found

- **Every sensor red for the reason its invariant names.** The invariant
  harness runs the SAME assertions against master's API (no `dedup_key`), so
  the red arm is a violated invariant, never an unknown keyword: master
  classifies a `skill` gap to `tool`, proposes it and fires `notify_fn`;
  three passes over two subjects yield 1 recorded + 5 merged + 1 gap (two
  subjects collapsed into one); 16 concurrent observers write 16 records.
  Four mutation arms confirm the committed tests are wired to the controls
  (drop the lock → 10 records; let the scan see keyed gaps → a merge event;
  drop the auto veto → the config grants auto; revert the classify guard →
  `authority` returned).
- **Degenerate ends.** Blank key falls back to similarity; a closed keyed gap
  re-opens rather than staying silent; `test_keyed_gap_is_never_a_merge_target`
  asserts its own premise (the two needs ARE over the 0.6 threshold), so it
  cannot pass because the strings were dissimilar.
- **Return-shape compatibility.** `self_improvement_loop` reads the routing
  dict with `.get(key, [])`; the new `surfaced` key is additive. Structural
  gaps are deliberately NOT put in `skipped`, which means "this pass could not
  route it" and must stay countable.
- **Locked set.** 0 of the 7 staged paths intersect the 80 entries parsed from
  `germline-lock.sh` FILES/DIRS.

## Residuals (carried on the PR, not fixed here)

- The loop's own summary does not yet count `surfaced` — `self_improvement_loop.py`
  is outside this unit's file list.
- A3.3 (briefing-card line for `authority`/`information`) and the
  `missions/gaps.py` producer are U3b's.
- A0.3's repo-wide grep sensor over bare `python3` in unlocked exec strings
  waits on U2, which owns the remaining anchor (`work-graph-complete.sh`).
- The 3.9 sensor here is grammar-level (the repo's existing
  `ast.parse(feature_version=(3, 9))` pattern) plus a recorded live import
  under 3.9.6; the standing runtime-3.9 CI leg arrives with the drill.
