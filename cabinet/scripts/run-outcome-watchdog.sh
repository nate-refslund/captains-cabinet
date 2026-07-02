#!/bin/bash
# run-outcome-watchdog.sh — launchd entry point for the cabinet's independent
# OUTCOME-monitoring watchdog (framework.watchdog.check).
#
# WHY THIS EXISTS (2026-06-29): every existing monitor checks that a PROCESS ran
# (exit 0, launchd "active", pipe-health green) — NONE verify the OUTCOME
# actually happened. On 2026-06-29 the 07:30 briefing job exited clean while its
# Telegram send 400'd silently; the undelivered backlog snowballed to 77 items
# over days, fully invisible. This watchdog adds the missing OUTCOME-verification
# layer: it evaluates a declarative registry of "what should be TRUE" and routes
# failures (auto-fix the deterministic-safe ones, escalate judgment ones to the
# Chair, file drift notes) — and stamps its own heartbeat for the dead-man's
# switch (the screenpipe pipe-watchdog pings the Chair if this heartbeat staleens).
#
# INDEPENDENCE is the whole point: the checker is stdlib-only and imports NOTHING
# it watches, so a broken watched system can't break the watchdog. This wrapper
# adds nothing heavy — it only fixes the launchd-PATH gotcha + points Redis at
# localhost, then execs the checker.
#
# Secrets: NONE read here. The checker's only outbound is a Redis trigger on
# localhost (the Chair turns it into a gated send) — the bot token never enters
# this process. Reversible: `launchctl bootout` the plist.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# launchd hands a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin) that EXCLUDES
# Homebrew, where redis-cli AND the brew python live. Without this the checker's
# redis reads silently return "" (every outcome looks unverifiable) and the
# `-m` python invocation can't find python3.12 — the exact PATH bug class that
# killed the 07:30 briefing on 2026-06-23. Prepend Homebrew bin.
export PATH="/opt/homebrew/bin:$PATH"

# triggers.sh + the checker default REDIS_HOST to "redis" (Docker service name).
# The Mac-native deployment runs Redis on localhost — match the officer/briefing
# plists so the Chair-escalation XADD and the heartbeat land on the right server.
export REDIS_HOST="${REDIS_HOST:-localhost}"
export REDIS_PORT="${REDIS_PORT:-6379}"

# Captain timezone for the briefing-slot math (the registry asserts "delivered by
# 07:30 + 19:30 LOCAL"). Sourced from platform.yml; fall back to the documented
# default. Read ONLY this one line (never source the whole config).
CAPTAIN_TZ_LINE="$(grep '^captain_timezone:' "$ROOT/instance/config/platform.yml" 2>/dev/null | awk '{print $2}')"
export CABINET_CAPTAIN_TZ="${CABINET_CAPTAIN_TZ:-${CAPTAIN_TZ_LINE:-Europe/Berlin}}"

PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
cd "$ROOT" || exit 1

# Stamp a wrapper-level heartbeat too (belt-and-suspenders): if the python
# checker itself crashes before stamping, this line still proves the WRAPPER
# fired this cycle. The dead-man's switch reads the checker's heartbeat (which
# only stamps on a successful sweep), so a wrapper-ran-but-checker-crashed case
# is exactly what we want the survivor to catch — we do NOT stamp the checker key
# here. This is just a log line.
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] outcome-watchdog: wrapper firing (tz=$CABINET_CAPTAIN_TZ)"

exec "$PY" -m framework.watchdog.check
