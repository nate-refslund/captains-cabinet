# Checkpoint review — feat/fresh-relaunch-prep, cp2

**Scope:** independent re-verification pass on top of cp1's already-fixed
build (`cabinet/scripts/relaunch-seed.sh`, `docs/runbooks/fresh-instance-
relaunch.md`, `docs/plans/fresh-instance-relaunch-manifest-2026-07-15.md`),
dispatched as a fresh "prep the relaunch" task that turned out to already
be substantially complete. This checkpoint does not re-litigate cp1's
findings — it independently reproduces cp1's claims rather than trusting
them, catches the branch up to a `origin/master` that had moved on since,
and fixes one real staleness bug found along the way.

## 0. Re-dispatch discovery (candor, evidence-first)

The dispatching task's instructions ("work ONLY in worktree
`/Users/nate/cabinet-worktrees/fresh-relaunch-prep`... create it... stage
on branch `feat/fresh-instance-relaunch`") describe a fresh build. Ground
truth, checked before touching anything: the worktree already existed
(checked out at `07aba7b1`, branch `feat/fresh-relaunch-prep`, already
pushed to `origin/feat/fresh-relaunch-prep`), matching `RESUME-BOARD.md`
row `fresh-instance-relaunch-prep` exactly, including a same-day
(2026-07-16) prior fix pass. The Captain-ruling text in this task's brief
is materially identical to the ruling text already implemented by that
prior work. Conclusion: this dispatch re-describes already-substantially-
complete work, most likely a re-send rather than a deliberate second pass.
Continuing on the existing branch (not creating a same-content,
differently-named duplicate branch) and reporting the discrepancy plainly,
per this repo's own candor-law doctrine, rather than silently complying
with a branch name that would fragment identical history.

## 1. Master catch-up (real gap, fixed before any other work)

Before this checkpoint, `feat/fresh-relaunch-prep`'s last merge of
`origin/master` was at `405abed3`. Current `origin/master` (`9018cac3`,
verified GREEN per-job via `gh run view --json jobs`: null-hatch,
framework-tests, clean-room-foundation, gitleaks, zizmor, clean-room-
source, ci — all `success`) had moved 9 commits further: PR #143
(lowercase proxy env), #144/#145 (redis-backup-v3 + hotfix), #146
(restore-drill-discovery-hotfix), plus an authority-tests clock freeze.
`git diff --stat origin/master..HEAD` before the merge showed large
deletions of files those PRs added (`redis-state.sh`, `redis_state.py`,
`test_redis_state*.py`, `backup.sh`, `restore-drill.sh`, ...) — drift, not
anything this branch's own work touched or intended to remove. Merged
`origin/master` in (clean, zero conflicts — the apparent path overlap
turned out to be files both branches had already picked up via an earlier
common merge, not competing edits). Post-merge `git diff --stat
origin/master..HEAD` now shows exactly this branch's own 11 files, nothing
else. `bash -n` + `docs-track-code-sweep.sh` + `check-layer-separation.sh`
all re-run clean after the merge.

## 2. Independent reproduction of cp1's safety claims (not re-trusted)

Built a synthetic fixture (old-root + fake `$HOME`, under this session's
scratchpad — never the live tree) and ran the real, unmodified
`relaunch-seed.sh` against it independently:

- `--dry-run`: confirmed zero filesystem footprint (checked before/after),
  correct printed plan, correctly excludes an out-of-allowlist product-spec
  fixture file from the plan.
- Real run: `TELEGRAM_COS_TOKEN` rotated to `__ROTATE_ME__`, every other
  line (`HQ_CHAT_ID`, `OTHER_SECRET`) byte-for-byte unchanged;
  `shared/cabinet.env` written at mode 600; officer memory seed contains
  ONLY top-level `*.md` (confirmed `reflections/retro.md` and
  `.session-state.json` both absent from the seed, present only in the
  archive); regression corpus fully copied; product-specs allowlist
  correctly admits only the 2 named files, excludes the 3rd fixture file;
  archive (`tar -tzf`) contains the DROP items too (by design — unfiltered
  safety net) with `Application Support/cabinet/` and `cabinet/.env`
  correctly under separate prefixes (review finding #2 still holds); zero
  occurrences of the fixture's fake secret value in captured stdout/stderr.
- Containment guard, both directions, reproduced empirically: `--runtime-
  root` nested under `--old-root` refuses (exit 64, nothing created);
  `--old-root` nested under `--runtime-root/shared` (the exact review
  finding #3 fixture shape) also refuses (exit 64), with the original
  fixture's `.session-state.json` confirmed still intact afterward — no
  data loss.

All of cp1's safety claims held up under independent reproduction.
`shellcheck` + `bash -n` re-run clean on all three core scripts
(`relaunch-seed.sh`, `runtime-provision.sh`, `cabinet-deploy.sh`).

## 3. Finding fixed this checkpoint

**[real, doc-only, not a script bug] Both the runbook and the manifest
asserted the shared Redis kill switch's state (`cabinet:killswitch`) as a
current fact ("It's currently ON", "is ACTIVE... right now") rather than
as a dated, re-checkable observation.** A fresh check this session
(`bash cabinet/scripts/kill-switch.sh status`, the canonical script, not a
guessed raw-redis key shape) shows **INACTIVE** — a real change since the
2026-07-15 observation both docs cited, presumed Captain-side (neither
build session touches it either direction). This is the exact class of
mistake this repo's own doctrine warns about elsewhere ("boundary state
changes under you across sessions" — germline lock state, same idea).
Left as originally worded, a reader executing this runbook on an actual
future relaunch day could be misled into skipping a fresh check because
the doc already told them what the switch's state "is." Fixed: both docs
now instruct a fresh `status` check at execution time and present the two
dated observations (2026-07-15 ACTIVE, 2026-07-16 INACTIVE) as history,
not as the state to expect going forward; also corrected a stale internal
cross-reference (the runbook's Step 1 pointed at "§6" for the kill-switch
note, which actually lives in the manifest's §5). `docs-track-code-
sweep.sh` and `check-layer-separation.sh` re-run clean after this edit.

## 4. Not re-opened (deliberately out of scope, same reasoning as cp1)

- `runtime-provision.sh`'s leaf-symlink list still doesn't reference
  `instance/fidelity/` — cp1's own header/runbook already name this gap
  and the reason it's not fixed here (that script belongs to the
  separately-already-reviewed `feat/dev-runtime-split` branch; this task's
  scope is additive). Independently confirmed the gap is still real and
  still accurately described; not touched.
- The 3 leaf paths cp1 flagged as unclassified-by-the-ruling
  (`.claude/settings.local.json`, `envelope-violations.jsonl`, `needs-
  ledger.jsonl`) and the manifest's own grey-area items (§3) remain
  flagged for the Captain, not silently resolved either way.

## 5. Net verdict

Ready to stage as-is. No script logic changed this checkpoint (only two
doc files edited, prose-only, both gates re-verified green); the master
catch-up merge and the kill-switch doc fix are the only substantive
changes. Everything cp1 built and reviewed remains correct under
independent re-verification. Branch not pushed to `master`; pushed to
`origin/feat/fresh-relaunch-prep` (same branch cp1 already lives on) per
this repo's existing practice of pushing feature branches for visibility
while staying off master until Captain-gated cutover.
