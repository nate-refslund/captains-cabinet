#!/bin/bash
# Clean-environment boundary shared by the Mac and legacy officer launchers.

_OFFICER_ENV_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_OFFICER_ENV_PARSER="$_OFFICER_ENV_LIB_DIR/officer-env.py"

officer_env_scrub_authority() {
  # A LaunchAgent or parent shell can carry these even when cabinet/.env is
  # parsed correctly.  Remove exact authority secrets and defensive naming
  # families before constructing the officer's env -i command.
  local _name
  while IFS= read -r _name; do
    case "$_name" in
      DASHBOARD_PASSWORD|NEXTAUTH_SECRET|AUTH_SECRET|SESSION_SECRET|VERDICT_SECRET|ONBOARDING_WEBHOOK_SECRET|TELEGRAM_WEBHOOK_SECRET|CABINET_CAPTAIN_CHANNEL|*SESSION*SIGN*|*VERDICT*SIGN*)
        unset "$_name"
        ;;
    esac
  done < <(compgen -e)
}

officer_env_load_file() {
  local _file="$1" _officer="$2" _project="${3:-}"
  [ -f "$_file" ] || return 0
  local _rendered _previous_names="${CABINET_OFFICER_ENV_NAMES:-}"
  local _scope_file="${CABINET_MCP_SCOPE_FILE:-${CABINET_ROOT:-}/cabinet/mcp-scope.yml}"
  if [ ! -f "$_scope_file" ]; then
    echo "[ERROR] officer MCP scope is missing: $_scope_file — refusing credential projection" >&2
    return 2
  fi
  local -a _observe_arg=()
  [ "${CABINET_OBSERVE_ONLY:-0}" = "1" ] && _observe_arg=(--observe-only)
  # macOS ships /bin/bash 3.2 (licensing — it will never ship 4.x), and every
  # officer launcher runs `set -euo pipefail`.  In 3.2 a plain "${arr[@]}" on an
  # EMPTY array aborts with "unbound variable"; bash >= 4.4 allows it.  The
  # array is empty on the DEFAULT (not observe-only) path, so the default path
  # was the broken one and no env override could route around it.  The
  # alternate-value form below expands to ZERO arguments when empty and to the
  # flag when set.  "${_observe_arg[@]:-}" is NOT a valid substitute here: it
  # expands to one EMPTY-STRING argument, which the parser's argparse rejects
  # as an unrecognized positional (exit 2) — same failure, new disguise.
  if ! _rendered="$(python3.12 "$_OFFICER_ENV_PARSER" "$_file" --officer "$_officer" --project "$_project" --scope-file "$_scope_file" ${_observe_arg[@]+"${_observe_arg[@]}"})"; then
    echo "[ERROR] officer environment parse failed for $_file — refusing to source it as shell code" >&2
    return 2
  fi
  # The parser emits only validated names and shlex.quote()-escaped values.
  eval "$_rendered"
  CABINET_OFFICER_ENV_NAMES="${_previous_names}${_previous_names:+ }${CABINET_OFFICER_ENV_NAMES:-}"
}

_officer_env_emit_prefix() {
  local _mode="$1"
  # Print a shell command prefix that starts the officer with a genuinely
  # clean environment.  Raw per-role token aliases are launcher-only and are
  # not forwarded; the resolved TELEGRAM_BOT_TOKEN is forwarded explicitly.
  local -a _names=(
    HOME PATH USER LOGNAME SHELL TMPDIR LANG LC_ALL LC_CTYPE TERM COLORTERM
    SSH_AUTH_SOCK
    CABINET_ROOT CABINET_SOURCE_REPO CABINET_OFFICER OFFICER_NAME
    CABINET_ENV CABINET_OBSERVE_ONLY
    CABINET_LANE CABINET_ACTIVE_PROJECT CABINET_BOT_MODE CABINET_CEO_OFFICER
    CABINET_CAPTAIN_LAW_SOCKET CABINET_CAPTAIN_LAW_CAPABILITY
    TELEGRAM_STATE_DIR TELEGRAM_BOT_TOKEN
    TELEGRAM_HQ_CHAT_ID CAPTAIN_TELEGRAM_ID CAPTAIN_TELEGRAM_CHAT_ID
    CLAUDE_CONFIG_DIR CLAUDE_SECURESTORAGE_CONFIG_DIR
  )
  local _name
  for _name in ${CABINET_OFFICER_ENV_NAMES:-}; do
    case "$_name" in
      TELEGRAM_*_TOKEN)
        continue
        ;;
      DASHBOARD_PASSWORD|NEXTAUTH_SECRET|AUTH_SECRET|SESSION_SECRET|VERDICT_SECRET|ONBOARDING_WEBHOOK_SECRET|TELEGRAM_WEBHOOK_SECRET|CABINET_CAPTAIN_CHANNEL|*SESSION*SIGN*|*VERDICT*SIGN*)
        continue
        ;;
      *) _names+=("$_name") ;;
    esac
  done

  printf 'env -i'
  local _seen=" "
  for _name in "${_names[@]}"; do
    case "$_seen" in *" $_name "*) continue ;; esac
    _seen="${_seen}${_name} "
    if [ "${!_name+x}" = x ]; then
      if [ "$_mode" = "redacted" ]; then
        printf ' %q=%s' "$_name" '<set>'
      else
        printf ' %q=%q' "$_name" "${!_name}"
      fi
    fi
  done
}

officer_env_command_prefix() {
  _officer_env_emit_prefix real
}

officer_env_redacted_prefix() {
  _officer_env_emit_prefix redacted
}

officer_env_write_one_shot_launcher() {
  # tmux send-keys echoes its command into pane scrollback.  Since the clean
  # env prefix contains credentials, typing that prefix into a pane would turn
  # the scrollback into a secret store.  Materialize the command in a 0700
  # one-shot script instead; it unlinks itself before starting the officer.
  # stdout contains only the script path so callers can safely capture it.
  local _directory="$1" _command="$2" _script _quoted_command
  mkdir -p "$_directory"
  chmod 700 "$_directory"
  umask 077
  _script="$(mktemp "$_directory/officer-launch.XXXXXX")"
  printf -v _quoted_command '%q' "$_command"
  {
    printf '#!/bin/bash\n'
    printf 'set -euo pipefail\n'
    printf 'rm -f -- "$0"\n'
    printf 'exec /bin/bash -c %s\n' "$_quoted_command"
  } > "$_script"
  chmod 700 "$_script"
  printf '%s\n' "$_script"
}
