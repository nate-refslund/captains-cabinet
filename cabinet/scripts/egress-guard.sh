#!/bin/bash
# egress-guard.sh — manager for the OPT-IN enforced egress allowlist.
#
# The Captain's directive: "implement the possibility of an enforced egress
# allowlist (default allow all)." This is that control — a real, enable-able
# outbound-egress jail that changes NOTHING until a captain turns it on.
#
# SOURCE OF TRUTH: framework/defaults/egress.yml (shipped: enforce=false =
# allow all) merged with the per-deployment override instance/config/egress.yml
# (instance wins; scalars replace, allow_hosts unions). See those files and
# docs/runbooks/egress-allowlist.md.
#
# SUBCOMMANDS
#   status    show whether enforcement is on + the resolved allowlist + proxy
#             state (read-only; installs/changes nothing).
#   runtime-state  print ENFORCE<TAB>PROXY_ENV for launchers (read-only).
#   dry-run   show what WOULD be allowed/blocked if enforce were on, install
#             nothing (works regardless of the current enforce value).
#   apply     reconcile runtime to whatever egress.yml currently says:
#               enforce=false -> idempotent teardown (allow all, no restriction)
#               enforce=true  -> install the allowlisting proxy + write the
#                                officer HTTP_PROXY env, FAIL CLOSED if it can't
#             This is the verb a boot hook / launchd calls.
#   enable    set enforce=true in instance/config/egress.yml, then apply.
#   disable   set enforce=false in instance/config/egress.yml, then apply.
#   stop      tear down the proxy + remove the restriction regardless of config.
#
# ENFORCEMENT MECHANISM (enforce=true): a local forward proxy
# (cabinet/scripts/egress-proxy.py, python3 stdlib, bound 127.0.0.1) that
# allows CONNECT/HTTP only to the resolved allowlist and 403s the rest, plus an
# exported HTTP_PROXY/HTTPS_PROXY/NO_PROXY file the officer launchers project
# into their clean environments.  On macOS the launcher also asks Seatbelt to
# deny direct external TCP/UDP, so proxy bypasses fail at the kernel boundary.
# Legacy Linux/Docker launchers get the proxy layer but still require a host or
# container network policy to catch raw sockets; see the runbook.
#
# Style contract: bash 3.2 portable (no mapfile / assoc arrays), set -u, clean
# under `shellcheck -S warning`. Secrets are never logged. Tests:
# cabinet/scripts/tests/test_egress_guard.py.

set -u

SELF_DIR=$(cd "$(dirname "$0")" && pwd -P) || exit 1
DEFAULT_ROOT=$(cd "$SELF_DIR/../.." && pwd -P) || exit 1
ROOT="${CABINET_ROOT:-$DEFAULT_ROOT}"

# Python interpreter (matches cabinet-doctor.sh): CABINET_PYTHON override, else
# the system 3.12, else whatever python3 is on PATH.
PY="${CABINET_PYTHON:-/opt/homebrew/bin/python3.12}"
command -v "$PY" >/dev/null 2>&1 || PY=python3

# The proxy backend the guard launches. Overridable for tests (fail-closed sim).
PROXY_SCRIPT="${EGRESS_PROXY_SCRIPT:-$SELF_DIR/egress-proxy.py}"

TAB=$(printf '\t')

# ------- globals populated by resolve_into_vars (init for set -u) -----------
ENFORCE=0
PROXY_PORT=8899
ALLOW_PRODUCT=1
STATE_DIR=""
ALLOW_LIST=""
PRODUCT_DOMAINS=""
EGRESS_DIR=""
ALLOW_FILE=""
READY_FILE=""
PID_FILE=""
ENV_FILE=""
LOG_FILE=""

usage() {
  cat >&2 <<'EOF'
usage: egress-guard.sh {status|dry-run|apply|enable|disable|stop}
  status    show enforcement state + resolved allowlist + proxy state
  runtime-state  machine-readable ENFORCE<TAB>PROXY_ENV for launchers
  dry-run   show what WOULD be allowed/blocked; install nothing
  apply     reconcile runtime to egress.yml (enforce=false -> allow all;
            enforce=true -> install the allowlisting proxy, fail closed)
  enable    set enforce=true in instance/config/egress.yml, then apply
  disable   set enforce=false in instance/config/egress.yml, then apply
  stop      tear down the proxy + remove the restriction
EOF
}

