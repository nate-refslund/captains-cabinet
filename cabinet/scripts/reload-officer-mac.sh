#!/bin/bash
# reload-officer-mac.sh — Reload a Mac-native officer LaunchAgent after config edit.
#
# Cross-phase helper used by Mac Migration Phase 3.2 (product.yml reload),
# Phase 4.5b (mcp.json reload), Phase 5 (daily-digest config), and any later
# phase where a config edit needs the officer LaunchAgent to pick up new state.
#
# Pattern: launchctl bootout → launchctl bootstrap → verify fresh PID.
#
# Usage:
#   bash cabinet/scripts/reload-officer-mac.sh <officer>
#
# Example:
#   bash cabinet/scripts/reload-officer-mac.sh cos
#
# Exits 0 on success, non-zero on bootout/bootstrap failure or missing plist.
#
# Per Spec 061 v1.1 Checkpoint 4.5b extraction (cross-spec META).

set -euo pipefail

OFFICER="${1:?Usage: reload-officer-mac.sh <officer>}"

PLIST="$HOME/Library/LaunchAgents/com.cabinet.officer.${OFFICER}.plist"
LABEL="com.cabinet.officer.${OFFICER}"
UID_NUM=$(id -u)
DOMAIN="gui/${UID_NUM}"

if [ ! -f "$PLIST" ]; then
  echo "reload-officer-mac.sh: plist not found at $PLIST" >&2
  echo "  Did you run deploy-mac.sh --officer $OFFICER first?" >&2
  exit 1
fi

echo "Reloading officer $OFFICER (plist: $PLIST)..."

# bootout — silent if not loaded; non-zero exit is fine in that case
if launchctl print "${DOMAIN}/${LABEL}" >/dev/null 2>&1; then
  echo "  bootout existing service..."
  launchctl bootout "${DOMAIN}/${LABEL}" 2>/dev/null || true
  # Give launchd a moment to fully tear down (avoids EALREADYRUNNING on bootstrap)
  sleep 1
fi

# bootstrap — must succeed
echo "  bootstrap fresh service..."
if ! launchctl bootstrap "${DOMAIN}" "${PLIST}"; then
  echo "reload-officer-mac.sh: launchctl bootstrap failed for $LABEL" >&2
  exit 2
fi

# Verify fresh PID via launchctl print
NEW_PID=$(launchctl print "${DOMAIN}/${LABEL}" 2>/dev/null | grep -E '^\s*pid\s*=' | awk '{print $3}' | head -1)

if [ -z "$NEW_PID" ] || [ "$NEW_PID" = "0" ]; then
  echo "reload-officer-mac.sh: bootstrap returned but no fresh PID — service may not have started" >&2
  echo "  Check $HOME/Library/Logs/cabinet/${OFFICER}.err.log for startup errors" >&2
  exit 3
fi

echo "  reloaded — new PID: $NEW_PID"
exit 0
