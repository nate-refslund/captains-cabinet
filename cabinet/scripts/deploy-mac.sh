#!/bin/bash
# deploy-mac.sh — Orchestrate Mac native Cabinet deployment.
#
# Substitutes envsubst variables against plist templates in cabinet/launchd/,
# writes them to ~/Library/LaunchAgents/, then bootstraps via launchctl.
#
# Usage:
#   bash cabinet/scripts/deploy-mac.sh --officer <officer>     # deploy one officer
#   bash cabinet/scripts/deploy-mac.sh --officer all           # deploy all 5 officers
#   bash cabinet/scripts/deploy-mac.sh --daemon <name>         # deploy a non-officer service
#                                                              #   (heartbeat-watchdog, cost-summary, worktree-listener)
#   bash cabinet/scripts/deploy-mac.sh --all                   # deploy everything
#   bash cabinet/scripts/deploy-mac.sh --dry-run               # show what would be done, don't execute
#
# Per Spec 059 v1.1 Checkpoint 2.8 (envsubst + WorkingDirectory + SoftResourceLimits + KeepAlive ratifications).

set -euo pipefail

REPO_ROOT="${CABINET_SOURCE_REPO:-$HOME/work/captains-cabinet}"
LAUNCHD_DIR="$HOME/Library/LaunchAgents"
LOGS_DIR="$HOME/Library/Logs/cabinet"
TEMPLATES_DIR="$REPO_ROOT/cabinet/launchd"

OFFICER=""
DAEMON=""
ALL=false
DRY_RUN=false

while [ $# -gt 0 ]; do
  case "$1" in
    --officer) OFFICER="${2:?--officer requires a name (or 'all')}"; shift 2 ;;
    --daemon)  DAEMON="${2:?--daemon requires a name}"; shift 2 ;;
    --all)     ALL=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    *) echo "deploy-mac.sh: unknown flag '$1'" >&2; exit 64 ;;
  esac
done

mkdir -p "$LAUNCHD_DIR" "$LOGS_DIR"

# envsubst-render a template → final plist + bootstrap (or just print if --dry-run)
deploy_plist() {
  local template="$1" final="$2" label="$3"
  if [ ! -f "$template" ]; then
    echo "deploy-mac.sh: template not found: $template" >&2
    return 1
  fi

  # Build envsubst input — only substitute the variables we care about
  # (avoids accidentally consuming other env vars in the template)
  local rendered
  rendered=$(OFFICER="$OFFICER_VAR" USER="$(id -un)" HOME="$HOME" REPO_ROOT="$REPO_ROOT" \
    envsubst '$OFFICER $USER $HOME $REPO_ROOT' < "$template")

  if $DRY_RUN; then
    echo "=== WOULD-WRITE $final ==="
    echo "$rendered"
    echo "=== WOULD-BOOTSTRAP $label ==="
    return 0
  fi

  echo "$rendered" > "$final"
  chmod 644 "$final"

  # If already loaded, bootout first (idempotent)
  if launchctl print "gui/$(id -u)/$label" >/dev/null 2>&1; then
    launchctl bootout "gui/$(id -u)" "$final" 2>/dev/null || true
    sleep 1
  fi

  launchctl bootstrap "gui/$(id -u)" "$final" || {
    echo "deploy-mac.sh: bootstrap failed for $label" >&2
    return 2
  }
  echo "deployed: $label"
}

# Officer deployment
deploy_officer() {
  local officer="$1"
  OFFICER_VAR="$officer"
  deploy_plist \
    "$TEMPLATES_DIR/com.cabinet.officer.template.plist" \
    "$LAUNCHD_DIR/com.cabinet.officer.$officer.plist" \
    "com.cabinet.officer.$officer"
}

# Daemon deployment (heartbeat-watchdog, cost-summary, worktree-listener)
deploy_daemon() {
  local daemon="$1"
  OFFICER_VAR=""  # daemons don't use OFFICER
  deploy_plist \
    "$TEMPLATES_DIR/com.cabinet.$daemon.template.plist" \
    "$LAUNCHD_DIR/com.cabinet.$daemon.plist" \
    "com.cabinet.$daemon"
}

# Execute
if [ "$ALL" = true ]; then
  for o in cos cto cpo cro coo; do deploy_officer "$o"; done
  for d in heartbeat-watchdog cost-summary worktree-listener; do deploy_daemon "$d"; done
elif [ "$OFFICER" = "all" ]; then
  for o in cos cto cpo cro coo; do deploy_officer "$o"; done
elif [ -n "$OFFICER" ]; then
  deploy_officer "$OFFICER"
elif [ -n "$DAEMON" ]; then
  deploy_daemon "$DAEMON"
else
  echo "Usage: deploy-mac.sh [--officer <name>|all] [--daemon <name>] [--all] [--dry-run]" >&2
  exit 64
fi

exit 0
