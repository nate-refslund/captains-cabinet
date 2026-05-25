#!/bin/bash
# run-org-evals.sh — Org-level eval runner
# Tests the Cabinet as a self-organizing system, not just individual behaviors.
#
# Usage: bash run-org-evals.sh [--verbose]

set -uo pipefail

CABINET_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../.." && pwd)"
EVALS_DIR="$CABINET_ROOT/cabinet/scripts/evals"

VERBOSE=${1:-""}
PASS=0
FAIL=0
SKIP=0

log() { echo "$1"; }
pass() { PASS=$((PASS + 1)); log "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); log "  FAIL: $1"; }
skip() { SKIP=$((SKIP + 1)); log "  SKIP: $1"; }

log "=== Org-Level Eval Runner ==="
log "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
log ""

# ------------------------------------------------------------------
# EVAL-ORG-001: Outcome Schema Validation
# ------------------------------------------------------------------
log "EVAL-ORG-001: Outcome Schema Validation"
if [ -f "$EVALS_DIR/eval-org-001-outcome-schema.sh" ]; then
    RESULT=$(bash "$EVALS_DIR/eval-org-001-outcome-schema.sh" "$CABINET_ROOT" 2>&1)
    if [ $? -eq 0 ]; then
        pass "Outcome schema validation"
    else
        fail "Outcome schema validation: $RESULT"
    fi
else
    skip "eval-org-001 not found"
fi

# ------------------------------------------------------------------
# EVAL-ORG-002: Mission Compiler
# ------------------------------------------------------------------
log "EVAL-ORG-002: Mission Compiler"
if [ -f "$EVALS_DIR/eval-org-002-mission-compiler.sh" ]; then
    RESULT=$(bash "$EVALS_DIR/eval-org-002-mission-compiler.sh" "$CABINET_ROOT" 2>&1)
    if [ $? -eq 0 ]; then
        pass "Mission compiler produces valid DAG"
    else
        fail "Mission compiler: $RESULT"
    fi
else
    skip "eval-org-002 not found"
fi

# ------------------------------------------------------------------
# EVAL-ORG-003: Work Graph Integrity
# ------------------------------------------------------------------
log "EVAL-ORG-003: Work Graph Integrity"
if [ -f "$EVALS_DIR/eval-org-003-work-graph-integrity.sh" ]; then
    RESULT=$(bash "$EVALS_DIR/eval-org-003-work-graph-integrity.sh" "$CABINET_ROOT" 2>&1)
    if [ $? -eq 0 ]; then
        pass "Work graph integrity"
    else
        fail "Work graph integrity: $RESULT"
    fi
else
    skip "eval-org-003 not found"
fi

# ------------------------------------------------------------------
# EVAL-ORG-004: OVI Computation + Trend
# ------------------------------------------------------------------
log "EVAL-ORG-004: OVI Computation + Trend"
if [ -f "$EVALS_DIR/eval-org-004-ovi-computation.sh" ]; then
    RESULT=$(bash "$EVALS_DIR/eval-org-004-ovi-computation.sh" "$CABINET_ROOT" 2>&1)
    if [ $? -eq 0 ]; then
        pass "OVI computation + trend detection"
    else
        fail "OVI computation: $RESULT"
    fi
else
    skip "eval-org-004 not found"
fi

# ------------------------------------------------------------------
# EVAL-ORG-005: Policy Engine
# ------------------------------------------------------------------
log "EVAL-ORG-005: Policy Engine"
if [ -f "$EVALS_DIR/eval-org-005-policy-engine.sh" ]; then
    RESULT=$(bash "$EVALS_DIR/eval-org-005-policy-engine.sh" "$CABINET_ROOT" 2>&1)
    if [ $? -eq 0 ]; then
        pass "Policy engine"
    else
        fail "Policy engine: $RESULT"
    fi
else
    skip "eval-org-005 not found"
fi

# ------------------------------------------------------------------
# EVAL-ORG-006: Role Lineage
# ------------------------------------------------------------------
log "EVAL-ORG-006: Role Lineage"
if [ -f "$EVALS_DIR/eval-org-006-role-lineage.sh" ]; then
    RESULT=$(bash "$EVALS_DIR/eval-org-006-role-lineage.sh" "$CABINET_ROOT" 2>&1)
    if [ $? -eq 0 ]; then
        pass "Role lineage"
    else
        fail "Role lineage: $RESULT"
    fi
else
    skip "eval-org-006 not found"
fi

# ------------------------------------------------------------------
# EVAL-ORG-007: Digest Sanitization
# ------------------------------------------------------------------
log "EVAL-ORG-007: Digest Sanitization"
if [ -f "$EVALS_DIR/eval-org-007-digest-sanitization.sh" ]; then
    RESULT=$(bash "$EVALS_DIR/eval-org-007-digest-sanitization.sh" "$CABINET_ROOT" 2>&1)
    if [ $? -eq 0 ]; then
        pass "Digest sanitization"
    else
        fail "Digest sanitization: $RESULT"
    fi
else
    skip "eval-org-007 not found"
fi

# ------------------------------------------------------------------
# EVAL-ORG-008: Three-Layer Separation
# ------------------------------------------------------------------
log "EVAL-ORG-008: Three-Layer Separation"
if [ -f "$EVALS_DIR/eval-org-008-three-layer-separation.sh" ]; then
    RESULT=$(bash "$EVALS_DIR/eval-org-008-three-layer-separation.sh" "$CABINET_ROOT" 2>&1)
    if [ $? -eq 0 ]; then
        pass "Three-layer separation"
    else
        fail "Three-layer separation: $RESULT"
    fi
else
    skip "eval-org-008 not found"
fi

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
log ""
log "=== Summary ==="
log "PASS: $PASS  FAIL: $FAIL  SKIP: $SKIP"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
