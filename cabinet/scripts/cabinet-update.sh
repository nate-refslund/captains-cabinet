#!/usr/bin/env bash
# cabinet-update.sh — the installed Cabinet takes a landed improvement, with
# no terminal in the loop.
#
# THE PROBLEM THIS SOLVES. An installed Cabinet is an unpacked export: no git,
# no remote, no way to learn that better bytes exist. Every improvement the org
# made about itself stopped at the repository. This is the last leg — the one
# that makes the result reach the operator.
#
# FOUR SUBCOMMANDS
#   publish --from <clone> [--to <root>]  cut a bundle from a checkout into an
#                                         install's inbox (the landing lane's
#                                         step, run from a clone after a merge)
#   status [--json]                       what is installed, what is waiting
#   apply --bundle <sha> [...]            take it, or refuse and say why
#   rollback [--to <stamp>]               put the previous bytes back
#
# WHAT IT REFUSES, AND WHY EVERY REFUSAL IS WHOLE-BUNDLE
#   * a per-file digest mismatch anywhere in the bundle;
#   * ANY differing path inside the locked constitutional set, parsed from the
#     INSTALLED germline-lock.sh — never from the bundle, because a bundle that
#     named its own boundary could widen it. The installed export carries no
#     filesystem flags, so this refusal IS the boundary there;
#   * an absent, empty or unreadable bundle;
#   * a preserve set that neither side declares;
#   * a second updater already running (the lock).
#   Partial application is never a legal state: the check precedes the first
#   write and the whole bundle stands or falls.
#
# WHAT IT NEVER TOUCHES. Any path in the preserve set (the operator's own
# data); any path the previous bundle did not ship — deletions are
# manifest-to-manifest, never bundle-versus-installed, because a bundle is a
# scrubbed export that contains no instance path at all and diffing it against
# the install would mark the operator's whole instance tree for deletion; the
# service definitions this deployment is supervised by; and secrets — nothing
# here reads cabinet/.env beyond the port the dashboard library already
# resolves.
#
# HOW IT SURVIVES ITSELF. A bundle may change this script, and the process this
# script restarts is the one that spawned it. So before the first write the
# updater copies itself into <root>/.updates/run/ and re-execs there in a NEW
# SESSION. Killing the caller — closing the window, restarting the dashboard —
# no longer kills the update.
#
# THE HEALTH GATE IS NOT AN IDENTITY PROBE. "Something answered as the
# dashboard" passes for an OLD process that survived a failed restart, so the
# gate requires the answering process to carry the NEW source commit AND a
# start time later than this apply began. Plus the receipt ledger still reads,
# plus the state-persistence preflight exits 0. Red ⇒ automatic rollback,
# restart, and a recorded rolled-back event. cabinet-doctor is REPORTED, never
# gated: a single-worker install is DEAD on fleet services it was never meant
# to run, and a doctor gate would roll back every good update.
#
# FOUR TEST SEAMS, every one env-gated and every one carrying TEST in its name
# so a reader never mistakes one for production behaviour — two of them
# (RECEIPTS_CMD, PREFLIGHT_CMD) can turn two of the health gate's three legs
# green, which is not a thing a production knob should be able to do.
# CABINET_UPDATE_TEST_RECEIPTS_CMD and CABINET_UPDATE_TEST_PREFLIGHT_CMD
# replace the gate's two non-dashboard legs with a command a fixture install
# can actually run; the defaults below them are the contract's legs and are
# pinned by their own arm. CABINET_UPDATE_TEST_KILL_AFTER=<n> models the updater
# DYING mid-write — the writer SIGKILLs itself after n files and this process
# follows it, deliberately WITHOUT rolling back, because a machine that lost
# power leaves nobody to roll anything back and only that leaves the resume
# path to prove. CABINET_UPDATE_TEST_HOLD_SECONDS=<n> holds the re-exec'd
# updater before its first write, so "survives the death of the process that
# spawned it" is a deterministic assertion instead of a race.
#
# Exit codes: 0 ok / 1 operational failure (gate red, rolled back) / 2 usage
# / 3 refusal (locked path, digest mismatch, unreadable bundle) / 4 busy.
set -uo pipefail

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
PY="${CABINET_PYTHON:-python3.12}"

EXIT_USAGE=2
EXIT_REFUSED=3
EXIT_BUSY=4

usage() {
  cat <<'EOF'
Usage: cabinet-update.sh <command> [options]

  publish --from <clone> [--to <install-root>]
        Cut an update bundle from a checkout and place it in the install's
        inbox. Run from a clone after a merge; never on the install itself.

  status [--json]
        The installed source commit, the bundles waiting, and the last apply.

  apply --bundle <sha> [--from terminal|web|chat] [--skip-rebuild]
        [--skip-restart] [--keep N]
        Verify, refuse or apply, rebuild, restart, gate, and roll back on red.

  rollback [--to <stamp>] [--from terminal|web|chat] [--skip-restart]
        Restore the newest snapshot (or the named one) and restart.

Root resolution: CABINET_ROOT, else the tree this script lives in.
EOF
}

fail_usage() { echo "cabinet-update: $*" >&2; usage >&2; exit "$EXIT_USAGE"; }

# ---- root -------------------------------------------------------------------
# Both homes of this script — <root>/cabinet/scripts/ and the re-exec'd copy at
# <root>/.updates/run/ — sit exactly two levels under the root.
ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
[ -d "$ROOT" ] || { echo "cabinet-update: root is not a directory: $ROOT" >&2; exit 1; }

UPD="$ROOT/.updates"
INBOX="$UPD/inbox"
APPLIED="$UPD/applied"
SNAPSHOTS="$UPD/snapshots"
STAGE="$UPD/stage"
RUN_DIR="$UPD/run"
STATE="$UPD/state.json"
LOCK="$UPD/.lock"
LOG="$UPD/update.log"

# The helper + the dashboard library, resolved so the re-exec'd copy finds its
# own siblings rather than the tree's.
LIB_DIR="${CABINET_UPDATE_LIB:-$SCRIPT_DIR/lib}"
BUNDLE_PY="$LIB_DIR/update_bundle.py"
DASH_LIB="$LIB_DIR/dashboard.sh"

KEEP="${CABINET_UPDATE_KEEP:-3}"
DOOR="terminal"

# Progress goes to STDERR, always. Stdout belongs to `status`, whose --json a
# machine parses; a progress line on stdout is how a captured verdict becomes
# "gate: leg green\ngreen" and every good update rolls itself back.
log() {
  mkdir -p "$UPD" 2>/dev/null || true
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG" 2>/dev/null || true
  printf '%s\n' "$*" >&2
}

