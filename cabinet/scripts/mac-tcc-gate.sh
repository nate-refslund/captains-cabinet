#!/bin/bash
# mac-tcc-gate.sh - hard gate for Mac TCC/code-signing readiness.

set -euo pipefail

JSON=0
if [ "${1:-}" = "--json" ]; then
  JSON=1
elif [ $# -gt 0 ]; then
  echo "Usage: mac-tcc-gate.sh [--json]" >&2
  exit 64
fi

TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

add_check() {
  printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$TMP"
}

if [ "$(uname -s)" != "Darwin" ]; then
  add_check "platform" warn "not macOS; TCC permission persistence must be verified on the Mac mini"
else
  add_check "platform" pass "macOS"
fi

for binary in claude cua-driver; do
  if ! command -v "$binary" >/dev/null 2>&1; then
    add_check "$binary" fail "missing"
    continue
  fi
  path="$(command -v "$binary")"
  if command -v codesign >/dev/null 2>&1 && codesign --verify --deep --strict "$path" >/dev/null 2>&1; then
    add_check "$binary-codesign" pass "$path"
  else
    add_check "$binary-codesign" fail "$path is not verifiably code-signed"
  fi
done

add_check "manual-accessibility" warn "grant Accessibility to claude/cua-driver/officer launcher, reboot, then confirm grants persist"
add_check "manual-screen-recording" warn "grant Screen Recording to screenpipe and cua-driver, reboot, then confirm grants persist"
add_check "manual-full-disk-access" warn "grant Full Disk Access to claude and cua-driver, reboot, then confirm grants persist"

if [ "$JSON" = "1" ]; then
  python3 - "$TMP" <<'PY'
import json
import sys
from pathlib import Path

checks = []
for line in Path(sys.argv[1]).read_text().splitlines():
    name, status, detail = line.split("\t", 2)
    checks.append({"name": name, "status": status, "detail": detail})
print(json.dumps({"checks": checks}, indent=2, sort_keys=True))
PY
else
  while IFS=$'\t' read -r name status detail; do
    printf '%-28s %-5s %s\n' "$name" "$status" "$detail"
  done < "$TMP"
fi

if grep -q $'\tfail\t' "$TMP"; then
  exit 1
fi
