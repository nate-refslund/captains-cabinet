#!/bin/bash
# record-capability-gap.sh — an officer records a capability gap (a wall it
# hit that current tools can't solve).
#
# This is the explicit half of the self-extension loop (the other half is the
# self-improvement loop INFERRING gaps from recurring workarounds). When an
# officer can't do something with the tools it has, it records it here instead
# of silently working around it — so the cabinet can auto-skill it (if it's a
# procedure) or propose a fix to the Captain (if it needs code/an MCP).
#
# Usage:
#   record-capability-gap.sh --need "<one line: what I couldn't do>" \
#       [--kind procedure|tool|integration] \
#       [--evidence "<what I tried / why I'm stuck>"] \
#       [--touches secrets,spending,...]    # hard-ceiling categories, if known
#
# OFFICER_NAME (env) is used as recorded_by. Idempotent-ish: a near-identical
# recurring gap increments a hit-count instead of duplicating.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

NEED=""; KIND=""; EVIDENCE=""; TOUCHES=""
while [ $# -gt 0 ]; do
  case "$1" in
    --need) NEED="$2"; shift 2 ;;
    --kind) KIND="$2"; shift 2 ;;
    --evidence) EVIDENCE="$2"; shift 2 ;;
    --touches) TOUCHES="$2"; shift 2 ;;
    -h|--help) sed -n '1,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "record-capability-gap: unknown arg: $1" >&2; exit 64 ;;
  esac
done

if [ -z "$NEED" ]; then
  echo "record-capability-gap: --need is required" >&2
  exit 64
fi

OFFICER="${OFFICER_NAME:-${CABINET_OFFICER:-unknown}}"

CABINET_ROOT="$CABINET_ROOT" OFFICER="$OFFICER" \
NEED="$NEED" KIND="$KIND" EVIDENCE="$EVIDENCE" TOUCHES="$TOUCHES" \
python3 - <<'PY'
import os, sys
sys.path.insert(0, os.environ["CABINET_ROOT"])
from framework.learning.capability_gaps import record_gap

touches = [t.strip() for t in os.environ.get("TOUCHES", "").split(",") if t.strip()]
kind = os.environ.get("KIND") or None
g = record_gap(
    need=os.environ["NEED"],
    kind=kind,
    evidence=os.environ.get("EVIDENCE", ""),
    recorded_by=os.environ.get("OFFICER", "unknown"),
    touches=touches or None,
)
print(f"capability gap recorded: {g['gap_id']} [{g['kind']}] status={g['status']} hit_count={g['hit_count']}")
print(f"  need: {g['need']}")
if g['kind'] == 'procedure':
    print("  → procedure: the self-improvement loop will try to auto-skill this (eval-gated).")
else:
    print("  → tool/integration: the loop will propose a fix to the Captain (nothing installs without approval).")
PY
