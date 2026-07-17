# Germline addendum — vault/docs watch patterns for post-file-write-memory.sh

- **Date:** 2026-07-17 (vault wave; ceremony block revised to MASTER-FIRST
  the same day — ledger row CG-30)
- **Provenance:** Captain-ratified 2026-07-16 — `product-brain/` becomes the
  cabinet's default VAULT (`vault/`), and the `docs/` tree joins the memory
  index. Landed per the 2026-07-07 full-autonomy grant; THIS file is the
  ceremony note for the one schg-locked piece.
- **Reference patch:** `patches/germline-vault-hook-watch-2026-07-17.patch`
  — kept as the ceremony proof; SUPERSEDED as an apply step by the master
  checkout (the CG-27/CG-31 checkout-from-master precedent).
- **Why a ceremony:** `cabinet/scripts/hooks/` is a germline DIR
  (`germline-lock.sh` DIRS list, locked `-R` with schg) — on the LIVE box the
  hook inode cannot change outside a Captain sudo window. The git-side
  content (tree files are NOT schg in a clean worktree) landed on master
  2026-07-17 in the CG-30 landing commit; the window's only job is syncing
  the live inode to that already-reviewed master content.

## What landed on master (git side, no lock touched)

`cabinet/scripts/hooks/post-file-write-memory.sh` (`pfwm_source_type`):

1. adds `*/vault/*.md` → `product_brain` (the cabinet vault, any depth;
   the source_type keeps the pre-rename DB taxonomy name so existing
   `cabinet_memory` rows' upsert identity survives);
2. adds `"${CABINET_ROOT}"/docs/*.md` → `framework_doc` (ROOTED under the
   deployment root on purpose — an unrooted `*/docs/*.md` would ingest any
   foreign repo's docs tree an officer happens to edit);
3. KEEPS the legacy `*/product-brain/*.md` arm (un-migrated checkouts and
   externally-relocated corpora with the old dir name still embed).

Plus the hook-side test additions in
`cabinet/scripts/tests/test_bootstrap_memory_chain.py` (they assert the new
patterns and landed WITH the hook change in the same commit).

## Interim state (live box, until the sync window) — already covered

- The nightly `memory-reconcile` (03:30) walks `vault/`, legacy
  `product-brain/`, and `docs/**/*.md` DIRECTLY (landed unlocked in the same
  wave), so every vault/docs write is embedded at most one night late.
- `backfill-memory.sh` queues both trees with explicit source_types —
  independent of the hook's watch list.
- The only ceremony delta is INSTANT (same-session) embedding of vault/docs
  writes via the hook.

## Live-inode sync ceremony (Captain sudo window — relock the SAME day)

The window does NOT patch or commit — the content is already on master; it
syncs the schg live inode via checkout-from-master (CG-27/CG-31 precedent):

```bash
cd "$CABINET_ROOT"
git fetch origin
sudo bash cabinet/scripts/germline-lock.sh unlock cabinet/scripts/hooks
git checkout origin/master -- cabinet/scripts/hooks/post-file-write-memory.sh
git diff --quiet origin/master -- cabinet/scripts/hooks/post-file-write-memory.sh  # blob-verify
bash -n cabinet/scripts/hooks/post-file-write-memory.sh
sudo bash cabinet/scripts/germline-lock.sh lock
bash cabinet/scripts/germline-lock.sh status && bash cabinet/scripts/germline-lock.sh verify
python3.12 -m pytest cabinet/scripts/tests/test_bootstrap_memory_chain.py -q
```

## Same-window optional cleanup (text-only, recorded here so it isn't lost)

`framework/acting/run_action_lane.py` (schg) still imports and calls
`framework.env.product_brain_dir` — a WORKING deprecated alias of
`org_vault_dir()`, so nothing is broken and no urgent edit exists. At the
next convenient unlock window, flip the import/call + the gather_signals
docstring to `org_vault_dir` and drop the alias from the lane; the alias
itself stays in `framework/env.py` until then (the rename ratchet allowlists
both files with this reason).
