#!/bin/bash
# attention-submit.sh — the thin SHELL producer entry to the attention gateway
# (attention-gateway spec §4.4). Shell watchdogs/pagers that once posted raw to
# the Telegram Bot API submit here instead: the item flows through the gate
# (charter route, quiet hours, standing-card dedup) and the gated channel, so
# every send inherits the killswitch, token scrub, and feed journal. This
# script contains NO direct API call by design (the one-door ratchet proves it).
#
# Usage:   attention-submit.sh <kind> <subject> [situation text...]
# Env:     CABINET_GATE_DRY=1  → print the decision JSON, deliver nothing
# Exit:    non-zero on a gate/charter error (the caller must hear a failure).
set -euo pipefail

KIND="${1:?usage: attention-submit.sh <kind> <subject> [situation...]}"
SUBJECT="${2:?usage: attention-submit.sh <kind> <subject> [situation...]}"
shift 2 || true
SITUATION="${*:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

KIND="$KIND" SUBJECT="$SUBJECT" SITUATION="$SITUATION" \
  python3.12 - "$CABINET_ROOT" <<'PY'
import os, sys, json
sys.path.insert(0, sys.argv[1])
from framework.attention import gate

item = {"kind": os.environ["KIND"], "subject": os.environ["SUBJECT"],
        "situation": os.environ.get("SITUATION", "")}

if os.environ.get("CABINET_GATE_DRY") == "1":
    # eyeball gate: resolve the decision, deliver NOTHING (no send/edit/enqueue)
    decision = gate.decide(item)
    print(json.dumps({k: v for k, v in decision.items() if k != "text"}))
    sys.exit(0)

out = gate.submit(item)
d = out["decision"]
print(f"attention-submit: {d['action']} class={d['class_id']} reason={d['reason']}")
PY
