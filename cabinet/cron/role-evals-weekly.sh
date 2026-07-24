#!/usr/bin/env bash
# role-evals-weekly.sh — Weekly role eval cron: run all evals, scan for
# failure patterns that warrant role-charter evolution proposals, then
# CLOSE THE LOOP by handing control to the self-improvement loop driver
# which validates learnings and — report-only by default (services.yml
# REPORT_ONLY="1") — WITHHOLDS applies; it auto-applies gate-cleared
# learnings ONLY when armed via REPORT_ONLY=0 (a Captain-gated switch).
#
# Phase 2 of the convergence plan + R8 (close the loop). Cadence: weekly
# via launchd (see `cabinet/launchd/com.cabinet.role-evals-weekly.template.plist`).
#
# Flow:
#   1. Run every registered role eval via `framework.measurement.role_eval_runner`
#      — emits eval_run_started + eval_passed/eval_failed events per eval.
#      Role attribution is roster-driven (R8 retarget, 2026-07-04): declared
#      slugs from the retired work-preset roster (cto/cpo/cro/coo) resolve
#      against cabinet/officer-capabilities.conf to a LIVE role (this
#      deployment: cos), so step 3's proposals target roles that
#      roles.lifecycle.load_role can actually load instead of dead-ending.
#   2. Scan the last 4 weeks of eval_failed events for clusters via
#      `framework.measurement.eval_pattern_detector` — surfaces patterns
#      worth a charter amendment.
#   3. Hand off to `cabinet/cron/self-improvement-loop.sh` which:
#         - drafts role evolution proposals from the patterns
#         - runs the scenario + golden eval validation gate
#         - REPORT-ONLY BY DEFAULT (services.yml REPORT_ONLY="1", audit-
#           ratified soak): validated proposals are WITHHELD as would-apply,
#           zero mutations. Auto-apply arms ONLY on an explicit REPORT_ONLY=0
#           (a Captain-gated switch); even then it applies only what clears
#           the validation gate — skeleton proposals stay
#           pending_captain_approval (applied changes log
#           `captain_auto_ratified: true` for audit)
#         - proposes hat graduations (auto-applied only when armed)
#         - induces + promotes draft skills
#         - emits self_improvement_loop_completed bracketing the run
#   4. Print a structured summary; logs flow to ~/Library/Logs/cabinet/
#      (when invoked from the LaunchAgent).
#
# Exits 0 even if individual evals fail — the runner records eval_failed
# events, and the loop is the consumer of that signal.

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

echo "=== Role evals — weekly run @ $(date -u '+%Y-%m-%dT%H:%M:%SZ') ==="

# Step 1: Run all evals (always exit 0 so we still hit pattern detection)
python3 -m framework.measurement.role_eval_runner || true

echo ""
echo "=== Pattern detection (window=28d, min_occurrences=3) ==="

# Step 2: Scan for failure patterns (read-only signal for the loop driver)
python3 -m framework.measurement.eval_pattern_detector || true

echo ""
echo "=== Self-improvement loop (proposals → validate → report-only; auto-apply only when armed via REPORT_ONLY=0) ==="

# Step 3: Close the loop. The driver handles its own failure modes; if it
# returns non-zero we still exit 0 here so the LaunchAgent doesn't loop on
# transient module failures (the events themselves are the audit signal).
"$SCRIPT_DIR/self-improvement-loop.sh" || echo "self-improvement-loop returned non-zero (loop completion is best-effort)"

exit 0
