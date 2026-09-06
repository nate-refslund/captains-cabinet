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

mkdir -p "$FAKE_BIN" "$FAKE_REPO/cabinet/scripts" "$FAKE_REPO/cabinet" \
  "$FAKE_REPO/.claude/agents" "$FAKE_REPO/instance/config"
ln -s "$REPO_ROOT/cabinet/scripts/start-officer-mac.sh" "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh"
ln -s "$REPO_ROOT/cabinet/scripts/lib" "$FAKE_REPO/cabinet/scripts/lib"
ln -s "$REPO_ROOT/cabinet/scripts/observe-only.sh" "$FAKE_REPO/cabinet/scripts/observe-only.sh"
ln -s "$REPO_ROOT/cabinet/scripts/gen-officer-mcp-config.py" "$FAKE_REPO/cabinet/scripts/gen-officer-mcp-config.py"
cp "$REPO_ROOT/cabinet/officer-capabilities.conf" "$FAKE_REPO/cabinet/officer-capabilities.conf"
cp "$REPO_ROOT/cabinet/mcp-scope.yml" "$FAKE_REPO/cabinet/mcp-scope.yml"
echo '{}' > "$FAKE_REPO/.mcp.json.mac-native"
echo '# cos' > "$FAKE_REPO/.claude/agents/cos.md"
printf 'git_repos: []\n' > "$FAKE_REPO/instance/config/platform.yml"

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
printf '%s' "$OUT" | grep -q 'env -i' \
  && ! printf '%s' "$OUT" | grep -q 'DASHBOARD_PASSWORD' \
  && pass "start-officer-mac launches from a clean environment without dashboard authority" \
  || fail "clean officer environment boundary missing"

printf 'active\n' > "$FAKE_REPO/instance/config/observe-only"
OUT="$(PATH="$FAKE_BIN:$PATH" CABINET_SOURCE_REPO="$FAKE_REPO" CABINET_MAC_DRY_RUN=1 bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" cos 2>/dev/null)"
printf '%s' "$OUT" | grep -q 'observe_only=1' \
  && printf '%s' "$OUT" | grep -q 'CABINET_ENV=<set>' \
  && pass "observe-only dry-run pins the process cap and dev dispatch environment" \
  || fail "observe-only process cap/dev dispatch environment missing"
rm -f "$FAKE_REPO/instance/config/observe-only"

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
printf 'testburg\n' > "$FAKE_REPO/instance/config/active-project.txt"
OUT="$(PATH="$FAKE_BIN:$PATH" CABINET_SOURCE_REPO="$FAKE_REPO" CABINET_MAC_DRY_RUN=1 bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" cos 2>/dev/null)"
printf '%s' "$OUT" | grep -q 'CABINET_LANE=testburg' \
  && pass "start-officer-mac exports CABINET_LANE from active-project.txt [FIX-4]" \
  || fail "CABINET_LANE export missing from mac dry-run output"

# No active-project.txt → no lane → must NOT export an empty CABINET_LANE
# (lets resolve_lane fall through to PROJECT/None — fail-safe to unmeasured).
rm -f "$FAKE_REPO/instance/config/active-project.txt"
OUT="$(PATH="$FAKE_BIN:$PATH" CABINET_SOURCE_REPO="$FAKE_REPO" CABINET_MAC_DRY_RUN=1 bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" cos 2>/dev/null)"
printf '%s' "$OUT" | grep -q 'CABINET_LANE=' \
  && fail "start-officer-mac leaked an empty CABINET_LANE export" \
  || pass "start-officer-mac omits CABINET_LANE when no active-project.txt (fail-safe)"

# Malformed/metachar active-project.txt → slug allowlist REJECTION path
# (start-officer-mac.sh:188 else/unset arm). A poisoned active-project.txt must
# NOT export CABINET_LANE — exercises the validation branch the present/absent
# cases above never reached. Variant a: spaces + bang. Variant b: cmd-separator.
INJ_SENTINEL="$(mktemp -u "$TMP_DIR/mac-inject.XXXXXX")"
printf 'Bad Slug!\n' > "$FAKE_REPO/instance/config/active-project.txt"
OUT="$(PATH="$FAKE_BIN:$PATH" CABINET_SOURCE_REPO="$FAKE_REPO" CABINET_MAC_DRY_RUN=1 bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" cos 2>/dev/null)"
printf '%s' "$OUT" | grep -q 'CABINET_LANE=' \
  && fail "start-officer-mac exported CABINET_LANE for a malformed slug (allowlist bypassed)" \
  || pass "start-officer-mac rejects malformed active-project.txt slug (no CABINET_LANE)"

printf 'a;touch %s\n' "$INJ_SENTINEL" > "$FAKE_REPO/instance/config/active-project.txt"
OUT="$(PATH="$FAKE_BIN:$PATH" CABINET_SOURCE_REPO="$FAKE_REPO" CABINET_MAC_DRY_RUN=1 bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" cos 2>/dev/null)"
printf '%s' "$OUT" | grep -q 'CABINET_LANE=' \
  && fail "start-officer-mac exported CABINET_LANE for a cmd-separator slug (allowlist bypassed)" \
  || { [ -e "$INJ_SENTINEL" ] \
       && fail "start-officer-mac cmd-separator slug FIRED a side-effect (RCE seam)" \
       || pass "start-officer-mac rejects cmd-separator active-project.txt slug (no CABINET_LANE, no side-effect)"; }
