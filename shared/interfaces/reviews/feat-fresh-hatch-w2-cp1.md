# Checkpoint review — feat/fresh-hatch-w2, cp1

**Scope:** Wave-2 fresh-relaunch hardening (Captain 100%-SCRATCH ruling,
2026-07-18). One commit, off `origin/master @2f121dbe`. Seven content files
plus this artifact — 768 changed lines, so FW-019's checkpoint-review gate
trips on line count; this is that review.

- `cabinet/scripts/relaunch-seed.sh` — rewritten to ARCHIVE-ONLY (seeds
  nothing) + the relative-`--archive-path` containment fix.
- `cabinet/scripts/runtime-provision.sh` — persist 10 governance leaves + 3
  dirs across deploys; header provenance reword.
- `cabinet/scripts/cabinet-deploy.sh` — deploy-side consultant filter,
  `lib_roster` label-validated fleet derivation, non-canonical kickstart
  confinement, header reword.
- `.gitignore` — germline trio (posture/trust-ladder/standing-grants).
- `cabinet/scripts/tests/test_relaunch_seed_archive_only.py` — new (14 tests).
- `docs/runbooks/fresh-instance-relaunch.md`,
  `docs/plans/fresh-instance-relaunch-manifest-2026-07-15.md` — Docs-Must-
  Track-Code (archive-only behavior + supersession header).

**Reviewer:** self-review (authoring session). Genuine critical pass, not a
rubber stamp — the findings below were caught and fixed before this commit.

**Model note:** running on Opus 4.8 per the Captain 2026-07-18 exception
(Fable exhausted); the task itself states this, so no STOP was required.

## Security posture (Corridor analyzePlan, pre-code)

Corridor confirmed three guardrails, all satisfied:

1. **Path-containment-before-write.** `--archive-path` is absolutized
   (`$PWD` prefix) + lexically normalized BEFORE `refuse_if_nested`, mirroring
   the existing `RUNTIME_ROOT` handling. A relative archive path resolving
   into old-root is now refused (exit 64) instead of silently writing the tar
   inside the read-only source. Pinned by
   `test_relative_archive_path_inside_old_root_is_refused` +
   `..._outside_..._is_absolutized`.
2. **Secret masking.** The archive deliberately holds the real, un-rotated
   `cabinet/.env` (rollback net), but the script never echoes a secret VALUE —
   only paths/var-names — and the archive file is created mode-600. Pinned by
   `test_no_secret_value_leaks_to_output` + `test_archive_is_mode_restricted`.
3. **Regex-validated shell tokens.** `cabinet-deploy.sh`'s fleet derivation
   validates every roster-derived label with
   `re.fullmatch(r"com\.cabinet\.officer\.([a-z0-9-]+)")` before it becomes a
   shell token — a byte-mirror of `deploy-mac.sh`. Pinned by
   `test_roster_derivation_rejects_unsafe_label` (a `../evil` roster slug is
   rejected, not emitted).

## What was checked

1. **Removal, not flag-gating.** The load-bearing safety property of the
   archive-only seeder is that it never READS a live-content path. All six
   seed functions + `PRODUCT_SPECS` were DELETED, not commented/flagged
   (grep confirms zero residual `seed_*`/`PRODUCT_SPECS`/`has_env`).
2. **Archive completeness ("nothing lost").** Real end-to-end runs show the
   full old-root member captures `instance/memory/**` (org-brain + lane
   tier2), `shared/interfaces/**` (governance ledgers/world-chronicle/
   product-specs), and `cabinet/.env`, excluding only `__pycache__`/`*.pyc`;
   `.git` kept. The seed dir stays empty of live content.
3. **`.gitignore` twins.** The germline trio is now IGNORED; the tracked
   `*.yml.example` twins remain not-ignored and tracked (verified via
   `git check-ignore` + `git ls-files`).
4. **`act-first-surfaces.yml` NOT added** to `INSTANCE_PERSISTENT_FILES` —
   it is git-tracked; linking would shadow it (verified tracked). Its absence
   is documented in-line.
5. **Ratchets + gates green over the working tree:** vault-rename ratchet
   (no `product-brain` token introduced in `relaunch-seed.sh` or the runbook —
   both are ratchet-forbidden surfaces; the manifest is `docs/plans/` =
   historical-allowlisted so its existing mentions stay), never-a-score,
   library-retirement, `docs-track-code-sweep` (GREEN 60/0), layer-sep (no new
   violations — no `framework/`/`presets/` Python touched), `bash -n` on all
   three scripts.

## Findings (fixed before this commit)

1. **[stale-doc-in-code] CONTAINMENT header referenced deleted functions.**
   The original `relaunch-seed.sh` CONTAINMENT paragraph justified the
   reverse-nesting guard by naming `seed_officer_memory`'s converge-by-delete
   — a function this change deletes. Left as-is it would dangle. Reworded to
   the general "no path this script touches can alias its own read-only
   source" rationale; the guard itself is kept (defense-in-depth) and now also
   documents the absolutize-before-guard fix.
2. **[accuracy] "ENTIRELY gitignored" was wrong.** `runtime-provision.sh`'s
   header claimed `roles/{active,archive,hats}` are entirely gitignored;
   `git ls-files` shows each ships a tracked `.gitkeep` (negated in
   `.gitignore`). Reworded to "bulk-gitignored except a tracked `.gitkeep`
   skeleton", and the new persistence dirs were folded into the same
   enumeration to keep the header in lockstep with the code.
3. **[docs-track-code] runbook seed language + a stale cross-ref.** Every
   "carried forward / curated seed / seeded `.env` / `__ROTATE_ME__`
   placeholder" reference was moved to archive-only wording; the §0
   reversibility note's "before anything is seeded or moved … §7 Rollback"
   was both seed-stale and a wrong section ref (rollback is Step 9) — fixed
   in the one sentence I was already touching.
4. **[back-compat] `--telegram-token-var` kept as accepted-but-inert.**
   Rather than drop the flag (which would break existing runbook
   invocations), it is accepted as a documented no-op; its value is still
   validated as a well-formed env-var name so a malformed one still fails
   loudly.

## Verification evidence

- New suite: `test_relaunch_seed_archive_only.py` — **14 passed**.
- Regression-adjacent: `test_lib_roster` + `test_deploy_mac_exact_fleet` +
  `test_deploy_mac_stop` + `test_recovery_exact` — **50 passed** (no existing
  test covered the three edited scripts before this change; mine is first).
- `.gitignore`-reading suites (`test_memory_supersede_apply`,
  `test_task_sync_scheduling`, `test_world_asset_intake`) — **128 passed**.
- Ratchets (`vault_rename` + `never_a_score` + `library_retirement`) —
  **26 passed, 1 skipped**.
- `docs-track-code-sweep` GREEN (files=60 findings=0); layer-sep OK
  (baseline=24 allowlist=19 current=43 new=0); `bash -n` clean ×3.

## Out of scope (named, not touched)

Audit `PRELAUNCH-FOUNDATION-AUDIT-2026-07-18.md` items #56 (PEP-668), #57
(work-store schemas), #58 (doctor-RED scope grants), #59 (doctor-side
consultant keepalive), #60 (baked PATH) are fresh-hatch-path defects tracked
separately — none is a `relaunch-seed`/`runtime-provision`/`cabinet-deploy`
surface. Item 4a here is the DEPLOY side of the consultant seam and aligns
`cabinet-deploy` with `deploy-mac`'s `guard_consultant`; it does NOT close the
doctor-side #59.
