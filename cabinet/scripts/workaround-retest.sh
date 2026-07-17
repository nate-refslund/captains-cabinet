#!/bin/bash
# workaround-retest.sh — officer/CLI entry to the sandboxed workaround
# retest runner (thin exec wrapper; ALL logic + safety screens live in
# cabinet/scripts/workaround-retest.py so they are unit-testable).
#
# WHAT IT DOES: given workaround id(s) from cabinet/config/workarounds.yml
# (or --all, or --from-delta <radar-delta.json>), runs each row's SAFE
# read-only retest probe sandboxed and emits one JSON verdict line per row:
#   {"id": "...", "verdict": "still_needed" | "fix_confirmed" | "inconclusive", ...}
# A fix_confirmed verdict files a PROPOSE-ONLY retirement proposal
# (fingerprint-deduped, needs-ledger pattern) to
# shared/interfaces/workaround-retire-proposals.jsonl. Nothing is ever
# applied, upgraded, restarted, or edited by this tool.
#
# SAFETY (three honest layers; details in the .py header): (1) the registry
# is reviewed-PR config — the first trust boundary; (2) a fast screen filters
# drift/typos (read-only first-token allowlist, mutation-verb blocklist incl.
# path-qualified verbs, no redirection) — NOT a complete boundary, since a
# `bash -c` value can reassemble a verb at runtime; (3) on macOS execution
# runs under an OS sandbox (deny file-write/network/signal) that contains even
# a screen-bypassing verb — each verdict is stamped sandboxed=true|false. Env
# is constructed (no inherited credentials); output is scrubbed of secret
# shapes before journaling; hard per-probe timeout. Rows that fail the screen
# are refused, never executed.
#
# Usage:
#   bash cabinet/scripts/workaround-retest.sh <workaround-id> [...]
#   bash cabinet/scripts/workaround-retest.sh --all
#   bash cabinet/scripts/workaround-retest.sh --from-delta cabinet/logs/platform-radar/delta-YYYY-MM-DD.json
#   bash cabinet/scripts/workaround-retest.sh --list
#
# Doctrine: docs/runbooks/platform-adoption-gating.md
# Skill:    memory/skills/platform-radar-triage.md
# Exit:     0 ran · 2 usage · 3 row refused by screen · 4 registry/id error
#           · 5 delta unreadable
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3.12 "$SCRIPT_DIR/workaround-retest.py" "$@"
