#!/bin/bash
# open-cabinet.sh — take me to my Cabinet. Start it if it isn't running, then
# open it in the browser (launcher area, 2026-08-25).
#
# WHY IT EXISTS. Setting a Cabinet up happens once; opening it happens every
# day. Until now only the setup run ever opened a browser, so the second
# double-click of the app had nothing to do and did nothing visible — and
# after a reboot, on a Mac where the background helpers were never turned on,
# nothing restarted the dashboard at all. This is the everyday path: probe,
# start if needed, open, say what happened.
#
# WHAT IT WILL NOT DO. It never stops or kills anything, never touches
# launchd, and never takes a port away from another program. If someone else
# has the door, it says so and moves to a free one.
#
# EVERY EXIT SAYS SOMETHING. A run that ends without a sentence is the defect
# this script was written against; there is a test that greps every exit point.
#
# Usage: bash cabinet/scripts/open-cabinet.sh [--no-browser]
#   --no-browser        do everything except raising a browser window
#   HATCH_NO_OPEN=1     same, from the environment (SSH sessions imply it)
#   CABINET_OPEN_TRIES  health-probe attempts, 2s apart (default 150 ≈ 10 min,
#                       because a first build is minutes, not seconds)
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# WHERE AM I. Normally cabinet/scripts/ inside the cabinet. But the Hatch
# Cabinet.app also carries a copy of this file (and of the probe lib) and drops
# them at the TOP of the install as app-owned dotfiles — that is what lets the
# app open a Cabinet that was set up before this script existed, without
# writing anything into the operator's cabinet/scripts/. Both layouts resolve
# to the same root, and the cabinet's OWN copy always wins when there is one.
if [ -d "$SCRIPT_DIR/cabinet/scripts" ]; then
  CABINET_ROOT="${CABINET_ROOT:-$SCRIPT_DIR}"
else
  CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/.." && cd .. && pwd)}"
fi

for _lib in "$SCRIPT_DIR/lib/dashboard.sh" \
            "$CABINET_ROOT/cabinet/scripts/lib/dashboard.sh" \
            "$SCRIPT_DIR/.hatch-dashboard-lib.sh"; do
  if [ -f "$_lib" ]; then
    # The path is chosen at run time from the three layouts above, so there is
    # no single literal for shellcheck to follow; the guard below is what
    # actually proves the lib loaded.
    # shellcheck source=cabinet/scripts/lib/dashboard.sh
    # shellcheck disable=SC1091
    . "$_lib"
    break
  fi
done
if ! command -v cabinet_dash_state >/dev/null 2>&1; then
  echo "Couldn't find the part that knows where your Cabinet answers."
  echo "Nothing was started and nothing was changed. Looked in:"
  echo "    $SCRIPT_DIR/lib/dashboard.sh"
  echo "    $CABINET_ROOT/cabinet/scripts/lib/dashboard.sh"
  echo "    $SCRIPT_DIR/.hatch-dashboard-lib.sh"
  exit 1
fi

NO_BROWSER=0
while [ $# -gt 0 ]; do
  case "$1" in
    --no-browser) NO_BROWSER=1; shift ;;
    -h|--help)
      echo "usage: bash cabinet/scripts/open-cabinet.sh [--no-browser]"
      exit 0 ;;
    *) echo "open-cabinet: unknown argument '$1'" >&2
       echo "usage: bash cabinet/scripts/open-cabinet.sh [--no-browser]" >&2
       exit 2 ;;
  esac
done
if [ "${HATCH_NO_OPEN:-0}" = "1" ] || [ -n "${SSH_CONNECTION:-}" ]; then
  NO_BROWSER=1
fi

cd "$CABINET_ROOT" || { echo "Couldn't reach your Cabinet folder: $CABINET_ROOT"; exit 1; }

PORT="$(cabinet_dash_port "$CABINET_ROOT")"
URL="http://127.0.0.1:${PORT}/"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="${CABINET_OPEN_LOG_DIR:-$HOME/hatch-logs/open-$STAMP}"
DASH_LOG="$LOG_DIR/dashboard.log"
MOVED_DOOR=""

