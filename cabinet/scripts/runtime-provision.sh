#!/bin/bash
# runtime-provision.sh — blue/green runtime-slot primitives for the dev/runtime
# split (Captain-approved 2026-07-15: the fleet should run off a clean pinned
# checkout, never the live dev tree — see docs/runbooks/dev-runtime-split-
# cutover.md for the one-time migration this enables, and cabinet-deploy.sh
# for the ongoing `cabinet deploy` command built on these primitives).
#
# THIS SCRIPT NEVER TOUCHES $HOME/captains-cabinet or any live officer.
# It only manages a separate <runtime_root> directory tree (recommended
# default ~/.cabinet/runtime — see cabinet-deploy.sh) that launchd gets
# repointed at ONLY by the cutover runbook, a deliberate later step.
#
# LAYOUT (<runtime_root>/):
#   repo.git/            bare MIRROR clone of the cabinet remote (`fetch`
#                         updates it; every release worktree shares its
#                         object store — cheap, and the same worktree
#                         primitive this codebase already leans on for its
#                         30+ parallel dev worktrees).
#   releases/<sha>/       one `git worktree add --detach` per provisioned
#                         commit — a full, independent checkout pinned at
#                         that exact sha. Disposable; never developed in.
#   shared/               persistent, NEVER per-release, survives every
#                         future deploy — holds ONLY the individually-
#                         gitignored instance-data leaves + secrets (see
#                         "WHY LEAF-LEVEL, NOT A WHOLE instance/ SYMLINK"
#                         below), e.g. shared/instance/config/roster.yml,
#                         shared/instance/memory/, shared/cabinet.env.
#   current                symlink -> releases/<sha> currently live. The
#                         ONLY path launchd/officers should ever be pointed
#                         at (stable across every future deploy).
#   previous               symlink -> the release 'current' pointed at
#                         immediately before the last promote/rollback
#                         (the rollback target).
#   .cabinet-deploy.log    append-only audit trail (promote/rollback lines;
#                         cabinet-deploy.sh appends its own deploy/restart
#                         lines here too).
#
# WHY instance DATA IS SHARED, NOT COPIED (read before changing this):
# instance/ mixes git-TRACKED judged-config templates (platform.yml,
# contexts/, posture-presets/, ...) with gitignored REAL deployment data
# (roster.yml, posture.yml, memory/, state/, cache/, secrets). A blue/green
# release is a FRESH worktree, so copying instance/ into each new slot would
# either (a) go stale the instant an officer writes new state after
# promotion — a ROLLBACK would then silently lose everything written since
# promotion — or (b) need a hand-rolled tracked-vs-untracked path list that
# rots the moment .gitignore's instance/ entries change. Symlinking the
# gitignored leaves into shared/ instead means every release (old and new,
# before AND after a rollback) reads and writes the exact same physical
# files — zero divergence, zero data loss on rollback.
#
# WHY LEAF-LEVEL, NOT A WHOLE instance/ SYMLINK (fixed 2026-07-15 — an
# earlier version of this file symlinked the entire instance/ directory in
# one shot; that is a real bug, not a style choice): instance/config/ alone
# ships ~50 git-TRACKED doctrine/example/schema files (adapters.yml,
# comms-surface.yml, every contexts/*.yml, ...) that a future commit
# legitimately updates, sitting right next to ~10 gitignored deployment-
# local files (roster.yml, autonomy.yml, product.yml, ...). Symlinking the
# WHOLE instance/ directory to shared/instance freezes the tracked files at
# whatever the FIRST release happened to contain — every subsequent
# `cabinet-deploy.sh deploy` would silently stop updating instance/config's
# tracked defaults, defeating the entire point of pinning-and-updating
# commits. So `link_instance_data` (below) symlinks only the individually-
# gitignored leaves (files, linked only once a shared/ copy already exists —
# never fabricated from nothing) plus the handful of directories that are
# bulk-gitignored (state/, cache/, archive/, loop-prompts/, secrets/, the
# fresh-relaunch persistence additions evidence/ + onboarding/{formation,v2,access-records,
# purge-receipts}, and roles/{active,archive,hats}) — verified against
# .gitignore + `git ls-files` at fix time, not guessed. NOT "ENTIRELY"
# gitignored: roles/{active,archive,hats}/ each ship a tracked `.gitkeep`
# (negated in .gitignore) — the same seeded-class shape as instance/memory —
# so replacing such a dir with a shared/ symlink shows an accepted deleted-
# `.gitkeep` status line in the disposable release worktree, while the
# directory's existence is preserved by the shared/ mkdir regardless.
# instance/memory/ is the one leaf that additionally must SEED its tracked
# tier2/<officer>/{,reflections/}.gitkeep skeleton into shared/ from the
# release's own tree, then is symlinked whole like any other bulk-gitignored
# directory. KEEP THIS LIST IN
# LOCKSTEP WITH .gitignore — same discipline as germline-lock.sh's own
# "keep in lockstep with pre-tool-use.sh §5" rule.
#
# EVERY class ADOPTS BEFORE IT LINKS (2026-07-25 — read the ADOPTION INVARIANT
# above link_instance_data before changing any loop below). Listing a path is
# not the same as carrying it: the state a list entry names lives in the LIVE
# RELEASE, not in shared/, until something copies it there. A loop that only
# mkdir's an empty shared/ dir and symlinks to it discards exactly the data the
# entry was added to protect — and, when the slot being provisioned IS the live
# release, its `rm -rf` destroys that data outright.
#
# A second, load-bearing side effect of sharing (not copying) the
# gitignored leaves: schg (system-immutable, see germline-lock.sh) is an
# INODE flag, not a path flag — locking shared/instance/config/{posture,
# trust-ladder,standing-grants}.yml and act-first-surfaces.yml ONCE keeps
# them locked through every future release automatically, with no per-
# deploy re-lock needed for that half of the germline set (the framework/+
# cabinet/-side germline CODE, which DOES get a fresh inode per release via
# the worktree checkout, still needs a per-slot relock — see
# cabinet-deploy.sh's health gate and its printed post-promote reminder).
#
# germline-lock.sh's OWN chflags calls require root (verified: `need_root`
# in that script — schg can only be set/cleared by root) and officers carry
# no passwordless sudo — so THIS script never attempts to chflags anything.
# A freshly-provisioned release is legitimately unarmed until an explicit,
# Captain-available relock; that gap is inert until the slot is promoted.
#
# Usage:
#   runtime-provision.sh init      <runtime_root> --remote <git-url> [--seed-fresh-instance]
#   runtime-provision.sh fetch     <runtime_root>
#   runtime-provision.sh resolve   <runtime_root> <ref>           # -> prints full sha
#   runtime-provision.sh provision <runtime_root> <ref>           # -> PROVISIONED_SHA=/PROVISIONED_SLOT=
#   runtime-provision.sh promote   <runtime_root> <sha>
#   runtime-provision.sh rollback  <runtime_root>                 # current <-> previous
#   runtime-provision.sh current   <runtime_root>                 # -> prints sha, or NONE
#   runtime-provision.sh list      <runtime_root>
#   runtime-provision.sh prune     <runtime_root> [--keep N]      # default 5; current+previous always kept
#
# --seed-fresh-instance (init only) is a SANDBOX/DEV convenience: it
# provisions one throwaway release at the mirror's HEAD purely to run ITS
# OWN generate-instance.py --defaults (a fresh preset instance, same as any
# first hatch — no captain data anywhere in this path), harvests the result
# into shared/instance as the seed, then discards the throwaway release. It
# is NEVER the real cutover path — the real migration MOVES the live
# deployment's actual instance/ data; see the cutover runbook.
#
# Exit codes: 0 success · 1 operational failure · 64 usage error.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: runtime-provision.sh <command> [args]
Commands:
  init      <runtime_root> --remote <git-url> [--seed-fresh-instance]
  fetch     <runtime_root>
  resolve   <runtime_root> <ref>
  provision <runtime_root> <ref>
  promote   <runtime_root> <sha>
  rollback  <runtime_root>
  current   <runtime_root>
  list      <runtime_root>
  prune     <runtime_root> [--keep N]
