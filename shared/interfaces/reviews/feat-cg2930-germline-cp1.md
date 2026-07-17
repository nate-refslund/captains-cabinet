# Checkpoint review — feat/cg2930-germline cp1 (2026-07-17)

Integration landing of the two reviewed germline-hygiene lanes (CG-29 +
CG-30) from one clean worktree off origin/master @ddcbd07b, plus the ledger
flips and docs-track-code truth-ups the landing itself requires. No schg
live inode is touched anywhere in this batch — germline git-side CONTENT
lands on master; the live box syncs at a Captain checkout window
(CG-27/CG-31 checkout-from-master precedent).

## Review provenance (pre-integration, per lane)

- **cg29-library-danglers** — adversarially re-verified before integration:
  lane diff re-applied on the master tip; master-first routing probed
  against the CG-27 (32a26c6d, ceremony e72da30c) / CG-31 (2bc98153)
  precedent; ratchet suite run pre/post diff; mutant re-run confirmed a
  re-granted `library` now TRIPS `test_germline_grant_surfaces_stay_library_free`.
- **cg30-vault-hookwatch** — reviewed lane diff (hook watch-arms + test
  locks in one unit); rooted `${CABINET_ROOT}/docs/*.md` pattern prevents
  foreign-repo ingest; legacy `*/product-brain/*.md` arm kept.

## What this batch contains

1. **CG-29 content** (removal-only on the two grant surfaces + comment-only
   on the launcher): `library` dropped from every `cabinet/mcp-scope.yml`
   officer/scaffold grant + `universal:`; `mcp__library` dropped from
   `.claude/settings.json` permissions.allow; stale
   "notion/linear/neon/library" merge-comment in
   `cabinet/scripts/start-officer-mac.sh` replaced (carries the
   `library deregistered 2026-07-16` mark the staged-patch ratchet skips
   on). Ratchet extended: `test_germline_grant_surfaces_stay_library_free`.
   Ledger/plan/addendum/runbook re-routed to master-first (lane-authored).
2. **CG-30 content**: `post-file-write-memory.sh` gains `*/vault/*.md` →
   product_brain + rooted `${CABINET_ROOT}/docs/*.md` → framework_doc,
   keeps the legacy arm; 3 pattern locks added to
   `test_bootstrap_memory_chain.py`.
3. **Integrator additions** (this checkpoint's own delta):
   - ledger yml + plan-doc rows CG-29/CG-30 flipped captain-gated→done,
     last_update 2026-07-17, notes record content-on-master +
     checkout-activate ceremony (never edit-in-live-tree); CG-30 gate_cmd
     revised from the superseded in-window `git apply` to
     checkout-from-master (mirrors CG-29/CG-31 wording).
   - `docs/proposals/germline-vault-hook-watch-addendum-2026-07-17.md`
     ceremony block revised to the checkout-from-master form (the old
     block would have had the Captain run a `git apply` that fails on
     already-landed content mid-sudo-window).
   - comment/docstring truth-ups in `test_bootstrap_memory_chain.py` and
     `test_vault_rename_ratchet.py` (ALLOWED reason string): patterns no
     longer "land via the patch" — they landed on master; patch = ceremony
     reference.

## Gates at this checkpoint

Pre-edit: A13 GREEN, uniqueness GREEN (327 ids), status-parity GREEN
(327/327). Post-edit battery (recorded in the landing evidence): both lane
suites + full cabinet/scripts/tests via python3.12, `bash -n` on the hook +
launcher, A13/status-parity/uniqueness re-run, docs-track-code sweep,
layer-separation new=0. schg guard: worktree copies carry NO flags; live-box
inodes verified schg (all three CG-29 surfaces + the hook file + the hooks
DIR) — activation stays Captain-window-only.
