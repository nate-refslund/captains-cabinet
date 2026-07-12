#!/bin/bash
# kill-switch.sh — Emergency halt / resume for all Officers
# Usage: kill-switch.sh activate | deactivate | status
#
# FAIL-CLOSED CONTRACT (2026-07-11 hardening-loop finding, ceremony patch):
# an emergency surface must never report success it cannot prove, and never
# report safe-to-proceed when the control plane is unreachable.
#   activate   — SET is rc-checked AND read back; anything short of a
#                verified "active" prints FAILURE to stderr and exits 1.
#   deactivate — DEL rc-checked + read-back proves the key is gone.
#   status     — control plane unreachable => "UNKNOWN … treat as ACTIVE"
#                and exit 2 (never a false INACTIVE; callers gate on rc 0).
#   default    — 127.0.0.1, not the docker-DNS name `redis` (the same
#                gotcha pre-tool-use.sh:18-21 already guards hook-side;
#                the env-derived host still honors REDIS_URL overrides).

REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379}"
REDIS_HOST=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
REDIS_PORT=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)
# docker-legacy residue guard (mirrors cabinet-doctor.sh): a bare `redis`
# hostname never resolves on the Mac-native fleet.
[ "$REDIS_HOST" = "redis" ] && REDIS_HOST=127.0.0.1

ACTION="${1:?Usage: kill-switch.sh activate|deactivate|status}"

case "$ACTION" in
  activate)
    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET cabinet:killswitch active > /dev/null 2>&1 \
       && [ "$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET cabinet:killswitch 2>/dev/null)" = "active" ]; then
      echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') — KILL SWITCH ACTIVATED (verified by read-back)"
      echo "All Officer operations will halt on their next tool invocation."
    else
      echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') — KILL SWITCH ACTIVATION FAILED: control plane at ${REDIS_HOST}:${REDIS_PORT} unreachable or write unverified." >&2
      echo "Officers are NOT provably halted. Escalate: stop launchd jobs directly (launchctl bootout) or fix Redis, then re-run." >&2
      exit 1
    fi
    ;;
  deactivate)
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DEL cabinet:killswitch > /dev/null 2>&1
    if [ -z "$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET cabinet:killswitch 2>/dev/null)" ] \
       && redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" PING > /dev/null 2>&1; then
      echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') — KILL SWITCH DEACTIVATED (verified by read-back)"
      echo "Officers will resume normal operation."
    else
      echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') — KILL SWITCH DEACTIVATION UNVERIFIED: control plane at ${REDIS_HOST}:${REDIS_PORT} unreachable." >&2
      echo "The switch may still be ACTIVE. Fix Redis, then re-run." >&2
      exit 1
    fi
    ;;
  status)
    if ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" PING > /dev/null 2>&1; then
      echo "Kill switch: UNKNOWN — control plane at ${REDIS_HOST}:${REDIS_PORT} unreachable (fail-closed: treat as ACTIVE for gating purposes)"
      exit 2
    fi
    STATE=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET cabinet:killswitch 2>/dev/null)
    if [ "$STATE" = "active" ]; then
      echo "Kill switch: ACTIVE (all operations halted)"
    else
      echo "Kill switch: INACTIVE (normal operation)"
    fi
    ;;
  *)
    echo "Usage: kill-switch.sh activate|deactivate|status"
    exit 1
    ;;
esac
