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

# Debounce on the sentinel's mtime. GNU FIRST: `stat -f` on GNU means "file
# system" and SUCCEEDS printing a mount point, so the old BSD-first order was
# not portable at all in the GNU direction, which is what the comment claimed.
if [ -f "$SENTINEL" ]; then
  _now=$(date +%s)
  _last=$(stat -c %Y "$SENTINEL" 2>/dev/null || stat -f %m "$SENTINEL" 2>/dev/null || echo 0)
  [ $((_now - _last)) -lt "$DEBOUNCE_S" ] && exit 0
fi

HOOK_INPUT=$(cat)

# G3 (docs/proposals/germline-amendment-employee-phase1-2026-09.md). This hook is
# the officer's ONLY pull tick, and it had two silences. `python3` is whatever the
# officer's PATH resolves (3.9.6 under launchd on this box, while the framework
# targets 3.12), so the interpreter — not the code — decided whether the pull path
# imported at all; and `2>/dev/null` threw away the traceback that would have said
# so. A claim sensor that cannot fail loudly reports "no task" for a broken import
# and for an empty queue in exactly the same way.
# HOME is defaulted because `set -u` is on: an unset HOME must not abort the tick.
CABINET_HOOK_LOG="${CABINET_HOOK_LOG:-${HOME:-/tmp}/Library/Logs/cabinet/hooks.err}"
mkdir -p "$(dirname "$CABINET_HOOK_LOG")" || CABINET_HOOK_LOG=/dev/stderr

# Holder identity for the claim the pull path takes
# (framework/missions/claims.py derive_holder, CABINET_WORKER_ID). Unset, the
# holder degrades to <role>@session:<pid>, so one role's two live sessions are
# told apart by a pid that a restart reuses. The session id is stable for the
# session that actually holds the work. jq absent or the field missing ⇒
# "nosession", never an empty holder.
_SESSION_ID="$(jq -r '.session_id // "nosession"' <<<"$HOOK_INPUT" 2>>"$CABINET_HOOK_LOG")"
export CABINET_WORKER_ID="${OFFICER}@${_SESSION_ID:-nosession}"

RESULT="$("${CABINET_PYTHON:-python3.12}" -c "
import sys; sys.path.insert(0, '$CABINET_ROOT')
from framework.missions.session_bridge import get_next_task, format_task_for_session
task = get_next_task('$OFFICER', cabinet_root='$CABINET_ROOT')
if task:
    print(format_task_for_session(task))
" 2>>"$CABINET_HOOK_LOG")"

[ -z "$RESULT" ] && exit 0

# Debounce ONLY on a real injection: an empty poll must not burn DEBOUNCE_S, so a
# task becoming ready seconds later still surfaces on the next prompt.
touch "$SENTINEL"

MSG="Mission task available: $RESULT"
printf '%s' "$MSG" | jq -R -s '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: .}}'
