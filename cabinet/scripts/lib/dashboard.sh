#!/bin/bash
# dashboard.sh — the ONE place that answers "where is the dashboard, and is
# that thing on the port actually mine?" (identity-probe area, 2026-08-25).
#
# WHY THIS EXISTS — a measured incident, not a theory. On the Captain's Mac an
# unrelated local Next.js dev server was listening on 3100. Every probe in the
# tree asked `curl -fsS .../api/health` and treated ANY 200 as "the cabinet is
# up": the foreign app answered 200 with HTML, so the sensor said green while
# the real dashboard was down and nothing restarted it. The health endpoint has
# carried an identity marker since it was written
# (cabinet/dashboard/src/app/api/health/route.ts -> {ok, service, ts}); the
# sensors simply never read it. A bare-200 probe is the classic wrong-sensor
# bug: it measures "a socket answered", not "MY service answered".
#
# THREE STATES, never two. "down" and "someone else has the port" need
# different answers — one is "start it", the other is "do NOT start here and do
# NOT kill anything, move to a free door and say so".
#
#   mine   the health body carries the cabinet-dashboard identity marker
#   other  something answered on the port and it is not the cabinet
#   down   nothing is listening
#
# PORT IS SINGLE-SOURCE. CABINET_DASHBOARD_PORT in cabinet/.env is the
# deployment's own record of which door it answers on; start-dashboard.sh
# already honors it (explicit env > cabinet/.env > 3100, the D4a precedence).
# Every probe and every opener derives the port from that same value through
# cabinet_dash_port — a hardcoded 3100 in a probe is how a moved dashboard
# becomes invisible to its own tooling.
#
# WRITES: exactly one, cabinet_dash_record_port, and it only ever APPENDS.
# cabinet/.env holds the deployment's secrets; a rewrite is how you lose them.
# A later CABINET_DASHBOARD_PORT= line wins for both readers (`set -a; .` takes
# the last assignment, and the sed reader below takes `tail -1`), so appending
# is a complete change.
#
# Source it: . "$SCRIPT_DIR/lib/dashboard.sh"   (no side effects on source)

# The marker the dashboard's own /api/health prints. Assembled from two pieces
# so a grep for the literal in this tree finds the route and the readers rather
# than this comment. If the route's `service` value ever changes, this is the
# one line that changes with it.
CABINET_DASH_SERVICE="cabinet-dashboard"
CABINET_DASH_MARKER="\"service\":\"${CABINET_DASH_SERVICE}\""

# cabinet_dash_root [dir] — the cabinet checkout root. Explicit arg wins, then
# CABINET_ROOT, then two levels up from this lib.
cabinet_dash_root() {
  if [ "${1:-}" != "" ]; then printf '%s\n' "$1"; return 0; fi
  if [ "${CABINET_ROOT:-}" != "" ]; then printf '%s\n' "$CABINET_ROOT"; return 0; fi
  ( cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd )
}

# cabinet_dash_port [root] — explicit env > <root>/cabinet/.env > 3100.
# Same precedence start-dashboard.sh applies, so a probe and the server it
# probes can never disagree about which door is the door.
cabinet_dash_port() {
  local root port
  root="$(cabinet_dash_root "${1:-}")"
  port="${CABINET_DASHBOARD_PORT:-}"
  if [ -z "$port" ] && [ -f "$root/cabinet/.env" ]; then
    # tr -cd '0-9': the recorded value may carry quotes, a trailing comment or
    # a CR from an editor. Digits are the whole of a port.
    port="$(sed -n 's/^CABINET_DASHBOARD_PORT=//p' "$root/cabinet/.env" | tail -1 | tr -cd '0-9')" || port=""
  fi
  case "$port" in
    ''|*[!0-9]*) port=3100 ;;
  esac
  # Degenerate end: a mangled .env line must never yield a junk URL. Anything
  # outside the TCP range falls back to the default rather than propagating.
  if [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then port=3100; fi
  printf '%s\n' "$port"
}

# cabinet_dash_url [root] — the base URL, trailing slash. Loopback by
# construction: this is what a person on THIS Mac opens.
cabinet_dash_url() {
  printf 'http://127.0.0.1:%s/\n' "$(cabinet_dash_port "${1:-}")"
}

# cabinet_dash_state <base-url> — prints mine | other | down.
# rc mirrors it (0 mine, 1 down, 2 other) so callers may branch either way.
#
# Deliberately NOT `curl -f`: a foreign app that answers 404 or 500 on
# /api/health still HAS the port, and -f would have collapsed that into the
# same silence as nothing-listening. curl's own exit code carries the
# distinction: 7 is "couldn't connect" (nothing there); anything else after a
# successful connect means someone is holding the door.
cabinet_dash_state() {
  local url="$1" body rc
  body="$(curl -sS --max-time 2 "${url}api/health" 2>/dev/null)"; rc=$?
  if [ "$rc" -eq 0 ]; then
    # Whitespace out before matching: the marker is a fact about the JSON, not
    # about how a serializer happened to space it. (Next's Response.json emits
    # no spaces today; a pretty-printer must not be able to blind the probe.)
    body="$(printf '%s' "$body" | tr -d ' \t\n\r')"
    case "$body" in
      *"$CABINET_DASH_MARKER"*) printf 'mine\n'; return 0 ;;
      *) printf 'other\n'; return 2 ;;
    esac
  fi
  # 7 = connection refused / nothing listening. Every other failure happened
  # AFTER something accepted the connection, so the port is occupied.
  if [ "$rc" -eq 7 ]; then printf 'down\n'; return 1; fi
  printf 'other\n'; return 2
}

# cabinet_dash_port_free <port> — rc 0 when nothing is listening.
cabinet_dash_port_free() {
  local state
  state="$(cabinet_dash_state "http://127.0.0.1:$1/")"
  [ "$state" = "down" ]
}

# cabinet_dash_pick_port [first] [last] — first free port in the range, printed.
# Prints nothing and returns 1 when the whole range is taken (the caller then
# says so plainly rather than guessing).
cabinet_dash_pick_port() {
  local first="${1:-3100}" last="${2:-3199}" p
  p="$first"
  while [ "$p" -le "$last" ]; do
    if cabinet_dash_port_free "$p"; then printf '%s\n' "$p"; return 0; fi
    p=$((p + 1))
  done
  return 1
}

# cabinet_dash_record_port <root> <port> [why] — APPEND the port to
# cabinet/.env. Never rewrites, never reorders, never drops a line: the file
# holds this deployment's secrets and every existing byte survives.
cabinet_dash_record_port() {
  local root="$1" port="$2" why="${3:-}" env_file
  env_file="$root/cabinet/.env"
  case "$port" in ''|*[!0-9]*) echo "cabinet_dash_record_port: not a port: $port" >&2; return 2 ;; esac
  ( umask 077
    {
      printf '\n# Written by Captain'"'"'s Cabinet %s.\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      if [ -n "$why" ]; then printf '# %s\n' "$why"; fi
      printf 'CABINET_DASHBOARD_PORT=%s\n' "$port"
    } >> "$env_file" ) || return 1
  chmod 600 "$env_file" 2>/dev/null || true
}
