#!/bin/bash
# evals-redis-sandbox.sh — throwaway Redis for the golden-eval suite (2026-07-17).
#
# WHY: run-golden-evals.sh resolves REDIS_HOST/PORT with a 127.0.0.1:6379
# default — on the live Mac that is the PRODUCTION Redis. EVAL-001 then
# `SET cabinet:killswitch active` mid-suite and the suite's cleanup trap
# `DEL cabinet:killswitch` UNCONDITIONALLY — so every FW-025 pre-push eval
# run momentarily ARMED the fleet emergency stop and then silently CLEARED
# it, including a killswitch the Captain had deliberately armed (the
# 2026-07-15 lockdown was found inactive on 07-16 with pushes in between —
# the clobber mechanism is real regardless of which actor cleared it).
# Tests must never touch the emergency stop.
#
# THE DECLARATION MUST PROVE ITSELF (2026-07-27). CABINET_EVALS_REDIS_DISPOSABLE=1
# used to be taken on trust: `return 0`, no check of any kind. An environment
# variable is a claim about the CALLER'S INTENT, not a property of the server —
# and it travels. Exported once in a shell, inherited by a child, copied from a
# CI recipe into a laptop's .env, and the suite that "must never touch a live
# Redis" is pointed straight at one, with a reassuring log line. Reproduced: with
# the flag set and the endpoint holding an ARMED cabinet:killswitch plus live
# fleet state, start() returned 0 and the suite's SET/DEL cleared the stop.
#
# So the declaration now has to be a property of the ENDPOINT, and it is checked
# before the suite may write anything:
#   1. the endpoint answers PING — an endpoint nobody can reach cannot be proven
#      to be anything;
#   2. cabinet:killswitch is ABSENT — the suite SETs and unconditionally DELs
#      that key, so running over an armed one destroys a Captain stop (the
#      2026-07-15 lockdown, found inactive on 07-16, is this exact shape); and
#   3. the endpoint itself carries the marker key cabinet:evals:disposable —
#      whoever provisions a throwaway declares it AT the throwaway. CI sets it
#      on its service container in one step. A stray env var can no longer
#      bless a server, because the server has to agree.
#
# HONEST LIMIT: (3) is a convention, not a cryptographic proof — someone who
# deliberately writes that marker onto a live control plane has declared it
# disposable and this code will believe them. What it removes is the ACCIDENT:
# an inherited variable, a copied recipe, a shell that kept a stale export.
#
# CONTRACT (sourced by run-golden-evals.sh; bash 3.2 compatible):
#   evals_redis_sandbox_start
#     * If CABINET_EVALS_REDIS_DISPOSABLE=1 — the caller declares the
#       ALREADY-RESOLVED endpoint throwaway (CI's redis:7 service container) —
#       PROVE that (see above) and return 0, or REFUSE with non-zero and let
#       the caller abort. It no longer returns 0 unconditionally.
#     * Otherwise spawn an ephemeral localhost redis-server (random high
#       port, no persistence, private tmp dir) and EXPORT the full endpoint
#       triple at it: REDIS_HOST + REDIS_PORT (every hook prefers these)
#       AND REDIS_URL defensively — the hooks fall back to deriving
#       host/port from the URL when HOST/PORT are absent, and a stale
#       inherited REDIS_URL must never be the thing a future refactor
#       resolves toward the live instance (endpoint-resolution drift
#       false-failed EVAL-001/008/015/016 on the first CI run).
#     * Returns non-zero WITHOUT exporting anything if the sandbox cannot
#       start (no redis-server binary / no free port) — the caller must
#       REFUSE to run rather than fall back to a possibly-live endpoint.
#   evals_redis_sandbox_stop
#     * Kill the spawned server + remove its tmp dir. Safe to call
#       unconditionally (no-op when nothing was spawned).
#
# The sandbox starts EMPTY — exactly the state CI's service container is in
# when the suite passes there, so emptiness is already a proven-green input.

_EVALS_SANDBOX_PID=""
_EVALS_SANDBOX_DIR=""

