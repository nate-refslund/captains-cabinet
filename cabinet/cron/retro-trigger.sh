#!/bin/bash
# retro-trigger.sh — Fires retro when reflection threshold reached
# Event-based: every 5 reflections cabinet-wide OR every 48h as a safety floor
# (so retros happen even on quiet days; floor matches CLAUDE.md's 48h).

# Shell hardening (2026-07-26, cron-CI wave): -u + pipefail, deliberately NOT
# -e. The failure path below reads $? after `_send_err=$(...)`; errexit aborts
# ON that assignment, before the diagnostic prints, so the log loses the error
# markers the outcome-watchdog pages on (JOB_ERROR_MARKERS,
# framework/watchdog/registry.py:753) while the exit code stays 1 — a failure
# that reads as silence. Verified against a scratch Redis: -uo is
# byte-identical to no flags in both success and failure modes, -euo deletes
# the diagnostic every time. Same reasoning already documented in
# cabinet/scripts/run-golden-evals.sh; same flags as cost-summary.sh /
# heartbeat-watchdog.sh / limit-reset-watchdog.sh.
set -uo pipefail

# B4 Mac portability (2026-07-03): explicit REDIS_HOST/PORT win; REDIS_URL is
# a fallback; default 127.0.0.1 — the old 'redis' Docker-DNS default made every
# redis-cli below fail silently on Mac.
if [ -n "${REDIS_HOST:-}" ] || [ -n "${REDIS_PORT:-}" ]; then
  REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
  REDIS_PORT="${REDIS_PORT:-6379}"
elif [ -n "${REDIS_URL:-}" ]; then
  REDIS_HOST=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
  REDIS_PORT=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)
  REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
  REDIS_PORT="${REDIS_PORT:-6379}"
else
  REDIS_HOST="127.0.0.1"
  REDIS_PORT="6379"
fi
TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M:%S UTC')

# Resolve CABINET_ROOT — env var wins, otherwise script-relative (cabinet/cron/.. = repo root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

# Source cabinet/.env (Telegram tokens etc.) if present — launchd/cron runs
# get no login environment, so without this every Telegram send dies
# token-less. set -a exports the vars to child scripts (send-to-group.sh /
# send-to-warroom.sh and helpers).
if [ -f "$CABINET_ROOT/cabinet/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$CABINET_ROOT/cabinet/.env"
  set +a
fi
TRIGGERS_LIB="$CABINET_ROOT/cabinet/scripts/lib/triggers.sh"

if [ ! -f "$TRIGGERS_LIB" ]; then
  echo "[$TIMESTAMP] retro-trigger.sh FATAL: triggers lib not found at $TRIGGERS_LIB (CABINET_ROOT=$CABINET_ROOT) — retro NOT fired" >&2
  exit 1
fi
# shellcheck source=/dev/null
. "$TRIGGERS_LIB"
if ! declare -f trigger_send > /dev/null; then
  echo "[$TIMESTAMP] retro-trigger.sh FATAL: trigger_send not defined after sourcing $TRIGGERS_LIB — retro NOT fired" >&2
  exit 1
fi

# Threshold: 5 reflections since last retro
THRESHOLD=5

# PROVEN READS (2026-07-26 fail-open sweep). These were
# `redis-cli ... 2>/dev/null || echo 0`, so an unreachable control plane made
# REFLECTIONS_SINCE exactly 0 — indistinguishable from "no new reflections" —
# and the retro silently never fired, for as long as the outage lasted, with
# exit 0 and no log line. An unreadable counter is not a zero counter.
#
# The DECISION is unchanged (do not fire): reading the count is what decides
# whether a retro is due, and firing one on an unknown count would be inventing
# a rule. What changes is that the skip is now LOUD and carries a
# JOB_ERROR_MARKERS token, so the outcome-watchdog's log-tail scan sees it.
PLANE_LIB="$CABINET_ROOT/cabinet/scripts/lib/plane-read.sh"
if [ -r "$PLANE_LIB" ]; then
  # shellcheck source=/dev/null
  . "$PLANE_LIB"
fi
if ! command -v plane_read_int > /dev/null 2>&1; then
  echo "[$TIMESTAMP] retro-trigger.sh FATAL: proven-read helper missing at $PLANE_LIB — cannot source reflection counts, retro NOT fired" >&2
  exit 1
fi

# Sets RETRO_COUNT in THIS shell — never via $( ), which would run the read in
# a subshell and strand PLANE_REASON there (found by execution: the failure
# path died on `PLANE_REASON: unbound variable` under set -u).
RETRO_COUNT=0
_retro_count() {   # $1 = key
  plane_read_int GET "$1"
  case "$PLANE_VERDICT" in
    VALUE)  RETRO_COUNT="$PLANE_VALUE"; return 0 ;;
    ABSENT) RETRO_COUNT=0;              return 0 ;;   # proven-unset counter = 0
    *)      RETRO_COUNT=0;              return 11 ;;
  esac
}

