#!/bin/bash
# cost-summary.sh — Daily 23:00 Captain-timezone cost digest to HQ group.
#
# Reads per-officer daily cost from Redis HSET cabinet:cost:tokens:daily:<YYYY-MM-DD>
# (populated by stop-hook.sh per-turn) and posts a reader-friendly digest.
#
# Per Spec 064 v1.1 Checkpoint 7.7 + v1.1 CTO #5 (inline-quote not --stdin).

set -uo pipefail

REPO_ROOT="${CABINET_SOURCE_REPO:-$HOME/work/captains-cabinet}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

# Use Captain timezone for the date (matches their day-cycle)
TZ_NAME=$(grep captain_timezone "$REPO_ROOT/instance/config/platform.yml" 2>/dev/null | awk '{print $2}')
TZ_NAME="${TZ_NAME:-UTC}"
TODAY=$(TZ="$TZ_NAME" date +%Y-%m-%d)

OFFICERS=("cos" "cto" "cpo" "cro" "coo")
MSG="💰 Cabinet cost summary $TODAY"

TOTAL_MICRO=0
for o in "${OFFICERS[@]}"; do
  # HGET the per-officer aggregate field from today's HSET
  DAILY_MICRO=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HGET "cabinet:cost:tokens:daily:$TODAY" "${o}_cost_micro" 2>/dev/null)
  [[ "$DAILY_MICRO" =~ ^[0-9]+$ ]] || DAILY_MICRO=0
  # Convert microdollars → dollars (integer cents for display)
  DAILY_CENTS=$(( DAILY_MICRO / 10000 ))
  DAILY_DOLLARS=$(( DAILY_CENTS / 100 )).$(printf "%02d" $(( DAILY_CENTS % 100 )))
  MSG="$MSG
  $o: \$$DAILY_DOLLARS"
  TOTAL_MICRO=$(( TOTAL_MICRO + DAILY_MICRO ))
done

TOTAL_CENTS=$(( TOTAL_MICRO / 10000 ))
TOTAL_DOLLARS=$(( TOTAL_CENTS / 100 )).$(printf "%02d" $(( TOTAL_CENTS % 100 )))
MSG="$MSG

Total: \$$TOTAL_DOLLARS"

# Audit-fix 2026-05-23: timezone caveat documented.
# launchd's StartCalendarInterval Hour=23 fires at 23:00 LOCAL (the user's TZ,
# as set by `systemsetup -gettimezone`). Phase 1 Checkpoint 1.1 sets the Mac to
# Europe/Berlin → 23:00 fire = 23:00 Berlin = 21:00 UTC. The plist Hour IS
# Captain-tz-aware as long as Phase 1.1 set the system TZ correctly. If running
# on a Mac with a different system TZ, manually adjust the plist Hour.

# send-to-group.sh takes message as positional arg, NOT --stdin
bash "$REPO_ROOT/cabinet/scripts/send-to-group.sh" "$MSG" 2>/dev/null || \
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) cost-summary: send-to-group failed; message was: $MSG" >&2

exit 0
