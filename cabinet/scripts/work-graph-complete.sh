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
# THE CLAIM FENCE (2026-09-07). A task pulled through the real pull path
# carries an unguessable claim token. `--claim <id>` (or CABINET_CLAIM_ID)
# hands it back, and a done/failed completion is routed through
# framework.missions.claims.complete, which REFUSES — exit 4, zero events — a
# token that is not the task's latest claim, a holder that is not the claim's
# holder, a task that already carries a terminal event, and a completion with
# no token at all while somebody's claim is live. A task nobody holds still
# completes with no token: that is the compatibility path for callers that
# predate claims, and it is flipped to fail-closed once every pull carries one.
#
# `--status verified` deliberately does NOT go through the fence. A
# verification is another role's act on someone else's work — fencing it on the
# executor's claim would refuse exactly the separation of duties the block
# below exists to keep.
#
# Usage:
#   work-graph-complete.sh <node_id> [--status done|failed|verified] [--evidence FILE_OR_TEXT] [--actor ROLE] [--claim CLAIM_ID]
#   work-graph-complete.sh outcome-launch-mvp-task-003 --status done --evidence /tmp/api-deploy.log
#   work-graph-complete.sh acme-001-ci --status done --evidence "3 green staging runs"
#   work-graph-complete.sh outcome-x-task-001 --status failed --evidence "Tests red on PR #42"
#   work-graph-complete.sh outcome-x-task-001 --status verified --actor auditor --evidence /tmp/audit.log
#
# SEPARATION OF DUTIES: --status verified requires an attributed actor (--actor
# or OFFICER_NAME; the "system" fallback is refused), and the compiler's status
# overlay declines to credit a verification whose actor is the node's own owner
# or is not the node's declared verifier_role. The actor is SELF-ASSERTED: this
# stops the defaulted, unattributed and accidental cases, NOT an officer who
# types another role's name. It is not authentication and must not be sold as such.
#
# <node_id> accepts BOTH work-graph id shapes (2026-07-05 fix — see the
# resolution block below): compiler-generated "<outcome_id>-task-NNN" ids AND
# the ratified explicit node_id values from instance/config/outcomes.yml
# (e.g. acme-001-ci, sys-001-parity). Unknown ids exit 2 without emitting.
#
# Resume signal:
#   Exit 0 + emitted event = success. Exit non-zero = failure (see stderr).
#
# Environment:
#   OFFICER_NAME       — actor for the emitted event (defaults to "system";
#                        --actor overrides it, and "system" is refused for
#                        --status verified)
#   CABINET_ROOT       — repo root (defaults to script's two-levels-up)
#   OUTCOMES_FILE      — outcome declarations for node-id resolution
#                        (defaults to $CABINET_ROOT/instance/config/outcomes.yml)
#   DATABASE_URL       — if set, also UPDATEs work_graph_nodes row (best-effort)
#   CABINET_EVENT_LOG_DIR — event log target (defaults to ~/Library/Application Support/cabinet/events)
#   CABINET_CLAIM_ID   — claim token, when --claim is not passed
#   CABINET_WORKER_ID  — holder identity asserted alongside the token (optional;
#                        the token alone is the credential when it is unset,
#                        because the holder a shell can derive is not stable)
#   CABINET_PYTHON     — interpreter for the helper calls (default python3.12)

set -euo pipefail

# --- defaults ---
STATUS="done"
EVIDENCE=""
NODE_ID=""
ACTOR_ARG=""
CLAIM_ID="${CABINET_CLAIM_ID:-}"

# Every helper below is pinned. A bare `python3` resolved to whatever the
# caller's PATH offered — 3.9 on the reference box — and these helpers are not
# held to the 3.9 floor the locked hook's import set is.
CABINET_PY="${CABINET_PYTHON:-python3.12}"

