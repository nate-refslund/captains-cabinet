#!/bin/bash
# run-undo-sweep.sh — launchd entry for the HOURLY UNDO-3 reconciliation sweep
# (checkpoint 2026-07-04 condition 5: "Schedule UNDO-3 sweep (with a real
# make_monday_probe — the None-probe mints false ttl_ok on outage)").
#
# This is the estate's FIRST machine-label producer: for every acted journal
# row past its 48h TTL whose ledger record is still outcome=unknown it emits a
# superseding ttl_ok / silent_revert consequence event (idempotent — a human
# confirm/undo already moved the cell, so the sweep skips it), computes the
# per-cell human-revert-rate (F2b input) and GCs journal files past the 30-day
# retention floor. All logic lives in framework/frontdoor/action_reconcile.py
# (run_sweep, built + tested dark in W2); this script only wires the LIVE env
# and transports around it.
#
# FALSE-LABEL GUARD (the exact checkpoint-cited failure path): run_sweep with
# monday_probe=None — or a probe that errors on a Monday outage — conservatively
# verdicts ttl_ok, i.e. it MINTS false ok-labels while blind. So this runner
# (1) refuses to sweep when no Monday key is present, and (2) pre-flights one
# read-only Monday query and SKIPS the whole run on failure. A skipped hour is
# recoverable (the outcome=unknown gate re-picks the rows next run); a false
# ttl_ok label is not.
#
# Secrets: MONDAY_API_TOKEN/MONDAY_API_KEY are read from the pipes' _shared/.env
# by value only inside the process env — never echoed, never in the plist.
# cabinet/.env is deliberately NOT sourced here: it ships empty placeholder
# values (e.g. ANTHROPIC_API_KEY=) that would shadow the real _shared keys if
# exported blindly, and the sweep needs nothing from it.
#
# Reversible:
#   launchctl bootout gui/$(id -u)/com.cabinet.undo-sweep \
#     || launchctl unload ~/Library/LaunchAgents/com.cabinet.undo-sweep.plist
set -o pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# launchd hands a minimal PATH that excludes Homebrew (python3.12, redis-cli).
export PATH="/opt/homebrew/bin:$PATH"
export REDIS_HOST="${REDIS_HOST:-localhost}"

# Monday key (+ NATE_MONDAY_USER_ID if set) live in the PersonalSource shared
# env (instance platform.yml shared_env_path, via lib/personal-env.sh — R070
# indirection) — the same source of truth action_exec uses for live deliveries.
. "$ROOT/cabinet/scripts/lib/personal-env.sh"
personal_env_source

PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
cd "$ROOT" || exit 1
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

exec "$PY" - <<'PYEOF'
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.getcwd())          # repo root (launchd WorkingDirectory)

from framework.frontdoor import action_exec, action_reconcile


def _ts() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Belt-and-braces env load (same non-clobbering loader the live executor uses),
# in case the shell source above was skipped (e.g. a moved .env).
action_exec._load_shared_env()

if not (os.environ.get("MONDAY_API_TOKEN") or os.environ.get("MONDAY_API_KEY")):
    # No key ⇒ no real probe ⇒ every past-TTL row would mint a blind ttl_ok.
    # Skip loudly; the outcome=unknown gate keeps the rows eligible next hour.
    print(f"[{_ts()}] undo-sweep: SKIPPED — MONDAY_API_TOKEN/MONDAY_API_KEY unset "
          "(a probe-less sweep mints false ttl_ok labels; fix the env, not the guard)")
    sys.exit(1)

try:
    # Read-only liveness pre-flight: _probe_verdict treats a probe EXCEPTION as
    # ttl_ok (conservative for a single flaky row), so a full Monday outage must
    # be caught BEFORE the sweep or every row gets a false ok-label.
    action_exec._monday_post("query { me { id } }", {})
except Exception as e:                                    # noqa: BLE001 — any outage skips
    print(f"[{_ts()}] undo-sweep: SKIPPED — Monday pre-flight failed ({e}); "
          "sweeping blind would mint false ttl_ok labels")
    sys.exit(1)

probe = action_reconcile.make_monday_probe(
    action_exec._monday_post,
    # Optional: attributing a revert to Nate's own hand upgrades the label to
    # verdict_human. Absent id ⇒ silent reverts stay verdict_judge (still valid).
    nate_user_id=os.environ.get("NATE_MONDAY_USER_ID") or None)

res = action_reconcile.run_sweep(monday_probe=probe)
summary = {
    "ttl_ok": len(res.get("ttl_ok") or []),
    "silent_reverts": len(res.get("silent_reverts") or []),
    "skipped": res.get("skipped", 0),
    "gc_pruned": len((res.get("gc") or {}).get("pruned") or []),
    "revert_rate_cells": len(res.get("human_revert_rates") or {}),
}
print(f"[{_ts()}] undo-sweep: {json.dumps(summary, sort_keys=True)}")
PYEOF
