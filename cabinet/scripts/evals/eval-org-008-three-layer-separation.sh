#!/bin/bash
# eval-org-008: Three-layer separation — framework must not reference instance paths
set -uo pipefail

CABINET_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

FAILURES=0

# Framework files must not hardcode instance-specific paths or values
# Allowed: references to instance/config/ as a PATTERN (load-preset reads it)
# Blocked: specific instance values (Notion IDs, product names, etc.)

# Check framework/ Python and YAML files for instance-specific references
INSTANCE_REFS=$(grep -rl "instance/memory/tier2/\(cos\|cto\|cpo\|cro\|coo\)/" \
    "$CABINET_ROOT/framework/" 2>/dev/null || true)
if [ -n "$INSTANCE_REFS" ]; then
    echo "FAIL: framework/ files reference specific officer tier2 paths:"
    echo "$INSTANCE_REFS"
    FAILURES=$((FAILURES + 1))
fi

# Framework policies must not reference specific product names
while IFS= read -r policy_file; do
    if grep -qi "sensed\|nate" "$policy_file" 2>/dev/null; then
        echo "FAIL: framework policy $policy_file contains product-specific references"
        FAILURES=$((FAILURES + 1))
    fi
done < <(find "$CABINET_ROOT/framework/policies/" -name '*.yml' 2>/dev/null)

# Framework schemas must not contain instance-specific defaults
while IFS= read -r schema_file; do
    if grep -qi "sensed\|nate" "$schema_file" 2>/dev/null; then
        echo "FAIL: framework schema $schema_file contains product-specific references"
        FAILURES=$((FAILURES + 1))
    fi
done < <(find "$CABINET_ROOT/framework/schemas/" -name '*.json' 2>/dev/null)

# OVI components (framework) must not reference instance-specific tables/queries
while IFS= read -r ovi_file; do
    if grep -qi "sensed\|nate" "$ovi_file" 2>/dev/null; then
        echo "FAIL: framework OVI config $ovi_file contains product-specific references"
        FAILURES=$((FAILURES + 1))
    fi
done < <(find "$CABINET_ROOT/framework/ovi/" -name '*.yml' 2>/dev/null)

# Instance config must not contain framework-level policy definitions
# (policies in instance/ are overrides only, not base definitions)
if [ -d "$CABINET_ROOT/instance/config/policies" ]; then
    while IFS= read -r policy_file; do
        if grep -q "type: binary_block\|type: destructive_rm" "$policy_file" 2>/dev/null; then
            echo "WARN: instance policy $policy_file contains framework-level policy types (should be in framework/policies/)"
        fi
    done < <(find "$CABINET_ROOT/instance/config/policies/" -name '*.yml' 2>/dev/null)
fi

# Verify product.yml does not contain Sensed-specific references
if grep -qi "sensed" "$CABINET_ROOT/instance/config/product.yml" 2>/dev/null; then
    echo "FAIL: instance/config/product.yml still contains Sensed references"
    FAILURES=$((FAILURES + 1))
fi

if [ "$FAILURES" -gt 0 ]; then
    echo "FAIL: $FAILURES layer separation violations found"
    exit 1
fi

echo "OK: Three-layer separation intact"
exit 0