now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# ---- events -----------------------------------------------------------------
# Never silenced: a swallowed emit is an update with no record. A failure to
# record is REPORTED and does not abort the update itself — the bytes are
# already where they are, and pretending otherwise would be the larger lie.
emit_event() {
  local kind="$1" actor="$2" payload="$3"
  if ! ( cd "$ROOT" && "$PY" -m framework.events.emitter "$kind" "$actor" "$payload" ) >>"$LOG" 2>&1; then
    log "WARN: $kind was NOT recorded in the ledger (emitter failed; see $LOG)"
  fi
}

# Door kind -> ledger actor. The terminal is attribution, not authentication:
# it is the same uid as every officer on the box, so it never claims to be the
# Captain. Only the web and chat doors carry an authenticated session.
door_actor() {
  case "$1" in
    web|chat) printf 'captain\n' ;;
    *) printf 'system\n' ;;
  esac
}

# The ledger only ever sees the agnostic kinds; the older spellings are
# accepted so an existing invocation keeps working.
normalize_door() {
  case "${1:-terminal}" in
    cli|terminal) printf 'terminal\n' ;;
    dashboard|web) printf 'web\n' ;;
    chat) printf 'chat\n' ;;
    *) return 1 ;;
  esac
}

json_escape() { "$PY" -c 'import json,sys; sys.stdout.write(json.dumps(sys.argv[1]))' "$1"; }

# ---- the updater lock -------------------------------------------------------
# flock(1) is not on every box this runs on (macOS has none), so the lock is
# taken with the interpreter that IS pinned here. The lock lives on the open
# file description bash holds on fd 9, not on the python process: the child's
# exit closes only its copy of the descriptor, the description stays open in
# this shell, and the lock is held for the life of the update.
# An ALREADY-HELD lock, inherited across the re-exec. The lock is taken in the
# dispatch below, before the self-copy, and rides the open file description
# through `exec` — the descriptor survives, so the process that arrives here
# after the exec is already the holder. Re-asserting on that SAME descriptor
# succeeds and changes nothing. Re-OPENING the file would be the bug: a second
# open is a second description, closing the first one drops the lock, and the
# race the early lock exists to close is handed straight back.
lock_is_inherited() {
  [ "${CABINET_UPDATE_LOCK_HELD:-0}" = "1" ] || return 1
  "$PY" - <<'PYHELD' 9<&9
import fcntl, sys
try:
    fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
except Exception:
    sys.exit(1)
sys.exit(0)
PYHELD
}

take_lock() {
  mkdir -p "$UPD" || return 1
  lock_is_inherited && return 0
  exec 9>>"$LOCK" || return 1
  "$PY" - <<'PYLOCK' 9<&9
import fcntl, sys
try:
    fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    sys.exit(1)
sys.exit(0)
PYLOCK
}

# The door and the bundle, read BEFORE the option parse, because the lock is
# now taken in front of everything and a refusal has to say which door it came
# from. Deliberately forgiving: anything malformed leaves the default here and
# is refused properly by the real parse a moment later.
preparse_door() {
  local prev="" arg normalized
  for arg in "$@"; do
    if [ "$prev" = "--from" ]; then
      normalized="$(normalize_door "$arg")" && { printf '%s\n' "$normalized"; return 0; }
      break
    fi
    prev="$arg"
  done
  printf 'terminal\n'
}

preparse_bundle() {
  local prev="" arg
  for arg in "$@"; do
    if [ "$prev" = "--bundle" ]; then
      case "$arg" in
        ''|*[!0-9a-fA-F]*) : ;;
        *) printf '%s\n' "$arg"; return 0 ;;
      esac
      break
    fi
    prev="$arg"
  done
  printf '\n'
}

# ONE busy refusal for both doors. Rollback used to exit 4 in silence, which
# made the door the Captain reaches for when an update went wrong the only
# refusal on this path that left no row in the ledger — invisible to every
# surface that reads receipts rather than exit codes.
refuse_busy() { # <to_sha>
  echo "cabinet-update: another update is running" >&2
  emit_event cabinet_update_refused "$(door_actor "$DOOR")" \
    "{\"to_sha\":$(json_escape "${1:-}"),\"reason\":\"busy\",\"locked_paths\":[],\"door\":$(json_escape "$DOOR")}"
  exit "$EXIT_BUSY"
}

# ---- re-exec into .updates/run/ under a new session -------------------------
# Copy through a unique name and RENAME into place. `cp` truncates its target
# and rewrites it, and the target here is the file a running updater is
# EXECUTING FROM: bash reads its next command from a byte offset, so a rewrite
# underneath it makes it continue out of the other version's bytes — measured,
# and measured end to end (a successful apply that then reported failure to the
# door that spawned it). rename(2) swaps the directory entry and leaves the
# running process on the inode it already opened. The lock makes this
# unreachable in the first place; this is the half that does not depend on the
# lock being right.
install_run_copy() { # <source> <destination>
  local src="$1" dst="$2" tmp
  tmp="$dst.$$.tmp"
  cp "$src" "$tmp" || { rm -f "$tmp"; return 1; }
  chmod +x "$tmp" 2>/dev/null || true
  mv -f "$tmp" "$dst" || { rm -f "$tmp"; return 1; }
}

reexec_detached() {
  mkdir -p "$RUN_DIR/lib" || return 1
  install_run_copy "$SCRIPT_PATH" "$RUN_DIR/cabinet-update.sh" || return 1
  install_run_copy "$BUNDLE_PY" "$RUN_DIR/lib/update_bundle.py" || return 1
  [ -f "$DASH_LIB" ] && install_run_copy "$DASH_LIB" "$RUN_DIR/lib/dashboard.sh"
  export CABINET_UPDATE_REEXEC=1
  export CABINET_ROOT="$ROOT"
  export CABINET_UPDATE_LIB="$RUN_DIR/lib"
  if command -v setsid >/dev/null 2>&1; then
    exec setsid bash "$RUN_DIR/cabinet-update.sh" "$@"
  fi
  # No setsid(1) on this platform. The interpreter already pinned here has the
  # same call. A process that is already a session leader raises EPERM — which
  # is already the property wanted, so it is not an error.
  exec "$PY" -c '
import os, sys
try:
    os.setsid()
except OSError:
    pass
os.execvp(sys.argv[1], sys.argv[1:])
' bash "$RUN_DIR/cabinet-update.sh" "$@"
}

# ---- state ------------------------------------------------------------------
write_state() { # <json>
  mkdir -p "$UPD"
  printf '%s\n' "$1" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
}

