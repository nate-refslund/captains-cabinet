#!/bin/bash
# surface-pin-tick.sh — one Captain-surface PIN tick (overview standing card).
#
# PARTIAL ARMING per the 2026-07-10 order (captain-decisions 16:30Z, "3 KNOBS
# RATIFIED"): this runs ONLY the pin lifecycle (`engine --pin-tick` →
# pin_lifecycle.step; pin_mode resolves from instance/config/comms-surface.yml
# = overview). The pacing engine and the escalation gate stay DARK — arming
# either is a separate deliberate step (safety-rails doc §arming).
#
# Scheduled via the cabinet/services.yml row `surface-pin` (300s). Idempotent:
# the gate's standing-card dedup suppresses no-change ticks, edits never
# notify, the pin is set once and kept.

set -u
TIMESTAMP=$(date -u '+%Y-%m-%d %H:%M:%S UTC')

# Resolve CABINET_ROOT — env var wins, otherwise script-relative
# (cabinet/cron/.. = repo root).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

# Source cabinet/.env (Telegram token + Captain id) — launchd runs get no
# login environment; without this the send dies token-less. set -a exports
# to the python child.
if [ -f "$CABINET_ROOT/cabinet/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$CABINET_ROOT/cabinet/.env"
  set +a
fi

# The tick must see the same room the Captain sees: runtime sends enabled
# (framework.env.allow_sends) + the admission law the intake/briefing rows
# already run under (C3, 2026-07-10). Explicit env (a future wrapper/plist
# override) still wins.
export CABINET_ENV="${CABINET_ENV:-runtime}"
export CABINET_ADMISSION_LAW="${CABINET_ADMISSION_LAW:-1}"

cd "$CABINET_ROOT" || {
  echo "[$TIMESTAMP] surface-pin-tick.sh FATAL: cd $CABINET_ROOT failed" >&2
  exit 1
}

OUT=$(python3.12 -m framework.comms.surface.engine --pin-tick 2>&1)
RC=$?
if [ "$RC" -ne 0 ]; then
  echo "[$TIMESTAMP] surface-pin-tick.sh FATAL: pin tick rc=$RC — ${OUT:-no output}" >&2
  exit 1
fi
# The engine is fail-soft (a broken tick reports ("card","error",…) ops and
# exits 0) — surface that as a FATAL non-zero exit here, or a rotated token /
# broken charter wedges the pinned card at a stale count while every check
# stays green (review 2026-07-10 finding #2). Op tuples only ever carry
# "error" as the failure action, never card copy.
case "$OUT" in
  *'"error"'*)
    echo "[$TIMESTAMP] surface-pin-tick.sh FATAL: tick reported errors — $OUT" >&2
    exit 1;;
esac
echo "[$TIMESTAMP] Surface pin tick ok: $OUT"
