#!/bin/bash
# run-fidelity-f1.sh — launchd entry for the MONTHLY F1 fidelity batch
# (lane-supply 2026-07-05; part of waking the eval stack the 2026-07-03
# re-review found dead at runtime — F1 existed as framework/fidelity/run_f1.py
# with a __main__ but NOTHING scheduled it).
#
# What one run does (framework/fidelity/run_f1.py): build held-out reply
# cases → blind-drive the officer (leak-guarded, no side effects) → draft a
# generic-assistant baseline → score (OAuth judge + Voyage STYLE) → aggregate
# the decision-match rate and assert the clone still beats the 0.083
# generic-assistant baseline. A regression here (exit nonzero + the assert
# message in the log) is the monthly canary that the clone's judgment decayed.
#
# MONTHLY because a batch is expensive (n≈24 officer drives + judge calls) and
# fidelity drift is slow — the fast label loop is the hourly verifier + probes;
# this is the slow calibration floor. Schedule: services.yml `fidelity-f1`,
# calendar day 1 06:30 (generate-plists.py renders launchd Day/Hour/Minute).
#
# FAIL-SAFE: any failure (missing OAuth/Voyage creds, leaked cases, a lost
# baseline) exits nonzero with the reason in the log and writes NO misleading
# artifact — run_f1 emits its per-case consequence events through the same
# validated emitter as everything else, and leaked cases are counted +
# excluded, never silently scored (run_f1.py docstring).
#
# Secrets: OAuth judge + VOYAGE_API_KEY etc. reach the process via env from
# cabinet/.env / the PersonalSource shared env (instance platform.yml
# shared_env_path) — never argv, never echoed.
#
# Knobs (env, optional): F1_ROLE (default cos), F1_CASES (default 24).
#
# Reversible:
#   launchctl bootout gui/$(id -u)/com.cabinet.fidelity-f1 \
#     && rm ~/Library/LaunchAgents/com.cabinet.fidelity-f1.plist
set -o pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# launchd's minimal PATH excludes Homebrew (python3.12) — the retro-trigger
# FATAL lesson (services.yml:118-122). It ALSO excludes ~/.local/bin, where
# the `claude` CLI lives: oauth_llm.py drives officer+judge via `claude -p`
# subprocesses and swallows FileNotFoundError → without this the whole batch
# false-fails in seconds (empty decisions, match_rate 0.0, a false
# fidelity-decay page — seed-run finding 2026-07-07).
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

# Env order: cabinet/.env first, then the PersonalSource shared env so REAL
# keys win over cabinet/.env's empty placeholders (run-undo-sweep.sh env-order
# gotcha). Path is instance data via lib/personal-env.sh (R070 indirection).
if [ -f "$ROOT/cabinet/.env" ]; then set -a; . "$ROOT/cabinet/.env"; set +a; fi
. "$ROOT/cabinet/scripts/lib/personal-env.sh"
personal_env_source

PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
cd "$ROOT" || exit 1
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] fidelity-f1: starting monthly batch" \
     "(role=${F1_ROLE:-cos}, cases=${F1_CASES:-24})"
exec "$PY" framework/fidelity/run_f1.py "${F1_ROLE:-cos}" "${F1_CASES:-24}"
