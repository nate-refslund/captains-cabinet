#!/bin/bash
# session-task-inject.sh — UserPromptSubmit hook
# Injects the next mission task into the officer's session on first prompt.
set -u

# Bug fix (R4): hook lives at cabinet/scripts/hooks/, so repo root is three
# levels up. Convergence had only two ../ which resolved to cabinet/.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-${CABINET_OFFICER:-unknown}}"
SENTINEL="/tmp/.session-task-injected-${OFFICER}"

# Only run on the first prompt of a session
[ -f "$SENTINEL" ] && exit 0

HOOK_INPUT=$(cat)

touch "$SENTINEL"

RESULT="$(python3 -c "
import sys; sys.path.insert(0, '$CABINET_ROOT')
from framework.missions.session_bridge import get_next_task, format_task_for_session
task = get_next_task('$OFFICER', cabinet_root='$CABINET_ROOT')
if task:
    print(format_task_for_session(task))
" 2>/dev/null)"

[ -z "$RESULT" ] && exit 0

MSG="Mission task available: $RESULT"
printf '%s' "$MSG" | jq -R -s '{hookSpecificOutput: {additionalContext: .}}'
