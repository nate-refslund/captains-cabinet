#!/bin/bash
# cabinet/scripts/due-at-reminder-tick.sh — Spec 041 cron worker
#
# Drains officer_tasks rows where due_at <= NOW() AND status IN (queue, wip)
# AND reminder_fired_at IS NULL. Atomic SELECT-FOR-UPDATE-SKIP-LOCKED + UPDATE
# pattern in a single CTE statement; rows are claimed + marked fired in the
# same transaction. For each claimed row, pushes a task_reminder trigger to
# the owning officer's Redis stream via trigger_send.
#
# Scheduled by the FLEET MANIFEST, not a hand-written crontab: the
# cabinet/services.yml row `due-at-reminder-tick` (kind: cron, interval_s
# 300) is rendered to
# cabinet/launchd/generated/com.cabinet.due-at-reminder-tick.plist by
# cabinet/scripts/generate-plists.py. That generated wrapper cd's to the repo
# root, `source cabinet/.env`, then `exec`s this one command every 5 minutes
# (install the plist via deploy-mac.sh / cabinet-bootstrap, same Captain-arm
# step as every other cron row). Interval (not a calendar slot) because "fire
# within ~5 min of due_at" is a cadence, not a wall-clock time.
#
# Connection string: reads CONN > NEON_CONNECTION_STRING > DATABASE_URL. The
# generated wrapper sources cabinet/.env before exec; this script ALSO sources
# it (below) so a direct invocation (officer shell / manual / test) resolves
# the same conn string. In Work Cabinet, NEON_CONNECTION_STRING points at the
# tasks Neon (where officer_tasks lives — same DB the dashboard reads).
# Personal Cabinet points at its own postgres. No conn string on the box =
# degrade LOUDLY (one stderr line, exit 0), never invent cred plumbing.
#
# Idempotent: re-running after a fire produces zero new triggers for the
# same task. Re-arm trigger (officer_tasks_due_at_rearm_trg) clears
# reminder_fired_at on any due_at change so the new time can fire.
#
# Exits 0 always — never block the next cron run.

set -u

# Resolve the repo root from THIS script's own location so it works on the Mac
# box, a fresh clone, or any checkout path — never the convergence-era absolute
# /opt path (mirrors memory-reconcile.sh / memory-worker.sh /
# run-status-sweep.sh).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
export CABINET_ROOT

# launchd runs carry no login env. The generated plist already sources
# cabinet/.env before exec'ing us; sourcing it here too lets a DIRECT run
# (officer shell / manual / test) resolve the same NEON_CONNECTION_STRING.
# set -a exports it into psql's env; secrets stay in the file and nothing here
# echoes a value (same discipline as memory-reconcile.sh).
set -a
# shellcheck disable=SC1091
source "$CABINET_ROOT/cabinet/.env" 2>/dev/null
set +a

# Mac-native Redis defaults for triggers.sh -> redis-cli. The plist sets
# REDIS_HOST=localhost; a direct run needs the same default (Docker exports its
# own REDIS_HOST/REDIS_PORT, so these only fill the empty case).
export REDIS_HOST="${REDIS_HOST:-localhost}"
export REDIS_PORT="${REDIS_PORT:-6379}"

CONN="${CONN:-${NEON_CONNECTION_STRING:-${DATABASE_URL:-}}}"
if [ -z "$CONN" ]; then
  echo "[due-at-reminder-tick] no DB connection string set (CONN | NEON_CONNECTION_STRING | DATABASE_URL) — degrading loudly, nothing fired" >&2
  exit 0
fi

# Shared trigger library (redis-cli XADD to the owning officer's stream +
# idle-session wake). The old hardcoded convergence-era /opt path did not
# exist on the Mac box, so trigger_send was undefined and EVERY fire silently
# failed (the dead-limb bug the tick-live lane fixed). Sourced SCRIPT-relative
# (not $CABINET_ROOT-relative): a CABINET_ROOT override points at a different
# RUNTIME root (instance config, .env, needs ledger — the test harnesses use a
# tmp one), but code always lives beside code.
# shellcheck disable=SC1091
. "$SCRIPT_DIR/lib/triggers.sh"

# Identify the worker for trigger sender attribution + log readability.
export OFFICER_NAME="${OFFICER_NAME:-due-at-reminder}"

