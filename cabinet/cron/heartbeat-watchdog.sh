#!/bin/bash
# heartbeat-watchdog.sh — Detect silent officers, restart them, alert HQ.
#
# Fires every 5 min via LaunchAgent. Checks each fulltime officer for two
# failure modes:
#   1. Heartbeat stale — `cabinet:heartbeat:<officer>` Redis key doesn't EXIST
#      (writer SETEXes 900s TTL on every tool-use; absence ⇒ no tool calls in
#      ≥15min).
#   2. Pane PID dead — sentinel at $HOME/Library/Caches/cabinet/<officer>.pane.pid
#      exists but `kill -0 <pid>` fails (start-officer-mac.sh publishes the
#      tmux pane_pid here; absent ⇒ wrapper hasn't booted yet; dead PID ⇒
#      claude+shell tree exited but wrapper somehow stuck).
#
# On stale: restart via `launchctl kickstart -k gui/<uid>/com.cabinet.officer.<o>`
# (the -k flag cycles the agent; KeepAlive then relaunches it cleanly). Also
# send a Telegram alert so the operator has visibility.
#
# Rate-limited: max 3 restarts per officer per hour. Counter at
# `cabinet:watchdog:restart-count:<officer>` (INCR with EXPIRE 3600 on first
# hit). On cap-exceeded we still alert but skip the restart so a perpetually-
# broken officer doesn't spin.
#
# Alerts deduped 1h via Redis NX-key. Dedup key CLEARED on first successful
# heartbeat after a known-stale state so re-failures alert promptly.
#
# Per Spec 064 v1.1 Checkpoints 7.6 + v1.1 CTO #3 (TTL-based, no BSD/GNU date
# divergence) + v1.1 CTO #7 (dedup-clear on recovery).
#
# Hardening 2026-05-26: was alert-only; now self-heals. Restart strategy uses
# `launchctl kickstart -k` rather than direct `start-officer-mac.sh` invocation
# because launchctl properly tears down + respawns the wrapper through the
# normal lifecycle (KeepAlive, throttle, env vars from plist). Direct invocation
# would leave the original wrapper running too.
#
# Detection latency math:
# - Officer heartbeat writer SETEXes 900s TTL on every tool-use.
# - Watchdog fires every 300s (StartInterval=300 in plist).
# - If officer dies right after a heartbeat, TTL expires in 900s + next watchdog
#   tick in up to 300s = up to 20 min before restart fires.

set -uo pipefail

REPO_ROOT="${CABINET_SOURCE_REPO:-$HOME/work/captains-cabinet}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
SENTINEL_DIR="$HOME/Library/Caches/cabinet"

# Rate-limit: max N restarts per officer per hour.
RESTART_CAP_PER_HOUR=3

# Fulltime officer roster — consultant officers (e.g. CRO if configured consultant) excluded.
# Reads from instance/config/platform.yml ideally; hardcoded default for now.
FULLTIME_OFFICERS=("cos" "cto" "cpo" "coo")

restart_officer() {
  local o="$1" reason="$2"

  # Rate-limit check via Redis counter (INCR, set TTL on first hit).
  local cnt
  cnt=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" INCR "cabinet:watchdog:restart-count:$o" 2>/dev/null || echo "0")
  if [ "$cnt" = "1" ]; then
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" EXPIRE "cabinet:watchdog:restart-count:$o" 3600 > /dev/null 2>&1 || true
  fi

  if [ "$cnt" -gt "$RESTART_CAP_PER_HOUR" ]; then
    # Cap exceeded — escalate via Telegram but skip restart so we don't spin.
    local MSG="🛑 [HEARTBEAT] $o stuck after $RESTART_CAP_PER_HOUR restart attempts in last hour ($reason). Restart loop suppressed — manual intervention required: \`launchctl print gui/\$(id -u)/com.cabinet.officer.$o\`"
    bash "$REPO_ROOT/cabinet/scripts/send-to-group.sh" "$MSG" 2>/dev/null || \
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) heartbeat-watchdog: $o cap-exceeded (send-to-group failed): $reason" >&2
    return 1
  fi

  # Within budget — restart via launchctl kickstart -k (cycles agent, KeepAlive respawns).
  local uid label rc
  uid=$(id -u)
  label="gui/$uid/com.cabinet.officer.$o"
  if launchctl kickstart -k "$label" 2>/dev/null; then
    rc=0
  else
    rc=$?
  fi

  local MSG
  if [ "$rc" -eq 0 ]; then
    MSG="⚠️ [HEARTBEAT] $o stale ($reason). Auto-restarted (attempt $cnt/$RESTART_CAP_PER_HOUR this hour) via \`launchctl kickstart -k $label\`."
  else
    MSG="🛑 [HEARTBEAT] $o stale ($reason). \`launchctl kickstart\` returned $rc — agent may be unloaded. Run \`bash $REPO_ROOT/cabinet/scripts/deploy-mac.sh\` to reinstall LaunchAgents."
  fi
  bash "$REPO_ROOT/cabinet/scripts/send-to-group.sh" "$MSG" 2>/dev/null || \
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) heartbeat-watchdog: $o restart rc=$rc (send-to-group failed): $reason" >&2
  return 0
}

for o in "${FULLTIME_OFFICERS[@]}"; do
  STALE_REASON=""

  # Probe 1 — heartbeat TTL key
  EXISTS=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" EXISTS "cabinet:heartbeat:$o" 2>/dev/null || echo "0")
  if [ "$EXISTS" = "0" ]; then
    STALE_REASON="heartbeat-expired"
  fi

  # Probe 2 — pane_pid sentinel (only if heartbeat still alive; cross-check)
  if [ -z "$STALE_REASON" ] && [ -f "$SENTINEL_DIR/$o.pane.pid" ]; then
    PANE_PID=$(cat "$SENTINEL_DIR/$o.pane.pid" 2>/dev/null || echo "")
    if [ -n "$PANE_PID" ] && ! kill -0 "$PANE_PID" 2>/dev/null; then
      STALE_REASON="pane-pid-dead-$PANE_PID"
    fi
  fi

  if [ -n "$STALE_REASON" ]; then
    # Stale — alert+restart (deduped by Redis 1h TTL key)
    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "cabinet:alert:heartbeat-stale:$o" 1 NX EX 3600 2>/dev/null | grep -q OK; then
      restart_officer "$o" "$STALE_REASON"
    fi
  else
    # Officer is alive — clear any prior stale-alert dedup so re-failures alert promptly.
    # NOTE: do NOT clear cabinet:watchdog:restart-count — that's the rate-limit budget;
    # let it expire naturally on its 1h TTL so a flaky officer can't bypass the cap by
    # alternating dead/alive states.
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DEL "cabinet:alert:heartbeat-stale:$o" > /dev/null 2>&1
  fi
done

exit 0
