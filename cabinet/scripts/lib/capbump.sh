#!/usr/bin/env bash
# capbump.sh — Spec 051 v6 AC #3 + CTO #11 cap-bump anti-abuse Redis counter.
# Sourced by the FW-099 Stripe integration webhook handler and by the FW-101
# customer dashboard cap-bump endpoint when a customer requests a same-day
# spend-cap increase.
#
# WHY REDIS (not state file): the per-cabinet-per-day bump count is a PROXY-side
# concern (server-resident, multi-officer shared state). It must live in the proxy
# Redis, not the customer's local repo files. The cabinet-side implementation here
# mirrors the counter read/increment logic so the billing webhook can authorise
# the charge before calling the proxy admin API to raise the team-budget ceiling.
#
# ANTI-ABUSE RULE (Spec 051 CTO #11):
#   1st bump of the day  → multiplier = 1   (charge base bump fee)
#   2nd+ bumps same day  → multiplier = 2   (double price, anti-abuse)
#
# Counter key: cabinet:capbump:<cabinet-slug>:<yyyy-mm-dd>
# TTL: 48h (auto-expire after 2 days; 7-day retention for audit is FW-097's job).
#
# Redis host/port via env (matches visual-uat-semaphore.sh + post-tool-use.sh
# conventions). Key prefix overridable via CAPBUMP_PREFIX for hermetic testing.
# Fail-safe: Redis unavailable or non-integer result → return multiplier 1 (safe).
# No hardcoded framework paths.

: "${REDIS_HOST:=redis}"
: "${REDIS_PORT:=6379}"
: "${CAPBUMP_PREFIX:=cabinet:capbump}"
: "${CAPBUMP_TTL:=172800}"   # 48h in seconds

_capbump_redis() { redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" "$@" 2>/dev/null; }

# Increment the bump counter for <slug> today and print the new count.
# Returns 0 always; prints "" on Redis failure (caller treats as first bump).
# Usage: _capbump_incr <cabinet-slug> [<date-yyyy-mm-dd>]
_capbump_incr() {
  local slug="${1:?cabinet-slug}" day="${2:-$(date -u +%Y-%m-%d)}"
  local key="${CAPBUMP_PREFIX}:${slug}:${day}" count
  command -v redis-cli >/dev/null 2>&1 || { echo ""; return 0; }
  # INCR then set TTL only if it was just created (NX). Using a pipeline via
  # separate calls is safe — we read the post-incr count and set TTL; a race
  # on TTL is harmless (counter is preserved, just gets extended TTL at worst).
  count="$(_capbump_redis INCR "$key")"
  case "$count" in
    ''|*[!0-9]*) echo ""; return 0 ;;
  esac
  # Set TTL on first bump (EXPIRE is idempotent — re-setting is safe).
  if [ "$count" = "1" ]; then
    _capbump_redis EXPIRE "$key" "$CAPBUMP_TTL" >/dev/null
  fi
  printf '%s' "$count"
  return 0
}

# Print the price multiplier for the NEXT bump for <slug> today.
#   • 1  = first bump of the day (current count is 0 or Redis unavailable)
#   • 2  = second or subsequent bump (current count ≥ 1)
# Does NOT increment the counter — call capbump_record after the Stripe charge
# succeeds to commit the bump.
# Usage: capbump_multiplier <cabinet-slug> [<date-yyyy-mm-dd>]
capbump_multiplier() {
  local slug="${1:?cabinet-slug}" day="${2:-$(date -u +%Y-%m-%d)}"
  local key="${CAPBUMP_PREFIX}:${slug}:${day}" count
  command -v redis-cli >/dev/null 2>&1 || { echo "1"; return 0; }
  count="$(_capbump_redis GET "$key")"
  # Treat missing key (nil), empty, or non-numeric as 0 (first bump)
  case "$count" in
    ''|nil|*[!0-9]*) count=0 ;;
  esac
  if [ "$count" -ge 1 ]; then
    echo "2"
  else
    echo "1"
  fi
  return 0
}

# Record a completed bump (increment counter + set TTL). Call AFTER the Stripe
# one-shot charge succeeds. Prints the new count; prints "" on Redis failure.
# Usage: capbump_record <cabinet-slug> [<date-yyyy-mm-dd>]
capbump_record() {
  local slug="${1:?cabinet-slug}" day="${2:-$(date -u +%Y-%m-%d)}"
  _capbump_incr "$slug" "$day"
  return 0
}
