#!/bin/bash
# eval-org-002: Mission compiler produces valid DAG from sample outcomes
set -uo pipefail

CABINET_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
COMPILER="$CABINET_ROOT/cabinet/scripts/compile-mission.py"
OUTCOMES="$CABINET_ROOT/instance/config/outcomes.yml"

if [ ! -f "$COMPILER" ]; then
    echo "FAIL: mission compiler not found at $COMPILER"
    exit 1
fi

OUTPUT=$(python3 "$COMPILER" --outcomes "$OUTCOMES" --output json 2>&1)
EXIT_CODE=$?

if [ "$EXIT_CODE" -ne 0 ]; then
    echo "FAIL: mission compiler exited with code $EXIT_CODE: $OUTPUT"
    exit 1
fi

# Validate the output is valid JSON with expected structure
python3 - "$OUTPUT" << 'PY'
import json, sys

data = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
try:
    missions = json.loads(data)
except json.JSONDecodeError as e:
    print(f"FAIL: compiler output is not valid JSON: {e}")
    sys.exit(1)

if not isinstance(missions, (list, dict)):
    print(f"FAIL: expected list or dict, got {type(missions).__name__}")
    sys.exit(1)

if isinstance(missions, dict):
    missions = missions.get('missions', [missions])

if len(missions) == 0:
    print("FAIL: no missions produced")
    sys.exit(1)

for i, mission in enumerate(missions):
    wg = mission.get('work_graph', mission)
    nodes = wg.get('nodes', mission.get('nodes', []))
    edges = wg.get('edges', mission.get('edges', []))
    if len(nodes) == 0:
        print(f"FAIL: mission[{i}] has no nodes")
        sys.exit(1)
    # Check all nodes have IDs
    node_ids = set()
    for n in nodes:
        nid = n.get('id')
        if not nid:
            print(f"FAIL: mission[{i}] has node without id")
            sys.exit(1)
        node_ids.add(nid)
    # Check all edges reference valid nodes
    for e in edges:
        if e.get('from') not in node_ids:
            print(f"FAIL: edge references unknown from-node '{e.get('from')}'")
            sys.exit(1)
        if e.get('to') not in node_ids:
            print(f"FAIL: edge references unknown to-node '{e.get('to')}'")
            sys.exit(1)

print(f"OK: {len(missions)} missions with valid DAG structure")
PY