# ---------------------------------------------------------------- config ----
# Merge framework default + instance override in python (PyYAML, structured —
# no shell interpolation of file contents), resolve allow_product to the
# captain's own org_domains exactly like framework/env.py, and emit TAB-keyed
# lines the shell reads without eval.
resolve_into_vars() {
  local out rc
  out=$("$PY" - "$ROOT" 2>/dev/null <<'PYEOF'
import os, sys
try:
    import yaml
except Exception:
    sys.exit(3)

root = sys.argv[1]

def load(rel):
    # FAIL-CLOSED config load. An ABSENT file is fine (use defaults); a file
    # that EXISTS but cannot be read or parsed is fatal (exit 4) — never
    # silently return {} and let a corrupt egress.yml fall back to the
    # allow-all scalar default while the captain intended enforce=true.
    path = os.path.join(root, rel)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            d = yaml.safe_load(fh.read())
    except Exception:
        sys.exit(4)
    if d is None:          # present but empty = no overrides, use defaults
        return {}
    if not isinstance(d, dict):   # present but not a mapping = malformed
        sys.exit(4)
    return d

base = load("framework/defaults/egress.yml")
inst = load("instance/config/egress.yml")

def scalar(key, default):
    if key in inst and inst[key] is not None:
        return inst[key]
    if key in base and base[key] is not None:
        return base[key]
    return default

enforce = bool(scalar("enforce", False))
try:
    port = int(scalar("proxy_port", 8899))
except Exception:
    port = -1
allow_product = bool(scalar("allow_product", True))

# allow_hosts: UNION of framework floor + instance additions.
hosts = []
for src in (base.get("allow_hosts"), inst.get("allow_hosts")):
    if isinstance(src, (list, tuple)):
        for h in src:
            if isinstance(h, str) and h.strip():
                hosts.append(h.strip().lower().rstrip("."))

# allow_product -> org_domains (mirror framework/env.py org_domains()).
domains = []
if allow_product:
    for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
        d = load(rel)
        val = d.get("org_domains")
        if val is None and isinstance(d.get("product"), dict):
            val = d["product"].get("org_domains")
        if isinstance(val, (list, tuple)):
            cleaned = [x.strip().lower().rstrip(".")
                       for x in val if isinstance(x, str) and x.strip()]
            if cleaned:
                domains = cleaned
                break
    hosts.extend(domains)

seen = set()
allow = []
for h in hosts:
    if h and h not in seen:
        seen.add(h)
        allow.append(h)

# state dir: CABINET_STATE_DIR env, else platform.yml/product.yml state_dir.
state = (os.environ.get("CABINET_STATE_DIR") or "").strip()
if not state:
    for rel in ("instance/config/platform.yml", "instance/config/product.yml"):
        d = load(rel)
        v = d.get("state_dir")
        if v is None and isinstance(d.get("product"), dict):
            v = d["product"].get("state_dir")
        if isinstance(v, str) and v.strip():
            state = v.strip()
            break
if state:
    state = os.path.expanduser(state)

lines = []
lines.append("STATE_DIR\t%s" % state)
lines.append("ENFORCE\t%d" % (1 if enforce else 0))
lines.append("PROXY_PORT\t%d" % port)
lines.append("ALLOW_PRODUCT\t%d" % (1 if allow_product else 0))
for d in domains:
    lines.append("PRODUCT_DOMAIN\t%s" % d)
for h in allow:
    lines.append("ALLOW\t%s" % h)
sys.stdout.write("\n".join(lines) + "\n")
PYEOF
  )
  rc=$?
  if [ "$rc" -ne 0 ] || [ -z "$out" ]; then
    if [ "$rc" -eq 4 ]; then
      # A config file exists but is unreadable/unparseable/malformed. FAIL
      # CLOSED — do NOT fall back to the allow-all default the captain may
      # have overridden to enforce=true.
      echo "egress-guard: FAIL-CLOSED — a config file is present but unparseable; refusing to resolve to the allow-all default" >&2
    else
      echo "egress-guard: config resolution failed (python/PyYAML unavailable or egress.yml unreadable)" >&2
    fi
    return 1
  fi

  ENFORCE=0; PROXY_PORT=8899; ALLOW_PRODUCT=1; STATE_DIR=""
  ALLOW_LIST=""; PRODUCT_DOMAINS=""
  local key val
  while IFS="$TAB" read -r key val; do
    case "$key" in
      STATE_DIR)       STATE_DIR="$val" ;;
      ENFORCE)         ENFORCE="$val" ;;
      PROXY_PORT)      PROXY_PORT="$val" ;;
      ALLOW_PRODUCT)   ALLOW_PRODUCT="$val" ;;
      PRODUCT_DOMAIN)  PRODUCT_DOMAINS="$PRODUCT_DOMAINS $val" ;;
      ALLOW)           ALLOW_LIST="$ALLOW_LIST $val" ;;
    esac
  done <<EOF
