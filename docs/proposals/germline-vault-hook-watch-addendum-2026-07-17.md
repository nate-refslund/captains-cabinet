# Germline addendum — vault/docs watch patterns for post-file-write-memory.sh

- **Date:** 2026-07-17 (vault wave)
- **Provenance:** Captain-ratified 2026-07-16 — `product-brain/` becomes the
  cabinet's default VAULT (`vault/`), and the `docs/` tree joins the memory
  index. Landed per the 2026-07-07 full-autonomy grant; THIS file is the
  ceremony note for the one schg-locked piece.
- **Staged patch:** `patches/germline-vault-hook-watch-2026-07-17.patch`
- **Why a ceremony:** `cabinet/scripts/hooks/` is a germline DIR
  (`germline-lock.sh` DIRS list, locked `-R` with schg). The vault-rename lane
  deliberately shipped ZERO edits inside it — a merge must never touch
  germline paths. The hook's watch list is the only rename surface that lives
  there.

## What the patch does

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
patterns, so they can only land WITH the hook change).

## Interim state (until the ceremony) — already covered

- The nightly `memory-reconcile` (03:30) walks `vault/`, legacy
  `product-brain/`, and `docs/**/*.md` DIRECTLY (landed unlocked in the same
  wave), so every vault/docs write is embedded at most one night late.
- `backfill-memory.sh` queues both trees with explicit source_types —
  independent of the hook's watch list.
- The only ceremony delta is INSTANT (same-session) embedding of vault/docs
  writes via the hook.

## Apply ceremony (Captain sudo window — relock the SAME day)

```bash
cd "$CABINET_ROOT"
sudo bash cabinet/scripts/germline-lock.sh unlock cabinet/scripts/hooks
git apply --3way patches/germline-vault-hook-watch-2026-07-17.patch
bash -n cabinet/scripts/hooks/post-file-write-memory.sh
python3.12 -m pytest cabinet/scripts/tests/test_bootstrap_memory_chain.py -q
git add -- cabinet/scripts/hooks/post-file-write-memory.sh \
           cabinet/scripts/tests/test_bootstrap_memory_chain.py
git commit   # normal trailer; push per the multi-writer protocol
sudo bash cabinet/scripts/germline-lock.sh lock
bash cabinet/scripts/germline-lock.sh status
```

## Same-window optional cleanup (text-only, recorded here so it isn't lost)

`framework/acting/run_action_lane.py` (schg) still imports and calls
`framework.env.product_brain_dir` — a WORKING deprecated alias of
`org_vault_dir()`, so nothing is broken and no urgent edit exists. At the
next convenient unlock window, flip the import/call + the gather_signals
docstring to `org_vault_dir` and drop the alias from the lane; the alias
itself stays in `framework/env.py` until then (the rename ratchet allowlists
both files with this reason).