rm -f "$FAKE_REPO/instance/config/active-project.txt" "$INJ_SENTINEL"

# --- T5: strict arg contract (hatch-rehearsal fix 2026-07-07) ---
# a) --dry-run FLAG (no env var) must take the dry path — parity with
#    deploy-mac.sh's --dry-run, so an operator's natural guess is safe.
OUT="$(PATH="$FAKE_BIN:$PATH" CABINET_SOURCE_REPO="$FAKE_REPO" bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" cos --dry-run 2>/dev/null)"
printf '%s' "$OUT" | grep -q "cd $FAKE_REPO" \
  && pass "start-officer-mac honors the --dry-run flag (no env var needed)" \
  || fail "--dry-run flag did not produce the dry-run command output"

# b) Unknown flags must be REJECTED (exit 64), never silently ignored — a
#    mistyped flag falling through to the real path kills the live session.
RC=0
PATH="$FAKE_BIN:$PATH" CABINET_SOURCE_REPO="$FAKE_REPO" \
  bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" cos --bogus-flag >/dev/null 2>&1 || RC=$?
[ "$RC" = "64" ] \
  && pass "start-officer-mac rejects unknown flags with exit 64" \
  || fail "unknown flag was not rejected with exit 64 (got rc=$RC)"

# c) Missing officer arg → usage + exit 64 (not a bare set -u crash).
RC=0
PATH="$FAKE_BIN:$PATH" CABINET_SOURCE_REPO="$FAKE_REPO" \
  bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" >/dev/null 2>&1 || RC=$?
[ "$RC" = "64" ] \
  && pass "start-officer-mac exits 64 without an officer argument" \
  || fail "missing officer arg did not exit 64 (got rc=$RC)"

# d) Extra positional arg → exit 64.
RC=0
PATH="$FAKE_BIN:$PATH" CABINET_SOURCE_REPO="$FAKE_REPO" \
  bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" cos extra >/dev/null 2>&1 || RC=$?
[ "$RC" = "64" ] \
  && pass "start-officer-mac rejects extra positional args with exit 64" \
  || fail "extra positional arg was not rejected with exit 64 (got rc=$RC)"

CABINET_SOURCE_REPO="$REPO_ROOT" bash "$REPO_ROOT/cabinet/scripts/deploy-mac.sh" --officer cos --dry-run > "$TMP_DIR/deploy.out"
grep -q '<key>CABINET_SOURCE_REPO</key>' "$TMP_DIR/deploy.out" \
  && grep -q '<key>CABINET_ROOT</key>' "$TMP_DIR/deploy.out" \
  || fail "officer plist did not export Cabinet root env vars"
pass "deploy-mac dry-run renders without envsubst dependency"

# --- T6: runtime-constitution assembly FAILS CLOSED (2026-09-06) -------------
# The launcher assembles the runtime constitution + safety boundaries via
# load-preset.sh.  On a non-zero exit it used to log "may be incomplete" and
# CONTINUE, starting an officer whose own rules were of unknown provenance —
# while every sibling assembly failure in the same script already refuses
# (egress, security paths, sandbox, broker, one-shot launcher).
#
# CABINET_MAC_DRY_RUN=1 skips the whole assembly block, so NO test could reach
# that branch: it was an unsensored fail-open.  CABINET_MAC_TEST_ASSEMBLY=1 runs
# the assembly and then behaves like --dry-run, which makes both arms testable.
# Hermetic: scratch HOME (no writes to the live fleet's log dir), scratch
# CABINET_RUNTIME_DIR (never the live /tmp/cabinet-runtime bundle), stubbed
# load-preset/check-deps, and stub `claude`/`tmux` that record any invocation.
echo
echo "T6: constitution assembly fail-closed"

ASM_HOME="$TMP_DIR/asm-home"
ASM_RUNTIME="$TMP_DIR/asm-runtime"
mkdir -p "$ASM_HOME" "$ASM_RUNTIME"
CLAUDE_SENTINEL="$TMP_DIR/asm-claude-invoked"
TMUX_SENTINEL="$TMP_DIR/asm-tmux-invoked"
PRESET_SENTINEL="$TMP_DIR/asm-load-preset-invoked"

cat > "$FAKE_BIN/claude" <<SH
#!/bin/sh
: >> "$CLAUDE_SENTINEL"
if [ "\$1" = "--help" ]; then
  echo "Usage: claude --agent <name>"
elif [ "\$1" = "--version" ]; then
  echo "2.1.150"
fi
SH
chmod +x "$FAKE_BIN/claude"

# Any boot step is a recorded, non-zero failure — the launcher must never reach
# tmux at all in these arms, and if it ever does the arm fails loudly.
cat > "$FAKE_BIN/tmux" <<SH
#!/bin/sh
: >> "$TMUX_SENTINEL"
exit 1
SH
chmod +x "$FAKE_BIN/tmux"

