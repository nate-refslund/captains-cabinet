#!/bin/bash
# health-check.sh — Runs every 5 min via cron (in Watchdog container)
[ -f /etc/environment.cabinet ] && source /etc/environment.cabinet
# Checks each Officer's Redis heartbeat (set by post-tool-use hook in Officers container).
# Alerts Captain if an Officer's heartbeat is stale (>15 min).

# B4 Mac portability (matches research-sweep.sh + lib/triggers.sh): an
# explicit REDIS_HOST (caller/wrapper env) WINS; REDIS_URL is the fallback for
# docker deployments that set it in the compose env / environment.cabinet. The
# old unconditional derive clobbered the caller's REDIS_HOST with the
# docker-era `redis` hostname → dead Redis on every Mac-native run.
REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
REDIS_HOST="${REDIS_HOST:-$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)}"
REDIS_PORT="${REDIS_PORT:-$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)}"

TELEGRAM_COS_TOKEN="${TELEGRAM_COS_TOKEN:?not set}"
CAPTAIN_TELEGRAM_ID="${CAPTAIN_TELEGRAM_ID:?not set}"

TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M:%S UTC')

# Roster source — DERIVED, not hardcoded. The watchdog container ships
# health-check.sh standalone (Dockerfile.watchdog: COPY .../health-check.sh
# /opt/watchdog/), with NO repo tree, so the .claude/agents/ roster (the
# canonical resolved set) is unreachable from here. Redis IS reachable and is
# the cross-container, deployment-resolved roster: load-preset.sh writes
# cabinet:officer:expected:<slug>=active for each hired+defined officer at
# activation (the same resolved set that lands in .claude/agents/). We
# enumerate those keys exactly as officer-supervisor.sh does (the 7th working
# script that already derives the roster this way), so health-check tracks the
# LIVE officers — preset-agnostic — instead of a stale hardcoded list.
OFFICERS=()
while IFS= read -r officer; do
  [ -n "$officer" ] && OFFICERS+=("$officer")
done < <(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" KEYS "cabinet:officer:expected:*" 2>/dev/null \
           | sed 's/cabinet:officer:expected://' | sort)

send_alert() {
  local message="$1"
  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_COS_TOKEN}/sendMessage" \
    -d chat_id="$CAPTAIN_TELEGRAM_ID" \
    -d text="⚠️ Cabinet Health Alert ($TIMESTAMP)

$message" \
    -d parse_mode="Markdown" > /dev/null 2>&1
}

check_officer() {
  local officer="$1"
  local redis_key="cabinet:heartbeat:$officer"

  # Check if heartbeat exists (TTL of 900s = 15 min, set by post-tool-use hook)
  local heartbeat
  heartbeat=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "$redis_key" 2>/dev/null)

  if [ -n "$heartbeat" ] && [ "$heartbeat" != "" ]; then
    # Heartbeat exists and hasn't expired — Officer is alive
    echo "[$TIMESTAMP] Officer $officer: healthy (last heartbeat: $heartbeat)"
    return 0
  else
    # No heartbeat — check if we already flagged this
    local flag_key="cabinet:health:alert-sent:$officer"
    local already_alerted
    already_alerted=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "$flag_key" 2>/dev/null)

    if [ "$already_alerted" = "yes" ]; then
      echo "[$TIMESTAMP] Officer $officer: still down (alert already sent)"
    else
      send_alert "🔴 *$officer* has no heartbeat. The Officer may have crashed or stalled. Check tmux in the Officers container."
      redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "$flag_key" "yes" EX 21600 > /dev/null 2>&1  # 6h dedup
      echo "[$TIMESTAMP] Officer $officer: DOWN — alert sent to Captain"
    fi
    return 1
  fi
}

# ============================================================
# Run checks
# ============================================================
echo "[$TIMESTAMP] Running health checks..."

# Empty-roster guard. An empty OFFICERS list must NEVER read as healthy — that
# was the whole defect (a static list could drift to phantoms; a silently
# empty derived list is the same failure with the opposite cause). Distinguish
# the two: Redis unreachable vs. Redis up but zero expected-active officers.
# Both are alert-worthy; dedup with the same flag pattern as check_officer.
if [ "${#OFFICERS[@]}" -eq 0 ]; then
  if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" PING > /dev/null 2>&1; then
    reason="Redis is up but has NO cabinet:officer:expected:* keys — no officers are activated. Run load-preset.sh / supervisor."
    flag_key="cabinet:health:alert-sent:__no-roster__"
  else
    reason="Redis is UNREACHABLE at ${REDIS_HOST}:${REDIS_PORT} — health-check cannot derive the roster or read heartbeats."
    flag_key=""  # can't dedup via Redis when Redis is down; alert every run
  fi
  already=""
  [ -n "$flag_key" ] && already=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "$flag_key" 2>/dev/null)
  if [ "$already" != "yes" ]; then
    send_alert "🔴 *Cabinet roster empty.* $reason"
    [ -n "$flag_key" ] && redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "$flag_key" "yes" EX 21600 > /dev/null 2>&1
    echo "[$TIMESTAMP] EMPTY ROSTER — alert sent: $reason"
  else
    echo "[$TIMESTAMP] EMPTY ROSTER — $reason (alert already sent)"
  fi
fi

DOWN_COUNT=0
for officer in "${OFFICERS[@]}"; do
  # Only check Officers that should be running
  EXPECTED=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "cabinet:officer:expected:$officer" 2>/dev/null)
  if [ "$EXPECTED" = "active" ]; then
    if ! check_officer "$officer"; then
      DOWN_COUNT=$((DOWN_COUNT + 1))
    fi
  fi
done

# Check Redis kill switch state
KILLSWITCH=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET cabinet:killswitch 2>/dev/null)
if [ "$KILLSWITCH" = "active" ]; then
  echo "[$TIMESTAMP] Kill switch is ACTIVE — skipping further checks"
fi

# Posture attestation status (sovereign amendment 2026-07-05) — LOG-ONLY,
# never alerts: the resolution itself is fail-safe (anything ambiguous is
# guardian), so this line is observability, not enforcement. The watchdog
# container ships this script without the repo tree — guard on the file and
# on `ls -lO` (macOS-only flag output; Linux prints the guardian fallback).
POSTURE_FILE="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)}/instance/config/posture.yml"
if [ -f "$POSTURE_FILE" ]; then
  _P_DECLARED=$(grep -E '^posture:' "$POSTURE_FILE" 2>/dev/null | awk '{print $2}')
  if ls -lO "$POSTURE_FILE" 2>/dev/null | grep -q schg; then
    echo "[$TIMESTAMP] Posture: declared=${_P_DECLARED:-?} attestation=LOCKED (schg) — ruling is live"
  else
    echo "[$TIMESTAMP] Posture: declared=${_P_DECLARED:-?} attestation=UNLOCKED — resolves guardian until the Captain locks it (sudo bash cabinet/scripts/germline-lock.sh lock)"
  fi
else
  echo "[$TIMESTAMP] Posture: no posture.yml — guardian (today's rules)"
fi

# Log overall status
echo "[$TIMESTAMP] Health check complete. Down: $DOWN_COUNT"
