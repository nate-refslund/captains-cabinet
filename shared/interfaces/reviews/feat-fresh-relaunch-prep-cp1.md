# Checkpoint review — feat/fresh-relaunch-prep, cp1

**Scope:** the two build deliverables added on top of the already-merged
`feat/dev-runtime-split` work and the already-written seed manifest
(`docs/plans/fresh-instance-relaunch-manifest-2026-07-15.md`): `cabinet/
scripts/relaunch-seed.sh` (new script) and `docs/runbooks/fresh-instance-
relaunch.md` (new runbook). Staged diff: 829 changed lines (2 new files).
Triggers FW-019's checkpoint-review gate on line count alone; this is
that review.

**Reviewer:** self-review (same session that authored both files) — the
runbook is designed-not-executed (nothing in it was run against the live
tree or fleet), and the script's every code path WAS actually exercised
against a synthetic fixture (never the live tree), not just eyeballed —
see "Verification performed" below. This is a genuine critical pass: four
real issues were found and fixed before this commit, listed below with
what would have gone wrong had they shipped as first drafted.

## What was checked

1. **Every technical claim was verified against the actual scripts in this
   worktree**, not assumed from memory — `runtime-provision.sh` (its
   `link_instance_data()` leaf lists and the `shared/shared/interfaces`
   wildcard block specifically), `cabinet-deploy.sh`, `hatch.sh` (the
   `--defaults` auto-adopt behavior and why `--clean-room` cannot be used
   here), `kill-switch.sh`, `germline-lock.sh`, `cabinet-doctor.sh`, and
   `instance/flavor-a/README.md` were all read in full or in the relevant
   part before either document asserted anything about their behavior.
2. **Real ground-truth check of the manifest's KEEP list against
   `git ls-files`/`.gitignore`**, not trusted at face value — this
   surfaced that several manifest KEEP entries (`instance/flavor-a/**`,
   most of `instance/fidelity/regression_corpus/`, the ~20 tracked
   `instance/config/*.yml` files) are git-TRACKED and need **zero** seed
   action (they ship with any checkout automatically), while only a
   specific subset (`cabinet/.env`, `instance/config/{extensions.yml,
   extra-mcps.json}`, `instance/memory/tier2/<officer>/*.md` top-level,
   the regression corpus's live-uncommitted delta, and exactly two
   `shared/interfaces/product-specs/*.md` files) are genuinely gitignored
   real data that needed copying. The script implements only the latter
   set; the former is documented as "no action needed" rather than
   silently omitted.
3. **No secret VALUES appear anywhere in either file** — `cabinet/.env`
   values are never echoed by the script (verified empirically, see
   below), and neither document quotes a real secret.
4. **Full `shellcheck` + `bash -n` pass**, not just eyeballed.
5. **`cabinet/scripts/docs-track-code-sweep.sh` and `cabinet/scripts/
   check-layer-separation.sh`** both run against the staged diff — GREEN,
   zero findings, zero new layer-separation violations.

## Verification performed (not just claimed)

Built a synthetic fixture tree under this session's scratchpad (old-root +
a fake `$HOME` including a fake `Library/Application Support/cabinet/`) —
**never** the real `/Users/nate/captains-cabinet` — and ran the actual
script against it:

- `--dry-run` prints the exact plan and creates **zero** filesystem
  footprint (verified: the destination path did not exist before or after).
- A real run correctly redacted only the configured token line (chat id
  and every other secret byte-for-byte unchanged), wrote `shared/
  cabinet.env` at mode 600, seeded exactly the KEEP allowlist (officer
  top-level `*.md` only — `reflections/`, `evolution-proposals/`, and
  `.session-state.json` all confirmed absent from the seed), seeded only
  the two named `product-specs` files (a third, out-of-list fixture file
  was confirmed excluded), and produced a full, unfiltered archive
  (confirmed via `tar -tzf`: the archive contains the DROP items too —
  `.session-state.json`, `reflections/`, `evolution-proposals/` — by
  design, since it is the unfiltered rollback safety net, not the seed).