# Captain-arm helper (owner-slug resolution, card filing, verdict reconcile).
ARM="$SCRIPT_DIR/captain-reminder-arm.py"
PY="${PYTHON:-python3.12}"
# The Captain owner slug (framework.env.captain_slug()). A claimed row that is
# type='reminder' OR owned by this slug routes to the needs-ledger one-tap card
# surface instead of an officer's Redis stream. Resolved once; if the resolver
# is down CAPTAIN_SLUG is empty and only the type='reminder' signal routes, so a
# real officer row can never be mis-carded.
CAPTAIN_SLUG="$("$PY" "$ARM" owner-slug 2>/dev/null || true)"
# Snooze bump window — the needs SNOOZE_DAYS constant (framework.authority.needs
# SNOOZE_DAYS = 7); env-overridable for parity with a re-tuned needs window.
SNOOZE_DAYS="${SNOOZE_DAYS:-7}"

# Atomic claim + mark in a single statement. CTE FOR UPDATE SKIP LOCKED prevents
# two ticks from double-firing the same row; the outer UPDATE flips
# reminder_fired_at on those locked rows; RETURNING gives the work payload.
# LIMIT 100 = safety cap per tick (spec §cron-worker).
#
# RETURNING carries ONLY the machine-controlled routing fields
# (id, officer_slug, due_at, type) — the untrusted title is DELIBERATELY ABSENT.
# BOTH routes re-read the exact title by id below (parameterized ::bigint), so a
# newline OR tab embedded in a title can never forge a synthetic claim row, shift
# a routing field, or truncate a benign one: no title byte ever transits the
# claim TSV. (An earlier revision streamed the title LAST; a newline still
# spawned a second physical line that survived the tab filter as a forged
# officer-routing row — closed by dropping title from the stream entirely.)
#
# psql -tA emits a trailing "UPDATE N" status line on RETURNING UPDATE statements
# even with --tuples-only. Filter to lines containing a tab (valid row delimiter)
# so the status line is dropped before the row loop.
RAW="$(psql "$CONN" -tA -F $'\t' --no-psqlrc -v ON_ERROR_STOP=1 -c "
WITH due_tasks AS (
  SELECT id
  FROM officer_tasks
  WHERE due_at IS NOT NULL
    AND due_at <= NOW()
    AND status IN ('queue', 'wip')
    AND reminder_fired_at IS NULL
  ORDER BY due_at ASC
  LIMIT 100
  FOR UPDATE SKIP LOCKED
)
UPDATE officer_tasks
SET reminder_fired_at = NOW()
WHERE id IN (SELECT id FROM due_tasks)
RETURNING id, officer_slug, due_at, type;
" 2>&1)"
psql_rc=$?

if [ $psql_rc -ne 0 ]; then
  echo "[due-at-reminder-tick] psql failed rc=$psql_rc output=${RAW}" >&2
  exit 0
fi

# Keep only lines containing the tab field separator (drop the "UPDATE N" status).
ROWS="$(printf '%s\n' "$RAW" | grep -E $'\t' || true)"

count=0        # officer triggers sent
carded=0       # Captain cards filed
bumped=0       # snoozed reminders re-armed
fail=0
now_iso="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# --- fire phase: route each claimed row -------------------------------------
# A row is a CAPTAIN reminder when type='reminder' OR its owner is the Captain
# slug → needs-ledger one-tap card; otherwise it is an OFFICER reminder → the
# owning officer's Redis stream (the pre-existing Spec 041 behavior).
if [ -n "$ROWS" ]; then
  while IFS=$'\t' read -r task_id officer_slug due_at rtype; do
    [ -z "$task_id" ] && continue
    # Both routes need a bare-integer id: the by-id title re-read and the Captain
    # card's file-card --task-id ::bigint-bind it, and the officer payload's
    # --argjson id requires numeric JSON. A non-numeric id can only be a corrupt
    # claim stream — skip it loudly, never let it reach a query or a payload.
    if ! [[ "$task_id" =~ ^[0-9]+$ ]]; then
      fail=$((fail + 1))
      echo "[due-at-reminder-tick] non-numeric task_id skipped: $task_id" >&2
      continue
    fi
    # Re-read the EXACT title by id (parameterized ::bigint; newline/tab/quote/
    # $()-safe). The untrusted title is NEVER carried on the claim TSV, so an
    # embedded delimiter can neither forge a synthetic routing row nor truncate a
    # benign one — the title stays DATA end-to-end for BOTH routes. The :'id'
    # bind is fed on STDIN (heredoc), NOT -c: psql interpolates variables only
    # for STDIN/-f input, never a -c string — matching my-tasks.sh's discipline.
    real_title="$(psql "$CONN" -tA --no-psqlrc -v ON_ERROR_STOP=1 \
      -v id="$task_id" <<'SQL' 2>/dev/null
