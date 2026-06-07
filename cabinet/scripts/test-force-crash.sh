#!/bin/bash
# test-force-crash.sh — verify the watchdog restarts a force-killed officer.
#
# Post-activation validation. Run this AFTER the cabinet has been live for
# a few hours and you want to verify the supervisor / KeepAlive chain
# actually catches a hard crash.
#
# What it does:
#   1. Picks an officer (default: cos; override --officer)
#   2. Records the officer's tmux session PID + claude process PID
#   3. SIGKILL the claude process (simulates a hard crash)
#   4. Waits up to 60s for the watchdog (com.cabinet.heartbeat-watchdog +
#      LaunchAgent KeepAlive) to restart the officer
#   5. Verifies the new PID is alive + tmux session is back + heartbeat
#      fresh in Redis
#   6. Reports pass/fail
#
# Does NOT kill anything in --dry-run mode.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

OFFICER="cos"
DRY_RUN=0
TIMEOUT=60

while [ $# -gt 0 ]; do
  case "$1" in
    --officer) OFFICER="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    -h|--help) sed -n '1,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown: $1" >&2; exit 64 ;;
  esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; exit 1; }

echo "==========================================="
echo "  Force-crash test — officer: $OFFICER"
echo "==========================================="

# 1. Pre-state — officer must be running before we can crash it
TMUX_SESSION="officer-$OFFICER"
if ! tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
  fail "tmux session $TMUX_SESSION not found. Officer must be running first."
fi

# Find the claude process PID
PANE_PID=$(tmux list-panes -t "$TMUX_SESSION" -F '#{pane_pid}' 2>/dev/null | head -1)
if [ -z "$PANE_PID" ]; then
  fail "Couldn't find pane PID for $TMUX_SESSION"
fi
ok "Officer $OFFICER pane PID: $PANE_PID"

CLAUDE_PID=$(pgrep -P "$PANE_PID" -f claude | head -1)
if [ -z "$CLAUDE_PID" ]; then
  warn "No claude child of pane $PANE_PID; will kill the pane shell instead"
  CLAUDE_PID="$PANE_PID"
fi
ok "Target PID to kill: $CLAUDE_PID"

# Pre-crash heartbeat
HEARTBEAT_BEFORE=$(redis-cli -h "${REDIS_HOST:-127.0.0.1}" -p "${REDIS_PORT:-6379}" \
  GET "cabinet:heartbeat:liveness:$OFFICER" 2>/dev/null || echo "(none)")
ok "Heartbeat before crash: $HEARTBEAT_BEFORE"

if [ "$DRY_RUN" = "1" ]; then
  echo ""
  echo "  --dry-run set; would have killed PID $CLAUDE_PID."
  echo "  Exiting without crashing the officer."
  exit 0
fi

# 2. Crash it
echo ""
warn "Sending SIGKILL to PID $CLAUDE_PID..."
kill -9 "$CLAUDE_PID" || fail "kill -9 failed (may have been owned by another user)"
ok "SIGKILL sent. Now watching for restart..."

# 3. Wait up to TIMEOUT seconds for recovery
echo ""
echo "  Waiting up to ${TIMEOUT}s for watchdog recovery..."
SECONDS=0
RECOVERED=0
while [ "$SECONDS" -lt "$TIMEOUT" ]; do
  sleep 5
  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    NEW_PANE_PID=$(tmux list-panes -t "$TMUX_SESSION" -F '#{pane_pid}' 2>/dev/null | head -1)
    if [ -n "$NEW_PANE_PID" ] && [ "$NEW_PANE_PID" != "$PANE_PID" ]; then
      RECOVERED=1
      ok "Recovered! New pane PID: $NEW_PANE_PID (after ${SECONDS}s)"
      break
    fi
  fi
  echo "    ...${SECONDS}s waiting"
done

if [ "$RECOVERED" = "0" ]; then
  fail "Officer $OFFICER did NOT recover within ${TIMEOUT}s. Check launchctl + heartbeat-watchdog logs."
fi

# 4. Verify heartbeat refreshed (session-start.sh fires the liveness key)
sleep 3
HEARTBEAT_AFTER=$(redis-cli -h "${REDIS_HOST:-127.0.0.1}" -p "${REDIS_PORT:-6379}" \
  GET "cabinet:heartbeat:liveness:$OFFICER" 2>/dev/null || echo "(none)")
if [ "$HEARTBEAT_AFTER" != "(none)" ] && [ "$HEARTBEAT_AFTER" != "$HEARTBEAT_BEFORE" ]; then
  ok "Heartbeat refreshed: $HEARTBEAT_AFTER"
else
  warn "Heartbeat not yet refreshed — session may still be booting. Check again in 30s."
fi

echo ""
echo "==========================================="
echo "  Force-crash test PASS for officer: $OFFICER"
echo "  Recovery time: ${SECONDS}s"
echo "==========================================="
