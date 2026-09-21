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
# WRITES: three, all of them named. `cabinet_dash_record_port` only ever
# APPENDS to cabinet/.env — that file holds the deployment's secrets and a
# rewrite is how you lose them; a later CABINET_DASHBOARD_PORT= line wins for
# both readers (`set -a; .` takes the last assignment, and the sed reader below
# takes `tail -1`), so appending is a complete change. `cabinet_launchd_install`
# writes ONE plist into the user's LaunchAgents directory, which is the whole
# point of it. `cabinet_dash_record_door` writes the door verdict to the path
# the caller names in CABINET_DASH_DOOR_RECORD, and to nothing when that is
# unset. Everything else here reads.
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

# The launchd label the dashboard runs under when it runs supervised. Named
# once, here, beside the port and the identity marker — the three facts every
# probe and every restarter needs about the same process.
CABINET_DASH_LABEL="${CABINET_DASH_LABEL:-com.cabinet.dashboard}"

# cabinet_launchd_install <plist> [label] — put a launchd job where it SURVIVES
# A RESTART, then load THAT copy.
#
# WHY THIS EXISTS, and it is a measured three-week outage rather than a tidiness
# argument. hatch's move-in used to walk `cabinet/launchd/generated/*.plist` and
# bootstrap each file WHERE IT LAY. launchd re-reads agents at login from the
# user's own LaunchAgents directory and from nowhere else, so a job bootstrapped
# out of the checkout exists only until the next restart. On the Captain's Mac
# one restart (~2026-08-29) cleared all fifty scheduled jobs; the fleet was dark
# until 2026-09-15 and nothing on the box said so. `deploy-mac.sh` has always
# done it the durable way (render -> write LaunchAgents -> bootstrap the
# installed copy); this is that same order, in the one function every other
# caller can reach.
#
# It lives in THIS lib, next to CABINET_DASH_LABEL, deliberately: the label is
# already a launchd fact stated here, hatch and the updater both source this
# file already, and a separate library would be one more thing the updater's
# run-copy, the fixtures and the drill each have to remember to carry — the
# silent-degradation shape this tree has paid for more than once.
#
# rc 0 = the job is loaded from its installed copy. 2 = there was nothing to
# install, or it is not a plist. 1 = it could not be written. 3 = it was
# installed and launchd would not take it. In every non-zero case the reason is
# left in CABINET_LAUNCHD_INSTALL_ERROR, because the caller's job is to SAY why,
# not to guess.
cabinet_launchd_install() {
  local src label dir dest staged lc uid out
  src="${1:-}"
  lc="${CABINET_LAUNCHCTL:-launchctl}"
  CABINET_LAUNCHD_INSTALL_ERROR=""
  if [ -z "$src" ] || [ ! -f "$src" ]; then
    CABINET_LAUNCHD_INSTALL_ERROR="no plist at ${src:-(nothing named)}"
    return 2
  fi
  label="${2:-}"
  [ -n "$label" ] || label="$(basename "$src" .plist)"
  if command -v plutil >/dev/null 2>&1 && ! plutil -lint "$src" >/dev/null 2>&1; then
    CABINET_LAUNCHD_INSTALL_ERROR="$src is not a readable plist"
    return 2
  fi
  dir="$HOME/Library/LaunchAgents"
  dest="$dir/$label.plist"
  mkdir -p "$dir" 2>/dev/null || {
    CABINET_LAUNCHD_INSTALL_ERROR="$dir could not be created"
    return 1
  }
  # Stage and rename: the target may be the file launchd is reading, and a
  # truncating copy is a window in which the job has no definition at all.
  staged="$dest.tmp.$$"
  cp "$src" "$staged" 2>/dev/null || { rm -f "$staged" 2>/dev/null; CABINET_LAUNCHD_INSTALL_ERROR="could not write $dest"; return 1; }
  chmod 644 "$staged" 2>/dev/null || true
  mv -f "$staged" "$dest" 2>/dev/null || { rm -f "$staged" 2>/dev/null; CABINET_LAUNCHD_INSTALL_ERROR="could not replace $dest"; return 1; }
  uid="$(id -u)"
  # Bootout first, unconditionally: launchd answers an already-loaded label
  # with its catch-all "Bootstrap failed: 5: Input/output error", and a `print`
  # probe does not always agree that it is loaded (deploy-mac.sh pays for the
  # same lesson on the officer leg). Bootout errors harmlessly when it is not.
  "$lc" bootout "gui/$uid" "$dest" >/dev/null 2>&1 || true
  if out="$("$lc" bootstrap "gui/$uid" "$dest" 2>&1)"; then
    return 0
  fi
  CABINET_LAUNCHD_INSTALL_ERROR="$(printf '%s' "$out" | tr '\n' ' ' | sed 's/  */ /g')"
  [ -n "$CABINET_LAUNCHD_INSTALL_ERROR" ] || CABINET_LAUNCHD_INSTALL_ERROR="launchd would not take $label"
  return 3
}