EOF
}

# ---- path helpers -------------------------------------------------------------
# abs_path <path> — resolve to an absolute path without relying on GNU
# realpath (not guaranteed present on macOS; mirrors hatch.sh's own
# defensive resolution pattern). Existing dirs/files resolve physically; a
# not-yet-existing leaf resolves its deepest existing ancestor and appends
# the remainder lexically.
abs_path() {
  local p="$1"
  if [ -d "$p" ]; then
    (cd "$p" && pwd)
  elif [ -e "$p" ]; then
    (cd "$(dirname "$p")" && printf '%s/%s' "$(pwd)" "$(basename "$p")")
  else
    local parent
    if parent="$(cd "$(dirname "$p")" 2>/dev/null && pwd)"; then
      printf '%s/%s' "$parent" "$(basename "$p")"
    else
      printf '%s' "$p"
    fi
  fi
}

# require_runtime_root <path> — every command but `init` needs an
# already-provisioned runtime_root; refuse to silently mkdir one.
require_runtime_root() {
  local root="$1"
  [ -d "$root" ] && [ -d "$root/repo.git" ] || {
    echo "runtime-provision.sh: '$root' is not an initialized runtime root (no repo.git/) — run 'init' first." >&2
    exit 1
  }
}

# git_r <runtime_root> <git-args...> — every git call against the bare
# mirror goes through this one helper so the --git-dir wiring lives in
# exactly one place.
git_r() {
  local root="$1"; shift
  git --git-dir="$root/repo.git" "$@"
}

# swap_symlink <target> <link_path> — force-replace link_path with a
# symlink to target.
#
# FIXED 2026-07-15 (was named atomic_symlink and did `ln -s target tmp; mv -f
# tmp link_path` — empirically WRONG on macOS, verified with a throwaway
# two-directory /tmp reproduction before this fix landed): when link_path
# already exists and is itself a symlink pointing at a directory, BSD `mv`'s
# target-directory detection follows the symlink (stat(), not lstat()) and
# moves the source INSIDE the directory link_path points to, instead of
# replacing link_path. Concretely: `current` never actually updated, and a
# stray tmp symlink was littered inside the OLD release directory on every
# single promote/rollback call — the core blue/green swap silently never
# happened while both callers reported success. GNU coreutils' `-T` flag
# fixes this on Linux; BSD/macOS `mv` has no equivalent, so this needed a
# different primitive rather than a different mv flag.
#
# `ln -sfn` does not have that failure mode: `-n` means "treat link_path as
# the file to replace, even if it is itself a symlink to a directory" —
# exactly this case — and is the same idiom this repo already uses
# elsewhere for symlink swaps (create-project.sh, start-officer.sh). It is
# NOT a single-syscall atomic rename on BSD (unlink, then re-link — a brief
# gap where link_path resolves to neither the old nor new target; GNU's `ln
# -f` does the rename-based swap internally and has no such gap). Accepted
# as a deliberate, low-stakes tradeoff: promote/rollback are explicit,
# infrequent, operator/deploy-script-invoked actions, not a race-prone hot
# path, and this is the already-proven pattern in this codebase — not a new
# one. Renamed from atomic_symlink to swap_symlink (every call site updated
# below) since "atomic" was never quite true and this fix is the moment to
# stop implying it.
swap_symlink() {
  local target="$1" link_path="$2"
  ln -sfn "$target" "$link_path"
}

