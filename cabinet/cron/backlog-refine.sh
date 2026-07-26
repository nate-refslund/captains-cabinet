#!/bin/bash
# backlog-refine.sh — Triggers the backlog owner to refine the backlog.
# Target officer: BACKLOG_REFINE_OFFICER (default cos — the CPO seat was
# retired; the live roster is cos + lane CEOs + comms-officer). Scheduled
# via the cabinet/services.yml row `backlog-refine` (daily); this header
# used to claim 12h/CPO — fixed 2026-07-09 (W10: the cron fired into a
# dead officer stream for as long as the CPO seat has been retired).

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

TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M:%S UTC')

# B4 Mac portability (matches cabinet/scripts/lib/triggers.sh): an explicit
# REDIS_HOST (the generated launchd wrapper sets localhost) WINS; REDIS_URL is
# the fallback for docker deployments that set it in the compose env. The old
# unconditional derive clobbered the wrapper's REDIS_HOST with the docker-era
# `redis` hostname → FATAL on every Mac-native run (2026-07-10 deploy).
REDIS_URL="${REDIS_URL:-redis://localhost:6379}"
REDIS_HOST="${REDIS_HOST:-$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)}"
REDIS_PORT="${REDIS_PORT:-$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)}"

TRIGGER_MSG="[$TIMESTAMP] Scheduled backlog refinement. Review /tasks for new items + status drift, incorporate recent research briefs from shared/interfaces/research-briefs/, update priorities in shared/backlog.md, and ensure top items have specs in shared/interfaces/product-specs/."

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

# PRIMARY: Push to Redis Stream
if [ ! -f "$TRIGGERS_LIB" ]; then
  echo "[$TIMESTAMP] backlog-refine.sh FATAL: triggers lib not found at $TRIGGERS_LIB (CABINET_ROOT=$CABINET_ROOT) — trigger NOT pushed" >&2
  exit 1
fi
# shellcheck source=/dev/null
. "$TRIGGERS_LIB"
if ! declare -f trigger_send > /dev/null; then
  echo "[$TIMESTAMP] backlog-refine.sh FATAL: trigger_send not defined after sourcing $TRIGGERS_LIB — trigger NOT pushed" >&2
  exit 1
fi

# trigger_send writes to stderr on XADD failure; capture stderr so we can
# distinguish real success from silent-drop and refuse to print false-positive.
TARGET_OFFICER="${BACKLOG_REFINE_OFFICER:-cos}"
_send_err=$(OFFICER_NAME=cron trigger_send "$TARGET_OFFICER" "$TRIGGER_MSG" 2>&1 >/dev/null)
_send_rc=$?
if [ "$_send_rc" -ne 0 ] || [ -n "$_send_err" ]; then
  echo "[$TIMESTAMP] backlog-refine.sh FATAL: trigger_send failed (rc=$_send_rc, err=${_send_err:-none}) — trigger NOT pushed" >&2
  exit 1
fi

echo "[$TIMESTAMP] Backlog refinement trigger pushed to $TARGET_OFFICER"
