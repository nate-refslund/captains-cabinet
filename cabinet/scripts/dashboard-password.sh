#!/bin/bash
# dashboard-password.sh — reset or inspect the local dashboard password.
#
# The operator CHOOSES their dashboard password on first open of the dashboard
# (the login page shows a "create a password" screen while none is set). This
# script is no longer the way in — it is the reset/inspect helper:
#
#   --reset      Clear the stored password and return the dashboard to its
#                first-run "create a password" screen. Reveals nothing — the
#                operator simply chooses a new one. This is what the
#                double-clickable "Reset Cabinet Password" runs.
#   --copy       Copy the current password to the macOS clipboard without
#                printing it (for a Captain who set one and wants it to hand).
#   --help, -h   Print this help.
#
# Reads/writes only DASHBOARD_PASSWORD in the Captain-owned cabinet/.env. The
# password is never printed, placed in argv, or written to a log. Run from
# anywhere:
#   bash cabinet/scripts/dashboard-password.sh --reset

set -uo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
ENV_FILE="$CABINET_ROOT/cabinet/.env"

MODE="copy"
case "${1:---copy}" in
  --copy) MODE="copy" ;;
  --reset) MODE="reset" ;;
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

# ---------------------------------------------------------------------------
# Shared safety gate on cabinet/.env: it must exist, be a real file owned by us
# with 0600 perms. Identical to the read path the copy mode has always used —
# the reset writes the same file, so it earns the same guard.
# ---------------------------------------------------------------------------
if [ ! -f "$ENV_FILE" ]; then
  echo "Dashboard is not set up yet. Run: bash cabinet/scripts/setup-env.sh --defaults" >&2
  exit 1
fi
if [ -L "$ENV_FILE" ]; then
  echo "Refusing to touch cabinet/.env because it is a symbolic link." >&2
  exit 1
fi
if [ ! -O "$ENV_FILE" ]; then
  echo "Refusing to touch cabinet/.env because it is not owned by the current user." >&2
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
  echo "Refusing to touch cabinet/.env until its permissions are 600 (Captain only)." >&2
  echo "Fix it with: chmod 600 cabinet/.env" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# --reset : clear the password, then restart the dashboard so the running
# process forgets it too and shows the first-run "create a password" screen.
# Reveals no secret; requires local machine access (this is a local file op).
# ---------------------------------------------------------------------------
if [ "$MODE" = "reset" ]; then
  tmp="$(mktemp "${ENV_FILE}.reset.XXXXXX")" || {
    echo "Could not create a temporary file to reset the password." >&2
    exit 1
  }
  chmod 600 "$tmp"
  if grep -qE '^DASHBOARD_PASSWORD=' "$ENV_FILE"; then
    # Replace the whole line (robust even if the value contains '=').
    awk '/^DASHBOARD_PASSWORD=/ { print "DASHBOARD_PASSWORD="; next } { print }' \
      "$ENV_FILE" > "$tmp"
  else
    cat "$ENV_FILE" > "$tmp"
    printf 'DASHBOARD_PASSWORD=\n' >> "$tmp"
  fi
  if ! mv "$tmp" "$ENV_FILE"; then
    rm -f "$tmp"
    echo "Could not save the reset. Nothing was changed." >&2
    exit 1
  fi
  chmod 600 "$ENV_FILE"

  # Drop the old password from the RUNNING dashboard so it returns to first-run.
  # On the Mac the dashboard is a launchd KeepAlive job; kickstart -k restarts
  # it, and it re-reads cabinet/.env (now with no password) on the way up.
  if command -v launchctl >/dev/null 2>&1 \
     && launchctl kickstart -k "gui/$(id -u)/com.cabinet.dashboard" >/dev/null 2>&1; then
    echo "Password cleared. The dashboard is restarting — open it and choose a new password."
  else
    echo "Password cleared. Reopen the dashboard (or restart the Cabinet) and it will ask you to choose a new password."
  fi
  exit 0
fi

# ---------------------------------------------------------------------------
# --copy : hand the current password to the clipboard without printing it.
# ---------------------------------------------------------------------------
password="$(sed -n 's/^DASHBOARD_PASSWORD=//p' "$ENV_FILE" | head -n 1)"
case "$password" in
  \"*\") password="${password#\"}"; password="${password%\"}" ;;
  \'*\') password="${password#\'}"; password="${password%\'}" ;;
esac
if [ -z "$password" ] || [ "$password" = "changeme" ] || [ "$password" = "changeme_secure_password" ]; then
  unset password
  echo "No password is set yet. Open the dashboard and choose one on the first screen." >&2
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
