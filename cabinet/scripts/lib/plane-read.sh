#!/bin/bash
# plane-read.sh — THE proven read for every control-plane VALUE the cabinet
# reports on. One implementation, not a second dialect.
#
# WHY THIS FILE EXISTS (incident 2026-07-26, control-plane fail-open sweep):
# `cabinet/cron/cost-summary.sh` read the day's spend with
#
#     DAILY_MICRO=$(redis-cli ... HGET ... 2>/dev/null)
#     [[ "$DAILY_MICRO" =~ ^[0-9]+$ ]] || DAILY_MICRO=0
#
# and with the control plane unreachable sent the Captain's group
# `💰 Total: $0.00`, exit 0, stderr empty — proven byte-identical to a true
# zero-spend day. The outage rendered as a LEGITIMATE BUSINESS RESULT.
#
# That is the shape, not the instance: a value read through `2>/dev/null` and
# coerced to its type's identity element (`0`, `""`, absent) — WHICH IS ALSO A
# VALID ANSWER. `|| echo 0` is the same bug written shorter. The reader cannot
# tell "I read a zero" from "I could not read", and neither can anyone
# downstream, because both render the same bytes.
#
# THE CONTRACT (three outcomes, never two):
#
#   VALUE          proven: a live server answered THIS read and returned a
#                  payload. `PLANE_VALUE` is genuinely that key's content.
#   ABSENT         proven: a live server answered THIS read and the key/field
#                  is genuinely unset (empty reply). This — and ONLY this — is
#                  the legitimate business zero.
#   INDETERMINATE  anything else: refused connection, timeout, NOAUTH, NOPERM,
#                  WRONGTYPE, LOADING, missing redis-cli, malformed frame,
#                  unparseable payload. NOT a zero. NOT an empty. A caller that
#                  cannot source a number MUST NOT print one.
#
# HOW THE READ PROVES ITSELF (one round trip, nonce sandwich) — the discipline
# is lifted verbatim from cabinet/scripts/hooks/killswitch-read.sh, which
# proved it against redis 8.8:
#
#     printf 'ECHO <n1>\n<CMD...>\nECHO <n2>\n' | redis-cli ...
#
# `redis-cli` prints error text ON STDOUT AND EXITS 0 for NOAUTH / NOPERM /
# WRONGTYPE / LOADING, so neither the exit code nor "the output looked empty"
# is evidence. But an error reply always costs an EXTRA line, and a NOAUTH or
# refused server cannot echo the nonce at all — so "first line == n1 AND last
# line == n2 AND the payload has the expected line count" is positive proof
# that a live, authenticated server answered THIS command. The nonces are
# fresh per invocation, so a value stored IN the key cannot forge the frame.
#
# WHY NOT IN cabinet/scripts/hooks/ (the schg-locked dir killswitch-read.sh
# lives in): the emergency stop's verdict must be unforgeable because forging
# it PERMITS AN ACT. This helper only decides whether a REPORT may print a
# number; an officer who wanted to hide spend would edit cost-summary.sh — not
# germline either — so locking the helper alone buys nothing while making every
# future repair need a Captain ceremony. If that calculus ever changes it is a
# one-line addition to germline-lock.sh FILES[] (cabinet/scripts/lib/ already
# carries three locked members), with no move.
#
# USAGE
#   . "$CABINET_ROOT/cabinet/scripts/lib/plane-read.sh"
#   plane_read_int HGET cabinet:cost:tokens:daily:2026-07-26 cos_cost_micro
#   case "$PLANE_VERDICT" in
#     VALUE)         use "$PLANE_VALUE" ;;
#     ABSENT)        genuinely nothing recorded — the real zero ;;
#     INDETERMINATE) report unavailable, print NO number, "$PLANE_REASON" ;;
#   esac
#
# Exit codes (also the function return codes): 0 = VALUE, 1 = ABSENT,
# 11 = INDETERMINATE. Exit 0 ONLY on a proven payload, so a missing or crashed
# helper is fail-closed for any caller that gates on rc 0. 11 matches
# killswitch-read.sh's INDETERMINATE code deliberately — one vocabulary.
#
# bash 3.2 compatible (macOS system bash). No mapfile, no assoc arrays.

# Pre-declare the result variables. Callers run under `set -u`, and a read that
# never happened must leave a readable (empty) verdict rather than an unbound
# fatal — a crash on the error path is its own kind of fail-open.
PLANE_VERDICT="${PLANE_VERDICT:-}"
PLANE_VALUE="${PLANE_VALUE:-}"
PLANE_REASON="${PLANE_REASON:-}"
PLANE_LINES="${PLANE_LINES:-0}"

