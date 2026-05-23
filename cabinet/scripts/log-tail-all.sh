#!/bin/bash
# log-tail-all.sh — Multi-tail all officer logs in one terminal.
#
# Streams stdout + stderr from all 5 officer LaunchAgents simultaneously,
# prefixed with [officer] for visual disambiguation.
#
# Usage:
#   bash cabinet/scripts/log-tail-all.sh                    # default 5 officers
#   bash cabinet/scripts/log-tail-all.sh cos cto cpo        # subset
#
# Logs live at $HOME/Library/Logs/cabinet/<officer>.{out,err}.log per Spec 059 v1.1
# plist convention (Mac-native, NOT Linux-FHS /var/log/cabinet/).
#
# Per Spec 064 v1.1 Checkpoint 7.5.

set -uo pipefail   # no -e: tail processes may die; we want the others to keep going

LOG_DIR="${CABINET_LOG_DIR:-$HOME/Library/Logs/cabinet}"
OFFICERS=("${@:-cos cto cpo cro coo}")
# If passed as space-separated single string, split:
if [ "${#OFFICERS[@]}" -eq 1 ] && [[ "${OFFICERS[0]}" == *" "* ]]; then
  read -ra OFFICERS <<< "${OFFICERS[0]}"
fi

if [ ! -d "$LOG_DIR" ]; then
  echo "log-tail-all.sh: log directory not found at $LOG_DIR" >&2
  echo "  (officers may not have started yet, or CABINET_LOG_DIR env mismatched)" >&2
  exit 1
fi

# Trap on Ctrl-C: kill all backgrounded tails
trap 'kill $(jobs -p) 2>/dev/null; exit 0' INT TERM

for o in "${OFFICERS[@]}"; do
  OUT_LOG="$LOG_DIR/$o.out.log"
  ERR_LOG="$LOG_DIR/$o.err.log"
  if [ -f "$OUT_LOG" ]; then
    tail -F "$OUT_LOG" 2>/dev/null | sed "s/^/[$o] /" &
  fi
  if [ -f "$ERR_LOG" ]; then
    tail -F "$ERR_LOG" 2>/dev/null | sed "s/^/[$o ERR] /" &
  fi
done

# Wait until all tails exit (Ctrl-C triggers the trap above)
wait
