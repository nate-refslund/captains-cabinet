#!/bin/bash
# appshell-gate.sh — acceptance gate for the Hatch app shell (HATCH-APPSHELL-V05, spec 8).
#
# Scratch-dir only; the repo is treated READ-ONLY. Exit 0 = gate PASS.
#   (a) fresh egg cut + (b) .app build — build-hatch-app.sh (cuts its own fresh egg)
#   (c) structure + signature + payload-hash asserts
#   (d) headless stub smoke (HATCH_APP_SMOKE=1): unpack + engine --dry-run --defaults
#   (e) pytest cabinet/scripts/tests/test_appshell_build.py
#   (f) claims-lint over the runbook + every appshell source
#
# Usage: bash cabinet/scripts/appshell/appshell-gate.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RUNBOOK="$REPO_ROOT/docs/runbooks/hatch-appshell-v05-2026-07-10.md"

SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/appshell-gate.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT

step() { printf '\n[appshell-gate] %s\n' "$*"; }

step "(a+b) fresh egg cut + .app build"
bash "$SCRIPT_DIR/build-hatch-app.sh" --out "$SCRATCH/dist"

APP="$SCRATCH/dist/Hatch Cabinet.app"

step "(c) structure + signature + payload-hash asserts"
[ -x "$APP/Contents/MacOS/HatchCabinet" ] || { echo "gate: stub executable missing" >&2; exit 1; }
[ -f "$APP/Contents/Resources/payload/cabinet-egg.zip" ] || { echo "gate: payload zip missing" >&2; exit 1; }
[ -f "$APP/Contents/Resources/payload/payload-info.json" ] || { echo "gate: payload-info.json missing" >&2; exit 1; }
[ -x "$APP/Contents/Resources/hatch-run.command" ] || { echo "gate: runner missing or not executable" >&2; exit 1; }
/usr/bin/plutil -lint "$APP/Contents/Info.plist"
/usr/bin/codesign --verify --strict "$APP"
ZIP_SHA="$(/usr/bin/shasum -a 256 "$APP/Contents/Resources/payload/cabinet-egg.zip" | awk '{print $1}')"
INFO_SHA="$(python3.12 -c 'import json,sys; print(json.load(open(sys.argv[1]))["payload_sha256"])' \
  "$APP/Contents/Resources/payload/payload-info.json")"
[ "$ZIP_SHA" = "$INFO_SHA" ] || { echo "gate: payload sha mismatch: zip=$ZIP_SHA info=$INFO_SHA" >&2; exit 1; }
echo "payload sha256 verified: $ZIP_SHA"

step "(d) headless stub smoke (engine dry-run on the export bytes)"
HATCH_APP_SMOKE=1 CABINET_HATCH_PREFIX="$SCRATCH/prefix" "$APP/Contents/MacOS/HatchCabinet"

step "(e) pytest"
python3.12 -m pytest "$REPO_ROOT/cabinet/scripts/tests/test_appshell_build.py" -q

step "(f) claims-lint (runbook + appshell sources)"
bash "$SCRIPT_DIR/claims-lint.sh" "$RUNBOOK" "$SCRIPT_DIR"/*

step "PASS"
