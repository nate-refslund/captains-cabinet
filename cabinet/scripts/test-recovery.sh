#!/bin/bash
# test-recovery.sh — exact, non-reboot recovery drill for the Mac fleet.
#
# The drill operates ONLY on the enabled rows in cabinet/services.yml plus the
# deployment-local roster officers.  Disabled rows, legacy installed plists,
# and the independently-attested egress proxy are never activation inputs.
#
# Preconditions (all fail closed before the first bootout):
#   * the loaded Cabinet labels exactly equal the enabled fleet (+ egress when
#     launchd-owned), with no disabled/legacy Cabinet job loaded;
#   * roster officer tmux sessions exactly match the roster;
#   * observe-only is active, posture-narrow is exactly earn_up, and the kill
#     switch is provably ACTIVE;
#   * egress runtime + status attest successfully;
#   * Redis is reachable and Cabinet Doctor is GREEN;
#   * every enabled label has a regular, non-symlink installed plist whose
#     internal Label exactly matches the manifest/roster label.
#
# Mutation:
#   1. boot out exactly the enabled labels (never a glob);
#   2. kill exactly the roster officer tmux sessions to simulate logout;
#   3. prove the enabled labels/sessions are absent while egress remains exact;
#   4. bootstrap exactly those same installed plists;
#   5. exact-compare labels, sessions, observe posture, egress attestation,
#      Redis PONG, and the semantic Cabinet Doctor result with the PRE state.
#
# A trap makes a best-effort attempt to restore every enabled label if the
# drill exits after mutation starts.  It never starts a label outside the
# allowlist.  This simulates logout/login, not loss of Redis or host power.
#
# Usage:
#   bash cabinet/scripts/test-recovery.sh [--dry-run] [--timeout 90]
#       [--evidence-dir /path/to/empty-or-new-directory]

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd -P)}"
DRY_RUN=0
TIMEOUT=90
EVIDENCE_DIR=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --timeout)
      [ $# -ge 2 ] || { echo "test-recovery.sh: --timeout requires seconds" >&2; exit 64; }
      TIMEOUT="$2"; shift 2 ;;
    --evidence-dir)
      [ $# -ge 2 ] || { echo "test-recovery.sh: --evidence-dir requires a path" >&2; exit 64; }
      EVIDENCE_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '2,33p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "test-recovery.sh: unknown flag '$1'" >&2; exit 64 ;;
  esac
done
case "$TIMEOUT" in ''|*[!0-9]*) echo "test-recovery.sh: timeout must be a positive integer" >&2; exit 64 ;; esac
[ "$TIMEOUT" -gt 0 ] || { echo "test-recovery.sh: timeout must be > 0" >&2; exit 64; }

if [ -n "$EVIDENCE_DIR" ]; then
  if [ -L "$EVIDENCE_DIR" ] || { [ -e "$EVIDENCE_DIR" ] && [ ! -d "$EVIDENCE_DIR" ]; }; then
    echo "test-recovery.sh: evidence path must be a real directory, not a file/symlink" >&2
    exit 73
  fi
  mkdir -p "$EVIDENCE_DIR" || exit 73
  if [ -n "$(find "$EVIDENCE_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    echo "test-recovery.sh: evidence directory must be empty: $EVIDENCE_DIR" >&2
    exit 73
  fi
  EVIDENCE_DIR="$(cd "$EVIDENCE_DIR" && pwd -P)" || exit 73
fi

PY="${RECOVERY_PYTHON:-python3.12}"
LAUNCHCTL="${RECOVERY_LAUNCHCTL:-launchctl}"
TMUX="${RECOVERY_TMUX:-tmux}"
REDIS_CLI="${RECOVERY_REDIS_CLI:-redis-cli}"
OBSERVE_CONTROL="${RECOVERY_OBSERVE_CONTROL:-$CABINET_ROOT/cabinet/scripts/observe-only.sh}"
KILL_SWITCH_CONTROL="${RECOVERY_KILL_SWITCH_CONTROL:-$CABINET_ROOT/cabinet/scripts/kill-switch.sh}"
EGRESS_GUARD="${RECOVERY_EGRESS_GUARD:-$CABINET_ROOT/cabinet/scripts/egress-guard.sh}"
DOCTOR="${RECOVERY_DOCTOR:-$CABINET_ROOT/cabinet/scripts/cabinet-doctor.sh}"
LAUNCH_AGENTS_DIR="${RECOVERY_LAUNCH_AGENTS_DIR:-${HOME:?HOME is required}/Library/LaunchAgents}"
EGRESS_LABEL="${RECOVERY_EGRESS_LABEL:-com.cabinet.egress-proxy}"
POLL_INTERVAL="${RECOVERY_POLL_INTERVAL:-2}"
GUI_DOMAIN="gui/$(id -u)"

for cmd in "$PY" "$LAUNCHCTL" "$TMUX" "$REDIS_CLI"; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "test-recovery.sh: required command unavailable: $cmd" >&2; exit 69;
  }
