# Action-mode eval (EVAL-026) — harness + fixtures

Runnable half of golden eval **eval-026-action-mode-autonomy-seam**
(AUTONOMY-GRADED ACTION SEAM, Captain law 2026-07-17): every autonomous
mutation's mode is a FUNCTION of the posture level — propose-first/earn-trust
→ ASK; act-then-tell → ACT with proven undo + receipt; sovereign → GO;
**Ring-0 ALWAYS Captain regardless**. Unknown posture/ring/reversibility →
propose (fail-closed).

The eval BODY belongs in `memory/golden-evals/` (schg-locked on the live
checkout); it is staged for the Captain's next germline window via
`docs/proposals/germline-amendment-action-mode-eval-2026-07-17.md`. The
runnable half lives here, non-germline, wired into
`cabinet/scripts/run-golden-evals.sh` (section EVAL-026-ACTION-MODE).

Layout:
- `harness.py` — deterministic `--self-test` CLI (no LLM, no network, no
  subprocess). Imports `framework/authority/action_mode.py` and checks:
  1. every pinned matrix arm in `fixtures/matrix.json` returns exactly the
     pinned `(mode, captain_card)` — postures are passed explicitly, so the
     harness never reads the live instance ruling (hermetic on any box);
  2. `RING0_CATEGORIES` equals the fixture's enumeration EXACTLY — a
     widened or shrunk Captain-only plane is a mismatch, never a skip;
  3. the mode vocabulary stays exactly `{propose, act_tell, go}`.
- `fixtures/matrix.json` — the pinned posture × ring × reversibility
  matrix: the three ladder levels + the forward-compatible `act_then_tell`
  rung (undo-handle-required rule, both refusal arms), the Ring-0 override
  under EVERY posture, the category backstop (a Ring-0 category outranks a
  claimed ring 2, normalization variants included), and every fail-closed
  arm (unknown posture/ring/reversibility, empty category, non-mapping
  descriptor).

Run it directly:

    python3.12 cabinet/evals/action-mode/harness.py --self-test

Companion pytest suite (richer arms, resolver integration, purity, the
`ring_for_repo_path` immutable-core read):
`framework/authority/tests/test_action_mode.py`.
