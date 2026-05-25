#!/bin/bash
# One-shot officer restart at 03:00 Berlin = 01:00 UTC.
# Captain msg 2078 (2026-04-27 21:28 UTC): authorized restart at 3 AM so officers
# pick up the new pre-send refine hook + voice-context changes that ship in
# settings.json + send-voice.sh and don't hot-reload mid-session.
#
# Self-deletes its triggering cron line in /etc/crontab after firing so this
# is genuinely one-shot — not a recurring nightly disruption.
#
# Reversibility: restarting officers is reversible (supervisor auto-respawns
# claude --continue with prior session id). The cron line is removed by this
# script's own sed; if the script is re-armed, the line is re-added.

set -e
LOG=/var/log/cabinet/restart-officers-oneshot.log
mkdir -p "$(dirname "$LOG")"
echo "=== $(date -u +%FT%TZ) — restart-all-officers-oneshot fired ===" >> "$LOG"

# Restart both officer containers. supervisor inside each respawns the claude
# sessions with --continue, preserving conversation history. New sessions
# read settings.json fresh, so the new hooks become active.
# List your officer containers here (one per project/cabinet)
for container in cabinet-officers; do
  if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
    echo "Restarting $container..." >> "$LOG"
    docker restart "$container" >> "$LOG" 2>&1 || echo "WARN: restart $container failed" >> "$LOG"
  else
    echo "skip $container — not running" >> "$LOG"
  fi
done

# Self-delete the triggering cron line so this is truly one-shot.
if grep -q 'restart-all-officers-oneshot.sh' /etc/crontab; then
  sed -i '/restart-all-officers-oneshot.sh/d' /etc/crontab
  echo "self-deleted from /etc/crontab" >> "$LOG"
else
  echo "no triggering cron line to delete (already removed)" >> "$LOG"
fi

echo "=== done ===" >> "$LOG"
