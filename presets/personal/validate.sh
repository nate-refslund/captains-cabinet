#!/usr/bin/env bash
# presets/personal/validate.sh
# Preset validation gate. Run by cabinet-spawn.sh / cabinet-bootstrap.sh BEFORE
# any container starts; a MISSING validate.sh is itself a hard-gate failure
# (cabinet-bootstrap.sh: "Preset '<slug>' has no validate.sh — cannot pass hard
# gate"), which is one of the concrete reasons this preset could not be
# activated before 2026-07-27.
#
# Mirrors presets/portfolio/validate.sh, MINUS the lane-CEO template arm: this
# preset has no lanes and generates no per-lane officer. It adds one arm the
# others do not need — the roster must stay free of C-suite archetypes, which
# is this preset's entire reason to exist.

set -euo pipefail

PRESET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PRESET_NAME="$(basename "$PRESET_DIR")"

fail() {
  echo "Preset $PRESET_NAME validation FAILED: $1" >&2
  exit 1
}

ok() {
  echo "✓ $1"
}

echo "→ Validating preset: $PRESET_NAME"

# 1. Required-files presence
required_files=(
  "preset.yml"
  "constitution-addendum.md"
  "safety-addendum.md"
  "schemas.sql"
  "terminology.yml"
  "agents"
  "measurement/scenarios"
)

for f in "${required_files[@]}"; do
  if [ ! -e "$PRESET_DIR/$f" ]; then
    fail "missing required: $f"
  fi
done
ok "all required files present"

# 2. Addenda non-empty + length sanity (no placeholder-only)
for addendum in constitution-addendum.md safety-addendum.md; do
  size=$(wc -c < "$PRESET_DIR/$addendum")
  if [ "$size" -lt 200 ]; then
    fail "$addendum is suspiciously short ($size bytes; <200 = likely placeholder)"
  fi
done
ok "addenda non-empty"

# 3. preset.yml schema check (key fields)
preset_yml="$PRESET_DIR/preset.yml"
for key in name description naming_style agent_archetypes terminology workspace_mount; do
  if ! grep -q "^${key}:" "$preset_yml"; then
    fail "preset.yml missing required key: $key"
  fi
done
ok "preset.yml schema valid"

# 4. Agent role-defs parse (frontmatter + non-empty body)
agents_dir="$PRESET_DIR/agents"
if [ -z "$(ls -A "$agents_dir" 2>/dev/null | grep -v README)" ]; then
  if [ ! -f "$agents_dir/README.md" ]; then
    fail "agents/ is empty and no README.md describing inheritance source"
  fi
  ok "agents/ uses inheritance README pattern"
else
  for agent_md in "$agents_dir"/*.md; do
    [ -e "$agent_md" ] || continue
    [ "$(basename "$agent_md")" = "README.md" ] && continue
    if ! head -1 "$agent_md" | grep -q "^---$" 2>/dev/null && ! grep -q "^# " "$agent_md"; then
      fail "agent role-def missing frontmatter or top heading: $(basename "$agent_md")"
    fi
    body_size=$(wc -c < "$agent_md")
    if [ "$body_size" -lt 500 ]; then
      fail "agent role-def too short ($body_size bytes; likely placeholder): $(basename "$agent_md")"
    fi
  done
  ok "agent role-defs parse"
fi

# 4b. No C-suite in the roster. This preset exists BECAUSE its operator does
# not run a company; a cos/cto/cpo/cro/coo archetype creeping into
# agent_archetypes would silently restore the mismatch (an org chart for a
# company nobody here runs) that made the first briefing read as irrelevant.
for csuite in cos cto cpo cro coo compliance-officer operations-officer; do
  if grep -qE "^  - ${csuite}( |$)" "$preset_yml"; then
    fail "preset.yml declares a C-suite archetype: $csuite (this preset ships an IC-altitude roster)"
  fi
done
ok "roster carries no C-suite archetype"

# 4c. The self-improvement validation gate FAILS CLOSED on zero role/learning
# scenarios, so an activatable preset with no seed bricks it. Pin that the seed
# is present and registers under a category the gate collects.
if ! grep -rqE 'category\s*=\s*["'"'"'](role|learning)["'"'"']' "$PRESET_DIR/measurement/scenarios"; then
  fail "measurement/scenarios ships no role/learning scenario — the self-improvement gate would fail closed"
fi
ok "measurement seed registers a role/learning scenario"

# 5. mcp-scope.yml check (if preset declares one)
if [ -f "$PRESET_DIR/mcp-scope.yml" ]; then
  if ! grep -q "^agents:" "$PRESET_DIR/mcp-scope.yml" 2>/dev/null; then
    fail "mcp-scope.yml missing 'agents:' section"
  fi
  ok "mcp-scope.yml present + parsed"
fi

# 6. naming_style sanity
naming_style=$(grep "^naming_style:" "$preset_yml" | awk '{print $2}')
case "$naming_style" in
  functional|role-initials|personal) ok "naming_style: $naming_style" ;;
  *) fail "naming_style invalid: $naming_style (must be functional|role-initials|personal)" ;;
esac

echo "✅ Preset $PRESET_NAME validation PASSED"
exit 0
