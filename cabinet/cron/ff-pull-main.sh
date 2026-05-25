#!/usr/bin/env bash
# cabinet/cron/ff-pull-main.sh — #192 FF-pull backstop for the shared /opt working-tree checkout.
#
# WHY: detached-worktree pushes advance origin/mac-native but NOT the /opt working-tree that
# officers READ from — so officers can read stale merged code/hooks until someone FF-pulls. Manual
# FF-pull is the PRIMARY mitigation; this is the ~15-min BACKSTOP. CoS-spec'd 2026-05-25 (Option B):
# installed as a HOST cron (/etc/cron.d/cabinet-ff-pull, wired by CoS via host-agent) because the
# host has the repo rw + git, while the watchdog container mounts it :ro (preserving that boundary).
#
# SAFETY (writes to the shared tree — a bug affects every officer): NEVER clobbers local work.
# Fast-forwards ONLY when (a) HEAD is on the main branch, (b) the TRACKED tree is clean, and
# (c) the checkout is strictly behind origin (an ancestor). Dirty / diverged / wrong-branch -> skip.
# Never a merge commit, never a force, never a reset.
set -u

REPO="${CABINET_REPO:-/opt/founders-cabinet}"
BRANCH="${CABINET_MAIN_BRANCH:-mac-native}"
LOG="${FF_PULL_LOG:-${REPO}/cabinet/logs/ff-pull-main.log}"
LOCK="${FF_PULL_LOCK:-/tmp/cabinet-ff-pull.lock}"

log() { printf '%s [ff-pull] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$LOG" 2>/dev/null; }

# Single-flight: cron overlap must not run two pulls concurrently.
exec 9>"$LOCK" 2>/dev/null || exit 0
flock -n 9 2>/dev/null || { log "another run holds the lock; skip"; exit 0; }

cd "$REPO" 2>/dev/null || { log "repo $REPO not found; skip"; exit 0; }

# Branch-guard: only touch the checkout when it is ON the main branch. If another officer has a
# different branch checked out on the shared tree, DO NOT pull main onto it — skip.
cur="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
if [ "$cur" != "$BRANCH" ]; then
  log "HEAD is '$cur' not '$BRANCH'; skip (do not disturb another checkout)"
  exit 0
fi

# Tracked-only clean-gate (THE #192 gotcha): a `git status --porcelain` check would falsely abort
# because the shared checkout ALWAYS carries untracked .claude/worktrees/ + spawned-cabinets/.
# We gate on TRACKED changes only — unstaged OR staged — so untracked cruft never blocks the pull,
# but real uncommitted work is never clobbered.
if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
  log "tracked changes present (unstaged or staged); skip (won't clobber local work)"
  exit 0
fi

# Fetch the main branch.
if ! git fetch origin "$BRANCH" --quiet 2>/dev/null; then
  log "git fetch origin $BRANCH failed; skip"
  exit 0
fi

local_sha="$(git rev-parse HEAD 2>/dev/null || echo)"
remote_sha="$(git rev-parse "origin/${BRANCH}" 2>/dev/null || echo)"
[ -n "$local_sha" ] && [ -n "$remote_sha" ] || { log "could not resolve HEAD/origin sha; skip"; exit 0; }

# Already up to date -> silent no-op (no 15-min log spam).
[ "$local_sha" = "$remote_sha" ] && exit 0

# Strictly-behind check: HEAD must be an ancestor of origin/main, else the histories diverged and a
# fast-forward is impossible — skip + warn (a human must resolve; the backstop never force-resolves).
if ! git merge-base --is-ancestor HEAD "origin/${BRANCH}" 2>/dev/null; then
  log "WARN: HEAD ${local_sha:0:9} is NOT an ancestor of origin/${BRANCH} ${remote_sha:0:9} (diverged); skip"
  exit 0
fi

# Fast-forward ONLY.
if git merge --ff-only "origin/${BRANCH}" --quiet 2>/dev/null; then
  log "fast-forwarded ${local_sha:0:9} -> ${remote_sha:0:9}"
else
  log "WARN: ff-only merge failed unexpectedly (${local_sha:0:9} -> ${remote_sha:0:9}); skip"
fi
exit 0
