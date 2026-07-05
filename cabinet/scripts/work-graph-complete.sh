#!/usr/bin/env bash
# work-graph-complete.sh — officer marks a mission work-graph node as done/failed/verified
#
# Closes the mission loop the rebuild left open: officers can now record task
# completion from within their session, emitting a typed event to the ledger
# and (best-effort) updating the work_graph_nodes Postgres row.
#
# The mission compiler reads completion events when rebuilding the work graph
# at session start, so subsequent sessions see the up-to-date task statuses
# without per-session reset.
#
# Usage:
#   work-graph-complete.sh <node_id> [--status done|failed|verified] [--evidence FILE_OR_TEXT]
#   work-graph-complete.sh outcome-launch-mvp-task-003 --status done --evidence /tmp/api-deploy.log
#   work-graph-complete.sh polads-001-ci --status done --evidence "3 green staging runs"
#   work-graph-complete.sh outcome-x-task-001 --status failed --evidence "Tests red on PR #42"
#
# <node_id> accepts BOTH work-graph id shapes (2026-07-05 fix — see the
# resolution block below): compiler-generated "<outcome_id>-task-NNN" ids AND
# the ratified explicit node_id values from instance/config/outcomes.yml
# (e.g. polads-001-ci, sys-001-parity). Unknown ids exit 2 without emitting.
#
# Resume signal:
#   Exit 0 + emitted event = success. Exit non-zero = failure (see stderr).
#
# Environment:
#   OFFICER_NAME       — actor for the emitted event (defaults to "system")
#   CABINET_ROOT       — repo root (defaults to script's two-levels-up)
#   OUTCOMES_FILE      — outcome declarations for node-id resolution
#                        (defaults to $CABINET_ROOT/instance/config/outcomes.yml)
#   DATABASE_URL       — if set, also UPDATEs work_graph_nodes row (best-effort)
#   CABINET_EVENT_LOG_DIR — event log target (defaults to ~/Library/Application Support/cabinet/events)

set -euo pipefail

# --- defaults ---
STATUS="done"
EVIDENCE=""
NODE_ID=""

usage() {
  cat <<'EOF' >&2
Usage: work-graph-complete.sh <node_id> [--status done|failed|verified] [--evidence FILE_OR_TEXT]

Records completion of a mission work-graph node.

Arguments:
  <node_id>                  Either a compiler task id "<outcome_id>-task-NNN"
                             OR a ratified node_id from instance/config/outcomes.yml
                             (e.g. polads-001-ci, sys-001-parity)

Options:
  --status done|failed|verified   Completion status (default: done)
  --evidence FILE_OR_TEXT         Path to evidence file, or inline evidence text
  -h, --help                      Show this help

Environment:
  OFFICER_NAME       Actor for the emitted event (default: "system")
  OUTCOMES_FILE      Outcomes file for node-id resolution (default: instance/config/outcomes.yml)
  DATABASE_URL       If set, also updates work_graph_nodes row
EOF
}

# --- arg parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --status)
      shift
      [[ $# -gt 0 ]] || { echo "work-graph-complete: --status requires a value" >&2; exit 2; }
      STATUS="$1"
      ;;
    --evidence)
      shift
      [[ $# -gt 0 ]] || { echo "work-graph-complete: --evidence requires a value" >&2; exit 2; }
      EVIDENCE="$1"
      ;;
    --status=*)
      STATUS="${1#--status=}"
      ;;
    --evidence=*)
      EVIDENCE="${1#--evidence=}"
      ;;
    --)
      shift
      ;;
    -*)
      echo "work-graph-complete: unknown flag: $1" >&2
      usage
      exit 2
      ;;
    *)
      if [[ -z "$NODE_ID" ]]; then
        NODE_ID="$1"
      else
        echo "work-graph-complete: unexpected positional arg: $1 (node_id already set to '$NODE_ID')" >&2
        exit 2
      fi
      ;;
  esac
  shift
done

# --- validate inputs ---
if [[ -z "$NODE_ID" ]]; then
  echo "work-graph-complete: <node_id> is required" >&2
  usage
  exit 2
fi

