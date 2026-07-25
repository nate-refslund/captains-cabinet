#!/bin/bash
# kill-switch.sh — Emergency halt / resume for all Officers
# Usage: kill-switch.sh activate | deactivate | status
#
# FAIL-CLOSED CONTRACT (2026-07-11 hardening-loop finding, ceremony patch):
# an emergency surface must never report success it cannot prove, and never
# report safe-to-proceed when the control plane is unreachable.
#   activate   — SET is rc-checked AND read back; anything short of a
#                verified "active" prints FAILURE to stderr and exits 1.
#   deactivate — DEL rc-checked + read-back proves the key is gone.
#   status     — control plane unreadable => "STOPPED — CANNOT VERIFY"
#                and exit 2 (never a false INACTIVE; callers gate on rc 0).
#   default    — 127.0.0.1, not the docker-DNS name `redis` (the same
#                gotcha pre-tool-use.sh:18-21 already guards hook-side;
#                the env-derived host still honors REDIS_URL overrides).
#
# INVERTED DEFAULT + SECOND CHANNEL (2026-07-25 adversarial audit). Two bugs
# were found here, both of which made the Captain's phone say INACTIVE while
# the fleet kept working:
#   1. `status` proved reachability with PING and then compared GET's answer to
#      the literal "active". Measured on redis 8.8, `CONFIG SET requirepass X`
#      makes PING itself answer "NOAUTH Authentication required." WITH EXIT 0 —
#      so the reachability probe passed, the GET returned error text, the
#      comparison failed, and the verb printed INACTIVE. `ACL SETUSER default
#      -get` (PING still PONGs), `LPUSH cabinet:killswitch x` (WRONGTYPE) and a
#      restart replaying an AOF (LOADING) did the same. The read now goes
#      through the one shared helper (cabinet/scripts/hooks/killswitch-read.sh),
#      which only reports CLEAR on a definitive AUTHENTICATED clear read.
#   2. Endpoint drift: this script honoured only REDIS_URL while every hook
#      honours REDIS_HOST/REDIS_PORT first — so on any non-default port the
#      Captain's status verb and the officers' gate read DIFFERENT servers.
#      The helper's _ks_endpoint is now the single resolver for both.
#
# THE STOP MARKER (second channel — READ here, NOT armed by default).
# The shared reader also honours a filesystem stop marker (instance/config/estop,
# or CABINET_ESTOP_MARKER). It exists for the pre-armed-clearing-loop class:
# `while :; do redis-cli DEL cabinet:killswitch; sleep 1; done` clears the Redis
# channel within a second of every arming but never touches the filesystem, so a
# stop carried on BOTH channels survives it. `deactivate` clears the marker, so
# a Captain who arms it by hand can still resume through the normal verb.
#
# DECLARED RESIDUAL (RES-016) — activate does NOT arm the marker yet, so the
# pre-armed clearing loop still wins. This is deliberate and needs a Captain
# call: arming a durable filesystem latch changes the emergency stop's
# contract — killswitch-watchdog.py exists precisely to re-arm a switch that a
# raw DEL cleared, and with a latch that scenario stops being reachable through
# Redis alone. That is a governance change, not a bug fix, and it belongs in a
# ruling rather than inside a fail-closed patch. DEFECT 2 IS THEREFORE OPEN:
# the mechanism is built and tested (the reader honours the marker), but nothing
# arms the second channel automatically.
#
# EXIT CODES (unchanged, several consumers depend on them):
#   status: 0 = a definitive read (ACTIVE or INACTIVE), 2 = cannot verify.
#   cabinet-doctor.sh gates on rc; framework/comms/surface/killswitch_card.py
#   maps rc!=0 to its UNKNOWN state; hatch.sh greps the two definitive lines.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"

# THE one reader. Absolute path into the schg-locked hooks directory, never via
# PATH, so the helper cannot be shimmed. Missing helper => refuse everything.
KS_HELPER="$SCRIPT_DIR/hooks/killswitch-read.sh"
if [ ! -r "$KS_HELPER" ]; then
  echo "kill-switch.sh: FATAL — the shared emergency-stop reader is missing at $KS_HELPER; refusing to report or flip a switch this script cannot read." >&2
  exit 2