cat > "$FAKE_REPO/cabinet/scripts/check-deps.sh" <<'SH'
#!/bin/sh
exit 0
SH
chmod +x "$FAKE_REPO/cabinet/scripts/check-deps.sh"

run_assembly_arm() {  # $1 = load-preset stub exit code → sets ARM_RC / ARM_OUT / ARM_ERR
  cat > "$FAKE_REPO/cabinet/scripts/load-preset.sh" <<SH
#!/bin/sh
: >> "$PRESET_SENTINEL"
echo "[load-preset stub] rc=$1" >&2
exit $1
SH
  chmod +x "$FAKE_REPO/cabinet/scripts/load-preset.sh"
  rm -f "$CLAUDE_SENTINEL" "$TMUX_SENTINEL" "$PRESET_SENTINEL"
  ARM_RC=0
  ARM_OUT="$(HOME="$ASM_HOME" PATH="$FAKE_BIN:$PATH" CABINET_SOURCE_REPO="$FAKE_REPO" \
    CABINET_RUNTIME_DIR="$ASM_RUNTIME" CABINET_MAC_TEST_ASSEMBLY=1 \
    bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" cos 2>"$TMP_DIR/asm.err")" || ARM_RC=$?
  ARM_ERR="$(cat "$TMP_DIR/asm.err")"
}

# T6a: load-preset FAILS → refuse the boot, before any boot step.
run_assembly_arm 1
[ -e "$PRESET_SENTINEL" ] \
  && pass "T6a: CABINET_MAC_TEST_ASSEMBLY=1 actually runs the assembly block" \
  || fail "T6a: assembly block was skipped — the arm below would pass vacuously"
[ "$ARM_RC" = "78" ] \
  && pass "T6a: failed constitution assembly refuses the boot (exit 78)" \
  || fail "T6a: failed constitution assembly did not exit 78 (got rc=$ARM_RC)"
printf '%s' "$ARM_OUT" | grep -q 'dangerously-skip-permissions' \
  && fail "T6a: launcher still assembled a claude command after a failed assembly" \
  || pass "T6a: no claude command assembled after a failed assembly"
[ -e "$CLAUDE_SENTINEL" ] \
  && fail "T6a: claude was invoked after a failed constitution assembly" \
  || pass "T6a: claude never invoked after a failed constitution assembly"
[ -e "$TMUX_SENTINEL" ] \
  && fail "T6a: tmux was invoked after a failed constitution assembly" \
  || pass "T6a: tmux never invoked after a failed constitution assembly"
printf '%s' "$ARM_ERR" | grep -q 'REFUSING to boot' \
  && printf '%s' "$ARM_ERR" | grep -q 'load-preset.sh' \
  && printf '%s' "$ARM_ERR" | grep -qF "$ASM_RUNTIME" \
  && pass "T6a: refusal names the failure, the bundle path and the recovery" \
  || fail "T6a: refusal message missing recovery detail — $ARM_ERR"

# T6b: load-preset SUCCEEDS → the pre-existing path is untouched (still renders
# the full boot command and still probes the claude CLI).
run_assembly_arm 0
[ "$ARM_RC" = "0" ] \
  && pass "T6b: successful assembly still exits 0" \
  || fail "T6b: successful assembly exited rc=$ARM_RC — $ARM_ERR"
printf '%s' "$ARM_OUT" | grep -q "cd $FAKE_REPO" \
  && printf '%s' "$ARM_OUT" | grep -q 'dangerously-skip-permissions' \
  && pass "T6b: successful assembly still assembles the officer boot command" \
  || fail "T6b: boot command missing after a successful assembly — $ARM_OUT"
[ -e "$CLAUDE_SENTINEL" ] \
  && pass "T6b: successful assembly reaches the claude capability probe" \
  || fail "T6b: claude was never probed — execution stopped before the boot path"

# T6c: plain --dry-run must STILL skip the assembly block (the knob changes
# nothing for the rehearsal path hatch.sh proof-c1 depends on).
rm -f "$PRESET_SENTINEL" "$CLAUDE_SENTINEL" "$TMUX_SENTINEL"
HOME="$ASM_HOME" PATH="$FAKE_BIN:$PATH" CABINET_SOURCE_REPO="$FAKE_REPO" \
  CABINET_RUNTIME_DIR="$ASM_RUNTIME" CABINET_MAC_DRY_RUN=1 \
  bash "$FAKE_REPO/cabinet/scripts/start-officer-mac.sh" cos >/dev/null 2>&1
[ -e "$PRESET_SENTINEL" ] \
  && fail "T6c: --dry-run now runs load-preset — rehearsal gained a side effect" \
  || pass "T6c: --dry-run still skips the assembly block (no side effects)"

rm -f "$FAKE_REPO/cabinet/scripts/load-preset.sh" "$FAKE_REPO/cabinet/scripts/check-deps.sh" \
      "$FAKE_BIN/tmux"

echo "=== Mac dry-run eval PASS ==="
