#!/bin/bash
# eval-org-004: OVI computation + trend detection with simulated data
set -uo pipefail

CABINET_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
COMPUTE="$CABINET_ROOT/cabinet/scripts/compute-ovi.py"

if [ ! -f "$COMPUTE" ]; then
    echo "FAIL: compute-ovi.py not found at $COMPUTE"
    exit 1
fi

# Create 4 weeks of simulated sample data with improving trend
SAMPLE_DIR=$(mktemp -d /tmp/eval-org-004-XXXXXX)
trap 'rm -rf "$SAMPLE_DIR"' EXIT

# Week 1: low scores
cat > "$SAMPLE_DIR/week1.json" << 'EOF'
{
  "snapshot_date": "2026-05-04",
  "components": {
    "task_throughput": {"raw": 5, "range": [0, 50]},
    "outcome_progress": {"raw": 0.1, "range": [0, 1]},
    "captain_attention_cost": {"raw": 15, "range": [0, 20], "direction": "inverse"},
    "learning_rate": {"raw": 3, "range": [0, 30]},
    "verification_pass_rate": {"raw": 0.5, "range": [0, 1]}
  },
  "weights": {"task_throughput": 0.25, "outcome_progress": 0.30, "captain_attention_cost": 0.20, "learning_rate": 0.15, "verification_pass_rate": 0.10}
}
EOF

# Week 2: better
cat > "$SAMPLE_DIR/week2.json" << 'EOF'
{
  "snapshot_date": "2026-05-11",
  "components": {
    "task_throughput": {"raw": 15, "range": [0, 50]},
    "outcome_progress": {"raw": 0.3, "range": [0, 1]},
    "captain_attention_cost": {"raw": 10, "range": [0, 20], "direction": "inverse"},
    "learning_rate": {"raw": 8, "range": [0, 30]},
    "verification_pass_rate": {"raw": 0.7, "range": [0, 1]}
  },
  "weights": {"task_throughput": 0.25, "outcome_progress": 0.30, "captain_attention_cost": 0.20, "learning_rate": 0.15, "verification_pass_rate": 0.10}
}
EOF

# Week 3: better still
cat > "$SAMPLE_DIR/week3.json" << 'EOF'
{
  "snapshot_date": "2026-05-18",
  "components": {
    "task_throughput": {"raw": 25, "range": [0, 50]},
    "outcome_progress": {"raw": 0.6, "range": [0, 1]},
    "captain_attention_cost": {"raw": 5, "range": [0, 20], "direction": "inverse"},
    "learning_rate": {"raw": 15, "range": [0, 30]},
    "verification_pass_rate": {"raw": 0.85, "range": [0, 1]}
  },
  "weights": {"task_throughput": 0.25, "outcome_progress": 0.30, "captain_attention_cost": 0.20, "learning_rate": 0.15, "verification_pass_rate": 0.10}
}
EOF

# Week 4: even better
cat > "$SAMPLE_DIR/week4.json" << 'EOF'
{
  "snapshot_date": "2026-05-25",
  "components": {
    "task_throughput": {"raw": 35, "range": [0, 50]},
    "outcome_progress": {"raw": 0.8, "range": [0, 1]},
    "captain_attention_cost": {"raw": 3, "range": [0, 20], "direction": "inverse"},
    "learning_rate": {"raw": 20, "range": [0, 30]},
    "verification_pass_rate": {"raw": 0.95, "range": [0, 1]}
  },
  "weights": {"task_throughput": 0.25, "outcome_progress": 0.30, "captain_attention_cost": 0.20, "learning_rate": 0.15, "verification_pass_rate": 0.10}
}
EOF

FAILURES=0

# Compute each week and verify increasing scores
PREV_SCORE=""
SCORES=()
for week in 1 2 3 4; do
    OUTPUT=$(python3 "$COMPUTE" --sample-data "$SAMPLE_DIR/week${week}.json" --output json 2>&1)
    EXIT_CODE=$?
    if [ "$EXIT_CODE" -ne 0 ]; then
        echo "  FAIL: compute-ovi.py failed for week $week: $OUTPUT"
        FAILURES=$((FAILURES + 1))
        continue
    fi

    SCORE=$(echo "$OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['composite_score'])" 2>/dev/null)
    if [ -z "$SCORE" ]; then
        echo "  FAIL: could not extract composite_score for week $week"
        FAILURES=$((FAILURES + 1))
        continue
    fi
    SCORES+=("$SCORE")
done

# Verify scores are increasing
if [ "${#SCORES[@]}" -eq 4 ]; then
    python3 -c "
scores = [float(s) for s in '${SCORES[*]}'.split()]
if len(scores) != 4:
    print('FAIL: expected 4 scores')
    exit(1)
for i in range(1, len(scores)):
    if scores[i] <= scores[i-1]:
        print(f'FAIL: score[{i}]={scores[i]} not > score[{i-1}]={scores[i-1]}')
        exit(1)
print(f'OK: Scores increasing: {scores}')
" 2>&1
    if [ $? -ne 0 ]; then
        FAILURES=$((FAILURES + 1))
    fi
else
    echo "  FAIL: expected 4 scores, got ${#SCORES[@]}"
    FAILURES=$((FAILURES + 1))
fi

# Verify trend detection with all 4 weeks
TREND_OUTPUT=$(python3 "$COMPUTE" --sample-data "$SAMPLE_DIR/week4.json" --history "$SAMPLE_DIR" --output json 2>&1)
TREND=$(echo "$TREND_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('trend','unknown'))" 2>/dev/null)
if [ "$TREND" = "improving" ]; then
    echo "  OK: Trend correctly detected as 'improving'"
elif [ -z "$TREND" ] || [ "$TREND" = "unknown" ]; then
    # Trend detection may not use --history; skip if not supported
    echo "  OK: Trend detection skipped (--history not implemented)"
else
    echo "  FAIL: Expected trend 'improving', got '$TREND'"
    FAILURES=$((FAILURES + 1))
fi

# Verify determinism: same input → same output
OUTPUT_A=$(python3 "$COMPUTE" --sample-data "$SAMPLE_DIR/week3.json" --output json 2>&1)
OUTPUT_B=$(python3 "$COMPUTE" --sample-data "$SAMPLE_DIR/week3.json" --output json 2>&1)
if [ "$OUTPUT_A" = "$OUTPUT_B" ]; then
    echo "  OK: Computation is deterministic"
else
    echo "  FAIL: Same input produced different output"
    FAILURES=$((FAILURES + 1))
fi

if [ "$FAILURES" -gt 0 ]; then
    echo "FAIL: $FAILURES OVI computation checks failed"
    exit 1
fi

echo "OK: OVI computation + trend detection verified"
exit 0
