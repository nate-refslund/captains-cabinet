#!/bin/bash
# grant-mac-permissions.sh — interactive helper for macOS TCC grants.
#
# macOS Transparency, Consent & Control (TCC) requires the USER to click
# Allow on each Privacy & Security pane. There is NO scripted way to grant
# these permissions — Apple deliberately mandates user mediation.
#
# What this script CAN do:
#   1. Open the right System Settings pane for each permission
#   2. Tell the Captain which apps need Allow
#   3. Verify (where tools support a check) before moving on
#
# Permissions needed for the Captain-layer (framework-required tools only —
# these run on every deployment, opt-in sensor layer or not):
#
#   - Screen Recording        : cua-driver + (Cabinet Chrome to screenshot
#                                itself if you ever want it to)
#   - Accessibility           : cua-driver (clicks/types via AX API)
#   - Automation              : cua-driver (cross-app scripting hooks)
#   - Full Disk Access        : Backup script (cabinet/scripts/backup.sh)
#                                if it needs to read ~/Library/Application Support
#                                of other apps; OPTIONAL.
#
# If you also opted into the built-in screenpipe personal-source adapter
# (instance/config/sources.yml names it — see instance/flavor-a/README.md),
# that adapter needs ITS OWN Screen Recording / Accessibility / Microphone /
# Input Monitoring grants — walked through in that same README, not here
# (R168, 2026-07-16: this script no longer names a specific personal-
# productivity tool a fresh Captain hasn't necessarily chosen).

set -uo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }

pause_for_captain() {
  local msg="$1"
  echo ""
  echo -e "  ${YELLOW}>>${NC} $msg"
  echo -n "  Press Enter when done (or Ctrl+C to abort)... "
  read -r _
}

open_pane() {
  # Open a specific System Settings privacy pane. macOS 13+ syntax.
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_$1" 2>/dev/null || \
    open "x-apple.systempreferences:com.apple.preference.security" 2>/dev/null
}

echo "==========================================="
echo "  Cabinet — macOS permissions grant"
echo "==========================================="
echo ""
echo "  Each step opens a System Settings pane. Click 'Allow' for the"
echo "  listed apps, then press Enter here to continue to the next pane."
echo ""
echo "  If an app isn't listed yet, the first time it tries to use the"
echo "  capability macOS will prompt you — click Allow and re-run this"
echo "  script."
echo ""

# 1) Screen Recording — cua-driver
echo "[1/3] Screen Recording (cua-driver)"
open_pane "ScreenCapture"
pause_for_captain "Grant Screen Recording to: Terminal (or iTerm), cua-driver, Google Chrome"

# 2) Accessibility — cua-driver clicks/types
echo "[2/3] Accessibility (cua-driver)"
open_pane "Accessibility"
pause_for_captain "Grant Accessibility to: cua-driver, Terminal (so launched processes inherit)"

# 3) Automation — cua-driver scripting cross-app
echo "[3/3] Automation (cua-driver cross-app scripting)"
open_pane "Automation"
pause_for_captain "Grant Automation entries that say 'Terminal/cua-driver wants to control X' as they appear"

echo ""
echo "==========================================="
echo "  Verifying grants..."
echo "==========================================="

# Verify cua-driver if installed
if command -v cua-driver >/dev/null 2>&1; then
  if cua-driver check_permissions 2>&1 | tail -3; then
    ok "cua-driver permissions verified"
  else
    warn "cua-driver permission check failed — re-run grant pane above + this script"
  fi
else
  warn "cua-driver not installed — skipping verification (run install-mac-tools.sh first)"
fi

echo ""
echo "  (If you opted into the screenpipe personal-source adapter, verify"
echo "  and grant its permissions separately per instance/flavor-a/README.md.)"
echo ""
echo "==========================================="
echo "  Permissions step complete."
echo ""
echo "  Next: bash cabinet/scripts/start-cabinet-chrome.sh"
echo "==========================================="