done
for script in "$OBSERVE_CONTROL" "$KILL_SWITCH_CONTROL" "$EGRESS_GUARD" "$DOCTOR"; do
  [ -f "$script" ] || { echo "test-recovery.sh: required control missing: $script" >&2; exit 69; }
done

WORK="$(mktemp -d "${TMPDIR:-/tmp}/cabinet-recovery.XXXXXX")" || exit 70
PLAN="$WORK/plan"
mkdir -p "$PLAN"
MUTATION_STARTED=0
COMPLETED=0

cleanup() {
  rc=$? copy_rc=0
  trap - EXIT INT TERM HUP
  if [ "$MUTATION_STARTED" -eq 1 ] && [ "$COMPLETED" -ne 1 ]; then
    echo "  [RECOVERY] interrupted/failed — restoring only enabled fleet labels" >&2
    while IFS=$'\t' read -r _name label plist _kind; do
      [ -n "${label:-}" ] || continue
      if ! "$LAUNCHCTL" print "$GUI_DOMAIN/$label" >/dev/null 2>&1; then
        "$LAUNCHCTL" bootstrap "$GUI_DOMAIN" "$plist" >/dev/null 2>&1 ||
          echo "  [RECOVERY-FAIL] could not bootstrap $label from $plist" >&2
      fi
    done < "$PLAN/enabled.tsv"
  fi
  if [ -n "$EVIDENCE_DIR" ] && [ -d "$WORK" ]; then
    mkdir -p "$EVIDENCE_DIR" 2>/dev/null || true
    cp -R "$WORK"/. "$EVIDENCE_DIR"/ 2>/dev/null || copy_rc=1
  fi
  rm -rf "$WORK"
  if [ "$copy_rc" -ne 0 ] && [ "$rc" -eq 0 ]; then
    echo "  [FAIL] recovery state passed but evidence publication failed: $EVIDENCE_DIR" >&2
    rc=74
  fi
  exit "$rc"
}
trap cleanup EXIT INT TERM HUP

die() {
  printf 'RECOVERY DRILL FAILED — %s\n' "$*" > "$WORK/result.txt" 2>/dev/null || true
  echo "  [FAIL] $*" >&2
  exit 1
}
ok() { echo "  [OK] $*"; }

cd "$CABINET_ROOT" || die "cannot cd to $CABINET_ROOT"

# Build the sole activation allowlist.  lib_roster is the same source used by
# Cabinet Doctor; no officer slug is copied into this framework script.
if ! "$PY" - "$CABINET_ROOT" "$LAUNCH_AGENTS_DIR" "$PLAN" <<'PY'
from __future__ import annotations

import plistlib
import re
import sys
from pathlib import Path

import yaml

root = Path(sys.argv[1]).resolve()
launch_agents = Path(sys.argv[2])
out = Path(sys.argv[3])
sys.path.insert(0, str(root / "cabinet" / "scripts"))
import lib_roster  # noqa: E402

doc = yaml.safe_load((root / "cabinet" / "services.yml").read_text()) or {}
manifest = doc.get("services")
if not isinstance(manifest, list):
    raise SystemExit("services.yml: services must be a list")
