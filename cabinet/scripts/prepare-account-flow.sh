#!/bin/bash
# prepare-account-flow.sh — Chair-driven account signup, up to the credential
# boundary (sibling of framework/learning/self_proposal.py — both PREPARE +
# SURFACE for Nate's one-tap; neither self-grants).
#
# Drives a signup up to the credential/OTP boundary, then surfaces a
# "credential needed" card to Nate via the front-door intake. The credential
# entry stays Nate's — the Chair NEVER reads, types, stores, or logs it.
#
# HARD LINE (shared/interfaces/captain-patterns.md →
# autonomy-boundary-accounts-and-self-guards): this script PREPARES + SURFACES
# only. It cannot enter a credential or create an account itself. It plans the
# flow, checks scope, and enqueues the human step.
#
# DEPENDENCY (genuine residual): the actual browser-driving needs the Chair to
# hold `claude-in-chrome` MCP scope, which is NOT granted today. When scope is
# absent, this script degrades to surfacing the WHOLE signup as a manual step
# (it never silently no-ops). Granting claude-in-chrome is itself a
# self-proposal (prepare_mcp_proposal surfaces the scope line; Nate applies it).
#
# Usage:
#   prepare-account-flow.sh --service <name> [--urgency ping-now|batch]
#   prepare-account-flow.sh --list            # list configured flows
#
# Reads instance/config/account-flows.yml (copy from .yml.example). The browser
# steps themselves are performed by the Chair using the claude-in-chrome MCP
# tools when scoped — this script computes the plan + the human boundary and
# surfaces it; it deliberately does not embed browser automation (that is the
# Chair's tool-call surface, gated by mcp-scope.yml).

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

SERVICE=""; URGENCY="ping-now"; LIST=0
while [ $# -gt 0 ]; do
  case "$1" in
    --service) SERVICE="$2"; shift 2 ;;
    --urgency) URGENCY="$2"; shift 2 ;;
    --list) LIST=1; shift ;;
    -h|--help) sed -n '1,40p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "prepare-account-flow: unknown arg: $1" >&2; exit 64 ;;
  esac
done

CABINET_ROOT="$CABINET_ROOT" SERVICE="$SERVICE" URGENCY="$URGENCY" LIST="$LIST" \
python3 - <<'PY'
import os, sys, json
from datetime import datetime, timezone

root = os.environ["CABINET_ROOT"]
sys.path.insert(0, root)
service = os.environ.get("SERVICE", "").strip()
urgency = os.environ.get("URGENCY", "ping-now").strip()
if urgency not in ("ping-now", "batch", "fyi"):
    urgency = "ping-now"
do_list = os.environ.get("LIST") == "1"

# --- load the flows recipe (fail-closed: missing file => no flows) ---------
try:
    from yaml import safe_load
except ImportError:
    safe_load = None

cfg_path = os.path.join(root, "instance", "config", "account-flows.yml")
flows = []
if safe_load and os.path.exists(cfg_path):
    try:
        data = safe_load(open(cfg_path).read()) or {}
        flows = [f for f in (data.get("flows") or []) if isinstance(f, dict)]
    except Exception:
        flows = []

if do_list:
    if not flows:
        print("No account flows configured. Copy "
              "instance/config/account-flows.yml.example -> account-flows.yml.")
    for f in flows:
        print(f"- {f.get('service','?')}  ({f.get('signup_url','?')})  "
              f"touches={f.get('touches') or []}")
    sys.exit(0)

if not service:
    print("prepare-account-flow: --service is required (or --list)", file=sys.stderr)
    sys.exit(64)

flow = next((f for f in flows if f.get("service") == service), None)
if flow is None:
    print(f"prepare-account-flow: no flow named '{service}'. "
          f"Add it to instance/config/account-flows.yml (see .yml.example).",
          file=sys.stderr)
    sys.exit(2)

# --- is claude-in-chrome scoped for the Chair? -----------------------------
def chair_has_chrome():
    scope_path = os.path.join(root, "cabinet", "mcp-scope.yml")
    if not (safe_load and os.path.exists(scope_path)):
        return False
    try:
        s = safe_load(open(scope_path).read()) or {}
        agents = s.get("agents") or {}
        cos = (agents.get("cos") or {}).get("mcps") or []
        return any("chrome" in str(m).lower() for m in cos)
    except Exception:
        return False

has_chrome = chair_has_chrome()
captain_fields = flow.get("captain_supplies") or []
touches = flow.get("touches") or []
ceiling_note = ""
if touches:
    ceiling_note = (f"\n⚠ This flow touches {touches} — Captain-gated end to end "
                    "(not just the credential step).")

if has_chrome:
    body = (
        f"🔐 Account signup for *{service}* reached the credential boundary.\n"
        f"I filled the safe fields at {flow.get('signup_url')}. "
        f"Now YOUR step — enter in the open browser tab: "
        f"{', '.join(captain_fields) or '(the credential field)'}. "
        f"Reply `done` and I'll finish the rest.{ceiling_note}"
    )
    state = "awaiting-credential"
else:
    body = (
        f"🔐 Account signup for *{service}* needs you (I don't have browser "
        f"scope yet, so I can't drive the form). Please sign up at "
        f"{flow.get('signup_url')} — the credential fields "
        f"({', '.join(captain_fields) or 'password/OTP'}) are yours regardless. "
        f"To let me drive future signups up to the credential, grant the Chair "
        f"`claude-in-chrome` scope (I'll surface that scope line separately)."
        f"{ceiling_note}"
    )
    state = "manual-signup-no-browser-scope"

# --- surface via the durable intake (never the credential value) -----------
item = {
    "source": "account-flow",
    "kind": "credential-needed",
    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "urgency_tier": urgency,
    "payload": {
        "summary": body,
        "service": service,
        "state": state,
        "touches": touches,
        # NB: captain field LABELS only — never a credential value.
        "captain_fields": captain_fields,
    },
}
enqueued = None
try:
    from framework.frontdoor import intake
    enqueued = intake.enqueue(item)
except Exception as e:
    enqueued = None

# audit (no secret)
try:
    from framework.events.emitter import emit
    emit("account_flow_surfaced", actor="cos", payload={
        "service": service, "state": state, "touches": touches,
        "has_browser_scope": has_chrome,
    })
except Exception:
    pass

print(json.dumps({
    "service": service, "state": state, "has_browser_scope": has_chrome,
    "enqueued_id": enqueued, "captain_fields": captain_fields,
}, indent=2))
print("\n--- surfaced card ---\n" + body)
PY
