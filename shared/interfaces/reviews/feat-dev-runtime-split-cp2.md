# Checkpoint review — feat/dev-runtime-split, cp2

**Scope:** `docs/runbooks/dev-runtime-split-cutover.md` only, second pass.
Between cp1 and this review, `cabinet/scripts/runtime-provision.sh` (Lane A)
and `cabinet/scripts/cabinet-deploy.sh` (Lane B) both landed in this shared
worktree. The runbook was reconciled against both real scripts (its own §2
promise: "their own `--help`/header comment is authoritative over this
document if the two ever disagree") — this review verifies that
reconciliation is actually accurate, not just present.

## What was checked

1. **Every CLI surface the doc now claims for `runtime-provision.sh`**
   (`init --remote [--seed-fresh-instance]`, `provision <ref>` →
   `PROVISIONED_SHA=`/`PROVISIONED_SLOT=`, `promote <sha>`, `rollback`,
   `current`, `list`, `prune [--keep N]`) was checked against the script's
   own `usage()` (lines 84-99) and each `cmd_*` function body (lines
   155-392) — verb names, argument order, and stdout contract all match.
2. **Every CLI surface the doc claims for `cabinet-deploy.sh`**
   (`deploy --runtime-root [--ref] [--dry-run]`, `status --runtime-root`,
   `rollback --runtime-root`) was checked against its own header comment
   (lines 65-68, 93-99) and argument parser (lines 117-125) — matches,
   including the `CABINET_DEPLOY_RUNTIME_ROOT` env-var alternative the doc
   does not currently mention (minor omission, not an inaccuracy — noted
   below, not blocking).
3. **The germline-relock design.** `runtime-provision.sh`'s own header
   (lines 42-49) and `cabinet-deploy.sh`'s own header (lines 24-41)
   independently describe the exact health-gate/WARN-vs-DEAD/post-promote-
   status design the runbook's "Ongoing-update path" callout summarizes —
   cross-checked line by line, no drift.

## Finding (fixed before this commit)

**[real bootstrapping gap, found this pass] provisioning a pre-merge ref
would silently break Step 3.** `runtime-provision.sh promote` is invoked as
`"$RELEASE/cabinet/scripts/runtime-provision.sh"` — the copy *inside the
just-provisioned release*, deliberately (so `promote` always runs the
version of itself that shipped with that commit, not a possibly-newer live
copy). But Step 1 provisions `origin/master`'s tip by default. If
`feat/dev-runtime-split` (which is what actually adds
`runtime-provision.sh`/`cabinet-deploy.sh`/this runbook) has not yet been
merged into whatever `origin/master` resolves to at provision time, the
release built in Step 1 would not contain either script — Step 3 would
fail on a plain file-not-found with no explanation in the doc as written.
Fixed: added an explicit precondition (§3) naming the dependency and its
two resolutions (merge first, or provision the exact sha that has these
scripts rather than a bare branch ref that might predate them).

## Not fixed / accepted as-is (named, not hidden)

- **`CABINET_DEPLOY_RUNTIME_ROOT`** (the env-var alternative to
  `--runtime-root` that `cabinet-deploy.sh` itself supports per its own
  usage line) is not mentioned in the runbook's §5 examples. Not wrong —
  `--runtime-root` is the more explicit, copy-paste-safe form for a runbook
  — just incomplete; a reader who greps the script's own `--help` will find
  it. Left out deliberately rather than padding §5 with every equivalent
  spelling.
- **No live execution of either script happened in this review** — by the
  task's mandate, nothing in this branch touches the live tree or live
  fleet. Verification here is static: reading the actual shipped source and
  cross-checking every claim against it, plus the mechanical `bash -n`
  syntax pass over all 15 bash blocks in the current doc (clean). The
  sandbox dry-run proof against the real scripts is a separate, already
  in-flight task (#24) and is not duplicated here.

## Verdict

APPROVE for commit. The one real gap found this pass (pre-merge provisioning
bootstrap hazard) is fixed in the file this review accompanies.