# cabinet_launchd_state [label] — running | loaded | not-loaded | unknown.
#
# READ-ONLY, and `unknown` is a real answer: a box with no launchctl (every
# Linux CI runner this tree also runs on) cannot be asked, and answering
# "not-loaded" there would be a confident wrong negative — the exact shape of
# the bare-200 probe this library was written to replace.
cabinet_launchd_state() {
  local label lc out
  label="${1:-$CABINET_DASH_LABEL}"
  lc="${CABINET_LAUNCHCTL:-launchctl}"
  command -v "$lc" >/dev/null 2>&1 || { printf 'unknown\n'; return 0; }
  if out="$("$lc" print "gui/$(id -u)/$label" 2>/dev/null)"; then
    case "$out" in
      *"state = running"*) printf 'running\n' ;;
      *) printf 'loaded\n' ;;
    esac
    return 0
  fi
  printf 'not-loaded\n'
}

# cabinet_dash_record_door <supervised:0|1> <reason> — leave the door verdict
# where the CALLER asked for it, and nowhere else.
#
# The path comes from CABINET_DASH_DOOR_RECORD because the restart happens in a
# subshell (the updater closes its lock descriptor before restarting), so a
# variable cannot carry the answer back out. Unset means "nobody asked": this
# function then writes nothing at all rather than inventing a file under a root
# that may have no `.updates` directory. Two plain lines, not JSON — the reason
# is launchd's own text and a hand-rolled JSON escape is a bug waiting for the
# first quote in it.
cabinet_dash_record_door() {
  local path="${CABINET_DASH_DOOR_RECORD:-}" reason
  [ -n "$path" ] || return 0
  reason="$(printf '%s' "${2:-}" | tr '\n' ' ')"
  mkdir -p "$(dirname "$path")" 2>/dev/null || return 0
  { printf 'supervised=%s\n' "${1:-0}"
    printf 'reason=%s\n' "$reason"
  } > "$path" 2>/dev/null || return 0
}