read_state_field() { # <field>
  [ -f "$STATE" ] || { printf '\n'; return 0; }
  "$PY" -c '
import json, sys
try:
    doc = json.load(open(sys.argv[1]))
except Exception:
    doc = {}
value = doc.get(sys.argv[2], "")
print(value if isinstance(value, str) else json.dumps(value))
' "$STATE" "$1"
}

# The installed identity. NOT a .cabinet-version file: the export already
# stamps egg-manifest.json with the commit it was cut from, and a second
# identity file is a second thing that can disagree with the first.
installed_sha_of() { # <root>
  "$PY" -c '
import json, sys
from pathlib import Path
try:
    print(json.loads((Path(sys.argv[1]) / "egg-manifest.json").read_text()).get("source_commit") or "")
except Exception:
    print("")
' "$1"
}
installed_sha() { installed_sha_of "$ROOT"; }

# ---- publish ----------------------------------------------------------------
cmd_publish() {
  local from="" to="$ROOT"
  while [ $# -gt 0 ]; do
    case "$1" in
      --from) [ $# -ge 2 ] || fail_usage "--from needs a checkout"; from="$2"; shift 2 ;;
      --to) [ $# -ge 2 ] || fail_usage "--to needs an install root"; to="$2"; shift 2 ;;
      *) fail_usage "unknown publish option '$1'" ;;
    esac
  done
  [ -n "$from" ] || fail_usage "publish needs --from <clone>"
  [ -e "$from/.git" ] || { echo "cabinet-update: --from is not a checkout (no .git): $from" >&2; exit "$EXIT_REFUSED"; }
  [ -f "$from/cabinet/scripts/egg-export.sh" ] \
    || { echo "cabinet-update: $from carries no egg-export.sh — publish needs the exporter" >&2; exit "$EXIT_REFUSED"; }
  [ -d "$to" ] || { echo "cabinet-update: --to is not a directory: $to" >&2; exit "$EXIT_REFUSED"; }

  local target_inbox installed extra=()
  target_inbox="$to/.updates/inbox"
  mkdir -p "$target_inbox" || exit 1
  installed="$(installed_sha_of "$to")"
  # The changelog is only honest when this checkout actually carries the
  # commit the install is on; otherwise the bundle says so rather than
  # rendering an empty list as "nothing changed".
  if [ -n "$installed" ]; then
    extra=(--changelog-from "$installed")
  fi
  bash "$from/cabinet/scripts/egg-export.sh" --bundle "$target_inbox" "${extra[@]+"${extra[@]}"}" >&2 || exit 1

  # from_sha is the INSTALL's identity at cut time. The exporter cannot know
  # it — it only knows the checkout — so it is stamped here, where both ends
  # are in hand.
  if [ -n "$installed" ]; then
    local head sha_manifest
    head="$(git -C "$from" rev-parse HEAD)"
    sha_manifest="$target_inbox/$head.manifest.json"
    [ -f "$sha_manifest" ] && "$PY" -c '
import json, sys
path, from_sha = sys.argv[1], sys.argv[2]
doc = json.load(open(path))
doc["from_sha"] = from_sha
open(path, "w").write(json.dumps(doc, indent=2, sort_keys=True) + "\n")
' "$sha_manifest" "$installed"
  fi
  log "publish: bundle placed in $target_inbox"
  return 0
}

# ---- status -----------------------------------------------------------------
cmd_status() {
  local as_json=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --json) as_json=1; shift ;;
      *) fail_usage "unknown status option '$1'" ;;
    esac
  done
  "$PY" - "$ROOT" "$as_json" <<'PYSTATUS'
import json, os, pwd, sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
as_json = sys.argv[2] == "1"
upd = root / ".updates"


def installed():
    try:
        return json.loads((root / "egg-manifest.json").read_text()).get("source_commit") or ""
    except Exception:
        return ""


def owner(path):
    try:
        return pwd.getpwuid(path.stat().st_uid).pw_name
    except Exception:
        return ""


