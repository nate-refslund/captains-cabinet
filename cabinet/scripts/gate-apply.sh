#!/bin/bash
# gate-apply.sh — the DARK germline code-apply lane [D15, sovereign spec §4
# SOV-8]. SHIPS DARK: no setup script installs or loads this; the paired
# com.cabinet.gate-apply.plist carries Disabled=true and is armed ONLY by the
# Captain's explicit `sudo launchctl load` AFTER the unprivileged sandbox
# verify harness exists. Until then, germline code apply stays Captain-manual
# in every posture (directive f exemption extended to the apply lane itself).
#
# DOCTRINE (the killed design ran the S1/S2/S3 pytest suite as root — never):
#   * verify runs UNPRIVILEGED (drop-to-$CABINET_VERIFY_USER, default nobody)
#     pinned to the bundle content-hash, with git hooks disabled
#     (core.hooksPath=/dev/null). pytest NEVER executes with euid 0.
#   * root does ONLY a non-executing, hash-matched
#     `git -c core.hooksPath=/dev/null apply` — and reads immutable-core.yml
#     + the revert plan from the LOCKED LIVE TREE, never from the bundle.
#   * every refusal exits non-zero BEFORE any tree mutation.
#
# PACK LAYOUT (produced by framework/learning/gate.py ratify()):
#   <packdir>/pack.json          evidence pack (verdict, sha256, stages)
#   <packdir>/bundle.patch       the exact unified diff (sha256 must match)
#
# USAGE:
#   sudo bash cabinet/scripts/gate-apply.sh apply  <packdir>   # DARK path
#        bash cabinet/scripts/gate-apply.sh verify <packdir>   # unprivileged
#   sudo bash cabinet/scripts/gate-apply.sh watch              # 72h rollback
#
# TEST MODE: CABINET_GATE_APPLY_TEST=1 lets the REFUSAL paths run without
# root, against a scratch tree named by CABINET_GATE_APPLY_ROOT. It never
# weakens a refusal — apply still refuses unless every check passes AND the
# target is that explicit scratch tree.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_MODE="${CABINET_GATE_APPLY_TEST:-0}"
LIVE_ROOT="${CABINET_GATE_APPLY_ROOT:-$REPO}"
VERIFY_USER="${CABINET_VERIFY_USER:-nobody}"
PY="python3.12"

refuse() { echo "gate-apply: REFUSED: $*" >&2; exit 2; }
note()   { echo "gate-apply: $*" >&2; }

# ---------------------------------------------------------------------------
# Shared refusal checks (run before ANYTHING mutates, in every mode)
# ---------------------------------------------------------------------------

sha256_of() { /usr/bin/shasum -a 256 "$1" | awk '{print $1}'; }

check_posture_locked() {
  # The ruling file must exist AND be schg-locked in the LIVE tree — an
  # unlocked estate means a Captain edit window is open; the apply lane must
  # never race it.
  local posture="$LIVE_ROOT/instance/config/posture.yml"
  [ -f "$posture" ] || refuse "posture.yml absent — no attested ruling ($posture)"
  local flags
  flags="$(/usr/bin/stat -f '%Sf' "$posture" 2>/dev/null || true)"
  case ",$flags," in
    *,schg,*|*schg*) : ;;
    *) refuse "posture.yml is not schg-locked — ruling not attested" ;;
  esac
}

check_pack() {
  # Forged-pack defense: pack.json must carry verdict=pass and a sha256 that
  # matches the bundle bytes EXACTLY. jq-free (python for parsing).
  local packdir="$1"
  [ -d "$packdir" ] || refuse "pack dir not found: $packdir"
  [ -f "$packdir/pack.json" ] || refuse "pack.json missing (forged/incomplete pack)"
  [ -f "$packdir/bundle.patch" ] || refuse "bundle.patch missing (forged/incomplete pack)"
  local verdict want_sha have_sha
  verdict="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("verdict",""))' "$packdir/pack.json")" \
    || refuse "pack.json unparseable"
  [ "$verdict" = "pass" ] || refuse "pack verdict is '$verdict', not pass"
  want_sha="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("sha256",""))' "$packdir/pack.json")"
  have_sha="$(sha256_of "$packdir/bundle.patch")"
  [ -n "$want_sha" ] || refuse "pack.json carries no sha256 (forged pack)"
  [ "$want_sha" = "$have_sha" ] || refuse "bundle hash mismatch (forged pack): pack=$want_sha bundle=$have_sha"
}

check_ring0() {
  # Ring-0 re-check against the LOCKED LIVE TREE's immutable-core.yml — never
  # the bundle's copy (a bundle could ship a permissive enumeration).
  local packdir="$1"
  local core="$LIVE_ROOT/framework/policies/immutable-core.yml"
  [ -f "$core" ] || refuse "live immutable-core.yml unreadable — cannot see Ring-0"
  CABINET_ROOT="$LIVE_ROOT" "$PY" - "$packdir/bundle.patch" <<'PYEOF' || refuse "diff touches Ring-0 (per the LOCKED live tree)"
import sys
from pathlib import Path
sys.path.insert(0, __import__("os").environ["CABINET_ROOT"])
from framework.learning.gate import diff_paths, load_ring0, touches_ring0
ring0 = load_ring0()
if ring0 is None:
    sys.exit(1)  # unreadable enumeration refuses
sys.exit(1 if touches_ring0(diff_paths(Path(sys.argv[1]).read_text()), ring0) else 0)
PYEOF
}

