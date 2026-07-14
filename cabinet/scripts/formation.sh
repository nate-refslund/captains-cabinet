#!/usr/bin/env bash
# cabinet/scripts/formation.sh — the Formation deep self-setup run (Phase 3 SCAFFOLD).
#
# Foreground stage machine ("run this and go to bed"): stamps
#   FORMATION_START -> DISCOVERY_DONE -> READ_SCOPE_RATIFIED -> INGEST_DONE
#   -> STRATEGY_DONE -> BRIEFING_DONE
# with an APPEND-ONLY journal at
#   instance/onboarding/formation/<run-id>/journal.jsonl
# and journal-based RESUME (re-run with --run-id <id>; already-journaled
# stages are skipped — Ctrl-C loses nothing).
#
# SCAFFOLD HONESTY: every stage is an honest IOU stub ("not yet built —
# Phase 3 increment N") — no LLM call, no network, no Captain data read,
# nothing proposed, nothing activated. The mission compiler structurally
# never reads any formation surface (its filename gate reads only the
# ratified outcomes file — tested invariant, framework/onboarding/tests/
# test_formation.py; this script never even names that file). A printed
# cost estimate + the per-run call cap (CABINET_FORMATION_CALL_CAP,
# default 25) front-run every run.
#
# UNDO: formation.sh --undo <run-id> supersede-archives the whole run dir to
# instance/onboarding/formation/_pre-adopt-<UTC-stamp>/<run-id>/ — the
# generate-instance --adopt idiom: nothing deleted, ever.
#
# NOT GRANTED: append-interface.sh (the Captain-law ledgers) — formation
# never writes captain-decisions/patterns/intents (closes the
# self-persuasion channel; pinned by test_formation_script.py).
#
# Bash 3.2-compatible (macOS /bin/bash). Python side: fixed argv only —
# python3.12 -m framework.onboarding.formation <cmd> --run-id <id>.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
: "${CABINET_ROOT:=$REPO_ROOT}"
export CABINET_ROOT
PY="${CABINET_PYTHON:-python3.12}"
FORMATION_DIR="$CABINET_ROOT/instance/onboarding/formation"

# shellcheck source=cabinet/scripts/hatch-lib/flight-recorder.sh
. "$SCRIPT_DIR/hatch-lib/flight-recorder.sh"

usage() {
  cat <<'EOF'
formation.sh — Formation deep self-setup run (Phase 3 SCAFFOLD; propose-only)

USAGE
  bash cabinet/scripts/formation.sh                 # new run (prints run-id)
  bash cabinet/scripts/formation.sh --run-id <id>   # RESUME a run (journal-based)
  bash cabinet/scripts/formation.sh --undo <id>     # supersede-archive a run
  bash cabinet/scripts/formation.sh --help

STAGES (stamped in order; each is an honest IOU stub in the scaffold)
  FORMATION_START -> DISCOVERY_DONE -> READ_SCOPE_RATIFIED -> INGEST_DONE
  -> STRATEGY_DONE -> BRIEFING_DONE

SAFETY MODEL
  * PROPOSE-ONLY: outputs live under instance/onboarding/formation/<run-id>/
    — the mission compiler structurally cannot read them; nothing activates.
  * RESUME: journal.jsonl is append-only; re-run with --run-id to continue.
  * COST: prints an estimate up front; per-run LLM call cap from
    CABINET_FORMATION_CALL_CAP (default 25; the scaffold makes 0 calls).
  * UNDO: --undo <run-id> archives the run dir to
    instance/onboarding/formation/_pre-adopt-<stamp>/ — nothing deleted.

ENV
  CABINET_ROOT                 deployment root (default: this checkout)
  CABINET_FORMATION_CALL_CAP   per-run LLM call cap (recorded at open)
  CABINET_PYTHON               python interpreter (default: python3.12)
EOF
}

RUN_ID=""
UNDO_ID=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --run-id)  RUN_ID="${2:-}"; [ -n "$RUN_ID" ] || { echo "formation: --run-id needs a value" >&2; exit 2; }; shift 2 ;;
    --undo)    UNDO_ID="${2:-}"; [ -n "$UNDO_ID" ] || { echo "formation: --undo needs a run-id" >&2; exit 2; }; shift 2 ;;
    *) echo "formation: unknown flag: $1 (see --help)" >&2; exit 2 ;;
  esac
done

cd "$REPO_ROOT"   # -m framework.onboarding.formation must resolve

# ---- undo path ---------------------------------------------------------------
if [ -n "$UNDO_ID" ]; then
  echo "==== FORMATION UNDO — supersede-archive of run $UNDO_ID ===="
  "$PY" -m framework.onboarding.formation undo --run-id "$UNDO_ID"
  echo "Nothing deleted — restore by moving the archived dir back."
  exit 0
fi

# ---- open (new or resume) ----------------------------------------------------
if [ -n "$RUN_ID" ]; then
  RUN_ID="$("$PY" -m framework.onboarding.formation open --run-id "$RUN_ID" --id-only)"
else
  RUN_ID="$("$PY" -m framework.onboarding.formation open --id-only)"
fi
RUN_DIR="$FORMATION_DIR/$RUN_ID"
JOURNAL="$RUN_DIR/journal.jsonl"

flight_init "$RUN_DIR/logs" "$RUN_DIR/flight.log"
flight_stamp FORMATION_START

echo "==== FORMATION (Phase 3 scaffold) — run $RUN_ID ===="
echo "Journal (append-only): $JOURNAL"
echo "Resume anytime:  bash cabinet/scripts/formation.sh --run-id $RUN_ID"
echo "Undo everything: bash cabinet/scripts/formation.sh --undo $RUN_ID"
echo ""
"$PY" -m framework.onboarding.formation estimate --run-id "$RUN_ID"
echo ""

# ---- the stage loop (idempotent stubs; journal rows are the resume state) ----
for STAMP in DISCOVERY_DONE READ_SCOPE_RATIFIED INGEST_DONE STRATEGY_DONE BRIEFING_DONE; do
  flight_step_begin "$STAMP" "formation stage stub"
  t0="$(date +%s)"
  line="$("$PY" -m framework.onboarding.formation stage --run-id "$RUN_ID" --stamp "$STAMP")"
  status="${line%% *}"
  t1="$(date +%s)"
  if [ "$status" = "already-done" ]; then
    flight_step_end "$STAMP" skip "$((t1 - t0))"
    echo "  [skip] $STAMP — already journaled (resume)"
  else
    flight_step_end "$STAMP" ok "$((t1 - t0))"
    flight_stamp "$STAMP"
    echo "  [iou ] $STAMP — honest stub written (${line#* })"
  fi
done

echo ""
echo "==== FORMATION run $RUN_ID complete (scaffold: all stages honest IOUs) ===="
echo "Nothing activated: the mission compiler cannot read any of this run's files."
echo "(Summary below reuses hatch-lib's flight recorder — its TTFR line is"
echo " hatch vocabulary; formation has no receipt stage, so ignore it here.)"
flight_summary