$out
EOF
  ALLOW_LIST="${ALLOW_LIST# }"
  PRODUCT_DOMAINS="${PRODUCT_DOMAINS# }"

  if [ -z "$STATE_DIR" ]; then
    STATE_DIR="${HOME:-/tmp}/.cabinet/state"
  fi
  EGRESS_DIR="$STATE_DIR/egress"
  ALLOW_FILE="$EGRESS_DIR/allow.hosts"
  READY_FILE="$EGRESS_DIR/proxy.ready"
  PID_FILE="$EGRESS_DIR/proxy.pid"
  ENV_FILE="$EGRESS_DIR/proxy.env"
  LOG_FILE="$EGRESS_DIR/proxy.log"
  return 0
}

# ---------------------------------------------------------------- proxy -----
# Echo the tracked proxy pid iff a live proxy is running, else return 1.
proxy_pid() {
  [ -n "$PID_FILE" ] && [ -f "$PID_FILE" ] || return 1
  local pid
  pid=$(cat "$PID_FILE" 2>/dev/null) || return 1
  case "$pid" in
    ''|*[!0-9]*) return 1 ;;
  esac
  if kill -0 "$pid" 2>/dev/null; then
    echo "$pid"
    return 0
  fi
  return 1
}

# The actual bound port (proxy_port may be 0 = OS-chosen); read from ready-file.
running_port() {
  [ -n "$READY_FILE" ] && [ -f "$READY_FILE" ] || return 1
  local p
  p=$(sed -n 's/^READY \([0-9][0-9]*\).*/\1/p' "$READY_FILE" 2>/dev/null | head -1)
  [ -n "$p" ] || return 1
  echo "$p"
}

stop_proxy() {
  local pid i
  if pid=$(proxy_pid); then
    kill "$pid" 2>/dev/null || true
    i=0
    while [ "$i" -lt 20 ] && kill -0 "$pid" 2>/dev/null; do
      sleep 0.1
      i=$((i + 1))
    done
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE" "$READY_FILE" "$ENV_FILE" 2>/dev/null || true
}

APPLY_LOCK=""
acquire_apply_lock() {
  mkdir -p "$EGRESS_DIR" 2>/dev/null || return 1
  APPLY_LOCK="$EGRESS_DIR/apply.lock"
  local i=0 owner=""
  while [ "$i" -lt 100 ]; do
    if mkdir "$APPLY_LOCK" 2>/dev/null; then
      printf '%s\n' "$$" > "$APPLY_LOCK/pid"
      return 0
    fi
    owner=$(cat "$APPLY_LOCK/pid" 2>/dev/null || true)
    case "$owner" in
      ''|*[!0-9]*) ;;
      *)
        if ! kill -0 "$owner" 2>/dev/null; then
          rm -rf "$APPLY_LOCK" 2>/dev/null || true
          continue
        fi
        ;;
    esac
    sleep 0.1
    i=$((i + 1))
  done
  echo "egress-guard: FAIL-CLOSED — could not acquire runtime apply lock" >&2
  return 1
}