# The endpoint-side declaration. Provisioning a throwaway means SAYING SO AT
# THE THROWAWAY, so the claim cannot arrive by inheritance from somewhere else.
EVALS_DISPOSABLE_MARKER="cabinet:evals:disposable"

# The key the suite actually writes. Pinned to the literal `kill-switch.sh`
# hardcodes on BOTH its write paths, NOT to $KILLSWITCH_KEY — that variable
# steers only the READ, so honouring it here would check one key while
# run-golden-evals.sh SET/DELs another.
_EVALS_KILLSWITCH_KEY="cabinet:killswitch"

# Prove a declared-disposable endpoint really is one. Fail-closed: every exit
# path that is not a proof returns non-zero, and run-golden-evals.sh refuses.
evals_redis_endpoint_is_disposable() {
  local host port armed declared
  host="${REDIS_HOST:-127.0.0.1}"
  port="${REDIS_PORT:-6379}"

  if ! command -v redis-cli > /dev/null 2>&1; then
    echo "evals-redis-sandbox: redis-cli not found — cannot verify the declared-disposable endpoint at $host:$port" >&2
    return 1
  fi
  if ! redis-cli -h "$host" -p "$port" PING 2>/dev/null | grep -q PONG; then
    echo "evals-redis-sandbox: REFUSED — declared-disposable endpoint $host:$port did not answer PING." >&2
    echo "An endpoint that cannot be reached cannot be proven throwaway." >&2
    return 1
  fi

  # 1) Never run over an armed stop: the suite DELs this key unconditionally.
  armed=$(redis-cli -h "$host" -p "$port" EXISTS "$_EVALS_KILLSWITCH_KEY" 2>/dev/null)
  if [ "$armed" != "0" ]; then
    echo "evals-redis-sandbox: REFUSED — $_EVALS_KILLSWITCH_KEY is present at $host:$port" >&2
    echo "(EXISTS returned '$armed'). This suite SETs and then unconditionally DELs" >&2
    echo "that key, so running here would clear an emergency stop that something" >&2
    echo "or someone armed. Clearing it is Captain-side only." >&2
    return 1
  fi

  # 2) The endpoint must carry the declaration itself.
  declared=$(redis-cli -h "$host" -p "$port" EXISTS "$EVALS_DISPOSABLE_MARKER" 2>/dev/null)
  if [ "$declared" != "1" ]; then
    echo "evals-redis-sandbox: REFUSED — CABINET_EVALS_REDIS_DISPOSABLE=1 is set, but" >&2
    echo "$host:$port does not carry the marker key $EVALS_DISPOSABLE_MARKER, so nothing" >&2
    echo "about the ENDPOINT says it is a throwaway — only this process's environment" >&2
    echo "does, and that travels. If it really is disposable, declare it there:" >&2
    echo "  redis-cli -h $host -p $port SET $EVALS_DISPOSABLE_MARKER 1" >&2
    echo "Never do that against a real fleet's Redis. Otherwise unset the variable" >&2
    echo "and let this suite start its own ephemeral redis-server." >&2
    return 1
  fi
  return 0
}

