#!/usr/bin/env bash
# outbox-relay.sh — Dispatch pending outbox entries to their adapters.
#
# LEGACY mode (default): reads outbox_queued events from the event ledger,
# dispatches each via the registered adapter (Phase 5 plugs real adapters:
# Monday/Jira/Linear/Asana/GitHub/Notion), and emits a terminal
# outbox_dispatched or outbox_failed event. Replay-based idempotency.
#
# COG-1 TABLE-DRAIN mode (--drain-tasks-outbox, or COG1_DRAIN_TASKS_OUTBOX=1):
# drains the co-committed officer_tasks_outbox table for the tasks pilot
# (docs/plans/cognitive-core-phase-1-contract-2026-07-20.md §6). This mode is
# OFF by default and armed only after the §8.2 arming step. When it is armed
# this wrapper runs a FAIL-LOUD preflight (below) — an unarmed/misconfigured
# drain must never fill rows nothing drains, or silently die on a missing
# driver.
#
# Interpreter: python3.12 (house rule — replaces the old bare `python3` exec;
# launchd/cron carry a bare PATH so the interpreter is resolved explicitly).
# S0 pin: the production work store is PostgreSQL 17.10, so the drain path
# needs psycopg2 in THIS interpreter.
#
# Cadence: every 60 seconds via cron / launchd. Safe to invoke ad-hoc.
#
# Usage:
#   cron/outbox-relay.sh                    — legacy: dispatch pending, summary
#   cron/outbox-relay.sh --json             — JSON summary on stdout
#   cron/outbox-relay.sh --list-pending     — list pending entries, no dispatch
#   cron/outbox-relay.sh --drain-tasks-outbox --dsn <conninfo>   — COG-1 drain

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

# --- Resolve the house interpreter python3.12 (bare `python3` is banned:
# hermetic/launchd shells resolve a different major without an explicit path).
PY="${CABINET_PYTHON:-}"
if [ -z "$PY" ]; then
  for _cand in /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 \
               "$(command -v python3.12 2>/dev/null || true)"; do
    if [ -n "$_cand" ] && [ -x "$_cand" ]; then PY="$_cand"; break; fi
  done
fi
if [ -z "$PY" ] || \
   ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info[:2]==(3,12) else 1)' 2>/dev/null; then
  echo "outbox-relay FATAL: python3.12 not found (house interpreter required — set CABINET_PYTHON)" >&2
  exit 70
fi

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

# --- COG-1 drain preflight (fail-loud when the table drain is armed) --------
# "Armed" = the flag is passed OR the env arms it. When armed, BOTH the
# Postgres driver AND the authority pointer must be usable, else refuse loudly
# (a broken drain must never masquerade as a running one — §8.2).
_drain_on=0
for _a in "$@"; do [ "$_a" = "--drain-tasks-outbox" ] && _drain_on=1; done
[ "${COG1_DRAIN_TASKS_OUTBOX:-}" = "1" ] && _drain_on=1

if [ "$_drain_on" = "1" ]; then
  # (a) driver present in the pinned interpreter
  if ! "$PY" -c 'import psycopg2' 2>/dev/null; then
    echo "outbox-relay FATAL: --drain-tasks-outbox needs psycopg2 in $PY (arming preflight failed)" >&2
    exit 71
  fi
  # (b) authority pointer: ABSENT => legacy fail-safe (fine, pre-cutover);
  #     present-but-UNREADABLE => a real misconfiguration, refuse loudly.
  _ptr="${CABINET_COG1_AUTHORITY:-$HOME/.cabinet/state/cog1-authority}"
  if [ -e "$_ptr" ] && [ ! -r "$_ptr" ]; then
    echo "outbox-relay FATAL: COG-1 authority pointer '$_ptr' exists but is unreadable (arming preflight failed)" >&2
    exit 72
  fi
fi

cd "$CABINET_ROOT"

# Hand off to the pinned interpreter. If the env armed the drain but the flag
# was not passed explicitly, inject it so the relay actually drains the table.
if [ "$_drain_on" = "1" ]; then
  case " $* " in
    *" --drain-tasks-outbox "*) exec "$PY" -m framework.outbox.relay "$@" ;;
    *)                          exec "$PY" -m framework.outbox.relay --drain-tasks-outbox "$@" ;;
  esac
else
  exec "$PY" -m framework.outbox.relay "$@"
fi