release_apply_lock() {
  [ -n "$APPLY_LOCK" ] && rm -rf "$APPLY_LOCK" 2>/dev/null || true
  APPLY_LOCK=""
}

teardown() {
  stop_proxy
  rm -f "$ALLOW_FILE" 2>/dev/null || true
}

render_env_file() {
  local addr="http://127.0.0.1:$PROXY_PORT"
  cat <<EOF
# egress proxy env — written by egress-guard.sh apply (enforce=true).
# Officer launch sources this to route proxy-honouring egress through the
# allowlisting proxy. Absent/empty => no restriction (allow all).
export HTTP_PROXY="$addr"
export HTTPS_PROXY="$addr"
export http_proxy="$addr"
export https_proxy="$addr"
export NO_PROXY="localhost,127.0.0.1,::1"
export no_proxy="localhost,127.0.0.1,::1"
EOF
}

write_env_file() {
  local tmp="$ENV_FILE.tmp.$$"
  umask 077
  render_env_file > "$tmp"
  chmod 600 "$tmp"
  mv -f "$tmp" "$ENV_FILE"
}

runtime_file_is_owned_regular() {
  local path="$1" owner=""
  [ -f "$path" ] && [ ! -L "$path" ] || return 1
  owner=$(stat -f '%u' "$path" 2>/dev/null || stat -c '%u' "$path" 2>/dev/null || true)
  [ "$owner" = "$(id -u)" ]
}

# Recompute the runtime contract from Captain config and compare it with every
# artifact the launcher is about to trust.  The state directory is mutable
# runtime data, not authority: a stale/forged pid, allowlist, ready file, or
# proxy env makes launch fail closed rather than changing the effective policy.
attest_runtime() {
  [ "$ENFORCE" = 1 ] || return 0
  if [ ! -d "$EGRESS_DIR" ] || [ -L "$EGRESS_DIR" ]; then
    echo "egress-guard: FAIL-CLOSED — runtime state directory is absent or symlinked" >&2
    return 1
  fi
  local path
  for path in "$ALLOW_FILE" "$READY_FILE" "$PID_FILE" "$ENV_FILE"; do
    if ! runtime_file_is_owned_regular "$path"; then
      echo "egress-guard: FAIL-CLOSED — runtime attestation rejected $(basename "$path")" >&2
      return 1
    fi
  done
  local pid port command_line expected_allow actual_allow expected_env actual_env
  pid=$(proxy_pid 2>/dev/null || true)
  port=$(running_port 2>/dev/null || true)
  if [ -z "$pid" ] || [ -z "$port" ]; then
    echo "egress-guard: FAIL-CLOSED — attested proxy is not live/ready" >&2
    return 1
  fi
  command_line=$(ps -p "$pid" -o command= 2>/dev/null || true)
  case "$command_line" in
    *"$PROXY_SCRIPT"*"--allow-file"*"$ALLOW_FILE"*"--ready-file"*"$READY_FILE"*) ;;
    *)
      echo "egress-guard: FAIL-CLOSED — proxy pid command does not match the reviewed backend/state" >&2
      return 1 ;;
  esac
  expected_allow=""
  set -f
  # shellcheck disable=SC2086 # deliberate word-split of resolved allowlist
  for path in $ALLOW_LIST; do
    expected_allow="${expected_allow}${expected_allow:+
}$path"
  done
  set +f
  actual_allow=$(cat "$ALLOW_FILE" 2>/dev/null) || return 1
  if [ "$actual_allow" != "$expected_allow" ]; then
    echo "egress-guard: FAIL-CLOSED — runtime allowlist does not match Captain config" >&2
    return 1
  fi
  PROXY_PORT="$port"
  expected_env=$(render_env_file)
  actual_env=$(cat "$ENV_FILE" 2>/dev/null) || return 1
  if [ "$actual_env" != "$expected_env" ]; then
    echo "egress-guard: FAIL-CLOSED — proxy environment failed attestation" >&2
    return 1
  fi
  return 0
}

