#!/bin/bash
# build-hatch-app.sh — build "Hatch Cabinet.app" (thin shell v0.6.0, HATCH-APPSHELL-V05).
#
# Dev-Mac tool: cuts a FRESH egg via egg-export.sh (never ships this working
# tree), zips it into the bundle payload, compiles the single-file Swift stub
# (swiftc from the Command Line Tools — the hatch target never compiles
# anything), assembles the bundle, ad-hoc signs it, and verifies it. The repo
# is treated read-only; every output lands under --out (outside the repo).
#
# The built .app is PRIVATE-SIDE PREP: CG-7 blocks all publishing; the CG-5
# distribution-vehicle ruling is surfaced in the spec, not bypassed here.
set -euo pipefail

usage() {
  cat <<'EOF'
build-hatch-app.sh — build "Hatch Cabinet.app" from a fresh egg cut

Usage:
  bash cabinet/scripts/appshell/build-hatch-app.sh [--out DIR] [--force]

  --out DIR   output dir for "Hatch Cabinet.app" (created if absent; must be
              OUTSIDE the repo). Default: a fresh mktemp dir, printed.
  --force     replace an existing "Hatch Cabinet.app" under --out.
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
APP_VERSION="0.6.0"

OUT_ARG=""
FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --out) [ $# -ge 2 ] || { echo "build-hatch-app: --out needs a value" >&2; exit 2; }; OUT_ARG="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "build-hatch-app: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
  esac
done

if [ -z "$OUT_ARG" ]; then
  OUT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/hatch-app.XXXXXX")"
else
  mkdir -p "$OUT_ARG"
  OUT_DIR="$(cd "$OUT_ARG" && pwd)"
fi
case "$OUT_DIR/" in
  "$REPO_ROOT"/*) echo "build-hatch-app: --out must be OUTSIDE the repo ($REPO_ROOT)" >&2; exit 2 ;;
esac

APP="$OUT_DIR/Hatch Cabinet.app"
if [ -e "$APP" ]; then
  [ "$FORCE" = "1" ] || { echo "build-hatch-app: $APP exists (use --force to replace)" >&2; exit 2; }
  rm -rf "$APP"
fi

command -v git >/dev/null 2>&1 || { echo "build-hatch-app: git required (egg cut + provenance)" >&2; exit 3; }
xcrun -f swiftc >/dev/null 2>&1 || { echo "build-hatch-app: swiftc not found — install the Command Line Tools (dev-Mac builder; the hatch target never compiles anything)" >&2; exit 3; }
command -v python3.12 >/dev/null 2>&1 || { echo "build-hatch-app: python3.12 required (payload-info.json)" >&2; exit 3; }

SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/hatch-app-build.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT

step() { printf '\n[build-hatch-app] %s\n' "$*"; }

step "(1/6) fresh egg cut (egg-export.sh --out, from a pristine clone of HEAD)"
SOURCE_HEAD="$(git -C "$REPO_ROOT" rev-parse HEAD)"
SOURCE_BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
# Cut from a scratch clone pinned to HEAD: the manifest AND the tree both
# come from HEAD, so parallel-wave working-tree edits (e.g. expect-present
# rows for files not yet committed) can neither skew nor fail the cut.
# Fresh-cut doctrine: never ship — or read packaging state from — this
# working tree. The clone is read-only toward the source repo.
git clone -q "$REPO_ROOT" "$SCRATCH/src"
git -C "$SCRATCH/src" checkout -q "$SOURCE_HEAD"
if ! bash "$SCRATCH/src/cabinet/scripts/egg-export.sh" --out "$SCRATCH/egg" >"$SCRATCH/egg-export.log" 2>&1; then
  tail -20 "$SCRATCH/egg-export.log" >&2
  echo "build-hatch-app: egg export failed (full log was in scratch)" >&2
  exit 1
fi
tail -2 "$SCRATCH/egg-export.log" || true
[ -f "$SCRATCH/egg/cabinet/scripts/hatch.sh" ] || { echo "build-hatch-app: egg cut is missing cabinet/scripts/hatch.sh" >&2; exit 1; }
EGG_FILES="$(find "$SCRATCH/egg" -type f | wc -l | tr -d ' ')"

step "(2/6) zip payload (ditto -c -k)"
/usr/bin/ditto -c -k "$SCRATCH/egg" "$SCRATCH/cabinet-egg.zip"

step "(3/6) assemble bundle skeleton + render templates"
CONTENTS="$APP/Contents"
mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Resources/payload"
BUILD_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
BUNDLE_VERSION="$(date -u +%Y%m%d.%H%M%S)"
# APP_VERSION is templated too (2026-08-25): it used to be a literal in
# Info.plist.in AND a variable here, and the two drifted the moment one moved.
sed -e "s/@BUNDLE_VERSION@/$BUNDLE_VERSION/g" -e "s/@BUILD_UTC@/$BUILD_UTC/g" \
    -e "s/@APP_VERSION@/$APP_VERSION/g" \
  "$SCRIPT_DIR/Info.plist.in" > "$CONTENTS/Info.plist"
sed -e "s/@APP_VERSION@/$APP_VERSION/g" -e "s/@BUILD_UTC@/$BUILD_UTC/g" \
  "$SCRIPT_DIR/hatch-run.command.in" > "$CONTENTS/Resources/hatch-run.command"
chmod 0755 "$CONTENTS/Resources/hatch-run.command"
bash -n "$CONTENTS/Resources/hatch-run.command"
# The app carries the everyday opener and the probe lib too — the SAME bytes
# the egg ships, taken from the cut rather than from this working tree. They
# are what lets the app open a Cabinet that was set up before the opener
# existed (dropped at the TOP of the install, never into cabinet/scripts/).
for pair in "cabinet/scripts/open-cabinet.sh:open-cabinet.sh" \
            "cabinet/scripts/lib/dashboard.sh:lib-dashboard.sh"; do
  src="$SCRATCH/egg/${pair%%:*}"
  [ -f "$src" ] || { echo "build-hatch-app: the egg cut is missing ${pair%%:*}" >&2; exit 1; }
  cp "$src" "$CONTENTS/Resources/${pair##*:}"
  chmod 0755 "$CONTENTS/Resources/${pair##*:}"
  bash -n "$CONTENTS/Resources/${pair##*:}"
done

step "(4/6) compile stub (swiftc, ad-hoc linker signature)"
swiftc -O "$SCRIPT_DIR/main.swift" -o "$CONTENTS/MacOS/HatchCabinet"

step "(5/6) payload + payload-info.json"
cp "$SCRATCH/cabinet-egg.zip" "$CONTENTS/Resources/payload/cabinet-egg.zip"
PAYLOAD_SHA="$(/usr/bin/shasum -a 256 "$CONTENTS/Resources/payload/cabinet-egg.zip" | awk '{print $1}')"
# Provenance describes the ACTUAL cut: the manifest as of HEAD (the clone's).
MANIFEST_SHA="$(/usr/bin/shasum -a 256 "$SCRATCH/src/cabinet/scripts/egg-export-manifest.txt" | awk '{print $1}')"
PAYLOAD_SHA="$PAYLOAD_SHA" MANIFEST_SHA="$MANIFEST_SHA" SOURCE_HEAD="$SOURCE_HEAD" \
SOURCE_BRANCH="$SOURCE_BRANCH" BUILD_UTC="$BUILD_UTC" APP_VERSION="$APP_VERSION" \
EGG_FILES="$EGG_FILES" \
python3.12 - "$CONTENTS/Resources/payload/payload-info.json" <<'PYEOF'
import json, os, sys
info = {
    "app_version": os.environ["APP_VERSION"],
    "built_utc": os.environ["BUILD_UTC"],
    "source_head": os.environ["SOURCE_HEAD"],
    "source_branch": os.environ["SOURCE_BRANCH"],
    "egg_manifest_sha256": os.environ["MANIFEST_SHA"],
    "payload_sha256": os.environ["PAYLOAD_SHA"],
    "egg_file_count": int(os.environ["EGG_FILES"]),
}
with open(sys.argv[1], "w") as f:
    json.dump(info, f, indent=2, sort_keys=True)
    f.write("\n")
PYEOF

step "(6/6) ad-hoc sign + verify"
/usr/bin/codesign --force --sign - "$APP"
/usr/bin/plutil -lint "$CONTENTS/Info.plist"
/usr/bin/codesign --verify --strict "$APP"
/usr/bin/codesign -dv "$APP" 2>&1 | sed -n '1,4p'

step "bundle structure"
find "$APP" | sed "s|$OUT_DIR/||" | sort

printf '\n[build-hatch-app] OK — %s\n' "$APP"
printf '[build-hatch-app] payload: %s files, sha256 %s\n' "$EGG_FILES" "$PAYLOAD_SHA"
printf '[build-hatch-app] source:  %s @ %s\n' "$SOURCE_BRANCH" "$SOURCE_HEAD"
