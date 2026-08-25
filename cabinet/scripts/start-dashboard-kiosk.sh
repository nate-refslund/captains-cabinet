#!/bin/bash
# start-dashboard-kiosk.sh — open the office wall-display fullscreen.
#
# Waits for the dashboard to be reachable, then launches Google Chrome in
# kiosk (fullscreen, no chrome UI) pointed at the /display page. Runs on the
# Mac mini that's physically attached to the office monitor.
#
# Separate Chrome profile (~/.cabinet-kiosk-profile) so it doesn't share
# cookies/state with the Captain's Cabinet automation Chrome
# (~/.cabinet-chrome-profile, the one officers drive via chrome-devtools MCP).
#
# Wrapped by the com.cabinet.dashboard-kiosk LaunchAgent. Idempotent-ish:
# if a kiosk Chrome is already running on this profile, it focuses rather
# than spawning a second.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=cabinet/scripts/lib/dashboard.sh
. "$SCRIPT_DIR/lib/dashboard.sh"

# One resolver for the port (explicit env > cabinet/.env > 3100) so a moved
# dashboard does not become invisible to its own wall display.
PORT="$(cabinet_dash_port)"
BASE="http://127.0.0.1:${PORT}/"
URL="${BASE}display"
PROFILE_DIR="${CABINET_KIOSK_PROFILE_DIR:-$HOME/.cabinet-kiosk-profile}"

CHROME_APP="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ ! -x "$CHROME_APP" ]; then
  echo "start-dashboard-kiosk: Google Chrome not found at $CHROME_APP" >&2
  echo "  Install: brew install --cask google-chrome" >&2
  exit 1
fi

# Wait up to 120s for the dashboard to come up (first-run build can be slow).
# IDENTITY, not a bare 200: another program on this port answers 200 too, and
# a kiosk pointed at somebody else's dev server is worse than a blank screen.
echo "start-dashboard-kiosk: waiting for $URL ..."
for _ in $(seq 1 60); do
  if [ "$(cabinet_dash_state "$BASE")" = "mine" ]; then
    break
  fi
  sleep 2
done

KIOSK_STATE="$(cabinet_dash_state "$BASE")"
if [ "$KIOSK_STATE" = "other" ]; then
  echo "start-dashboard-kiosk: port $PORT is answering, but it is not this Cabinet —" >&2
  echo "  another program has that port. Nothing of theirs was changed." >&2
  exit 1
fi
if [ "$KIOSK_STATE" != "mine" ]; then
  echo "start-dashboard-kiosk: dashboard not reachable after 120s — is com.cabinet.dashboard running?" >&2
  exit 1
fi

mkdir -p "$PROFILE_DIR"
echo "start-dashboard-kiosk: launching kiosk Chrome → $URL"

# --kiosk           fullscreen, no UI, hard to exit (wall-display mode)
# --user-data-dir   isolated profile (separate from automation Chrome)
# --no-first-run / --no-default-browser-check  suppress dialogs
# --disable-session-crashed-bubble / --disable-infobars  no nags after power loss
# --incognito NOT used — we want the page to persist across restarts
exec "$CHROME_APP" \
  --kiosk \
  --user-data-dir="$PROFILE_DIR" \
  --no-first-run \
  --no-default-browser-check \
  --disable-session-crashed-bubble \
  --disable-features=Translate \
  --app="$URL"
