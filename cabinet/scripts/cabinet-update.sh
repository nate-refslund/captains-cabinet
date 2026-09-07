#!/usr/bin/env bash
# cabinet-update.sh — the installed Cabinet takes a landed improvement, with
# no terminal in the loop.
#
# THE PROBLEM THIS SOLVES. An installed Cabinet is an unpacked export: no git,
# no remote, no way to learn that better bytes exist. Every improvement the
# org made about itself stopped at the repository. This is the last leg — the
# one that makes the result reach the operator.
#
# FOUR SUBCOMMANDS
#   publish --from <clone> [--to <root>]  cut a bundle from a clone into an
#                                         install's inbox (the landing lane's
#                                         step, run from a clone after a merge)
#   status [--json]                       what is installed, what is waiting
#   apply --bundle <sha> [...]            take it, or refuse and say why
#   rollback [--to <stamp>]               put the previous bytes back
#
# WHAT IT REFUSES, AND WHY EACH REFUSAL IS WHOLE-BUNDLE
#   * a digest mismatch anywhere in the bundle;
#   * ANY differing path inside the locked constitutional set, parsed from the
#     INSTALLED germline-lock.sh (never from the bundle — a bundle that named
#     its own boundary could widen it). The installed export is not itself
#     flag-locked, so this refusal IS the boundary there;
#   * an absent, empty or unreadable bundle;
#   * a preserve set that neither side declares.
#   Partial application is never a legal state: the check precedes the first
#   write and the whole bundle stands or falls.
#
# WHAT IT NEVER TOUCHES: any path in the preserve set (the operator's own
# data), any path the previous bundle did not ship (deletions are
# manifest-to-manifest), launchd definitions, and secrets — nothing here reads
# cabinet/.env beyond the port the dashboard library already resolves.
#
# HOW IT SURVIVES ITSELF. A bundle may change this script and the process this
# script restarts is the one that spawned it, so before the first write the
# updater copies itself into <root>/.updates/run/ and re-execs there in a NEW
# SESSION. Killing the caller — closing the window, restarting the dashboard —
# no longer kills the update.
#
# THE HEALTH GATE IS NOT AN IDENTITY PROBE. "Something answered as the
# dashboard" passes for an OLD process that survived a failed restart, so the
# gate requires the answering process to carry the NEW source commit and a
# start time later than this apply. Plus the receipts read model exits 0, plus
# the state-persistence preflight exits 0. Red ⇒ automatic rollback, restart,
# and a recorded rolled-back event. cabinet-doctor is REPORTED, never gated: a
# single-worker install DEADs on services it was never meant to run, and a
# doctor gate would roll back every good update.
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

  publish --from <clone> [--to <install-root>] [--keep N]
        Cut an update bundle from a checkout and place it in the install's
        inbox. Run from a clone after a merge; never on the install itself.

  status [--json]
        The installed source commit, the bundles waiting, and the last apply.

  apply --bundle <sha> [--from terminal|web|chat] [--skip-rebuild]
        [--skip-restart] [--keep N]
        Verify, refuse or apply, rebuild, restart, gate, and roll back on red.

  rollback [--to <stamp>] [--from terminal|web|chat] [--skip-restart]
        Restore the newest snapshot (or the named one) and restart.

Root resolution: CABINET_ROOT, else the checkout this script lives in.
EOF
}

fail_usage() { echo "cabinet-update: $*" >&2; usage >&2; exit "$EXIT_USAGE"; }

# ---- root -------------------------------------------------------------------
resolve_root() {
  if [ -n "${CABINET_ROOT:-}" ]; then printf '%s\n' "$CABINET_ROOT"; return 0; fi
  # The re-exec'd copy lives at <root>/.updates/run/, not at <root>/cabinet/scripts/.
  case "$SCRIPT_DIR" in
    */.updates/run) (cd "$SCRIPT_DIR/../.." && pwd) ;;
    *) (cd "$SCRIPT_DIR/../.." && pwd) ;;
  esac
}
ROOT="$(resolve_root)"
[ -d "$ROOT" ] || { echo "cabinet-update: root not a directory: $ROOT" >&2; exit 1; }

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
# own siblings rather than the checkout's.
LIB_DIR="${CABINET_UPDATE_LIB:-$SCRIPT_DIR/lib}"
BUNDLE_PY="$LIB_DIR/update_bundle.py"
DASH_LIB="$LIB_DIR/dashboard.sh"

