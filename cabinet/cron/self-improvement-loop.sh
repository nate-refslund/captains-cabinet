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
# Exit code contract (loud-red gate, T2-arm-schedules review fix 2026-07-07):
# exits 0 whenever the loop COMPLETES with a green or not-evaluated
# validation gate, regardless of how many proposals were applied — "no work
# to do" is a valid successful outcome. Exits 3 (plus a stderr line carrying
# the watchdog's FATAL marker) when the gate WAS evaluated and is RED: a red
# gate parks every concrete proposal (blocked_by_validation), and under
# launchd that state must page (non-zero last-exit + marker scan), never log
# green. role-evals-weekly.sh wraps its inline call in `|| echo`, so the
# weekly chain tolerates the non-zero.
#
# REPORT_ONLY gate (audit-ratified soak mode, 2026-07-07): REPORT-ONLY IS
# THE DEFAULT — an UNSET or truthy (1/true/yes/on, case-insensitive)
# REPORT_ONLY makes this wrapper prepend `--report-only` to the driver
# args; ONLY an explicit REPORT_ONLY=0 (or false/no/off) arms apply-mode.
# (Review fix 2026-07-07: the gate used to default to ARMED when the env
# was absent, so role-evals-weekly.sh's inline call and hand runs bypassed
# the declared zero-mutation soak.) In report-only mode the driver runs
# the propose + validation stages for REAL but WITHHOLDS every apply/
# promote/graduate mutation; it emits the bracketing events with
# `report_only: true` + a `would_apply` summary, and prints a grep-able
# `REPORT_ONLY_SUMMARY:` JSON line into this service's log. The loud-red
# gate contract below applies unchanged — a RED evaluated validation gate
# still exits 3 and pages, report-only or not (a failing safety net is an
# org-health pathology independent of whether applies are armed). To arm
# auto-apply: flip the services.yml row env to REPORT_ONLY: "0" +
# re-render/reload (and export REPORT_ONLY=0 for the weekly chain / hand
# runs). The env gates ANY invocation of this wrapper — the LaunchAgent,
# the inline call from role-evals-weekly.sh, and manual runs alike.
#
# Forwarded flags (anything you pass to this script is forwarded verbatim
# to the Python driver `python3 -m framework.learning.self_improvement_loop`):
#
#   --dry-run            Plan only — write NO events, NO proposal YAMLs, NO
#                        draft skill files. Safe to run anywhere; produces a
#                        report of what *would* have been done.
#   --report-only        Propose + validate for real, apply WITHHELD; real
#                        bracketing events with report_only: true. Usually
#                        injected by the REPORT_ONLY env gate above rather
#                        than passed by hand. --dry-run wins if both given.
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
#   REPORT_ONLY=1 ./self-improvement-loop.sh      # observe-only soak pass
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

# REPORT_ONLY env gate (see header): prepend --report-only when armed.
# `set --` prepend is bash-3.2-safe (no array expansion under set -u) and
# involves no interpolation — the env var only selects a fixed literal flag.
#
# FAIL-SAFE DEFAULT (review fix 2026-07-07): UNSET defaults to REPORT-ONLY.
# The soak gate used to live only in the LaunchAgent's env, so any other
# caller — role-evals-weekly.sh's inline invocation, a hand run, a future
# weekly plist without the env — ran fully ARMED during the declared
# zero-mutation soak. Now only an explicit REPORT_ONLY=0 (or false/no/off)
# arms apply-mode; the services.yml flip-to-"0" instruction is unchanged and
# remains the one sanctioned arming switch.
case "$(printf '%s' "${REPORT_ONLY:-1}" | tr '[:upper:]' '[:lower:]')" in
  0|false|no|off)
    : # explicitly armed — flags pass through untouched
    ;;
  *)
    echo "REPORT_ONLY=${REPORT_ONLY:-<unset→1>} → running with --report-only (apply/promote/graduate withheld; export REPORT_ONLY=0 to arm)"
    set -- --report-only "$@"
    ;;
esac

# Forward all flags (--dry-run, --report-only, --skip-evals, --json,
# --window-days, etc.) to the Python driver. The driver parses them via
# argparse and applies the correct gate behavior; see its --help for the
# full list.
exec "$PY" -m framework.learning.self_improvement_loop "$@"