# Endpoint resolution — IDENTICAL precedence to killswitch-read.sh, so a
# non-default port can never make two readers talk to two different servers
# (the bug that hid a disabled emergency stop, 2026-07-25).
_plane_endpoint() {
  if [ -n "${REDIS_HOST:-}" ] || [ -n "${REDIS_PORT:-}" ]; then
    _PLANE_HOST="${REDIS_HOST:-127.0.0.1}"
    _PLANE_PORT="${REDIS_PORT:-6379}"
  elif [ -n "${REDIS_URL:-}" ]; then
    _PLANE_HOST=$(printf '%s' "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
    _PLANE_PORT=$(printf '%s' "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2)
    _PLANE_HOST="${_PLANE_HOST:-127.0.0.1}"
    _PLANE_PORT="${_PLANE_PORT:-6379}"
  else
    _PLANE_HOST="127.0.0.1"
    _PLANE_PORT="6379"
  fi
  # docker-legacy residue: a bare `redis` hostname never resolves on the
  # Mac-native fleet (mirrors killswitch-read.sh / cabinet-doctor.sh).
  [ "$_PLANE_HOST" = "redis" ] && _PLANE_HOST=127.0.0.1
  return 0
}

# Redis error replies that arrive as TEXT with rc 0. Any of these appearing as
# a payload line means the command did not execute — never a value.
_plane_line_is_error() {
  case "$1" in
    ERR\ *|WRONGTYPE\ *|NOAUTH\ *|NOPERM\ *|LOADING\ *|BUSYGROUP\ *|NOGROUP\ *|\
MOVED\ *|ASK\ *|CLUSTERDOWN\ *|TRYAGAIN\ *|CROSSSLOT\ *|MASTERDOWN\ *|\
READONLY\ *|MISCONF\ *|NOSCRIPT\ *|OOM\ *|EXECABORT\ *|NOREPLICAS\ *|\
UNBLOCKED\ *|NOPROTO\ *|WRONGPASS\ *)
      return 0 ;;
  esac
  return 1
}

# The one round trip. Sets _PLANE_RAW / _PLANE_FRAME_OK / _PLANE_PAYLOAD /
# _PLANE_NLINES (payload line count) / _PLANE_RC.
_plane_probe() {
  local n1 n2 raw rc err nlines total _a
  _plane_endpoint

  # The probe speaks redis-cli's INLINE protocol (one command per line), which
  # splits on whitespace. An argument carrying a space or newline would be
  # re-split into a DIFFERENT command than the caller asked for — so refuse it
  # rather than issue it. Every cabinet key/field is whitespace-free; this is
  # the fail-closed guard for the day one is not.
  for _a in "$@"; do
    case "$_a" in
      *[![:graph:]]*|"")
        _PLANE_FRAME_OK=0
        _PLANE_REASON_RAW="refusing to issue '$*' — an argument carries whitespace or is empty, which the inline protocol would re-split"
        return 0 ;;
    esac
  done

  if ! command -v redis-cli >/dev/null 2>&1; then
    _PLANE_FRAME_OK=0
    _PLANE_REASON_RAW="redis-cli not found on PATH"
    return 0
  fi

  n1=$(dd if=/dev/urandom bs=8 count=1 2>/dev/null | od -An -tx1 | tr -d ' \n')
  n2=$(dd if=/dev/urandom bs=8 count=1 2>/dev/null | od -An -tx1 | tr -d ' \n')
  if [ -z "$n1" ] || [ -z "$n2" ] || [ "$n1" = "$n2" ]; then
    _PLANE_FRAME_OK=0
    _PLANE_REASON_RAW="could not mint a read nonce"
    return 0
  fi

  # `-t` bounds the connect phase so a WEDGED server cannot hang a cron job.
  # PORTABILITY: not every redis-cli build honours -t (redis-tools 7.0.x errors
  # on the flag itself); a flag-parse error is retried WITHOUT it. A genuine
  # outage never matches that pattern and stays INDETERMINATE.
  raw=$( { printf 'ECHO %s\n' "$n1"
           printf '%s\n' "$*"
           printf 'ECHO %s\n' "$n2"; } \
         | redis-cli -t "${PLANE_READ_TIMEOUT_S:-5}" -h "$_PLANE_HOST" -p "$_PLANE_PORT" 2>&1 )
  rc=$?
  err=$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')
  case "$err" in
    *unrecognized\ option*|*unknown\ option*|*bad\ number\ of\ args*|*invalid\ option*|*ambiguous*)
      raw=$( { printf 'ECHO %s\n' "$n1"
               printf '%s\n' "$*"
               printf 'ECHO %s\n' "$n2"; } \
             | redis-cli -h "$_PLANE_HOST" -p "$_PLANE_PORT" 2>&1 )
      rc=$?
      ;;
  esac

  _PLANE_RAW="$raw"
  _PLANE_RC="$rc"
  total=$(printf '%s\n' "$raw" | wc -l | tr -d ' ')
  # Frame proof: >=2 lines, first == n1, last == n2. Everything strictly
  # between the nonces is this command's reply.
  if [ "$total" -lt 2 ] \
     || [ "$(printf '%s\n' "$raw" | sed -n '1p')" != "$n1" ] \
     || [ "$(printf '%s\n' "$raw" | sed -n "${total}p")" != "$n2" ]; then
    _PLANE_FRAME_OK=0
    _PLANE_REASON_RAW="control plane at ${_PLANE_HOST}:${_PLANE_PORT} did not answer a verifiable read (rc=$rc): $(printf '%s' "$raw" | tr '\n' ' ' | cut -c1-120)"
    return 0
  fi

  nlines=$(( total - 2 ))
  if [ "$nlines" -le 0 ]; then
    _PLANE_PAYLOAD=""
    _PLANE_NLINES=0
  else
    _PLANE_PAYLOAD=$(printf '%s\n' "$raw" | sed -n "2,$(( total - 1 ))p")
    _PLANE_NLINES="$nlines"
  fi
  _PLANE_FRAME_OK=1
  _PLANE_REASON_RAW=""
  return 0
}

