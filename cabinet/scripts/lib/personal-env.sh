#!/bin/bash
# personal-env.sh — PersonalSource-adapter shared-env indirection for the
# cabinet/scripts/run-*.sh launchd wrappers (operative-egg plan R070).
#
# Shell mirror of framework.env.shared_env_path() — the resolver that lifted
# the launcher's personal-pipes credential path OUT of universal framework code
# (action_exec._load_shared_env + actfirst_canary's env-perms check). Same
# seam, shell side: WHICH shared credentials .env (if any) backs this
# deployment's PersonalSource adapter is INSTANCE DATA — a sibling of the
# adapter binding in instance/config/sources.yml — so the runner layer carries
# no personal-source path of its own. A clean-room / Flavor-B deployment
# (NullPersonalSource) configures nothing and every helper below quietly
# no-ops: nothing sourced, nothing crashes, downstream code fails closed on
# its own missing keys.
#
# Resolution order (mirrors framework/env.py::shared_env_path):
#   1. $CABINET_SHARED_ENV — explicit per-process override. Non-empty wins;
#      an empty value never claims the slot (empty-env doctrine).
#   2. top-level `shared_env_path:` in $ROOT/instance/config/platform.yml,
#      else product.yml (first hit wins). A leading `~` is expanded here —
#      the Python resolver returns the value verbatim and its callers
#      expanduser(); shell callers need a usable path.
#   3. "" — no shared env configured: personal_env_source is a no-op.
#
# Usage (from a run-*.sh wrapper, after ROOT is set):
#   . "$ROOT/cabinet/scripts/lib/personal-env.sh"
#   personal_env_source            # plain overwrite source — call AFTER
#                                  # sourcing cabinet/.env so REAL keys win
#                                  # over its empty placeholders (the
#                                  # run-undo-sweep.sh env-order gotcha)
#   f="$(personal_env_file)"       # or resolve only, for single-key reads
#
# set -u safe (every expansion guarded). No personal-source literal lives in
# this file or in any wrapper — the concrete path lives ONLY in
# instance/config/platform.yml (shared_env_path).

# Repo root: honor CABINET_ROOT, else self-locate (this file lives at
# cabinet/scripts/lib/, three levels below the repo root).
_PERSONAL_ENV_ROOT="${CABINET_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

# Print the resolved shared-env path ("" when none is configured).
personal_env_file() {
  local p=""
  if [ -n "${CABINET_SHARED_ENV:-}" ]; then
    p="$CABINET_SHARED_ENV"
  else
    local cfg
    for cfg in "$_PERSONAL_ENV_ROOT/instance/config/platform.yml" \
               "$_PERSONAL_ENV_ROOT/instance/config/product.yml"; do
      [ -f "$cfg" ] || continue
      p="$(sed -n 's/^shared_env_path:[[:space:]]*//p' "$cfg" | head -n 1)"
      p="${p%%#*}"                                  # strip inline comment
      p="$(printf '%s' "$p" \
             | sed -e 's/[[:space:]]*$//' \
                   -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'\$/\1/")"
      [ -n "$p" ] && break
    done
  fi
  case "$p" in
    "~")   p="${HOME:-}" ;;
    "~/"*) p="${HOME:-}${p#\~}" ;;
  esac
  printf '%s\n' "$p"
}

# Source the resolved shared env (set -a, plain overwrite semantics — later
# assignment wins, which is exactly why wrappers call this AFTER cabinet/.env).
# Missing/unconfigured file → silent no-op (clean-room / NullPersonalSource).
personal_env_source() {
  local _pe_file
  _pe_file="$(personal_env_file)"
  if [ -n "$_pe_file" ] && [ -f "$_pe_file" ]; then
    set -a
    . "$_pe_file"
    set +a
  fi
}
