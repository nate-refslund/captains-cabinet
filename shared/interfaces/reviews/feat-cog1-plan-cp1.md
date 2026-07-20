# COG-1 plan landing — review artifact (FW-019, branch feat/cog1-plan)

Verdict: PASS (plan-review; implementation not yet begun)

Scope of this batch: docs/plans/cognitive-core-phase-1-contract-2026-07-20.md (new, 369
lines) + the COG-1 ledger/plan-doc status flip todo→in-flight (append-only note with
provenance). No code.

Review evidence (process-law steps 2–3, run 2026-07-20):
- Ground: 8 Opus reader lenses + Fable synthesis over origin/master @cbf52e49
  (wf_7971a1ed-53a). Premise check reshaped the phase ×4 (canonical-tasks pinned to
  officer_tasks via the repo's own ratchet; torn-tail conditional closed
  verified-already-hardened; outbox_* vocabulary fencing added; relay framed as
  extend/compose of framework/outbox).
- Plan authorship: Fable planner (wf_1bc68d0b-f62), with a recorded leading dissent
  (refused event-type renames at the 91/91 cap on a Phase-0-promised file).
- Attack: 4 independent lenses — architecture (Fable), adversarial (Fable), operations
  (Opus), product-agnostic/governance (Opus). All verdict=revise; 1 P0 (consumer
  task-events-watch.py calls the frozen v1 validator directly and skip-ACKs — v2 would
  be silently poison-discarded; found by 3 lenses independently) + 16 deduplicated P1s.
- Revision: Fable reviser applied all 19 fixes (0 unfixed), byte-verifying every new
  claim; also fixed a fresh-hatch-breaking P1-3×P1-15 interaction (identity GUC ordered
  before 047 in load-preset) and a phantom citation the attackers missed.
- Verification: fresh Fable verifier — ready_to_land=true, all 19 blockers closed,
  12/12 byte-spot-checks EXACT, coherence confirmed. Three editorial nits fixed by the
  orchestrator before landing (M1 bytes-vs-behavior wording; §8.2a cross-reference;
  §9.3 destination-column exclusion named).
- Named deliberate interpretation carried forward for implementation reviewers: the
  foundry.md:255 shadow-gate stop condition is read EMISSION-scoped — capture is a
  stated live-in-transaction coupling from the 047 apply, gated by pre-apply harness
  evidence + a rehearsed one-command disarm (per the architecture attacker's own
  prescribed fix).

Gates at this commit: A13 parity OK (349 ids), ledger-status-parity GREEN (0 findings),
docs-track-code-sweep GREEN (60 files, 0 findings), egg-export 46 passed/1 skipped,
git diff --check clean.

Models: Fable 5 on judgment (planner/architecture/adversarial/reviser/verifier),
Opus 4.8 1M on execution lenses — per the two-tier routing law (Captain 2026-07-20).