open_browser() {
  # $1 = url. Prints its own sentence either way; never fatal.
  if [ "$NO_BROWSER" = "1" ]; then
    echo "Your Cabinet is ready at $1 (no browser window was opened, as you asked)."
    return 0
  fi
  if ! command -v open >/dev/null 2>&1; then
    echo "Your Cabinet is ready — go to $1 in your browser."
    return 0
  fi
  if open "$1"; then
    echo "Your Cabinet is open in your browser."
  else
    echo "Couldn't open your browser — go to $1 yourself."
  fi
  return 0
}

# Wait for MY dashboard to answer on $1. An identity match is the only thing
# that counts as an answer: a foreign app returning 200 is not my Cabinet
# coming up, and treating it as one is exactly the bug this area exists for.
wait_for_mine() {
  local url="$1" tries="${CABINET_OPEN_TRIES:-150}" waited=0 state
  echo "Waiting for your Cabinet to answer. You don't need to do anything."
  while [ "$tries" -gt 0 ]; do
    state="$(cabinet_dash_state "$url")"
    if [ "$state" = "mine" ]; then return 0; fi
    sleep 2
    waited=$((waited + 2))
    tries=$((tries - 1))
    if [ "$((waited % 60))" = "0" ]; then
      echo "Still starting (${waited}s so far — the first time, it builds itself). This is normal."
    fi
  done
  return 1
}

start_dashboard() {
  # $1 = port to serve on. Starts it detached so it outlives this window.
  mkdir -p "$LOG_DIR" 2>/dev/null || true
  : > "$DASH_LOG" 2>/dev/null || true
  CABINET_DASHBOARD_PORT="$1" nohup bash "$CABINET_ROOT/cabinet/scripts/start-dashboard.sh" >>"$DASH_LOG" 2>&1 &
  echo "Starting your Cabinet (id $!). It keeps running after this window closes."
  echo "Notes for later, if anything looks wrong: $DASH_LOG"
}

STATE="$(cabinet_dash_state "$URL")"

case "$STATE" in
  mine)
    echo "Your Cabinet is already running at $URL."
    open_browser "$URL"
    exit 0
    ;;
  other)
    # Someone else's program has the door. Do NOT stop it, do NOT serve on top
    # of it — find a free door, write it down so everything else agrees, and
    # say so in one line the operator can act on.
    echo "Your usual door ($URL) is in use by another app on this Mac."
    echo "Nothing of theirs was stopped or changed."
    NEWPORT="$(cabinet_dash_pick_port 3100 3199)"
    if [ -z "$NEWPORT" ]; then
      echo "Every door from 3100 to 3199 is busy, so your Cabinet has nowhere to answer."
      echo "Close one of those programs and open this app again."
      exit 1
    fi
    if ! cabinet_dash_record_port "$CABINET_ROOT" "$NEWPORT" \
         "port $PORT was in use by another app; your Cabinet moved to $NEWPORT."; then
      echo "Couldn't write down the new door in $CABINET_ROOT/cabinet/.env."
      echo "Nothing was changed. Your Cabinet was not started."
      exit 1
    fi
    PORT="$NEWPORT"
    URL="http://127.0.0.1:${PORT}/"
    MOVED_DOOR=1
    start_dashboard "$PORT"
    ;;
  *)
    echo "Your Cabinet isn't running. Starting it now."
    start_dashboard "$PORT"
    ;;
esac

if wait_for_mine "$URL"; then
  if [ -n "$MOVED_DOOR" ]; then
    echo "Your usual door was in use by another app, so your Cabinet now answers at $URL"
  fi
  open_browser "$URL"
  exit 0
fi

echo "Your Cabinet is taking longer than expected to answer."
echo "Nothing is broken and nothing is lost — give it a minute, then go to:"
echo "    $URL"
echo "If it still doesn't load, the notes are in: $DASH_LOG"
exit 1