_plane_indeterminate() {
  PLANE_VERDICT=INDETERMINATE
  PLANE_VALUE=""
  PLANE_REASON="$1"
  return 11
}

# plane_read <redis command and args...> — SCALAR read (GET / HGET / EXISTS /
# XLEN / PING / INCR ...). The reply must be exactly one payload line.
#
# VALUE  -> PLANE_VALUE is that line (non-empty, not an error reply)
# ABSENT -> the server answered and the reply was empty (nil / unset key)
# INDETERMINATE -> anything else, INCLUDING a multi-line reply where one was
#                  not expected (an error reply costs the extra line, which is
#                  exactly how NOPERM is caught).
plane_read() {
  _PLANE_FRAME_OK=0; _PLANE_PAYLOAD=""; _PLANE_NLINES=0; _PLANE_REASON_RAW=""
  _plane_probe "$@"
  if [ "$_PLANE_FRAME_OK" != "1" ]; then
    _plane_indeterminate "$_PLANE_REASON_RAW"; return 11
  fi
  if [ "$_PLANE_NLINES" -gt 1 ]; then
    _plane_indeterminate "scalar read '$*' returned ${_PLANE_NLINES} lines at ${_PLANE_HOST}:${_PLANE_PORT} (error reply or wrong type): $(printf '%s' "$_PLANE_PAYLOAD" | tr '\n' ' ' | cut -c1-120)"
    return 11
  fi
  if _plane_line_is_error "$_PLANE_PAYLOAD"; then
    _plane_indeterminate "control plane refused '$*' at ${_PLANE_HOST}:${_PLANE_PORT}: $(printf '%s' "$_PLANE_PAYLOAD" | cut -c1-120)"
    return 11
  fi
  if [ -z "$_PLANE_PAYLOAD" ]; then
    PLANE_VERDICT=ABSENT
    PLANE_VALUE=""
    PLANE_REASON="verified absent at ${_PLANE_HOST}:${_PLANE_PORT}"
    return 1
  fi
  PLANE_VERDICT=VALUE
  PLANE_VALUE="$_PLANE_PAYLOAD"
  PLANE_REASON="verified read at ${_PLANE_HOST}:${_PLANE_PORT}"
  return 0
}

