#!/bin/bash
# cost-summary.sh — Daily 23:00 Captain-timezone cost digest to HQ group.
#
# Reads per-officer daily cost from Redis HSET cabinet:cost:tokens:daily:<YYYY-MM-DD>
# (populated per-turn by cabinet/scripts/hooks/session-stop.sh — the LIVE Stop
# hook; stop-hook.sh is a twin wired to no event) and posts a reader-friendly digest.
#
# Per Spec 064 v1.1 Checkpoint 7.7 + v1.1 CTO #5 (inline-quote not --stdin).

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

# Use Captain timezone for the date (matches their day-cycle)
TZ_NAME=$(grep captain_timezone "$REPO_ROOT/instance/config/platform.yml" 2>/dev/null | awk '{print $2}')
TZ_NAME="${TZ_NAME:-UTC}"
TODAY=$(TZ="$TZ_NAME" date +%Y-%m-%d)

# ---- Cost-ledger liveness (added 2026-07-25) --------------------------------
# This digest, and far more importantly the daily spending caps in
# pre-tool-use.sh, read cabinet:cost:tokens:daily:<date> and NOTHING else. An
# empty key reads as "$0 spent today", so a dead writer does not tighten the
# caps — it removes them, silently. A digest that prints "$0.00" for every
# officer looks like a quiet day and looks identical to a broken ledger.
#
# Hosted here rather than as its own services.yml row on purpose: this is
# already the scheduled cost consumer (daily 23:00, plist-only, no service
# row), and cabinet/config/cognitive-architecture-contract.yml holds
# services_total/services_enabled at a shrink-only budget that
# cognitive-architecture-census.py --check enforces inside
# verify-cognitive-phase*.sh. New periodic work composes into an existing
# runner; it does not grow the service count.
#
# Advisory here by design: never let a health probe abort the digest.
LEDGER_HEALTH_NOTE=""
LEDGER_HEALTH_SCRIPT="$REPO_ROOT/cabinet/scripts/check-cost-ledger-health.sh"
if [ -r "$LEDGER_HEALTH_SCRIPT" ]; then
  if ! LEDGER_HEALTH_OUT=$(REDIS_HOST="$REDIS_HOST" REDIS_PORT="$REDIS_PORT" \
        CABINET_ROOT="$REPO_ROOT" bash "$LEDGER_HEALTH_SCRIPT" 2>&1); then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) cost-summary: COST LEDGER UNHEALTHY — spending caps may not be enforcing" >&2
    printf '%s\n' "$LEDGER_HEALTH_OUT" >&2
    LEDGER_HEALTH_NOTE=$(printf '%s' "$LEDGER_HEALTH_OUT" \
      | grep -E '^[[:space:]]*\[FAIL\]' | head -2 | sed 's/^[[:space:]]*\[FAIL\][[:space:]]*//')
  fi
fi

# Officer roster — derived from instance/roles/active/*.yml (seeded by
# bootstrap-roles.sh) so the digest tracks the REAL roster (portfolio lane
# CEOs included, retired roles dropped). Consultants stay listed — they
# spend tokens too.
OFFICERS=()
ROLES_DIR="$REPO_ROOT/instance/roles/active"
if [ -d "$ROLES_DIR" ]; then
  for role_yml in "$ROLES_DIR"/*.yml; do
    [ -f "$role_yml" ] || continue
    OFFICERS+=("$(basename "$role_yml" .yml)")
  done
fi
if [ "${#OFFICERS[@]}" -eq 0 ]; then
  # Fallback when instance/roles/active/ is empty/missing (NOT yet seeded by
  # bootstrap-roles.sh — the case on the hq deployment today). DERIVE from
  # .claude/agents/*.md — the deployment-resolved roster (load-preset.sh /
  # sync-agents.sh render it; this Mac-cron script has the repo tree, so it's
  # reachable). An empty roles dir must NEVER fall through to a phantom
  # hardcoded set; cost-summary doesn't filter by officer_type (consultants
  # spend tokens too), so all agent slugs are correct here.
  AGENTS_DIR="$REPO_ROOT/.claude/agents"
  if [ -d "$AGENTS_DIR" ]; then
    for agent_md in "$AGENTS_DIR"/*.md; do
      [ -f "$agent_md" ] || continue
      slug="$(basename "$agent_md" .md)"
      [ "$slug" = "TEMPLATE" ] && continue
      OFFICERS+=("$slug")
    done
  fi
fi
if [ "${#OFFICERS[@]}" -eq 0 ]; then
  # Neither instance/roles/active/ nor .claude/agents/ yielded a roster.
  # Emit totals-only (still useful) and log — never invent phantom officers.
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) cost-summary: no roster from instance/roles/active/ or .claude/agents/ — totals-only digest" >&2
fi
MSG="💰 Cabinet cost summary $TODAY"
if [ -n "$LEDGER_HEALTH_NOTE" ]; then
  # Surface it in the digest itself — a silent $0.00 day is exactly what a dead
  # ledger looks like, so the reader must be told the numbers may not be real.
  MSG="$MSG"$'\n'"⚠️ Cost ledger unhealthy — the figures below may be incomplete, and the daily spending caps read the same source:"$'\n'"$LEDGER_HEALTH_NOTE"
fi

TOTAL_MICRO=0
# Empty-safe expansion (bash 3.2 + set -u): the totals-only branch above means
# OFFICERS can be legitimately empty, and a bare "${OFFICERS[@]}" is an
# unbound-variable fatal there. ${OFFICERS[@]+...} expands to zero words.
for o in ${OFFICERS[@]+"${OFFICERS[@]}"}; do
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
