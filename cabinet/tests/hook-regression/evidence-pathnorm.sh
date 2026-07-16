#!/bin/bash
# evidence-pathnorm.sh — PR#140 Evidence Recorder read/write-boundary hardening.
#
# Pins the four P0/P1 officer-hook closures added for the Evidence Recorder v1
# boundary (pre-tool-use.sh §0a observe doorway, §5a raw-read inversion):
#   #1  path-normalization: the raw-store block matched a LITERAL
#       'instance/evidence/' substring, so a `..` dir-hop
#       (instance/config/../evidence/v1/.signing-key -> the HMAC signing key)
#       or a symlinked dir component dodged it. Fixed with normpath+realpath on
#       the native Read/Edit/Write arm and per-token normpath+realpath on the
#       Bash arm.
#   #2  the append-only store could be wiped: `rm -rf instance/x/../evidence/v1`
#       (and the bare-parent `rm -rf instance/evidence`, and `mv` moving the
#       store away) slipped the substring case and §5b's trailing-slash-only
#       GERM_PATH_RE. Fixed by the normpath fold + a dedicated target-anchored
#       rm/rmdir/unlink/shred/mv arm. (GERM_PATH_RE is left untouched — the
#       lockstep meta-test pins it to immutable-core.yml.)
#   #3  the safe doorways (observe-only §0a AND evidence-read §5a) allowed with
#       a LINE-ORIENTED grep -qE '^...$', so a two-line command whose first line
#       was the legit doorway smuggled the second line. Fixed by rejecting the
#       doorway for any multi-line command BEFORE the shape check.
#   #4  an interpreter importing the recorder modules dodged the dotted
#       `framework.evidence` substring via `from framework import evidence`.
#       Fixed with a fail-closed structural interpreter+module screen.
#
# Every BLOCK probe here ALLOWS (exit 0) on pre-fix 2f0253b7 and BLOCKS (exit 2)
# with the fix; every ALLOW probe stays exit 0 (no false-positive on the legit
# bounded doorways or ordinary source reads).
#
# Redis stub (fixtures/redis-cli, reachable + no kill-switch key) is put on PATH
# per probe so the fail-closed kill switch does not mask the evidence logic — the
# same pattern germline-readonly.sh uses. CABINET_HOOK_TEST_MODE=1 is set inline
# per probe (no global export).
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
HOOK="$REPO_ROOT/cabinet/scripts/hooks/pre-tool-use.sh"
TEST_BIN="$SCRIPT_DIR/fixtures"
PASS=0
FAIL=0

# Self-contained symlink fixture: <WORK>/instance/pub -> evidence, so a token
# <WORK>/instance/pub/v1/.signing-key realpath-resolves into a path containing
# '/instance/evidence/' WITHOUT mutating the repo tree. Torn down on exit.
WORK="$(mktemp -d 2>/dev/null || mktemp -d -t pr140)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/instance/evidence/v1"
ln -s evidence "$WORK/instance/pub"
SYMPATH="$WORK/instance/pub/v1/.signing-key"

# python3-unavailable fixture: a failing `python3` shadow so the §5a Bash
# normalizer's `... || printf '%s' "$EVIDENCE_READ_CMD"` fallback fires and
# EVIDENCE_CMD_NORM degrades to the UN-normalized command. This ISOLATES the
# destructive-verb arm: with no normalization the case block cannot fold a bare
# `instance/evidence` (no trailing slash) into a match, so ONLY the
# rm/rmdir/unlink/shred/mv arm blocks the store wipe. Under this fixture the arm
# is the sole blocker (proven load-bearing); on pristine 2f0253b7 the same
# command ALLOWS. Lives under WORK so the EXIT trap tears it down.
PYFAIL="$WORK/pyfail-bin"
mkdir -p "$PYFAIL"
printf '#!/bin/sh\nexit 1\n' > "$PYFAIL/python3"
chmod +x "$PYFAIL/python3"

# probe LABEL JSON EXPECTED [EXTRA_ENV]
probe() {
  local label="$1" payload="$2" expected="$3" extra="${4:-}" result exit_code verdict
  result=$(printf '%s' "$payload" | env $extra PATH="$TEST_BIN:$PATH" CABINET_HOOK_TEST_MODE=1 OFFICER_NAME=cto bash "$HOOK" 2>/dev/null; echo "EXIT:$?")
  exit_code="${result##*EXIT:}"
  if [ "$exit_code" = "$expected" ]; then
    verdict=PASS; PASS=$((PASS+1))
  else
    verdict=FAIL; FAIL=$((FAIL+1))
  fi
  printf "%-6s | %-56s | want=%s exit=%s\n" "$verdict" "$label" "$expected" "$exit_code"
}

# probe_pyfail LABEL JSON EXPECTED — like probe() but prepends the failing
# python3 shadow to PATH (redis stub stays reachable via $TEST_BIN). Used to
# isolate the destructive-verb arm from the realpath normalizer.
probe_pyfail() {
  local label="$1" payload="$2" expected="$3" result exit_code verdict
  result=$(printf '%s' "$payload" | env PATH="$PYFAIL:$TEST_BIN:$PATH" CABINET_HOOK_TEST_MODE=1 OFFICER_NAME=cto bash "$HOOK" 2>/dev/null; echo "EXIT:$?")
  exit_code="${result##*EXIT:}"
  if [ "$exit_code" = "$expected" ]; then
    verdict=PASS; PASS=$((PASS+1))
  else
    verdict=FAIL; FAIL=$((FAIL+1))
  fi
  printf "%-6s | %-56s | want=%s exit=%s\n" "$verdict" "$label" "$expected" "$exit_code"
}

