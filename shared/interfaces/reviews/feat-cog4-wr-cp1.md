# FW-019 review artifact — feat/cog4-wr cp1 (WR riders landing)

Branch: `feat/cog4-wr` off `origin/master` @ `de5d16c4` · Landing agent, 2026-07-23.

## What lands

The COG-4 WR rider lane — two read-only, serve-surface-only instruments:

- **R1 — the verdict inbox** (cherry-pick of `fe2ecfee` → `38fe6560`):
  `cabinet/scripts/cog3-verdict-inbox.py` (457 lines) + battery
  `test_cog3_verdict_inbox.py` (418 lines) + gate/manifest/pin-test entries
  + unit review artifact `feat-cog4-wr-r1-cp1.md`. 6 files, 976 insertions.
- **R3 — the weekly shadow-dividend report** (cherry-pick of `10e31dc4` →
  `a2323149`): `cabinet/scripts/cog3-shadow-dividend.py` (560 lines) +
  battery `test_cog3_shadow_dividend.py` (419 lines) + gate/pin-test entries
  + unit review artifact `feat-cog4-wr-r3-cp1.md`. 5 files, 1035 insertions.

Total: ~2011 inserted lines across 11 file changes (2 shared files joined).

## Review chain

Both units were built in isolated worktrees and **fresh-context adversarially
reviewed: SHIP, zero must-fixes** (see the per-unit cp artifacts
`feat-cog4-wr-r1-cp1.md` / `feat-cog4-wr-r3-cp1.md`, which record the review
claims re-run). Per the landing brief, content is landed faithfully — no
re-litigation; this artifact covers the integration only.

## Cross-unit joins reconciled by the landing agent (integrator law L1111)

Both units grew the same exact-set surfaces in their own commits; reconciled
by UNION — no entry from either unit dropped:

1. `cabinet/scripts/cog2-import-gate.py` — `ALLOWLIST_EXACT_OBJECTIVES`:
   both CLIs present, each keeping its own provenance comment.
2. `cabinet/scripts/tests/test_cog3_import_gate.py` —
   `test_cog3_allowlist_covers_the_reader_clis_only`: exact-set assertion now
   pins the three wave-1 instruments **plus both riders**; the doc comment
   merged to name both (R1 BACKLOG :1559 · R3 COG-4 §18).
3. `cabinet/scripts/egg-export-manifest.txt` — R1 shipped its own
   `expect-present` entry; R3 shipped none, so the landing added
   `expect-present cabinet/scripts/cog3-shadow-dividend.py` (+ comment
   mirroring the R1 pattern) so BOTH CLIs are present in every joined
   surface, as the landing brief requires.

## Verification on the integrated branch (python3.12)

- R1 + R3 + import-gate batteries: **82 passed**.
- `cog2-import-gate.py` scan: **OK** (shadow boundary intact).
- `check-layer-separation.sh`: **OK** — baseline=24 allowlist=19 current=43
  new=0 fixed=0.
- `verify-cognitive-architecture.sh` (census): **PASS**.
- `test_egg_export.py`: **58 passed, 1 skipped** (validates the manifest join).
- Full `cabinet/scripts/tests` sweep: **3 failed, 2627 passed, 10 skipped**
  — the 3 failures are exactly the documented pre-existing rollback-ratchet
  full-clone failures
  (`test_cognitive_phase{1,2,3}_rollback::test_manifest_covers_committed_cogN_footprint`),
  re-confirmed failing IDENTICALLY on a clean `origin/master` worktree
  (pre-existing, not introduced here; being fixed by a parallel W1 unit).

## Structural constraints held

Both CLIs are read-only serve-surface consumers (their batteries pin that
they never open the row store / bypass `query.serve_graph`); no
authority/action-plane code imports the shadow models; no germline path
touched; no framework→instance coupling added.
