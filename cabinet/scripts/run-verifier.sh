#!/bin/bash
# run-verifier.sh — launchd entry for the HOURLY B2.8 verdict-supply verifier
# (lane-supply 2026-07-05; wakes the stack the 2026-07-03 re-review found dead:
# no __main__, no services.yml row, no plist, CABINET_PROBES_ENABLED only in
# comments).
#
# What one run does (framework/probes/run_verifier.py): read the consequence
# ledger, derive the executed act-first action cards' implicit success claims
# (cabinet:action:* cohort — the ledger rows with proposal.required=false),
# reconcile each against the machine outcome its correlation-id accumulated
# (undo-sweep ttl_ok / probe ok / probe failed), and emit
# review{verdict, source: verdict_judge} SUPERSEDES on the SAME
# (actor, lane, action_type) graduation cell the act-first gate reads. This is
# machine label supply — verdicts that flow with ZERO Captain attention.
#
# FAIL-CLOSED (Corridor invariants): outcome still unknown → RT#4
# could-not-observe → NO verdict; any error → NO verdict + nonzero exit; a
# landed HUMAN verdict is never overwritten (flavor-A seniority); fabrication
# demotes are structurally unreachable from this claim scope (see the module
# docstring). Reads the ledger only — NO external systems, NO Redis writes.
#
# Live emits require CABINET_PROBES_ENABLED=1 (set in the services.yml row /
# plist EnvironmentVariables — installing the plist IS the flip, same posture
# as the undo-sweep). `--dry-run` (any invocation) is always allowed: collector
# emit, zero ledger writes — the eyeball/proof mode.
#
# Secrets: none needed (ledger-only). cabinet/.env is still sourced for
# HEALTHCHECKS_PING_KEY (liveness ping, fail-open when absent) — values only in
# process env, never echoed, never argv.
#
# Reversible:
#   launchctl bootout gui/$(id -u)/com.cabinet.verifier \
#     && rm ~/Library/LaunchAgents/com.cabinet.verifier.plist
set -o pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# launchd hands a minimal PATH that excludes Homebrew (python3.12) — the
# retro-trigger FATAL lesson (services.yml:118-122).
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# Env order: cabinet/.env first, then the PersonalSource shared env so REAL
# keys win over cabinet/.env's empty placeholders (the run-undo-sweep.sh
# env-order gotcha — "empty env values never claim keys" is also enforced
# Python-side). The shared-env PATH is instance data (platform.yml
# shared_env_path, via lib/personal-env.sh — R070 indirection); a clean-room
# deployment (NullPersonalSource) configures none and sources nothing.
if [ -f "$ROOT/cabinet/.env" ]; then set -a; . "$ROOT/cabinet/.env"; set +a; fi
. "$ROOT/cabinet/scripts/lib/personal-env.sh"
personal_env_source

PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
cd "$ROOT" || exit 1
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

exec "$PY" -m framework.probes.run_verifier "$@"