# ---- instance-data linking (leaf-level — see file header "WHY LEAF-LEVEL,
# NOT A WHOLE instance/ SYMLINK" for the full rationale/fix history) --------
# Space-separated, not arrays (bash 3.2-safe; none of these paths contain
# spaces). KEEP IN LOCKSTEP WITH .gitignore. The onboarding/{v2,purge-receipts}
# + evidence/ entries are the fresh-relaunch persistence additions (post-cutover
# data-loss fix): whole-dir symlinks so a deploy/rollback never strands a
# lane-CEO's onboarding run or the Captain-owned evidence store on the old
# slot. Deliberately EXCLUDES instance/onboarding/.onboarding-v2.lock — an
# ephemeral run lock that must NOT carry across deploys (it lives in the
# onboarding/ parent, not under the v2/ leaf, so symlinking v2/ cannot drag
# it along).
# The shared/interfaces/{foundry,world} + world-aesthetic corpus entries are the
# state-persistence-preflight additions (2026-07-25): each is gitignored runtime
# state with ZERO tracked content, so a whole-dir symlink shadows nothing.
# foundry/ is the COG-5 sealed append-only trajectory archive whose own contract
# says "rollback = verified RESTORE, never cache-delete"; world/ holds the
# append-only chronicle series that services.yml orders ARCHIVED, never
# truncated. corpus/{positive,negative} are the judge's taste-accumulation
# frames — Captain approve/reject rulings on renders that no longer exist
# anywhere, and _corpus.py integrity-checks every read, so a lost corpus is a
# hard judge failure. They are linked at the SUBDIR level deliberately: the
# corpus root holds a git-TRACKED manifest.json that a whole-dir link would
# shadow (the same "never shadow a tracked file" rule as the wildcard block).
INSTANCE_PERSISTENT_DIRS="instance/roles/active instance/roles/archive instance/roles/hats instance/loop-prompts instance/archive instance/state instance/cache instance/onboarding/formation instance/onboarding/v2 instance/onboarding/purge-receipts instance/onboarding/access-records instance/evidence secrets shared/interfaces/foundry shared/interfaces/world cabinet/scripts/world-aesthetic/corpus/positive cabinet/scripts/world-aesthetic/corpus/negative"
# Gitignored in bulk but ships a tracked tier2/<officer>/{,reflections/}.gitkeep
# skeleton — seeded into shared/ from the release's own tree, then
# symlinked whole like any PERSISTENT_DIRS entry.
#
# The five 2026-07-25 additions are the state-persistence-preflight fix. Each is
# gitignored in bulk but ships a tracked .gitkeep skeleton, so SEEDED (not plain
# DIRS) is the correct home — accumulated data is adopted from the live release
# first, the tracked skeleton then fills any gap, and the dir is symlinked like
# any other. Every one of them was silently discarded on
# EVERY deploy, with no error and a passing health gate:
#   memory/skills/evolved  ratified Captain rules (captain-rules/ratify-rule.sh)
#   memory/tier3           decision log, experience records, research archive
#   memory/logs            the tool-call log
#   cabinet/cache          org-runtime.sqlite3 (append-only DB trigger), the
#                          chained-hash predictions store, COG-2 beliefs, COG-4
#                          scheduler, and the purge undo archive — ORIGINAL
#                          stores despite the directory's name, seeded once at
#                          setup and never re-seeded per deploy
#   cabinet/logs           append-only verdict series cabinet-doctor reads
#                          ACROSS runs (retrieval-eval history, doctor-history,
#                          task-sync drift, hook FP corpus) — losing them makes
#                          the rolling-window health checks unmeasurable
INSTANCE_PERSISTENT_SEEDED_DIRS="instance/memory memory/skills/evolved memory/tier3 memory/logs cabinet/cache cabinet/logs"
# Individual leaves inside an otherwise richly git-tracked directory.
# Symlinked ONLY when a shared/ copy already exists — never fabricated, so
# a from-scratch runtime root leaves the path absent, same as a from-scratch
# checkout (every consumer already has its own not-found guard for that,
# e.g. deploy-mac.sh/cabinet-deploy.sh's roster_officers()). The germline
# posture/trust-ladder/standing-grants leaves + the comms-charter override
# and its amendment/proposal sidecars + the memory-supersession-soak /
# workaround-retire / governance-labels series are
# here (fresh-relaunch persistence, post-cutover data-loss fix) so a deploy
# or rollback never resets earned posture, the Captain's routing charter, or
# those governance ledgers to a fresh checkout's blank state.
# instance/config/act-first-surfaces.yml is DELIBERATELY ABSENT: it is
# git-TRACKED, so linking it would SHADOW the release's own tracked copy —
# the same "never shadow a tracked file" guard the wildcard block below
# already applies to shared/interfaces/deployment-status.md.
# instance/config/captain-availability.yml joins the germline-posture family for
# the same reason (availability dial, Captain ruling 2026-07-26): it is the
# captain's own declared time budget, written from his phone, and a deploy that
# reset it would silently return the org to UNKNOWN — re-widening the pacing cap
# and telling the Captain-Seat reviewer there is no budget to judge cost against.
# instance/config/captain-dates.yml joins on the same rule (dated commitments,
# Captain-Seat finding 1 2026-07-26): the dates HE set, written from his phone. A
# deploy that reset it would drop every open date out of every briefing — which
# IS the failure the store was built to prevent, and it would fail silently
# (an empty list is a legal state, so nothing would look broken).
# The report-only shadow-detector journal is intentionally NOT in this list:
# regenerable detector output that a germline law bars any tracked surface
# from naming (the CI shadow-grep proof enforces it) — so it is never linked.
INSTANCE_PERSISTENT_FILES="instance/config/product.yml instance/config/active-project.txt instance/config/active-preset instance/config/roster.yml instance/config/publish-scan-patterns.local instance/config/extensions.yml instance/config/required-plugins.yml instance/config/extra-mcps.json instance/config/autonomy.yml instance/config/act-first-enabled .claude/settings.local.json shared/interfaces/action-lessons.yml shared/interfaces/falsifier-series.jsonl shared/interfaces/envelope-violations.jsonl shared/interfaces/charter-shadow-series.jsonl shared/interfaces/golden-eval-scalar.jsonl shared/interfaces/memory-supersession-proposals.jsonl shared/interfaces/needs-ledger.jsonl shared/interfaces/prediction-calibration.jsonl shared/interfaces/preference-pairs.jsonl shared/interfaces/world-chronicle.jsonl shared/interfaces/attention-queue.json instance/config/posture.yml instance/config/trust-ladder.yml instance/config/standing-grants.yml instance/config/comms-charter.yml instance/config/comms-charter-amendments.jsonl instance/config/comms-charter-proposals.jsonl instance/config/captain-availability.yml instance/config/captain-dates.yml shared/interfaces/memory-supersession-soak.jsonl shared/interfaces/workaround-retire-proposals.jsonl shared/interfaces/governance-labels.jsonl instance/config/trusted-mcps.json instance/config/war-room-seed.yml .claude/project-config.json bin/cabinet-calread"
# The four trailing entries are the 2026-07-25 state-persistence-preflight fix.
# trusted-mcps.json / war-room-seed.yml / .claude/project-config.json are
# hand-authored local config whose every sibling was already on this list —
# they were the lone omissions, and each was silently reset to absent on every
# deploy. bin/cabinet-calread is here for a different reason: its bytes ARE
# rebuildable from tracked Swift source, but the macOS Full Calendar Access TCC
# grant is keyed to the ad-hoc signature's CDHASH, so ANY rebuild costs a
# one-time Captain re-grant in System Settings. Carrying the built binary
# preserves the CDHASH and therefore the grant. Listed as an individual FILE,
# never a bin/ directory link — see the state-persistence policy's known_gap
# row for why Cabinet Companion.app needs a design call first.

