#!/bin/bash
# Captain-side switch for the 72-hour observation posture.
#
# Presence is deliberately narrow-only. A running officer re-checks the marker
# in pre-tool-use.sh on every call, while a fresh launcher also switches
# CABINET_ENV to dev, removes computer-control, and installs source-write
# Seatbelt denies. Disable remains sticky in an existing process until restart.

set -euo pipefail

ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)}"
MARKER="$ROOT/instance/config/observe-only"
ACTION="${1:-status}"

marker_state() {
  # A dangling symlink has -e=false.  Test link-presence separately so it is
  # rejected as an invalid marker rather than silently disabling the cap.
  if [ ! -e "$MARKER" ] && [ ! -L "$MARKER" ]; then printf 'disabled\n'; return 0; fi
  if [ ! -f "$MARKER" ] || [ -L "$MARKER" ]; then printf 'invalid\n'; return 1; fi
  local value
  value=$(tr -d '[:space:]' < "$MARKER")
  if [ "$value" = active ]; then printf 'active\n'; return 0; fi
  printf 'invalid\n'
  return 1
}

case "$ACTION" in
  status)
    marker_state
    ;;
  enable)
    mkdir -p "$(dirname "$MARKER")"
    if [ -e "$MARKER" ] || [ -L "$MARKER" ]; then
      current=$(marker_state) || {
        echo "observe-only: existing marker is invalid; inspect it manually" >&2
        exit 1
      }
      [ "$current" = active ] && { echo "observe-only: already active"; exit 0; }
    fi
    umask 077
    tmp="$MARKER.tmp.$$"
    printf 'active\n' > "$tmp"
    mv "$tmp" "$MARKER"
    chmod 600 "$MARKER"
    # User-immutable is defense in depth; the officer Seatbelt profile and
    # hook are the actual same-UID runtime boundaries.
    chflags uchg "$MARKER" 2>/dev/null || true
    echo "observe-only: ACTIVE — restart officers to add env/CUA/Seatbelt layers"
    ;;
  disable)
    if [ -e "$MARKER" ] || [ -L "$MARKER" ]; then
      chflags nouchg "$MARKER" 2>/dev/null || true
      rm -f "$MARKER"
    fi
    echo "observe-only: disabled on disk; restart officers to remove sticky process caps"
    ;;
  *)
    echo "Usage: observe-only.sh {status|enable|disable}" >&2
    exit 64
    ;;
esac