here = installed()
available = []
inbox = upd / "inbox"
for manifest_path in sorted(inbox.glob("*.manifest.json")) if inbox.is_dir() else []:
    try:
        doc = json.loads(manifest_path.read_text())
    except Exception:
        continue
    sha = doc.get("source_sha") or ""
    tarball = inbox / f"{sha}.tar.gz"
    if not sha or not tarball.is_file() or sha == here:
        continue
    stat = tarball.stat()
    available.append({
        "sha": sha,
        "short": sha[:8],
        "built_at": doc.get("built_at") or "",
        "from_sha": doc.get("from_sha"),
        "file_count": len(doc.get("files") or {}),
        "changelog": doc.get("changelog") or [],
        # A5.11: the inbox is same-uid writable, so the card says who put the
        # file there and when. That is the honest limit of the trust story
        # until an officer-sandbox deny lands under .updates/.
        "owner": owner(tarball),
        "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc)
                         .strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
available.sort(key=lambda row: row["built_at"], reverse=True)

state = {}
if (upd / "state.json").is_file():
    try:
        state = json.loads((upd / "state.json").read_text())
    except Exception:
        state = {}

snapshots = []
if (upd / "snapshots").is_dir():
    snapshots = sorted(p.name for p in (upd / "snapshots").iterdir() if p.is_dir())

report = {
    "installed_sha": here,
    "installed_short": here[:8],
    "phase": state.get("phase", "idle"),
    "last": state or None,
    "available": available,
    "latest": available[0] if available else None,
    "snapshots": snapshots,
}
if as_json:
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
else:
    print("installed : %s" % (here[:8] or "(unknown)"))
    print("phase     : %s" % report["phase"])
    if not available:
        print("waiting   : nothing (no bundle in the inbox that differs from the install)")
    for row in available:
        print("waiting   : %s  built %s  %d files  owner %s"
              % (row["short"], row["built_at"], row["file_count"], row["owner"]))
        for line in row["changelog"][:5]:
            print("            - %s" % line)
    print("snapshots : %d" % len(snapshots))
PYSTATUS
}

# ---- health gate ------------------------------------------------------------
# Three legs, and the dashboard leg is itself three questions that must not be
# collapsed into one:
#
#   WHICH CABINET answered      `source_commit`, which the dashboard reads from
#                               its own environment at request time. An update
#                               rewrites the identity BEFORE it restarts, so a
#                               process that survived a failed restart still
#                               answers with the old one.
#   WHICH BUILD is serving      `build_commit`, inlined at `next build`. Asked
#                               ONLY when this apply actually rebuilt. A bundle
#                               that changes no dashboard file does not rebuild,
#                               and demanding the new sha from an unchanged
#                               build rolled every framework-only update back —
#                               which is most of them (found in review,
#                               2026-09-07).
#   WHEN it started             `started_at`, from the process's own uptime.
#                               Identity alone passes an old process on a box
#                               where the previous build carried the same
#                               commit (a rebuild, a rollback-then-forward).
#
# rc 0 = green. Nothing is printed to stdout here on purpose: the verdict is
# the exit status.
health_gate() { # <to_sha> <apply_started_at> <skip_restart> <rebuilt>
  local to_sha="$1" started="$2" skip_restart="$3" rebuilt="${4:-0}"
  local tries="${CABINET_OPEN_TRIES:-150}" url state_ok=0

  if [ "$skip_restart" = "1" ]; then
    log "gate: dashboard leg THIN (--skip-restart: nothing was restarted, so a start time cannot be compared)"
  else
    if [ "$rebuilt" = "1" ]; then
      log "gate: build stamp leg armed (this apply rebuilt the dashboard, so the build must be the new one)"
    else
      log "gate: build stamp leg THIN (nothing was rebuilt in this apply, so the running build's stamp is not this update's identity and cannot be asked for it)"
    fi
    url="${CABINET_UPDATE_HEALTH_URL:-}"
    if [ -z "$url" ]; then
      if [ -f "$DASH_LIB" ]; then
        # shellcheck disable=SC1090
        . "$DASH_LIB"
        url="$(cabinet_dash_url "$ROOT")api/health"
      else
        log "gate: dashboard leg RED (no dashboard library at $DASH_LIB, so the door cannot be resolved)"
        return 1
      fi
    fi
    while [ "$tries" -gt 0 ]; do
      if "$PY" - "$url" "$to_sha" "$started" "$rebuilt" <<'PYHEALTH'
import json, sys, urllib.request
from datetime import datetime

url, to_sha, started, rebuilt = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]


def same_commit(answer, expected):
    """Prefix match either way: an export stamps a full sha, a checkout may
    carry a short one, and neither is wrong."""
    return bool(answer) and (answer.startswith(expected) or expected.startswith(answer))


def epoch(value):
    """ISO-8601 -> seconds. NEVER a string comparison: the dashboard answers
    with milliseconds and the updater's own clock reading does not, so
    `...T12:00:00.123Z` sorts BEFORE `...T12:00:00Z` and a restart in the same
    second as the apply began would read as a process that predates it — a
    good update rolled back on a lexicographic accident."""
    value = (value or "").strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


try:
    with urllib.request.urlopen(url, timeout=3) as response:
        body = json.loads(response.read().decode("utf-8"))
except Exception as exc:
    print("health: no answer yet (%s)" % exc, file=sys.stderr)
    sys.exit(1)
if body.get("service") != "cabinet-dashboard":
    print("health: something answered and it is not this cabinet", file=sys.stderr)
    sys.exit(1)
identity = body.get("source_commit") or ""
if not identity:
    print("health: the answer carries no identity", file=sys.stderr)
    sys.exit(1)
if not same_commit(identity, to_sha):
    print("health: the cabinet answering is %s, expected %s"
          % (identity[:12], to_sha[:12]), file=sys.stderr)
    sys.exit(1)
if rebuilt == "1":
    build = body.get("build_commit") or ""
    if not build:
        print("health: the answer carries no build stamp", file=sys.stderr)
        sys.exit(1)
    if not same_commit(build, to_sha):
        print("health: the answering build is %s, expected %s"
              % (build[:12], to_sha[:12]), file=sys.stderr)
        sys.exit(1)
answered_at = epoch(body.get("started_at"))
apply_at = epoch(started)
if answered_at is None:
    print("health: the answer carries no start time", file=sys.stderr)
    sys.exit(1)
if apply_at is not None and int(answered_at) < int(apply_at):
    print("health: the answering process predates this update — the restart did not happen", file=sys.stderr)
    sys.exit(1)
sys.exit(0)
PYHEALTH
      then state_ok=1; break; fi
      tries=$((tries - 1))
      [ "$tries" -gt 0 ] && "$PY" -c 'import time; time.sleep(2)'
    done
    [ "$state_ok" = "1" ] || { log "gate: dashboard leg RED"; return 1; }
    log "gate: dashboard leg green"
  fi

  # The receipt ledger still reads under the new bytes. The contract names this
  # leg `receipts --json`; this tree has no such CLI yet (the read model is
  # framework/events/emitter.replay and the /receipts page over it), so the
  # gate exercises THAT and the seam below is where a CLI plugs in when one
  # lands. Stated rather than quietly skipped.
  # Written as explicit ifs, not `${VAR:-default}`: bash ends a parameter
  # expansion at the FIRST unescaped `}`, so a default containing a brace (a
  # python dict literal, say) leaks its tail into the command as literal text —
  # and does so even when the variable IS set, which is the shape of bug that
  # makes a gate red for a reason nobody can read.
  local receipts_cmd preflight_cmd
  receipts_cmd="${CABINET_UPDATE_TEST_RECEIPTS_CMD:-}"
  if [ -z "$receipts_cmd" ]; then
    receipts_cmd="$PY -c 'import sys; from framework.events.emitter import replay; sys.stdout.write(str(len(replay())))'"
  fi
  preflight_cmd="${CABINET_UPDATE_TEST_PREFLIGHT_CMD:-}"
  if [ -z "$preflight_cmd" ]; then
    preflight_cmd="$PY cabinet/scripts/state-persistence-preflight.py --repo ."
  fi
  if ! ( cd "$ROOT" && eval "$receipts_cmd" ) >>"$LOG" 2>&1; then
    log "gate: receipts leg RED — see $LOG"
    return 1
  fi
  log "gate: receipts leg green"
  if ! ( cd "$ROOT" && eval "$preflight_cmd" ) >>"$LOG" 2>&1; then
    log "gate: persistence preflight RED — see $LOG"
    return 1
  fi
  log "gate: persistence preflight green"

  # REPORTED, never gated.
  if [ -f "$ROOT/cabinet/scripts/cabinet-doctor.sh" ] && [ "${CABINET_UPDATE_SKIP_DOCTOR:-0}" != "1" ]; then
    if ( cd "$ROOT" && bash cabinet/scripts/cabinet-doctor.sh ) >>"$LOG" 2>&1; then
      log "doctor: reported green"
    else
      log "doctor: reported findings (NOT a gate) — see $LOG"
    fi
  fi
  return 0
}