if _retro_count "cabinet:reflections:count"; then
  REFLECTIONS_NOW="$RETRO_COUNT"
else
  echo "[$TIMESTAMP] retro-trigger.sh FATAL: control plane unreadable ($PLANE_REASON) — reflection count could not be sourced, retro NOT fired (this is NOT 'no new reflections')" >&2
  exit 1
fi
if _retro_count "cabinet:reflections:count_at_last_retro"; then
  LAST_RETRO_COUNT="$RETRO_COUNT"
else
  echo "[$TIMESTAMP] retro-trigger.sh FATAL: control plane unreadable ($PLANE_REASON) — last-retro count could not be sourced, retro NOT fired" >&2
  exit 1
fi

REFLECTIONS_SINCE=$((REFLECTIONS_NOW - LAST_RETRO_COUNT))

# Safety floor: also fire if last retro was 48h ago (catches quiet periods)
# stamp key fix (HIGH-8 2026-07-03): the script read cos:retro, a key nothing
# ever writes — the floor clock was permanently at epoch 0. The retro task's
# real name is cross-officer-retro; read it (legacy cos:retro as fallback for
# any historical value).
#
# PROVEN READS too (2026-07-26): an unreadable stamp used to yield "" -> `date`
# fails -> LAST_RETRO_EPOCH=0 -> HOURS_SINCE_RETRO ~490000 -> the 48h safety
# floor fires EVERY tick for the duration of the outage. A PROVEN-ABSENT stamp
# keeping that epoch-0 "never ran, so fire the floor" behaviour is deliberate
# and unchanged; an UNREADABLE one must not impersonate it.
LAST_RETRO_TS=""
plane_read GET "cabinet:schedule:last-run:cos:cross-officer-retro"
case "$PLANE_VERDICT" in
  VALUE)         LAST_RETRO_TS="$PLANE_VALUE" ;;
  INDETERMINATE) echo "[$TIMESTAMP] retro-trigger.sh FATAL: control plane unreadable ($PLANE_REASON) — last-retro timestamp could not be sourced, retro NOT fired (refusing to let an unreadable stamp trip the 48h safety floor)" >&2; exit 1 ;;
esac
if [ -z "$LAST_RETRO_TS" ]; then
  plane_read GET "cabinet:schedule:last-run:cos:retro"   # legacy key
  case "$PLANE_VERDICT" in
    VALUE)         LAST_RETRO_TS="$PLANE_VALUE" ;;
    INDETERMINATE) echo "[$TIMESTAMP] retro-trigger.sh FATAL: control plane unreadable ($PLANE_REASON) — legacy last-retro timestamp could not be sourced, retro NOT fired" >&2; exit 1 ;;
  esac
fi
LAST_RETRO_EPOCH=$(date -d "$LAST_RETRO_TS" +%s 2>/dev/null \
  || date -j -f "%Y-%m-%dT%H:%M:%SZ" "$LAST_RETRO_TS" +%s 2>/dev/null \
  || echo 0)
NOW_EPOCH=$(date -u +%s)
HOURS_SINCE_RETRO=$(( (NOW_EPOCH - LAST_RETRO_EPOCH) / 3600 ))

SHOULD_FIRE=false
REASON=""

if [ "$REFLECTIONS_SINCE" -ge "$THRESHOLD" ]; then
  SHOULD_FIRE=true
  REASON="$REFLECTIONS_SINCE reflections since last retro (threshold: $THRESHOLD)"
elif [ "$HOURS_SINCE_RETRO" -ge 48 ]; then
  SHOULD_FIRE=true
  REASON="${HOURS_SINCE_RETRO}h since last retro (safety floor: 48h)"
