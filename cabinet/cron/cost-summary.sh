#!/bin/bash
# cost-summary.sh — Daily 23:00 Captain-timezone cost digest to HQ group.
#
# Reads per-officer daily cost from Redis HSET cabinet:cost:tokens:daily:<YYYY-MM-DD>
# (populated by stop-hook.sh per-turn) and posts a reader-friendly digest.
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

# FAIL-CLOSED SPEND REPORTING (2026-07-26). Until this date the per-officer read
# below was `redis-cli ... 2>/dev/null` with a `|| DAILY_MICRO=0` coercion, so
# with the control plane unreachable this job sent the Captain's group
# `💰 Total: $0.00`, exit 0, stderr empty — proven BYTE-IDENTICAL to a true
# zero-spend day. The outage rendered as a legitimate business result, on the
# one surface that reaches him personally.
#
# The rule now: this job may never emit a number it cannot source. Either the
# control plane is PROVEN readable and every figure is a proven read, or the
# group gets one honest "cost data unavailable" line and no digest at all.
# plane-read.sh returns VALUE / ABSENT / INDETERMINATE (the killswitch-read.sh
# discipline); ABSENT after a proven-live plane is the ONLY legitimate zero.
PLANE_LIB="$REPO_ROOT/cabinet/scripts/lib/plane-read.sh"
UNAVAIL_REASON=""
if [ -r "$PLANE_LIB" ]; then
  # shellcheck disable=SC1090
  . "$PLANE_LIB"
fi
if ! command -v plane_read_int >/dev/null 2>&1; then
  # A missing/broken helper must NOT degrade to the old silent-zero path.
  UNAVAIL_REASON="proven-read helper unavailable at $PLANE_LIB"
fi

# Use Captain timezone for the date (matches their day-cycle)
TZ_NAME=$(grep captain_timezone "$REPO_ROOT/instance/config/platform.yml" 2>/dev/null | awk '{print $2}')
TZ_NAME="${TZ_NAME:-UTC}"
TODAY=$(TZ="$TZ_NAME" date +%Y-%m-%d)

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

# Prove the plane ONCE up front, so an outage yields one honest line instead of
# N innocent-looking zeroes. (Cheap: a single framed PING.)
if [ -z "$UNAVAIL_REASON" ]; then
  if ! plane_reachable; then
    UNAVAIL_REASON="$PLANE_REASON"
  fi
fi

TOTAL_MICRO=0
# Empty-safe expansion (bash 3.2 + set -u): the totals-only branch above means
# OFFICERS can be legitimately empty, and a bare "${OFFICERS[@]}" is an
# unbound-variable fatal there. ${OFFICERS[@]+...} expands to zero words.
for o in ${OFFICERS[@]+"${OFFICERS[@]}"}; do
  [ -n "$UNAVAIL_REASON" ] && break
  # HGET the per-officer aggregate field from today's HSET — PROVEN read.
  #   VALUE         a live server answered and returned this officer's spend.
  #   ABSENT        a live server answered and the field is genuinely unset —
  #                 the ONLY legitimate zero (officer spent nothing today).
  #   INDETERMINATE could not read. NOT a zero. Abandons the whole digest.
  plane_read_int HGET "cabinet:cost:tokens:daily:$TODAY" "${o}_cost_micro"
  case "$PLANE_VERDICT" in
    VALUE)  DAILY_MICRO="$PLANE_VALUE" ;;
    ABSENT) DAILY_MICRO=0 ;;
    *)      UNAVAIL_REASON="$PLANE_REASON"; break ;;
  esac
  # Convert microdollars → dollars (integer cents for display)
  DAILY_CENTS=$(( DAILY_MICRO / 10000 ))
  DAILY_DOLLARS=$(( DAILY_CENTS / 100 )).$(printf "%02d" $(( DAILY_CENTS % 100 )))
  MSG="$MSG
  $o: \$$DAILY_DOLLARS"
  TOTAL_MICRO=$(( TOTAL_MICRO + DAILY_MICRO ))
done

if [ -n "$UNAVAIL_REASON" ]; then
  # NO digest, NO total, NO number of any kind — the Captain must be able to
  # tell "I cannot read the spend" from "the cabinet spent nothing".
  MSG="⚠️ Cabinet cost summary $TODAY — cost data unavailable: control plane unreachable.
No spend figures are being reported because none could be sourced (this is NOT a zero-spend day).
Detail: $UNAVAIL_REASON"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) cost-summary: FATAL cost data unavailable — control plane unreachable: $UNAVAIL_REASON" >&2
else
  TOTAL_CENTS=$(( TOTAL_MICRO / 10000 ))
  TOTAL_DOLLARS=$(( TOTAL_CENTS / 100 )).$(printf "%02d" $(( TOTAL_CENTS % 100 )))
  MSG="$MSG

Total: \$$TOTAL_DOLLARS"
fi

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