KEEP="${CABINET_UPDATE_KEEP:-3}"

log() {
  mkdir -p "$UPD" 2>/dev/null || true
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG" 2>/dev/null || true
  printf '%s\n' "$*"
}

now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# ---- events -----------------------------------------------------------------
# Never silenced: a swallowed emit is an update with no record. Failure to
# record is reported and does not abort the update itself.
emit_event() {
  local kind="$1" actor="$2" payload="$3"
  if ! ( cd "$ROOT" && "$PY" -m framework.events.emitter "$kind" "$actor" "$payload" ) >>"$LOG" 2>&1; then
    log "WARN: $kind was NOT recorded in the ledger (emitter failed; see $LOG)"
  fi
}

# door kind -> ledger actor. The terminal is attribution, not authentication:
# it is the same uid as everything else on the box, so it never claims to be
# the Captain. The web and chat doors carry an authenticated session.
door_actor() {
  case "$1" in
    web|chat) printf 'captain\n' ;;
    *) printf 'system\n' ;;
  esac
}

# Legacy spellings accepted so an older invocation keeps working; the ledger
# only ever sees the agnostic kinds.
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
# flock(1) is not on every box this runs on (it is absent on macOS), so the
# lock is taken with the interpreter that IS pinned here. The lock lives on the
# open file description bash holds on fd 9, not on the python process: the
# child's exit closes its copy of the descriptor, the description stays open in
# this shell, and the lock stays held for the life of the update.
take_lock() {
  mkdir -p "$UPD" || return 1
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

# ---- re-exec into .updates/run/ under a new session -------------------------
reexec_detached() {
  mkdir -p "$RUN_DIR/lib" || return 1
  cp "$SCRIPT_PATH" "$RUN_DIR/cabinet-update.sh" || return 1
  cp "$BUNDLE_PY" "$RUN_DIR/lib/update_bundle.py" || return 1
  [ -f "$DASH_LIB" ] && cp "$DASH_LIB" "$RUN_DIR/lib/dashboard.sh"
  chmod +x "$RUN_DIR/cabinet-update.sh" 2>/dev/null || true
  export CABINET_UPDATE_REEXEC=1
  export CABINET_ROOT="$ROOT"
  export CABINET_UPDATE_LIB="$RUN_DIR/lib"
  if command -v setsid >/dev/null 2>&1; then
    exec setsid bash "$RUN_DIR/cabinet-update.sh" "$@"
  fi
  # No setsid on this platform: the interpreter already pinned here has the
  # same call. A process that is already a session leader raises EPERM; that
  # is already the property we want, so it is not an error.
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

installed_sha() {
  "$PY" -c '
import json, sys
from pathlib import Path
path = Path(sys.argv[1]) / "egg-manifest.json"
try:
    print(json.loads(path.read_text()).get("source_commit") or "")
except Exception:
    print("")
' "$ROOT"
}

# ---- publish ----------------------------------------------------------------
cmd_publish() {
  local from="" to="$ROOT"
  while [ $# -gt 0 ]; do
    case "$1" in
      --from) [ $# -ge 2 ] || fail_usage "--from needs a checkout"; from="$2"; shift 2 ;;
      --to) [ $# -ge 2 ] || fail_usage "--to needs an install root"; to="$2"; shift 2 ;;
      --keep) [ $# -ge 2 ] || fail_usage "--keep needs a number"; KEEP="$2"; shift 2 ;;
      *) fail_usage "unknown publish option '$1'" ;;
    esac
  done
  [ -n "$from" ] || fail_usage "publish needs --from <clone>"
  [ -d "$from/.git" ] || { echo "cabinet-update: --from is not a checkout (no .git): $from" >&2; exit "$EXIT_REFUSED"; }
  [ -x "$from/cabinet/scripts/egg-export.sh" ] || [ -f "$from/cabinet/scripts/egg-export.sh" ] \
    || { echo "cabinet-update: $from carries no egg-export.sh — publish needs the exporter" >&2; exit "$EXIT_REFUSED"; }

  local target_inbox installed
  target_inbox="$to/.updates/inbox"
  mkdir -p "$target_inbox" || exit 1
  installed="$( CABINET_ROOT="$to" "$PY" -c '
import json, sys
from pathlib import Path
path = Path(sys.argv[1]) / "egg-manifest.json"
try:
    print(json.loads(path.read_text()).get("source_commit") or "")
except Exception:
    print("")
' "$to" )"

  local extra=()
  if [ -n "$installed" ] && git -C "$from" cat-file -e "${installed}^{commit}" 2>/dev/null; then
    extra=(--changelog-from "$installed")
  fi
  bash "$from/cabinet/scripts/egg-export.sh" --bundle "$target_inbox" "${extra[@]+"${extra[@]}"}" || exit 1

  # from_sha is the install's identity at cut time — the exporter cannot know
  # it, so it is stamped here, where both ends are in hand.
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
for manifest_path in sorted((upd / "inbox").glob("*.manifest.json")) if (upd / "inbox").is_dir() else []:
    try:
        doc = json.loads(manifest_path.read_text())
    except Exception:
        continue
    sha = doc.get("source_sha") or ""
    tarball = upd / "inbox" / f"{sha}.tar.gz"
    if not sha or not tarball.is_file():
        continue
    if sha == here:
        continue
    stat = tarball.stat()
    available.append({
        "sha": sha,
        "short": sha[:8],
        "built_at": doc.get("built_at") or "",
        "from_sha": doc.get("from_sha"),
        "file_count": len(doc.get("files") or {}),
        "changelog": doc.get("changelog") or [],
        "owner": owner(tarball),
        "mtime": stat.st_mtime,
        "path": str(tarball),
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
    print(f"installed : {here[:8] or '(unknown)'}")
    print(f"phase     : {report['phase']}")
    if not available:
        print("waiting   : nothing (no bundle in the inbox that differs from the install)")
    for row in available:
        print(f"waiting   : {row['short']}  built {row['built_at']}  {row['file_count']} files  owner {row['owner']}")
        for line in row["changelog"][:5]:
            print(f"            - {line}")
    print(f"snapshots : {len(snapshots)}")
PYSTATUS
}

# ---- health gate ------------------------------------------------------------
# Three legs, each reporting its own verdict. An identity-only probe would pass
# an OLD process that survived a failed restart, so the dashboard leg requires
# the answering process to carry the new source commit AND to have started
# after this apply began.
health_gate() { # <to_sha> <apply_started_at> <skip_restart>
  local to_sha="$1" started="$2" skip_restart="$3"
  local tries="${CABINET_OPEN_TRIES:-150}" url state_ok=0 verdict_dash="thin"

  if [ "$skip_restart" = "1" ]; then
    log "gate: dashboard leg THIN (--skip-restart: nothing was restarted, so a start time cannot be compared)"
  else
    # shellcheck disable=SC1090
    [ -f "$DASH_LIB" ] && . "$DASH_LIB"
    url="${CABINET_UPDATE_HEALTH_URL:-$(cabinet_dash_url "$ROOT")api/health}"
    verdict_dash="red"
    while [ "$tries" -gt 0 ]; do
      if "$PY" - "$url" "$to_sha" "$started" <<'PYHEALTH'
import json, sys, urllib.request
url, to_sha, started = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with urllib.request.urlopen(url, timeout=3) as response:
        body = json.loads(response.read().decode("utf-8"))
except Exception as exc:
    print(f"health: no answer yet ({exc})", file=sys.stderr)
    sys.exit(1)
if body.get("service") != "cabinet-dashboard":
    print("health: something answered and it is not this cabinet", file=sys.stderr)
    sys.exit(1)
stamp = body.get("source_commit") or ""
if not stamp:
    print("health: the answer carries no source_commit", file=sys.stderr)
    sys.exit(1)
if not (stamp.startswith(to_sha) or to_sha.startswith(stamp)):
    print(f"health: answering process carries {stamp[:12]}, expected {to_sha[:12]}", file=sys.stderr)
    sys.exit(1)
if (body.get("started_at") or "") <= started:
    print("health: the answering process predates this update — the restart did not happen", file=sys.stderr)
    sys.exit(1)
sys.exit(0)
PYHEALTH
      then state_ok=1; verdict_dash="green"; break; fi
      tries=$((tries - 1))
      "$PY" -c 'import time; time.sleep(2)'
    done
    [ "$state_ok" = "1" ] || { log "gate: dashboard leg RED"; printf 'red\n'; return 1; }
    log "gate: dashboard leg green"
  fi

  local receipts_cmd preflight_cmd
  receipts_cmd="${CABINET_UPDATE_RECEIPTS_CMD:-$PY -m framework.missions.receipts --json}"
  preflight_cmd="${CABINET_UPDATE_PREFLIGHT_CMD:-$PY cabinet/scripts/state-persistence-preflight.py --repo .}"
  if ! ( cd "$ROOT" && eval "$receipts_cmd" ) >>"$LOG" 2>&1; then
    log "gate: receipts leg RED ($receipts_cmd) — see $LOG"
    printf 'red\n'; return 1
  fi
  log "gate: receipts leg green"
  if ! ( cd "$ROOT" && eval "$preflight_cmd" ) >>"$LOG" 2>&1; then
    log "gate: persistence preflight RED ($preflight_cmd) — see $LOG"
    printf 'red\n'; return 1
  fi
  log "gate: persistence preflight green"

  # REPORTED, never gated: a single-worker install DEADs on fleet services it
  # was never meant to run, and gating here would roll back every good update.
  if [ -f "$ROOT/cabinet/scripts/cabinet-doctor.sh" ]; then
    ( cd "$ROOT" && bash cabinet/scripts/cabinet-doctor.sh ) >>"$LOG" 2>&1 \
      && log "doctor: reported green" || log "doctor: reported findings (NOT a gate) — see $LOG"
  fi
  printf 'green\n'
  return 0
}

restart_dashboard() {
  # shellcheck disable=SC1090
  [ -f "$DASH_LIB" ] || { log "restart: no dashboard library at $DASH_LIB"; return 1; }
  . "$DASH_LIB"
  cabinet_dash_restart "$ROOT" "taking an update"
}

# ---- rollback ---------------------------------------------------------------
restore_snapshot() { # <snapshot-dir>
  local snap="$1"
  "$PY" "$BUNDLE_PY" restore --root "$ROOT" --snapshot "$snap" >>"$LOG" 2>&1 || return 1
  if [ -d "$snap/next-previous" ]; then
    rm -rf "$ROOT/cabinet/dashboard/.next.rollback-tmp"
    [ -d "$ROOT/cabinet/dashboard/.next" ] && mv "$ROOT/cabinet/dashboard/.next" "$ROOT/cabinet/dashboard/.next.rollback-tmp"
    mv "$snap/next-previous" "$ROOT/cabinet/dashboard/.next" || return 1
    rm -rf "$ROOT/cabinet/dashboard/.next.rollback-tmp"
  fi
  local from_sha
  from_sha="$("$PY" -c '
import json, sys
print(json.load(open(sys.argv[1])).get("from_sha") or "")
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
  local want="" door="terminal" skip_restart=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --to) [ $# -ge 2 ] || fail_usage "--to needs a snapshot stamp"; want="$2"; shift 2 ;;
      --from) [ $# -ge 2 ] || fail_usage "--from needs a door"; door="$(normalize_door "$2")" || fail_usage "unknown door '$2'"; shift 2 ;;
      --skip-restart) skip_restart=1; shift ;;
      *) fail_usage "unknown rollback option '$1'" ;;
    esac
  done
  take_lock || { echo "cabinet-update: another update is running" >&2; exit "$EXIT_BUSY"; }
  local snap_name
  snap_name="${want:-$(newest_snapshot)}"
  [ -n "$snap_name" ] && [ -d "$SNAPSHOTS/$snap_name" ] || {
    echo "cabinet-update: no snapshot to roll back to" >&2; exit 1; }
  local before after
  before="$(installed_sha)"
  restore_snapshot "$SNAPSHOTS/$snap_name" || { echo "cabinet-update: restore failed — see $LOG" >&2; exit 1; }
  [ "$skip_restart" = "1" ] || restart_dashboard || log "restart after rollback did not complete"
  after="$(installed_sha)"
  write_state "{\"phase\":\"rolled_back\",\"from_sha\":$(json_escape "$before"),\"to_sha\":$(json_escape "$after"),\"snapshot\":$(json_escape "$snap_name"),\"finished_at\":$(json_escape "$(now_utc)"),\"door\":$(json_escape "$door")}"
  emit_event cabinet_update_rolled_back "$(door_actor "$door")" \
    "{\"from_sha\":$(json_escape "$before"),\"to_sha\":$(json_escape "$after"),\"reason\":\"requested\",\"door\":$(json_escape "$door")}"
  log "rolled back to $snap_name"
  return 0
}

# ---- apply ------------------------------------------------------------------
refuse() { # <exit> <reason> <to_sha> <locked-json>
  local code="$1" reason="$2" to_sha="$3" locked="${4:-[]}"
  log "REFUSED: $reason"
  emit_event cabinet_update_refused "$(door_actor "${DOOR:-terminal}")" \
    "{\"to_sha\":$(json_escape "$to_sha"),\"reason\":$(json_escape "$reason"),\"locked_paths\":$locked,\"door\":$(json_escape "${DOOR:-terminal}")}"
  exit "$code"
}

cmd_apply() {
  local sha="" skip_rebuild=0 skip_restart=0
  DOOR="terminal"
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
  case "$sha" in *[!0-9a-fA-F]*|'') fail_usage "bundle id must be a hex sha" ;; esac

  take_lock || {
    echo "cabinet-update: another update is running" >&2
    emit_event cabinet_update_refused "$(door_actor "$DOOR")" \
      "{\"to_sha\":$(json_escape "$sha"),\"reason\":\"busy\",\"locked_paths\":[],\"door\":$(json_escape "$DOOR")}"
    exit "$EXIT_BUSY"
  }

  mkdir -p "$INBOX" "$APPLIED" "$SNAPSHOTS" "$STAGE"

  # RESUME FIRST. A killed apply leaves state.json at `applying` with its
  # snapshot on disk; the tree is then neither version. Nothing else may run
  # until it is put back.
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

  local manifest tarball
  manifest="$INBOX/$sha.manifest.json"
  tarball="$INBOX/$sha.tar.gz"
  [ -f "$manifest" ] || refuse "$EXIT_REFUSED" "no manifest for bundle $sha in $INBOX" "$sha"
  [ -s "$tarball" ] || refuse "$EXIT_REFUSED" "bundle $sha is absent or empty in $INBOX" "$sha"

  local here
  here="$(installed_sha)"
  if [ -n "$here" ] && [ "$here" = "$sha" ]; then
    log "installed source commit is already $sha — nothing to do"
    return 0
  fi

  local stage_tree="$STAGE/$sha/tree"
  rm -rf "$STAGE/$sha"
  mkdir -p "$stage_tree"
  tar -xzf "$tarball" -C "$stage_tree" || refuse "$EXIT_REFUSED" "bundle $sha could not be unpacked" "$sha"

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
    refuse "$EXIT_REFUSED" "the plan could not be computed (preserve or locked set unreadable) — see $LOG" "$sha"
  fi

  local locked_hits
  locked_hits="$("$PY" -c '
import json, sys
print(json.dumps(json.load(open(sys.argv[1]))["locked_hits"]))
' "$plan_file")"
  if [ "$locked_hits" != "[]" ]; then
    echo "----------------------------------------------------------------------"
    echo "This update touches the constitutional set, so none of it was applied."
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
    refuse "$EXIT_REFUSED" "bundle $sha changes locked constitutional paths" "$sha" "$locked_hits"
  fi

  local changed_n deleted_n skipped
  changed_n="$("$PY" -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["changed"]))' "$plan_file")"
  deleted_n="$("$PY" -c 'import json,sys; print(len(json.load(open(sys.argv[1]))["deleted"]))' "$plan_file")"
  skipped="$("$PY" -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))["skipped_preserved"]))' "$plan_file")"

  if [ "$changed_n" = "0" ] && [ "$deleted_n" = "0" ]; then
    log "bundle $sha changes nothing outside the preserve set — recording it and stopping"
    cp "$manifest" "$APPLIED/$sha.manifest.json"
    "$PY" "$BUNDLE_PY" stamp-identity --root "$ROOT" --source-commit "$sha" \
      --applied-at "$(now_utc)" ${here:+--from-sha "$here"} >>"$LOG" 2>&1
    return 0
  fi

  local started stamp snap
  started="$(now_utc)"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  snap="$SNAPSHOTS/$stamp-${here:-unknown}"
  "$PY" "$BUNDLE_PY" snapshot --root "$ROOT" --plan "$plan_file" --snapshot "$snap" >>"$LOG" 2>&1 \
    || { echo "cabinet-update: snapshot failed — nothing was written" >&2; exit 1; }

  write_state "{\"phase\":\"applying\",\"from_sha\":$(json_escape "$here"),\"to_sha\":$(json_escape "$sha"),\"snapshot\":$(json_escape "$(basename "$snap")"),\"started_at\":$(json_escape "$started"),\"door\":$(json_escape "$DOOR")}"

  local kill_arg=()
  [ -n "${CABINET_UPDATE_TEST_KILL_AFTER:-}" ] && kill_arg=(--kill-after "$CABINET_UPDATE_TEST_KILL_AFTER")
  "$PY" "$BUNDLE_PY" apply-plan --root "$ROOT" --tree "$stage_tree" --plan "$plan_file" \
    "${kill_arg[@]+"${kill_arg[@]}"}" >>"$LOG" 2>&1 \
    || { log "write failed — rolling back"; restore_snapshot "$snap"; write_state "{\"phase\":\"rolled_back\",\"reason\":\"write failed\"}"; exit 1; }

  "$PY" "$BUNDLE_PY" stamp-identity --root "$ROOT" --source-commit "$sha" \
    --applied-at "$(now_utc)" ${here:+--from-sha "$here"} >>"$LOG" 2>&1

  # ---- staged rebuild, swapped by rename last ----
  local dashboard_changed=0
  "$PY" -c '
import json, sys
plan = json.load(open(sys.argv[1]))
touched = plan["changed"] + plan["deleted"]
sys.exit(0 if any(p.startswith("cabinet/dashboard/") for p in touched) else 1)
' "$plan_file" && dashboard_changed=1
  if [ "$dashboard_changed" = "1" ] && [ "$skip_rebuild" = "0" ]; then
    if ! stage_build "$stage_tree" "$snap"; then
      log "build failed — rolling back"
      restore_snapshot "$snap"
      [ "$skip_restart" = "1" ] || restart_dashboard || true
      write_state "{\"phase\":\"rolled_back\",\"from_sha\":$(json_escape "$sha"),\"to_sha\":$(json_escape "$here"),\"snapshot\":$(json_escape "$(basename "$snap")"),\"reason\":\"build failed\",\"finished_at\":$(json_escape "$(now_utc)")}"
      emit_event cabinet_update_rolled_back "$(door_actor "$DOOR")" \
        "{\"from_sha\":$(json_escape "$sha"),\"to_sha\":$(json_escape "$here"),\"reason\":\"build failed\",\"door\":$(json_escape "$DOOR")}"
      exit 1
    fi
  elif [ "$dashboard_changed" = "1" ]; then
    log "rebuild SKIPPED by request — the running build is now older than the code it serves (THIN)"
  fi

  [ "$skip_restart" = "1" ] || restart_dashboard || log "restart did not complete — the gate will say so"

  local verdict
  verdict="$(health_gate "$sha" "$started" "$skip_restart")"
  if [ "$verdict" != "green" ]; then
    log "health gate RED — rolling back automatically"
    restore_snapshot "$snap"
    [ "$skip_restart" = "1" ] || restart_dashboard || true
    write_state "{\"phase\":\"rolled_back\",\"from_sha\":$(json_escape "$sha"),\"to_sha\":$(json_escape "$here"),\"snapshot\":$(json_escape "$(basename "$snap")"),\"reason\":\"health gate red\",\"finished_at\":$(json_escape "$(now_utc)")}"
    emit_event cabinet_update_rolled_back "$(door_actor "$DOOR")" \
      "{\"from_sha\":$(json_escape "$sha"),\"to_sha\":$(json_escape "$here"),\"reason\":\"health gate red\",\"door\":$(json_escape "$DOOR")}"
    exit 1
  fi

  cp "$manifest" "$APPLIED/$sha.manifest.json"
  prune_snapshots
  local built_at owner mtime
  built_at="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("built_at") or "")' "$manifest")"
  owner="$("$PY" -c '
import pwd, sys, os
try:
    print(pwd.getpwuid(os.stat(sys.argv[1]).st_uid).pw_name)
except Exception:
    print("")
' "$tarball")"
  mtime="$("$PY" -c 'import os,sys,datetime; print(datetime.datetime.utcfromtimestamp(os.stat(sys.argv[1]).st_mtime).strftime("%Y-%m-%dT%H:%M:%SZ"))' "$tarball")"
  write_state "{\"phase\":\"applied\",\"from_sha\":$(json_escape "$here"),\"to_sha\":$(json_escape "$sha"),\"snapshot\":$(json_escape "$(basename "$snap")"),\"started_at\":$(json_escape "$started"),\"finished_at\":$(json_escape "$(now_utc)"),\"changed\":$changed_n,\"deleted\":$deleted_n,\"skipped_preserved\":$skipped,\"built_at\":$(json_escape "$built_at"),\"door\":$(json_escape "$DOOR")}"
  emit_event cabinet_update_applied "$(door_actor "$DOOR")" \
    "{\"from_sha\":$(json_escape "$here"),\"to_sha\":$(json_escape "$sha"),\"changed\":$changed_n,\"deleted\":$deleted_n,\"snapshot\":$(json_escape "$(basename "$snap")"),\"door\":$(json_escape "$DOOR"),\"source_commit\":$(json_escape "$sha"),\"built_at\":$(json_escape "$built_at"),\"inbox_owner\":$(json_escape "$owner"),\"inbox_mtime\":$(json_escape "$mtime"),\"skipped_preserved\":$skipped}"
  log "applied ${here:0:8} -> ${sha:0:8}: $changed_n changed, $deleted_n deleted"
  if [ "$skipped" != "[]" ]; then
    log "kept your own data instead of the shipped copy: $skipped"
  fi
  return 0
}

# The build runs in the STAGE tree, not in the install: a failed build must
# never be able to leave the served directory half-written. The previous build
# is moved into the snapshot (it is a local artifact, not shipped content) and
# the new one is renamed into place LAST.
stage_build() { # <stage-tree> <snapshot-dir>
  local stage_tree="$1" snap="$2"
  local stage_dash="$stage_tree/cabinet/dashboard"
  local live_dash="$ROOT/cabinet/dashboard"
  [ -d "$stage_dash" ] || { log "build: the bundle carries no dashboard"; return 0; }
  command -v npm >/dev/null 2>&1 || { log "build: no node toolchain on this box"; return 1; }

  if [ -d "$live_dash/node_modules" ] && [ -f "$live_dash/package-lock.json" ] \
     && [ -f "$stage_dash/package-lock.json" ] \
     && cmp -s "$live_dash/package-lock.json" "$stage_dash/package-lock.json"; then
    # Same lockfile, same dependencies: reuse what is already installed rather
    # than paying a fresh install per update (the loop tax, not the typing).
    ln -s "$live_dash/node_modules" "$stage_dash/node_modules"
  else
    ( cd "$stage_dash" && npm ci --include=dev --no-audit --no-fund ) >>"$LOG" 2>&1 || return 1
  fi
  ( cd "$stage_dash" && CABINET_BUILD_SOURCE_COMMIT="${1:-}" npm run build ) >>"$LOG" 2>&1 || return 1
  [ -d "$stage_dash/.next" ] || { log "build: produced no output"; return 1; }
  mkdir -p "$snap"
  if [ -d "$live_dash/.next" ]; then
    rm -rf "$snap/next-previous"
    mv "$live_dash/.next" "$snap/next-previous" || return 1
  fi
  mv "$stage_dash/.next" "$live_dash/.next" || return 1
  log "build: swapped in a fresh build (previous one snapshotted)"
  return 0
}

prune_snapshots() {
  [ -d "$SNAPSHOTS" ] || return 0
  local keep="$KEEP" names count
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

# ---- dispatch ---------------------------------------------------------------
CMD="${1:-}"
[ -n "$CMD" ] || { usage; exit "$EXIT_USAGE"; }
shift

case "$CMD" in
  publish) cmd_publish "$@" ;;
  status)  cmd_status "$@" ;;
  apply|rollback)
    [ -f "$BUNDLE_PY" ] || { echo "cabinet-update: helper missing: $BUNDLE_PY" >&2; exit 1; }
    if [ "${CABINET_UPDATE_REEXEC:-0}" != "1" ]; then
      reexec_detached "$CMD" "$@"
    fi
    if [ "$CMD" = "apply" ]; then cmd_apply "$@"; else cmd_rollback "$@"; fi
    ;;
  -h|--help|help) usage ;;
  *) fail_usage "unknown command '$CMD'" ;;
esac