SELECT title FROM officer_tasks WHERE id = :'id'::bigint;
SQL
    )"
    if [ "$rtype" = "reminder" ] || { [ -n "$CAPTAIN_SLUG" ] && [ "$officer_slug" = "$CAPTAIN_SLUG" ]; }; then
      # Captain reminder → one-tap card. Stream the title to the arm on stdin, so
      # it never transits argv or a TSV field.
      if printf '%s' "$real_title" | "$PY" "$ARM" file-card \
           --task-id "$task_id" --due-at "$due_at" >/dev/null 2>&1; then
        carded=$((carded + 1))
      else
        fail=$((fail + 1))
        echo "[due-at-reminder-tick] file-card failed task_id=$task_id" >&2
      fi
      continue
    fi
    # Officer reminder → the owning officer's stream. jq -n --arg binds the
    # by-id title as a literal JSON string (no shell/JSON injection).
    payload="$(jq -cn \
      --arg type "task_reminder" \
      --argjson id "$task_id" \
      --arg t "$real_title" \
      --arg d "$due_at" \
      --arg n "$now_iso" \
      '{type:$type, task_id:$id, title:$t, due_at:$d, now:$n}' 2>/dev/null)"
    if [ -z "$payload" ]; then
      echo "[due-at-reminder-tick] jq payload build failed task_id=$task_id" >&2
      fail=$((fail + 1))
      continue
    fi
    if trigger_send "$officer_slug" "$payload"; then
      count=$((count + 1))
    else
      fail=$((fail + 1))
      echo "[due-at-reminder-tick] trigger_send failed officer_slug=$officer_slug task_id=$task_id" >&2
    fi
  done <<< "$ROWS"
fi

# --- reconcile phase: apply the Captain's card verdicts (runs EVERY tick) ----
# grant (done)  → the arm closes the need (mark granted); nothing else to do.
# later (snooze) → the arm prints the reminder's task id; the tick bumps its
#   due_at with ONE guarded, parameterized UPDATE. The Spec 041 re-arm trigger
#   clears reminder_fired_at on the due_at change, so the row refires next tick.
#   The guard (still-overdue AND already-fired) makes a still-snoozed card's
#   repeat print a no-op after the first bump — no new state machine.
SNOOZE_TASKS="$("$PY" "$ARM" reconcile 2>/dev/null || true)"
if [ -n "$SNOOZE_TASKS" ]; then
  while IFS= read -r snooze_id; do
    [[ "$snooze_id" =~ ^[0-9]+$ ]] || continue
    # The :'id' / :'days' binds are fed on STDIN (heredoc), NOT -c — psql
    # interpolates variables only for STDIN/-f input (my-tasks.sh discipline).
    # A hostile SNOOZE_DAYS is still safe: :'days'::int is a bound literal cast,
    # so a non-integer fails the cast (query aborts), never breaks out of quoting.
    bump_out="$(psql "$CONN" -tA --no-psqlrc -v ON_ERROR_STOP=1 \
        -v id="$snooze_id" -v days="$SNOOZE_DAYS" <<'SQL' 2>/dev/null
UPDATE officer_tasks
   SET due_at = NOW() + make_interval(days => :'days'::int)
 WHERE id = :'id'::bigint
   AND status IN ('queue', 'wip')
   AND due_at <= NOW()
   AND reminder_fired_at IS NOT NULL
RETURNING id;
SQL
    )"
    if printf '%s\n' "$bump_out" | grep -qE '^[0-9]+$'; then
      bumped=$((bumped + 1))
    fi
  done <<< "$SNOOZE_TASKS"
fi

# One summary line EVERY run — a quiet tick included. launchd advances the log
# mtime ONLY when we WRITE, and the outcome-watchdog derives a freshness floor
# for this 300s row (framework/watchdog/registry.py) — a silent quiet stretch
# would false-page it DOWN (the limit-reset-watchdog "log only on events"
# lesson). The reconcile phase above also runs every tick, so this one line is
# both the heartbeat and the outcome record.
echo "[due-at-reminder-tick] fired=$count carded=$carded snooze_bumped=$bumped fail=$fail elapsed_at=$now_iso"