restart_dashboard() {
  [ -f "$DASH_LIB" ] || { log "restart: no dashboard library at $DASH_LIB"; return 1; }
  # shellcheck disable=SC1090
  . "$DASH_LIB"
  # fd 9 CLOSED, in a subshell, before the restart runs. The lock lives on an
  # open file description this process holds on fd 9, and the unsupervised
  # restart path starts a DETACHED dashboard — which inherits every open
  # descriptor and would then hold the updater's lock for as long as it lives.
  # Every later update, from the card the Captain taps, would refuse itself as
  # busy for ever. "One updater at a time" is not "one updater ever".
  #
  # It is a subshell with `exec` and NOT `cabinet_dash_restart ... 9>&-`,
  # because the second one does not work on the bash this ships against (3.2 on
  # macOS): a per-command redirection SAVES the original descriptor by duping
  # it to a high fd, and that duplicate is inherited by the detached child —
  # measured, the child holds the same lock on fd 10. `exec` inside a subshell
  # closes without saving, so there is nothing left to inherit.
  # The env flag goes with the descriptor. It says "the lock you inherited is
  # yours"; a process that no longer has the descriptor must not be told it
  # still holds the lock, or an updater spawned from the restarted dashboard
  # would trust an fd 9 that belongs to something else entirely.
  ( exec 9>&-; unset CABINET_UPDATE_LOCK_HELD
    cabinet_dash_restart "$ROOT" "taking an update" )
}

# ---- restore ----------------------------------------------------------------
restore_snapshot() { # <snapshot-dir>
  local snap="$1" from_sha
  "$PY" "$BUNDLE_PY" restore --root "$ROOT" --snapshot "$snap" >>"$LOG" 2>&1 || return 1
  # The built dashboard is a LOCAL artifact, not shipped content, so it lives
  # beside the snapshot rather than in it. Restoring it before the gate is what
  # makes "gate red ⇒ roll back ⇒ gate green" true instead of hopeful.
  if [ -d "$snap/next-previous" ]; then
    rm -rf "$ROOT/cabinet/dashboard/.next.rollback-tmp"
    [ -d "$ROOT/cabinet/dashboard/.next" ] && mv "$ROOT/cabinet/dashboard/.next" "$ROOT/cabinet/dashboard/.next.rollback-tmp"
    mv "$snap/next-previous" "$ROOT/cabinet/dashboard/.next" || return 1
    rm -rf "$ROOT/cabinet/dashboard/.next.rollback-tmp"
  fi
  from_sha="$("$PY" -c '
import json, sys
try:
    print(json.load(open(sys.argv[1])).get("from_sha") or "")
except Exception:
    print("")
' "$snap/snapshot.json")"
  if [ -n "$from_sha" ]; then
    "$PY" "$BUNDLE_PY" stamp-identity --root "$ROOT" --source-commit "$from_sha" \
      --applied-at "$(now_utc)" >>"$LOG" 2>&1 || true
  fi
  return 0
}

newest_snapshot() {
  [ -d "$SNAPSHOTS" ] || return 1
  ls -1 "$SNAPSHOTS" 2>/dev/null | sort | tail -1
}

cmd_rollback() {
  local want="" skip_restart=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --to) [ $# -ge 2 ] || fail_usage "--to needs a snapshot stamp"; want="$2"; shift 2 ;;
      --from) [ $# -ge 2 ] || fail_usage "--from needs a door"; DOOR="$(normalize_door "$2")" || fail_usage "unknown door '$2'"; shift 2 ;;
      --skip-restart) skip_restart=1; shift ;;
      *) fail_usage "unknown rollback option '$1'" ;;
    esac
  done
  case "$want" in *[!0-9A-Za-z_-]*) fail_usage "snapshot stamps are [0-9A-Za-z_-] only" ;; esac
  # THE RE-EXEC ENTRY POINT'S OWN LOCK. On the normal path the dispatch below
  # has already taken it and `lock_is_inherited` makes this a no-op — but the
  # dispatch skips locking when `CABINET_UPDATE_REEXEC=1`, which is how the
  # re-exec'd copy arrives and what a caller that sets the variable by hand
  # gets. Without this line that entry point would run unlocked, so it stays,
  # and `test_a_re_execed_updater_takes_the_lock_for_itself` is its arm.
  take_lock || refuse_busy ""
  local snap_name before after
  snap_name="${want:-$(newest_snapshot)}"
  { [ -n "$snap_name" ] && [ -d "$SNAPSHOTS/$snap_name" ]; } || {
    echo "cabinet-update: no snapshot to roll back to" >&2; exit 1; }
  before="$(installed_sha)"
  restore_snapshot "$SNAPSHOTS/$snap_name" || { echo "cabinet-update: restore failed — see $LOG" >&2; exit 1; }
  [ "$skip_restart" = "1" ] || restart_dashboard || log "restart after rollback did not complete"
  after="$(installed_sha)"
  write_state "{\"phase\":\"rolled_back\",\"from_sha\":$(json_escape "$before"),\"to_sha\":$(json_escape "$after"),\"snapshot\":$(json_escape "$snap_name"),\"reason\":\"requested\",\"finished_at\":$(json_escape "$(now_utc)"),\"door\":$(json_escape "$DOOR")}"
  emit_event cabinet_update_rolled_back "$(door_actor "$DOOR")" \
    "{\"from_sha\":$(json_escape "$before"),\"to_sha\":$(json_escape "$after"),\"reason\":\"requested\",\"door\":$(json_escape "$DOOR")}"
  log "rolled back to $snap_name"
  return 0
}

# ---- apply ------------------------------------------------------------------
refuse() { # <exit> <reason> <to_sha> [locked-json]
  local code="$1" reason="$2" to_sha="$3" locked="${4:-[]}"
  log "REFUSED: $reason"
  # Several refusals happen AFTER the bundle is unpacked (a digest mismatch, an
  # unreadable plan, a locked path). A5.14: none of them leaves a tree behind.
  drop_stage "$to_sha"
  emit_event cabinet_update_refused "$(door_actor "$DOOR")" \
    "{\"to_sha\":$(json_escape "$to_sha"),\"reason\":$(json_escape "$reason"),\"locked_paths\":$locked,\"door\":$(json_escape "$DOOR")}"
  exit "$code"
}

plan_field() { # <plan-file> <field>
  "$PY" -c '
import json, sys
value = json.load(open(sys.argv[1]))[sys.argv[2]]
print(json.dumps(value) if not isinstance(value, str) else value)
' "$1" "$2"
}