roster_rows = lib_roster.officer_service_rows(root)
rows = list(manifest) + roster_rows
label_re = re.compile(r"^com\.cabinet\.[A-Za-z0-9._-]+$")
seen: set[str] = set()
enabled: list[tuple[str, str, Path, str]] = []
disabled: list[str] = []
officer_sessions: list[str] = []

for row in rows:
    if not isinstance(row, dict):
        raise SystemExit("services.yml: every service row must be a mapping")
    name = str(row.get("name") or "")
    label = str(row.get("label") or "")
    kind = str(row.get("kind") or "daemon")
    if not name or not label_re.fullmatch(label):
        raise SystemExit(f"invalid fleet row name/label: {name!r} {label!r}")
    if label in seen:
        raise SystemExit(f"duplicate fleet label: {label}")
    seen.add(label)
    if row.get("disabled") is True:
        disabled.append(label)
        continue
    plist = launch_agents / f"{label}.plist"
    if not plist.is_file() or plist.is_symlink():
        raise SystemExit(f"enabled label has no regular installed plist: {label} ({plist})")
    try:
        with plist.open("rb") as fh:
            actual = plistlib.load(fh).get("Label")
    except Exception as exc:
        raise SystemExit(f"installed plist is invalid for {label}: {type(exc).__name__}")
    if actual != label:
        raise SystemExit(f"installed plist Label mismatch: expected {label}, got {actual!r}")
    enabled.append((name, label, plist, kind))
    if kind == "officer":
        officer_sessions.append(name)

if not enabled:
    raise SystemExit("enabled fleet is empty — refusing a vacuous recovery drill")

enabled.sort(key=lambda row: row[1])
(out / "enabled.tsv").write_text("".join(
    f"{name}\t{label}\t{plist}\t{kind}\n" for name, label, plist, kind in enabled
))
(out / "enabled-labels.txt").write_text("".join(f"{r[1]}\n" for r in enabled))
(out / "disabled-labels.txt").write_text("".join(f"{x}\n" for x in sorted(disabled)))
(out / "officer-sessions.txt").write_text(
    "".join(f"{x}\n" for x in sorted(officer_sessions))
)
PY
then
  die "could not derive and validate exact fleet plan"
fi

loaded_labels() {
  "$LAUNCHCTL" list 2>/dev/null |
    awk '$3 ~ /^com\.cabinet\.[A-Za-z0-9._-]+$/ {print $3}' | sort -u
}

officer_sessions() {
  "$TMUX" list-sessions -F '#S' 2>/dev/null |
    grep -E '^officer-[A-Za-z0-9._-]+$' | sort -u || true
}

controlled_labels() {
  # Egress is an independently-attested boundary and must remain running.  It
  # is excluded only when it is not itself an enabled manifest label.
  local all="$1"
  if grep -Fxq "$EGRESS_LABEL" "$PLAN/enabled-labels.txt"; then
    cat "$all"
  else
    grep -Fvx "$EGRESS_LABEL" "$all" || true
  fi
}

capture_observe() {
  local dest="$1" state posture hash kill_state
  state="$(bash "$OBSERVE_CONTROL" status 2>&1)" || return 1
  kill_state="$(bash "$KILL_SWITCH_CONTROL" status 2>&1)" || return 1
  [ -f "$CABINET_ROOT/instance/config/posture-narrow" ] || return 1
  posture="$(tr -d '[:space:]' < "$CABINET_ROOT/instance/config/posture-narrow")"
  hash="$("$PY" - "$CABINET_ROOT/instance/config/posture-narrow" <<'PY'
import hashlib, pathlib, sys
print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())
PY
)" || return 1
  printf 'observe=%s\nposture=%s\nposture_sha256=%s\nkill_switch=%s\n' \
    "$state" "$posture" "$hash" "$kill_state" > "$dest"
  [ "$state" = active ] && [ "$posture" = earn_up ] &&
    printf '%s' "$kill_state" | grep -q '^Kill switch: ACTIVE'
}

capture_egress() {
  local prefix="$1" runtime
  runtime="$(bash "$EGRESS_GUARD" runtime-state 2>"$prefix.egress-runtime.err")" || return 1
  printf '%s\n' "$runtime" > "$prefix.egress-runtime"
  [ "${runtime%%$'\t'*}" = 1 ] || return 1
  bash "$EGRESS_GUARD" status > "$prefix.egress-status" 2>"$prefix.egress-status.err"
}

