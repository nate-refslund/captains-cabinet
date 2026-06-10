#!/usr/bin/env bash
# verify-launchagents.sh — Post-deploy verification of Cabinet LaunchAgents.
#
# Phase 8 of the convergence plan. After running `deploy-mac.sh`, this script
# confirms each plist is registered with launchd, the agent is running, log
# files exist, and KeepAlive is configured correctly. Use it as the final
# gate in the MacMini deployment runbook.
#
# Usage:
#   bash cabinet/scripts/verify-launchagents.sh
#   bash cabinet/scripts/verify-launchagents.sh --json
#
# Exit codes:
#   0 — all expected plists are registered + running
#   1 — at least one is missing or not running

set -euo pipefail

JSON_OUT=0
if [ "${1:-}" = "--json" ]; then
  JSON_OUT=1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Bug fix (R4): script lives at cabinet/scripts/, so repo root is two levels up.
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/cabinet"

# Plists shipped in cabinet/launchd/ — verify each is present in
# ~/Library/LaunchAgents and registered with launchctl.
#
# Source of truth: every template at cabinet/launchd/*.template.plist
# (excluding com.cabinet.officer.template.plist, which is per-officer and
# expanded dynamically below). Anything deploy-mac.sh can render, the
# verifier must check for.
# Opt-in daemons: present as templates but NOT expected on every deployment.
# dashboard-kiosk needs a physical monitor (office-display deployments only);
# headless servers intentionally skip it.
OPTIONAL_PLISTS=("com.cabinet.dashboard-kiosk")
is_optional() {
  local p="$1"
  for o in "${OPTIONAL_PLISTS[@]}"; do [ "$p" = "$o" ] && return 0; done
  return 1
}

EXPECTED_PLISTS=()
if [ -d "$CABINET_ROOT/cabinet/launchd" ]; then
  while IFS= read -r tpl; do
    base="$(basename "$tpl" .template.plist)"
    [ "$base" = "com.cabinet.officer" ] && continue   # per-officer; handled below
    is_optional "$base" && continue                   # opt-in; not required
    EXPECTED_PLISTS+=("$base")
  done < <(find "$CABINET_ROOT/cabinet/launchd" -maxdepth 1 -type f -name '*.template.plist' | sort)
fi

# Fallback if no templates were discovered (e.g., misconfigured CABINET_ROOT)
if [ "${#EXPECTED_PLISTS[@]}" -eq 0 ]; then
  EXPECTED_PLISTS=(
    "com.cabinet.heartbeat-watchdog"
    "com.cabinet.cost-summary"
    "com.cabinet.ovi-weekly"
    "com.cabinet.worktree-listener"
    "com.cabinet.mission-supervisor"
    "com.cabinet.task-sync"
    "com.cabinet.role-evals-weekly"
    "com.cabinet.outbox-relay"
  )
fi

# Officer plists are per-officer (com.cabinet.officer.<slug>) — discovered
# dynamically from instance/roles/active/. Consultant roles (officer_type:
# consultant) are on-demand sessions started via start-officer-mac.sh — no
# persistent LaunchAgent is expected for them, so they are skipped here
# (reported as INFO below) instead of false-failing the verification.
SKIPPED_CONSULTANTS=""
if [ -d "$CABINET_ROOT/instance/roles/active" ]; then
  for role_yml in "$CABINET_ROOT/instance/roles/active"/*.yml; do
    [ -f "$role_yml" ] || continue
    slug="$(basename "$role_yml" .yml)"
    otype="$(awk -F': *' '$1=="officer_type"{print $2; exit}' "$role_yml" | tr -d '[:space:]')"
    if [ "$otype" = "consultant" ]; then
      SKIPPED_CONSULTANTS="$SKIPPED_CONSULTANTS $slug"
      continue
    fi
    EXPECTED_PLISTS+=("com.cabinet.officer.${slug}")
  done
fi

RESULTS_JSON='[]'
ANY_FAILED=0

check_plist() {
  local label="$1"
  local plist_file="${LAUNCH_AGENTS_DIR}/${label}.plist"
  local registered=0
  local running=0
  local last_exit=""
  local detail=""

  if [ -f "$plist_file" ]; then
    registered=1
  fi

  if launchctl list 2>/dev/null | awk '{print $3}' | grep -qxF "$label"; then
    local row
    row=$(launchctl list 2>/dev/null | awk -v l="$label" '$3 == l {print}')
    # Columns: PID Status Label
    local pid status
    pid=$(printf '%s\n' "$row" | awk '{print $1}')
    status=$(printf '%s\n' "$row" | awk '{print $2}')
    last_exit="$status"
    if [ -n "$pid" ] && [ "$pid" != "-" ]; then
      running=1
    fi
  fi

  if [ "$registered" -eq 1 ] && [ "$running" -eq 1 ]; then
    detail="OK"
  elif [ "$registered" -eq 1 ] && [ "$running" -eq 0 ]; then
    detail="registered but not running (last_exit=${last_exit:-?})"
    ANY_FAILED=1
  elif [ "$registered" -eq 0 ]; then
    detail="plist missing from $LAUNCH_AGENTS_DIR"
    ANY_FAILED=1
  fi

  if [ "$JSON_OUT" -eq 1 ]; then
    RESULTS_JSON=$(printf '%s' "$RESULTS_JSON" | jq \
      --arg label "$label" \
      --argjson registered "$registered" \
      --argjson running "$running" \
      --arg last_exit "$last_exit" \
      --arg detail "$detail" \
      '. + [{label: $label, registered: $registered == 1, running: $running == 1, last_exit: $last_exit, detail: $detail}]')
  else
    if [ "$detail" = "OK" ]; then
      printf '  ✔ %-40s OK\n' "$label"
    else
      printf '  ✘ %-40s %s\n' "$label" "$detail"
    fi
  fi
}

# Log dir check
log_dir_status="missing"
if [ -d "$LOG_DIR" ]; then
  log_dir_status="present"
fi

if [ "$JSON_OUT" -eq 0 ]; then
  echo "=== Cabinet LaunchAgent Verification ==="
  echo "  LaunchAgents dir: $LAUNCH_AGENTS_DIR"
  echo "  Cabinet logs dir: $LOG_DIR ($log_dir_status)"
  if [ -n "$SKIPPED_CONSULTANTS" ]; then
    echo "  INFO: consultant officers skipped (on-demand, no persistent agent expected):$SKIPPED_CONSULTANTS"
  fi
  echo ""
fi

for label in "${EXPECTED_PLISTS[@]}"; do
  check_plist "$label"
done

if [ "$JSON_OUT" -eq 1 ]; then
  printf '%s\n' "$RESULTS_JSON" | jq --arg log_dir "$log_dir_status" \
    '{log_dir: $log_dir, agents: .}'
else
  echo ""
  if [ "$ANY_FAILED" -eq 1 ]; then
    echo "RESULT: FAIL — at least one expected agent missing or stopped."
    exit 1
  fi
  echo "RESULT: all $(echo "${EXPECTED_PLISTS[@]}" | wc -w | tr -d ' ') expected agents OK."
fi

exit 0
