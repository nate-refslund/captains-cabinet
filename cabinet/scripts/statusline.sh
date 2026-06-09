#!/bin/bash
# cabinet/scripts/statusline.sh — Cabinet status line for the CC TUI (gap report G8)
#
# Reads a JSON payload from stdin (CC provides session context such as
# project_dir, model, transcript_path) and prints a single status line of the
# form:
#
#   <officer> | OVI: 0.62 ↑ | mission: outcome-001 (3/5)
#
# Wired in .claude/settings.json:
#   "statusLine": { "type": "command", "command": "bash <project>/cabinet/scripts/statusline.sh" }
#
# Side-effect-free, fast (<200ms target). No network calls, no LLM calls.
# Reads only local event log + role registry.

set -u

# Read stdin (CC payload — we don't strictly need it but consume it to avoid
# SIGPIPE downstream).
_INPUT="$(cat 2>/dev/null || true)"

# Script lives at cabinet/scripts/statusline.sh — repo root is TWO levels up
# (../.. not ../). The earlier one-level resolution silently broke event-log
# discovery whenever CABINET_ROOT wasn't already exported.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
OFFICER="${OFFICER_NAME:-${CABINET_OFFICER:-unknown}}"

# ---- OVI: read the latest snapshot from the local event log ----
# Event-log discovery, in priority order:
#   1. $CABINET_EVENT_LOG_DIR    — matches framework/events/emitter.py
#                                  _event_log_dir(), which reads the same env
#                                  var. Single source of truth.
#   2. $CABINET_ROOT/memory/logs/events — legacy repo-relative path, retained for
#                                  Cabinets that have historic events here.
#   3. ~/Library/Application Support/cabinet/events — emitter's durable default
#                                  when nothing else is set.
#   4. /tmp/cabinet-events       — emitter's pre-durability default, retained for
#                                  Cabinets with historic events there.
# (F3/event-kernel-unification will collapse this list. Until then we accept
# all four so the statusline keeps working across the migration.)
OVI_DIR=""
for candidate in \
  "${CABINET_EVENT_LOG_DIR:-}" \
  "$CABINET_ROOT/memory/logs/events" \
  "$HOME/Library/Application Support/cabinet/events" \
  "/tmp/cabinet-events"; do
  if [ -n "$candidate" ] && [ -d "$candidate" ]; then
    OVI_DIR="$candidate"
    break
  fi
done
OVI_LINE=""
if [ -d "$OVI_DIR" ]; then
  # The framework emits ovi_published events with payload.score.
  OVI_LINE="$(grep -lh 'ovi_published' "$OVI_DIR"/*.jsonl 2>/dev/null | tail -1 | xargs -I {} grep 'ovi_published' {} 2>/dev/null | tail -1)"
fi

OVI_SCORE=""
OVI_TREND="·"
if [ -n "$OVI_LINE" ]; then
  OVI_SCORE="$(printf '%s' "$OVI_LINE" | python3 -c 'import json,sys
try:
    d=json.loads(sys.stdin.read())
    p=d.get("payload") or {}
    s=p.get("score") or p.get("ovi") or p.get("composite")
    if s is not None: print(f"{float(s):.2f}")
except Exception:
    pass' 2>/dev/null)"
  # Trend arrow: compare against previous if available
  PREV="$(grep -h 'ovi_published' "$OVI_DIR"/*.jsonl 2>/dev/null | tail -2 | head -1)"
  if [ -n "$PREV" ] && [ -n "$OVI_SCORE" ]; then
    PREV_SCORE="$(printf '%s' "$PREV" | python3 -c 'import json,sys
try:
    d=json.loads(sys.stdin.read())
    p=d.get("payload") or {}
    s=p.get("score") or p.get("ovi") or p.get("composite")
    if s is not None: print(f"{float(s):.2f}")
except Exception:
    pass' 2>/dev/null)"
    if [ -n "$PREV_SCORE" ]; then
      OVI_TREND="$(python3 -c "
prev=float('$PREV_SCORE'); cur=float('$OVI_SCORE')
print('↑' if cur > prev else '↓' if cur < prev else '→')" 2>/dev/null)"
    fi
  fi
fi

# ---- Mission: most-recent active mission + its ready/done counts ----
MISSION_LINE=""
if [ -d "$OVI_DIR" ]; then
  # Latest mission_created event for any active mission this officer participates in
  LAST_MISSION="$(grep -h 'mission_created' "$OVI_DIR"/*.jsonl 2>/dev/null | tail -1)"
  if [ -n "$LAST_MISSION" ]; then
    OUTCOME_ID="$(printf '%s' "$LAST_MISSION" | python3 -c 'import json,sys
try:
    d=json.loads(sys.stdin.read())
    print((d.get("payload") or {}).get("outcome_id") or "")
except Exception:
    pass' 2>/dev/null)"
    if [ -n "$OUTCOME_ID" ]; then
      TASK_COUNT="$(printf '%s' "$LAST_MISSION" | python3 -c 'import json,sys
try:
    d=json.loads(sys.stdin.read())
    print((d.get("payload") or {}).get("task_count") or 0)
except Exception:
    print(0)' 2>/dev/null)"
      DONE_COUNT="$(grep -h 'work_item_completed' "$OVI_DIR"/*.jsonl 2>/dev/null | grep -c "\"outcome_id\": \"$OUTCOME_ID\"" || echo 0)"
      MISSION_LINE="mission: $OUTCOME_ID ($DONE_COUNT/$TASK_COUNT)"
    fi
  fi
fi

# ---- Assemble ----
parts=("$OFFICER")
if [ -n "$OVI_SCORE" ]; then
  parts+=("OVI: $OVI_SCORE $OVI_TREND")
fi
if [ -n "$MISSION_LINE" ]; then
  parts+=("$MISSION_LINE")
fi

# Join with " | "
joined=""
for p in "${parts[@]}"; do
  if [ -z "$joined" ]; then
    joined="$p"
  else
    joined="$joined | $p"
  fi
done

printf '%s\n' "$joined"
