#!/usr/bin/env bash
# task-sync.sh — Bidirectional sync between Cabinet's canonical tasks and
# the configured external task system (Jira / Linear / Asana / GitHub
# Issues; Monday is plugin-routed — see task_adapters/base.py).
#
# Phase 5 of the convergence plan. Reads `instance/config/projects/<active>.yml`,
# instantiates the adapter named in `tasks.system`, and runs a sync cycle.
# Plugin-routed / block-less projects are a clean no-op (INFO line, exit 0).
#
# Cadence: every 15 minutes via the cabinet/services.yml `task-sync` row
# (interval_s: 900, rendered by generate-plists.py). That row is THE cadence
# truth — the old 5-min header claim and the hand-kept task-sync template
# plist were both deleted 2026-07-17 (adapter kit).
#
# Usage:
#   cron/task-sync.sh             — sync once, print summary
#   cron/task-sync.sh --health    — just health-check the adapter, exit 0/1
#   cron/task-sync.sh --json      — JSON summary on stdout

set -euo pipefail

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

cd "$CABINET_ROOT"
# Bare `python3` under launchd resolves to /usr/bin/python3 (system 3.9) on a
# stock Mac; the runner + adapters target 3.12 (`X | Y` unions). Same pin as
# cabinet/cron/self-improvement-loop.sh.
PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
command -v "$PY" >/dev/null 2>&1 || PY=python3
exec "$PY" -m cabinet.scripts.task_sync_runner "$@"
