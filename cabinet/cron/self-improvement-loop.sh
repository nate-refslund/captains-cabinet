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
# Cadence: invoked from role-evals-weekly.sh after eval + pattern detection,
# and optionally on its own LaunchAgent (see
# `cabinet/launchd/com.cabinet.self-improvement-loop.template.plist`).
#
# Exits 0 whenever the loop COMPLETES, regardless of how many proposals
# were applied — "no work to do" is a valid successful outcome.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

cd "$CABINET_ROOT"

echo "=== Self-improvement loop @ $(date -u '+%Y-%m-%dT%H:%M:%SZ') ==="

# Forward extra flags (e.g. --dry-run, --json, --window-days) to the module
exec python3 -m framework.learning.self_improvement_loop "$@"
