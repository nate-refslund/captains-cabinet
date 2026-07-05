#!/bin/bash
# session-task-inject.sh — UserPromptSubmit hook
# Injects the next mission task into the officer's session on first prompt.
set -u

# Bug fix (R4): hook lives at cabinet/scripts/hooks/, so repo root is three
# levels up. Convergence had only two ../ which resolved to cabinet/.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
OFFICER="${OFFICER_NAME:-${CABINET_OFFICER:-unknown}}"
SENTINEL="/tmp/.session-task-injected-${OFFICER}"
# Instance-tunable debounce (default 90s). Was a lifetime sentinel (inject ONCE
# per session); now re-inject at most once per DEBOUNCE_S so the NEXT ready
# mission task surfaces after the current one is started/completed — the compiler
# marks work_item_started -> IN_PROGRESS (A2) and it drops out of ready_tasks.
DEBOUNCE_S="${SESSION_TASK_INJECT_DEBOUNCE_S:-90}"

# Debounce on the sentinel's mtime (portable: BSD stat -f %m / GNU stat -c %Y).
if [ -f "$SENTINEL" ]; then
  _now=$(date +%s)
  _last=$(stat -f %m "$SENTINEL" 2>/dev/null || stat -c %Y "$SENTINEL" 2>/dev/null || echo 0)
  [ $((_now - _last)) -lt "$DEBOUNCE_S" ] && exit 0
fi

HOOK_INPUT=$(cat)

RESULT="$(python3 -c "
import sys; sys.path.insert(0, '$CABINET_ROOT')
from framework.missions.session_bridge import get_next_task, format_task_for_session
task = get_next_task('$OFFICER', cabinet_root='$CABINET_ROOT')
if task:
    print(format_task_for_session(task))
" 2>/dev/null)"

[ -z "$RESULT" ] && exit 0

# Debounce ONLY on a real injection: an empty poll must not burn DEBOUNCE_S, so a
# task becoming ready seconds later still surfaces on the next prompt.
touch "$SENTINEL"

MSG="Mission task available: $RESULT"
printf '%s' "$MSG" | jq -R -s '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: .}}'
