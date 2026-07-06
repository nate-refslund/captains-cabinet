#!/usr/bin/env bash
# Build + ad-hoc-sign the read-only EventKit calendar helper (cabinet-calread),
# the Apple Calendar provider substrate for the double-book gather
# (framework/frontdoor/calendar_read.py). macOS-only (needs swiftc + EventKit).
#
# Output: $CABINET_ROOT/bin/cabinet-calread  (gitignored; calendar_read.py resolves
# it via $CABINET_CAL_HELPER else <root>/bin/cabinet-calread).
#
# First run of the built binary triggers a macOS Calendar permission prompt —
# grant FULL ACCESS. The ad-hoc signature keys the TCC grant to the binary's
# cdhash, so a rebuild (any source change) needs a one-time re-grant.
set -euo pipefail

ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
HELPER_DIR="$ROOT/framework/frontdoor/calread_helper"
SRC="$HELPER_DIR/calread.swift"
PLIST="$HELPER_DIR/Info.plist"
OUT_DIR="$ROOT/bin"
OUT="$OUT_DIR/cabinet-calread"

if ! command -v swiftc >/dev/null 2>&1; then
  echo "error: swiftc not found (needs Xcode Command Line Tools; macOS only)" >&2
  exit 1
fi
[ -f "$SRC" ] || { echo "error: missing source $SRC" >&2; exit 1; }
[ -f "$PLIST" ] || { echo "error: missing $PLIST" >&2; exit 1; }

mkdir -p "$OUT_DIR"
swiftc "$SRC" -o "$OUT" \
  -framework EventKit -framework Foundation \
  -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker "$PLIST"
codesign --force --sign - --identifier com.cabinet.calread "$OUT"

echo "built + signed: $OUT"
codesign -dv "$OUT" 2>&1 | sed -n '1,3p' || true
echo
echo "NEXT: run it once and grant FULL calendar access at the prompt:"
echo "  $OUT read \"\$(date +%Y-%m-%dT00:00:00)\" \"\$(date -v+1d +%Y-%m-%dT00:00:00)\""
echo "(ad-hoc signature: a rebuild changes the cdhash and needs a one-time re-grant.)"