# cabinet_dash_restart <root> [why] — put a NEW dashboard process on the port.
#
# WHY THIS IS A FUNCTION AND NOT THREE LINES AT THE CALL SITE. There are two
# ways this deployment runs its dashboard and they need opposite handling:
# supervised by launchd (restart the JOB — killing the process alone just makes
# KeepAlive start the OLD build again from the OLD working directory), or
# started on demand from the app (nothing supervises it, so the caller must
# kill the listener itself and start a detached replacement). Getting that
# backwards produces the worst outcome available: something answers on the
# port, so every identity probe says "up", while the bytes serving are the ones
# the caller just tried to replace.
#
# rc 0 = a restart was ORDERED, not that the new process is healthy. Liveness
# is the caller's own gate — this function deliberately makes no claim about
# what came back, because a restarter that also declares success is how a
# failed restart gets reported as a good one.
cabinet_dash_restart() {
  local root why port
  root="$(cabinet_dash_root "${1:-}")"
  why="${2:-a restart was requested}"
  port="$(cabinet_dash_port "$root")"

  local lc
  lc="${CABINET_LAUNCHCTL:-launchctl}"
  if command -v "$lc" >/dev/null 2>&1 \
     && "$lc" print "gui/$(id -u)/$CABINET_DASH_LABEL" >/dev/null 2>&1; then
    # Loaded: kickstart -k is the supervised restart. A kill here would be
    # undone by KeepAlive with the pre-update process arguments.
    if "$lc" kickstart -k "gui/$(id -u)/$CABINET_DASH_LABEL" >/dev/null 2>&1; then
      printf 'cabinet_dash_restart: restarted the supervised dashboard (%s)\n' "$why" >&2
      cabinet_dash_record_door 1 ""
      return 0
    fi
    printf 'cabinet_dash_restart: the supervised job would not restart\n' >&2
    cabinet_dash_record_door 1 "the supervised job would not restart"
    return 1
  fi

  # Unsupervised. Only ever kill a listener this deployment OWNS: the identity
  # probe is what separates "my dashboard" from the unrelated dev server that
  # once held this port on the Captain's Mac and was read as the cabinet by
  # every bare-200 probe in the tree.
  local state pids
  state="$(cabinet_dash_state "$(cabinet_dash_url "$root")")"
  if [ "$state" = "other" ]; then
    printf 'cabinet_dash_restart: port %s is held by something that is not this cabinet — not killing it\n' "$port" >&2
    cabinet_dash_record_door 0 "port $port is held by something that is not this cabinet"
    return 1
  fi
  if [ "$state" = "mine" ]; then
    pids="$(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$pids" ]; then
      # shellcheck disable=SC2086
      kill $pids 2>/dev/null || true
      "${CABINET_PYTHON:-python3.12}" -c 'import time; time.sleep(2)' 2>/dev/null || true
      pids="$(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null || true)"
      # shellcheck disable=SC2086
      [ -z "$pids" ] || kill -9 $pids 2>/dev/null || true
    fi
  fi
  # PUT IT BACK UNDER SUPERVISION IF THIS BOX WILL LET US, and only then fall
  # back. An unsupervised dashboard is an orphan: it dies with the terminal
  # that spawned it and it does not come back after a restart. Measured — the
  # dashboard the 2026-09-10 apply started on the Captain's Mac was dead by
  # 2026-09-21, and the web door, which is his ONLY no-terminal door, had been
  # gone for days with nothing saying so.
  #
  # After the kill above, never before it: the new job has to bind the port,
  # and an orphan still holding it would make the supervised start fail while
  # the old bytes kept answering — the worst outcome this function has.
  local plist door_reason=""
  plist="$root/cabinet/launchd/generated/$CABINET_DASH_LABEL.plist"
  if [ -f "$plist" ]; then
    if cabinet_launchd_install "$plist" "$CABINET_DASH_LABEL"; then
      printf 'cabinet_dash_restart: the door is SUPERVISED again on %s (%s)\n' "$port" "$why" >&2
      cabinet_dash_record_door 1 ""
      return 0
    fi
    door_reason="${CABINET_LAUNCHD_INSTALL_ERROR:-launchd would not take the job}"
  else
    door_reason="no $CABINET_DASH_LABEL.plist under cabinet/launchd/generated/ — the schedule has not been rendered on this box"
  fi
  # A non-GUI launchd manager answers a bootstrap with an I/O error; that is
  # the officer's measured case and it is not recoverable from here. A door
  # nobody supervises beats no door at all, so the detached start still
  # happens — it is being UNSUPERVISED SILENTLY that cost three weeks.
  printf 'cabinet_dash_restart: door is UNSUPERVISED (bootstrap into gui/%s failed: %s)\n' \
    "$(id -u)" "$door_reason" >&2
  cabinet_dash_record_door 0 "$door_reason"

  [ -x "$root/cabinet/scripts/start-dashboard.sh" ] || [ -f "$root/cabinet/scripts/start-dashboard.sh" ] || {
    printf 'cabinet_dash_restart: no start-dashboard.sh under %s\n' "$root" >&2
    return 1
  }
  mkdir -p "$root/cabinet/logs" 2>/dev/null || true
  ( cd "$root" && CABINET_ROOT="$root" nohup bash cabinet/scripts/start-dashboard.sh \
      >>"$root/cabinet/logs/dashboard-restart.log" 2>&1 </dev/null & ) || return 1
  printf 'cabinet_dash_restart: started an unsupervised dashboard on %s (%s)\n' "$port" "$why" >&2
  return 0
}

