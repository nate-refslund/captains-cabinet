#!/bin/bash
# heartbeat-watchdog.sh — Detect silent officers + alert via HQ group.
#
# Fires every 5 min via LaunchAgent. Checks each fulltime officer's heartbeat
# (TTL-based: if `cabinet:heartbeat:<officer>` Redis key doesn't EXIST, officer
# is stale — heartbeat writer SETEXes with 900s TTL on every tool-use).
#
# Alerts deduped 1h via Redis NX-key. Dedup key CLEARED on first successful
# heartbeat after a known-stale state so re-failures alert promptly.
#
# Per Spec 064 v1.1 Checkpoints 7.6 + v1.1 CTO #3 (TTL-based, no BSD/GNU date
# divergence) + v1.1 CTO #7 (dedup-clear on recovery).
#
# Detection latency math (audit-fix 2026-05-23 — document the worst case):
# - Officer heartbeat writer SETEXes 900s TTL on every tool-use.
# - Watchdog fires every 300s (StartInterval=300 in plist).
# - If officer dies right after a heartbeat, TTL expires in 900s + next watchdog
#   tick in up to 300s = up to 20 min before alert fires. Acceptable for
#   non-safety-critical officer monitoring; tighten only if real ops show
#   the 20-min window misses critical incidents.

set -uo pipefail

REPO_ROOT="${CABINET_SOURCE_REPO:-$HOME/work/captains-cabinet}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

# Fulltime officer roster — consultant officers (e.g. CRO if configured consultant) excluded.
# Reads from instance/config/platform.yml ideally; hardcoded default for now.
FULLTIME_OFFICERS=("cos" "cto" "cpo" "coo")

for o in "${FULLTIME_OFFICERS[@]}"; do
  EXISTS=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" EXISTS "cabinet:heartbeat:$o" 2>/dev/null)

  if [ "$EXISTS" = "0" ]; then
    # Stale — alert (deduped by Redis 1h TTL key)
    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "cabinet:alert:heartbeat-stale:$o" 1 NX EX 3600 2>/dev/null | grep -q OK; then
      MSG="⚠️ [HEARTBEAT] $o stale — check launchctl print gui/\$(id -u)/com.cabinet.officer.$o"
      bash "$REPO_ROOT/cabinet/scripts/send-to-group.sh" "$MSG" 2>/dev/null || \
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) heartbeat-watchdog: officer $o stale (send-to-group failed)" >&2
    fi
  else
    # Officer is alive — clear any prior stale-alert dedup so re-failures alert promptly
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DEL "cabinet:alert:heartbeat-stale:$o" > /dev/null 2>&1
  fi
done

exit 0
