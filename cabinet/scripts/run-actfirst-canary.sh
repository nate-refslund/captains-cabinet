#!/bin/bash
# run-actfirst-canary.sh — launchd entry for the WEEKLY TI-7 canary + breaker
# pass (checkpoint 2026-07-04 condition 5: "+ TI-7 canary/breaker weekly
# runner"; the breakers were "CODED, NOT ARMED — no weekly runner scheduled,
# 0 canaries ever run").
#
# All logic lives in framework/frontdoor/actfirst_canary.py (run_weekly, built
# + tested dark in W2 L3): per act-first-eligible kind (monday_task_create /
# monday_task_update / reminder_create) it runs the JOURNAL-ONLY synthetic
# create→verify→reverse cycle — canary:true journal rows, ZERO consequence-
# ledger emission, so a canary can never look like real acting — plus the kind
# breaker (undo-rate), silence breaker, veto-ledger divergence audit and the
# env-perms check. This script only wires the LIVE transports (Monday GraphQL
# + argv-list osascript) and surfaces the result to the log.
#
# FAIL-CLOSED BY DESIGN: any canary failure OR cannot-run (including a missing
# Monday key) freezes that kind's action_type inside run_canary itself — no
# auto-unfreeze; only a manually-run green canary lifts it. The runner does NOT
# pre-flight-skip on a missing key: TI-7's contract is that an unprovable undo
# capability must freeze acting, not silently defer the check.
#
# Secrets: MONDAY_API_TOKEN/MONDAY_API_KEY from the PersonalSource shared env
# (instance platform.yml shared_env_path) — never echoed, never in the plist.
# cabinet/.env is deliberately NOT sourced (it ships empty placeholder values
# that would shadow the real shared-env keys).
#
# Reversible:
#   launchctl bootout gui/$(id -u)/com.cabinet.actfirst-canary \
#     || launchctl unload ~/Library/LaunchAgents/com.cabinet.actfirst-canary.plist
set -o pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# launchd hands a minimal PATH that excludes Homebrew (python3.12, redis-cli,
# where the freeze flags + cap counters live).
export PATH="/opt/homebrew/bin:$PATH"
export REDIS_HOST="${REDIS_HOST:-localhost}"

# PersonalSource shared env — path is instance data via lib/personal-env.sh
# (R070 indirection); clean-room (NullPersonalSource) sources nothing.
. "$ROOT/cabinet/scripts/lib/personal-env.sh"
personal_env_source

# Calendar-lane env (ACTION_LANE_CALENDAR / CABINET_CAL_*): lives in the
# instance-local cabinet/.env, which this runner deliberately does NOT source
# wholesale (see the secrets note above — the tracked template ships empty
# placeholders that would shadow real shared-env keys). But since F3
# (2026-07-05: canary exercises the REAL act-first calendar path; the
# "Cabinet" sandbox is retired) the probe MUST see the same calendar config
# the live lane uses — without it _resolve_calendar falls back to the retired
# "Cabinet" default and the weekly canary freezes calendar_event_create every
# Monday on 'calinfo: calendar not found' (seen 2026-07-06/07). So import ONLY
# the allowlisted calendar keys, line-parsed (never sourced — no code
# execution, no secret shadowing), skipping empty values and anything already
# set. Absent file / absent keys ⇒ no-op and the canary fails closed as before.
if [ -f "$ROOT/cabinet/.env" ]; then
  while IFS='=' read -r k v; do
    case "$k" in
      ACTION_LANE_CALENDAR|CABINET_CAL_HELPER|CABINET_CAL_PRIVATE|CABINET_CAL_ALLDAY_BUSY_BLOCKS)
        v="${v%\"}"; v="${v#\"}"
        if [ -n "$v" ] && [ -z "$(printenv "$k")" ]; then export "$k=$v"; fi
        ;;
    esac
  done < "$ROOT/cabinet/.env"
fi

PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
cd "$ROOT" || exit 1
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

exec "$PY" - <<'PYEOF'
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.getcwd())          # repo root (launchd WorkingDirectory)

from framework.frontdoor import actfirst_canary, action_exec


def _ts() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Same non-clobbering env loader the live executor uses (backstop to the shell
# source above). A key that is STILL missing after this is a cannot-run and is
# handled inside run_canary as a freeze, per the TI-7 contract.
action_exec._load_shared_env()

kinds = actfirst_canary.canary_kinds()
if not kinds:
    # Nothing act-first-eligible yet (surfaces YAML still propose-only) — a
    # canary would probe nothing. Quiet no-op, NOT a failure: the runner arms
    # itself the moment the first kind is marked eligible.
    print(f"[{_ts()}] actfirst-canary: no act-first-eligible kinds — nothing to probe")
    sys.exit(0)

out = actfirst_canary.run_weekly(
    monday_post=action_exec._monday_post,        # JSON-built body, argv-free
    osascript=action_exec._default_osascript)    # argv-list only, never shell

canary = out.get("canary") or {}
summary = {
    "kinds_probed": len(canary.get("results") or []),
    "kinds_ok": sum(1 for r in (canary.get("results") or []) if r.get("ok")),
    "frozen_now": canary.get("frozen") or [],
    "breaker_frozen": [f.get("action_type")
                       for f in (out.get("breaker") or {}).get("frozen") or []],
    "silenced": [s.get("action_type")
                 for s in (out.get("silence") or {}).get("silenced") or []],
    "veto_divergences": len(out.get("veto_divergences") or []),
    "env_perms": (out.get("env_perms") or {}).get("mode") if out.get("env_perms") else None,
}
print(f"[{_ts()}] actfirst-canary: {json.dumps(summary, sort_keys=True)}")

# Pages are the human-attention lines (canary freezes, veto divergences,
# env-perms drift). Surface each verbatim so the log is greppable; a non-zero
# exit marks the run red for anything tailing the log. The freezes themselves
# are ALREADY in effect (Redis flags set inside run_canary) — this is telemetry,
# not enforcement.
for page in out.get("pages") or []:
    print(f"[{_ts()}] actfirst-canary PAGE: {page}")
sys.exit(1 if (out.get("pages") or []) else 0)
PYEOF