# Install the restriction. FAIL-CLOSED: any step that cannot be verified
# returns non-zero and leaves NO proxy env behind (egress is never silently
# left open when enforce=true).
install_enforce() {
  local desired="$EGRESS_DIR/allow.desired.$$"
  case "$PROXY_PORT" in
    ''|*[!0-9]*)
      echo "egress-guard: invalid proxy_port '$PROXY_PORT'" >&2
      return 1 ;;
  esac
  if [ "$PROXY_PORT" -gt 65535 ]; then
    echo "egress-guard: proxy_port out of range: $PROXY_PORT" >&2
    return 1
  fi
  if [ ! -f "$PROXY_SCRIPT" ]; then
    echo "egress-guard: FAIL-CLOSED — proxy backend missing: $PROXY_SCRIPT" >&2
    return 1
  fi
  mkdir -p "$EGRESS_DIR" 2>/dev/null || {
    echo "egress-guard: FAIL-CLOSED — cannot create state dir: $EGRESS_DIR" >&2
    return 1
  }

  # Materialise the desired allowlist first.  If a matching verified proxy is
  # already running, keep it: concurrent officer launches should not flap the
  # shared proxy and interrupt sessions that are already constrained.
  umask 077
  if ! : > "$desired" 2>/dev/null; then
    echo "egress-guard: FAIL-CLOSED — cannot write allowlist: $ALLOW_FILE" >&2
    return 1
  fi
  set -f
  # shellcheck disable=SC2086 # deliberate word-split of the space-joined list
  for h in $ALLOW_LIST; do
    printf '%s\n' "$h" >> "$desired"
  done
  set +f

  local live_pid="" live_port=""
  live_pid=$(proxy_pid 2>/dev/null || true)
  live_port=$(running_port 2>/dev/null || true)
  if [ -n "$live_pid" ] && [ -n "$live_port" ] \
    && [ -f "$ALLOW_FILE" ] && [ -f "$ENV_FILE" ] \
    && cmp -s "$desired" "$ALLOW_FILE" \
    && { [ "$PROXY_PORT" = 0 ] || [ "$PROXY_PORT" = "$live_port" ]; }; then
    rm -f "$desired"
    PROXY_PORT="$live_port"
    write_env_file
    return 0
  fi

  stop_proxy
  if ! mv -f "$desired" "$ALLOW_FILE" 2>/dev/null; then
    rm -f "$desired"
    echo "egress-guard: FAIL-CLOSED — cannot install allowlist: $ALLOW_FILE" >&2
    return 1
  fi

  rm -f "$READY_FILE" 2>/dev/null || true

  # Launch the proxy fully detached (no inherited std fds -> the caller's
  # captured pipes see EOF when the guard returns, proxy keeps running).
  nohup "$PY" "$PROXY_SCRIPT" \
    --port "$PROXY_PORT" \
    --allow-file "$ALLOW_FILE" \
    --ready-file "$READY_FILE" \
    --pid-file "$PID_FILE" \
    </dev/null >"$LOG_FILE" 2>&1 &
  local child=$!

  # Verify: the proxy wrote its ready-file AND is still alive. ok stays 0 on
  # any failure path (dead child, never-ready) so we fail closed by timeout.
  local i=0 ok=0
  while [ "$i" -lt 50 ]; do
    if [ -f "$READY_FILE" ] && kill -0 "$child" 2>/dev/null; then
      ok=1
      break
    fi
    sleep 0.1
    i=$((i + 1))
  done

  if [ "$ok" != 1 ]; then
    echo "egress-guard: FAIL-CLOSED — proxy did not come up (enforce=true); egress NOT restricted, no proxy env written" >&2
    kill "$child" 2>/dev/null || true
    rm -f "$ENV_FILE" 2>/dev/null || true
    return 1
  fi

  # Reflect the actually-bound port (handles proxy_port: 0).
  local bound
  if bound=$(running_port); then
    PROXY_PORT="$bound"
  fi

  write_env_file
  return 0
}

