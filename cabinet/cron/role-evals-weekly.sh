#!/usr/bin/env bash
# role-evals-weekly.sh — Weekly role eval cron: run all evals + scan for
# failure patterns that warrant role-charter evolution proposals.
#
# Phase 2 of the convergence plan. Cadence: weekly via launchd (see
# `cabinet/launchd/com.cabinet.role-evals-weekly.template.plist`).
#
# Flow:
#   1. Run every registered role eval via `framework.measurement.role_eval_runner`
#      — emits eval_run_started + eval_passed/eval_failed events per eval.
#   2. Scan the last 4 weeks of eval_failed events for clusters via
#      `framework.measurement.eval_pattern_detector` — surfaces patterns
#      worth a charter amendment.
#   3. Print a structured summary; logs flow to ~/Library/Logs/cabinet/
#      (when invoked from the LaunchAgent).
#
# Exits 0 even if individual evals fail — the runner records eval_failed
# events, and pattern detection is the consumption signal, not exit code.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

cd "$CABINET_ROOT"

echo "=== Role evals — weekly run @ $(date -u '+%Y-%m-%dT%H:%M:%SZ') ==="

# Step 1: Run all evals (always exit 0 so we still hit pattern detection)
python3 -m framework.measurement.role_eval_runner || true

echo ""
echo "=== Pattern detection (window=28d, min_occurrences=3) ==="

# Step 2: Scan for failure patterns
python3 -m framework.measurement.eval_pattern_detector

exit 0
