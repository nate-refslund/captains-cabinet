#!/usr/bin/env bash
# outbox-relay.sh — Dispatch pending outbox entries to their adapters.
#
# Phase 1.4 of the convergence plan. Reads outbox_queued events from the
# ledger, dispatches each via the registered adapter (Phase 5 plugs real
# adapters: Monday/Jira/Linear/Asana/GitHub/Notion), and emits a terminal
# outbox_dispatched or outbox_failed event.
#
# Idempotency: replay-based — already-dispatched outbox ids never re-fire.
# Transient failures (network blips) emit outbox_failed with terminal=false;
# permanent failures (unknown destination) emit terminal=true.
#
# Cadence: every 60 seconds via cron / launchd. Safe to invoke ad-hoc.
#
# Usage:
#   cron/outbox-relay.sh                 — dispatch pending, print summary
#   cron/outbox-relay.sh --json          — JSON summary on stdout
#   cron/outbox-relay.sh --list-pending  — list pending entries, do not dispatch

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
exec python3 -m framework.outbox.relay "$@"
