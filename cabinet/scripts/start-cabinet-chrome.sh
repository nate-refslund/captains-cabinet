#!/bin/bash
# start-cabinet-chrome.sh — launch the dedicated Cabinet Chrome profile.
#
# Why a dedicated profile:
#   - Captain logs into product platforms (Linear, Monday, Notion, Gmail,
#     etc.) ONCE in this profile. All Cabinet officers inherit those
#     sessions via the chrome-devtools MCP.
#   - Banking, personal email, sensitive sites live in the Captain's MAIN
#     Chrome profile — this dedicated profile keeps them isolated.
#   - Remote debugging port is bound to 127.0.0.1 ONLY (per Corridor
#     security guidance) so only local Cabinet processes can connect.
#
# Idempotent:
#   - If a Cabinet Chrome is already running on 127.0.0.1:9222, do nothing.
#   - Otherwise, launch in background; verify CDP is reachable; print URL.
#
# LaunchAgent (com.cabinet.chrome-profile) wraps this so it auto-starts at
# boot. Deploy via: bash cabinet/scripts/deploy-mac.sh --daemon chrome-profile

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

PROFILE_DIR="${CABINET_CHROME_PROFILE_DIR:-$HOME/.cabinet-chrome-profile}"
DEBUG_PORT="${CABINET_CHROME_DEBUG_PORT:-9222}"
# 127.0.0.1 only — never bind to 0.0.0.0. Corridor security invariant:
# "all remote debugging and MCP communication interfaces bind exclusively to
# 127.0.0.1 to prevent exposure to external network interfaces".
DEBUG_HOST="127.0.0.1"

CHROME_APP="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ ! -x "$CHROME_APP" ]; then
  echo "[start-cabinet-chrome] Google Chrome not found at $CHROME_APP" >&2
  echo "[start-cabinet-chrome] Install: brew install --cask google-chrome" >&2
  exit 1
fi

# Idempotency check: if CDP endpoint already responsive, do nothing.
if curl -fsS "http://$DEBUG_HOST:$DEBUG_PORT/json/version" >/dev/null 2>&1; then
  echo "[start-cabinet-chrome] Cabinet Chrome already running on $DEBUG_HOST:$DEBUG_PORT — no-op."
  curl -s "http://$DEBUG_HOST:$DEBUG_PORT/json/version" | head -200
  exit 0
fi

mkdir -p "$PROFILE_DIR"

echo "[start-cabinet-chrome] Profile dir : $PROFILE_DIR"
echo "[start-cabinet-chrome] Debug bind  : $DEBUG_HOST:$DEBUG_PORT (local-only)"
echo "[start-cabinet-chrome] Launching Chrome..."

# --no-first-run + --no-default-browser-check: prevent first-launch dialogs
# --disable-features=DefaultBrowserSettingEnforcement: stop "make default" nag
# --restore-last-session: keep the Captain's Cabinet tabs (Linear, Monday, etc.)
#   open across restarts
nohup "$CHROME_APP" \
  --user-data-dir="$PROFILE_DIR" \
  --remote-debugging-port="$DEBUG_PORT" \
  --remote-debugging-address="$DEBUG_HOST" \
  --no-first-run \
  --no-default-browser-check \
  --disable-features=DefaultBrowserSettingEnforcement \
  --restore-last-session \
  >"$HOME/Library/Logs/cabinet/chrome-profile.out.log" 2>"$HOME/Library/Logs/cabinet/chrome-profile.err.log" &
disown

# Wait up to 10s for CDP to come online.
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 1
  if curl -fsS "http://$DEBUG_HOST:$DEBUG_PORT/json/version" >/dev/null 2>&1; then
    echo "[start-cabinet-chrome] Ready after ${i}s."
    curl -s "http://$DEBUG_HOST:$DEBUG_PORT/json/version" | python3 -m json.tool 2>/dev/null | head -10
    echo ""
    echo "[start-cabinet-chrome] Next steps for Captain:"
    echo "  1. Switch to the new Chrome window."
    echo "  2. Sign into: Linear, Monday, Notion, Gmail (and any other tools"
    echo "     officers should be able to read/write on your behalf)."
    echo "  3. These sessions persist in $PROFILE_DIR."
    echo "  4. The chrome_devtools MCP can now drive this Chrome instance"
    echo "     for all officer browser tasks."
    exit 0
  fi
done

echo "[start-cabinet-chrome] WARN: CDP not responsive on $DEBUG_HOST:$DEBUG_PORT after 10s." >&2
echo "[start-cabinet-chrome] Check $HOME/Library/Logs/cabinet/chrome-profile.err.log" >&2
exit 1
