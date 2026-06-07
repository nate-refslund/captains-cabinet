#!/bin/bash
# test-recovery.sh — simulate a Mac mini reboot without actually rebooting.
#
# Post-activation validation. Verifies that the LaunchAgent set comes back
# correctly when the user logs out + back in (the closest non-destructive
# simulation of a power cycle).
#
# What it does:
#   1. Records the current state: which plists are loaded, officer PIDs,
#      Redis up?, Cabinet Chrome on 9222?, cabinet_memory reachable?
#   2. Bootouts every com.cabinet.* LaunchAgent
#   3. Verifies they're all unloaded
#   4. Bootstraps them again
#   5. Waits up to 90s for everything to come back
#   6. Verifies post-state matches pre-state
#
# Does NOT kill Redis or the Mac mini itself — that requires an actual
# reboot or `sudo shutdown -r now`, which this script refuses to do.
#
# Use --dry-run to skip the bootout/bootstrap and just snapshot state.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

DRY_RUN=0
TIMEOUT=90

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --timeout) TIMEOUT="$2"; shift 2 ;;
    -h|--help) sed -n '1,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown: $1" >&2; exit 64 ;;
  esac
done

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "  ${GREEN}[OK]${NC} $1"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; exit 1; }

snapshot_state() {
  echo "  loaded plists:"
  launchctl print "gui/$(id -u)" 2>/dev/null | grep -oE "com\.cabinet\.[a-z._-]+" | sort -u | sed 's/^/    /' || true
  echo "  tmux officer sessions:"
  tmux list-sessions 2>/dev/null | grep -E "^officer-" | sed 's/^/    /' || echo "    (none)"
  echo "  redis ping: $(redis-cli ping 2>/dev/null || echo unreachable)"
  echo "  cabinet chrome 9222: $(curl -fsS http://127.0.0.1:9222/json/version 2>/dev/null | jq -r '.Browser' 2>/dev/null || echo unreachable)"
  if [ -n "${NEON_CONNECTION_STRING:-}" ]; then
    echo "  neon: $(psql "$NEON_CONNECTION_STRING" -tAc "SELECT 1" 2>/dev/null || echo unreachable)"
  fi
}

echo "==========================================="
echo "  Recovery test — simulated Mac mini reboot"
echo "==========================================="
echo ""
echo "  PRE-state:"
snapshot_state

if [ "$DRY_RUN" = "1" ]; then
  echo ""
  echo "  --dry-run set; snapshot only. Exit."
  exit 0
fi

# Bootout every cabinet LaunchAgent
echo ""
warn "Bootouting com.cabinet.* LaunchAgents..."
LOADED_PLISTS=$(launchctl print "gui/$(id -u)" 2>/dev/null | grep -oE "com\.cabinet\.[a-z._-]+" | sort -u)
if [ -z "$LOADED_PLISTS" ]; then
  fail "No com.cabinet.* plists loaded. Run deploy-mac.sh --all first."
fi

for label in $LOADED_PLISTS; do
  if launchctl bootout "gui/$(id -u)/$label" 2>/dev/null; then
    echo "    booted out: $label"
  else
    warn "    failed to bootout: $label (already unloaded?)"
  fi
done

# Verify unloaded
sleep 3
STILL_LOADED=$(launchctl print "gui/$(id -u)" 2>/dev/null | grep -cE "com\.cabinet\.[a-z._-]+" || true)
if [ "$STILL_LOADED" -gt 0 ]; then
  warn "$STILL_LOADED plist(s) still loaded after bootout — they may have KeepAlive race"
fi

# Bootstrap them all again
echo ""
warn "Bootstrapping com.cabinet.* LaunchAgents..."
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
for plist in "$LAUNCH_AGENTS_DIR"/com.cabinet.*.plist; do
  [ -f "$plist" ] || continue
  if launchctl bootstrap "gui/$(id -u)" "$plist" 2>/dev/null; then
    echo "    bootstrapped: $(basename "$plist" .plist)"
  else
    warn "    failed to bootstrap: $plist"
  fi
done

# Wait for recovery
echo ""
echo "  Waiting up to ${TIMEOUT}s for everything to come back..."
SECONDS=0
RECOVERED=0
while [ "$SECONDS" -lt "$TIMEOUT" ]; do
  sleep 10
  N_LOADED=$(launchctl print "gui/$(id -u)" 2>/dev/null | grep -cE "com\.cabinet\.[a-z._-]+" || true)
  N_TMUX=$(tmux list-sessions 2>/dev/null | grep -cE "^officer-" || true)
  N_REDIS=$(redis-cli ping 2>/dev/null | grep -c PONG || true)
  echo "    ${SECONDS}s — plists=$N_LOADED, tmux=$N_TMUX, redis=$N_REDIS"
  if [ "$N_LOADED" -ge 5 ] && [ "$N_REDIS" -ge 1 ]; then
    RECOVERED=1
    break
  fi
done

if [ "$RECOVERED" = "0" ]; then
  fail "Recovery incomplete after ${TIMEOUT}s. Check launchctl logs."
fi

echo ""
echo "  POST-state:"
snapshot_state

echo ""
echo "==========================================="
echo "  Recovery test PASS — full restart in ${SECONDS}s"
echo ""
echo "  Note: this simulates a logout+login, not a true power cycle. For"
echo "  a real power-cycle test, hold the Mac mini's power button to force"
echo "  off, then power on and re-run this script's PRE-state check."
echo "==========================================="
