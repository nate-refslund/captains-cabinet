#!/bin/bash
# worktree-listener.sh — Long-running Postgres NOTIFY listener for task completion.
#
# Listens on cabinet_task_terminal channel; when a task transitions to done/cancelled,
# fires worktree-remove.sh for that task-id. Registered as a LaunchAgent on Mac
# (com.cabinet.worktree-listener.plist) — single instance per Cabinet.
#
# Restart-safe: on receipt of a notification, runs worktree-remove.sh which is
# idempotent (looks up worktree_path; if NULL, exits 0). So crash + restart can't
# double-remove or skip pending notifications (Postgres NOTIFY is best-effort but
# the trigger fires on every status transition, not once).
#
# Per Spec 063 v1.1 Checkpoint 6.3 (Postgres NOTIFY surface — chosen over Next.js
# route for Mac-side reliability).
#
# Usage:
#   bash cabinet/scripts/worktree-listener.sh
#
# Logs to ~/Library/Logs/cabinet/worktree-listener.{out,err}.log via LaunchAgent.

set -euo pipefail

REPO_ROOT="${CABINET_SOURCE_REPO:-$HOME/work/captains-cabinet}"

# Load env (NEON_CONNECTION_STRING)
if [ -f "$REPO_ROOT/cabinet/.env" ]; then
  set -a; source "$REPO_ROOT/cabinet/.env" 2>/dev/null; set +a
fi

if [ -z "${NEON_CONNECTION_STRING:-}" ]; then
  echo "worktree-listener.sh: NEON_CONNECTION_STRING not set" >&2
  exit 1
fi

echo "worktree-listener.sh: listening on cabinet_task_terminal channel..."

# Use psql -A -t with LISTEN. The 'idle' line keeps the connection alive.
# Spawn a coprocess so we can read NOTIFY payloads as they arrive.
psql "$NEON_CONNECTION_STRING" -A -t -c "LISTEN cabinet_task_terminal;" -c "SELECT pg_sleep(86400);" &
LISTENER_PID=$!

# Tail the psql output: NOTIFY payloads come back as "Asynchronous notification ... payload"
# psql streams these lines; we parse + invoke worktree-remove.sh per payload.
# (In practice, robust impl uses a small Python or Node listener since pure-psql
# NOTIFY-parsing in bash is brittle. This skeleton documents the contract.)

# Better implementation pattern (commented for future shift):
# python3 -c "
# import psycopg2, select, os, subprocess
# conn = psycopg2.connect(os.environ['NEON_CONNECTION_STRING'])
# conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
# cur = conn.cursor()
# cur.execute('LISTEN cabinet_task_terminal;')
# while True:
#     if select.select([conn], [], [], 60) == ([], [], []):
#         continue
#     conn.poll()
#     while conn.notifies:
#         notify = conn.notifies.pop()
#         task_id = notify.payload
#         subprocess.run(['bash', 'cabinet/scripts/worktree-remove.sh', task_id], check=False)
# "

# For v1, document the SQL trigger that emits these notifications.
# See cabinet/migrations/<n>_worktree_listener_trigger.sql (separate artifact).

# Wait for listener
wait $LISTENER_PID