# ---------------------------------------------------------------- verbs -----
# Non-fatal wiring check. Enforcement only constrains officers whose launch
# loads the proxy env this guard writes.  Accept either a traditional source
# or the reviewed officer_env_load_file parser used by the clean launchers.
warn_if_unwired() {
  command -v grep >/dev/null 2>&1 || return 0
  local wired
  # Match a line that actually SOURCES proxy.env, but exclude this control's
  # OWN files — the guard prints the source idiom as advice, its test seeds it
  # as an example, and the runbook documents it; none is an officer launch
  # wrapper. Any OTHER file that sources proxy.env is real wiring. (Excluding
  # them is what keeps the warning firing in the real tree, not just in tests.)
  wired=$(grep -rIlE '((source|\.)[[:space:]]+.*proxy\.env|officer_env_load_file.*(proxy|EGRESS_ENV))' "$ROOT" \
            --exclude-dir=.git \
            --exclude='egress-guard.sh' \
            --exclude='egress-proxy.py' \
            --exclude='test_egress_guard.py' \
            --exclude='egress-allowlist.md' 2>/dev/null \
          | head -1)
  [ -n "$wired" ] && return 0
  echo "egress-guard: WARNING — no officer launch wrapper in the tree loads the proxy env file yet." >&2
  echo "  Enforcement is ACTIVE, but it constrains NOTHING ALREADY RUNNING until you add, in your officer launch:" >&2
  echo "    [ -f \"\$CABINET_STATE_DIR/egress/proxy.env\" ] && . \"\$CABINET_STATE_DIR/egress/proxy.env\"" >&2
  echo "  see docs/runbooks/egress-allowlist.md (\"Wiring officers to the proxy\")." >&2
  return 0
}

cmd_apply() {
  resolve_into_vars || return 1
  acquire_apply_lock || return 1
  trap 'release_apply_lock' EXIT
  trap 'release_apply_lock; exit 130' HUP INT TERM
  local rc=0
  if [ "$ENFORCE" = 1 ]; then
    if install_enforce && attest_runtime; then
      local n
      n=$(printf '%s\n' "$ALLOW_LIST" | wc -w | tr -d ' ')
      echo "egress-guard: ENFORCING — proxy on http://127.0.0.1:$PROXY_PORT, $n host(s) allowed."
      echo "egress-guard: officer launch must load $ENV_FILE (see runbook)."
      warn_if_unwired
      rc=0
    else
      rc=1
    fi
  else
    teardown
    echo "egress-guard: enforce=false — allow all (no restriction active)."
  fi
  release_apply_lock
  trap - EXIT HUP INT TERM
  return "$rc"
}

cmd_runtime_state() {
  resolve_into_vars || return 1
  if [ "$ENFORCE" = 1 ] && ! attest_runtime; then
    return 1
  fi
  printf '%s\t%s\n' "$ENFORCE" "$ENV_FILE"
}

# Set the enforce flag in instance/config/egress.yml, preserving comments
# (line-oriented replace via python; seed from the .example/default if absent).
# Dirty-guarded against a concurrent writer of a TRACKED file.
set_enforce() {
  local want="$1"
  local st
  st=$(git -C "$ROOT" status --porcelain -- "instance/config/egress.yml" 2>/dev/null | head -1)
  case "$st" in
    ' M'*|'M '*|'MM'*|'AM'*|'UU'*)
      echo "egress-guard: instance/config/egress.yml is dirty (owned by another writer) — refusing to edit" >&2
      return 1 ;;
  esac
  "$PY" - "$ROOT" "$want" <<'PYEOF'
import os, re, sys
root, want = sys.argv[1], sys.argv[2]
target = os.path.join(root, "instance/config/egress.yml")
example = os.path.join(root, "instance/config/egress.yml.example")
default = os.path.join(root, "framework/defaults/egress.yml")
if os.path.exists(target):
    with open(target, encoding="utf-8") as fh:
        text = fh.read()
else:
    seed = example if os.path.exists(example) else default
    try:
        with open(seed, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = "enforce: %s\n" % want
pat = re.compile(r'^([ \t]*)enforce:.*$', re.M)
if pat.search(text):
    text = pat.sub(lambda m: "%senforce: %s" % (m.group(1), want), text, count=1)
else:
    if text and not text.endswith("\n"):
        text += "\n"
    text += "enforce: %s\n" % want
os.makedirs(os.path.dirname(target), exist_ok=True)
tmp = "%s.tmp.%d" % (target, os.getpid())
with open(tmp, "w", encoding="utf-8") as fh:
    fh.write(text)
os.replace(tmp, target)
PYEOF
}