# The build runs in the STAGE tree, never in the install: a failed build must
# not be able to leave the served directory half-written. The previous build is
# moved beside the snapshot (a local artifact the export manifest deletes, not
# shipped content) and the new one is renamed into place LAST.
# rc 0 = built and swapped · 1 = the build failed · 2 = there was nothing to
# build (a bundle that deletes dashboard files ships none). 2 is NOT a build:
# the caller must not then demand the new build stamp at the gate.
stage_build() { # <stage-tree> <snapshot-dir> <to_sha>
  local stage_tree="$1" snap="$2" to_sha="$3"
  local stage_dash="$stage_tree/cabinet/dashboard"
  local live_dash="$ROOT/cabinet/dashboard"
  [ -d "$stage_dash" ] || { log "build: the bundle carries no dashboard"; return 2; }

  # THE BUILD SEAM. A fixture install has no node toolchain, and the property
  # under test in the suite is the gate's reading of the build stamp and the
  # rename-last swap — not npm. Named `CABINET_UPDATE_TEST_` so it can never be
  # mistaken for a production knob; the default below is the behaviour, and
  # test_health_gate_defaults_are_the_contract_legs pins it.
  local build_cmd
  build_cmd="${CABINET_UPDATE_TEST_BUILD_CMD:-}"
  if [ -n "$build_cmd" ]; then
    ( cd "$stage_dash" && CABINET_BUILD_SOURCE_COMMIT="$to_sha" eval "$build_cmd" ) >>"$LOG" 2>&1 || return 1
  else
    command -v npm >/dev/null 2>&1 || { log "build: no node toolchain on this box"; return 1; }
    if [ -d "$live_dash/node_modules" ] && [ -f "$live_dash/package-lock.json" ] \
       && [ -f "$stage_dash/package-lock.json" ] \
       && cmp -s "$live_dash/package-lock.json" "$stage_dash/package-lock.json"; then
      # Same lockfile, same dependencies: reuse what is installed rather than
      # paying a fresh install on every update.
      ln -s "$live_dash/node_modules" "$stage_dash/node_modules"
    else
      ( cd "$stage_dash" && npm ci --include=dev --no-audit --no-fund ) >>"$LOG" 2>&1 || return 1
    fi
    ( cd "$stage_dash" && CABINET_BUILD_SOURCE_COMMIT="$to_sha" npm run build ) >>"$LOG" 2>&1 || return 1
  fi
  [ -d "$stage_dash/.next" ] || { log "build: produced no output"; return 1; }
  mkdir -p "$snap"
  if [ -d "$live_dash/.next" ]; then
    rm -rf "$snap/next-previous"
    mv "$live_dash/.next" "$snap/next-previous" || return 1
  fi
  mv "$stage_dash/.next" "$live_dash/.next" || return 1
  log "build: swapped in a fresh build (the previous one is beside the snapshot)"
  return 0
}

prune_snapshots() {
  [ -d "$SNAPSHOTS" ] || return 0
  local keep="$KEEP" names count old
  case "$keep" in ''|*[!0-9]*) keep=3 ;; esac
  names="$(ls -1 "$SNAPSHOTS" 2>/dev/null | sort)"
  count="$(printf '%s\n' "$names" | grep -c . || true)"
  [ "$count" -gt "$keep" ] || return 0
  printf '%s\n' "$names" | head -n "$((count - keep))" | while IFS= read -r old; do
    [ -n "$old" ] || continue
    rm -rf "${SNAPSHOTS:?}/$old"
    log "pruned snapshot $old"
  done
}

# The staged trees, under the SAME keep policy as the snapshots. A staged tree
# is not a way back — the snapshot is — so this is pure disk hygiene, and it is
# needed because an apply can leave one behind on four different exits: refused,
# rolled back, killed mid-write, or a resume that never reached the green path.
# Newest first (`ls -1t`), because the useful one is always the last one.
prune_stage() {
  [ -d "$STAGE" ] || return 0
  local keep="$KEEP" names count old
  case "$keep" in ''|*[!0-9]*) keep=3 ;; esac
  names="$(ls -1t "$STAGE" 2>/dev/null)"
  count="$(printf '%s\n' "$names" | grep -c . || true)"
  [ "$count" -gt "$keep" ] || return 0
  printf '%s\n' "$names" | tail -n "$((count - keep))" | while IFS= read -r old; do
    [ -n "$old" ] || continue
    rm -rf "${STAGE:?}/$old"
    log "pruned staged tree ${old:0:8}"
  done
}

# Drop the tree this apply unpacked, then bound whatever else is lying around.
drop_stage() { # <sha>
  [ -n "${1:-}" ] && [ -d "$STAGE/$1" ] && rm -rf "${STAGE:?}/$1"
  prune_stage
  return 0
}

roll_back_after() { # <snapshot-dir> <to_sha> <from_sha> <reason> <skip_restart>
  local snap="$1" to_sha="$2" from_sha="$3" reason="$4" skip_restart="$5"
  log "$reason — rolling back automatically"
  restore_snapshot "$snap" || log "the automatic rollback did not complete cleanly — see $LOG"
  [ "$skip_restart" = "1" ] || restart_dashboard || true
  # A5.14: the staged tree does not outlive the apply that unpacked it, on the
  # way out either. Rollback is the exit most likely to be repeated with a
  # different bundle, so leaving one here is one whole unpacked export per
  # distinct failed sha, for ever, on the operator's disk.
  drop_stage "$to_sha"
  write_state "{\"phase\":\"rolled_back\",\"from_sha\":$(json_escape "$to_sha"),\"to_sha\":$(json_escape "$from_sha"),\"snapshot\":$(json_escape "$(basename "$snap")"),\"reason\":$(json_escape "$reason"),\"finished_at\":$(json_escape "$(now_utc)")}"
  emit_event cabinet_update_rolled_back "$(door_actor "$DOOR")" \
    "{\"from_sha\":$(json_escape "$to_sha"),\"to_sha\":$(json_escape "$from_sha"),\"reason\":$(json_escape "$reason"),\"door\":$(json_escape "$DOOR")}"
  exit 1
}

