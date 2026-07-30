#!/usr/bin/env bash
# build-companion.sh — compile + assemble + ad-hoc-sign the Cabinet menu-bar
# companion ("bin/Cabinet Companion.app") on-target. Wave D / D1, spec:
# DESIGN-companion-2026-07-10.md §3/§9. Clone of the shipped
# build-calendar-helper.sh precedent (swiftc on-target, codesign --sign -),
# extended from bare-binary to an LSUIElement .app bundle.
#
# Source:  cabinet/companion/main.swift + cabinet/companion/pet.swift
#          + cabinet/companion/Info.plist
# Output:  $ROOT/bin/Cabinet Companion.app   (gitignored — never enters git
#          HEAD, so it never rides the egg; the egg ships SOURCE + this script)
#
# Signing posture (§9): ad-hoc (`codesign --sign -`) with the STABLE identifier
# com.cabinet.companion (keys notifications/defaults/login-item identity).
# A locally built bundle carries no com.apple.quarantine xattr, so Gatekeeper
# never intervenes — no prompt, no Apple account, $0. Developer ID +
# notarization is OC-3, Captain-gated, deferred to the stranger-download
# milestone. Unlike cabinet-calread this app touches no TCC-gated framework,
# so a rebuild costs no re-grant.
#
# Run it:   bash cabinet/scripts/build-companion.sh
# Then:     open "$ROOT/bin/Cabinet Companion.app"        (menu bar only)
# Headless: "$ROOT/bin/Cabinet Companion.app/Contents/MacOS/cabinet-companion" --smoke
set -euo pipefail

ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
SRC_DIR="$ROOT/cabinet/companion"
SRC="$SRC_DIR/main.swift"
# pet.swift is the desk pet's BODY (floating window beside the Dock); main.swift
# stays the brain. Both compile into the ONE binary — the pet adds no target,
# no dependency and no daemon.
PET="$SRC_DIR/pet.swift"
PLIST="$SRC_DIR/Info.plist"
APP="$ROOT/bin/Cabinet Companion.app"
MACOS_DIR="$APP/Contents/MacOS"
OUT="$MACOS_DIR/cabinet-companion"
IDENTIFIER="com.cabinet.companion"

if ! command -v swiftc >/dev/null 2>&1; then
  echo "error: swiftc not found (needs Xcode Command Line Tools; macOS only)" >&2
  exit 1
fi
[ -f "$SRC" ] || { echo "error: missing source $SRC" >&2; exit 1; }
[ -f "$PET" ] || { echo "error: missing source $PET" >&2; exit 1; }
[ -f "$PLIST" ] || { echo "error: missing $PLIST" >&2; exit 1; }

# fail early on a malformed plist (the bundle would be silently broken)
plutil -lint "$PLIST" >/dev/null

mkdir -p "$MACOS_DIR"
cp "$PLIST" "$APP/Contents/Info.plist"
swiftc -O "$SRC" "$PET" -o "$OUT"
codesign --force --sign - --identifier "$IDENTIFIER" "$APP"

echo "built + signed: $APP"
codesign -dv "$APP" 2>&1 | sed -n '1,4p' || true
echo
echo "smoke:  \"$OUT\" --smoke        (headless one-shot; prints STATE=… reason=…)"
echo "run:    open \"$APP\"           (menu-bar only — LSUIElement, no Dock icon)"
echo "login item stays OFF until enabled from the menu (SMAppService, opt-in)."
