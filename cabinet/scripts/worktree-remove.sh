#!/bin/bash
# worktree-remove.sh — Remove a Cabinet worktree after task completion.
#
# Looks up the worktree path from the /tasks record, validates it is safely
# under ~/work/cabinet-worktrees/, then git-worktree-removes it.
#
# CRITICAL SAFETY GUARD: refuses to remove anything that does NOT resolve under
# ~/work/cabinet-worktrees/. Specifically protects .claude/worktrees/ (dev-tasks
# plugin territory) from accidental removal. Uses realpath to resolve symlinks
# + .. traversal attempts before the boundary check.
#
# Usage:
#   bash cabinet/scripts/worktree-remove.sh <task-id>
#
# Per Spec 063 v1.1 Checkpoint 6.2 (HIGHEST-priority CTO fold — realpath safety).

set -euo pipefail

TASK_ID="${1:?Usage: worktree-remove.sh <task-id>}"

SOURCE_REPO="${CABINET_SOURCE_REPO:-$HOME/work/captains-cabinet}"
CABINET_WORKTREE_ROOT="${CABINET_WORKTREE_ROOT:-$HOME/work/cabinet-worktrees}"
FORENSICS_DIR="${CABINET_FORENSICS_DIR:-$SOURCE_REPO/cabinet/logs/worktree-removed}"

# Look up the worktree path from /tasks
if [ -z "${NEON_CONNECTION_STRING:-}" ]; then
  echo "worktree-remove.sh: NEON_CONNECTION_STRING not set — cannot look up worktree_path" >&2
  exit 1
fi

WORKTREE_PATH=$(psql "$NEON_CONNECTION_STRING" -tA -c \
  "SELECT worktree_path FROM officer_tasks WHERE id = $TASK_ID;" 2>/dev/null)

if [ -z "$WORKTREE_PATH" ] || [ "$WORKTREE_PATH" = "NULL" ]; then
  echo "worktree-remove.sh: task $TASK_ID has no worktree_path — nothing to remove" >&2
  exit 0
fi

# Resolve symlinks + .. traversal to canonical absolute path
# realpath -m: 'missing' mode (does not fail if path doesn't exist)
RESOLVED=$(realpath -m "$WORKTREE_PATH" 2>/dev/null || echo "/dev/null/INVALID")
ROOT_RESOLVED=$(realpath -m "$CABINET_WORKTREE_ROOT" 2>/dev/null || echo "/dev/null/INVALID")

# Case-glob against literal HOME-prefixed root (handles macOS case-insensitive FS)
case "$RESOLVED" in
  "$ROOT_RESOLVED"/*)
    # OK — path resolves inside our root; safe to remove
    ;;
  *)
    echo "worktree-remove.sh: REFUSE — path $RESOLVED does not resolve under $ROOT_RESOLVED" >&2
    echo "  Cabinet worktrees live at $CABINET_WORKTREE_ROOT only." >&2
    echo "  .claude/worktrees/ (dev-tasks plugin) is OUT OF SCOPE." >&2
    exit 1
    ;;
esac

# Forensics: log uncommitted state before --force removal
mkdir -p "$FORENSICS_DIR"
FORENSICS_FILE="$FORENSICS_DIR/${TASK_ID}.txt"
{
  echo "Worktree removal forensics — task $TASK_ID"
  echo "Removed at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Path: $RESOLVED"
  echo ""
  echo "git status --porcelain:"
  git -C "$RESOLVED" status --porcelain 2>/dev/null || echo "  (not a git worktree — already removed?)"
  echo ""
  echo "git log -1 --oneline:"
  git -C "$RESOLVED" log -1 --oneline 2>/dev/null || echo "  (could not read log)"
} > "$FORENSICS_FILE"

# Remove the worktree (--force handles uncommitted state)
git -C "$SOURCE_REPO" worktree remove --force "$RESOLVED" 2>/dev/null || {
  echo "worktree-remove.sh: git worktree remove failed (already gone or corrupted); cleaning directly" >&2
  rm -rf "$RESOLVED"
}

# Clear the worktree_path field
psql "$NEON_CONNECTION_STRING" -q -c \
  "UPDATE officer_tasks SET worktree_path = NULL WHERE id = $TASK_ID;" \
  >/dev/null 2>&1 || true

echo "worktree-remove.sh: removed $RESOLVED (forensics: $FORENSICS_FILE)"
exit 0
