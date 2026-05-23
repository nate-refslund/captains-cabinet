#!/bin/bash
# send-to-group.sh — Legacy wrapper, auto-routes to sensed-warroom.
#
# Phase 1 CP7 (Captain decision 2026-04-16 CD3: auto-migrate existing
# send-to-group calls to sensed-warroom). Preserves the original CLI
# signature so every existing caller keeps working. New code should call
# send-to-warroom.sh directly with an explicit context.
#
# Usage: send-to-group.sh "Your message here"

MESSAGE="${1:?Usage: send-to-group.sh \"message\"}"

# Resolve sibling script path via $BASH_SOURCE so this works on Hetzner Docker
# (/opt/founders-cabinet/) AND on Mac native (~/work/captains-cabinet/) without
# branching on host. Reviewer audit caught hardcoded Docker path 2026-05-23.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/send-to-warroom.sh" sensed "$MESSAGE"
