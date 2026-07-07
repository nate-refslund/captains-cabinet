#!/usr/bin/env bash
# presets/_template/validate.sh
# Preset validation gate — ships with the template so every preset created
# from it (cp -r presets/_template presets/<your-slug>) inherits the gate.
# Run by cabinet-bootstrap.sh / cabinet-spawn.sh BEFORE any session starts;
# bootstrap HARD-FAILS a preset that has no validate.sh (AC #66), so a copied
# preset must carry this file. Non-zero exit aborts bootstrap/spawn.
#
# Mirrors the generic pattern in presets/{work,portfolio}/validate.sh,
# plus one template-specific check: every REPLACE_ME scaffold marker must be
# customized away before the copied preset validates.

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

# 0. The template itself is never a loadable preset (load-preset.sh rejects
#    it too). Running this gate in place means someone skipped the copy step.
if [ "$PRESET_NAME" = "_template" ]; then
  fail "_template is not a loadable preset. Copy it to presets/<your-slug>/ and customize every REPLACE_ME marker first."
fi

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

# 2. REPLACE_ME scaffold markers customized away (template-specific check).
#    Scans the loaded config surface — the files load-preset.sh assembles —
#    not README.md or agents/TEMPLATE.md, which may stay as reference.
for f in preset.yml terminology.yml constitution-addendum.md safety-addendum.md schemas.sql; do
  if grep -q "REPLACE_ME" "$PRESET_DIR/$f"; then
    fail "$f still contains REPLACE_ME scaffold markers — customize it before loading (see presets/_template/README.md checklist)"
  fi
done
ok "no REPLACE_ME scaffold markers remain"

# 3. Addenda non-empty + length sanity (no placeholder-only)
for addendum in constitution-addendum.md safety-addendum.md; do
  size=$(wc -c < "$PRESET_DIR/$addendum")
  if [ "$size" -lt 200 ]; then
    fail "$addendum is suspiciously short ($size bytes; <200 = likely placeholder)"
  fi
done
ok "addenda non-empty"

# 4. preset.yml schema check (key fields)
preset_yml="$PRESET_DIR/preset.yml"
for key in name description naming_style agent_archetypes terminology workspace_mount; do
  if ! grep -q "^${key}:" "$preset_yml"; then
    fail "preset.yml missing required key: $key"
  fi
done
ok "preset.yml schema valid"

# 5. Agent role-defs parse (frontmatter + non-empty body)
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

# 6. mcp-scope.yml check (if preset declares one)
if [ -f "$PRESET_DIR/mcp-scope.yml" ]; then
  if ! grep -q "^agents:" "$PRESET_DIR/mcp-scope.yml" 2>/dev/null; then
    fail "mcp-scope.yml missing 'agents:' section"
  fi
  ok "mcp-scope.yml present + parsed"
fi

# 7. naming_style sanity
naming_style=$(grep "^naming_style:" "$preset_yml" | awk '{print $2}')
case "$naming_style" in
  functional|role-initials|personal) ok "naming_style: $naming_style" ;;
  *) fail "naming_style invalid: $naming_style (must be functional|role-initials|personal)" ;;
esac

echo "✅ Preset $PRESET_NAME validation PASSED"
exit 0
