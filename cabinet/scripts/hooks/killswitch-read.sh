#!/bin/bash
# killswitch-read.sh — THE one emergency-stop reader for the whole cabinet.
#
# WHY THIS FILE EXISTS (incident 2026-07-25, adversarial audit):
# every reader used to decide "the switch is clear" by testing
# `[ "$answer" = "active" ]`. Measured against redis 8.8, `redis-cli GET`
# prints the ERROR TEXT ON STDOUT AND EXITS 0 for all of:
#   * NOAUTH  — `CONFIG SET requirepass X`      -> "NOAUTH Authentication required."
#   * NOPERM  — `ACL SETUSER default -get`      -> "NOPERM ... 'get' command"
#   * WRONGTYPE — `LPUSH cabinet:killswitch x`  -> "WRONGTYPE Operation against..."
#   * LOADING — any restart replaying an AOF    -> "LOADING Redis is loading..."
# so ONE allowed command silently disabled the Captain's emergency stop while
# every status surface printed "INACTIVE". Absence of the literal string
# "active" is NOT evidence of a clear switch — it is the absence of evidence.
#
# THE CONTRACT (inverted default): only a DEFINITIVE, AUTHENTICATED "the switch
# is clear" may permit action. Three verdicts:
#
#   CLEAR          proven: the control plane answered, authenticated, and the
#                  key is genuinely absent. ONLY this permits action.
#   ACTIVE         proven: the Captain armed the stop.
#   INDETERMINATE  anything else — auth error, permission error, wrong type,
#                  loading, timeout, refused connection, missing redis-cli,
#                  malformed frame, unrecognised value.
#
# INDETERMINATE MUST BEHAVE EXACTLY LIKE ACTIVE for anything that acts, and be
# REPORTED DISTINCTLY to the Captain — he has to be able to tell "stopped" from
# "I cannot tell", and must never be shown "inactive" for either.
#
# WHY IT LIVES IN cabinet/scripts/hooks/: that directory is schg-locked as a
# whole (germline-lock.sh DIRS, `chflags -R schg`), so this file inherits the
# lock with NO change to the germline set. A helper anywhere else would be
# officer-writable, and moving the emergency stop's decision into a writable
# file would be strictly worse than the bug it fixes.
#
# HOW THE READ PROVES ITSELF (one round trip, nonce sandwich):
#   printf 'ECHO <n1>\nGET cabinet:killswitch\nECHO <n2>\n' | redis-cli ...
# Measured byte-exact replies:
#   healthy, key absent  -> "<n1>\n\n<n2>"                    3 lines, mid ""
#   healthy, armed       -> "<n1>\nactive\n<n2>"              3 lines, mid "active"
#   NOPERM on get        -> "<n1>\nNOPERM ...\n\n<n2>"        4 lines  -> INDETERMINATE
#   NOAUTH               -> first line is the error, not <n1> -> INDETERMINATE
#   connection refused   -> first line is the error, not <n1> -> INDETERMINATE
# An error reply always costs an extra line, and a NOAUTH/refused server cannot
# echo the nonce at all, so "3 lines AND first==n1 AND last==n2" is a positive
# proof that a live, authenticated server answered THIS GET. The nonces are
# fresh per invocation, so a value stored in the key cannot forge the frame.
#
# SECOND CHANNEL (the pre-armed-DEL-loop mitigation): a filesystem marker,
# default instance/config/estop. kill-switch.sh writes it BEFORE the Redis SET
# and removes it on a verified deactivate, so a
# `while :; do redis-cli DEL cabinet:killswitch; done` loop — which never
# touches the filesystem — no longer clears the stop. The verdict is the OR of
# both channels: the marker present in ANY form can only ever raise the alarm,
# never lower it. NOT ARMED BY DEFAULT: `kill-switch.sh activate` writes only
# the Redis key today, so the loop above still wins — the mechanism is built and
# test-pinned but switching it on changes the watchdog's contract and needs a
# Captain ruling. Tracked as RES-016 in docs/plans/declared-residuals-register.md,
# which also records the honest limit (a same-uid adversary can `rm` the marker).
#
# USAGE
#   source .../killswitch-read.sh; killswitch_read; echo "$KS_VERDICT $KS_REASON"
#   bash   .../killswitch-read.sh            # prints "VERDICT<TAB>reason"
# Exit codes (script form): 0 = CLEAR, 10 = ACTIVE, 11 = INDETERMINATE.
# Exit 0 ONLY on CLEAR, so a missing, unreadable or crashed helper is
# fail-closed by construction for any caller that gates on rc 0.
#
# bash 3.2 compatible (macOS system bash). No arrays-of-assoc, no mapfile.

