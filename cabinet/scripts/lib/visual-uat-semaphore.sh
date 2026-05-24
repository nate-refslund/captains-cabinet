#!/usr/bin/env bash
# visual-uat-semaphore.sh — Spec 049 AC #13 (M2 real crash-safe semaphore).
# Sourced by the Gate-4 stagehand-runner to cap concurrent Chromium/CDP runs at
# agent_caps.visual_uat_concurrent (default 2).
#
# WHY NOT BLPOP (M2): BLPOP is a queue primitive, not a mutex — a crashed holder
# never returns its token, leaking a permit forever. Instead: N per-permit keys via
# `SET key <owner> NX EX <ttl>`. The TTL makes it crash-safe BY CONSTRUCTION — a
# holder that dies mid-run lets its permit auto-expire; no leak, no manual reap.
#
# Release + renew are OWNER-CHECKED + ATOMIC (redis EVAL): a holder whose TTL lapsed
# and whose slot was retaken by a NEW owner must NOT delete the new owner's permit
# (the GET==owner-then-DEL race) — the Lua check-and-del closes that.
#
# MF-5 (permit held ONLY during active Chromium/CDP work) is the RUNNER's
# responsibility: it calls vuat_sem_release before the AC #4 preview-availability
# poll AND the cost-cap officer-decision wait (both unbounded/human-latency), then
# re-acquires on resume — so a stuck holder can't starve the pool for minutes. This
# lib provides the acquire/release/renew primitives; the runner places them.
#
# No hardcoded paths; Redis host/port via env (matches post-tool-use.sh conventions).
# Permit-key prefix overridable via VUAT_SEM_PREFIX (hermetic testing).

: "${REDIS_HOST:=redis}"
: "${REDIS_PORT:=6379}"
: "${VUAT_SEM_PREFIX:=cabinet:visual-uat:slot}"

_vuat_redis() { redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" "$@" 2>/dev/null; }

# Acquire one free permit out of <max_slots>. Prints the acquired slot key + returns 0;
# returns 1 if all permits are taken (caller waits/retries up to the lock-wait timeout).
# Usage: vuat_sem_acquire <max_slots> <owner> <ttl_seconds>
vuat_sem_acquire() {
  local max="${1:?max_slots}" owner="${2:?owner}" ttl="${3:?ttl}" i key res
  command -v redis-cli >/dev/null 2>&1 || return 1
  for (( i=1; i<=max; i++ )); do
    key="${VUAT_SEM_PREFIX}:${i}"
    res="$(_vuat_redis SET "$key" "$owner" NX EX "$ttl")"
    if [ "$res" = "OK" ]; then echo "$key"; return 0; fi
  done
  return 1
}

# Release a permit — ONLY if still owned by <owner> (atomic check-and-del). Idempotent;
# always returns 0 (releasing an already-expired/retaken permit is a safe no-op).
# Usage: vuat_sem_release <slot_key> <owner>
vuat_sem_release() {
  local key="${1:?slot_key}" owner="${2:?owner}"
  _vuat_redis EVAL \
    "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) else return 0 end" \
    1 "$key" "$owner" >/dev/null
  return 0
}

# Extend a held permit's TTL — only if still owned. Returns 0 if renewed, 1 if the
# permit was lost (expired + retaken, or never held). The runner renews before a TTL
# would lapse during a legitimately long active hold.
# Usage: vuat_sem_renew <slot_key> <owner> <ttl_seconds>
vuat_sem_renew() {
  local key="${1:?slot_key}" owner="${2:?owner}" ttl="${3:?ttl}" r
  r="$(_vuat_redis EVAL \
    "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('EXPIRE', KEYS[1], ARGV[2]) else return 0 end" \
    1 "$key" "$owner" "$ttl")"
  [ "$r" = "1" ] && return 0 || return 1
}