usage() {
  cat <<'EOF' >&2
Usage: work-graph-complete.sh <node_id> [--status done|failed|verified] [--evidence FILE_OR_TEXT] [--actor ROLE]

Records completion of a mission work-graph node.

Arguments:
  <node_id>                  Either a compiler task id "<outcome_id>-task-NNN"
                             OR a ratified node_id from instance/config/outcomes.yml
                             (e.g. acme-001-ci, sys-001-parity)

Options:
  --status done|failed|verified   Completion status (default: done)
  --evidence FILE_OR_TEXT         Path to evidence file, or inline evidence text
  --claim CLAIM_ID                The claim token this task was pulled with (or
                                  CABINET_CLAIM_ID). done/failed completions are
                                  fenced on it; a refusal exits 4 and emits nothing.
  --actor ROLE                    Actor for the emitted event (overrides OFFICER_NAME).
                                  For --status verified an attributed actor is required:
                                  supply --actor or OFFICER_NAME (the "system" fallback is
                                  refused). Validators verify, executors complete.
                                  Self-asserted, so this separates duties -- it stops the
                                  defaulted/unattributed cases, not a deliberate rename,
                                  and it is not authentication.
  -h, --help                      Show this help

Environment:
  OFFICER_NAME       Actor for the emitted event (default: "system"; not accepted for --status verified)
  OUTCOMES_FILE      Outcomes file for node-id resolution (default: instance/config/outcomes.yml)
  DATABASE_URL       If set, also updates work_graph_nodes row
  CABINET_CLAIM_ID   Claim token when --claim is not passed
  CABINET_WORKER_ID  Holder identity asserted alongside the token
  CABINET_PYTHON     Interpreter for the helper calls (default python3.12)

Exit codes:
  0  event emitted
  2  bad arguments / unresolvable node id (no event)
  4  the claim fence refused the completion (no event)
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
    --actor)
      shift
      [[ $# -gt 0 ]] || { echo "work-graph-complete: --actor requires a value" >&2; exit 2; }
      ACTOR_ARG="$1"
      ;;
    --actor=*)
      ACTOR_ARG="${1#--actor=}"
      ;;
    --claim)
      shift
      [[ $# -gt 0 ]] || { echo "work-graph-complete: --claim requires a value" >&2; exit 2; }
      CLAIM_ID="$1"
      ;;
    --claim=*)
      CLAIM_ID="${1#--claim=}"
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
# e.g. acme-001-ci / sys-001-parity / widgets-002-spec, so a completed
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
#      stdlib-only line scanner (no PyYAML is assumed anywhere in this
#      resolver; every helper runs on $CABINET_PY): it tracks the nearest
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
  RESOLVED="$(NODE_ID="$NODE_ID" OUTCOMES_FILE="$OUTCOMES_FILE" "$CABINET_PY" - <<'PY'
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
ACTOR="${ACTOR_ARG:-${OFFICER_NAME:-system}}"

# A verification must be ATTRIBUTED. The "system" fallback let a
# `--status verified` land with no officer named at all, which is the
# unaccountable case: nothing downstream can tell who checked the work.
# `done`/`failed` keep the permissive fallback — an executor reporting its own
# completion is legitimate and is what this script is mostly used for.
#
# NOTE ON STRENGTH: $OFFICER_NAME (and --actor) are self-supplied by the
# caller and every officer runs as the same OS user, so this is separation of
# duties, NOT authentication. It stops accidents and self-dealing; it does not
# stop a determined caller from naming any actor it likes.
# Fold before comparing: a bare literal test let "System" and "system " through.
ACTOR_FOLDED="$(printf '%s' "$ACTOR" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
if [[ "$STATUS" == "verified" && ( -z "$ACTOR_FOLDED" || "$ACTOR_FOLDED" == "system" ) ]]; then
  echo "work-graph-complete: --status verified requires an attributed actor" >&2
  echo "  pass --actor <role> or set OFFICER_NAME; validators verify, executors complete" >&2
  exit 2
fi

# --- map status to event_type ---
case "$STATUS" in
  done)     EVENT_TYPE="work_item_completed" ;;
  failed)   EVENT_TYPE="work_item_failed" ;;
  verified) EVENT_TYPE="work_item_verified" ;;
esac

