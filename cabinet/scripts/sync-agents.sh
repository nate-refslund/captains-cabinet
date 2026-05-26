#!/bin/bash
# sync-agents.sh — Sync preset agent definitions into .claude/agents/.
#
# Purpose
# -------
# Claude Code v2.1.150+ discovers project subagents from `.claude/agents/*.md`
# (see https://code.claude.com/docs/en/sub-agents). On a fresh clone or worktree,
# that directory only holds `.gitkeep` — every other file is generated. This
# script populates `.claude/agents/` from `presets/<active>/agents/*.md` so the
# `claude --agent <officer>` flag in start-officer-mac.sh resolves correctly.
#
# This is a focused, idempotent helper. It does ONE thing — copy agent role
# definitions for the hired roster — and intentionally does NOT touch:
#   - the assembled constitution/safety boundaries at /tmp/cabinet-runtime/
#   - Neon/cabinet-postgres schemas
#   - Redis "expected-active" markers
#
# The wider activation flow (load-preset.sh) still does all of the above,
# including its own inline copy of these agent files; sync-agents.sh exists as
# a standalone script that:
#   (a) setup scripts can invoke without dragging in DB connections, and
#   (b) developers can run by hand to refresh `.claude/agents/` after editing
#       a preset role definition.
#
# Hired roster source of truth: `cabinet/mcp-scope.yml` — agents listed under
# `agents:` are hired; agents under `scaffolds:` are reserved but skipped.
# (load-preset.sh uses the same source — keep them in lockstep.)
#
# Usage:
#   bash cabinet/scripts/sync-agents.sh         # use active preset from instance/config/active-preset
#   bash cabinet/scripts/sync-agents.sh <slug>  # force a specific preset
#
# Exit codes:
#   0  — success (sync completed; may have copied 0 files if hired list empty)
#   1  — fatal error (preset missing, mcp-scope.yml missing, malformed scope)
#   2  — usage error

set -uo pipefail

# ---------------------------------------------------------------
# Script-relative CABINET_ROOT (R4/R5 pattern, mirrors load-preset.sh fallback)
# ---------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CABINET_ROOT_DEFAULT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CABINET_ROOT="${CABINET_ROOT:-$CABINET_ROOT_DEFAULT}"

ACTIVE_PRESET_FILE="$CABINET_ROOT/instance/config/active-preset"
MCP_SCOPE_FILE="$CABINET_ROOT/cabinet/mcp-scope.yml"
AGENTS_DIR="$CABINET_ROOT/.claude/agents"
INSTANCE_OVERLAY_DIR="$CABINET_ROOT/instance/agents"

log() {
  echo "[sync-agents $(date -u +%H:%M:%S)] $1" >&2
}

# ---------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------
FORCED_PRESET=""
case "${1:-}" in
  -h|--help)
    sed -n '2,/^# Exit codes:/p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  "")
    : # use active-preset file
    ;;
  -*)
    log "ERROR: unknown flag: $1"
    exit 2
    ;;
  *)
    FORCED_PRESET="$1"
    ;;
esac

# ---------------------------------------------------------------
# Resolve active preset
# ---------------------------------------------------------------
if [ -n "$FORCED_PRESET" ]; then
  ACTIVE_PRESET="$FORCED_PRESET"
elif [ -f "$ACTIVE_PRESET_FILE" ]; then
  ACTIVE_PRESET=$(tr -d '[:space:]' < "$ACTIVE_PRESET_FILE")
else
  ACTIVE_PRESET="work"
  log "WARN: $ACTIVE_PRESET_FILE not found — defaulting to 'work'"
fi

PRESET_DIR="$CABINET_ROOT/presets/$ACTIVE_PRESET"
if [ ! -d "$PRESET_DIR" ]; then
  log "ERROR: preset '$ACTIVE_PRESET' not found at $PRESET_DIR"
  exit 1
fi

if [ "$ACTIVE_PRESET" = "_template" ]; then
  log "ERROR: _template is not a loadable preset"
  exit 1
