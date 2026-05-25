#!/bin/bash
# send-to-group.sh — Legacy wrapper, auto-routes to the default warroom.
#
# Preserves the original CLI signature so every existing caller keeps working.
# New code should call send-to-warroom.sh directly with an explicit context.
#
# Usage: send-to-group.sh "Your message here"

MESSAGE="${1:?Usage: send-to-group.sh \"message\"}"

# Resolve the default warroom context from active-project or fall back to first entry in warrooms.yml
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEFAULT_CTX=$(cat "$CABINET_ROOT/instance/config/active-project.txt" 2>/dev/null | tr -d '[:space:]')
DEFAULT_CTX="${DEFAULT_CTX:-default}"
exec bash "$SCRIPT_DIR/send-to-warroom.sh" "$DEFAULT_CTX" "$MESSAGE"