# ---- adoption primitives (2026-07-25 fix; see ADOPTION INVARIANT below) ----
#
# THE BUG THESE EXIST TO KILL. Adding a path to a persistence list did NOT make
# it persist. A directory of runtime state lives in the LIVE RELEASE, never in
# shared/ — so the DIRS loop happily `mkdir -p`'d an EMPTY shared/ dir, symlinked
# the new slot at it, and left the real data behind in the outgoing release for
# `prune` to rm -rf. Worse, when cmd_provision reused the live slot by sha (a
# routine redeploy with no new commits, or a retry after a failed health gate)
# that same loop's `rm -rf "$slot/$rel"` deleted the live data OUTRIGHT.
# Measured end-to-end 2026-07-25: 9 of 13 durable paths lost on a normal deploy
# and 4 destroyed in place on a same-sha redeploy, both at exit 0.
#
# ADOPTION INVARIANT (the property every caller below relies on):
#   before any `rm -rf "$slot/$rel"`, every UNTRACKED file beneath it has been
#   copied into shared/ (or an identically-named file was already there).
# Tracked files are recoverable from git by definition, so once that holds the
# removal provably destroys no unique bytes. This is why _adopt_untracked is
# called on the SLOT as well as on the outgoing release — the slot is the thing
# being deleted, so it is the thing that must be proven safe to delete.

# _adopt_untracked <src_root> <rel> <shared_abs> <label> [name_glob]
#
# Copy every untracked regular file under <src_root>/<rel> into <shared_abs>,
# NEVER overwriting a file already present there (shared/ is the authoritative
# physical store; a release copy never wins over it). No-op when the source is
# absent or is already a symlink — that symlink is the steady state after any
# previous provision, and following it would copy shared/ onto itself.
#
# Only UNTRACKED files are adopted: copying a git-tracked file into shared/ and
# then symlinking the directory would SHADOW the release's own tracked copy with
# a frozen snapshot — the same hazard the wildcard block guards against for
# deployment-status.md.
_adopt_untracked() {
  local src_root="$1" rel="$2" shared_abs="$3" label="$4" glob="${5:-}"
  local src tracked f sub n=0 nl
  src="$src_root/$rel"
  [ -d "$src" ] || return 0
  [ -L "$src" ] && return 0
  nl='
'
  tracked="$nl$(git -C "$src_root" ls-files -- "$rel" 2>/dev/null)$nl"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    sub="${f#"$src/"}"
    case "$tracked" in *"$nl$rel/$sub$nl"*) continue ;; esac
    [ -e "$shared_abs/$sub" ] && continue
    # A FAILED copy must abort the whole provision. Swallowing it (the obvious
    # `cp ... || true` shape) would break the ADOPTION INVARIANT silently and
    # leave the caller free to rm -rf the only remaining copy — the exact class
    # of failure this whole fix exists to end. Fail closed and loudly instead.
    if ! mkdir -p "$shared_abs/$(dirname "$sub")" 2>/dev/null ||
       ! cp -p "$f" "$shared_abs/$sub" 2>/dev/null; then
      echo "runtime-provision.sh: FATAL — could not adopt '$f' into '$shared_abs/$sub'." >&2
      echo "  Aborting: the next step removes the release copy, so continuing would" >&2
      echo "  destroy the only copy of this state. Fix the destination and re-run." >&2
      exit 1
    fi
    n=$((n+1))
  done <<EOF
