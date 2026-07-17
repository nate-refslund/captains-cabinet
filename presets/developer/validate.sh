#!/usr/bin/env bash
# presets/developer/validate.sh
# Preset validation gate (Spec 034 v3 AC #49 — CRO H3 fix), developer twin
# of presets/work/validate.sh plus two developer-specific asserts:
#   7. framework-neutrality of the onboarding block (no instance plugin ids,
#      cabinet_default_plugins stays empty by design)
#   8. personal-residue battery (no mother-instance names/products/tools)
# Run by cabinet-spawn.sh BEFORE any container starts. Non-zero exit aborts spawn.
#
# Checks required files, addenda content, preset.yml schema, and agent role-defs.

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

# 7. Framework-neutrality of the onboarding block (developer-specific).
# A shipped preset must never re-import instance-specific tooling: the
# corridor/brain plugin ids were de-instanced from ALL shipped presets
# (2026-07-17 prerequisite commit) and cabinet_default_plugins is empty by
# design — no plugin is cabinet-universal.
onboarding_block="$(awk '/^onboarding:/{flag=1} flag' "$preset_yml")"
if [ -n "$onboarding_block" ]; then
  if printf '%s\n' "$onboarding_block" | grep -v '^\s*#' | grep -qE '\b(corridor|brain)\b'; then
    fail "onboarding block re-imports instance-specific plugin ids (corridor/brain) — those belong to instance/config/extensions.yml, never a shipped preset"
  fi
  plugins_line="$(printf '%s\n' "$onboarding_block" | grep -E '^\s*cabinet_default_plugins:' | head -1 || true)"
  if [ -n "$plugins_line" ] && ! printf '%s\n' "$plugins_line" | grep -qE 'cabinet_default_plugins:\s*\[\s*\]'; then
    fail "cabinet_default_plugins must stay [] in a shipped preset (deployments add plugins via instance overlays): $plugins_line"
  fi
fi
ok "onboarding block framework-neutral"

# 8. Personal-residue battery (developer-specific): the preset ships to every
# fork — zero mother-instance residue (names, employers, products, personal
# tooling). Case-insensitive; word-bounded short tokens (\bnate\b — else
# "coordinate"/"designate" false-positive); this script excludes itself
# (it must carry the pattern to enforce it — the repo-level parity test
# sweeps validate.sh too).
residue_pattern='\bnate\b|refslund|naref|polads|stephie|jobdanmark|\bjfm\b|jysk|stepnetwork|step network|screenpipe|obsidian'
if residue_hits=$(grep -rniE "$residue_pattern" "$PRESET_DIR" --exclude-dir=__pycache__ --exclude=validate.sh 2>/dev/null); then
  fail "personal residue found:
$residue_hits"
fi
ok "personal-residue battery clean"

echo "✅ Preset $PRESET_NAME validation PASSED"
exit 0