evals_redis_sandbox_start() {
  if [ "${CABINET_EVALS_REDIS_DISPOSABLE:-}" = "1" ]; then
    evals_redis_endpoint_is_disposable || return 1
    echo "evals-redis-sandbox: endpoint PROVEN disposable (marker present, no armed stop) — using resolved ${REDIS_HOST:-127.0.0.1}:${REDIS_PORT:-6379}"
    return 0
  fi
  # Binary discovery mirrors fw-002-spending-limits.sh: launchd-flavored
  # shells carry a bare PATH, so fall back to the standard brew prefixes
  # and PATH-prepend the found dir (redis-cli ships alongside redis-server).
  local server_bin
  server_bin="$(command -v redis-server 2>/dev/null)"
  if [ -z "$server_bin" ]; then
    local _cand
    for _cand in /opt/homebrew/bin/redis-server /usr/local/bin/redis-server; do
      if [ -x "$_cand" ]; then server_bin="$_cand"; break; fi
    done
    [ -n "$server_bin" ] && PATH="$(dirname "$server_bin"):$PATH"
  fi
  if [ -z "$server_bin" ]; then
    echo "evals-redis-sandbox: redis-server binary not found — cannot sandbox" >&2
    return 1
  fi
  # Without redis-cli the PING-wait below can never see a PONG and would
  # burn the full port-retry budget before emitting a misleading error.
  if ! command -v redis-cli > /dev/null 2>&1; then
    echo "evals-redis-sandbox: redis-cli binary not found — cannot verify a sandbox" >&2
    return 1
  fi
  _EVALS_SANDBOX_DIR=$(mktemp -d "${TMPDIR:-/tmp}/evals-redis-sandbox.XXXXXX") || return 1
  # Physical path for the identity check below (macOS /tmp is a symlink to
  # /private/tmp; redis reports its dir resolved). MUST be non-empty — an
  # empty pattern would make the `grep -qF` identity check match anything.
  local sandbox_dir_phys
  sandbox_dir_phys="$(cd "$_EVALS_SANDBOX_DIR" && pwd -P)"
  if [ -z "$sandbox_dir_phys" ]; then
    rm -rf "$_EVALS_SANDBOX_DIR" 2>/dev/null
    _EVALS_SANDBOX_DIR=""
    return 1
  fi

  local attempt port
  attempt=0
  while [ "$attempt" -lt 10 ]; do
    attempt=$((attempt + 1))
    port=$((20000 + RANDOM % 20000))
    redis-server --port "$port" --bind 127.0.0.1 --save "" --appendonly no \
      --dir "$_EVALS_SANDBOX_DIR" --logfile "$_EVALS_SANDBOX_DIR/redis.log" \
      > /dev/null 2>&1 &
    _EVALS_SANDBOX_PID=$!

    # PING-wait ≤5s (0.1s steps). A suite-side redis-cli that fails silently
    # is the B4 tested-nothing class — verify liveness before proceeding.
    local tick
    tick=0
    while [ "$tick" -lt 50 ]; do
      # Our spawn must still be alive BEFORE a PONG is trusted: if the port
      # was already held, our server died on bind and the PONG would come
      # from the FOREIGN server — exporting the triple at it would aim the
      # suite's killswitch writes at a redis that is not the sandbox.
      if ! kill -0 "$_EVALS_SANDBOX_PID" 2>/dev/null; then
        break
      fi
      if redis-cli -h 127.0.0.1 -p "$port" PING 2>/dev/null | grep -q PONG; then
        # Identity check: the responder's working dir must be OUR tmp dir
        # (compare physical paths — redis reports its dir resolved).
        if redis-cli -h 127.0.0.1 -p "$port" CONFIG GET dir 2>/dev/null \
            | grep -qF "$sandbox_dir_phys"; then
          export REDIS_HOST="127.0.0.1"
          export REDIS_PORT="$port"
          export REDIS_URL="redis://127.0.0.1:$port"
          echo "evals-redis-sandbox: ephemeral redis on 127.0.0.1:$port (pid $_EVALS_SANDBOX_PID) — live redis untouched"
          return 0
        fi
        # A live responder that is not ours — abandon this port.
        break
      fi
      tick=$((tick + 1))
      sleep 0.1
    done
    kill "$_EVALS_SANDBOX_PID" 2>/dev/null
    wait "$_EVALS_SANDBOX_PID" 2>/dev/null
    _EVALS_SANDBOX_PID=""
  done

  echo "evals-redis-sandbox: could not start an ephemeral redis after 10 port attempts" >&2
  rm -rf "$_EVALS_SANDBOX_DIR" 2>/dev/null
  _EVALS_SANDBOX_DIR=""
  return 1
}

evals_redis_sandbox_stop() {
  if [ -n "$_EVALS_SANDBOX_PID" ]; then
    kill "$_EVALS_SANDBOX_PID" 2>/dev/null
    wait "$_EVALS_SANDBOX_PID" 2>/dev/null
    _EVALS_SANDBOX_PID=""
  fi
  if [ -n "$_EVALS_SANDBOX_DIR" ]; then
    rm -rf "$_EVALS_SANDBOX_DIR" 2>/dev/null
    _EVALS_SANDBOX_DIR=""
  fi
}
