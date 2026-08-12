#!/bin/bash
# Reset Cabinet Password — double-click this in Finder to reset a forgotten
# dashboard password. No Terminal to open, no command to type: double-clicking
# runs it, and every question and answer is a normal Mac dialog box.
#
# It clears the current password and returns the dashboard to its first-run
# "create a password" screen, where you choose a new one. Nothing is ever shown
# to you or sent anywhere. Resetting requires being at the Cabinet computer —
# you have to be able to double-click this file — so a locked-out stranger on
# the web can never trigger it.
#
# All it does is call the reset helper next to it; keep this file with the repo.

set -uo pipefail

# The repo root is this file's own folder — resolve it however we were launched.
ROOT="$(cd "$(dirname "$0")" && pwd)"
HELPER="$ROOT/cabinet/scripts/dashboard-password.sh"

have_osascript() { command -v osascript >/dev/null 2>&1; }

if [ ! -f "$HELPER" ]; then
  msg="Could not find the Cabinet reset helper. Keep 'Reset Cabinet Password' in your Cabinet folder, next to the 'cabinet' folder."
  if have_osascript; then
    osascript - "$msg" <<'OSA' >/dev/null 2>&1 || true
on run argv
  display dialog (item 1 of argv) buttons {"OK"} default button "OK" with title "Cabinet"
end run
OSA
  else
    echo "$msg" >&2
  fi
  exit 1
fi

# Confirm first — a reset is not something to do by a stray double-click.
if have_osascript; then
  if ! osascript >/dev/null 2>&1 <<'OSA'
display dialog "Reset your Cabinet password?

The current password will be cleared. The next time you open the dashboard, it will ask you to choose a new one." buttons {"Cancel", "Reset password"} default button "Cancel" cancel button "Cancel" with title "Cabinet" with icon caution
OSA
  then
    exit 0  # Cancelled — nothing changed.
  fi
fi

result="$(bash "$HELPER" --reset 2>&1)"

if have_osascript; then
  osascript - "$result" <<'OSA' >/dev/null 2>&1 || true
on run argv
  display dialog (item 1 of argv) buttons {"OK"} default button "OK" with title "Cabinet"
end run
OSA
else
  echo "$result"
fi