$(if [ -n "$glob" ]; then find "$src" -type f -name "$glob" 2>/dev/null; else find "$src" -type f 2>/dev/null; fi)
EOF
  [ "$n" -gt 0 ] && echo "runtime-provision.sh: adopted $n file(s) of runtime state from $label into shared/$rel"
  return 0
}

# _seed_tracked <slot> <rel> <shared_abs> — copy this release's TRACKED skeleton
# files under <rel> into shared/, never overwriting. SEEDED class only, and it
# runs AFTER adoption so real accumulated data always beats a `.gitkeep`.
_seed_tracked() {
  local slot="$1" rel="$2" shared_abs="$3" f sub n=0
  [ -d "$slot/$rel" ] || return 0
  [ -L "$slot/$rel" ] && return 0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    sub="${f#"$rel/"}"
    [ -f "$slot/$f" ] || continue
    [ -e "$shared_abs/$sub" ] && continue
    mkdir -p "$shared_abs/$(dirname "$sub")"
    cp -p "$slot/$f" "$shared_abs/$sub" 2>/dev/null && n=$((n+1))
  done <<EOF
$(git -C "$slot" ls-files -- "$rel" 2>/dev/null)
EOF
  [ "$n" -gt 0 ] && echo "runtime-provision.sh: seeded $n tracked skeleton file(s) into shared/$rel"
  return 0
}

# link_instance_data <slot> <root> — the leaf-level linking pass. Called
# unconditionally from cmd_provision (both on a fresh worktree checkout and
# when reusing an already-provisioned slot), so re-running `provision` for
# an existing sha idempotently refreshes newly-added shared/ data too.
link_instance_data() {
  local slot="$1" root="$2" rel shared_abs rel_dir f

  # Resolve the live (outgoing) release once — every adoption pass below reads
  # it. This is the release that holds the accumulated state on the very first
  # provision after a path joins one of the lists.
  local cur_rel=""
  [ -L "$root/current" ] && cur_rel="$(cd "$root/current" 2>/dev/null && pwd)"

  for rel in $INSTANCE_PERSISTENT_DIRS; do
    shared_abs="$root/shared/$rel"
    [ -n "$cur_rel" ] && _adopt_untracked "$cur_rel" "$rel" "$shared_abs" "the live release"
    [ "$slot" != "$cur_rel" ] && _adopt_untracked "$slot" "$rel" "$shared_abs" "this release"
    mkdir -p "$shared_abs"
    rel_dir="$(dirname "$slot/$rel")"
    mkdir -p "$rel_dir"
    rm -rf "${slot:?}/${rel:?}"
    ln -sfn "$shared_abs" "$slot/$rel"
  done

  for rel in $INSTANCE_PERSISTENT_SEEDED_DIRS; do
    shared_abs="$root/shared/$rel"
    [ -n "$cur_rel" ] && _adopt_untracked "$cur_rel" "$rel" "$shared_abs" "the live release"
    [ "$slot" != "$cur_rel" ] && _adopt_untracked "$slot" "$rel" "$shared_abs" "this release"
    _seed_tracked "$slot" "$rel" "$shared_abs"
    mkdir -p "$shared_abs"
    rel_dir="$(dirname "$slot/$rel")"
    mkdir -p "$rel_dir"
    rm -rf "${slot:?}/${rel:?}"
    ln -sfn "$shared_abs" "$slot/$rel"
  done

  for rel in $INSTANCE_PERSISTENT_FILES; do
    shared_abs="$root/shared/$rel"
    # ADOPTION (2026-07-25, state-persistence preflight). A file CREATED at
    # runtime lives in the live release, never in shared/ — so on its own the
    # [ -e ] guard below made this list inert for exactly those files: it
    # skipped them forever and every deploy discarded the file again, which is
    # how trusted-mcps.json and war-room-seed.yml stayed lost even after being
    # listed (measured — the fix was not complete without this). If shared/
    # has no copy yet but the CURRENT release holds a real, untracked,
    # non-symlink file, adopt it into shared/ so this release and every later
    # one link to the same physical file.
    #
    # The tracked check is not optional: adopting a git-tracked file would
    # SHADOW the release's own copy with a frozen snapshot, the same hazard
    # the wildcard block guards against for deployment-status.md.
    if [ ! -e "$shared_abs" ] && [ -n "$cur_rel" ] && \
       [ -f "$cur_rel/$rel" ] && [ ! -L "$cur_rel/$rel" ] && \
       ! git -C "$cur_rel" ls-files --error-unmatch "$rel" >/dev/null 2>&1; then
      mkdir -p "$(dirname "$shared_abs")"
      cp -p "$cur_rel/$rel" "$shared_abs"
      echo "runtime-provision.sh: adopted $rel from the live release into shared/ (first persistence)"
    fi
    [ -e "$shared_abs" ] || continue   # no prior instance-data yet — leave absent
    rel_dir="$(dirname "$slot/$rel")"
    mkdir -p "$rel_dir"
    rm -f "${slot:?}/${rel:?}"
    ln -sfn "$shared_abs" "$slot/$rel"
  done

  # secrets file — flattened name, matches shared/cabinet.env's existing spelling
  mkdir -p "$slot/cabinet"
  rm -f "${slot:?}/cabinet/.env"
  ln -sfn "$root/shared/cabinet.env" "$slot/cabinet/.env"

  # Wildcard leaves — discovered from whatever already exists in shared/.
  #
  # ADOPTION FIRST (2026-07-25 fix). Discovery-only was a hole, not a design:
  # NOTHING seeds <runtime_root>/shared/shared/interfaces/, and the files these
  # blocks carry are all CREATED AT RUNTIME inside the live release. So the
  # policy certified shared/interfaces/**/*.md as "wildcard-linked" while the
  # block discovered an empty (non-existent) directory and linked nothing.
  # Measured 2026-07-25: captain-decisions.md and captain-patterns.md — the
  # append-only Captain-law ledgers — were written into the live release and
  # LOST by the next deploy, at exit 0, counted as covered. The same
  # discovery-only hole applies to the *-ceo.md and .oauth-backup-* blocks, so
  # all three adopt from the outgoing release before discovering.
  if [ -n "$cur_rel" ]; then
    _adopt_untracked "$cur_rel" "shared/interfaces" \
      "$root/shared/shared/interfaces" "the live release" '*.md'
    _adopt_untracked "$cur_rel" "instance/agents" \
      "$root/shared/instance/agents" "the live release" '*-ceo.md'
    # Root-level dotfile glob: matched directly rather than via find, so this
    # never walks the whole release tree.
    for f in "$cur_rel"/.oauth-backup-*.json; do
      [ -f "$f" ] || continue
      [ -L "$f" ] && continue
      [ -e "$root/shared/$(basename "$f")" ] && continue
      mkdir -p "$root/shared"
      cp -p "$f" "$root/shared/$(basename "$f")" 2>/dev/null &&
        echo "runtime-provision.sh: adopted $(basename "$f") from the live release into shared/"
    done
  fi
  if [ -d "$root/shared/instance/agents" ]; then
    for f in "$root/shared/instance/agents/"*-ceo.md; do
      [ -e "$f" ] || continue
      rel="instance/agents/$(basename "$f")"
      mkdir -p "$(dirname "$slot/$rel")"
      rm -f "${slot:?}/${rel:?}"
      ln -sfn "$f" "$slot/$rel"
    done
  fi
  for f in "$root/shared/".oauth-backup-*.json; do
    [ -e "$f" ] || continue
    rel="$(basename "$f")"
    rm -f "${slot:?}/${rel:?}"
    ln -sfn "$f" "$slot/$rel"
  done
  if [ -d "$root/shared/shared/interfaces" ]; then
    find "$root/shared/shared/interfaces" -type f -name '*.md' 2>/dev/null | while IFS= read -r f; do
      rel="shared/interfaces/${f#"$root/shared/shared/interfaces/"}"
      case "$rel" in
        shared/interfaces/deployment-status.md) continue ;;  # tracked file — never shadow it
      esac
      mkdir -p "$(dirname "$slot/$rel")"
      rm -f "${slot:?}/${rel:?}"
      ln -sfn "$f" "$slot/$rel"
    done
  fi
}