cmd_apply() {
  local sha="" skip_rebuild=0 skip_restart=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --bundle) [ $# -ge 2 ] || fail_usage "--bundle needs a sha"; sha="$2"; shift 2 ;;
      --from) [ $# -ge 2 ] || fail_usage "--from needs a door"; DOOR="$(normalize_door "$2")" || fail_usage "unknown door '$2'"; shift 2 ;;
      --skip-rebuild) skip_rebuild=1; shift ;;
      --skip-restart) skip_restart=1; shift ;;
      --keep) [ $# -ge 2 ] || fail_usage "--keep needs a number"; KEEP="$2"; shift 2 ;;
      *) fail_usage "unknown apply option '$1'" ;;
    esac
  done
  [ -n "$sha" ] || fail_usage "apply needs --bundle <sha>"
  case "$sha" in *[!0-9a-fA-F]*|'') fail_usage "a bundle id is a hex sha" ;; esac

  # Same as cmd_rollback: a no-op behind the dispatch's lock, and the ONLY lock
  # on the `CABINET_UPDATE_REEXEC=1` entry point.
  take_lock || refuse_busy "$sha"

  mkdir -p "$INBOX" "$APPLIED" "$SNAPSHOTS" "$STAGE"

  # RESUME FIRST. A killed apply leaves state.json at `applying` with its
  # snapshot on disk, and the tree is then neither version. Nothing else may
  # run until that is put back.
  if [ "$(read_state_field phase)" = "applying" ]; then
    local stale
    stale="$(read_state_field snapshot)"
    if [ -n "$stale" ] && [ -d "$SNAPSHOTS/$stale" ]; then
      log "resume: a previous apply was interrupted — restoring $stale before anything else"
      restore_snapshot "$SNAPSHOTS/$stale" || { echo "cabinet-update: could not restore the interrupted apply" >&2; exit 1; }
      write_state "{\"phase\":\"rolled_back\",\"snapshot\":$(json_escape "$stale"),\"reason\":\"interrupted apply restored\",\"finished_at\":$(json_escape "$(now_utc)")}"
    else
      log "resume: state says applying but no snapshot was recorded — nothing to restore"
    fi
  fi

  local manifest tarball here
  manifest="$INBOX/$sha.manifest.json"
  tarball="$INBOX/$sha.tar.gz"
  [ -f "$manifest" ] || refuse "$EXIT_REFUSED" "no manifest for bundle $sha in the inbox" "$sha"
  [ -s "$tarball" ] || refuse "$EXIT_REFUSED" "bundle $sha is absent or empty in the inbox" "$sha"

  here="$(installed_sha)"
  if [ -n "$here" ] && [ "$here" = "$sha" ]; then
    log "the installed source commit is already $sha — nothing to do"
    return 0
  fi

  local stage_tree="$STAGE/$sha/tree"
  rm -rf "${STAGE:?}/$sha"
  mkdir -p "$stage_tree"
  tar -xzf "$tarball" -C "$stage_tree" 2>>"$LOG" || refuse "$EXIT_REFUSED" "bundle $sha could not be unpacked" "$sha"

  "$PY" "$BUNDLE_PY" verify --tree "$stage_tree" --manifest "$manifest" >>"$LOG" 2>&1 \
    || refuse "$EXIT_REFUSED" "bundle $sha failed per-file digest verification — see $LOG" "$sha"

  local prev_manifest_arg=()
  if [ -n "$here" ] && [ -f "$APPLIED/$here.manifest.json" ]; then
    prev_manifest_arg=(--previous-manifest "$APPLIED/$here.manifest.json")
  fi

  local plan_file="$STAGE/$sha/plan.json"
  if ! "$PY" "$BUNDLE_PY" plan --root "$ROOT" --tree "$stage_tree" \
        --manifest "$manifest" "${prev_manifest_arg[@]+"${prev_manifest_arg[@]}"}" \
        --out "$plan_file" >/dev/null 2>>"$LOG"; then
    refuse "$EXIT_REFUSED" "the plan could not be computed (the preserve or locked set is unreadable) — see $LOG" "$sha"
  fi

  local locked_hits
  locked_hits="$(plan_field "$plan_file" locked_hits)"
  if [ "$locked_hits" != "[]" ]; then
    {
      echo "----------------------------------------------------------------------"
      echo "This update changes the constitutional set, so none of it was applied."
      echo "Paths:"
      "$PY" -c '
import json, sys
for path in json.load(open(sys.argv[1]))["locked_hits"]:
    print("  " + path)
' "$plan_file"
      echo
      echo "Current boundary state:"
      ( cd "$ROOT" && bash cabinet/scripts/germline-lock.sh status ) 2>&1 | sed 's/^/  /'
      echo
      echo "Changing these bytes is a deliberate ceremony, not an update: unlock"
      echo "the boundary, apply, and lock it again in the same sitting."
      echo "----------------------------------------------------------------------"
    } >&2
    refuse "$EXIT_REFUSED" "bundle $sha changes locked constitutional paths" "$sha" "$locked_hits"
  fi

  local changed_n deleted_n skipped
  changed_n="$("$PY" -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["changed"]))' "$plan_file")"
  deleted_n="$("$PY" -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["deleted"]))' "$plan_file")"
  skipped="$(plan_field "$plan_file" skipped_preserved)"

  if [ "$changed_n" = "0" ] && [ "$deleted_n" = "0" ]; then
    log "bundle $sha changes nothing outside the preserve set — recording it and stopping"
    cp "$manifest" "$APPLIED/$sha.manifest.json"
    drop_stage "$sha"
    "$PY" "$BUNDLE_PY" stamp-identity --root "$ROOT" --source-commit "$sha" \
      --applied-at "$(now_utc)" ${here:+--from-sha "$here"} >>"$LOG" 2>&1
    write_state "{\"phase\":\"applied\",\"from_sha\":$(json_escape "$here"),\"to_sha\":$(json_escape "$sha"),\"changed\":0,\"deleted\":0,\"skipped_preserved\":$skipped,\"finished_at\":$(json_escape "$(now_utc)"),\"door\":$(json_escape "$DOOR")}"
    return 0
  fi

  local started stamp snap
  started="$(now_utc)"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  snap="$SNAPSHOTS/$stamp-${here:-unknown}"
  "$PY" "$BUNDLE_PY" snapshot --root "$ROOT" --plan "$plan_file" --snapshot "$snap" >>"$LOG" 2>&1 \
    || { echo "cabinet-update: the snapshot failed — nothing was written" >&2; exit 1; }

  write_state "{\"phase\":\"applying\",\"from_sha\":$(json_escape "$here"),\"to_sha\":$(json_escape "$sha"),\"snapshot\":$(json_escape "$(basename "$snap")"),\"started_at\":$(json_escape "$started"),\"door\":$(json_escape "$DOOR")}"

  # THE KILL SEAM, and why it does NOT fall through to the rollback below. A
  # failed write and a DEAD UPDATER are different events with different correct
  # answers: a write that returns an error can be rolled back by the process
  # that saw it, while a machine that lost power mid-apply leaves nobody to do
  # anything. Only the second one exercises the resume path, so the seam models
  # the second: the helper kills itself after N files and this process follows
  # it, leaving `state.json` at `applying` with the snapshot on disk for the
  # next apply or rollback to find.
  if [ -n "${CABINET_UPDATE_TEST_KILL_AFTER:-}" ]; then
    "$PY" "$BUNDLE_PY" apply-plan --root "$ROOT" --tree "$stage_tree" --plan "$plan_file" \
      --kill-after "$CABINET_UPDATE_TEST_KILL_AFTER" >>"$LOG" 2>&1
    log "test kill seam: the updater is stopping mid-apply, leaving state=applying"
    kill -9 "$$" 2>/dev/null
    exit 137
  fi
  "$PY" "$BUNDLE_PY" apply-plan --root "$ROOT" --tree "$stage_tree" --plan "$plan_file" \
    >>"$LOG" 2>&1 \
    || roll_back_after "$snap" "$sha" "$here" "the write failed" "$skip_restart"

  "$PY" "$BUNDLE_PY" stamp-identity --root "$ROOT" --source-commit "$sha" \
    --applied-at "$(now_utc)" ${here:+--from-sha "$here"} >>"$LOG" 2>&1

  # THE REBUILD IS CONDITIONAL, AND SO IS THE LEG THAT CHECKS IT. The dashboard
  # is rebuilt only when the bundle changed one of its files — a full `next
  # build` on every framework-only update would cost a minute or two and, on a
  # box with no node toolchain, would fail an update that has nothing to do
  # with the dashboard. `rebuilt` carries that fact to the gate: demanding the
  # new build stamp from a build nobody remade is what rolled every
  # framework-only update back (found in review, 2026-09-07).
  local dashboard_changed=0 rebuilt=0 build_rc=0
  "$PY" -c '
