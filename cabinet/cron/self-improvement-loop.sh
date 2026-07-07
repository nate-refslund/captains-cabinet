#!/usr/bin/env bash
# self-improvement-loop.sh — Close the Cabinet's learning loop end-to-end.
#
# R8 of the convergence plan. The Cabinet had all the pieces of a learning
# loop (eval runner → pattern detector → evolution proposal generator → hat
# graduator → skill induction → scenario evals → golden eval shells) but
# none of them chained into each other. This script wires them together
# and AUTO-APPLIES validated changes — no Captain wait, per the framework
# directive that learning should not block on manual approval.
#
# Chain:
#
#   1. role-evals run their patterns (call already happened upstream
#      when invoked from role-evals-weekly.sh; included here for ad-hoc
#      use so this driver also stands alone)
#   2. self-improvement-loop module:
#         a. propose role evolution from patterns
#         b. validate proposals (scenario evals + golden eval shells)
#         c. auto-apply accepted proposals
#         d. propose + auto-apply hat graduations
#         e. induce + promote draft skills
#         f. emit self_improvement_loop_completed
#
# Cadence: every 6h on its own LaunchAgent (fleet manifest row
# `self-improvement-loop` in cabinet/services.yml, armed 2026-07-07;
# template `cabinet/launchd/com.cabinet.self-improvement-loop.template.plist`).
# Also invoked inline from role-evals-weekly.sh after eval + pattern
# detection — the two cadences are overlap-safe (unique loop_id per run,
# idempotent proposal application).
#
# Exits 0 whenever the loop COMPLETES, regardless of how many proposals
# were applied — "no work to do" is a valid successful outcome.
#
# Forwarded flags (anything you pass to this script is forwarded verbatim
# to the Python driver `python3 -m framework.learning.self_improvement_loop`):
#
#   --dry-run            Plan only — write NO events, NO proposal YAMLs, NO
#                        draft skill files. Safe to run anywhere; produces a
#                        report of what *would* have been done.
#   --skip-evals         Bypass scenario + golden eval validation gate.
#                        Apply learnings without safety checks. For
#                        development/debugging only — production runs leave
#                        this OFF.
#   --json               Emit the structured run report as JSON.
#   --window-days N      Pattern detection window (default 28).
#   --min-occurrences N  Minimum cluster size to propose on (default 3).
#
# Examples:
#   ./self-improvement-loop.sh                    # normal run
#   ./self-improvement-loop.sh --dry-run --json   # preview as JSON
#   ./self-improvement-loop.sh --skip-evals       # dev/debug auto-apply

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

# Source cabinet/.env (Telegram tokens etc.) if present — launchd/cron runs
# get no login environment, so without this every Telegram send dies
# token-less. set -a exports the vars to child scripts (send-to-group.sh /
# send-to-warroom.sh and helpers).
if [ -f "$CABINET_ROOT/cabinet/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$CABINET_ROOT/cabinet/.env"
  set +a
fi

cd "$CABINET_ROOT"

echo "=== Self-improvement loop @ $(date -u '+%Y-%m-%dT%H:%M:%SZ') ==="

# Interpreter: pin to the fleet's Python (same idiom as apoptosis-sweep.sh).
# Bare `python3` under launchd resolves to /usr/bin/python3 (system 3.9) —
# the framework targets 3.12, so an unpinned run dies on 3.12-only code.
PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"

# Forward all flags (--dry-run, --skip-evals, --json, --window-days, etc.)
# to the Python driver. The driver parses them via argparse and applies the
# correct gate behavior; see its --help for the full list.
exec "$PY" -m framework.learning.self_improvement_loop "$@"