fi
# shellcheck source=/dev/null
. "$KS_HELPER"

_ks_endpoint
REDIS_HOST="$_KS_HOST"
REDIS_PORT="$_KS_PORT"
ESTOP_MARKER="$(_ks_marker_path)"

ACTION="${1:?Usage: kill-switch.sh activate|deactivate|status}"

# AUDIT TRAIL (2026-07-17 amendment, Wave-1 e2): every VERIFIED flip of the
# emergency stop leaves a ledger row (kill_switch_activated/_deactivated), so
# the switch's history is attributable — the incident: the 2026-07-15 lockdown
# read INACTIVE on 07-16 and no record could say which actor cleared it.
# Fail-quiet BY DESIGN: the ledger must never block, slow, or fail the
# emergency surface itself (`|| true`, output discarded — mirrors
# on-subagent-stop.sh). Emits only on the VERIFIED branches: an unverified
# flip is already a loud failure, and a false "activated" row would be worse
# than none. Direct redis-cli flips bypass this by nature — the sanctioned
# surfaces are this script and the Chair path that shells to it.
emit_flip_event() {
  python3 "$CABINET_ROOT/framework/events/emitter.py" "$1" \
    "${CABINET_OFFICER:-captain}" \
    '{"killswitch_id":"cabinet:killswitch","via":"kill-switch.sh"}' \
    > /dev/null 2>&1 || true
}

case "$ACTION" in
  activate)
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET cabinet:killswitch active > /dev/null 2>&1
    killswitch_read
    # killswitch_read short-circuits on an armed marker, so ask the Redis
    # channel explicitly — the two are reported separately below.
    _ks_redis_verdict
    if [ "$KS_VERDICT" = "ACTIVE" ]; then
      echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') — KILL SWITCH ACTIVATED (verified by read-back)"
      echo "All Officer operations will halt on their next tool invocation."
      # The Redis channel is reported separately from the combined verdict: if
      # a stop marker is what is holding the halt, the Captain must know the
      # control plane did not take the write (surfaces that read Redis
      # directly would still show the fleet as running).
      [ "$_KS_R_VERDICT" != "ACTIVE" ] && echo "WARNING: the control plane at ${REDIS_HOST}:${REDIS_PORT} did NOT take the stop ($_KS_R_VERDICT: $_KS_R_REASON)." >&2
      emit_flip_event kill_switch_activated
    else
      echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') — KILL SWITCH ACTIVATION FAILED: could not verify the stop is armed ($KS_VERDICT: $KS_REASON)." >&2
      echo "Officers are NOT provably halted. Escalate: stop launchd jobs directly (launchctl bootout) or fix Redis, then re-run." >&2
      exit 1
    fi
    ;;
  deactivate)
    rm -f "$ESTOP_MARKER" 2>/dev/null
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DEL cabinet:killswitch > /dev/null 2>&1
    killswitch_read
    if [ "$KS_VERDICT" = "CLEAR" ]; then
      echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') — KILL SWITCH DEACTIVATED (verified by read-back)"
      echo "Officers will resume normal operation."
      emit_flip_event kill_switch_deactivated
    else
      echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') — KILL SWITCH DEACTIVATION UNVERIFIED ($KS_VERDICT: $KS_REASON)." >&2
      echo "The switch may still be ACTIVE. Fix the control plane, then re-run." >&2
      exit 1
    fi
    ;;
  status)
    killswitch_read
    case "$KS_VERDICT" in
      ACTIVE)
        echo "Kill switch: ACTIVE (all operations halted) — $KS_REASON"
        ;;
      CLEAR)
        echo "Kill switch: INACTIVE (normal operation)"
        ;;
      *)
        # NEVER "inactive", and never a bare "unknown" that reads as benign:
        # the Captain must be able to tell "stopped" from "I cannot tell", and
        # both mean nothing may act.
        echo "Kill switch: STOPPED — CANNOT VERIFY ($KS_REASON). Every gate treats this exactly like ACTIVE; nothing is permitted to act until the switch can be read."
        exit 2
        ;;
    esac
    ;;
  *)
    echo "Usage: kill-switch.sh activate|deactivate|status"
    exit 1
    ;;
esac