# ---- commands -------------------------------------------------------------------

cmd_init() {
  [ $# -ge 1 ] || { echo "usage: runtime-provision.sh init <runtime_root> --remote <git-url> [--seed-fresh-instance]" >&2; exit 64; }
  local root="$1"; shift
  local remote="" seed_fresh=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --remote) remote="${2:?--remote requires a git URL}"; shift 2 ;;
      --seed-fresh-instance) seed_fresh=1; shift ;;
      *) echo "runtime-provision.sh init: unknown flag '$1'" >&2; exit 64 ;;
    esac
  done
  mkdir -p "$root"
  root="$(abs_path "$root")"
  mkdir -p "$root/releases" "$root/shared"

  if [ -d "$root/repo.git" ]; then
    echo "runtime-provision.sh: repo.git already present at $root/repo.git (idempotent — leaving as-is; run 'fetch' to update)"
  else
    [ -n "$remote" ] || { echo "runtime-provision.sh init: --remote <git-url> is required for a first init" >&2; exit 64; }
    git clone --mirror "$remote" "$root/repo.git"
    echo "runtime-provision.sh: cloned bare mirror of $remote -> $root/repo.git"
  fi

  if [ ! -e "$root/shared/instance" ]; then
    if [ "$seed_fresh" = "1" ]; then
      _seed_fresh_instance "$root"
    else
      mkdir -p "$root/shared/instance"
      cat >&2 <<EOF
runtime-provision.sh: shared/instance/ created EMPTY — no instance data seeded.
  This runtime root is not yet usable for a real deploy. Either:
    - the CUTOVER RUNBOOK migrates the live deployment's real instance/ data
      here (docs/runbooks/dev-runtime-split-cutover.md), or
    - re-run init with --seed-fresh-instance for a sandbox/dev instance
      (generate-instance.py --defaults — NEVER real captain data).
EOF
    fi
  fi
  [ -e "$root/shared/cabinet.env" ] || : > "$root/shared/cabinet.env"
  echo "runtime-provision.sh: runtime root ready at $root"
}

