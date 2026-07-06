#!/usr/bin/env bash
# diagnose-calendar-tcc.sh — SAFE transient-LaunchAgent probe that answers the
# UNPROVEN question: does the launchd officer chain get calendar fullAccess, or is
# it silently denied (or does a modal wait for a user at the screen)?
#
# It bootstraps a ONE-SHOT LaunchAgent with a UNIQUE per-run label that runs the
# signed helper's `probe` (side-effect-free authorizationStatus read) under the
# SAME launchd → bash → helper attribution chain the officers use, captures the
# exit code + the tccd decision from the unified log, then self-cleans (bootout +
# rm) on ANY exit/interrupt via trap. The unique label means a failed bootout can
# never collide with the real fleet.
#
# Run this in Nate's granted context to reconcile the two in-tension facts
# (Terminal-works vs rebuild-invalidates). From a write-only background context it
# will report writeOnly/denied — expected, not a bug.
set -uo pipefail

ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
HELPER="${CABINET_CAL_HELPER:-$ROOT/bin/cabinet-calread}"
UID_NUM="$(id -u)"
LABEL="com.cabinet.calread.tcc-probe.$$-$(date +%s)"
WORK="$(mktemp -d)"
PLIST="$WORK/$LABEL.plist"
RESULT="$WORK/result.txt"

cleanup() {
  launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
  rm -rf "$WORK" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

if [ ! -x "$HELPER" ]; then
  echo "helper not built/executable at $HELPER — build it first" >&2
  exit 2
fi

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>"$HELPER" probe > "$RESULT" 2>&1; echo "exit=\$?" >> "$RESULT"</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>AbandonProcessGroup</key><true/>
</dict>
</plist>
PLIST

echo "[diagnose] bootstrapping transient LaunchAgent $LABEL"
launchctl bootstrap "gui/$UID_NUM" "$PLIST" 2>/dev/null || true
launchctl kickstart -k "gui/$UID_NUM/$LABEL" 2>/dev/null || true

# Poll the result file up to ~20s.
for _ in $(seq 1 20); do
  [ -s "$RESULT" ] && break
  sleep 1
done

echo "--- probe result (launchd → bash → helper chain) ---"
if [ -s "$RESULT" ]; then
  cat "$RESULT"
  code="$(grep -o 'exit=[0-9]*' "$RESULT" | tail -1 | cut -d= -f2)"
  case "$code" in
    0) echo "VERDICT: GRANTED headless — the officer chain gets fullAccess." ;;
    5) echo "VERDICT: WRITE-ONLY headless — read/delete refuse; undo unavailable there." ;;
    3|4) echo "VERDICT: SILENT DENY (no prompt) — expected pre-grant headless state." ;;
    *) echo "VERDICT: inconclusive (exit=$code)." ;;
  esac
else
  echo "no result within 20s — likely a TCC hang or a modal waiting for a user at the screen."
  echo "Check for a waiting prompt:  log show --last 2m --predicate 'subsystem == \"com.apple.TCC\"' --info | grep -i prompt"
fi

echo "--- recent tccd decisions for Calendar (kTCCServiceCalendar) ---"
log show --last 2m --predicate 'subsystem == "com.apple.TCC"' --info 2>/dev/null \
  | grep -i "calendar\|kTCCServiceCalendar" | tail -20 || true