# --- emit the completion ---
# done/failed go through the CLAIM FENCE (framework.missions.claims), which
# takes the claims lock, replays the task's claim chain, refuses a stale or
# missing token with exit 4 and NO event, and only then appends. verified stays
# on the raw emitter: it is a second role's act, not the holder's, and has no
# claim of its own to present.
if [[ "$STATUS" == "verified" ]]; then
  PAYLOAD_JSON="$(NODE_ID="$NODE_ID" \
                  OUTCOME_ID="$OUTCOME_ID" \
                  TASK_INDEX="$TASK_INDEX" \
                  STATUS="$STATUS" \
                  EVIDENCE_TEXT="$EVIDENCE_TEXT" \
                  EVIDENCE_PATH="$EVIDENCE_PATH" \
                  "$CABINET_PY" -c '
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

  EVENT_JSON="$(cd "$CABINET_ROOT" && "$CABINET_PY" -m framework.events.emitter "$EVENT_TYPE" "$ACTOR" "$PAYLOAD_JSON")" || {
    echo "work-graph-complete: failed to emit $EVENT_TYPE event" >&2
    exit 1
  }
else
  # Optional args are collected in an array. The `[@]+` guard is not
  # decoration: bash 3.2 — the /bin/bash every mac ships — treats a plain
  # "${arr[@]}" on an EMPTY array as an unbound variable under `set -u`, so a
  # completion with no token and no evidence would have died here rather than
  # taking the compatibility path.
  CLAIM_ARGS=()
  if [[ -n "$CLAIM_ID" ]]; then CLAIM_ARGS+=(--claim "$CLAIM_ID"); fi
  if [[ -n "${CABINET_WORKER_ID:-}" ]]; then CLAIM_ARGS+=(--holder "$CABINET_WORKER_ID"); fi
  if [[ -n "$EVIDENCE_TEXT" ]]; then CLAIM_ARGS+=(--evidence-text "$EVIDENCE_TEXT"); fi
  if [[ -n "$EVIDENCE_PATH" ]]; then CLAIM_ARGS+=(--evidence-path "$EVIDENCE_PATH"); fi

  set +e
  EVENT_JSON="$(cd "$CABINET_ROOT" && "$CABINET_PY" -m framework.missions.claims complete \
      --json \
      --task-id "$NODE_ID" \
      --outcome-id "$OUTCOME_ID" \
      --task-index "$TASK_INDEX" \
      --status "$STATUS" \
      --actor "$ACTOR" \
      ${CLAIM_ARGS[@]+"${CLAIM_ARGS[@]}"})"
  CLAIM_RC=$?
  set -e
  if [[ $CLAIM_RC -eq 4 ]]; then
    echo "work-graph-complete: the claim fence refused this completion (no event emitted)" >&2
    exit 4
  fi
  if [[ $CLAIM_RC -ne 0 ]]; then
    echo "work-graph-complete: failed to emit $EVENT_TYPE event" >&2
    exit 1
  fi
fi

# --- best-effort DB update ---
# If DATABASE_URL is set, also update the work_graph_nodes row. This isn't the
# source of truth (the event ledger is), but populating the DB makes OVI and
# downstream queries fast without replay.
if [[ -n "${DATABASE_URL:-}" ]]; then
  NODE_ID="$NODE_ID" \
  STATUS="$STATUS" \
  EVIDENCE_TEXT="$EVIDENCE_TEXT" \
  "$CABINET_PY" - <<'PY' 2>&1 || echo "work-graph-complete: WARN db update failed (event still recorded)" >&2
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
echo "$EVENT_JSON" | "$CABINET_PY" -c 'import json, sys; e = json.load(sys.stdin); print(e["id"])'
echo "work-graph-complete: ${EVENT_TYPE} emitted for ${NODE_ID} (status=${STATUS}, actor=${ACTOR})" >&2

# --- stamp the reflection-experience marker (fix 2026-07-06, acme-ceo finding) ---
# Completing a work-graph node IS a "did work" event, but only record-experience.sh
# stamped cabinet:last-experience:<officer>. So an officer who advanced the graph via
# this script read reflection_due=0 and never auto-reflected — the outcome-watchdog
# then false-flagged them and the Chair nudged by hand every cycle. Mirror
# record-experience.sh's stamp for a real officer actor (any status is reflection-
# worthy work). Idempotent, EX 7200, never fails the script (|| true).
if [ -n "$ACTOR" ] && [ "$ACTOR" != "system" ]; then
  redis-cli -h "${REDIS_HOST:-localhost}" -p "${REDIS_PORT:-6379}" \
    SET "cabinet:last-experience:$ACTOR" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" EX 7200 >/dev/null 2>&1 || true
fi