# plane_read_int <redis command and args...> — the direct replacement for
#   X=$(redis-cli ... 2>/dev/null || echo 0)      and
#   X=$(redis-cli ... 2>/dev/null); [[ $X =~ ^[0-9]+$ ]] || X=0
# A payload that is not an integer is INDETERMINATE, never 0: a counter that
# came back as prose is a broken read, not an empty counter.
plane_read_int() {
  plane_read "$@"
  case "$PLANE_VERDICT" in
    ABSENT) return 1 ;;
    VALUE)  : ;;
    *)      return 11 ;;
  esac
  # Strict integer test (bash 3.2 safe): optional leading '-', then digits only.
  local _digits="${PLANE_VALUE#-}"
  if [ -n "$_digits" ] && [ -z "$(printf '%s' "$_digits" | tr -d '0-9')" ]; then
    return 0
  fi
  _plane_indeterminate "expected an integer from '$*' at ${_PLANE_HOST}:${_PLANE_PORT}, got: $(printf '%s' "$PLANE_VALUE" | cut -c1-60)"
  return 11
}

# plane_read_lines <redis command and args...> — MULTI-line read (HGETALL /
# KEYS / SMEMBERS / LRANGE). PLANE_VALUE is the newline-joined payload;
# PLANE_LINES is its line count. An empty reply is ABSENT (the collection is
# genuinely empty); ANY payload line that is a redis error reply makes the
# whole read INDETERMINATE.
plane_read_lines() {
  _PLANE_FRAME_OK=0; _PLANE_PAYLOAD=""; _PLANE_NLINES=0; _PLANE_REASON_RAW=""
  PLANE_LINES=0
  _plane_probe "$@"
  if [ "$_PLANE_FRAME_OK" != "1" ]; then
    _plane_indeterminate "$_PLANE_REASON_RAW"; return 11
  fi
  local _l
  while IFS= read -r _l; do
    if _plane_line_is_error "$_l"; then
      _plane_indeterminate "control plane refused '$*' at ${_PLANE_HOST}:${_PLANE_PORT}: $(printf '%s' "$_l" | cut -c1-120)"
      return 11
    fi
  done <<EOF
$_PLANE_PAYLOAD
EOF
  # An EMPTY collection comes back as a single blank payload line, not as zero
  # lines — so "no lines" and "one blank line" are the same observation and both
  # mean the key holds nothing. (Measured: `HGETALL <missing>` frames as
  # n1/""/n2.) A real multi-line reply always carries content.
  if [ "$_PLANE_NLINES" -eq 0 ] || [ -z "$_PLANE_PAYLOAD" ]; then
    PLANE_VERDICT=ABSENT; PLANE_VALUE=""; PLANE_LINES=0
    PLANE_REASON="verified empty at ${_PLANE_HOST}:${_PLANE_PORT}"
    return 1
  fi
  PLANE_VERDICT=VALUE
  PLANE_VALUE="$_PLANE_PAYLOAD"
  PLANE_LINES="$_PLANE_NLINES"
  PLANE_REASON="verified read at ${_PLANE_HOST}:${_PLANE_PORT}"
  return 0
}

# plane_reachable — proven reachability with no key involved. VALUE("PONG") or
# INDETERMINATE. Callers that report an AGGREGATE (a digest, a total) prove the
# plane once up front, so an outage produces ONE honest "unavailable" line
# instead of N innocent-looking zeroes.
plane_reachable() {
  plane_read PING
  if [ "$PLANE_VERDICT" = "VALUE" ] && [ "$PLANE_VALUE" = "PONG" ]; then
    return 0
  fi
  if [ "$PLANE_VERDICT" != "INDETERMINATE" ]; then
    _plane_indeterminate "PING to ${_PLANE_HOST}:${_PLANE_PORT} answered '${PLANE_VALUE}', not PONG"
    return 11
  fi
  return 11
}

# The endpoint the last read used — for honest "unavailable at host:port" copy.
plane_endpoint_str() { _plane_endpoint; printf '%s:%s' "$_PLANE_HOST" "$_PLANE_PORT"; }

# Script form — for callers in other languages and for the tests.
# Prints "VERDICT<TAB>value<TAB>reason"; exit 0/1/11.
if [ "${BASH_SOURCE[0]:-$0}" = "$0" ]; then
  _plane_mode="${1:-}"
  case "$_plane_mode" in
    --int)   shift; plane_read_int "$@" ;;
    --lines) shift; plane_read_lines "$@" ;;
    --ping)  plane_reachable ;;
    *)       plane_read "$@" ;;
  esac
  _plane_rc=$?
  printf '%s\t%s\t%s\n' "$PLANE_VERDICT" "$(printf '%s' "$PLANE_VALUE" | tr '\n' '|')" "$PLANE_REASON"
  exit "$_plane_rc"
fi
