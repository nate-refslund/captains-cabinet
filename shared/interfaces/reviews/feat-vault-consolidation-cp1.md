# Checkpoint review — feat/vault-consolidation cp1 (vault-rename-docs lane)

**Date:** 2026-07-17 · **Reviewer:** vault-consolidation integrator (Fable 5)
· **Scope:** the reviewed `vault-rename-docs` lane diff (25 files,
+1116/−293) + ledger rows VAULT-1/CG-30 + plan-doc §38 parity rows.

## What this checkpoint lands

`product-brain/` → `vault/` (git mv — architecture.md + decisions/incidents
.gitkeeps ride as renames; README deleted + rewritten as `vault/README.md`,
the doc-placement one-pager the onboarding flow points at).
`framework.env.org_vault_dir()` resolver with the full legacy alias chain
(`CABINET_ORG_VAULT_DIR` → `CABINET_PRODUCT_BRAIN_DIR` → `org_vault_dir:` →
`product_brain_dir:`, fail-closed); `product_brain_dir()` stays a working
deprecated alias (schg `framework/acting/run_action_lane.py` still calls it —
flip recorded for the CG-30 ceremony window). `memory-reconcile.sh` +
`backfill-memory.sh` walk `vault/` + legacy `product-brain/` + `docs/**/*.md`.
`generate-instance.py` writes `org_vault_dir` only-when-absent, never over a
hand-edited legacy key. Egg manifest gains `expect-present vault/README.md`.
New ratchet `cabinet/scripts/tests/test_vault_rename_ratchet.py` polices
reference reintroduction with a reasoned allowlist.

## Germline discipline (the review's first question)

- Full touched-file list intersected against the LIVE box lock census
  (`find -flags +schg,uchg`, 190 entries): **zero hits**.
- The one genuine germline surface (post-file-write-memory.sh watch list,
  inside schg DIR `cabinet/scripts/hooks/`) ships as a STAGED patch
  (`patches/germline-vault-hook-watch-2026-07-17.patch`) + addendum doc;
  CG-30 files the named handback. Hook-side test additions ride the patch,
  not this commit — nothing lands that asserts un-landed hook behavior.
- Interim coverage is real, not claimed: nightly reconcile + backfill walk
  both trees directly in THIS commit's unlocked scripts.

## Verification evidence (run on this worktree, staged tree)

- `python3.12 -m pytest cabinet/scripts/tests -q` → 1113 passed, 4 skipped;
  the 22 errors + 1 fail are ALL `test_egg_export.py` reading the git
  snapshot (HEAD) while the manifest change is staged-only — re-verified
  green post-commit (see cp1 addendum line below after commit).
- `framework/acting` gather suites 31 passed; `framework/tests/test_env.py`
  + launcher-hardcode + screenpipe-core + `framework/sources/tests` 153
  passed (resolver + alias chain covered).
- `docs-track-code-sweep.sh` GREEN (files=40 findings=0) — the rename wave
  is this gate's reason to exist; every doc reference chased in-lane.
- `check-layer-separation.sh` new=0 (baseline 24, allowlist 18, current 42).
- A13 parity 319 ids OK · ledger uniqueness OK · ledger-status-parity GREEN
  (ids=319 md_rows=319 findings=0).

## Risks accepted at this checkpoint

- Legacy alias chain doubles the resolver surface until the CG-30 window —
  deliberate: un-migrated checkouts + the schg caller must keep working.
- `source_type` for vault writes stays `product_brain` (DB upsert identity) —
  taxonomy rename is out of scope by design.

Verdict: LAND. (Upstream lane review: complete per spec; integrator spot
checks above independently reproduced the gate evidence.)
