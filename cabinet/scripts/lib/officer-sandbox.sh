#!/bin/bash
# macOS OS-level boundary for officer sessions.
#
# Hooks remain useful UX, but they are not a security boundary: a shell command
# can construct a protected path from variables and evade text matching.  The
# sandbox is enforced after path resolution by the kernel.  An unsandboxed,
# fixed-policy broker is the only officer append path to the Captain-law files.

officer_sandbox_write_profile() {
  local _root="$1" _out="$2" _broker_dir="${3:-}" _broker_socket="${4:-}" _enforce_egress="${5:-0}" _observe_only="${6:-0}"
  local _shared_env="${7:-}" _state_dir="${8:-}"
  shift 8 2>/dev/null || true
  local _quoted_root _quoted_broker _quoted_socket _quoted_ssh _quoted_home
  local _runtime="" _quoted_shared_dir="" _quoted_state="" _quoted_runtime="" _quoted_tier2=""
  # Seatbelt string literals use C-style escaping.  Repository roots containing
  # a newline are refused; quote/backslash are escaped.
  case "$_root" in *$'\n'*|*$'\r'*) return 2 ;; esac
  if [ -n "$_broker_dir" ] && [ -d "$_broker_dir" ]; then
    _broker_dir="$(cd "$_broker_dir" && pwd -P)"
  fi
  if [ -n "$_broker_socket" ] && [ -n "$_broker_dir" ]; then
    _broker_socket="$_broker_dir/$(basename "$_broker_socket")"
  fi
  _quoted_root="${_root//\\/\\\\}"
  _quoted_root="${_quoted_root//\"/\\\"}"
  _quoted_broker="${_broker_dir//\\/\\\\}"
  _quoted_broker="${_quoted_broker//\"/\\\"}"
  _quoted_socket="${_broker_socket//\\/\\\\}"
  _quoted_socket="${_quoted_socket//\"/\\\"}"
  _quoted_ssh="${SSH_AUTH_SOCK:-}"
  _quoted_ssh="${_quoted_ssh//\\/\\\\}"
  _quoted_ssh="${_quoted_ssh//\"/\\\"}"
  _quoted_home="${HOME:-}"
  case "$_quoted_home" in *$'\n'*|*$'\r'*) return 2 ;; esac
  _quoted_home="${_quoted_home//\\/\\\\}"
  _quoted_home="${_quoted_home//\"/\\\"}"
  if [ -n "$_shared_env" ]; then
    _shared_env="${_shared_env/#\~/${HOME:-}}"
    if [ -e "$_shared_env" ] || [ -L "$_shared_env" ]; then
      _shared_env="$(cd "$(dirname "$_shared_env")" && pwd -P)/$(basename "$_shared_env")"
    fi
    case "$_shared_env" in *$'\n'*|*$'\r'*) return 2 ;; esac
    _quoted_shared_dir="$(dirname "$_shared_env")"
    _quoted_shared_dir="${_quoted_shared_dir//\\/\\\\}"
    _quoted_shared_dir="${_quoted_shared_dir//\"/\\\"}"
  fi
  if [ -n "$_state_dir" ]; then
    _state_dir="${_state_dir/#\~/${HOME:-}}"
    if [ -d "$_state_dir" ]; then
      _state_dir="$(cd "$_state_dir" && pwd -P)"
    fi
    case "$_state_dir" in *$'\n'*|*$'\r'*) return 2 ;; esac
    _quoted_state="${_state_dir//\\/\\\\}"
    _quoted_state="${_quoted_state//\"/\\\"}"
  fi
  _runtime="${HOME:-}/Library/Application Support/cabinet"
  _quoted_runtime="${_runtime//\\/\\\\}"
  _quoted_runtime="${_quoted_runtime//\"/\\\"}"
  if [ -n "${CABINET_OFFICER:-}" ]; then
    case "$CABINET_OFFICER" in *[!a-z0-9-]*|'') return 2 ;; esac
    _quoted_tier2="$_quoted_root/instance/memory/tier2/$CABINET_OFFICER"
  fi
  umask 077
  {
    printf '(version 1)\n'
    printf '(allow default)\n'
    # Every dotenv-shaped file is outside the officer filesystem view,
    # including product repos outside CABINET_ROOT.  The regex is evaluated
    # against the kernel-resolved path, so a symlink alias cannot rename the
    # target into an allowed-looking path.
    printf '(deny file-read* (regex #"/\\.env[^/]*$"))\n'
    # The shared secret stores never enter the officer's filesystem view.  MCP
    # credentials needed by the role arrive through the reviewed env allowlist.
    printf '(deny file-read* (literal "%s/cabinet/.env"))\n' "$_quoted_root"
    printf '(deny file-read* (subpath "%s/cabinet/env"))\n' "$_quoted_root"
    printf '(deny file-write* (literal "%s/cabinet/.env"))\n' "$_quoted_root"
    printf '(deny file-write* (subpath "%s/cabinet/env"))\n' "$_quoted_root"
    printf '(deny file-write-unlink (literal "%s/cabinet/.env"))\n' "$_quoted_root"
    printf '(deny file-write-unlink (subpath "%s/cabinet/env"))\n' "$_quoted_root"
    for _env_name in .env .env.local .env.production .env.development; do
      printf '(deny file-read* (literal "%s/cabinet/dashboard/%s"))\n' "$_quoted_root" "$_env_name"
      printf '(deny file-write* (literal "%s/cabinet/dashboard/%s"))\n' "$_quoted_root" "$_env_name"
      printf '(deny file-write-unlink (literal "%s/cabinet/dashboard/%s"))\n' "$_quoted_root" "$_env_name"
    done
    if [ -n "$_quoted_shared_dir" ]; then
      # The configured master store may contain renamed sidecars in addition
      # to .env. Keep its whole directory private; role-scoped values were
      # already projected before entering the sandbox.
      printf '(deny file-read* (subpath "%s"))\n' "$_quoted_shared_dir"
      printf '(deny file-write* (subpath "%s"))\n' "$_quoted_shared_dir"
      printf '(deny file-write-unlink (subpath "%s"))\n' "$_quoted_shared_dir"
    fi
    if [ -n "$_quoted_home" ]; then
      # Same-UID does not mean same authority. Keep the Captain's personal
      # credential stores, recovery material, and backup connection service
      # outside the officer's filesystem view. Officers authenticate through
      # the reviewed clean env, SSH agent, and dedicated Claude config home.
      for _secret_dir in \
        .claude .codex .ssh .aws .gnupg \
        .config/gh .config/gcloud .config/op \
        .cabinet-recovery Cabinet-Backups \
        Library/Caches/cabinet/backup; do
        printf '(deny file-read* (subpath "%s/%s"))\n' "$_quoted_home" "$_secret_dir"
        printf '(deny file-write* (subpath "%s/%s"))\n' "$_quoted_home" "$_secret_dir"
        printf '(deny file-write-unlink (subpath "%s/%s"))\n' "$_quoted_home" "$_secret_dir"
      done
      for _secret_file in .netrc .npmrc .git-credentials; do
        printf '(deny file-read* (literal "%s/%s"))\n' "$_quoted_home" "$_secret_file"
        printf '(deny file-write* (literal "%s/%s"))\n' "$_quoted_home" "$_secret_file"
        printf '(deny file-write-unlink (literal "%s/%s"))\n' "$_quoted_home" "$_secret_file"
      done
    fi
    # Kernel-enforced Captain-law plane.  This catches redirects, interpreters,
    # split variables, symlinks, and any future tool that ultimately writes the
    # same vnode.
    for _ledger in captain-patterns.md captain-intents.md captain-decisions.md; do
      printf '(deny file-write* (literal "%s/shared/interfaces/%s"))\n' "$_quoted_root" "$_ledger"
      printf '(deny file-write-unlink (literal "%s/shared/interfaces/%s"))\n' "$_quoted_root" "$_ledger"
    done
    # Prevent replacing an ancestor directory to substitute an attacker-owned
    # tree at the protected path.  Other files inside shared/interfaces remain
    # writable; only unlink/rename of these ancestors is denied.
    printf '(deny file-write-unlink (literal "%s"))\n' "$_quoted_root"
    printf '(deny file-write-unlink (literal "%s/cabinet"))\n' "$_quoted_root"
    printf '(deny file-write-unlink (literal "%s/cabinet/env"))\n' "$_quoted_root"
    printf '(deny file-write-unlink (literal "%s/cabinet/dashboard"))\n' "$_quoted_root"
    printf '(deny file-write-unlink (literal "%s/shared"))\n' "$_quoted_root"
    printf '(deny file-write-unlink (literal "%s/shared/interfaces"))\n' "$_quoted_root"
    if [ "$_enforce_egress" = "1" ]; then
      # The local proxy is the only path to an external host.  HTTP clients
      # inherit its env, while raw sockets and proxy-bypassing clients are
      # rejected by Seatbelt.  Local Redis, broker, DNS, and proxy connections
      # remain possible; hostname filtering is performed by the proxy.
      printf '(deny network-outbound (remote tcp "*:*"))\n'
      printf '(deny network-outbound (remote udp "*:*"))\n'
      printf '(allow network-outbound (remote tcp "localhost:*"))\n'
      printf '(allow network-outbound (remote udp "localhost:*"))\n'
    fi
    if [ "$_observe_only" = "1" ]; then
      # Defense below the hook: HOME is write-denied by default.  The only
      # writable homes are this officer's tier-2 notes and explicit Cabinet
      # runtime stores. Product/repo roots outside HOME receive their own deny
      # below. This keeps Documents, Obsidian, and unrelated app state read-only.
      if [ -n "$_quoted_home" ]; then
        printf '(deny file-write* (subpath "%s"))\n' "$_quoted_home"
        printf '(deny file-write-unlink (subpath "%s"))\n' "$_quoted_home"
      fi
      local _source _real_source _quoted_source
      for _source in "$_root" "$@"; do
        [ -n "$_source" ] || continue
        _source="${_source/#\~/${HOME:-}}"
        if [ -d "$_source" ]; then
          _real_source="$(cd "$_source" && pwd -P)"
        else
          _real_source="$_source"
        fi
        case "$_real_source" in *$'\n'*|*$'\r'*) return 2 ;; esac
        _quoted_source="${_real_source//\\/\\\\}"
        _quoted_source="${_quoted_source//\"/\\\"}"
        printf '(deny file-write* (subpath "%s"))\n' "$_quoted_source"
        printf '(deny file-write-unlink (subpath "%s"))\n' "$_quoted_source"
      done
      if [ -n "$_quoted_tier2" ]; then
        printf '(allow file-write* (subpath "%s"))\n' "$_quoted_tier2"
        printf '(allow file-write-unlink (subpath "%s"))\n' "$_quoted_tier2"
      fi
      printf '(allow file-write* (subpath "%s/cabinet/cache"))\n' "$_quoted_root"
      printf '(allow file-write-unlink (subpath "%s/cabinet/cache"))\n' "$_quoted_root"
      printf '(allow file-write* (subpath "%s"))\n' "$_quoted_runtime"
      printf '(allow file-write-unlink (subpath "%s"))\n' "$_quoted_runtime"
      if [ -n "$_quoted_state" ]; then
        printf '(allow file-write* (subpath "%s"))\n' "$_quoted_state"
        printf '(allow file-write-unlink (subpath "%s"))\n' "$_quoted_state"
      fi
      # Raw evidence remains Captain-controlled even though sibling runtime
      # stores are writable during observation.
      printf '(deny file-write* (subpath "%s/evidence"))\n' "$_quoted_runtime"
      printf '(deny file-write-unlink (subpath "%s/evidence"))\n' "$_quoted_runtime"
    fi
    # Protect the boundary implementation itself from an officer preparing a
    # weaker next restart.  A germline amendment is still required for the
    # host-wide schg list; this is the immediate runtime backstop.
    for _boundary in \
      cabinet/scripts/start-officer-mac.sh \
      cabinet/scripts/start-officer.sh \
      cabinet/scripts/gen-officer-mcp-config.py \
      cabinet/scripts/append-interface.sh \
      cabinet/scripts/captain-law-broker.py \
      cabinet/scripts/egress-guard.sh \
      cabinet/scripts/egress-proxy.py \
      cabinet/scripts/observe-only.sh \
      cabinet/scripts/lib/officer-env.py \
      cabinet/scripts/lib/officer-env.sh \
      cabinet/scripts/lib/officer-sandbox.sh \
      framework/comms/channel_adapter.py \
      framework/comms/tools.py \
      framework/comms/mcp/server.py \
      framework/comms/adapters/telegram.py; do
      printf '(deny file-write* (literal "%s/%s"))\n' "$_quoted_root" "$_boundary"
      printf '(deny file-write-unlink (literal "%s/%s"))\n' "$_quoted_root" "$_boundary"
    done
    # The live egress switch and its attested runtime are Captain/launcher
    # state.  An officer cannot prepare a weaker next restart or forge a ready
    # proxy/env after the launcher reconciles it.
    printf '(deny file-write* (literal "%s/instance/config/egress.yml"))\n' "$_quoted_root"
    printf '(deny file-write-unlink (literal "%s/instance/config/egress.yml"))\n' "$_quoted_root"
    if [ -n "$_quoted_state" ]; then
      printf '(deny file-write* (subpath "%s/egress"))\n' "$_quoted_state"
      printf '(deny file-write-unlink (subpath "%s/egress"))\n' "$_quoted_state"
    fi
    if [ -n "$_broker_dir" ]; then
      # Socket connect is a network operation and remains allowed; file reads,
      # unlink, replacement, pidfile tampering, and sibling-socket discovery do
      # not.  Per-officer capabilities authenticate the request itself.
      printf '(deny file-read* (subpath "%s"))\n' "$_quoted_broker"
      printf '(deny file-write* (subpath "%s"))\n' "$_quoted_broker"
      printf '(deny file-write-unlink (subpath "%s"))\n' "$_quoted_broker"
    fi
    # The officer pane is a sandboxed child of an already-running, unsandboxed
    # tmux server.  A path-specific deny is insufficient: tmux supports custom
    # socket paths and the default can live under $TMPDIR.  Deny ALL outbound
    # Unix-domain sockets except the exact fixed-policy broker, the system DNS
    # resolver, and (when present) the inherited SSH agent needed for Git.
    # Seatbelt evaluates the resolved remote socket, so symlinked tmux clients
    # and home-grown protocol clients cannot proxy an unsandboxed command.
    printf '(deny network-outbound (require-all (remote unix-socket)'
    if [ -n "$_broker_socket" ]; then
      printf ' (require-not (literal "%s"))' "$_quoted_socket"
    fi
    printf ' (require-not (literal "/private/var/run/mDNSResponder"))'
    if [ -n "${SSH_AUTH_SOCK:-}" ]; then
      printf ' (require-not (literal "%s"))' "$_quoted_ssh"
    fi
    printf '))\n'
    # Defense in depth only; the UDS rule above is the boundary.  Common tmux
    # path denies make ordinary attempts fail before IPC but are not relied on
    # because package-manager paths may be symlinks.
    for _tmux in /opt/homebrew/bin/tmux /usr/local/bin/tmux /usr/bin/tmux; do
      printf '(deny process-exec (literal "%s"))\n' "$_tmux"
    done
  } > "$_out"
  chmod 600 "$_out"
}
