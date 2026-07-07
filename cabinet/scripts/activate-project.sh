#!/bin/bash
# activate-project.sh - onboard an existing project into the Cabinet runtime.

set -euo pipefail

SLUG="${1:-}"
shift 2>/dev/null || true

REPO_PATH=""
REPO_URL=""
NAME=""
DESCRIPTION=""
BRANCH="main"
ACTIVATE=0
DRY_RUN=0
NOTES=""

usage() {
  echo "Usage: activate-project.sh <slug> (--repo-path <path> | --repo-url <url>) --name <name> [--description <text>] [--branch <branch>] [--activate] [--dry-run]" >&2
  exit 64
}

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-path) REPO_PATH="${2:?--repo-path requires a path}"; shift 2 ;;
    --repo-url) REPO_URL="${2:?--repo-url requires a URL}"; shift 2 ;;
    --name) NAME="${2:?--name requires a value}"; shift 2 ;;
    --description) DESCRIPTION="${2:?--description requires a value}"; shift 2 ;;
    --branch) BRANCH="${2:?--branch requires a value}"; shift 2 ;;
    --activate) ACTIVATE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --notes) NOTES="${2:?--notes requires a value}"; shift 2 ;;
    *) echo "activate-project.sh: unknown flag '$1'" >&2; usage ;;
  esac
done

[ -n "$SLUG" ] || usage
[ -n "$NAME" ] || usage
if [ -n "$REPO_PATH" ] && [ -n "$REPO_URL" ]; then
  echo "activate-project.sh: pass exactly one of --repo-path or --repo-url" >&2
  exit 64
fi
if [ -z "$REPO_PATH" ] && [ -z "$REPO_URL" ]; then
  echo "activate-project.sh: pass --repo-path or --repo-url" >&2
  exit 64
fi
if ! [[ "$SLUG" =~ ^[a-z0-9][a-z0-9-]{0,31}$ ]]; then
  echo "activate-project.sh: slug must match ^[a-z0-9][a-z0-9-]{0,31}$" >&2
  exit 64
fi

if [ -z "${CABINET_ROOT:-}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  CABINET_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
fi
PROJECTS_DIR="$CABINET_ROOT/instance/config/projects"
PROJECT_FILE="$PROJECTS_DIR/${SLUG}.yml"
ACTIVE_FILE="$CABINET_ROOT/instance/config/active-project.txt"
ORG="$CABINET_ROOT/cabinet/scripts/org-runtime.py"
PRODUCT_REPO_ROOT="${PRODUCT_REPO_ROOT:-$CABINET_ROOT/projects}"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$CABINET_ROOT/workspace}"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

log() { echo "[activate-project] $1"; }
dry() { echo "[DRY-RUN] $1"; }

yaml_quote() {
  python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$1"
}

repo_mode() {
  if [ -n "$REPO_PATH" ]; then
    echo "existing_repo_path"
  else
    echo "existing_repo_url"
  fi
}

activation_status() {
  if [ "$ACTIVATE" = "1" ]; then
    echo "active"
  else
    echo "prepared"
  fi
}

activated_at() {
  if [ "$ACTIVATE" = "1" ]; then
    date -u '+%Y-%m-%dT%H:%M:%SZ'
  else
    echo ""
  fi
}

resolve_repo_path() {
  local raw="$1"
  if [ ! -d "$raw/.git" ]; then
    echo "activate-project.sh: --repo-path must point at a git working tree: $raw" >&2
    exit 1
  fi
  (cd "$raw" && pwd)
}

repo_ref=""
repo_source=""
if [ -n "$REPO_PATH" ]; then
  repo_source="$(resolve_repo_path "$REPO_PATH")"
  repo_ref="$(git -C "$repo_source" remote get-url origin 2>/dev/null || echo "$repo_source")"
else
  if ! echo "$REPO_URL" | grep -qE '^(https?://|git://|git@|ssh://)'; then
    echo "activate-project.sh: --repo-url does not look like a git URL" >&2
    exit 64
  fi
  repo_source="$PRODUCT_REPO_ROOT/$SLUG"
  repo_ref="$REPO_URL"
fi

MOUNT_PATH="$WORKSPACE_ROOT/$SLUG"
MODE="$(repo_mode)"
STATUS="$(activation_status)"
ACTIVATED_AT="$(activated_at)"

