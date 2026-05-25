#!/bin/bash
# eval-org-006: Role lineage — append-only, compiler output correct
set -uo pipefail

CABINET_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
COMPILER="$CABINET_ROOT/cabinet/scripts/compile-role.py"

if [ ! -f "$COMPILER" ]; then
    echo "FAIL: compile-role.py not found"
    exit 1
fi

TMPDIR=$(mktemp -d /tmp/eval-org-006-XXXXXX)
trap 'rm -rf "$TMPDIR"' EXIT

BASEDIR="$TMPDIR/agents"
LINEAGEDIR="$TMPDIR/lineage"
OUTDIR="$TMPDIR/output"
mkdir -p "$BASEDIR" "$LINEAGEDIR" "$OUTDIR"

# Create a sample base role
cat > "$BASEDIR/test-officer.md" << 'EOF'
# Test Officer

This is the base role definition.

## Responsibilities
- Do things
EOF

FAILURES=0

# Test 1: base + no lineage = exact copy
python3 "$COMPILER" test-officer --base-dir "$BASEDIR" --lineage-dir "$LINEAGEDIR" --output-dir "$OUTDIR" 2>/dev/null
if [ -f "$OUTDIR/test-officer.md" ]; then
    if diff -q "$BASEDIR/test-officer.md" "$OUTDIR/test-officer.md" > /dev/null 2>&1; then
        echo "  OK: base + no lineage = exact copy"
    else
        echo "  FAIL: base + no lineage should produce exact copy"
        FAILURES=$((FAILURES + 1))
    fi
else
    echo "  FAIL: no output file produced"
    FAILURES=$((FAILURES + 1))
fi

# Test 2: base + empty adaptations = exact copy
cat > "$LINEAGEDIR/test-officer.yml" << 'EOF'
role: test-officer
base_definition: agents/test-officer.md
adaptations: []
EOF

rm -f "$OUTDIR/test-officer.md"
python3 "$COMPILER" test-officer --base-dir "$BASEDIR" --lineage-dir "$LINEAGEDIR" --output-dir "$OUTDIR" 2>/dev/null
if [ -f "$OUTDIR/test-officer.md" ]; then
    if diff -q "$BASEDIR/test-officer.md" "$OUTDIR/test-officer.md" > /dev/null 2>&1; then
        echo "  OK: base + empty adaptations = exact copy"
    else
        echo "  FAIL: base + empty adaptations should produce exact copy"
        FAILURES=$((FAILURES + 1))
    fi
fi

# Test 3: base + adaptations = base + Adaptations section
cat > "$LINEAGEDIR/test-officer.yml" << 'EOF'
role: test-officer
base_definition: agents/test-officer.md
adaptations:
  - timestamp: "2026-05-25T10:00:00Z"
    trigger: reflection_loop
    evidence: "Evidence text"
    adaptation: "Added new capability"
    rationale: "Formalizing observed behavior"
    approved_by: captain
EOF

rm -f "$OUTDIR/test-officer.md"
python3 "$COMPILER" test-officer --base-dir "$BASEDIR" --lineage-dir "$LINEAGEDIR" --output-dir "$OUTDIR" 2>/dev/null

if [ -f "$OUTDIR/test-officer.md" ]; then
    COMPILED=$(cat "$OUTDIR/test-officer.md")

    if ! echo "$COMPILED" | grep -q "Adaptations"; then
        echo "  FAIL: missing Adaptations section"
        FAILURES=$((FAILURES + 1))
    else
        echo "  OK: Adaptations section present"
    fi

    if ! echo "$COMPILED" | grep -q "Added new capability"; then
        echo "  FAIL: missing adaptation text"
        FAILURES=$((FAILURES + 1))
    else
        echo "  OK: Adaptation text preserved"
    fi

    if ! echo "$COMPILED" | grep -q "Do things"; then
        echo "  FAIL: missing base content"
        FAILURES=$((FAILURES + 1))
    else
        echo "  OK: Base content preserved"
    fi
else
    echo "  FAIL: no output file for adaptation test"
    FAILURES=$((FAILURES + 1))
fi

if [ "$FAILURES" -gt 0 ]; then
    echo "FAIL: $FAILURES role lineage checks failed"
    exit 1
fi

echo "OK: Role lineage verified"
exit 0
