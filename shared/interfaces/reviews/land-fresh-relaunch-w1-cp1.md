# Checkpoint review — land/fresh-relaunch-w1, cp1 (Wave-1 landing)

**Scope:** the Wave-1 landing merge of `origin/feat/fresh-relaunch-prep`
onto `origin/master` (a4056f82) — launch machinery only: 3 scripts
(`cabinet/scripts/cabinet-deploy.sh`, `cabinet/scripts/runtime-provision.sh`,
`cabinet/scripts/relaunch-seed.sh`), a `cabinet-doctor.sh` check addition,
2 runbooks (`docs/runbooks/dev-runtime-split-cutover.md`,
`docs/runbooks/fresh-instance-relaunch.md`), the KEEP/DROP seed manifest
(`docs/plans/fresh-instance-relaunch-manifest-2026-07-15.md`), the branch's
own 4 FW-019 review artifacts, and the docs-sweep allowlist union. Merge
diff ~3.4k lines → FW-019 artifact required at commit time; this is it.

**Reviewer basis:** a clean-room review (AUD-1 isolation pattern: scratch
clone of origin/master, throwaway config) ran over the branch vs CURRENT
master before this landing. This artifact summarizes its verdict; the
integrator session applied ONLY the merge-resolution + the two CI-ratchet
fixes it prescribed.

## What the clean-room review established

1. **3 scripts reviewed against current master** (not the branch's stale
   fork point): cabinet-deploy.sh, runtime-provision.sh, relaunch-seed.sh.
2. **Core safety verified:** redis confinement holds; dry-run performs no
   kickstart; rollback path present; no secrets echoed by any script;
   fleet-safe (no live-tree/officer-session interference); **0 germline
   (schg) paths** among the 12 touched files.
3. **Exactly 2 CI blockers** (both A/B-verified: pass on true master,
   fail on the merged tree) — fixed IN THIS LANDING:
   * `relaunch-seed.sh` header prose carried a bare `product-brain` token
     → fails `test_vault_rename_ratchet.py::
     test_no_undeclared_product_brain_references` (ratchet landed
     2026-07-16). Prose reworded to "org-brain/vault"; zero behavior
     change.
   * `test_never_a_score_eval.py` scalar-consumer scan flags the two new
     files that mention the report-only golden-eval scalar series
     (jsonl; the literal filename is deliberately not written here — this
     artifact is not a sanctioned consumer either): `runtime-provision.sh`
     (INSTANCE_PERSISTENT_FILES persistence-symlink plumbing — never reads
     the series as a score) and the relaunch manifest (KEEP/DROP inventory
     doc, not a score consumer). Both added to the eval fixture's
     `scalar_reference_allowlist` with those honest reasons.
4. **Merge resolution:** single conflict in
   `cabinet/scripts/docs-sweep-allowlist.txt`; resolved as the UNION —
   every master entry kept (comms-charter / evidence-plane / retro-ledger
   additions incl. `instance/config/evidence-signing.yml`) AND the
   branch's `shared/cabinet.env` block with its WHY comment.

## Deferred to Wave 2 (per Captain 100%-SCRATCH ruling — NOT in this land)

* 2 high-severity findings, 2 medium, plus lows from the clean-room pass.
* The archive-only seeder rewrite of `relaunch-seed.sh`.
No seed behavior/logic was changed in Wave 1; only the prose reword and
the two allowlist entries above ride along with the merge.

## Verification performed in the landing worktree (python3.12)

* `test_vault_rename_ratchet.py` + `test_never_a_score_eval.py` — GREEN
  (the teeth on both fixes).
* `docs-track-code-sweep.sh` — GREEN (union allowlist holds).
* `check-layer-separation.sh` — 0 new violations.
* Full `cabinet/scripts/tests/` suite — green modulo the one pre-existing
  master failure the review pinned (`test_evidence_seam_bypass_replay
  [evidence-access.sh]`, fails identically on pristine master).