KILLSWITCH_KEY="${KILLSWITCH_KEY:-cabinet:killswitch}"

# Resolve the control-plane endpoint the SAME way for every reader. Before this
# helper, pre-tool-use.sh honoured REDIS_HOST/REDIS_PORT while kill-switch.sh
# honoured only REDIS_URL — so on any non-default port the hook and the status
# verb read DIFFERENT servers (found while reproducing this incident).
_ks_endpoint() {
  if [ -n "${REDIS_HOST:-}" ] || [ -n "${REDIS_PORT:-}" ]; then
    _KS_HOST="${REDIS_HOST:-127.0.0.1}"
    _KS_PORT="${REDIS_PORT:-6379}"
  elif [ -n "${REDIS_URL:-}" ]; then
    _KS_HOST=$(printf '%s' "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
    _KS_PORT=$(printf '%s' "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)
    _KS_HOST="${_KS_HOST:-127.0.0.1}"
    _KS_PORT="${_KS_PORT:-6379}"
  else
    _KS_HOST="127.0.0.1"
    _KS_PORT="6379"
  fi
  # docker-legacy residue: a bare `redis` hostname never resolves on the
  # Mac-native fleet (mirrors cabinet-doctor.sh / kill-switch.sh).
  [ "$_KS_HOST" = "redis" ] && _KS_HOST=127.0.0.1
  return 0
}

_ks_marker_path() {
  if [ -n "${CABINET_ESTOP_MARKER:-}" ]; then printf '%s' "$CABINET_ESTOP_MARKER"; return 0; fi
  local root="${CABINET_ROOT:-}"
  if [ -z "$root" ]; then
    root="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/../../.." 2>/dev/null && pwd)"
  fi
  printf '%s' "${root}/instance/config/estop"
}

# CLEAR | ACTIVE | INDETERMINATE for the filesystem channel. Existence in ANY
# form (symlink, directory, unreadable file, unexpected content) is never CLEAR:
# a marker we cannot read is a stop we cannot rule out.
_ks_marker_verdict() {
  local m content
  m="$(_ks_marker_path)"
  if [ ! -e "$m" ] && [ ! -L "$m" ]; then
    _KS_M_VERDICT=CLEAR; _KS_M_REASON=""; return 0
  fi
  if [ -f "$m" ] && [ ! -L "$m" ]; then
    content=$(tr -d '[:space:]' < "$m" 2>/dev/null)
    if [ "$content" = "active" ]; then
      _KS_M_VERDICT=ACTIVE; _KS_M_REASON="stop marker armed ($m)"; return 0
    fi
    _KS_M_VERDICT=INDETERMINATE
    _KS_M_REASON="stop marker present but unreadable/unexpected content ($m)"
    return 0
  fi
  _KS_M_VERDICT=INDETERMINATE
  _KS_M_REASON="stop marker present but not a regular file ($m)"
  return 0
}

# CLEAR | ACTIVE | INDETERMINATE for the Redis channel.
_ks_redis_verdict() {
  local n1 n2 raw nlines l1 l2 l3 probe rc err
  _ks_endpoint

  if ! command -v redis-cli >/dev/null 2>&1; then
    _KS_R_VERDICT=INDETERMINATE; _KS_R_REASON="redis-cli not found on PATH"; return 0
  fi

  n1=$(dd if=/dev/urandom bs=8 count=1 2>/dev/null | od -An -tx1 | tr -d ' \n')
  n2=$(dd if=/dev/urandom bs=8 count=1 2>/dev/null | od -An -tx1 | tr -d ' \n')
  if [ -z "$n1" ] || [ -z "$n2" ] || [ "$n1" = "$n2" ]; then
    _KS_R_VERDICT=INDETERMINATE; _KS_R_REASON="could not mint a read nonce"; return 0
  fi

  probe=$(printf 'ECHO %s\nGET %s\nECHO %s\n' "$n1" "$KILLSWITCH_KEY" "$n2")

  # `-t` bounds the connect phase so a WEDGED server cannot hang every officer's
  # tool call. PORTABILITY: not every redis-cli build honours -t (redis-tools
  # 7.0.x errors on the flag itself). A flag-parse error is retried WITHOUT -t
  # against a perfectly reachable server; a genuine outage never matches that
  # pattern and stays INDETERMINATE.
  raw=$(printf '%s\n' "$probe" | redis-cli -t 2 -h "$_KS_HOST" -p "$_KS_PORT" 2>&1)
  rc=$?
  err=$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')
  case "$err" in
    *unrecognized\ option*|*unknown\ option*|*bad\ number\ of\ args*|*invalid\ option*|*ambiguous*)
      raw=$(printf '%s\n' "$probe" | redis-cli -h "$_KS_HOST" -p "$_KS_PORT" 2>&1)
      rc=$?
      ;;
  esac

  nlines=$(printf '%s\n' "$raw" | wc -l | tr -d ' ')
  l1=$(printf '%s\n' "$raw" | sed -n '1p')
  l2=$(printf '%s\n' "$raw" | sed -n '2p')
  l3=$(printf '%s\n' "$raw" | sed -n '3p')

  if [ "$nlines" != "3" ] || [ "$l1" != "$n1" ] || [ "$l3" != "$n2" ]; then
    _KS_R_VERDICT=INDETERMINATE
    _KS_R_REASON="control plane at ${_KS_HOST}:${_KS_PORT} did not answer a verifiable read (rc=$rc): $(printf '%s' "$raw" | tr '\n' ' ' | cut -c1-120)"
    return 0
  fi
  # From here the frame is PROVEN: a live, authenticated server echoed both
  # fresh nonces around this GET, so line 2 is genuinely this key's value.
  case "$l2" in
    active) _KS_R_VERDICT=ACTIVE;  _KS_R_REASON="cabinet:killswitch = active" ;;
    "")     _KS_R_VERDICT=CLEAR;   _KS_R_REASON="verified clear at ${_KS_HOST}:${_KS_PORT}" ;;
    *)      _KS_R_VERDICT=INDETERMINATE
            _KS_R_REASON="cabinet:killswitch holds an unrecognised value ($(printf '%s' "$l2" | cut -c1-40))" ;;
  esac
  return 0
}