import json, sys
plan = json.load(open(sys.argv[1]))
touched = plan["changed"] + plan["deleted"]
sys.exit(0 if any(p.startswith("cabinet/dashboard/") for p in touched) else 1)
' "$plan_file" && dashboard_changed=1
  if [ "$dashboard_changed" = "1" ] && [ "$skip_rebuild" = "0" ]; then
    stage_build "$stage_tree" "$snap" "$sha"; build_rc=$?
    case "$build_rc" in
      0) rebuilt=1 ;;
      2) log "the plan touched the dashboard but the bundle ships none — nothing to build" ;;
      *) roll_back_after "$snap" "$sha" "$here" "the build failed" "$skip_restart" ;;
    esac
  elif [ "$dashboard_changed" = "1" ]; then
    log "rebuild SKIPPED by request — the running build is now older than the code it serves (THIN)"
  fi

  [ "$skip_restart" = "1" ] || restart_dashboard || log "the restart did not complete — the gate will say so"

  health_gate "$sha" "$started" "$skip_restart" "$rebuilt" \
    || roll_back_after "$snap" "$sha" "$here" "the health gate was red" "$skip_restart"

  # Pruning only after a green gate: an older snapshot is the only way back if
  # the next apply is the one that goes wrong.
  cp "$manifest" "$APPLIED/$sha.manifest.json"
  prune_snapshots
  # The staged tree has done its work. The way back is the snapshot, never
  # this: left behind, it is one whole unpacked export per apply, for ever, on
  # a disk that belongs to the operator.
  drop_stage "$sha"
  local built_at owner mtime
  built_at="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("built_at") or "")' "$manifest")"
  owner="$("$PY" -c '
import os, pwd, sys
try:
    print(pwd.getpwuid(os.stat(sys.argv[1]).st_uid).pw_name)
except Exception:
    print("")
' "$tarball")"
  mtime="$("$PY" -c '
import os, sys
from datetime import datetime, timezone
print(datetime.fromtimestamp(os.stat(sys.argv[1]).st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
' "$tarball")"
  write_state "{\"phase\":\"applied\",\"from_sha\":$(json_escape "$here"),\"to_sha\":$(json_escape "$sha"),\"snapshot\":$(json_escape "$(basename "$snap")"),\"started_at\":$(json_escape "$started"),\"finished_at\":$(json_escape "$(now_utc)"),\"changed\":$changed_n,\"deleted\":$deleted_n,\"skipped_preserved\":$skipped,\"built_at\":$(json_escape "$built_at"),\"door\":$(json_escape "$DOOR")}"
  emit_event cabinet_update_applied "$(door_actor "$DOOR")" \
    "{\"from_sha\":$(json_escape "$here"),\"to_sha\":$(json_escape "$sha"),\"changed\":$changed_n,\"deleted\":$deleted_n,\"snapshot\":$(json_escape "$(basename "$snap")"),\"door\":$(json_escape "$DOOR"),\"built_at\":$(json_escape "$built_at"),\"inbox_owner\":$(json_escape "$owner"),\"inbox_mtime\":$(json_escape "$mtime"),\"skipped_preserved\":$skipped}"
  log "applied ${here:0:8} -> ${sha:0:8}: $changed_n changed, $deleted_n deleted"
  if [ "$skipped" != "[]" ]; then
    log "kept your own data instead of the shipped copy: $skipped"
  fi
  return 0
}

# ---- dispatch ---------------------------------------------------------------
CMD="${1:-}"
[ -n "$CMD" ] || { usage; exit "$EXIT_USAGE"; }
shift

case "$CMD" in
  publish) cmd_publish "$@" ;;
  status)  cmd_status "$@" ;;
  apply|rollback)
    [ -f "$BUNDLE_PY" ] || { echo "cabinet-update: the helper is missing: $BUNDLE_PY" >&2; exit 1; }
    if [ "${CABINET_UPDATE_REEXEC:-0}" != "1" ]; then
      # THE LOCK COMES FIRST — ahead of the self-copy, not after it. The copy
      # writes the very file a first updater is executing from, so a second
      # caller that copied before locking corrupted a run that was already
      # under way. The lock rides the open file description through the exec
      # below, so the process on the other side is still the holder.
      DOOR="$(preparse_door "$@")"
      take_lock || refuse_busy "$(preparse_bundle "$@")"
      export CABINET_UPDATE_LOCK_HELD=1
      reexec_detached "$CMD" "$@"
    fi
    if [ -n "${CABINET_UPDATE_TEST_HOLD_SECONDS:-}" ]; then
      "$PY" -c 'import sys, time; time.sleep(float(sys.argv[1]))' "$CABINET_UPDATE_TEST_HOLD_SECONDS"
    fi
    if [ "$CMD" = "apply" ]; then cmd_apply "$@"; else cmd_rollback "$@"; fi
    ;;
  -h|--help|help) usage ;;
  *) fail_usage "unknown command '$CMD'" ;;
esac
