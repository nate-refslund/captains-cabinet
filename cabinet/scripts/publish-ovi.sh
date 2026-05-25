#!/bin/bash
# publish-ovi.sh — Compute OVI and publish markdown report to shared/digests/
#
# Usage:
#   bash publish-ovi.sh                        # live DB computation
#   bash publish-ovi.sh --sample-data FILE     # from sample data (CI/testing)
#
# Output: shared/digests/ovi-YYYY-WNN.md

set -uo pipefail

CABINET_ROOT="${CABINET_ROOT:-/opt/founders-cabinet}"
DIGESTS_DIR="$CABINET_ROOT/shared/digests"
COMPUTE_SCRIPT="$CABINET_ROOT/cabinet/scripts/compute-ovi.py"

mkdir -p "$DIGESTS_DIR"

WEEK=$(date -u +%Y-W%V)
OUTPUT_FILE="$DIGESTS_DIR/ovi-${WEEK}.md"

ARGS=("--output" "markdown")
for arg in "$@"; do
    ARGS+=("$arg")
done

OVI_OUTPUT=$(python3 "$COMPUTE_SCRIPT" "${ARGS[@]}" 2>&1)
OVI_EXIT=$?

if [ "$OVI_EXIT" -ne 0 ]; then
    echo "ERROR: OVI computation failed (exit $OVI_EXIT):" >&2
    echo "$OVI_OUTPUT" >&2
    exit 1
fi

echo "$OVI_OUTPUT" > "$OUTPUT_FILE"
echo "OVI report published to $OUTPUT_FILE" >&2