cmd_enable() {
  set_enforce true || return 1
  cmd_apply
}

cmd_disable() {
  set_enforce false || return 1
  cmd_apply
}

cmd_stop() {
  resolve_into_vars || return 1
  teardown
  echo "egress-guard: proxy stopped, restriction removed (allow all)."
  return 0
}

cmd_dry_run() {
  resolve_into_vars || return 1
  local ecur="false"
  [ "$ENFORCE" = 1 ] && ecur="true"
  echo "egress-guard dry-run (enforce currently: $ecur) — installs nothing"
  if [ -z "$ALLOW_LIST" ]; then
    echo "  If enforce=true, the proxy would ALLOW: (none — ALL egress blocked)"
  else
    echo "  If enforce=true, the proxy would ALLOW these hosts (and subdomains):"
    set -f
    # shellcheck disable=SC2086
    for h in $ALLOW_LIST; do
      echo "    - $h"
    done
    set +f
  fi
  echo "  All other hosts would be BLOCKED (403)."
  return 0
}

cmd_status() {
  resolve_into_vars || return 1
  local ecur="false"
  [ "$ENFORCE" = 1 ] && ecur="true"
  local aprod="false"
  [ "$ALLOW_PRODUCT" = 1 ] && aprod="true"

  echo "egress-guard status"
  if [ -f "$ROOT/framework/defaults/egress.yml" ]; then
    echo "  config_default:  framework/defaults/egress.yml (present)"
  else
    echo "  config_default:  framework/defaults/egress.yml (ABSENT)"
  fi
  if [ -f "$ROOT/instance/config/egress.yml" ]; then
    echo "  config_instance: instance/config/egress.yml (present)"
  else
    echo "  config_instance: instance/config/egress.yml (absent — using framework default)"
  fi
  echo "  enforce:         $ecur"
  echo "  allow_product:   $aprod"
  if [ -n "$PRODUCT_DOMAINS" ]; then
    echo "  product_domains: $PRODUCT_DOMAINS"
  else
    echo "  product_domains: (none)"
  fi
  echo "  proxy_port(cfg): $PROXY_PORT"

  local n
  n=$(printf '%s\n' "$ALLOW_LIST" | wc -w | tr -d ' ')
  echo "  allowlist ($n):"
  if [ -n "$ALLOW_LIST" ]; then
    set -f
    # shellcheck disable=SC2086
    for h in $ALLOW_LIST; do
      echo "    - $h"
    done
    set +f
  fi

  local pid bport
  if pid=$(proxy_pid); then
    if bport=$(running_port); then
      echo "  proxy:           RUNNING pid=$pid addr=http://127.0.0.1:$bport"
    else
      echo "  proxy:           RUNNING pid=$pid addr=http://127.0.0.1:$PROXY_PORT"
    fi
  else
    echo "  proxy:           STOPPED"
  fi
  if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then
    echo "  proxy_env:       $ENV_FILE (present)"
  else
    echo "  proxy_env:       $ENV_FILE (absent)"
  fi
  echo "  coverage:        proxy-honouring HTTP/HTTPS; Mac launchers also kernel-block direct external TCP/UDP."
  echo "  residual:        Linux/Docker raw sockets need a host/container network policy — see runbook."
  return 0
}

# ---------------------------------------------------------------- main ------
cmd="${1:-status}"
case "$cmd" in
  status)        cmd_status ;;
  runtime-state) cmd_runtime_state ;;
  dry-run|dryrun) cmd_dry_run ;;
  apply)         cmd_apply ;;
  enable)        cmd_enable ;;
  disable)       cmd_disable ;;
  stop)          cmd_stop ;;
  -h|--help|help) usage; exit 0 ;;
  *)
    echo "egress-guard: unknown command: $cmd" >&2
    usage
    exit 64 ;;
esac
