# Checkpoint review — feat/relaunch-phase0 (cp1) — 2026-07-21

FW-019 checkpoint-review artifact for the relaunch phase-0 batch (two reviewed
lanes integrated into one PR to master). Branch: `feat/relaunch-phase0`.
Interpreter: `python3.12`. Model note: this integration lane ran on
`claude-opus-4-8` (Captain-authorized Opus/Fable for the relaunch build); the
Lane A adversarial review was Fable 5.

## Scope of this batch

Two independently-reviewed fixes, landed together:

- **Lane A — killswitch send-path fail-closed.** Gates
  `framework/frontdoor/channel.py`'s `_post_one` (the single dict-payload
  chokepoint) and `send_document` (the one multipart send) on a fail-closed
  killswitch check that REUSES `action_exec`'s one SEC-3 reader
  (`_killswitch_state` over `_redis_get_strict`). Armed switch OR unreachable
  control plane HALTS every front-door send before any byte leaves the process,
  returning a structured refusal (never raising). Adds unit proofs, a
  deterministic golden-eval harness (EVAL-002-KILLSWITCH-SEND) wired into
  `run-golden-evals.sh`, the eval body, and a germline-amendment provenance
  doc. Send-path twin of EVAL-001 (killswitch at the pre-tool-use HOOK layer).
- **Lane B — gate-b null-hatch fix + runbook repo-identity.** Ships
  `instance/config/watchdog.yml.example` and an egg-export `watchdog-default`
  transform that materializes the live `watchdog.yml` from the scrubbed twin
  (same shape as `egress-default`), flipping the null-hatch (gate b) from RED
  (FileNotFoundError in the Phase-4 evidence-detectors lens test) to GREEN.
  Parameterizes the three cutover runbooks' provision URL to a
  `$NEW_REPO_URL` placeholder instead of the old private repo URL.

## Lane A adversarial review (Fable 5) — verdict: fix_required → FIXED

Four findings, all resolved in this batch:

- **(a) P1 census budget breach.** channel.py's fail-closed gate adds framework
  production non-comment lines; the shrink-only budget
  `framework_production_noncomment_lines` was exactly at its ceiling (62265).
  MEASURED delta with `cognitive-architecture-census.py --json` before/after:
  62265 → 62290 = **+25** (module count unchanged at 209; tests/, cabinet/evals,
  and instance/ are excluded from the count, so the delta is entirely
  channel.py). FIX: appended ONE `temporary_allowances` row to
  `cabinet/config/cognitive-architecture-contract.yml`
  (phase `relaunch-killswitch`, budget `framework_production_noncomment_lines`,
  additional **25**, sunset 2027-01-19, deletion_gate "killswitch gate folded or
  COG-7 compaction"), closed-set keys only. `census --check` now PASSES
  (62290 ≤ 62290).
- **(b) P1 egg-pin.** Lane A's new
  `docs/proposals/germline-amendment-killswitch-send-eval-2026-07-21.md` ships in
  the egg (kept by the `germline-amendment-*.md` glob in
  `t_proposals_archive`), which broke `test_egg_export.py`'s pinned sorted
  amendment list. FIX: inserted the filename into the sorted list, immediately
  after `germline-amendment-killswitch-events-2026-07-17.md` (`e` < `s`). Kept in
  the "kept" list per the Captain's not-yet-executed archive-out ruling (a later
  scrub wave reverses the whole amendments-kept policy; NOT reversed here).
- **(c) P3 wrapper completeness.** The three public send wrappers `open_thread`,
  `reply_current_observe_only`, `react_current_observe_only` were covered today
  (all funnel through `_post_one` via `_gated_method`/`_send_impl`) but were not
  in the harness send list. FIX: added all three to the harness (open_thread
  under the standard runtime; the two observe-only doorways under a new
  observe-mode runtime — they are structurally closed unless `allow_sends()` is
  False AND `CABINET_OBSERVE_ONLY=1`, which is the only mode they can reach the
  wire). Added a STRUCTURAL check (harness C5 + a mirroring pytest
  `test_every_public_send_routes_through_the_gated_chokepoint`): every public
  channel.py function taking an `http_post` param must call a gated spine
  (`_post_one`/`_send_impl`/`_gated_method`) or be `send_document` (own
  `_killswitch_halted` gate); the two indirect spines must themselves reach
  `_post_one`. A future send wrapper cannot silently bypass the stop.
- **(d) P2 verify method.** The egg-export / null-hatch / test_egg_export gates
  read git HEAD, so a staged-not-committed verify tests unpatched master. FIX:
  the batch is COMMITTED first, then the committed-tree gates are run against
  HEAD.

## Lane B review (Opus) — verdict: approve

The `watchdog-default` transform mirrors the established `egress-default`
pattern exactly (ship the scrubbed `.example` twin's bytes AS the live file so a
fresh egg hatches with a safe generic default; live watchdog data stays excluded
per the R120-class delete). Manifest gains matching `expect-present` +
verify-skip rows; the Phase-4 recompute shadow-proof test's reference
allowlist (under `framework/tests/`) gains the `.example` twin (which itself
names the staged-dark recompute-liveness id, hence the allowlist entry). Runbook change is a documentation-only parameterization. No
framework production-line impact (all Lane B code is in tests/, instance/, docs,
or shell transforms). Approved.

## Committed-tree verification (run on HEAD after commit)

- `cognitive-architecture-census.py --check` — PASS (62290 ≤ 62290)
- `pytest framework/frontdoor/tests cabinet/scripts/tests/test_killswitch_send_eval.py cabinet/scripts/tests/test_egg_export.py`
- `run-golden-evals.sh` — EVAL-002-KILLSWITCH-SEND PASS
- `null-hatch.sh` — PASS (Lane B fix)
- `check-layer-separation.sh` — new = 0
- `docs-track-code-sweep.sh`, `ledger-status-parity.sh`
- `pytest framework/ -q -rs` — no regressions

Pre-existing baseline (confirmed unchanged vs origin/master, NOT introduced
here): the two golden-eval fails FW-034/FW-076, and the COG-1 footprint ratchet
(`test_manifest_covers_committed_cog1_footprint`) which skips on shallow CI
checkouts and is scoped to the COG-1 baseline, not this relaunch work.
