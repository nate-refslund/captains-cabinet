# Checkpoint review — feat/dev-runtime-split, cp1

**Scope:** Lane C only — one new file, `docs/runbooks/dev-runtime-split-
cutover.md` (562 lines, docs-only, no application code). Triggers FW-019's
checkpoint-review gate on line count alone; this is that review.

**Reviewer:** self-review (same session that authored the doc), because the
change is documentation with zero runtime/execution surface (nothing in it
was run — the runbook is designed-not-executed by the task's own mandate).
The review below is a genuine critical pass, not a rubber stamp: three real
issues were found and fixed before this commit, listed below with what
would have gone wrong if they'd shipped as originally drafted.

## What was checked

1. **Every technical claim was verified against the actual scripts in this
   worktree**, not assumed from memory — `deploy-mac.sh`, `start-officer-
   mac.sh`, `cabinet-doctor.sh`, `hatch.sh`, `generate-plists.py`,
   `germline-lock.sh`, `reload-officer-mac.sh`, `restart-all-officers-
   oneshot.sh` were all read in full or in relevant part before the runbook
   asserted anything about their behavior.
2. **No secrets appear anywhere** — `cabinet/.env` values are never quoted;
   only field *names* are referenced, sourced from `cabinet/.env.example`
   (Corridor's plan-analysis guardrail for this change named exactly this
   requirement).
3. **Every `sudo` in the doc is tagged as the Captain's to type**, per the
   standing "attempt `sudo -n`, else a named handback" rule — the runbook
   never assumes the assistant can silently unlock/lock germline.
4. **All 14 bash code blocks were extracted and syntax-checked with
   `bash -n`** (concatenated) — genuinely run, not just eyeballed.

## Findings (fixed before this commit)

1. **[was going to be a real functional gap] `cos-inbound` poller ignored.**
   The first draft's Step 3 only re-ran `deploy-mac.sh --officer all`,
   assuming that covered "the fleet." Reading `com.cabinet.officer.cos-
   inbound.plist` directly showed its `ProgramArguments` has
   `/Users/nate/captains-cabinet` **hardcoded in the checked-in XML** — it
   is not template-rendered, so `deploy-mac.sh` never touches it. Left
   as-drafted, a cutover would have looked complete (officers repointed,
   doctor green) while the Chair's Telegram *receive* path kept polling
   `getUpdates` from the old dev tree — the kind of gap that only surfaces
   later as "why isn't the Chair responding to DMs." Fixed: added Step 3c
   (sed-based path substitution + reinstall) and a general Step 3d sweep
   (`grep` every installed plist for the old path) so the class of gap is
   caught even if another one like it exists that this review didn't name
   individually.
2. **[real, would have silently reinstalled stale definitions] the ~23
   non-template `cabinet/launchd/*.plist` files.** Grepping
   `cabinet/launchd/*.plist` for the live path turned up two dozen files
   (`com.cabinet.dashboard.plist`, `com.cabinet.backup.plist`, the
   `probe-*` family, etc.) that also carry the hardcoded live path. Reading
   `generate-plists.py`'s own docstring resolved why: these are stale,
   previously-committed *output* of that script (its real, current output
   is the gitignored `cabinet/launchd/generated/`), accidentally `git
   add`ed at some point in the past. A draft that said "cp the plist that
   matches the daemon's name" would have installed **stale service
   definitions** system-wide. Fixed: §2 now names this as a fourth,
   do-not-use category, and Step 3b regenerates via `generate-plists.py`
   into `generated/` instead of touching the checked-in files.
3. **[correctness/robustness fix] `generate-plists.py` env-var and
   git-tree assumptions.** `generate-plists.py:58` reads only
   `CABINET_ROOT` (never `CABINET_SOURCE_REPO`) and otherwise falls back to
   `git rev-parse --show-toplevel` from the script's own directory. The
   first draft of Step 1 provisioned releases via `git archive | tar -x`
   (mirroring `hatch.sh`'s clean-room export) — a deliberately `.git`-less
   tree, which would make that fallback hard-fail. Fixed: switched
   provisioning to `git clone` from a local mirror (hardlinked, no extra
   network round-trip, and every release keeps a real `.git`), and every
   script invocation in the doc now sets `CABINET_ROOT` explicitly
   alongside `CABINET_SOURCE_REPO` rather than relying on either script's
   fallback chain.
4. **[doc-quality, would have broken a literal copy-paste] angle-bracket
   placeholders inside bash blocks.** Three code blocks used
   `<the one from Step 1>`-style prose placeholders directly in shell
   assignments (`RELEASE=~/.cabinet/runtime/releases/<...>`) — harmless to
   a human reading it as "fill this in," but a literal copy-paste hits
   bash's `<`/`>` redirection parsing and fails with a confusing syntax
   error, and it also broke this review's own `bash -n` mechanical check.
   Fixed: replaced with a `$RELEASE` variable thread (set once in Step 1,
   with a one-line re-derivation comment — `ls -td .../releases/*/ | head
   -1` — for a reader starting a fresh shell instead of running the whole
   sequence in one).

## Not fixed / accepted as-is (named, not hidden)

- **Whether the ~2-dozen manifest daemons/watchdogs are even all live on
  the current deployment** was not independently verified against a real
  running fleet (this session never touched the live tree's runtime state,
  by mandate) — Step 3b regenerates *all* of `cabinet/services.yml`'s
  non-officer rows unconditionally, which is safe (idempotent bootout+
  bootstrap) even for rows that happen to be disabled or not currently
  installed.
- **The recurring germline-relock cost on every future `cabinet-deploy.sh`
  release** (each fresh checkout needs its own `schg` lock ceremony,
  because `instance/` is shared/symlinked but the code-side germline files
  are not) is flagged explicitly in the doc as a known gap for whoever
  builds `cabinet-deploy.sh` — deliberately not solved here, since solving
  it is that script's design problem, not this runbook's.
- **This review, and the runbook itself, could not be executed against a
  real fleet** — by the task's own mandate ("Do NOT execute any of it").
  Everything above is static verification (reading the actual scripts,
  grepping the actual checked-in files, syntax-checking the actual bash
  blocks) — not a live dry run. The doc says this about itself in its own
  status line; this review doesn't overclaim beyond that either.

## Verdict

APPROVE for commit. Docs-only change; the findings above were fixed in the
same pass, before this review was written, so the file this review
accompanies already reflects the fixes.
