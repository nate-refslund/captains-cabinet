#!/bin/bash
# heartbeat-watchdog.sh — Detect silent officers, restart them, alert HQ.
#
# Fires every 5 min via LaunchAgent. Decides restart based on the LIVENESS
# heartbeat, NOT the activity heartbeat — see B3 fix 2026-05-26.
#
# Two heartbeat keys (set by hooks in cabinet/scripts/hooks/):
#   cabinet:heartbeat:liveness:<officer>   TTL 1800s (30min)
#     Set by session-start.sh at boot, refreshed by post-tool-use.sh every
#     N tool calls. Missing ⇒ officer process is gone or wedged.
#   cabinet:heartbeat:activity:<officer>   TTL 3600s (60min)
#     Set by post-tool-use.sh on every tool call. Missing ⇒ no tool calls
#     recently. NOT a death signal — a healthy officer can idle for hours.
#
# Watchdog decision matrix:
#   liveness fresh                          → healthy, no action
#   liveness stale + pane-PID alive         → idle but alive, log only
#   liveness stale + pane-PID dead          → DEAD, restart + alert
#   liveness stale + no pane-PID sentinel   → likely never booted, restart + alert
#
# Pre-fix bug (B3): the watchdog read the legacy `cabinet:heartbeat:<o>` key
# (900s TTL refreshed only on tool calls), so a healthy officer thinking or
# waiting for a Captain DM for ≥15 min got kicked. Liveness/activity split
# fixes the false positive.
#
# Pre-fix bug (B3 part 2): the stale-alert NX-dedup key gated BOTH the
# Telegram alert AND the restart_officer() call. So an officer in a stuck
# loop got at most 1 restart attempt per hour even though the rate-limit
# counter advertised 3/hour. Now dedup gates only the alert text — restart
# attempts run on every stale tick (still capped by the 3/hour counter).
#
# Restart strategy: `launchctl kickstart -k gui/<uid>/com.cabinet.officer.<o>`
# (the -k flag cycles the agent; KeepAlive then relaunches it cleanly).
#
# Rate-limited: max 3 restarts per officer per hour. Counter at
# `cabinet:watchdog:restart-count:<officer>` (INCR with EXPIRE 3600 on first
# hit). On cap-exceeded we still alert but skip the restart.
#
# Per Spec 064 v1.1 Checkpoints 7.6 + v1.1 CTO #3 (TTL-based, no BSD/GNU date
# divergence) + v1.1 CTO #7 (dedup-clear on recovery) + B3 fix 2026-05-26
# (liveness vs activity).
#
# Detection latency math:
# - session-start sets liveness with 1800s TTL; post-tool-use refreshes every
#   N=5 tool calls.
# - Watchdog fires every 300s (StartInterval=300 in plist).
# - If officer dies right after a refresh, TTL expires in 1800s + next
#   watchdog tick in up to 300s = up to ~35 min before restart fires.

set -uo pipefail

REPO_ROOT="${CABINET_SOURCE_REPO:-$HOME/work/captains-cabinet}"