capture_doctor() {
  local prefix="$1" rc verdict
  if bash "$DOCTOR" > "$prefix.doctor-output" 2>&1; then rc=0; else rc=$?; fi
  verdict="$(grep '^CABINET_DOCTOR ' "$prefix.doctor-output" | tail -1)"
  printf 'rc=%s\n%s\n' "$rc" "$verdict" > "$prefix.doctor-result"
  # PIDs, log ages, and heartbeat timestamps legitimately change on restart.
  # Compare the stable semantic map instead: every finding's classification
  # plus its subject, in Doctor order.  This prevents equal aggregate counts
  # from hiding one check improving while another degrades.
  "$PY" - "$prefix.doctor-output" >> "$prefix.doctor-result" <<'PY'
import re, sys
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    match = re.match(r"^(OK|WARN|WAIVED|SKIP|DEAD)\s+(.*)$", line.rstrip("\n"))
    if not match:
        continue
    subject = match.group(2).split(" — ", 1)[0]
    print(f"{match.group(1)}\t{subject}")
PY
  [ "$rc" -eq 0 ] && printf '%s' "$verdict" | grep -q '^CABINET_DOCTOR GREEN '
}

capture_state() {
  local prefix="$1"
  loaded_labels > "$prefix.labels"
  officer_sessions > "$prefix.sessions"
  capture_observe "$prefix.observe" || return 1
  capture_egress "$prefix" || return 1
  "$REDIS_CLI" ping > "$prefix.redis" 2>/dev/null || return 1
  [ "$(tr -d '[:space:]' < "$prefix.redis")" = PONG ] || return 1
  capture_doctor "$prefix" || return 1
}

assert_exact_pre_fleet() {
  controlled_labels "$WORK/pre.labels" > "$WORK/pre.controlled-labels"
  if ! cmp -s "$PLAN/enabled-labels.txt" "$WORK/pre.controlled-labels"; then
    diff -u "$PLAN/enabled-labels.txt" "$WORK/pre.controlled-labels" >&2 || true
    die "loaded Cabinet labels do not exactly equal enabled manifest + roster; disabled/legacy/missing activation refused"
  fi
  if ! cmp -s "$PLAN/officer-sessions.txt" "$WORK/pre.sessions"; then
    diff -u "$PLAN/officer-sessions.txt" "$WORK/pre.sessions" >&2 || true
    die "officer tmux sessions do not exactly equal roster"
  fi
  while IFS= read -r label; do
    [ -n "$label" ] || continue
    if grep -Fxq "$label" "$WORK/pre.labels"; then
      die "disabled manifest label is loaded: $label"
    fi
  done < "$PLAN/disabled-labels.txt"
}

same_file() {
  local a="$1" b="$2" what="$3"
  if ! cmp -s "$a" "$b"; then
    diff -u "$a" "$b" >&2 || true
    die "$what changed across recovery"
  fi
  ok "$what exactly preserved"
}

echo "============================================"
echo "  Cabinet exact recovery drill (observe-only)"
echo "============================================"
echo "  enabled labels: $(wc -l < "$PLAN/enabled-labels.txt" | tr -d ' ')"
echo "  roster sessions: $(wc -l < "$PLAN/officer-sessions.txt" | tr -d ' ')"
echo "  egress boundary: $EGRESS_LABEL (preserved, never booted out)"

capture_state "$WORK/pre" || die "PRE snapshot/attestation failed"
assert_exact_pre_fleet
ok "PRE fleet equals enabled manifest + roster; no disabled/legacy job loaded"
ok "observe-only=active, posture-narrow=earn_up, and kill switch ACTIVE"
ok "egress and Cabinet Doctor attest; Redis PONG"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "  --dry-run: no bootout, tmux kill, or bootstrap performed"
  echo "RECOVERY DRILL DRY-RUN PASS"
  printf 'RECOVERY DRILL DRY-RUN PASS\n' > "$WORK/result.txt"
  COMPLETED=1
  exit 0
