#!/usr/bin/env bash
# migrate-active-task.sh — Spec 049 Phase 2a/3 (CTO #5 / lifecycle §3).
#
# Upgrades a pre-Spec-049 `.claude/active-task.json` (partial schema) to the
# current schema version on first /self-review. Adds MISSING fields with
# framework defaults; EXISTING fields are preserved. Idempotent: re-running
# is a no-op on an already-current file.
#
# Schema version history:
#   v2 (Phase 2a): schema_version, agentSteps, agentTokensTotal, agentStepCap,
#       agentTokenCap, agentStepBaseline, agentTokenBaseline, visualUatCost,
#       selfReviewPassed, selfReviewPassedAt, selfReviewPassedSha,
#       selfReviewIterationCount, gate4BuildHash, checkpointBuildHash,
#       atomic_commit_override.  (15 fields)
#   v3 (Phase 3 — this release): adds visualUatCostCap (Gate-4 STATE field,
#       config-init + bump-mutated), visualUatPagesPassedFailed, visualUatLastError.
#       (18 fields)  Per spec schema-version discipline: Phase 2a shipped real
#       v2 officer files → Phase 3 new fields MUST bump to v3.
#
# Baselines (agentStepBaseline / agentTokenBaseline, null until /pickup-task
# snapshots them): the C1 sources are CUMULATIVE per-officer, not per-task —
# `cabinet:toolcalls:$OFFICER` (steps) and the daily HSET `<role>_input +
# <role>_output` (tokens; NOT _cost_micro — that's micro-USD cost → visualUatCost).
# Per-task usage = current cumulative MINUS the baseline snapshotted at
# /pickup-task. agentSteps/agentTokensTotal hold those deltas.
#
# Project-specific cap VALUES (agentStepCap/agentTokenCap/visual_uat caps) are
# set from `.cabinet/agent-instructions.md → agent_caps` at /pickup-task CREATE
# time (lifecycle §1). This migration only guarantees the fields EXIST with
# framework defaults so downstream gates never read an undefined field.
#
# Usage:
#   migrate-active-task.sh [--validate] [path]
#     path      defaults to ./.claude/active-task.json
#     --validate  exit 0 if file is valid v3, else exit 3 + list missing/bad fields
set -euo pipefail

SCHEMA_VERSION=3
# Framework defaults (Spec 049 §"Per-task token+step ceiling" code block).
DEF_STEP_CAP=200
DEF_TOKEN_CAP=10000000
DEF_VISUAL_UAT_COST_CAP=5

VALIDATE=0
TARGET=""
for arg in "$@"; do
  case "$arg" in
    --validate) VALIDATE=1 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    -*) echo "migrate-active-task.sh: unknown flag: $arg" >&2; exit 2 ;;
    *) TARGET="$arg" ;;
  esac
done
TARGET="${TARGET:-./.claude/active-task.json}"

command -v jq >/dev/null 2>&1 || { echo "migrate-active-task.sh: jq required" >&2; exit 2; }

# The complete v3 default object. Merge semantics: defaults * existing → existing
# values win per-key, defaults fill only the missing keys (jq '*' is recursive
# but every default here is scalar/null so it behaves as fill-missing).
read -r -d '' V3_DEFAULTS <<JSON || true
{
  "schema_version": ${SCHEMA_VERSION},
  "agentSteps": 0,
  "agentTokensTotal": 0,
  "agentStepCap": ${DEF_STEP_CAP},
  "agentTokenCap": ${DEF_TOKEN_CAP},
  "agentStepBaseline": null,
  "agentTokenBaseline": null,
  "visualUatCost": 0,
  "visualUatCostCap": ${DEF_VISUAL_UAT_COST_CAP},
  "selfReviewPassed": false,
  "selfReviewPassedAt": null,
  "selfReviewPassedSha": null,
  "selfReviewIterationCount": 0,
  "gate4BuildHash": null,
  "checkpointBuildHash": null,
  "atomic_commit_override": null,
  "visualUatPagesPassedFailed": {"passed":[],"failed":[],"indeterminate":[]},
  "visualUatLastError": null
}
JSON

# Required v3 keys for --validate (caps may legitimately be re-tuned, presence is
# what the gate checks).
REQUIRED_KEYS='["schema_version","agentSteps","agentTokensTotal","agentStepCap","agentTokenCap","agentStepBaseline","agentTokenBaseline","visualUatCost","visualUatCostCap","selfReviewPassed","selfReviewPassedAt","selfReviewPassedSha","selfReviewIterationCount","gate4BuildHash","checkpointBuildHash","atomic_commit_override","visualUatPagesPassedFailed","visualUatLastError"]'

if [ ! -f "$TARGET" ]; then
  echo "migrate-active-task.sh: no state file at $TARGET" >&2
  # A missing file is not this script's job to create (/pickup-task creates it).
  exit 4
fi

if ! jq -e . "$TARGET" >/dev/null 2>&1; then
  echo "migrate-active-task.sh: $TARGET is not valid JSON" >&2
  exit 3
fi

if [ "$VALIDATE" -eq 1 ]; then
  MISSING=$(jq -r --argjson req "$REQUIRED_KEYS" '$req - (keys) | .[]' "$TARGET" 2>/dev/null || true)
  SV=$(jq -r '.schema_version // empty' "$TARGET")
  if [ -n "$MISSING" ]; then
    echo "INVALID: $TARGET missing v3 fields:" >&2
    echo "$MISSING" | sed 's/^/  - /' >&2
    exit 3
  fi
  if [ "$SV" != "$SCHEMA_VERSION" ]; then
    # Emit WARN on known-older version (m1), list defaulted keys.
    if [ "$SV" = "2" ]; then
      echo "WARN: $TARGET is schema_version=2; expected $SCHEMA_VERSION. New v3 fields will be defaulted (visualUatCostCap, visualUatPagesPassedFailed, visualUatLastError). Run without --validate to migrate." >&2
    else
      echo "INVALID: $TARGET schema_version=$SV (expected $SCHEMA_VERSION)" >&2
      exit 3
    fi
  else
    echo "VALID: $TARGET is Spec 049 v3 schema"
  fi
  exit 0
fi

# Migrate: defaults filled where missing, existing preserved, schema_version
# forced to current. Atomic write.
TMP="$(mktemp "${TARGET}.migrate.XXXXXX")"
trap 'rm -f "$TMP"' EXIT
jq -n --argjson defaults "$V3_DEFAULTS" --slurpfile existing "$TARGET" \
  '$defaults * $existing[0] | .schema_version = '"$SCHEMA_VERSION" > "$TMP"
mv "$TMP" "$TARGET"
trap - EXIT

echo "migrated: $TARGET → schema_version $SCHEMA_VERSION (existing fields preserved)"