record_event() {
  local type="$1"
  local payload
  payload="$(jq -nc \
    --arg slug "$SLUG" \
    --arg name "$NAME" \
    --arg repo "$repo_ref" \
    --arg repo_source "$repo_source" \
    --arg mode "$MODE" \
    --arg status "$STATUS" \
    --arg mount_path "$MOUNT_PATH" \
    --arg activated_at "$ACTIVATED_AT" \
    '{slug:$slug,name:$name,repo:$repo,repo_source:$repo_source,mode:$mode,status:$status,mount_path:$mount_path,activated_at:$activated_at}')"
  python3 "$ORG" org-event append \
    --product-slug "$SLUG" \
    --type "$type" \
    --aggregate-type project_activation \
    --aggregate-id "$SLUG" \
    --actor cos \
    --source activate-project \
    --payload "$payload" >/dev/null
}

write_project_file() {
  mkdir -p "$PROJECTS_DIR"
  if [ ! -f "$PROJECT_FILE" ]; then
    local template="$PROJECTS_DIR/_template.yml"
    if [ ! -f "$template" ]; then
      echo "activate-project.sh: missing template: $template" >&2
      exit 1
    fi
    {
      echo "# ============================================================="
      echo "# Project: $NAME"
      echo "# Activated: $ACTIVATED_AT"
      echo "# Repo: $repo_ref"
      echo "# ============================================================="
      echo ""
      NAME_Q="$(yaml_quote "$NAME")" \
      DESCRIPTION_Q="$(yaml_quote "$DESCRIPTION")" \
      REPO_Q="$(yaml_quote "$repo_ref")" \
      BRANCH_VALUE="$BRANCH" \
      MOUNT_VALUE="$MOUNT_PATH" \
      python3 - "$template" <<'PY'
import os
import sys
from pathlib import Path

lines = Path(sys.argv[1]).read_text().splitlines()
while lines and (not lines[0].strip() or lines[0].lstrip().startswith("#")):
    lines.pop(0)
text = "\n".join(lines) + "\n"
replacements = {
    'name: ""': f"name: {os.environ['NAME_Q']}",
    'description: ""': f"description: {os.environ['DESCRIPTION_Q']}",
    'repo: ""': f"repo: {os.environ['REPO_Q']}",
    'repo_branch: main': f"repo_branch: {os.environ['BRANCH_VALUE']}",
    'mount_path: ""': f"mount_path: {os.environ['MOUNT_VALUE']}",
}
for old, new in replacements.items():
    text = text.replace(old, new, 1)
print(text, end="")
PY
    } > "$PROJECT_FILE"
  fi
  update_activation_section
}

update_activation_section() {
  local tmp
  tmp="$(mktemp)"
  awk '
    /^activation:[[:space:]]*$/ { skip=1; next }
    /^[A-Za-z0-9_-]+:[[:space:]]*$/ && skip { skip=0 }
    !skip { print }
  ' "$PROJECT_FILE" > "$tmp"
  {
    echo ""
    echo "activation:"
    echo "  status: $STATUS"
    echo "  mode: $MODE"
    echo "  activated_at: $(yaml_quote "$ACTIVATED_AT")"
    echo "  activation_mission_id: \"\""
    echo "  notes: $(yaml_quote "$NOTES")"
  } >> "$tmp"
  mv "$tmp" "$PROJECT_FILE"
}

prepare_repo() {
  if [ -n "$REPO_URL" ]; then
    mkdir -p "$PRODUCT_REPO_ROOT"
    if [ -d "$repo_source/.git" ]; then
      log "Repo already exists: $repo_source"
    else
      git clone --branch "$BRANCH" "$REPO_URL" "$repo_source"
    fi
  fi
  mkdir -p "$WORKSPACE_ROOT"
  ln -sfn "$repo_source" "$MOUNT_PATH"
}

activate_project() {
  echo "$SLUG" > "$ACTIVE_FILE"
  if command -v redis-cli >/dev/null 2>&1; then
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "cabinet:active-project" "$SLUG" >/dev/null 2>&1 || true
  fi
  CABINET_ROOT="$CABINET_ROOT" bash "$CABINET_ROOT/cabinet/scripts/assemble-config.sh"
}

if [ "$DRY_RUN" = "1" ]; then
  dry "Would record project.activation_preflight for $SLUG"
  dry "Would prepare repo source $repo_source and mount $MOUNT_PATH"
  dry "Would write or update $PROJECT_FILE with activation.status=$STATUS"
  if [ "$ACTIVATE" = "1" ]; then
    dry "Would set active project and assemble instance/config/product.yml"
    dry "Would record project.activated for $SLUG"
  fi
  exit 0
fi

record_event "project.activation_preflight"
prepare_repo
write_project_file
if [ "$ACTIVATE" = "1" ]; then
  activate_project
  record_event "project.activated"
fi

log "Project $SLUG $STATUS (repo=$repo_source mount=$MOUNT_PATH)"