fi

MUTATION_STARTED=1
echo "  Booting out exact enabled fleet..."
while IFS=$'\t' read -r _name label _plist _kind; do
  "$LAUNCHCTL" bootout "$GUI_DOMAIN/$label" >/dev/null 2>&1 ||
    die "bootout failed for enabled label $label"
done < "$PLAN/enabled.tsv"

echo "  Removing exact roster tmux sessions to simulate logout..."
while IFS= read -r session; do
  [ -n "$session" ] || continue
  "$TMUX" kill-session -t "=$session" >/dev/null 2>&1 ||
    die "could not remove roster session $session"
done < "$PLAN/officer-sessions.txt"

# Prove the controlled fleet is actually down.  Egress must remain byte-exact.
down_labels="$WORK/down.labels"
loaded_labels > "$down_labels"
controlled_labels "$down_labels" > "$WORK/down.controlled-labels"
[ ! -s "$WORK/down.controlled-labels" ] ||
  die "one or more enabled Cabinet labels remained loaded after bootout"
officer_sessions > "$WORK/down.sessions"
[ ! -s "$WORK/down.sessions" ] || die "one or more officer sessions remained after exact teardown"
capture_egress "$WORK/down" || die "egress lost attestation during teardown"
same_file "$WORK/pre.egress-runtime" "$WORK/down.egress-runtime" "egress runtime during teardown"
same_file "$WORK/pre.egress-status" "$WORK/down.egress-status" "egress status during teardown"
capture_observe "$WORK/down.observe" || die "observe-only/kill-switch posture failed during teardown"
same_file "$WORK/pre.observe" "$WORK/down.observe" "observe-only posture during teardown"

echo "  Bootstrapping exact enabled fleet..."
while IFS=$'\t' read -r _name label plist _kind; do
  "$LAUNCHCTL" bootstrap "$GUI_DOMAIN" "$plist" >/dev/null 2>&1 ||
    die "bootstrap failed for enabled label $label"
done < "$PLAN/enabled.tsv"

echo "  Waiting up to ${TIMEOUT}s for exact recovery..."
start_epoch="$(date +%s)"
while :; do
  loaded_labels > "$WORK/wait.labels"
  controlled_labels "$WORK/wait.labels" > "$WORK/wait.controlled-labels"
  officer_sessions > "$WORK/wait.sessions"
  if cmp -s "$PLAN/enabled-labels.txt" "$WORK/wait.controlled-labels" &&
     cmp -s "$PLAN/officer-sessions.txt" "$WORK/wait.sessions" &&
     [ "$("$REDIS_CLI" ping 2>/dev/null)" = PONG ]; then
    break
  fi
  now="$(date +%s)"
  [ $((now - start_epoch)) -lt "$TIMEOUT" ] ||
    die "exact labels/sessions/Redis did not recover within ${TIMEOUT}s"
  sleep "$POLL_INTERVAL"
done

capture_state "$WORK/post" || die "POST snapshot/attestation failed"
controlled_labels "$WORK/post.labels" > "$WORK/post.controlled-labels"
same_file "$PLAN/enabled-labels.txt" "$WORK/post.controlled-labels" "enabled label set"
same_file "$WORK/pre.labels" "$WORK/post.labels" "complete Cabinet label set"
same_file "$WORK/pre.sessions" "$WORK/post.sessions" "roster session set"
same_file "$WORK/pre.observe" "$WORK/post.observe" "observe-only posture"
same_file "$WORK/pre.egress-runtime" "$WORK/post.egress-runtime" "egress runtime attestation"
same_file "$WORK/pre.egress-status" "$WORK/post.egress-status" "egress status attestation"
same_file "$WORK/pre.redis" "$WORK/post.redis" "Redis result"
same_file "$WORK/pre.doctor-result" "$WORK/post.doctor-result" "Cabinet Doctor semantic result"

COMPLETED=1
elapsed=$(( $(date +%s) - start_epoch ))
printf 'RECOVERY DRILL PASSED — exact enabled fleet restored in %ss\n' "$elapsed" > "$WORK/result.txt"
cat "$WORK/result.txt"