case "$STATUS" in
  done|failed|verified) ;;
  *)
    echo "work-graph-complete: invalid --status '$STATUS' (must be done|failed|verified)" >&2
    exit 2
    ;;
esac

# --- resolve cabinet root early (the node-id resolver needs it) ---
CABINET_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# --- resolve outcome_id + task_index from node_id ---
# TWO accepted id shapes (2026-07-05 fix — the old hard gate on '*-task-*'
# rejected every RATIFIED explicit node_id from instance/config/outcomes.yml,
# e.g. polads-001-ci / sys-001-parity / stephie-002-spec, so a completed
# outcome criterion was UNCOUNTABLE: the emit never happened and the mission
# compiler's DONE overlay — which keys on payload.task_id,
# framework/missions/compiler.py:279 — never advanced the graph):
#
#   1. Compiler-generated "<outcome_id>-task-NNN"
#      (framework/missions/compiler.py:_generate_task_id): resolved by string
#      split, no file read — the numeric-tail regex keeps this branch exact.
#   2. Explicit measurable_criteria node_id values from outcomes.yml (the
#      compiler honors them verbatim as work-graph node ids,
#      compiler.py:352): resolved by scanning $OUTCOMES_FILE for the owning
#      outcome. NOTE node ids are NOT string-prefixed with their outcome id
#      (sys-001-parity belongs to outcome-system-self-001), so split surgery
#      CANNOT work here — the file is the only truth. The scan is a
#      stdlib-only line scanner (system python3 has no PyYAML; the emitter
#      subprocess below already assumes python3): it tracks the nearest
#      preceding '- id:' outcome line and matches 'node_id:' lines by string
#      EQUALITY (never regex-interpolating the user-supplied id).
#      task_index = the node's 1-based ordinal within its outcome.
#
# FAIL-SAFE: an id in neither shape exits 2 with NO event emitted — a typo
# must never mint a spurious completion.
OUTCOMES_FILE="${OUTCOMES_FILE:-$CABINET_ROOT/instance/config/outcomes.yml}"

if [[ "$NODE_ID" =~ -task-[0-9]+$ ]]; then
  OUTCOME_ID="${NODE_ID%-task-*}"
  TASK_INDEX="${NODE_ID##*-task-}"
else
  RESOLVED="$(NODE_ID="$NODE_ID" OUTCOMES_FILE="$OUTCOMES_FILE" python3 - <<'PY'
import os
import re
import sys

node = os.environ["NODE_ID"]
path = os.environ["OUTCOMES_FILE"]
try:
    with open(path) as f:
        lines = f.read().splitlines()
except OSError as e:
    print(f"work-graph-complete: cannot read outcomes file {path}: {e}",
          file=sys.stderr)
    sys.exit(3)

# '- id:' begins an outcome entry; '- node_id:' begins a criterion node.
# Trailing '# comments' tolerated; ids restricted to the slug charset the
# schema uses. The user-supplied node id is compared by equality only.
outcome_re = re.compile(r"^\s*-\s*id:\s*([A-Za-z0-9._-]+)\s*(?:#.*)?$")
node_re = re.compile(r"^\s*-?\s*node_id:\s*([A-Za-z0-9._-]+)\s*(?:#.*)?$")

current = None
ordinal = 0
for line in lines:
    m = outcome_re.match(line)
    if m:
        current, ordinal = m.group(1), 0
        continue
    m = node_re.match(line)
    if m and current is not None:
        ordinal += 1
        if m.group(1) == node:
            print(f"{current} {ordinal}")
            sys.exit(0)
sys.exit(4)
PY
)" || {
    echo "work-graph-complete: node_id '$NODE_ID' is neither '<outcome_id>-task-NNN' nor a node_id declared in $OUTCOMES_FILE" >&2
    exit 2
  }
  OUTCOME_ID="${RESOLVED%% *}"
  TASK_INDEX="${RESOLVED##* }"
fi

# --- resolve evidence ---
EVIDENCE_TEXT=""
EVIDENCE_PATH=""
if [[ -n "$EVIDENCE" ]]; then
  if [[ -f "$EVIDENCE" ]]; then
    EVIDENCE_PATH="$EVIDENCE"
    # Read up to first 8 KB to keep event payloads compact
    EVIDENCE_TEXT="$(head -c 8192 "$EVIDENCE" 2>/dev/null || true)"
  else
    EVIDENCE_TEXT="$EVIDENCE"
  fi
