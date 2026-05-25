#!/bin/bash
# send-to-group.sh — Legacy wrapper, auto-routes to the active product warroom.
#
# Preserves the original CLI signature so every existing caller keeps working.
# New code should call send-to-warroom.sh directly with an explicit context.
#
# Usage: send-to-group.sh "Your message here"

MESSAGE="${1:?Usage: send-to-group.sh \"message\"}"

# Resolve sibling script path via $BASH_SOURCE so this works on Hetzner Docker
# (/opt/founders-cabinet/) AND on Mac native (~/work/captains-cabinet/) without
# branching on host. Reviewer audit caught hardcoded Docker path 2026-05-23.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-/opt/founders-cabinet}"
ACTIVE_CONTEXT="$(cat "$CABINET_ROOT/instance/config/active-project.txt" 2>/dev/null | tr -d '[:space:]')"
ACTIVE_CONTEXT="${ACTIVE_CONTEXT:-captains-cabinet}"
exec bash "$SCRIPT_DIR/send-to-warroom.sh" "$ACTIVE_CONTEXT" "$MESSAGE"
