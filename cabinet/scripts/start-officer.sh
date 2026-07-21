#!/bin/bash
# start-officer.sh — Start an Officer session in tmux
# Fully dynamic — no hardcoded officer list. Any officer with a bot token works.
#
# Usage:
#   Legacy (single-project):  start-officer.sh <officer>
#   Pool (FW-073, multi-project): start-officer.sh <officer> --project <slug>
#
# Pool mode (--project given) scopes the tmux window AND working dir per
# (officer, project) so claude --continue resumes per-project sessions, and
# exports CABINET_ACTIVE_PROJECT into the subshell so cost-counter hooks
# (FW-072) write per-project HSET fields. Legacy mode is unchanged.
#
# Requires: TELEGRAM_<UPPER>_TOKEN in environment (e.g. TELEGRAM_CTO_TOKEN)

OFFICER="${1:?Usage: start-officer.sh <officer> [--project <slug>]}"
shift

PROJECT=""
POOL_MODE=false
while [ $# -gt 0 ]; do
  case "$1" in
    --project)
      PROJECT="${2:?--project requires a slug argument}"
      # slug allowlist: lowercase alnum + hyphens, must NOT lead with hyphen
      # (so it cannot be confused with a flag in any downstream invocation).
      # Pool windows + workdirs + Redis stream suffix use this verbatim, so
      # rejecting shell-special chars closes a path-injection vector.
      if ! [[ "$PROJECT" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
        echo "start-officer.sh: --project slug must match [a-z0-9][a-z0-9-]* (got '$PROJECT')" >&2
        exit 1
      fi
      if [ "${#PROJECT}" -gt 32 ]; then
        echo "start-officer.sh: --project slug must be ≤32 chars (got ${#PROJECT})" >&2
        exit 1
      fi
      POOL_MODE=true
      shift 2
      ;;
    *)
      echo "start-officer.sh: unknown argument '$1'" >&2
      echo "Usage: start-officer.sh <officer> [--project <slug>]" >&2
      exit 1
      ;;
  esac
done

CABINET_ROOT="${CABINET_ROOT:-/opt/founders-cabinet}"

OFFICER_ENV_LIB="$CABINET_ROOT/cabinet/scripts/lib/officer-env.sh"
if [ ! -f "$OFFICER_ENV_LIB" ]; then
  # Test fixtures invoke the real launcher with a synthetic CABINET_ROOT.
  OFFICER_ENV_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/officer-env.sh"
fi
if [ ! -f "$OFFICER_ENV_LIB" ]; then
  echo "start-officer.sh: clean-environment library missing — refusing officer boot" >&2
  exit 78
fi
# shellcheck source=lib/officer-env.sh
source "$OFFICER_ENV_LIB"
officer_env_scrub_authority

# Resolve observe-only before parsing credentials so the effective (CUA-free)
# MCP scope and the projected secret set remain in lockstep.
export CABINET_OBSERVE_ONLY=0
OBSERVE_CONTROL="$CABINET_ROOT/cabinet/scripts/observe-only.sh"
if [ ! -f "$OBSERVE_CONTROL" ]; then
  OBSERVE_CONTROL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/observe-only.sh"
fi
OBSERVE_STATE="$(bash "$OBSERVE_CONTROL" status)" || {
  echo "start-officer.sh: invalid observe-only marker — refusing officer boot" >&2
  exit 78
}
if [ "$OBSERVE_STATE" = active ]; then
  export CABINET_OBSERVE_ONLY=1
  export CABINET_ENV=dev
fi

# Parse the reviewed officer subset of the base env.  Never source the shared
# store: it also contains dashboard/session/verdict authority credentials.
if [ -f "$CABINET_ROOT/cabinet/.env" ]; then
  if ! officer_env_load_file "$CABINET_ROOT/cabinet/.env" "$OFFICER"; then
    echo "start-officer.sh: base officer environment rejected — refusing officer boot" >&2
    exit 78
  fi
fi

# Legacy Linux/Docker boots receive the same allowlisting proxy environment.
# Unlike the Mac launcher, this path has no Seatbelt layer, so raw sockets still
# require a host/container network policy (documented in the egress runbook).
EGRESS_GUARD="$CABINET_ROOT/cabinet/scripts/egress-guard.sh"
EGRESS_ENFORCE=0
EGRESS_ENV_FILE=""
if [ ! -f "$EGRESS_GUARD" ]; then
  if [ "${CABINET_TEST_DRY_RUN:-0}" != "1" ]; then
    echo "start-officer.sh: egress guard missing — refusing officer boot" >&2
    exit 78
  fi
elif [ "${CABINET_TEST_DRY_RUN:-0}" != "1" ]; then
  if ! bash "$EGRESS_GUARD" apply >&2; then
    echo "start-officer.sh: egress reconciliation failed — refusing officer boot" >&2
    exit 78
  fi
fi
if [ -f "$EGRESS_GUARD" ] && [ "${CABINET_TEST_DRY_RUN:-0}" != "1" ]; then
  EGRESS_RUNTIME="$(bash "$EGRESS_GUARD" runtime-state)" || {
    echo "start-officer.sh: cannot resolve egress runtime state — refusing officer boot" >&2
    exit 78
  }
  IFS=$'\t' read -r EGRESS_ENFORCE EGRESS_ENV_FILE <<< "$EGRESS_RUNTIME"
  if [ "$EGRESS_ENFORCE" = "1" ]; then
    if [ -f "$EGRESS_ENV_FILE" ]; then
      if ! officer_env_load_file "$EGRESS_ENV_FILE" "$OFFICER"; then
        echo "start-officer.sh: enforced egress environment rejected — refusing officer boot" >&2
        exit 78
      fi
    elif [ "${CABINET_TEST_DRY_RUN:-0}" != "1" ]; then
      echo "start-officer.sh: egress is enforced but proxy env is absent — refusing officer boot" >&2
      exit 78
    fi
  fi
fi

# Assemble runtime Cabinet state (framework + preset + instance) before
# launching the officer's Claude Code session. Idempotent — safe to run on
# every officer start. See cabinet/scripts/load-preset.sh.
bash "$CABINET_ROOT/cabinet/scripts/load-preset.sh" 2>&1 | tail -3 >&2

# Resolve project slug:
#   Pool mode: --project explicit (per-window scoping)
#   Legacy mode: fall back to instance/config/active-project.txt (single-project)
if [ "$POOL_MODE" = true ]; then
  ACTIVE_SLUG="$PROJECT"
  if [ ! -f "$CABINET_ROOT/cabinet/env/${ACTIVE_SLUG}.env" ]; then
    echo "start-officer.sh: pool mode requires cabinet/env/${ACTIVE_SLUG}.env" >&2
    echo "  (provision via cabinet/scripts/create-project.sh ${ACTIVE_SLUG})" >&2
    exit 1
  fi
else
  ACTIVE_SLUG=$(cat "$CABINET_ROOT/instance/config/active-project.txt" 2>/dev/null | tr -d '[:space:]')
  # [FIX-4 hardening] Legacy ACTIVE_SLUG flows into CABINET_LANE and the clean
  # one-shot officer environment. Whitespace stripping alone does NOT remove
  # `;`, `&&`, `$()`, or backticks, so a poisoned
  # active-project.txt (gitignored, normally written by bootstrap-project.sh with
  # a clean slug) would be a shell-injection / RCE seam in the Docker path. Mirror
  # the --project allowlist (pool mode, above) and the Mac script's read: reject
  # any non-conforming value by CLEARING it. Empty ACTIVE_SLUG is the fail-safe —
  # no CABINET_LANE export → resolve_lane falls through to PROJECT/None →
  # unmeasured cell → propose-only at the gate.
  if [ -n "$ACTIVE_SLUG" ] && { ! [[ "$ACTIVE_SLUG" =~ ^[a-z0-9][a-z0-9-]*$ ]] || [ "${#ACTIVE_SLUG}" -gt 32 ]; }; then
    echo "start-officer.sh: active-project.txt slug must match [a-z0-9][a-z0-9-]* (≤32) (got '$ACTIVE_SLUG')" >&2
    ACTIVE_SLUG=""
  fi
fi
if [ -n "$ACTIVE_SLUG" ] && [ -f "$CABINET_ROOT/cabinet/env/${ACTIVE_SLUG}.env" ]; then
  if ! officer_env_load_file "$CABINET_ROOT/cabinet/env/${ACTIVE_SLUG}.env" "$OFFICER" "$ACTIVE_SLUG"; then
    echo "start-officer.sh: project officer environment rejected — refusing officer boot" >&2
    exit 78
  fi
fi

# ---------------------------------------------------------------
# Bot mode resolution (FW-084 / Spec 034 v3 AC #62)
# ---------------------------------------------------------------
# Read bot_mode + ceo_officer from the active project YAML (if present).
# Fallback: multi_officer (legacy behavior, preserves all pre-FW-084 cabinets).
#
# YAML keys read:
#   telegram.bot_mode    — single_ceo | multi_officer
#   telegram.ceo_officer — officer slug that acts as CEO (default: cos)
#
# In single_ceo mode:
#   - CEO officer  → receives TELEGRAM_BOT_TOKEN from TELEGRAM_<SLUG>_CEO_TOKEN
#     and gets Telegram channel plugin (polls Telegram, receives Captain DMs).
#   - Non-CEO officers → no TELEGRAM_BOT_TOKEN injected, no --channels plugin:telegram
#     (they are Telegram-dark; Captain-attention goes via the queue instead).
#
# In multi_officer mode (legacy): all officers get their own bot token (existing behavior).
#
# Adversary note (FW-084): non-CEO officers in single_ceo mode must NOT have
# TELEGRAM_BOT_TOKEN set — this prevents the channels plugin from initializing
# and closes the "non-CEO bypasses queue" attack surface. The token env var is
# the initialization gate; without it the plugin cannot start.

BOT_MODE="multi_officer"  # safe default — preserves all existing behavior
CEO_OFFICER="cos"         # canonical default per AC #75

_read_yml_field() {
  local file="$1" key="$2"
  grep -E "^[[:space:]]*${key}:[[:space:]]" "$file" 2>/dev/null \
    | head -1 | sed "s/^[[:space:]]*${key}:[[:space:]]*//" | tr -d '"' | tr -d "'" | awk '{print $1}'
}

if [ -n "$ACTIVE_SLUG" ] && [ -f "$CABINET_ROOT/instance/config/projects/${ACTIVE_SLUG}.yml" ]; then
  _PROJECT_YML="$CABINET_ROOT/instance/config/projects/${ACTIVE_SLUG}.yml"
  _bot_mode_raw=$(_read_yml_field "$_PROJECT_YML" "bot_mode")
  _ceo_officer_raw=$(_read_yml_field "$_PROJECT_YML" "ceo_officer")
  # Validate: only accept known mode values (reject injection attempts)
  if [ "$_bot_mode_raw" = "single_ceo" ] || [ "$_bot_mode_raw" = "multi_officer" ]; then
    BOT_MODE="$_bot_mode_raw"
  fi
  # Validate: ceo_officer must match slug allowlist (mirrors FW-073 regex)
  if [[ "$_ceo_officer_raw" =~ ^[a-z0-9][a-z0-9-]*$ ]] && [ "${#_ceo_officer_raw}" -le 32 ]; then
    CEO_OFFICER="$_ceo_officer_raw"
  fi
fi

# FW-085 substrate gap #3: when no project YAML exists yet (first-spawn cabinet
# before any create-project.sh ran), fall back to preset-level bot_mode. Closes
# the "Step Network single_ceo cabinet first-spawn → start-officer defaults to
# multi_officer → looks for TELEGRAM_COS_TOKEN → exits" trap.
if [ "$BOT_MODE" = "multi_officer" ]; then
  _ACTIVE_PRESET=$(cat "$CABINET_ROOT/instance/config/active-preset" 2>/dev/null | tr -d '[:space:]')
  if [ -n "$_ACTIVE_PRESET" ] && [ -f "$CABINET_ROOT/presets/$_ACTIVE_PRESET/preset.yml" ]; then
    _PRESET_YML="$CABINET_ROOT/presets/$_ACTIVE_PRESET/preset.yml"
    _preset_bot_mode=$(_read_yml_field "$_PRESET_YML" "telegram_bot_mode")
    if [ "$_preset_bot_mode" = "single_ceo" ]; then
      BOT_MODE="single_ceo"
    fi
  fi
fi

# Dynamic bot token lookup — constructs env var name from officer abbreviation.
# Behavior differs by bot_mode (FW-084):
#
#   multi_officer: TELEGRAM_<UPPER_OFFICER>_TOKEN (existing behavior — unchanged)
#   single_ceo + OFFICER == CEO_OFFICER: TELEGRAM_<UPPER_SLUG>_CEO_TOKEN
#   single_ceo + OFFICER != CEO_OFFICER: no token; this officer is Telegram-dark

BOT_TOKEN=""
IS_CEO_OFFICER=false

if [ "$BOT_MODE" = "single_ceo" ]; then
  if [ "$OFFICER" = "$CEO_OFFICER" ]; then
    IS_CEO_OFFICER=true
    # FW-085 substrate gap #3 (token alias resolution): try project-level
    # token first, then cabinet-level fallback (CABINET_ID env), then plain
    # TELEGRAM_CEO_TOKEN. The cabinet-level form is the practical "single
    # project per cabinet" pattern Captain uses (e.g. orchard = newsletter).
    _CEO_TOKEN_CANDIDATES=()
    if [ -n "$ACTIVE_SLUG" ]; then
      _SLUG_UPPER="$(echo "${ACTIVE_SLUG^^}" | tr "-" "_")"
      _CEO_TOKEN_CANDIDATES+=("TELEGRAM_${_SLUG_UPPER}_CEO_TOKEN")
    fi
    if [ -n "${CABINET_ID:-}" ]; then
      _CABINET_UPPER="$(echo "${CABINET_ID^^}" | tr "-" "_")"
      _CEO_TOKEN_CANDIDATES+=("TELEGRAM_${_CABINET_UPPER}_CEO_TOKEN")
    fi
    _CEO_TOKEN_CANDIDATES+=("TELEGRAM_CEO_TOKEN")

    BOT_TOKEN=""
    for _candidate in "${_CEO_TOKEN_CANDIDATES[@]}"; do
      if [ -n "${!_candidate:-}" ]; then
        BOT_TOKEN="${!_candidate}"
        break
      fi
    done
    if [ -z "$BOT_TOKEN" ] && [ "$CABINET_OBSERVE_ONLY" = 1 ] \
        && [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
      BOT_TOKEN="$TELEGRAM_BOT_TOKEN"
    fi

    if [ -z "$BOT_TOKEN" ]; then
      echo "start-officer.sh: single_ceo mode — no CEO bot token found in env" >&2
      echo "  Tried (in order): ${_CEO_TOKEN_CANDIDATES[*]}" >&2
      echo "  Set ONE of these in cabinet/.env or cabinet/env/<slug>.env" >&2
      exit 1
    fi
  else
    # Non-CEO officer in single_ceo mode: Telegram-dark. No bot token needed.
    IS_CEO_OFFICER=false
    BOT_TOKEN=""
  fi
else
  # multi_officer mode (legacy): each officer has their own token
  TOKEN_VAR="TELEGRAM_$(echo "${OFFICER^^}" | tr "-" "_")_TOKEN"
  BOT_TOKEN="${!TOKEN_VAR:?$TOKEN_VAR not set in environment}"
fi

# Pool mode scopes tmux window AND working dir per (officer, project).
# Legacy mode keeps the single-officer layout intact (back-compat).
if [ "$POOL_MODE" = true ]; then
  WINDOW="officer-$OFFICER-$ACTIVE_SLUG"
  OFFICER_DIR="$CABINET_ROOT/officers/$OFFICER/$ACTIVE_SLUG"
else
  WINDOW="officer-$OFFICER"
  OFFICER_DIR="$CABINET_ROOT/officers/$OFFICER"
fi
STATE_DIR="/home/cabinet/.claude-channels/$OFFICER"

# Write the Telegram state .env only when this officer has a bot token.
# In single_ceo mode, non-CEO officers are Telegram-dark: no token written,
# so the channels plugin cannot initialize even if somehow invoked.
mkdir -p "$STATE_DIR/telegram"
if [ -n "$BOT_TOKEN" ]; then
  echo "TELEGRAM_BOT_TOKEN=$BOT_TOKEN" > "$STATE_DIR/telegram/.env"
else
  # Explicitly clear any stale token from a previous multi_officer run.
  # Without this, a restarted non-CEO officer could inherit the old token
  # and gain Telegram access it should not have (adversary surface FW-084).
  echo "" > "$STATE_DIR/telegram/.env"
fi

# Each officer gets their own working subdirectory so --continue resumes
# the correct session (Claude Code scopes sessions by working directory).
# In pool mode, each (officer, project) is its own working dir → distinct
# session per project, switchable via tmux select-window.
mkdir -p "$OFFICER_DIR"
ln -sfn "$CABINET_ROOT/CLAUDE.md" "$OFFICER_DIR/CLAUDE.md"
ln -sfn "$CABINET_ROOT/.claude" "$OFFICER_DIR/.claude"
ln -sfn "$CABINET_ROOT/constitution" "$OFFICER_DIR/constitution"
ln -sfn "$CABINET_ROOT/memory" "$OFFICER_DIR/memory"
ln -sfn "$CABINET_ROOT/shared" "$OFFICER_DIR/shared"
ln -sfn "$CABINET_ROOT/cabinet" "$OFFICER_DIR/cabinet"
ln -sfn "$CABINET_ROOT/framework" "$OFFICER_DIR/framework"
ln -sfn "$CABINET_ROOT/presets" "$OFFICER_DIR/presets"
ln -sfn "$CABINET_ROOT/instance" "$OFFICER_DIR/instance"

# Check if this officer has a previous session to continue
# Claude Code stores sessions in ~/.claude/projects/<encoded-path>/
ENCODED_PATH=$(echo "$OFFICER_DIR" | sed 's|/|-|g')
HAS_SESSION=false
if [ -d "/home/cabinet/.claude/projects/$ENCODED_PATH" ]; then
  HAS_SESSION=true
fi

# Build the claude command — use --continue only if a prior session exists
# Officer orchestrator model: Fable 5 + max effort (upgraded from Opus 4.7; originally ratified 2026-05-24 msg 2687).
# Fable drives the loop; subagents + crew use Sonnet 4.6 for cost-efficient parallel work.
# Override via CABINET_MODEL env (e.g., CABINET_MODEL=claude-sonnet-4-6 to downgrade).
# CABINET_MODEL=claude-fable-5[1m] is available as an opt-in override once verified interactively.
#
# FW-084 bot mode gating:
#   - multi_officer OR (single_ceo AND IS_CEO_OFFICER): include --channels plugin:telegram
#   - single_ceo AND non-CEO: omit telegram plugin entirely (officer is Telegram-dark)
MODEL="${CABINET_MODEL:-claude-fable-5}"

# Legacy/Linux now uses the same structural MCP filter as the Mac launcher.
# In observe-only the generator replaces every static grant with the closed
# local set {redis-trigger-channel, cabinet-comms}; remote MCPs never boot.
MCP_GENERATOR="$CABINET_ROOT/cabinet/scripts/gen-officer-mcp-config.py"
if [ ! -f "$MCP_GENERATOR" ]; then
  MCP_GENERATOR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/gen-officer-mcp-config.py"
fi
if [ ! -f "$MCP_GENERATOR" ]; then
  echo "start-officer.sh: MCP config generator missing — refusing officer boot" >&2
  exit 78
fi
if [ "${CABINET_TEST_DRY_RUN:-0}" = "1" ]; then
  OFFICER_CFG_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cabinet-mcp-dryrun.XXXXXX")"
else
  OFFICER_CFG_DIR="${XDG_CACHE_HOME:-${HOME:-/home/cabinet}/.cache}/cabinet"
  mkdir -p "$OFFICER_CFG_DIR"
  chmod 700 "$OFFICER_CFG_DIR"
fi
OFFICER_MCP_PATH="$OFFICER_CFG_DIR/officer-mcp-${OFFICER}.json"
OFFICER_SETTINGS_PATH="$OFFICER_CFG_DIR/officer-settings-${OFFICER}.json"
GEN_MCP_ARGS=(
  --officer "$OFFICER"
  --scope "$CABINET_ROOT/cabinet/mcp-scope.yml"
  --input "$CABINET_ROOT/.mcp.json"
)
[ "$CABINET_OBSERVE_ONLY" = 1 ] && GEN_MCP_ARGS+=(--observe-only)
GEN_MCP_ARGS+=(
  --out-mcp "$OFFICER_MCP_PATH"
  --out-settings "$OFFICER_SETTINGS_PATH"
)
if ! python3.12 "$MCP_GENERATOR" \
      "${GEN_MCP_ARGS[@]}"; then
  echo "start-officer.sh: MCP config generation failed — FAIL CLOSED" >&2
  ( umask 077
    printf '{"mcpServers":{}}\n' > "$OFFICER_MCP_PATH"
    printf '{"enableAllProjectMcpServers":false}\n' > "$OFFICER_SETTINGS_PATH"
  )
fi
MCP_FLAGS="--mcp-config $OFFICER_MCP_PATH --strict-mcp-config --settings $OFFICER_SETTINGS_PATH"

_BASE_FLAGS="--model $MODEL $MCP_FLAGS --dangerously-load-development-channels server:redis-trigger-channel --dangerously-skip-permissions --effort max"
if [ "$CABINET_OBSERVE_ONLY" = 1 ]; then
  # Watchdog owns inbound during the soak; a second channels poller would race
  # getUpdates and would widen the observe surface beyond cabinet-comms.
  _CHANNEL_FLAGS=""
elif [ "$BOT_MODE" = "single_ceo" ] && [ "$IS_CEO_OFFICER" = false ]; then
  # Non-CEO in single_ceo mode: no Telegram plugin. Officer operates headless —
  # Captain-attention reaches Captain via the queue (cabinet:captain-attention:<project>).
  _CHANNEL_FLAGS=""
else
  # CEO officer OR multi_officer mode: include Telegram plugin as before.
  _CHANNEL_FLAGS="--channels plugin:telegram@claude-plugins-official"
fi
if [ "$HAS_SESSION" = true ]; then
  CLAUDE_CMD="claude --continue $_BASE_FLAGS $_CHANNEL_FLAGS"
else
  CLAUDE_CMD="claude $_BASE_FLAGS $_CHANNEL_FLAGS"
fi

# Per-window env injection. CABINET_ACTIVE_PROJECT is set ONLY in pool mode
# so legacy single-project deployments preserve the FW-072 cost-counter
# legacy field shape (`<officer>_<dim>`); pool mode opts into the per-project
# shape (`<officer>_<project>_<dim>`). Defensive unset before the conditional
# guards against env-file pollution: if a future reviewed env-parser change
# ever admits CABINET_ACTIVE_PROJECT, the unset ensures only the pool-mode
# branch can write it into the officer environment.
unset CABINET_ACTIVE_PROJECT
# [FIX-4] CABINET_LANE is LOAD-BEARING: framework/authority/lane.py resolve_lane()
# reads it FIRST as the lane dimension of the F+A cell tuple (officer, lane,
# action_type). It is derived from the SAME project/active-context machinery as
# CABINET_ACTIVE_PROJECT (ACTIVE_SLUG: --project in pool mode, else
# instance/config/active-project.txt). Defensive unset mirrors the
# CABINET_ACTIVE_PROJECT scrub above so a sourced cabinet/env/<slug>.env can't
# leak a stale lane into the subshell. Exported ONLY when a slug is resolved —
# an empty CABINET_LANE would shadow PROJECT in resolve_lane; omitting it lets
# resolve_lane fall through to PROJECT then None (fail-safe → unmeasured cell).
unset CABINET_LANE
# FW-084: in single_ceo mode, non-CEO officers do NOT get TELEGRAM_BOT_TOKEN or
# TELEGRAM_HQ_CHAT_ID — they are Telegram-dark. CEO officer gets both as before.
# multi_officer mode (legacy): all officers get full Telegram env (unchanged).
if [ "$BOT_MODE" = "single_ceo" ] && [ "$IS_CEO_OFFICER" = false ]; then
  # Non-CEO: no Telegram env vars. Captain-attention flows via queue.
  EXPORT_VARS="OFFICER_NAME=$OFFICER TELEGRAM_STATE_DIR=$STATE_DIR CABINET_BOT_MODE=$BOT_MODE CABINET_CEO_OFFICER=$CEO_OFFICER"
else
  # CEO or multi_officer: full Telegram env
  EXPORT_VARS="OFFICER_NAME=$OFFICER TELEGRAM_STATE_DIR=$STATE_DIR TELEGRAM_BOT_TOKEN=$BOT_TOKEN TELEGRAM_HQ_CHAT_ID=$TELEGRAM_HQ_CHAT_ID CABINET_BOT_MODE=$BOT_MODE CABINET_CEO_OFFICER=$CEO_OFFICER"
fi
if [ "$POOL_MODE" = true ]; then
  EXPORT_VARS="$EXPORT_VARS CABINET_ACTIVE_PROJECT=$ACTIVE_SLUG"
fi
# [FIX-4] Export the resolved lane in BOTH pool and legacy modes — wherever a
# project/active-context slug exists, the authority gate's resolve_lane() must
# see it. ACTIVE_SLUG is allowlist-constrained in BOTH modes (pool mode: slug
# regex [a-z0-9][a-z0-9-]* ≤32, line 29; legacy: same regex applied to the
# active-project.txt value, line 73 — non-conforming values are cleared), so it
# carries no shell metacharacters and is safe to word-split out of the unquoted
# `export $EXPORT_VARS`. When empty (legacy, no/invalid active-project.txt) it is
# NOT exported (fail-safe → resolve_lane falls through to PROJECT/None).
if [ -n "$ACTIVE_SLUG" ]; then
  EXPORT_VARS="$EXPORT_VARS CABINET_LANE=$ACTIVE_SLUG"
fi

# Materialize the resolved runtime values in this launcher shell, then build a
# safely shell-quoted env -i prefix.  This avoids the old unquoted
# `export $EXPORT_VARS` pane command and prevents stale tmux-global variables
# (including a dashboard password) from reaching Claude.
export OFFICER_NAME="$OFFICER"
export CABINET_OFFICER="$OFFICER"
export TELEGRAM_STATE_DIR="$STATE_DIR"
export CABINET_BOT_MODE="$BOT_MODE"
export CABINET_CEO_OFFICER="$CEO_OFFICER"
if [ "$BOT_MODE" = "single_ceo" ] && [ "$IS_CEO_OFFICER" = false ]; then
  unset TELEGRAM_BOT_TOKEN TELEGRAM_HQ_CHAT_ID
else
  export TELEGRAM_BOT_TOKEN="$BOT_TOKEN"
  export TELEGRAM_HQ_CHAT_ID="${TELEGRAM_HQ_CHAT_ID:-}"
fi
if [ "$POOL_MODE" = true ]; then
  export CABINET_ACTIVE_PROJECT="$ACTIVE_SLUG"
fi
if [ -n "$ACTIVE_SLUG" ]; then
  export CABINET_LANE="$ACTIVE_SLUG"
fi
OFFICER_ENV_PREFIX="$(officer_env_command_prefix)"

# Test hook: CABINET_TEST_DRY_RUN=1 dumps resolved arg-derived contracts and
# exits before any side-effectful tmux/claude calls. Used by the FW-073
# test harness to pin arg parsing + back-compat without spawning real sessions.
# FW-084: also exposes BOT_MODE, CEO_OFFICER, IS_CEO_OFFICER for test assertions.
if [ "${CABINET_TEST_DRY_RUN:-}" = "1" ]; then
  DISPLAY_EXPORT_VARS="$(printf '%s' "$EXPORT_VARS" | sed -E 's/(TELEGRAM_BOT_TOKEN=)[^ ]*/\1<redacted>/g')"
  printf 'POOL_MODE=%s\nWINDOW=%s\nOFFICER_DIR=%s\nACTIVE_SLUG=%s\nEXPORT_VARS=%s\nBOT_MODE=%s\nCEO_OFFICER=%s\nIS_CEO_OFFICER=%s\n' \
    "$POOL_MODE" "$WINDOW" "$OFFICER_DIR" "$ACTIVE_SLUG" "$DISPLAY_EXPORT_VARS" \
    "$BOT_MODE" "$CEO_OFFICER" "$IS_CEO_OFFICER"
  rm -rf -- "$OFFICER_CFG_DIR"
  exit 0
fi

# Prepare the launch command in a mode-0700, self-unlinking script.  The env -i
# prefix contains credentials and must never be typed into tmux pane history.
printf -v _OFFICER_DIR_Q '%q' "$OFFICER_DIR"
LAUNCH_COMMAND="cd $_OFFICER_DIR_Q && exec $OFFICER_ENV_PREFIX $CLAUDE_CMD"
LAUNCH_DIR="${XDG_CACHE_HOME:-/home/cabinet/.cache}/cabinet/officer-launch"
LAUNCH_SCRIPT="$(officer_env_write_one_shot_launcher "$LAUNCH_DIR" "$LAUNCH_COMMAND")"

# Kill any existing session for this (officer, project) tuple
tmux kill-window -t "cabinet:$WINDOW" 2>/dev/null

# Start Claude Code session
if ! tmux new-window -t cabinet -n "$WINDOW" -c "$OFFICER_DIR" \
    /usr/bin/env -i HOME="${HOME:-/home/cabinet}" PATH="$PATH" \
    USER="${USER:-cabinet}" LOGNAME="${LOGNAME:-cabinet}" SHELL=/bin/bash \
    /bin/bash --noprofile --norc "$LAUNCH_SCRIPT"; then
  rm -f "$LAUNCH_SCRIPT"
  echo "start-officer.sh: tmux failed to start $OFFICER" >&2
  exit 1
fi
for _try in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  [ ! -e "$LAUNCH_SCRIPT" ] && break
  sleep 0.05
done
if [ -e "$LAUNCH_SCRIPT" ]; then
  rm -f "$LAUNCH_SCRIPT"
  tmux kill-window -t "cabinet:$WINDOW" 2>/dev/null || true
  echo "start-officer.sh: one-shot launcher was not consumed — refusing officer boot" >&2
  exit 78
fi

# Wait for Claude Code to initialize, auto-confirm any startup prompts, then
# send the boot prompt. The prompt-handling + boot-submit logic is shared with
# start-officer-mac.sh via lib/officer-boot.sh (officer_boot_drive) so a fix
# lands ONCE for both platforms — see that file for the full rationale.
(
  # shellcheck source=lib/officer-boot.sh
  source /opt/founders-cabinet/cabinet/scripts/lib/officer-boot.sh
  BOOT_PROMPT="You are $OFFICER. Read your role definition at .claude/agents/$OFFICER.md and your session start checklist.$(officer_role_registry_clause /opt/founders-cabinet "$OFFICER") Read your foundation skills in memory/skills/. Read your tier 2 notes in instance/memory/tier2/$OFFICER/. Then announce yourself on the warroom: bash /opt/founders-cabinet/cabinet/scripts/send-to-group.sh '<b>$OFFICER online.</b> Session started. Checking for pending work.' — then check for pending triggers and overdue work immediately."
  officer_boot_drive "cabinet:$WINDOW" "$BOOT_PROMPT"
  # No permanent /loop needed — Redis Trigger Channel delivers all triggers
  # and scheduled work instantly. /loop is available for ad-hoc use only.
) &

if [ "$POOL_MODE" = true ]; then
  echo "Started $OFFICER (project=$ACTIVE_SLUG) in cabinet:$WINDOW (has_session=$HAS_SESSION, loop in ~20s)"
else
  echo "Started $OFFICER in cabinet:$WINDOW (has_session=$HAS_SESSION, loop in ~20s)"
fi
