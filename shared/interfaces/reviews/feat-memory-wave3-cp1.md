# Checkpoint review — feat/memory-wave3 cp1 (integration landing)

**Date:** 2026-07-16 · **Branch:** feat/memory-wave3 (worktree off origin/master
0baad320) · **Scope:** landing of memory-wave3 lanes BC / D / E from reviewed
lane diffs (base 405abed3) + ledger rows MEMORY-W3-BC/D/E + CG-27 + plan-doc §34
parity rows. Lane A-supersession deliberately NOT landed (not review-cleared at
integration time).

## Upstream lane reviews (performed pre-integration, per-lane; verdicts carried)

- **Lane BC (consolidation boot-pack):** all 9 review findings closed
  (P1 egg-export crash — .patch artifact moved to a plain file under
  docs/proposals/ + 2 expect-absent manifest rows; P1/P2 write plane — the
  staged germline patch now covers session-start.sh + pre-tool-use.sh +
  officer-sandbox.sh in ONE ceremony; P3 proposal-is-boot-path — --apply
  refuses unless the on-disk proposal byte-matches a fresh render; P2
  staleness — --check + doctor probe + retro Part 5 step 13; P2/P3
  docs-track-code — pack copies byte-parity + sweep GREEN). Teeth: the new
  suite fails 9 tests against the pre-fix build and 2 against a stale pack
  copy; doubling-line mutant, tamper/stale-proposal, pristine-hook-allows
  controls embedded. Post-ceremony simulation on a fresh clone: staged suite
  25 passed/1 skipped; germline-bash-write + germline-readonly harness
  verdicts byte-identical to pristine base; live-queue scan 0 leaked cls- rows.
- **Lane D (retrieval-eval gate):** four-layer wiring verified against the
  pinned base; ascending-sort blended mutant keeps recall@10=1.0 but collapses
  MRR to exactly 0.10 (no-rerank arm exits 1, rerank arm passes); live arms
  measurably diverge on the real store (rerank r@10=1.000/MRR=0.958 vs blended
  0.833/0.736); fingerprint stamped via a real passing live run; mutant
  controls (weight edit, rerank sort edit, seam removal) each change the sha,
  out-of-block comment edit does not; bash-awk vs python extraction parity
  pinned; bash-3.2 heredoc-quoting gotcha fixed with quote/paren-free markers.
- **Lane E (seam stamp):** both confirmed findings closed (P2
  detection-erasure — --if-absent is the only deploy-path mode, DO-NOTHING
  preserves stamped provenance so the DIMS-DRIFT WARN latches; P3
  three-readers — EMBED_* resolve process-env > cabinet/.env grep-extract >
  default identically in memory.sh and doctor ES_*). Proven end-to-end with a
  stateful stub psql incl. the latch cycle and a mutant reproducing the
  pre-fix false-green. Parameterized psql -v only; DSN never printed; no
  DELETE.

## Integration review (this checkpoint)

- Applied `git apply --3way` in lane order BC → D → E onto 0baad320. BC and E
  applied clean; D conflicted in cabinet/scripts/cabinet-doctor.sh and
  cabinet/services.yml (same-anchor insertions vs BC, and a pre-scrub context
  line). Resolutions verified line-by-line: BOTH doctor checks kept (BC N2
  digest-freshness + D check 11, each with its own header); services.yml keeps
  D's full retrieval-eval row AND master's de-Nate'd "Captain directive"
  comment (the diff's "Nate directive" context would have regressed the
  egg-scrub — rejected).
- Germline guard: `ls -lO` over every touched live path — none carry schg;
  germline-lock.sh status 78 locked / 0 unlocked, BOUNDARY ARMED. The
  boot-pack's schg-file changes ride ONLY the docs/proposals patch artifact +
  amendment doc (verified: no tree edit under cabinet/scripts/hooks/ or
  lib/officer-sandbox.sh).
- Verification in the integrated tree (python3.12): test_memory_distill +
  test_session_start_digest_patch 45 passed; test_retrieval_eval_gate 24
  passed; test_memory_rerank_toggle 5 passed; test_embed_seam_wiring 32
  passed; cabinet/scripts/lib/tests full 185 passed; cabinet/scripts/tests
  full 915 passed / 3 failed / 3 skipped — the 3 failures are
  test_egress_guard launchd-environment cases reproduced IDENTICALLY on a
  pristine 0baad320 worktree (pre-existing, not lane-caused). bash -n clean on
  all 6 touched .sh. docs-track-code-sweep GREEN (files=39 findings=0).
  check-layer-separation new=0. Ledger gates: A13 exit 0, uniqueness exit 0,
  ledger-status-parity GREEN (ids=312 md_rows=312 findings=0).
- Residuals (named, not blocking): lane A-supersession unlanded; the
  retrieval-eval launchd agent is not installed from this worktree (normal
  generate-plists + bootstrap path owns it); CG-27 ceremony is a Captain
  handback.

Verdict: LAND. One self-consistent unit; no unreviewed code beyond the two
conflict resolutions documented above.
