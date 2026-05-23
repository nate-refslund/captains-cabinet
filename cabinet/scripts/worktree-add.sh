#!/bin/bash
# worktree-add.sh — Create a Cabinet worktree for officer task isolation.
#
# Creates a git worktree at ~/work/cabinet-worktrees/<officer>-<task-id>/
# checked out at the specified branch (default: a fresh branch off master).
# Records the worktree path in the /tasks record's worktree_path field.
#
# CRITICAL boundary: Cabinet worktrees live at ~/work/cabinet-worktrees/ ONLY.
# NEVER touch .claude/worktrees/ (dev-tasks plugin territory per Phase B).
#
# Usage:
#   bash cabinet/scripts/worktree-add.sh <officer> <task-id> [branch]
#
# Example:
#   bash cabinet/scripts/worktree-add.sh cto 1234 feature/spec-038-tasks
#
# Per Spec 063 v1.1 Checkpoint 6.1.

set -euo pipefail

OFFICER="${1:?Usage: worktree-add.sh <officer> <task-id> [branch]}"
TASK_ID="${2:?Usage: worktree-add.sh <officer> <task-id> [branch]}"
BRANCH="${3:-}"

# Source repo location: Mac convention is ~/work/captains-cabinet
# Override via CABINET_SOURCE_REPO env if Captain has a different path
SOURCE_REPO="${CABINET_SOURCE_REPO:-$HOME/work/captains-cabinet}"
CABINET_WORKTREE_ROOT="${CABINET_WORKTREE_ROOT:-$HOME/work/cabinet-worktrees}"
WORKTREE_PATH="${CABINET_WORKTREE_ROOT}/${OFFICER}-${TASK_ID}"

# Idempotency check (Spec 063 v1.1 SHOULD-fold: re-run on same task-id)
if [ -d "$WORKTREE_PATH" ]; then
  if git -C "$SOURCE_REPO" worktree list --porcelain 2>/dev/null | grep -q "^worktree $WORKTREE_PATH$"; then
    echo "worktree-add.sh: worktree already exists at $WORKTREE_PATH (idempotent re-run)"
    echo "$WORKTREE_PATH"
    exit 0
  else
    echo "worktree-add.sh: $WORKTREE_PATH exists but is not a registered git worktree — refusing to overwrite" >&2
    exit 1
  fi
fi

if [ ! -d "$SOURCE_REPO/.git" ]; then
  echo "worktree-add.sh: source repo not found at $SOURCE_REPO" >&2
  echo "  Set CABINET_SOURCE_REPO env to override" >&2
  exit 1
fi

mkdir -p "$CABINET_WORKTREE_ROOT"

# Branch resolution:
# - If branch given + exists: check it out
# - If branch given + doesn't exist: create off master
# - If no branch: create cabinet-worktree/<officer>-<task-id> off master
if [ -z "$BRANCH" ]; then
  BRANCH="cabinet-worktree/${OFFICER}-${TASK_ID}"
fi

cd "$SOURCE_REPO"

if git rev-parse --verify "$BRANCH" >/dev/null 2>&1; then
  # Existing branch — check it out
  git worktree add "$WORKTREE_PATH" "$BRANCH"
else
  # New branch off master
  git worktree add -b "$BRANCH" "$WORKTREE_PATH" master
fi

# Update /tasks record's worktree_path field (best-effort — don't fail if Neon unreachable)
if [ -n "${NEON_CONNECTION_STRING:-}" ]; then
  psql "$NEON_CONNECTION_STRING" -q -c \
    "UPDATE officer_tasks SET worktree_path = '$WORKTREE_PATH' WHERE id = $TASK_ID;" \
    >/dev/null 2>&1 || echo "worktree-add.sh: /tasks update failed (non-fatal)" >&2
fi

echo "$WORKTREE_PATH"
exit 0
