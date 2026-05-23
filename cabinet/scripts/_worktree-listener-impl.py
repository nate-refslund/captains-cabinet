#!/usr/bin/env python3
"""
_worktree-listener-impl.py — Postgres NOTIFY listener for officer_tasks terminal transitions.

Invoked by cabinet/scripts/worktree-listener.sh (thin launcher) under the
worktree-listener LaunchAgent (com.cabinet.worktree-listener.plist).

Listens on the cabinet_task_terminal channel (fired by the trigger function
in cabinet/migrations/worktree-listener-trigger.sql). On each NOTIFY payload,
invokes worktree-remove.sh with the task id.

Audit-fix 2026-05-23: the v1 bash skeleton (psql -c "LISTEN ..." with pg_sleep)
did NOT actually stream NOTIFY payloads — psql emits "Asynchronous notification"
lines but there was no consumer parsing them. This Python implementation uses
psycopg2 (which mac Python3 + pip3 install psycopg2-binary at Phase 1.4 step).

Per Spec 063 v1.1 Checkpoint 6.3.

Usage (invoked by worktree-listener.sh):
  python3 cabinet/scripts/_worktree-listener-impl.py
"""

import os
import select
import subprocess
import sys

try:
    import psycopg2
    import psycopg2.extensions
except ImportError:
    print(
        "_worktree-listener-impl.py: psycopg2 not installed. "
        "Install with: pip3 install --user psycopg2-binary",
        file=sys.stderr,
    )
    sys.exit(1)

CONNECTION_STRING = os.environ.get("NEON_CONNECTION_STRING")
REPO_ROOT = os.environ.get("CABINET_SOURCE_REPO", os.path.expanduser("~/work/captains-cabinet"))
WORKTREE_REMOVE_SCRIPT = os.path.join(REPO_ROOT, "cabinet/scripts/worktree-remove.sh")

if not CONNECTION_STRING:
    print(
        "_worktree-listener-impl.py: NEON_CONNECTION_STRING env not set",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> int:
    conn = psycopg2.connect(CONNECTION_STRING)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("LISTEN cabinet_task_terminal;")
    print(
        "_worktree-listener-impl.py: listening on cabinet_task_terminal",
        file=sys.stderr,
    )

    while True:
        # Block up to 60s for a NOTIFY. select returns ([conn], [], []) if data is ready.
        if select.select([conn], [], [], 60) == ([], [], []):
            # No notification this 60s; loop back (keeps connection alive)
            continue
        conn.poll()
        while conn.notifies:
            notify = conn.notifies.pop(0)
            task_id = notify.payload
            print(
                f"_worktree-listener-impl.py: task_id={task_id} terminal transition; invoking worktree-remove.sh",
                file=sys.stderr,
            )
            # Invoke worktree-remove.sh — best-effort; don't crash listener on per-task error
            try:
                subprocess.run(
                    ["bash", WORKTREE_REMOVE_SCRIPT, task_id],
                    check=False,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                print(
                    f"_worktree-listener-impl.py: worktree-remove.sh timed out for task {task_id}",
                    file=sys.stderr,
                )
            except Exception as e:
                print(
                    f"_worktree-listener-impl.py: error invoking worktree-remove.sh for task {task_id}: {e}",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    sys.exit(main() or 0)