fi

if [ ! -d "$PRESET_DIR/agents" ]; then
  log "ERROR: preset '$ACTIVE_PRESET' has no agents/ directory at $PRESET_DIR/agents"
  exit 1
fi

# ---------------------------------------------------------------
# Resolve hired roster from mcp-scope.yml
# Single source of truth — `agents:` section, two-space indented slugs.
# Matches load-preset.sh:list_hired_agents() exactly so the two paths agree.
# ---------------------------------------------------------------
list_hired_agents() {
  [ -f "$MCP_SCOPE_FILE" ] || return
  awk '
    /^agents:[[:space:]]*$/     { section = "agents"; next }
    /^scaffolds:[[:space:]]*$/  { section = "scaffolds"; next }
    /^[A-Za-z]/                 { section = "" }
    section == "agents" && /^  [A-Za-z][A-Za-z0-9_-]*:[[:space:]]*$/ {
      name = $0
      sub(/^  /, "", name)
      sub(/:.*$/, "", name)
      print name
    }
  ' "$MCP_SCOPE_FILE"
}

if [ ! -f "$MCP_SCOPE_FILE" ]; then
  log "ERROR: $MCP_SCOPE_FILE missing — cannot determine hired roster"
  exit 1
fi

HIRED=$(list_hired_agents)
if [ -z "$HIRED" ]; then
  log "WARN: no agents listed under 'agents:' in $MCP_SCOPE_FILE — nothing to sync"
  mkdir -p "$AGENTS_DIR"
  exit 0
fi

# ---------------------------------------------------------------
# Copy preset agents (baseline)
# Idempotent: cp will replace any existing file with the same name.
# ---------------------------------------------------------------
mkdir -p "$AGENTS_DIR"

copied=0
skipped=0
missing=0
for slug in $HIRED; do
  src="$PRESET_DIR/agents/$slug.md"
  if [ ! -f "$src" ]; then
    log "WARN: hired agent '$slug' has no role definition at $src — skipping"
    missing=$((missing + 1))
    continue
  fi

  # Sanity check: every preset agent file MUST start with `---` (YAML frontmatter).
  # CC subagents without frontmatter become orphan markdown files — they won't
  # have a `name` field and won't be discoverable. Fail loud rather than silently
  # ship a broken roster.
  first_line=$(head -1 "$src")
  if [ "$first_line" != "---" ]; then
    log "ERROR: $src does not start with YAML frontmatter ('---'). Refusing to copy."
    log "       Every preset agent must declare name + description in frontmatter."
    exit 1
  fi

  cp "$src" "$AGENTS_DIR/$slug.md"
  copied=$((copied + 1))
done

# Skip the staged scaffolds that exist in the preset but aren't hired.
for src in "$PRESET_DIR/agents"/*.md; do
  [ -f "$src" ] || continue
  base=$(basename "$src")
  [ "$base" = "TEMPLATE.md" ] && continue
  slug="${base%.md}"
  if ! echo "$HIRED" | grep -qx "$slug"; then
    skipped=$((skipped + 1))
  fi
done

log "Preset baseline: copied=$copied skipped(scaffolds)=$skipped missing(hired-but-undefined)=$missing"

# ---------------------------------------------------------------
# Instance overlay (highest precedence)
# instance/agents/*.md beats preset baseline. Mirrors load-preset.sh behavior.
# ---------------------------------------------------------------
if [ -d "$INSTANCE_OVERLAY_DIR" ]; then
  overlay_count=0
  for src in "$INSTANCE_OVERLAY_DIR"/*.md; do
    [ -f "$src" ] || continue
    base=$(basename "$src")
    cp "$src" "$AGENTS_DIR/$base"
    log "Instance overlay applied: $base"
    overlay_count=$((overlay_count + 1))
  done
  [ "$overlay_count" -gt 0 ] && log "Instance overlay: $overlay_count file(s)"
fi

log "Agent sync complete — preset='$ACTIVE_PRESET' agents_dir='$AGENTS_DIR'"
exit 0
