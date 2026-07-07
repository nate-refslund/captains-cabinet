#!/bin/bash
# apoptosis-sweep.sh — entry point for the cabinet's hygiene / apoptosis organ
# (framework.hygiene.apoptosis). SCHEDULED since 2026-07-07: fleet manifest
# row `apoptosis-sweep` (cabinet/services.yml, daily 03:45 local) + template
# cabinet/launchd/com.cabinet.apoptosis-sweep.template.plist instantiated
# into ~/Library/LaunchAgents.
#
# WHAT IT RUNS: one hygiene sweep with a born-safe polarity —
#   * DIRECT action only for trivially-regenerable exhaust: gzip-rotate log
#     files past the retention windows named in instance/config/retention.yml
#     (originals archived into <dir>/archive/ before any removal; every delete
#     realpath-jailed to the designated log dirs), and delete __pycache__ dirs
#     under the repo when they exceed the size cap (Python regenerates them).
#   * PROPOSE-ONLY cards for anything irreversible (stale worktrees, dormant
#     skills, long-disabled services, never-instantiated launchd templates):
#     findings ride the existing front-door intake stream
#     (cabinet:frontdoor:intake) as one-tap decision cards for the Captain.
#     This script never removes any of those.
#
# SELF-HEARTBEAT: a completed sweep appends one line to
# ~/.cabinet/logs/apoptosis-sweep.log — the per-service log location the
# outcome-watchdog derives freshness floors from, so once the fleet manifest
# enrolls an 'apoptosis-sweep' row, silence of this organ is itself noticed.
#
# Secrets: NONE read here. Only localhost Redis is touched (the intake XADD).
# Reversible: propose-only for everything irreversible; rotated logs live on
# as .gz archives next to their dir.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# launchd hands a minimal PATH that excludes Homebrew (where redis-cli and the
# brew python live) — the exact PATH bug class that killed the 07:30 briefing
# on 2026-06-23. Prepend Homebrew bin. Same posture as run-outcome-watchdog.sh.
export PATH="/opt/homebrew/bin:$PATH"

# The Mac-native deployment runs Redis on localhost (intake's default is the
# Docker-era service name).
export REDIS_HOST="${REDIS_HOST:-localhost}"
export REDIS_PORT="${REDIS_PORT:-6379}"

# Inject the deployment's retention config — framework code never names the
# config layer itself (three-layer gate); this glue script is the sanctioned
# injection point, mirroring run-probes.sh / CABINET_PROBES_CONFIG.
export CABINET_RETENTION_CONFIG="${CABINET_RETENTION_CONFIG:-$ROOT/instance/config/retention.yml}"

PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
cd "$ROOT" || exit 1

exec "$PY" -m framework.hygiene.apoptosis "$@"