# Source cabinet/.env (Telegram tokens etc.) if present — launchd/cron runs
# get no login environment, so without this every Telegram send dies
# token-less. set -a exports the vars to child scripts (send-to-group.sh /
# send-to-warroom.sh and helpers).
if [ -f "$REPO_ROOT/cabinet/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$REPO_ROOT/cabinet/.env"
  set +a
fi
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
SENTINEL_DIR="$HOME/Library/Caches/cabinet"
LA_DIR="$HOME/Library/LaunchAgents"

# Rate-limit: max N restarts per officer per hour.
RESTART_CAP_PER_HOUR=3

# Fulltime officer roster — derived from instance/roles/active/*.yml
# (officer_type: field written by bootstrap-roles.sh). Consultants are
# on-demand sessions and must NOT be watchdog-restarted; an absent
# officer_type defaults to fulltime (pre-officer_type ymls).
FULLTIME_OFFICERS=()
ROLES_DIR="$REPO_ROOT/instance/roles/active"
if [ -d "$ROLES_DIR" ]; then
  for role_yml in "$ROLES_DIR"/*.yml; do
    [ -f "$role_yml" ] || continue
    otype=$(awk -F': *' '$1=="officer_type"{print $2; exit}' "$role_yml" | tr -d '[:space:]')
    if [ "${otype:-fulltime}" != "consultant" ]; then
      slug="$(basename "$role_yml" .yml)"
      # Same installed-plist filter as the fallback path below: this is a
      # RESTARTER, so a roster-seeded slug with no LaunchAgent on THIS host
      # (seeded but not yet deploy-mac'd, or deployed elsewhere) must not be
      # kickstarted — every attempt fails and false-alerts forever.
      if [ -f "$LA_DIR/com.cabinet.officer.$slug.plist" ]; then
        FULLTIME_OFFICERS+=("$slug")
      else
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) heartbeat-watchdog: skipping $slug — roster-seeded but no installed LaunchAgent on this host" >&2
      fi
    fi
  done
fi
if [ "${#FULLTIME_OFFICERS[@]}" -eq 0 ]; then
  # Fallback when instance/roles/active/ is empty/missing (NOT yet seeded by
  # bootstrap-roles.sh — the case on the hq deployment today). DERIVE from
  # .claude/agents/*.md (the deployment-resolved roster; this Mac-cron script
  # has the repo tree). An empty roles dir must NEVER fall through to a phantom
  # hardcoded set — that was the bug (phantom cto/cpo/coo have no LaunchAgent,
  # so `launchctl kickstart com.cabinet.officer.<phantom>` fails → false
  # restart-failure alerts while real officer deaths go unwatched).
  #
  # .claude/agents/*.md has no reliable officer_type signal (frontmatter omits
  # it; bodies are contradictory for lane CEOs), so we cannot fulltime-filter
  # here. Belt-and-braces instead: this is a RESTARTER, so only include a slug
  # that actually has an installed LaunchAgent to restart
  # (com.cabinet.officer.<slug>.plist). That guarantees no phantom is ever
  # kickstarted regardless of how .claude/agents/ drifts, and every officer
  # with a persistent agent on this host is fulltime by construction.
  AGENTS_DIR="$REPO_ROOT/.claude/agents"
  if [ -d "$AGENTS_DIR" ]; then
    for agent_md in "$AGENTS_DIR"/*.md; do
      [ -f "$agent_md" ] || continue
      slug="$(basename "$agent_md" .md)"
      [ "$slug" = "TEMPLATE" ] && continue
      # Only restart what has a persistent LaunchAgent (the restart target).
      if [ -f "$LA_DIR/com.cabinet.officer.$slug.plist" ]; then
        FULLTIME_OFFICERS+=("$slug")
      fi
    done
  fi
  if [ "${#FULLTIME_OFFICERS[@]}" -eq 0 ]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) heartbeat-watchdog: no roster from instance/roles/active/ or .claude/agents/ (+installed plists) — nothing to watch this tick" >&2
  fi
fi

restart_officer() {
  local o="$1" reason="$2" alert_now="${3:-1}"
  # alert_now=1 → send Telegram alert text; alert_now=0 → restart silently
  # (dedup window active for this officer). Restart attempts always run and
  # always increment the counter — the 3/hour cap is in the counter, not the
  # dedup. Pre-fix, the dedup blocked the counter from incrementing at all.

  # Rate-limit check via Redis counter (INCR, set TTL on first hit).
  local cnt
  cnt=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" INCR "cabinet:watchdog:restart-count:$o" 2>/dev/null || echo "0")
  if [ "$cnt" = "1" ]; then
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" EXPIRE "cabinet:watchdog:restart-count:$o" 3600 > /dev/null 2>&1 || true
  fi

  if [ "$cnt" -gt "$RESTART_CAP_PER_HOUR" ]; then
    # Cap exceeded — escalate via Telegram (only if dedup window allows) and
    # skip the restart so we don't spin.
    if [ "$alert_now" = "1" ]; then
      local MSG="🛑 [HEARTBEAT] $o stuck after $RESTART_CAP_PER_HOUR restart attempts in last hour ($reason). Restart loop suppressed — manual intervention required: \`launchctl print gui/\$(id -u)/com.cabinet.officer.$o\`"
      bash "$REPO_ROOT/cabinet/scripts/send-to-group.sh" "$MSG" 2>/dev/null || \
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) heartbeat-watchdog: $o cap-exceeded (send-to-group failed): $reason" >&2
    else
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) heartbeat-watchdog: $o cap-exceeded (alert suppressed by dedup): $reason" >&2
    fi
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

  if [ "$alert_now" = "1" ]; then
    local MSG
    if [ "$rc" -eq 0 ]; then
      MSG="⚠️ [HEARTBEAT] $o stale ($reason). Auto-restarted (attempt $cnt/$RESTART_CAP_PER_HOUR this hour) via \`launchctl kickstart -k $label\`."
    else
      MSG="🛑 [HEARTBEAT] $o stale ($reason). \`launchctl kickstart\` returned $rc — agent may be unloaded. Run \`bash $REPO_ROOT/cabinet/scripts/deploy-mac.sh\` to reinstall LaunchAgents."
    fi
    bash "$REPO_ROOT/cabinet/scripts/send-to-group.sh" "$MSG" 2>/dev/null || \
      echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) heartbeat-watchdog: $o restart rc=$rc (send-to-group failed): $reason" >&2
  else
    # Dedup window active — restart silently. Counter still incremented above.
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) heartbeat-watchdog: $o restart attempt $cnt/$RESTART_CAP_PER_HOUR (alert suppressed by dedup) rc=$rc: $reason" >&2
  fi
  return 0
}

# Reachability probe — if Redis is down, do NOTHING. Without Redis we can't
# read liveness or rate-limit counters; restarting blindly would be worse
# than waiting for the next 5-min tick when Redis returns. PING returns
# "PONG" on success; any other output (including empty from a timeout) means
# unreachable. Treat the watchdog as a no-op in that case (exit 0 so launchd
# doesn't accumulate failure backoff — the cron schedule will retry in 5min).
REDIS_PING=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -t 2 PING 2>/dev/null || echo "")
if [ "$REDIS_PING" != "PONG" ]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) heartbeat-watchdog: Redis unreachable at $REDIS_HOST:$REDIS_PORT — no-op, will retry next tick" >&2
  exit 0
fi

# Empty-safe expansion (bash 3.2 + set -u): on an unseeded/undeployed host the
# roster is legitimately empty and a bare "${FULLTIME_OFFICERS[@]}" is an
# unbound-variable fatal there. ${ARR[@]+...} expands to zero words when empty.
for o in ${FULLTIME_OFFICERS[@]+"${FULLTIME_OFFICERS[@]}"}; do
  # Probe 1 — LIVENESS heartbeat (the death signal)
  LIVE_EXISTS=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" EXISTS "cabinet:heartbeat:liveness:$o" 2>/dev/null || echo "0")

  # Probe 2 — pane_pid sentinel (cross-check: is the wrapper process alive?)
  PANE_PID_STATE="absent"   # absent | alive | dead
  PANE_PID=""
  if [ -f "$SENTINEL_DIR/$o.pane.pid" ]; then
    PANE_PID=$(cat "$SENTINEL_DIR/$o.pane.pid" 2>/dev/null || echo "")
    if [ -n "$PANE_PID" ]; then
      if kill -0 "$PANE_PID" 2>/dev/null; then
        PANE_PID_STATE="alive"
      else
        PANE_PID_STATE="dead"
      fi
    fi
  fi

  # Decision matrix (see header)
  if [ "$LIVE_EXISTS" = "1" ]; then
    # Liveness fresh — officer is healthy. Clear any prior stale-alert dedup
    # so the next failure alerts promptly. Do NOT clear the restart-count
    # counter; let it expire on its 1h TTL so a flaky officer alternating
    # dead/alive states can't bypass the cap.
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DEL "cabinet:alert:heartbeat-stale:$o" > /dev/null 2>&1
    continue
  fi

  # Liveness stale from here on. Branch on pane PID state.
  if [ "$PANE_PID_STATE" = "alive" ]; then
    # Officer process exists but isn't refreshing liveness. Could be a wedged
    # Claude binary, but more often it's a long idle stretch right at the
    # boundary of the 30min liveness TTL (e.g. officer thinking through a
    # large compaction, blocked on Captain input with no triggers). Do NOT
    # restart — that would interrupt a healthy session. Log to stderr so the
    # operator can investigate if this pattern recurs.
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) heartbeat-watchdog: $o liveness expired but pane-PID $PANE_PID alive — idle but alive, no restart" >&2
    continue
  fi

  # Liveness stale AND (pane PID dead OR no sentinel at all) — officer is gone.
  if [ "$PANE_PID_STATE" = "dead" ]; then
    STALE_REASON="liveness-expired+pane-pid-dead-$PANE_PID"
  else
    STALE_REASON="liveness-expired+pane-pid-absent"
  fi

  # Decoupled dedup: the NX-key gates ONLY the Telegram alert; restart_officer
  # ALWAYS runs and is rate-limited by the cabinet:watchdog:restart-count
  # counter (3/hour). Pre-fix, the NX-key blocked the restart call entirely
  # for an hour, defeating the 3/hour budget.
  ALERT_NOW=0
  if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "cabinet:alert:heartbeat-stale:$o" 1 NX EX 3600 2>/dev/null | grep -q OK; then
    ALERT_NOW=1
  fi
  # Pass ALERT_NOW so restart_officer can suppress duplicate Telegram noise
  # while still incrementing the restart counter and attempting the kickstart.
  restart_officer "$o" "$STALE_REASON" "$ALERT_NOW"
done

exit 0
