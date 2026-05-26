#!/usr/bin/env bash
# task-sync.sh — Bidirectional sync between Cabinet's canonical tasks and
# the configured external task system (Monday / Jira / Linear / Asana /
# GitHub Issues).
#
# Phase 5 of the convergence plan. Reads `instance/config/projects/<active>.yml`,
# instantiates the adapter named in `tasks.system`, and runs a sync cycle.
#
# Cadence: every 5 minutes via launchd (configured in cabinet/launchd/).
#
# Usage:
#   cron/task-sync.sh             — sync once, print summary
#   cron/task-sync.sh --health    — just health-check the adapter, exit 0/1
#   cron/task-sync.sh --json      — JSON summary on stdout

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

cd "$CABINET_ROOT"
exec python3 -m cabinet.scripts.task_sync_runner "$@"