# Public entry point. Sets KS_VERDICT + KS_REASON; returns 0/10/11.
killswitch_read() {
  _ks_marker_verdict
  # Fast path AND hard latch: an armed marker needs no round trip, so the stop
  # still reads ACTIVE even when the control plane is being fought over.
  if [ "$_KS_M_VERDICT" = "ACTIVE" ]; then
    KS_VERDICT=ACTIVE; KS_REASON="$_KS_M_REASON"; return 10
  fi
  _ks_redis_verdict
  if [ "$_KS_R_VERDICT" = "ACTIVE" ]; then
    KS_VERDICT=ACTIVE; KS_REASON="$_KS_R_REASON"; return 10
  fi
  if [ "$_KS_M_VERDICT" = "INDETERMINATE" ] || [ "$_KS_R_VERDICT" = "INDETERMINATE" ]; then
    KS_VERDICT=INDETERMINATE
    if [ "$_KS_M_VERDICT" = "INDETERMINATE" ] && [ "$_KS_R_VERDICT" = "INDETERMINATE" ]; then
      KS_REASON="$_KS_M_REASON; $_KS_R_REASON"
    elif [ "$_KS_M_VERDICT" = "INDETERMINATE" ]; then
      KS_REASON="$_KS_M_REASON"
    else
      KS_REASON="$_KS_R_REASON"
    fi
    return 11
  fi
  KS_VERDICT=CLEAR; KS_REASON="$_KS_R_REASON"
  return 0
}

# Script form — used by callers in other languages (python/swift shell out) and
# by the tests. One line: "VERDICT<TAB>reason".
if [ "${BASH_SOURCE[0]:-$0}" = "$0" ]; then
  killswitch_read
  _ks_rc=$?
  printf '%s\t%s\n' "$KS_VERDICT" "$KS_REASON"
  exit "$_ks_rc"
fi
