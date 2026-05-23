#!/bin/bash
# worktree-listener.sh — Thin launcher for the Python Postgres NOTIFY listener.
#
# Per Spec 063 v1.1 Checkpoint 6.3 + audit-fix 2026-05-23 (the v1 bash psql
# skeleton did NOT actually stream NOTIFY payloads — psql emitted them but
# no consumer parsed them).
#
# The real listener implementation is _worktree-listener-impl.py (uses
# psycopg2 to LISTEN on cabinet_task_terminal channel and invoke
# worktree-remove.sh per payload).
#
# This wrapper exists so the LaunchAgent (com.cabinet.worktree-listener.plist)
# can point at a .sh entry — keeps the entry point stable while implementation
# lives in Python. Also handles dependency check + exec into Python.

set -uo pipefail

REPO_ROOT="${CABINET_SOURCE_REPO:-$HOME/work/captains-cabinet}"

# Load env (NEON_CONNECTION_STRING)
if [ -f "$REPO_ROOT/cabinet/.env" ]; then
  set -a; source "$REPO_ROOT/cabinet/.env" 2>/dev/null; set +a
fi

if [ -z "${NEON_CONNECTION_STRING:-}" ]; then
  echo "worktree-listener.sh: NEON_CONNECTION_STRING not set in env" >&2
  exit 1
fi

PYTHON3=$(command -v python3 || true)
if [ -z "$PYTHON3" ]; then
  echo "worktree-listener.sh: python3 not found in PATH. Phase 1.4 should brew install python." >&2
  exit 1
fi

# Verify psycopg2 importable (Phase 1.4 should pip3 install --user psycopg2-binary)
if ! "$PYTHON3" -c "import psycopg2" 2>/dev/null; then
  echo "worktree-listener.sh: psycopg2 not installed. Run: pip3 install --user psycopg2-binary" >&2
  exit 1
fi

# Exec the Python listener (replaces this shell process; LaunchAgent KeepAlive
# restarts us if the Python crashes).
exec "$PYTHON3" "$REPO_ROOT/cabinet/scripts/_worktree-listener-impl.py"
