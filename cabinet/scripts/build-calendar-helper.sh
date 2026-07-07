#!/usr/bin/env bash
# Build + ad-hoc-sign the signed EventKit calendar helper (cabinet-calread),
# the Apple Calendar provider substrate for the calendar action lane. macOS-only
# (needs swiftc + EventKit).
#
# ONE CONSOLIDATED binary, dispatched on argv[1] (2026-07-06 — batched so there is
# exactly ONE rebuild and ONE TCC re-grant across all the calendar follow-ups):
#   read <start> <end>   — double-book gather (now emits EVERY event tagged
#                          all_day + availability; the all-day/free-vs-busy POLICY
#                          lives in calendar_read.py, not this binary)
#   delete <cal> <uid>   — fast confirmed-only reverse/undo (the AppleScript
#                          whose-uid delete stays as the authoritative fallback)
#   calinfo <cal>        — real per-calendar EventKit attributes for the F1
#                          real-sharees pre-write gate
#   probe                — authorizationStatus only, for the officer boot self-check
#
# Output: $CABINET_ROOT/bin/cabinet-calread  (gitignored; calendar_read.py /
# calendar_delete.py resolve it via $CABINET_CAL_HELPER else <root>/bin/cabinet-calread).
#
# First run of the built binary triggers a macOS Calendar permission prompt —
# grant FULL ACCESS (read AND delete AND calinfo need it; probe reads status only).
# The ad-hoc signature keys the TCC grant to the binary's CDHASH, so a rebuild
# (ANY source change) re-keys it and needs a ONE-TIME re-grant that covers ALL
# subcommands at once. A STABLE signing identity (Developer ID Application, or even
# a reused self-signed Code Signing cert) would key the grant to the code's
# Designated Requirement instead, so the grant would SURVIVE rebuilds — see
# docs/runbooks/calendar-officer-grant.md. This box currently has zero signing
# identities (`security find-identity -p codesigning`), so ad-hoc is the fallback.
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
echo "NEXT: run it once and grant FULL calendar access at the prompt (one re-grant"
echo "covers read + delete + calinfo; probe reads status only):"
echo "  $OUT read \"\$(date +%Y-%m-%dT00:00:00)\" \"\$(date -v+1d +%Y-%m-%dT00:00:00)\""
echo "then smoke the other subcommands (see instance/archive/proposals/calendar-followups-runbook-2026-07-06.md):"
echo "  $OUT calinfo Home     # expect found:true, writable:true, shared:false, shared_signal:none"
echo "  $OUT probe            # expect exit 0 (fullAccess) in a granted context"
echo "(ad-hoc signature: a rebuild changes the cdhash and needs a one-time re-grant.)"