fi

if [ "$SHOULD_FIRE" = true ]; then
  TRIGGER_MSG="[$TIMESTAMP] RETRO + EVOLUTION DUE — $REASON.

INPUTS to retro (gather BEFORE writing):
1. Experience records since last retro: ls memory/tier3/experience-records/
2. Reflections since last retro: find instance/memory/tier2/*/reflections/ -newer (last retro timestamp) — includes L1/L2/L3 self-assessments
3. Meta-improvement contributions surfaced to CoS: search recent triggers for L3 ideas
4. Captain corrections (negative feedback patterns): grep instance/memory/tier2/*/corrections.md — rising = drift, falling = calibration
5. Captain decisions: shared/interfaces/captain-decisions.md
6. Org health audit: bash cabinet/scripts/org-health-audit.sh — workload distribution, capability gaps, idle vs busy
7. Cross-validation / peer review activity: redis-cli KEYS 'cabinet:notified:*' — were reviewers actually triggered? Did they respond?
8. Auto-compact interventions: redis-cli MGET cabinet:supervisor:autocompact-count:* — officers needing safety net suggest context exhaustion patterns
9. Officer lifecycle events: any suspended or re-hired officers since last retro
10. Supervisor restarts: redis-cli MGET cabinet:supervisor:restart-count:* — high count signals instability
11. Trigger ACK health: which officers had pending triggers age too long

COMMUNICATIONS — rich signal on cabinet dynamics:
12. Inter-officer trigger volume: for each officer, redis-cli XLEN cabinet:triggers:<officer> — total inbound traffic. High volume = popular reviewer or overloaded officer. Near-zero = isolation.
13. Sender patterns: redis-cli XRANGE to see who sent to whom — reveals collaboration graph. Officers not in the graph are isolated; officer pairs with high traffic may have coordination friction.
14. Cross-validation effectiveness: cabinet:notified:spec:* and cabinet:notified:brief:* counts — were reviewers notified? Did they respond (look for response triggers within N hours)?
15. Captain DM volume to each officer (from JSONL session logs): grep message.content for telegram_telegram__reply invocations — reveals which officers the Captain interacts with most. Overloaded DM targets may need redistributed responsibilities.
16. Warroom posts: grep send-to-group.sh usage in JSONL — how much are officers broadcasting vs staying silent?
17. Captain reactions: mcp__plugin_telegram_telegram__react in JSONL — positive reactions = calibration, negative/no reactions on significant work = drift

Patterns to look for:
- Officer in high-frequency DM with Captain but low artifact output = captain-blocked or stuck
- Officer with high inbound triggers but low outbound = receiving but not contributing
- Isolated officer pairs (no triggers between them) = coordination gap to investigate

Phase 1 RETRO: Cross-officer patterns, handoff quality, coordination gaps. Score the cabinet on improving the WORK, the WORKFLOW, the IMPROVEMENT itself (3 levels).
Phase 2 EVOLUTION: Validate draft skills against golden evals, promote validated skills.

After: redis-cli -h $REDIS_HOST -p $REDIS_PORT SET cabinet:schedule:last-run:cos:cross-officer-retro \"\$(date -u +%Y-%m-%dT%H:%M:%SZ)\" && redis-cli -h $REDIS_HOST -p $REDIS_PORT SET cabinet:reflections:count_at_last_retro \"$REFLECTIONS_NOW\""

  # trigger_send writes to stderr on XADD failure; capture stderr so we can
  # distinguish real success from silent-drop and refuse to print false-positive.
  _send_err=$(OFFICER_NAME=cron trigger_send cos "$TRIGGER_MSG" 2>&1 >/dev/null)
  _send_rc=$?
  if [ "$_send_rc" -ne 0 ] || [ -n "$_send_err" ]; then
    echo "[$TIMESTAMP] retro-trigger.sh FATAL: trigger_send failed (rc=$_send_rc, err=${_send_err:-none}) — retro NOT fired" >&2
    exit 1
  fi
  echo "[$TIMESTAMP] Retro trigger fired: $REASON"
else
  echo "[$TIMESTAMP] No retro yet: $REFLECTIONS_SINCE/$THRESHOLD reflections, ${HOURS_SINCE_RETRO}h since last (floor: 48h)"
fi