echo "=== BLOCK: #1 path normalization (dir-hop + symlink component) ==="
probe "#1 Read .. dir-hop to signing key" \
  '{"tool_name":"Read","tool_input":{"file_path":"instance/config/../evidence/v1/.signing-key"}}' 2
probe "#1 Grep .. dir-hop into store" \
  '{"tool_name":"Grep","tool_input":{"path":"instance/x/../evidence/v1","pattern":"key"}}' 2
probe "#1 Read symlinked dir component" \
  "$(printf '{"tool_name":"Read","tool_input":{"file_path":"%s"}}' "$SYMPATH")" 2
probe "#1 Bash cat via symlinked dir component" \
  "$(printf '{"tool_name":"Bash","tool_input":{"command":"cat %s"}}' "$SYMPATH")" 2

echo "=== BLOCK: #2 append-only store deletion ==="
probe "#2 rm -rf .. into store" \
  '{"tool_name":"Bash","tool_input":{"command":"rm -rf instance/x/../evidence/v1"}}' 2
probe "#2 rm -rf bare-parent instance/evidence" \
  '{"tool_name":"Bash","tool_input":{"command":"rm -rf instance/evidence"}}' 2
probe "#2 rm -rf store direct" \
  '{"tool_name":"Bash","tool_input":{"command":"rm -rf instance/evidence/v1/"}}' 2
probe "#2 mv store away" \
  '{"tool_name":"Bash","tool_input":{"command":"mv instance/evidence /tmp/stash"}}' 2
probe "#2 escaped app-support delete" \
  '{"tool_name":"Bash","tool_input":{"command":"rm -rf ~/Library/Application\\ Support/cabinet/evidence/v1"}}' 2
# Isolates the destructive-verb arm from the realpath normalizer: python3 down
# → NORM un-normalized → the case block misses bare `instance/evidence` (no
# slash); only the rm arm blocks. Allows on pristine 2f0253b7 (no arm).
probe_pyfail "#2 rm bare-parent, normalizer bypassed (rm-arm is sole blocker)" \
  '{"tool_name":"Bash","tool_input":{"command":"rm -rf instance/evidence"}}' 2

echo "=== BLOCK: #3 line-oriented doorway smuggle (both doorways) ==="
probe "#3 evidence-read doorway + cat signing-key (2 line)" \
  '{"tool_name":"Bash","tool_input":{"command":"cabinet/scripts/evidence-read.sh DOGFOOD-001\ncat instance/evidence/v1/.signing-key"}}' 2
probe "#3 observe doorway + arbitrary 2nd line" \
  '{"tool_name":"Bash","tool_input":{"command":"cabinet/scripts/evidence-read.sh DOGFOOD-001\necho pwned > /tmp/pr140_should_never_run"}}' 2 "CABINET_OBSERVE_ONLY=1"

echo "=== BLOCK: #4 interpreter module import ==="
probe "#4 from framework import evidence" \
  '{"tool_name":"Bash","tool_input":{"command":"python3.12 -c \"from framework import evidence as e; print(e)\""}}' 2
probe "#4 from framework.onboarding import journey" \
  '{"tool_name":"Bash","tool_input":{"command":"python3.12 -c \"from framework.onboarding import journey\""}}' 2
probe "#4 stdin-fed python import" \
  '{"tool_name":"Bash","tool_input":{"command":"echo \"from framework import evidence\" | python3"}}' 2

echo "=== ALLOW: legit doorways stay open (no false-positive) ==="
probe "LEGIT evidence-read.sh <trial>" \
  '{"tool_name":"Bash","tool_input":{"command":"cabinet/scripts/evidence-read.sh DOGFOOD-001"}}' 0
probe "LEGIT observe-ack.sh <recipts>" \
  '{"tool_name":"Bash","tool_input":{"command":"cabinet/scripts/hooks/observe-ack.sh 12-34 56-78"}}' 0
probe "LEGIT evidence-read under observe-only" \
  '{"tool_name":"Bash","tool_input":{"command":"cabinet/scripts/evidence-read.sh DOGFOOD-001"}}' 0 "CABINET_OBSERVE_ONLY=1"
probe "LEGIT observe-ack under observe-only" \
  '{"tool_name":"Bash","tool_input":{"command":"cabinet/scripts/hooks/observe-ack.sh 1-2 3-4"}}' 0 "CABINET_OBSERVE_ONLY=1"
probe "LEGIT grep evidence in framework source" \
  '{"tool_name":"Bash","tool_input":{"command":"grep -rn evidence framework/onboarding"}}' 0
probe "LEGIT python unrelated to recorder" \
  '{"tool_name":"Bash","tool_input":{"command":"python3.12 -c \"print(1+1)\""}}' 0
probe "LEGIT read sibling instance/evidence-notes" \
  '{"tool_name":"Bash","tool_input":{"command":"cat instance/evidence-notes.md"}}' 0
probe "LEGIT ordinary onboarding doc read" \
  '{"tool_name":"Read","tool_input":{"file_path":"docs/onboarding/onboarding-v2-first-window.md"}}' 0

echo "=== Summary: PASS=$PASS  FAIL=$FAIL ==="
exit "$FAIL"