# ---------------------------------------------------------------------------
# verify — UNPRIVILEGED sandbox run (pytest lives ONLY here, never as root)
# ---------------------------------------------------------------------------

cmd_verify() {
  local packdir="$1"
  check_pack "$packdir"
  check_ring0 "$packdir"
  if [ "$(id -u)" -eq 0 ]; then
    if [ "$TEST_MODE" = "1" ]; then
      refuse "verify must not run as root (test mode has no drop path)"
    fi
    note "root caller: dropping to $VERIFY_USER for the verify run"
    exec /usr/bin/sudo -u "$VERIFY_USER" -H \
      CABINET_GATE_APPLY_ROOT="$LIVE_ROOT" \
      /bin/bash "$REPO/cabinet/scripts/gate-apply.sh" verify "$packdir"
  fi
  # Sandbox harness gate (D15): until a scratch worktree is prepared for this
  # bundle, verify FAILS CLOSED rather than pretending.
  local workdir="${CABINET_GATE_VERIFY_WORKDIR:-}"
  [ -n "$workdir" ] && [ -d "$workdir" ] \
    || refuse "no unprivileged sandbox worktree (set CABINET_GATE_VERIFY_WORKDIR) — sandbox harness not built"
  note "verify: unprivileged (uid $(id -u)) in $workdir, hooks disabled"
  ( cd "$workdir" \
      && git -c core.hooksPath=/dev/null apply --check "$packdir/bundle.patch" \
      && git -c core.hooksPath=/dev/null apply "$packdir/bundle.patch" \
      && "$PY" -m pytest -q -p no:cacheprovider ) \
    || refuse "unprivileged verify failed"
  note "verify: PASS (bundle $(sha256_of "$packdir/bundle.patch"))"
}

# ---------------------------------------------------------------------------
# apply — root-only, non-executing, hash-matched (DARK until Captain-armed)
# ---------------------------------------------------------------------------

cmd_apply() {
  local packdir="$1"
  if [ "$TEST_MODE" != "1" ] && [ "$(id -u)" -ne 0 ]; then
    refuse "apply requires root (sudo) — and stays DARK until the Captain arms the daemon"
  fi
  if [ "$TEST_MODE" = "1" ] && [ "$LIVE_ROOT" = "$REPO" ]; then
    refuse "test mode may only apply into an explicit scratch CABINET_GATE_APPLY_ROOT"
  fi
  check_posture_locked
  check_pack "$packdir"
  check_ring0 "$packdir"
  local sha
  sha="$(sha256_of "$packdir/bundle.patch")"
  note "apply: hash-matched non-executing git apply into $LIVE_ROOT (hooks disabled)"
  ( cd "$LIVE_ROOT" \
      && git -c core.hooksPath=/dev/null apply --check "$packdir/bundle.patch" \
      && git -c core.hooksPath=/dev/null apply "$packdir/bundle.patch" ) \
    || refuse "git apply failed (tree drifted since ratify?)"
  # Open the 72h watch with the revert plan FROM THE LIVE TREE (apply -R of
  # the exact hash-matched bundle) — apply_watch decides, the daemon executes.
  local pack_id
  pack_id="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1])).get("pack_id",""))' "$packdir/pack.json")"
  CABINET_ROOT="$LIVE_ROOT" "$PY" - "$pack_id" "$sha" "$packdir/bundle.patch" <<'PYEOF'
import os, sys
sys.path.insert(0, os.environ["CABINET_ROOT"])
from framework.learning.apply_watch import record_apply
record_apply(sys.argv[1], sha256=sys.argv[2],
             revert_plan=f"git -c core.hooksPath=/dev/null apply -R {sys.argv[3]}")
PYEOF
  note "apply: DONE pack=$pack_id sha=$sha — 72h watch open"
}

# ---------------------------------------------------------------------------
# watch — evaluate 72h decisions; execute recorded revert plans (root)
# ---------------------------------------------------------------------------

cmd_watch() {
  if [ "$TEST_MODE" != "1" ] && [ "$(id -u)" -ne 0 ]; then
    refuse "watch (the rollback executor) requires root"
  fi
  local decisions
  decisions="$(CABINET_ROOT="$LIVE_ROOT" "$PY" -m framework.learning.apply_watch --json)"
  echo "$decisions" | "$PY" -c '
import json, sys
for d in json.load(sys.stdin):
    if d.get("decision") == "rollback":
        print(d.get("revert_plan") or "")
' | while IFS= read -r plan; do
    [ -n "$plan" ] || continue
    case "$plan" in
      "git -c core.hooksPath=/dev/null apply -R "*) : ;;
      *) note "SKIP unrecognized revert plan: $plan"; continue ;;
    esac
    local_patch="${plan##* }"
    [ -f "$local_patch" ] || { note "SKIP rollback, patch gone: $local_patch"; continue; }
    note "ROLLBACK: $plan"
    ( cd "$LIVE_ROOT" && git -c core.hooksPath=/dev/null apply -R "$local_patch" ) \
      || note "rollback failed for $local_patch — Captain attention required"
  done
}

# ---------------------------------------------------------------------------

case "${1:-}" in
  verify) shift; [ $# -ge 1 ] || refuse "usage: gate-apply.sh verify <packdir>"; cmd_verify "$1" ;;
  apply)  shift; [ $# -ge 1 ] || refuse "usage: gate-apply.sh apply <packdir>";  cmd_apply "$1" ;;
  watch)  cmd_watch ;;
  *) echo "usage: gate-apply.sh {verify|apply|watch} [packdir]" >&2; exit 2 ;;
esac
