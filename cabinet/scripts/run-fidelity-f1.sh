#!/bin/bash
# run-fidelity-f1.sh — launchd entry for the WEEKLY F1 fidelity batch: the
# LABEL MINE (W3 reframe 2026-07-09; originally lane-supply 2026-07-05, part
# of waking the eval stack the 2026-07-03 re-review found dead at runtime —
# F1 existed as framework/fidelity/run_f1.py with a __main__ but NOTHING
# scheduled it).
#
# What one run does (framework/fidelity/run_f1.py): build held-out reply
# cases → blind-drive the officer (leak-guarded, no side effects) → draft a
# generic-assistant baseline → score (OAuth judge + Voyage STYLE) → aggregate
# the decision-match rate and assert the clone still beats the 0.083
# generic-assistant baseline. A regression here (exit nonzero + the assert
# message in the log) is the weekly canary that the clone's judgment decayed.
#
# WEEKLY, KNOBS ON (was: "MONTHLY because a batch is expensive"). The batch
# is no longer framed as a cost canary — it is the org's richest label mine
# (§4.3-5 reframe): with F1_WITH_INTENT=1 + F1_EMIT_SCORED=1 (Captain-
# authorized D1 knobs, 2026-06-20 — run_f1.run_batch docstring) every scored
# case persists a fidelity-case-scored consequence event, i.e. a LABEL.
# Labels are calibration INPUT (judge-calibration / D5 chain), never
# promotion fuel — the label floor and CG-10 stay fail-closed. Cost stays
# bounded (~24 drives per role per run) and is watched on the revived cost
# ledger (cabinet:cost:tokens:daily, live since 2026-07-07). Schedule:
# services.yml `fidelity-f1`, weekly Monday 06:30 (generate-plists.py renders
# launchd Weekday/Hour/Minute; weekday rows get an 8-day watchdog floor —
# registry.py::_floor_for_entry).
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
# Knobs (env, optional):
#   F1_ROLES        comma-separated lane roster (default "cos" — one lane;
#                   extend incrementally, e.g. "cos,polads-ceo", as verdict
#                   demand and cost budget allow).
#   F1_ROLE         legacy single-role override (honored when F1_ROLES unset).
#   F1_CASES        cases per role per run (default 24).
#   F1_WITH_INTENT  default 1 here (label mine); set 0 to revert to
#                   decision-only scoring.
#   F1_EMIT_SCORED  default 1 here (labels persisted); set 0 for a dry run.
#   F1_GATHER       default 1 here: the scheduled canary exercises the real
#                   gather-first reply path. Set 0 only for the explicit
#                   context-starved diagnostic arm, together with
#                   F1_EMIT_SCORED=0: scored rows do not carry an arm marker,
#                   so a diagnostic must not bank starved labels.
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

# Label-mine defaults (explicit env always wins — the services.yml row sets
# them too, so what launchd runs is manifest-visible).
export F1_WITH_INTENT="${F1_WITH_INTENT:-1}"
export F1_EMIT_SCORED="${F1_EMIT_SCORED:-1}"
export F1_GATHER="${F1_GATHER:-1}"

# Scored consequence rows do not carry the context-arm marker. Refuse every
# context-starved + emit-scored combination BEFORE a Python drive so a manual
# diagnostic cannot silently bank arm-ambiguous labels. Truthiness mirrors
# framework.fidelity.run_f1._env_flag (portable to macOS Bash 3.2).
_f1_truthy() {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) return 0 ;;
    *)             return 1 ;;
  esac
}
if ! _f1_truthy "$F1_GATHER" && _f1_truthy "$F1_EMIT_SCORED"; then
  echo "fidelity-f1: refusing context-starved scored run; set F1_EMIT_SCORED=0 with F1_GATHER=0" >&2
  exit 64
fi

ROLES="${F1_ROLES:-${F1_ROLE:-cos}}"
CASES="${F1_CASES:-24}"

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] fidelity-f1: starting weekly label-mine batch" \
     "(roles=${ROLES}, cases/role=${CASES}, with_intent=${F1_WITH_INTENT}," \
     "emit_scored=${F1_EMIT_SCORED}, gather=${F1_GATHER})"

rc=0
IFS=',' read -ra _ROLE_ARR <<< "$ROLES"
for role in "${_ROLE_ARR[@]}"; do
  role="${role// /}"   # trim spaces
  [ -z "$role" ] && continue
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] fidelity-f1: lane role=$role"
  "$PY" framework/fidelity/run_f1.py "$role" "$CASES" || rc=$?
done
exit "$rc"
