#!/usr/bin/env bash
# Atomic INCR with TTL preservation — wraps incr-with-ttl.lua.
#
# Source this from bash scripts that need race-safe daily counters:
#   . /opt/founders-cabinet/cabinet/scripts/lib/incr-counter.sh
#   incr_counter "cabinet:cost:tokens:daily:$(date -u +%Y-%m-%d)" 86400 100
#
# Or call directly:
#   /opt/founders-cabinet/cabinet/scripts/lib/incr-counter.sh <key> <ttl> [<incr>]
#
# Returns: the new counter value (stdout). Exit code 0 on success.

LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LUA_SCRIPT="$LIB_DIR/incr-with-ttl.lua"
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"

incr_counter() {
  local key="$1"
  local ttl="${2:?ttl_seconds required}"
  local incr="${3:-1}"

  if [ -z "$key" ]; then
    echo "ERROR: incr_counter <key> <ttl_sec> [<incr_amount>]" >&2
    return 2
  fi

  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
    EVAL "$(cat "$LUA_SCRIPT")" 1 "$key" "$ttl" "$incr"
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  incr_counter "$@"
fi