fi

# --- resolve actor (CABINET_ROOT already resolved above, before the node-id
#     resolver that needs it) ---
ACTOR="${OFFICER_NAME:-system}"

# --- map status to event_type ---
case "$STATUS" in
  done)     EVENT_TYPE="work_item_completed" ;;
  failed)   EVENT_TYPE="work_item_failed" ;;
  verified) EVENT_TYPE="work_item_verified" ;;
esac

# --- emit event via framework.events.emitter ---
# Build JSON payload safely via Python (handles escaping of EVIDENCE_TEXT)
PAYLOAD_JSON="$(NODE_ID="$NODE_ID" \
                OUTCOME_ID="$OUTCOME_ID" \
                TASK_INDEX="$TASK_INDEX" \
                STATUS="$STATUS" \
                EVIDENCE_TEXT="$EVIDENCE_TEXT" \
                EVIDENCE_PATH="$EVIDENCE_PATH" \
                python3 -c '
import json, os
print(json.dumps({
    "task_id": os.environ["NODE_ID"],
    "outcome_id": os.environ["OUTCOME_ID"],
    "task_index": int(os.environ["TASK_INDEX"]),
    "status": os.environ["STATUS"],
    "evidence_text": os.environ.get("EVIDENCE_TEXT") or None,
    "evidence_path": os.environ.get("EVIDENCE_PATH") or None,
}))
')"

EVENT_JSON="$(cd "$CABINET_ROOT" && python3 -m framework.events.emitter "$EVENT_TYPE" "$ACTOR" "$PAYLOAD_JSON")" || {
  echo "work-graph-complete: failed to emit $EVENT_TYPE event" >&2
  exit 1
}

# --- best-effort DB update ---
# If DATABASE_URL is set, also update the work_graph_nodes row. This isn't the
# source of truth (the event ledger is), but populating the DB makes OVI and
# downstream queries fast without replay.
if [[ -n "${DATABASE_URL:-}" ]]; then
  NODE_ID="$NODE_ID" \
  STATUS="$STATUS" \
  EVIDENCE_TEXT="$EVIDENCE_TEXT" \
  python3 - <<'PY' 2>&1 || echo "work-graph-complete: WARN db update failed (event still recorded)" >&2
import json
import os
import sys

node_id = os.environ["NODE_ID"]
status = os.environ["STATUS"]
evidence = os.environ.get("EVIDENCE_TEXT", "") or None

# Map our status to schema-allowed values (done|failed|verified are direct passthroughs)
status_db = status if status != "verified" else "done"  # schema only has 'done', 'failed'; verified is a separate event

try:
    import psycopg2
except ImportError:
    sys.exit(0)

try:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    with conn.cursor() as cur:
        # work_graph_nodes.id is UUID; our task_id is a string. We store our
        # logical task_id in description prefix or via a side-channel. For now,
        # this update is a no-op unless a uuid-resolution layer is added in
        # Phase 1.2 (mission supervisor persists missions to DB).
        # This block is intentionally tolerant — the event is the truth.
        cur.execute(
            "UPDATE work_graph_nodes SET status = %s, completed_at = NOW(), evidence = %s "
            "WHERE description LIKE %s AND status != %s",
            (status_db, evidence, f"%{node_id}%", status_db),
        )
        rows = cur.rowcount
        conn.commit()
        if rows:
            print(f"work-graph-complete: updated {rows} work_graph_nodes row(s)", file=sys.stderr)
    conn.close()
except Exception as e:
    print(f"work-graph-complete: db update soft-failed: {e}", file=sys.stderr)
    sys.exit(0)
PY
fi

# --- print event id to stdout for chaining ---
echo "$EVENT_JSON" | python3 -c 'import json, sys; e = json.load(sys.stdin); print(e["id"])'
echo "work-graph-complete: ${EVENT_TYPE} emitted for ${NODE_ID} (status=${STATUS}, actor=${ACTOR})" >&2