- Re-running after mutating the fixture (removing one officer note,
  adding another, changing a product-spec's content) converged correctly
  — the removed file disappeared from the seed, the new one appeared,
  confirming the idempotency claim empirically rather than by inspection
  only.
- Grepped the full captured stdout/stderr of every run for the fixture's
  fake secret strings — none found.
- Confirmed containment refusal empirically, twice: pointing
  `--runtime-root` at a path nested under the REAL live tree
  (`/Users/nate/captains-cabinet/...`) refused with exit 64 and created
  nothing on disk (checked directly); pointing it at a path nested under
  `--old-root` itself refused the same way.
- Confirmed the remaining exit-code paths: malformed
  `--telegram-token-var` → 64 before any write; nonexistent `--old-root` →
  1; unknown flag → 64; `--help` → 0 — matching the documented contract.

## Findings (fixed before this commit)

1. **[real bug, would have silently written to the wrong path]
   `seed_config_leaf`'s combined `local rel="$1" src="$OLD_ROOT/$rel"
   dst="$RUNTIME_ROOT/shared/$rel"` referenced `$rel` before it took
   effect in the same `local` statement.** `shellcheck` flagged this
   (SC2318); reproduced it directly in a throwaway bash function
   (`src`/`dst` came out as `X/` and `Y/`, `$rel` empty) before trusting
   the warning. Left as originally drafted, `instance/config/
   extensions.yml` and `extra-mcps.json` would have both resolved to the
   SAME wrong path (old-root's/runtime-root's bare `shared/` directory,
   missing the actual relative path) — the second call would have
   silently overwritten whatever the first one wrote, and neither file
   would have landed at its real intended location. Fixed: split into two
   `local` statements (shellcheck clean afterward; empirically re-verified
   both files land at their correct distinct paths).
2. **[real, would have violated `--dry-run`'s own contract] the script
   unconditionally `mkdir -p`'d the runtime root before computing its
   absolute path, even under `--dry-run`.** "Print the plan, write
   nothing" is the documented contract; an empty directory is still a
   write. Fixed: the `mkdir -p` is now skipped under `--dry-run` (the
   `abs_path` helper's own not-yet-existing-leaf fallback already handles
   the common case correctly without it — verified: `$HOME`-rooted default
   paths are already absolute, so the fallback returns them unchanged).
   Re-verified empirically: a fresh `--dry-run` against a path that did
   not exist before the call left it still absent afterward.
3. **[design issue, not a crash, but a real doctrine violation] the first
   draft hardcoded the 9 officer bucket names, including two product
   names (`polads-ceo`, `stephie-ceo`), directly in this script.**
   `cabinet/scripts/` is framework layer under this repo's own product/
   captain-agnostic-foundation rule (repo `CLAUDE.md`: "framework/,
   cabinet/ must NEVER hardcode a specific product or person"). Beyond the
   doctrine violation, a fixed list is also simply less correct — it
   would silently miss any officer bucket the manifest's author didn't
   anticipate, and silently no-op (with 7 printed "NOTE — not present"
   lines) for buckets that don't exist on a given old-root. Fixed:
   officer buckets are now discovered by listing `instance/memory/tier2/
   */` on old-root and iterating whatever is actually there — verified
   empirically to produce the identical seed result on the test fixture
   (which only has `cos` and `polads-ceo` populated) with less noise.
   `check-layer-separation.sh` re-run clean after the fix (0 new
   violations either way, but the fix removes a latent one).
4. **[real, narrow secrets-handling gap] the redacted `cabinet.env` was
   written via `sed ... > "$dst"` followed by a separate `chmod 600
   "$dst"`.** That leaves a window, however brief, where the file exists
   at the process's default umask (commonly world/group-readable) before
   being locked down — the exact class of issue Corridor's own plan
   analysis flagged for this build (no secret should be creatable at a
   looser mode than intended, even momentarily). Fixed: the write now
   happens inside a `(umask 077; ...)` subshell, so the file is created
   at mode 600 from its very first byte, matching the sibling cutover
   runbook's own `install -m 600` discipline for the same file; the
   trailing `chmod 600` is kept as a defensive backstop, not the sole
   protection.

## Flagged, not silently resolved (open items for the Captain / a follow-up pass)

These are real discrepancies or gaps found while building, surfaced here
rather than papered over — none of them block this commit, but none of
them were invented answers either:

1. **The dispatching task's literal instruction named a placeholder
   `TELEGRAM_BOT_TOKEN=__ROTATE_ME__`, but this repo's actual `cabinet/
   .env` schema has no such variable** — it has one token per officer
   (`TELEGRAM_COS_TOKEN`, `TELEGRAM_CTO_TOKEN`, ...). Fabricating a
   literal `TELEGRAM_BOT_TOKEN` line would have both left the real,
   sensitive token untouched AND added a dead unused variable — the
   opposite of the ruling's intent. Implemented instead as a
   `--telegram-token-var` flag defaulting to `TELEGRAM_COS_TOKEN` (the
   Chair/`cos-inbound` officer's token, matching "the Chair" framing
   elsewhere in the ruling and doctrine) — override the flag if a
   different token is actually the one meant.
2. **The dispatching task's paraphrase of the runtime layout
   (`~/cabinet-runtime/{src,releases,current,data}`) does not match the
   actual, already-built `runtime-provision.sh` layout
   (`~/.cabinet/runtime/{repo.git,releases,shared,current,previous}`).**
   Built against the real script's actual layout, per this repo's own
   "if those scripts exist, use them, their header is authoritative"
   rule — noting the mismatch rather than silently reconciling it one way
   or the other.
3. **`runtime-provision.sh`'s own leaf-symlink list does not currently
   reference `instance/fidelity/` at all.** The regression corpus is
   mostly git-tracked already (ships automatically), but any locally
   uncommitted growth on the live tree will not reach a provisioned
   release automatically even though `relaunch-seed.sh` captures it into
   `shared/`. Named in both the script's header and the runbook as a
   follow-up (commit the corpus growth before cutover, reconcile by hand,
   or extend that script's leaf list) — not fixed here, since
   `runtime-provision.sh` belongs to the separately-already-reviewed
   `feat/dev-runtime-split` branch and this task's scope is additive, not
   a revision of that file.
4. **Three leaf paths appear in `runtime-provision.sh`'s own
   `INSTANCE_PERSISTENT_FILES`/wildcard mechanism but are named in
   neither KEEP nor DROP by the 2026-07-15 ruling or the manifest:**
   `.claude/settings.local.json`, `shared/interfaces/envelope-
   violations.jsonl`, `shared/interfaces/needs-ledger.jsonl`. Treated as
   DROP-by-caution here (same shape as their named siblings) and not
   seeded — flagged for the Captain to confirm, the same way the manifest
   itself flags its own unnamed grey-area items.
