#!/bin/bash
# dashboard-password.sh — securely recover the local dashboard password.
#
# Reads only DASHBOARD_PASSWORD from the Captain-owned cabinet/.env and copies
# it to the macOS clipboard. The password is never printed, placed in argv, or
# written to a log. Run from anywhere:
#   bash cabinet/scripts/dashboard-password.sh --copy
#
# Options:
#   --copy       Copy the password to the clipboard (default).
#   --help, -h   Print this help.

set -uo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
ENV_FILE="$CABINET_ROOT/cabinet/.env"

case "${1:---copy}" in
  --copy) ;;
  --help|-h)
    awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"
    exit 0
    ;;
  *)
    echo "dashboard-password: unknown option: $1" >&2
    exit 64
    ;;
esac
[ "$#" -le 1 ] || { echo "dashboard-password: too many arguments" >&2; exit 64; }

if [ ! -f "$ENV_FILE" ]; then
  echo "Dashboard password is not set up yet. Run: bash cabinet/scripts/setup-env.sh --defaults" >&2
  exit 1
fi
if [ -L "$ENV_FILE" ]; then
  echo "Refusing to read cabinet/.env because it is a symbolic link." >&2
  exit 1
fi
if [ ! -O "$ENV_FILE" ]; then
  echo "Refusing to read cabinet/.env because it is not owned by the current user." >&2
  exit 1
fi

# GNU stat accepts `-f` as filesystem mode and may exit 0 with a non-mode
# report, so a BSD-or-GNU `||` chain is not portable. Keep the BSD result only
# when it is an octal mode; otherwise query the GNU form.
mode="$(stat -f '%Lp' "$ENV_FILE" 2>/dev/null || true)"
case "$mode" in
  ''|*[!0-7]*) mode="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || true)" ;;
esac
if [ "$mode" != "600" ]; then
  echo "Refusing to read cabinet/.env until its permissions are 600 (Captain only)." >&2
  echo "Fix it with: chmod 600 cabinet/.env" >&2
  exit 1
fi

password="$(sed -n 's/^DASHBOARD_PASSWORD=//p' "$ENV_FILE" | head -n 1)"
case "$password" in
  \"*\") password="${password#\"}"; password="${password%\"}" ;;
  \'*\') password="${password#\'}"; password="${password%\'}" ;;
esac
if [ -z "$password" ] || [ "$password" = "changeme" ] || [ "$password" = "changeme_secure_password" ]; then
  unset password
  echo "No secure dashboard password is configured. Run: bash cabinet/scripts/setup-env.sh --defaults" >&2
  exit 1
fi
if ! command -v pbcopy >/dev/null 2>&1; then
  unset password
  echo "Clipboard access is unavailable. Run this command on the Cabinet Mac." >&2
  exit 1
fi

if ! printf '%s' "$password" | pbcopy; then
  unset password
  echo "Could not copy the dashboard password to the clipboard." >&2
  exit 1
fi
unset password
echo "Dashboard password copied to the clipboard. It was not printed."
