#!/bin/bash
# mac-preflight.sh - host readiness checks for Mac-native Cabinet activation.

set -euo pipefail

JSON=0
if [ "${1:-}" = "--json" ]; then
  JSON=1
elif [ $# -gt 0 ]; then
  echo "Usage: mac-preflight.sh [--json]" >&2
  exit 64
fi

if [ -z "${CABINET_ROOT:-}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  CABINET_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi

TMP="$(mktemp)"
DRY_OUT="$(mktemp)"
DRY_ERR="$(mktemp)"
trap 'rm -f "$TMP" "$DRY_OUT" "$DRY_ERR"' EXIT

add_check() {
  local name="$1" status="$2" detail="$3"
  printf '%s\t%s\t%s\n' "$name" "$status" "$detail" >> "$TMP"
}

need_cmd() {
  local cmd="$1"
  if command -v "$cmd" >/dev/null 2>&1; then
    add_check "$cmd" pass "$(command -v "$cmd")"
  else
    add_check "$cmd" fail "missing"
  fi
}

for cmd in brew node npm claude git gh jq python3 redis-cli pg_dump tmux launchctl; do
  need_cmd "$cmd"
done

if command -v claude >/dev/null 2>&1; then
  add_check "claude-version" pass "$(claude --version 2>/dev/null || echo unknown)"
  if claude --help 2>&1 | grep -q -- '--agent'; then
    add_check "claude-native-agent" pass "--agent supported"
  else
    add_check "claude-native-agent" warn "--agent not advertised; officer launch will use boot prompt fallback"
  fi
fi

if command -v redis-cli >/dev/null 2>&1 && redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" ping >/dev/null 2>&1; then
  add_check "redis-ping" pass "PONG"
  appendonly="$(redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" CONFIG GET appendonly 2>/dev/null | tail -1 || true)"
  if [ "$appendonly" = "yes" ]; then
    add_check "redis-aof" pass "appendonly yes"
  else
    add_check "redis-aof" fail "appendonly=$appendonly"
  fi
else
  add_check "redis-ping" fail "not reachable at ${REDIS_HOST:-localhost}:${REDIS_PORT:-6379}"
fi

if command -v pg_dump >/dev/null 2>&1; then
  # pg_dump version check: accept >= 17 (Neon currently runs PG 17). pg_dump
  # is generally forward-compatible: pg_dump 18.x → PG 17 server works in
  # practice, so we don't pin to exactly 17.
  PGD_MAJOR="$(pg_dump --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1 | cut -d. -f1)"
  if [ -n "$PGD_MAJOR" ] && [ "$PGD_MAJOR" -ge 17 ]; then
    add_check "pg_dump" pass "$(pg_dump --version)"
  else
    add_check "pg_dump" fail "$(pg_dump --version 2>/dev/null || echo unknown) (need >= 17)"
  fi
fi

if command -v gh >/dev/null 2>&1; then
  if gh auth status >/dev/null 2>&1; then
    add_check "gh-auth" pass "authenticated"
  else
    add_check "gh-auth" fail "not authenticated"
  fi
fi

if [ -f "$CABINET_ROOT/.mcp.json.mac-native" ]; then
  add_check "mcp-mac-native" pass ".mcp.json.mac-native present"
else
  add_check "mcp-mac-native" fail ".mcp.json.mac-native missing"
fi

if CABINET_SOURCE_REPO="$CABINET_ROOT" bash "$CABINET_ROOT/cabinet/scripts/deploy-mac.sh" --officer cos --dry-run >"$DRY_OUT" 2>"$DRY_ERR"; then
  add_check "launchd-render" pass "officer plist dry-run rendered"
else
  add_check "launchd-render" fail "$(tr '\n' ' ' <"$DRY_ERR" | cut -c1-180)"
fi

active_slug="$(tr -d '[:space:]' < "$CABINET_ROOT/instance/config/active-project.txt" 2>/dev/null || true)"
if [ -n "$active_slug" ] && [ -f "$CABINET_ROOT/instance/config/projects/$active_slug.yml" ]; then
  add_check "active-project-config" pass "$active_slug"
  mount_path="$(awk '/^[[:space:]]*mount_path:/ {print $2; exit}' "$CABINET_ROOT/instance/config/projects/$active_slug.yml")"
  if [ -n "$mount_path" ] && [ -e "$mount_path" ]; then
    add_check "active-project-mount" pass "$mount_path"
  else
    add_check "active-project-mount" warn "${mount_path:-missing mount_path} not present on this host"
  fi
else
  add_check "active-project-config" fail "active project config missing"
fi

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
    printf '%-24s %-5s %s\n' "$name" "$status" "$detail"
  done < "$TMP"
fi

if grep -q $'\tfail\t' "$TMP"; then
  exit 1
fi
