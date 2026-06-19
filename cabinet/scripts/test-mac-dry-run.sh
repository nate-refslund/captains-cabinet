#!/bin/bash
# test-mac-dry-run.sh - Mac launch dry-run behavior without a Mac host.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
FAKE_BIN="$TMP_DIR/bin"
FAKE_REPO="$TMP_DIR/repo"

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

pass() { echo "  PASS: $1"; }
fail() { echo "  FAIL: $1" >&2; exit 1; }

echo "=== Mac dry-run eval ==="

mkdir -p "$FAKE_BIN" "$FAKE_REPO/cabinet/scripts" "$FAKE_REPO/cabinet" "$FAKE_REPO/.claude/agents"
ln -s "$REPO_ROOT/cabinet/scripts/start-officer-mac.sh" "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh"
cp "$REPO_ROOT/cabinet/officer-capabilities.conf" "$FAKE_REPO/cabinet/officer-capabilities.conf"
echo '{}' > "$FAKE_REPO/.mcp.json.mac-native"
echo '# cos' > "$FAKE_REPO/.claude/agents/cos.md"

cat > "$FAKE_BIN/claude" <<'SH'
#!/bin/sh
if [ "$1" = "--help" ]; then
  echo "Usage: claude --agent <name>"
elif [ "$1" = "--version" ]; then
  echo "2.1.150"
fi
SH
chmod +x "$FAKE_BIN/claude"

OUT="$(PATH="$FAKE_BIN:$PATH" CABINET_SOURCE_REPO="$FAKE_REPO" CABINET_MAC_DRY_RUN=1 bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" cos 2>/dev/null)"
printf '%s' "$OUT" | grep -q 'native_agent=true' \
  && pass "start-officer-mac detects native --agent support" \
  || fail "native agent support was not detected"
printf '%s' "$OUT" | grep -q -- '--agent cos' \
  && pass "start-officer-mac includes native agent flag" \
  || fail "native agent flag missing from command"
printf '%s' "$OUT" | grep -q "cd $FAKE_REPO" \
  && pass "start-officer-mac uses CABINET_SOURCE_REPO root" \
  || fail "CABINET_SOURCE_REPO root missing from command"

OUT="$(PATH="$FAKE_BIN:$PATH" CABINET_MAC_DRY_RUN=1 bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" cos 2>/dev/null)"
printf '%s' "$OUT" | grep -q "cd $FAKE_REPO" \
  && pass "start-officer-mac falls back to script-relative root" \
  || fail "script-relative repo root fallback missing"

cat > "$FAKE_BIN/claude" <<'SH'
#!/bin/sh
if [ "$1" = "--help" ]; then
  echo "Usage: claude"
elif [ "$1" = "--version" ]; then
  echo "2.1.150"
fi
SH
chmod +x "$FAKE_BIN/claude"

OUT="$(PATH="$FAKE_BIN:$PATH" CABINET_SOURCE_REPO="$FAKE_REPO" CABINET_MAC_DRY_RUN=1 bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" cos 2>/dev/null)"
printf '%s' "$OUT" | grep -q 'native_agent=false' \
  && pass "start-officer-mac falls back without --agent support" \
  || fail "fallback mode was not reported"

# --- T4 [FIX-4]: CABINET_LANE export from active-project.txt ---
# The Mac officer is single-project-per-LaunchAgent (no --project flag), so its
# lane source is instance/config/active-project.txt. resolve_lane() reads
# CABINET_LANE first, so the script MUST export it for per-lane bars to work.
cat > "$FAKE_BIN/claude" <<'SH'
#!/bin/sh
if [ "$1" = "--help" ]; then
  echo "Usage: claude --agent <name>"
elif [ "$1" = "--version" ]; then
  echo "2.1.150"
fi
SH
chmod +x "$FAKE_BIN/claude"
mkdir -p "$FAKE_REPO/instance/config"
printf 'sensed\n' > "$FAKE_REPO/instance/config/active-project.txt"
OUT="$(PATH="$FAKE_BIN:$PATH" CABINET_SOURCE_REPO="$FAKE_REPO" CABINET_MAC_DRY_RUN=1 bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" cos 2>/dev/null)"
printf '%s' "$OUT" | grep -q 'CABINET_LANE=sensed' \
  && pass "start-officer-mac exports CABINET_LANE from active-project.txt [FIX-4]" \
  || fail "CABINET_LANE export missing from mac dry-run output"

# No active-project.txt → no lane → must NOT export an empty CABINET_LANE
# (lets resolve_lane fall through to PROJECT/None — fail-safe to unmeasured).
rm -f "$FAKE_REPO/instance/config/active-project.txt"
OUT="$(PATH="$FAKE_BIN:$PATH" CABINET_SOURCE_REPO="$FAKE_REPO" CABINET_MAC_DRY_RUN=1 bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" cos 2>/dev/null)"
printf '%s' "$OUT" | grep -q 'CABINET_LANE=' \
  && fail "start-officer-mac leaked an empty CABINET_LANE export" \
  || pass "start-officer-mac omits CABINET_LANE when no active-project.txt (fail-safe)"

CABINET_SOURCE_REPO="$REPO_ROOT" bash "$REPO_ROOT/cabinet/scripts/deploy-mac.sh" --officer cos --dry-run > "$TMP_DIR/deploy.out"
grep -q '<key>CABINET_SOURCE_REPO</key>' "$TMP_DIR/deploy.out" \
  && grep -q '<key>CABINET_ROOT</key>' "$TMP_DIR/deploy.out" \
  || fail "officer plist did not export Cabinet root env vars"
pass "deploy-mac dry-run renders without envsubst dependency"

echo "=== Mac dry-run eval PASS ==="