# _seed_fresh_instance <root> — SANDBOX/DEV ONLY, called only from `init
# --seed-fresh-instance`. Provisions a throwaway release purely to run its
# own generate-instance.py --defaults once, harvests the resulting
# instance/ into shared/instance, then discards the throwaway worktree (the
# real first release is provisioned fresh right after by the normal
# `provision` flow).
_seed_fresh_instance() {
  local root="$1" seed_sha seed_slot py gen_log
  seed_sha="$(git_r "$root" rev-parse --verify --quiet HEAD 2>/dev/null || git_r "$root" rev-parse --verify refs/heads/master)"
  seed_slot="$root/releases/.seed-$$"
  git_r "$root" worktree add --detach "$seed_slot" "$seed_sha" >/dev/null
  py="python3.12"; command -v "$py" >/dev/null 2>&1 || py="python3"
  gen_log="$(mktemp)"
  if ! ( cd "$seed_slot" && "$py" cabinet/scripts/generate-instance.py --defaults ) >"$gen_log" 2>&1; then
    # Mirrors hatch.sh's own do_generate_instance fallback verbatim: THIS
    # repo's tracked instance/config/platform.yml already carries a real
    # 'officers:' block (it is itself a live deployment's checkout, not a
    # blank template), so generate-instance.py's own "inherited instance"
    # refusal fires on ANY fresh checkout of it, every time — --adopt is the
    # rehearsed, designed answer (archives the conflicting tracked file
    # aside under instance/_pre-adopt-<stamp>/, deletes nothing), not a
    # one-off retry hack.
    if grep -q "REFUSING to overwrite" "$gen_log"; then
      if ! ( cd "$seed_slot" && "$py" cabinet/scripts/generate-instance.py --defaults --adopt ) >>"$gen_log" 2>&1; then
        echo "runtime-provision.sh: --seed-fresh-instance generate-instance.py --defaults --adopt ALSO reported non-zero — inspect $gen_log and $seed_slot/instance manually before trusting the seed" >&2
      fi
    else
      echo "runtime-provision.sh: --seed-fresh-instance generate-instance.py step reported non-zero (not the known inherited-instance case) — see $gen_log; inspect $seed_slot/instance manually before trusting the seed" >&2
    fi
  fi
  rm -f "$gen_log"
  mkdir -p "$root/shared/instance"
  if [ -d "$seed_slot/instance" ]; then
    cp -a "$seed_slot/instance/." "$root/shared/instance/"
    echo "runtime-provision.sh: seeded shared/instance from a fresh --defaults generate-instance.py run (sandbox data only, no captain data)"
  fi
  git_r "$root" worktree remove --force "$seed_slot" 2>/dev/null || rm -rf "$seed_slot"
}