# cabinet_dash_link_modules <src-node_modules> <dst-node_modules> — materialise
# an installed dependency tree at <dst> as a HARDLINK TREE of <src>.
#
# WHY THIS IS NOT A SYMLINK, which is what it was until 2026-09-10. The staged
# rebuild builds the dashboard in a tree under `<root>/.updates/stage/`, and
# reusing the install's dependencies is the difference between a two-minute
# update and a five-minute one. The obvious way to reuse them is
# `ln -s <install>/node_modules <stage>/node_modules`, and it was the way until
# the FIRST real apply on the Captain's installed Cabinet, where the build died
# on its own dependency directory:
#
#     Symlink [project]/node_modules is invalid, it points out of the
#     filesystem root
#
# The bundler treats the project directory as the root of the world and refuses
# a link that leaves it. That is a reasonable thing for a bundler to do, and
# nothing about it is specific to this one: a staged build whose dependencies
# live OUTSIDE the staged project is asking every tool that walks the tree to
# follow a rope over the wall. So the dependencies come INSIDE the stage —
# without paying for a copy — as hardlinks. Same inodes, same bytes, no second
# gigabyte on the operator's disk, and every path inside the project.
#
# THE REMOVAL PROPERTY, which is the whole reason hardlinks and not a copy is
# safe: dropping the stage unlinks the stage's NAMES. The install's names still
# hold the same inodes, so the live dependency tree is untouched by a staged
# build that failed, was rolled back, or was pruned.
#
# THREE MECHANISMS, in order, because this ships to boxes this org does not
# own: `pax -rwl` (POSIX, present on macOS and on every Linux this targets),
# `rsync -a --link-dest` (present nearly everywhere else), and a real `cp -R`
# copy as the last resort — which is LOUD, because it costs the disk what the
# hardlinks were there to save.
#
# Internal symlinks (`node_modules/.bin/*` is a directory of them) are copied
# as symlinks by all three: they are relative and point INSIDE the tree, so
# they resolve in the stage exactly as they resolve in the install.
#
# rc 0 = the tree is there. 2 = there was no source to link from (the caller
# decides whether that is fatal). 1 = it could not be made.
cabinet_dash_link_modules() {
  local src="$1" dst="$2" src_dev dst_dev py
  py="${CABINET_PYTHON:-python3.12}"
  [ -d "$src" ] || {
    printf 'cabinet_dash_link_modules: no dependency tree at %s\n' "$src" >&2
    return 2
  }
  rm -rf "$dst" || return 1
  mkdir -p "$dst" || return 1

  # SAME FILESYSTEM OR HARDLINKS ARE IMPOSSIBLE. It is the same one by
  # construction — the stage lives under the install — so this is not a
  # decision, it is a line in the log for the day that stops being true (a
  # bind-mounted stage, a separate volume for `.updates`). Asked through
  # python's own stat rather than stat(1): GNU `stat -f` SUCCEEDS printing a
  # mount point where BSD `stat -f` takes a format string, so a shell probe
  # written either way is wrong on the other box.
  if command -v "$py" >/dev/null 2>&1; then
    src_dev="$("$py" -c 'import os,sys; print(os.stat(sys.argv[1]).st_dev)' "$src" 2>/dev/null || true)"
    dst_dev="$("$py" -c 'import os,sys; print(os.stat(sys.argv[1]).st_dev)' "$dst" 2>/dev/null || true)"
    if [ -n "$src_dev" ] && [ -n "$dst_dev" ] && [ "$src_dev" != "$dst_dev" ]; then
      printf 'cabinet_dash_link_modules: %s and %s are on DIFFERENT filesystems — hardlinks are impossible and this will fall through to a copy\n' \
        "$src" "$dst" >&2
    fi
  fi

  if command -v pax >/dev/null 2>&1 \
     && ( cd "$src" && pax -rwl . "$dst" ) >/dev/null 2>&1 \
     && [ -n "$(ls -A "$dst" 2>/dev/null)" ]; then
    printf 'cabinet_dash_link_modules: hardlinked the dependency tree into %s (pax)\n' "$dst" >&2
    return 0
  fi
  if command -v rsync >/dev/null 2>&1 \
     && rsync -a --link-dest="$src/" "$src/" "$dst/" >/dev/null 2>&1 \
     && [ -n "$(ls -A "$dst" 2>/dev/null)" ]; then
    printf 'cabinet_dash_link_modules: hardlinked the dependency tree into %s (rsync)\n' "$dst" >&2
    return 0
  fi
  printf 'cabinet_dash_link_modules: NEITHER pax NOR rsync could hardlink %s — COPYING it instead, which costs this box a second copy of the whole dependency tree\n' \
    "$src" >&2
  rm -rf "$dst" || return 1
  mkdir -p "$dst" || return 1
  cp -R "$src/." "$dst/" || return 1
  [ -n "$(ls -A "$dst" 2>/dev/null)" ] || return 1
  return 0
}
