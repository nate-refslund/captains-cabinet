#!/usr/bin/env bash
# outcome-ratify.sh — the TERMINAL DOOR of the tap.
#
# A thin wrapper, deliberately: every door calls the one writer
# (framework/outcomes/ratify.py) and none of them composes YAML of its own.
# This script resolves the interpreter and the root, and gets out of the way.
#
# The terminal door is ATTRIBUTION, not authentication: it runs as the same
# uid as every officer, so the writer records its actor as `operator` and
# never `captain`. `--principal` names who is at the keyboard; unset, the
# writer derives it from the environment.
#
# Interpreter: ${CABINET_PYTHON:-python3.12}. Never a bare `python3` — the
# officer PATH's python3 is 3.9 on the deployment this ships to, and an
# unpinned interpreter is how a pull-path module silently changed meaning.
#
# Usage:
#   bash cabinet/scripts/outcome-ratify.sh --list [--json]
#   bash cabinet/scripts/outcome-ratify.sh <proposal-id> [--principal <who>] [--json]
#
# Exit: 0 ratified / already ratified · 3 not found · 4 invalid row ·
#       5 refused (unknown door, no principal, or a git-worktree root).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$REPO_ROOT}"
PYTHON="${CABINET_PYTHON:-python3.12}"

cd "$REPO_ROOT"
exec "$PYTHON" -m framework.outcomes.ratify --door terminal --root "$CABINET_ROOT" "$@"