cmd_fetch() {
  [ $# -ge 1 ] || { echo "usage: runtime-provision.sh fetch <runtime_root>" >&2; exit 64; }
  local root; root="$(abs_path "$1")"
  require_runtime_root "$root"
  git_r "$root" fetch --prune
}

cmd_resolve() {
  [ $# -ge 2 ] || { echo "usage: runtime-provision.sh resolve <runtime_root> <ref>" >&2; exit 64; }
  local root ref sha
  root="$(abs_path "$1")"; ref="$2"
  require_runtime_root "$root"
  if sha="$(git_r "$root" rev-parse --verify --quiet "${ref}^{commit}")"; then
    printf '%s\n' "$sha"; return 0
  fi
  # Tolerate the origin/<branch> spelling out of habit: a --mirror clone
  # maps refs/heads/* directly (no refs/remotes/origin/* namespace), so
  # origin/master isn't a ref here even though 'master' is.
  case "$ref" in
    origin/*)
      local stripped="${ref#origin/}"
      if sha="$(git_r "$root" rev-parse --verify --quiet "${stripped}^{commit}")"; then
        printf '%s\n' "$sha"; return 0
      fi
      ;;
  esac
  echo "runtime-provision.sh resolve: cannot resolve ref '$ref' in $root/repo.git (fetch first?)" >&2
  exit 1
}

cmd_provision() {
  [ $# -ge 2 ] || { echo "usage: runtime-provision.sh provision <runtime_root> <ref>" >&2; exit 64; }
  local root ref sha slot
  root="$(abs_path "$1")"; ref="$2"
  require_runtime_root "$root"
  sha="$(cmd_resolve "$root" "$ref")"
  slot="$root/releases/$sha"
  if [ -d "$slot" ]; then
    echo "runtime-provision.sh: release $sha already provisioned at $slot (idempotent)"
  else
    git_r "$root" worktree add --detach "$slot" "$sha"
    echo "runtime-provision.sh: provisioned $sha -> $slot"
  fi
  # Persistent instance data + secrets: replace the individually-gitignored
  # leaves (only — see file header "WHY LEAF-LEVEL...") with symlinks into
  # the ONE shared physical tree. Called unconditionally (fresh checkout OR
  # reusing an existing slot) so newly-added shared/ data gets picked up on
  # a re-provision too. This deliberately means release worktrees always
  # show those specific leaf paths as "modified/deleted" under `git status`
  # — expected; they are disposable and never developed in (prune/promote-
  # time removal always uses `git worktree remove --force`).
  link_instance_data "$slot" "$root"
  echo "runtime-provision.sh: instance data + secrets linked (shared/ <-> $slot)"
  echo "PROVISIONED_SHA=$sha"
  echo "PROVISIONED_SLOT=$slot"
}

cmd_promote() {
  [ $# -ge 2 ] || { echo "usage: runtime-provision.sh promote <runtime_root> <sha>" >&2; exit 64; }
  local root sha slot old_target=""
  root="$(abs_path "$1")"; sha="$2"
  require_runtime_root "$root"
  slot="$root/releases/$sha"
  [ -d "$slot" ] || { echo "runtime-provision.sh promote: no provisioned release for $sha (run 'provision' first)" >&2; exit 1; }
  [ -L "$root/current" ] && old_target="$(readlink "$root/current")"
  swap_symlink "$slot" "$root/current"
  if [ -n "$old_target" ] && [ "$old_target" != "$slot" ]; then
    swap_symlink "$old_target" "$root/previous"
  fi
  printf '%s promote sha=%s slot=%s prev=%s\n' "$(date -u +%FT%TZ)" "$sha" "$slot" "${old_target:-none}" >> "$root/.cabinet-deploy.log"
  echo "runtime-provision.sh: current -> $slot"
}

cmd_rollback() {
  [ $# -ge 1 ] || { echo "usage: runtime-provision.sh rollback <runtime_root>" >&2; exit 64; }
  local root prev_target cur_target=""
  root="$(abs_path "$1")"
  require_runtime_root "$root"
  [ -L "$root/previous" ] || { echo "runtime-provision.sh rollback: no 'previous' marker — nothing to roll back to" >&2; exit 1; }
  prev_target="$(readlink "$root/previous")"
  [ -d "$prev_target" ] || { echo "runtime-provision.sh rollback: previous target $prev_target no longer exists on disk" >&2; exit 1; }
  [ -L "$root/current" ] && cur_target="$(readlink "$root/current")"
  swap_symlink "$prev_target" "$root/current"
  [ -n "$cur_target" ] && swap_symlink "$cur_target" "$root/previous"
  printf '%s rollback current->%s prev->%s\n' "$(date -u +%FT%TZ)" "$prev_target" "${cur_target:-none}" >> "$root/.cabinet-deploy.log"
  echo "runtime-provision.sh: rolled back — current -> $prev_target"
}

cmd_current() {
  [ $# -ge 1 ] || { echo "usage: runtime-provision.sh current <runtime_root>" >&2; exit 64; }
  local root; root="$(abs_path "$1")"
  require_runtime_root "$root"
  if [ -L "$root/current" ]; then
    basename "$(readlink "$root/current")"
  else
    echo "NONE"
  fi
}

cmd_list() {
  [ $# -ge 1 ] || { echo "usage: runtime-provision.sh list <runtime_root>" >&2; exit 64; }
  local root cur="" prev="" d sha marker
  root="$(abs_path "$1")"
  require_runtime_root "$root"
  [ -L "$root/current" ] && cur="$(basename "$(readlink "$root/current")")"
  [ -L "$root/previous" ] && prev="$(basename "$(readlink "$root/previous")")"
  for d in "$root"/releases/*/; do
    [ -d "$d" ] || continue   # unmatched glob -> literal pattern; skip
    sha="$(basename "$d")"
    case "$sha" in .seed-*) continue ;; esac
    marker=""
    [ "$sha" = "$cur" ] && marker="$marker current"
    [ "$sha" = "$prev" ] && marker="$marker previous"
    printf '%s%s\n' "$sha" "$marker"
  done
}

cmd_prune() {
  [ $# -ge 1 ] || { echo "usage: runtime-provision.sh prune <runtime_root> [--keep N]" >&2; exit 64; }
  local root keep=5
  root="$1"; shift
  while [ $# -gt 0 ]; do
    case "$1" in --keep) keep="${2:?--keep requires a number}"; shift 2 ;; *) echo "runtime-provision.sh prune: unknown flag '$1'" >&2; exit 64 ;; esac
  done
  root="$(abs_path "$root")"
  require_runtime_root "$root"
  local cur="" prev="" d sha candidates=()
  [ -L "$root/current" ] && cur="$(basename "$(readlink "$root/current")")"
  [ -L "$root/previous" ] && prev="$(basename "$(readlink "$root/previous")")"
  for d in "$root"/releases/*/; do
    [ -d "$d" ] || continue
    sha="$(basename "$d")"
    case "$sha" in .seed-*) continue ;; esac
    [ "$sha" = "$cur" ] && continue
    [ "$sha" = "$prev" ] && continue
    candidates+=("$d")
  done
  [ "${#candidates[@]}" -gt 0 ] || { echo "runtime-provision.sh: nothing to prune"; return 0; }
  local sorted i=0 rm_dir
  # `awk '{print $2}'` here would TRUNCATE any runtime root containing a space
  # and hand the truncated prefix to `rm -rf` — strip only the leading mtime
  # field instead, so the rest of the line survives verbatim.
  #
  # GNU-FIRST IS LOAD-BEARING, not stylistic. `-f` means "format string" to BSD
  # stat and "file system" to GNU stat, so a BSD-first probe does not fail over
  # on Linux the way an unknown flag would: it takes the GNU branch with
  # directives that mean nothing there. Under this script's `set -euo pipefail`
  # that non-zero status propagated out of the pipeline and prune EXITED 1
  # having pruned nothing (measured on Linux: CI run 30183105928, the
  # `test_prune_handles_a_runtime_root_containing_a_space` arm). Probing the
  # GNU form first is the only order where each platform's real answer wins.
  #
  # A candidate whose mtime cannot be read at all is DROPPED from the list
  # rather than defaulted, so it is never deleted. Prune keeping too much costs
  # disk; prune deleting the wrong release is unrecoverable.
  sorted="$(for d in "${candidates[@]}"; do
              stat -c '%Y %n' "$d" 2>/dev/null ||
              stat -f '%m %N' "$d" 2>/dev/null ||
              true
            done | sort -rn | sed 's/^[0-9]* //')"
  while IFS= read -r rm_dir; do
    [ -z "$rm_dir" ] && continue
    i=$((i+1))
    if [ "$i" -gt "$keep" ]; then
      git_r "$root" worktree remove --force "$rm_dir" 2>/dev/null || rm -rf "$rm_dir"
      echo "runtime-provision.sh: pruned $(basename "$rm_dir")"
    fi
  done <<< "$sorted"
}

main() {
  local cmd="${1:-}"
  case "$cmd" in
    -h|--help|"") usage; [ -n "$cmd" ] && exit 0 || exit 64 ;;
  esac
  shift
  case "$cmd" in
    init)      cmd_init "$@" ;;
    fetch)     cmd_fetch "$@" ;;
    resolve)   cmd_resolve "$@" ;;
    provision) cmd_provision "$@" ;;
    promote)   cmd_promote "$@" ;;
    rollback)  cmd_rollback "$@" ;;
    current)   cmd_current "$@" ;;
    list)      cmd_list "$@" ;;
    prune)     cmd_prune "$@" ;;
    *) echo "runtime-provision.sh: unknown command '$cmd'" >&2; usage >&2; exit 64 ;;
  esac
}
main "$@"
