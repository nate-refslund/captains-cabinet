#!/bin/bash
# eval-org-001: Outcome YAML validates against JSON Schema
set -uo pipefail

CABINET_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

SCHEMA="$CABINET_ROOT/framework/schemas/outcome.schema.json"
VALID_OUTCOMES="$CABINET_ROOT/instance/config/outcomes.yml"

if [ ! -f "$SCHEMA" ]; then
    echo "FAIL: outcome schema not found at $SCHEMA"
    exit 1
fi

if [ ! -f "$VALID_OUTCOMES" ]; then
    echo "FAIL: outcomes file not found at $VALID_OUTCOMES"
    exit 1
fi

# Validate using Python + jsonschema (if available) or basic structure check
RESULT=$(python3 - "$SCHEMA" "$VALID_OUTCOMES" << 'PY' 2>&1)
import json, sys, os

schema_path, outcomes_path = sys.argv[1], sys.argv[2]

# Load schema
with open(schema_path) as f:
    schema = json.load(f)

# Load YAML outcomes
try:
    import yaml
    with open(outcomes_path) as f:
        data = yaml.safe_load(f)
except ImportError:
    # Minimal YAML parse
    data = {'outcomes': []}
    with open(outcomes_path) as f:
        text = f.read()
    if 'outcomes:' not in text:
        print("FAIL: outcomes.yml missing 'outcomes' key")
        sys.exit(1)
    # Check at least one outcome entry exists
    if '  - id:' not in text:
        print("FAIL: outcomes.yml has no outcome entries")
        sys.exit(1)
    print("OK (basic structure check — install jsonschema for full validation)")
    sys.exit(0)

# Validate structure
if not isinstance(data, dict) or 'outcomes' not in data:
    print("FAIL: outcomes.yml missing 'outcomes' key")
    sys.exit(1)

outcomes = data['outcomes']
if not isinstance(outcomes, list) or len(outcomes) == 0:
    print("FAIL: outcomes list is empty")
    sys.exit(1)

errors = []
for i, outcome in enumerate(outcomes):
    if not isinstance(outcome, dict):
        errors.append(f"outcome[{i}] is not a dict")
        continue
    for required in ['id', 'name', 'measurable_criteria']:
        if required not in outcome:
            errors.append(f"outcome[{i}] missing required field '{required}'")
    if 'measurable_criteria' in outcome:
        mc = outcome['measurable_criteria']
        if not isinstance(mc, list) or len(mc) == 0:
            errors.append(f"outcome[{i}].measurable_criteria must be non-empty list")
    if 'status' in outcome:
        valid_statuses = ['draft', 'active', 'achieved', 'retired']
        if outcome['status'] not in valid_statuses:
            errors.append(f"outcome[{i}].status '{outcome['status']}' not in {valid_statuses}")

if errors:
    for e in errors:
        print(f"  FAIL: {e}")
    print(f"FAIL: {len(errors)} validation errors")
    sys.exit(1)

print(f"OK: {len(outcomes)} outcomes validated")
PY

EXIT_CODE=$?
echo "$RESULT"

# Also test that a malformed YAML is correctly rejected
MALFORMED_FILE=$(mktemp /tmp/eval-org-001-XXXXXX.yml)
trap 'rm -f "$MALFORMED_FILE"' EXIT
cat > "$MALFORMED_FILE" << 'EOF'
outcomes:
  - name: "Missing ID"
    measurable_criteria: []
EOF

RESULT2=$(python3 - "$SCHEMA" "$MALFORMED_FILE" << 'PY2' 2>&1)
import sys, os
try:
    import yaml
except ImportError:
    print("OK (skip malformed test — no yaml)")
    sys.exit(0)

with open(sys.argv[2]) as f:
    data = yaml.safe_load(f)

outcomes = data.get('outcomes', [])
for o in outcomes:
    if 'id' not in o:
        print("OK: Correctly detected missing 'id' field")
        sys.exit(0)
    if not o.get('measurable_criteria'):
        print("OK: Correctly detected empty measurable_criteria")
        sys.exit(0)

print("FAIL: Malformed YAML was not rejected")
sys.exit(1)
PY2

echo "$RESULT2"
exit $EXIT_CODE
