#!/bin/bash
# run-status-sweep.sh — launchd entry point for the TEMPORARY 30-min STATUS-SWEEP.
#
# Pushes ONE status-sweep trigger to the Chair's (cos) trigger stream. This is a
# BACKSTOP to the Redis trigger Channel: the Channel (cabinet/channels/redis-trigger-channel)
# wakes officers instantly on notify-officer messages, but it cannot wake a
# slept/idle session. This cron forces a periodic sweep + status DM regardless,
# so the Chair stays responsive at the very beginning of this new setup.
#
# Mechanism (mirrors notify-officer.sh exactly): trigger_send → redis-cli XADD to
# stream cabinet:triggers:cos (group officer-cos). The redis-trigger-channel MCP
# (OFFICER_NAME=cos) is subscribed to that stream and pushes the message live into
# the Chair's Claude Code session. The Chair (the LLM) composes the digest with
# judgment — the message is NOT hardcoded into a send here; this script only
# enqueues the trigger payload telling the Chair what to sweep.
#
# Secrets: NONE read. Unlike run-frontdoor-briefing.sh (which reads the bot token
# to send), this script never sends an outbound message and never reads cabinet/.env
# — it only pushes a Redis trigger on localhost. The actual Captain DM is the Chair's,
# behind the front-door channel's own gate.
#
# TEMPORARY + reversible. Disable with:
#   launchctl bootout gui/$(id -u)/com.cabinet.status-sweep \
#     || launchctl unload ~/Library/LaunchAgents/com.cabinet.status-sweep.plist
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# launchd hands us a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin) that EXCLUDES
# Homebrew, where redis-cli lives. triggers.sh shells out to redis-cli, so without
# this the XADD silently fails and NO trigger reaches the Chair (same bug class
# that killed the 07:30 briefing on 2026-06-23). Prepend Homebrew bin.
export PATH="/opt/homebrew/bin:$PATH"

# triggers.sh defaults REDIS_HOST to "redis" (the Docker service name). On the Mac
# native deployment Redis is on localhost — match the officer/briefing plists.
export REDIS_HOST="${REDIS_HOST:-localhost}"

# Sender label that shows up in the trigger envelope (From <sender>). Identifies
# this as the periodic backstop, not another officer.
export OFFICER_NAME="status-sweep-cron"

# Source the shared trigger library (the same one notify-officer.sh uses).
. "$ROOT/cabinet/scripts/lib/triggers.sh"

read -r -d '' SWEEP_PAYLOAD <<'EOF'
STATUS SWEEP (temporary 30-min beginner cadence, backstop to the Channel): check (1) background subagents running/done/stalled, (2) officers alive + any blockers surfaced to cos, (3) screenpipe pipe health, (4) pending cos-items + Captain-items, (5) lane/CEO progress, (6) check follow-ups.md due entries (gather-then-decide) — run `bash cabinet/scripts/due-followups.sh`; for each dated follow-up whose check_from date has arrived, GATHER (verify via brain/email whether it already resolved) THEN DECIDE per its nudge_if rule (a resolved item stays silent; only a genuinely-open one near its deadline pings the Captain; mark its status: done in the register when resolved or nudged+acted). Then DM the Captain a tight status digest via the front-door channel. Quiet-OK if nothing material changed.
EOF

trigger_send cos "$SWEEP_PAYLOAD"

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] status-sweep: trigger pushed to cos (stream cabinet:triggers:cos)"
