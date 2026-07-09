#!/bin/bash
# restart-all-officers-oneshot.sh — one-shot FLEET restart, DEPLOYMENT-AWARE.
#
# Officers pick up new settings.json / .mcp.json / framework code that do NOT
# hot-reload mid-session (a newly registered MCP server, a hook change, a
# pre-send refine hook). The supervisor respawns each claude session with
# --continue, so conversation history is preserved — restarting is reversible.
#
# DISPATCH by the real deployment (mirrors germline-lock.sh's schg|ro-mount
# backend split — infra dispatch on what is actually deployed, chosen by
# probing the host, never a hardcoded assumption):
#   * native launchd Mac (the live deployment since 2026-07-04) — officer
#     LaunchAgents present → reload each via reload-officer-mac.sh
#     (launchctl bootout → bootstrap; picks up the fresh merged .mcp.json).
#   * docker host (server deployment, cabinet/deploy/docker/) — cabinet officer
#     containers present → docker restart them, then self-delete the triggering
#     /etc/crontab line so the cron-armed run is truly one-shot.
#
# Historic note: before 2026-07-04 this script was docker-only (Hetzner
# /opt/founders-cabinet). On a native Mac that path no-ops loudly (`docker:
# command not found`); the native branch below is the fix (Captain 2026-07-09).
set -e
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || { echo "cannot cd $REPO" >&2; exit 1; }

# --- native launchd Mac: reload every loaded officer LaunchAgent -------------
# `com.cabinet.officer.<role>` (incl. cos-inbound); the `officer-supervisor-mac`
# label has a HYPHEN after officer, so the `officer\.` (dot) pattern correctly
# skips it — we never bounce the supervisor that would respawn the fleet.
MAC_AGENTS="$(launchctl list 2>/dev/null | awk '/com\.cabinet\.officer\.[a-z]/{print $3}')"
if [ -n "$MAC_AGENTS" ]; then
  n=$(printf '%s\n' "$MAC_AGENTS" | grep -c .)
  echo "restart-fleet: native launchd Mac — reloading $n officer agent(s)"
  rc=0
  while IFS= read -r label; do
    [ -n "$label" ] || continue
    officer="${label#com.cabinet.officer.}"
    echo "  reloading $officer ..."
    bash cabinet/scripts/reload-officer-mac.sh "$officer" || { echo "  WARN: reload $officer failed" >&2; rc=1; }
  done <<< "$MAC_AGENTS"
  echo "restart-fleet: done (native launchd)"
  exit "$rc"
fi

# --- docker host: restart the officer containers + self-delete the cron line -
if command -v docker >/dev/null 2>&1; then
  LOG=/var/log/cabinet/restart-officers-oneshot.log
  mkdir -p "$(dirname "$LOG")" 2>/dev/null || LOG=/dev/stderr
  echo "=== $(date -u +%FT%TZ) — restart-fleet (docker) fired ===" >> "$LOG"
  restarted=0
  for container in sensed-officers personal-cabinet-officers; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
      echo "Restarting $container..." >> "$LOG"
      docker restart "$container" >> "$LOG" 2>&1 && restarted=$((restarted+1)) \
        || echo "WARN: restart $container failed" >> "$LOG"
    else
      echo "skip $container — not running" >> "$LOG"
    fi
  done
  # Self-delete the triggering cron line so a cron-armed run is truly one-shot.
  if [ -f /etc/crontab ] && grep -q 'restart-all-officers-oneshot.sh' /etc/crontab; then
    sed -i '/restart-all-officers-oneshot.sh/d' /etc/crontab
    echo "self-deleted from /etc/crontab" >> "$LOG"
  fi
  echo "=== done (docker, restarted=$restarted) ===" >> "$LOG"
  echo "restart-fleet: done (docker, restarted=$restarted)"
  exit 0
fi

echo "restart-fleet: no fleet detected — no launchd officer agents (native Mac) " \
     "and no docker (server host). Nothing to restart." >&2
exit 1
